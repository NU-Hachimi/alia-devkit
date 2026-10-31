# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""The .acart file (the cart docs, docs/cart.md): a SquashFS image of a cart directory followed by
a 4 KiB trailer, so the system can read the manifest and check the file without
mounting it. SquashFS ignores anything after its own bytes_used, so the image mounts
as is (squashfuse, or the kernel for gzip images).

Trailer (little-endian, at file size - 4096):
  0   4  magic b"ACRT"
  4   2  trailer version (1)
  6   2  flags: bit 0 = signed
  8   8  image size (bytes before the trailer)
  16  32 SHA-256 of the image
  48  4  manifest length
  52  32 signing key id: SHA-256 of the raw ed25519 public key (zero when unsigned)
  84  64 ed25519 signature of SIG_DOMAIN + image SHA-256 + manifest SHA-256
  148 .. the manifest (cart.toml, exactly as in the image), zero padded
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import cart as cartlib

MAGIC = b"ACRT"
VERSION = 1
TRAILER_SIZE = 4096
HEAD = struct.Struct("<4sHHQ32sI32s64s")
MANIFEST_MAX = TRAILER_SIZE - HEAD.size
FLAG_SIGNED = 1
SIG_DOMAIN = b"alia-acart-v1\0"
COMPRESSORS = ("zstd", "gzip")  # squashfuse reads both; the board's kernel only gzip


class AcartError(ValueError):
    pass


@dataclass
class Trailer:
    image_size: int
    sha256: bytes
    manifest: str
    signed: bool
    key_id: bytes
    signature: bytes

    def signed_message(self) -> bytes:
        return SIG_DOMAIN + self.sha256 + hashlib.sha256(self.manifest.encode()).digest()


def read_trailer(path: str | Path) -> Trailer:
    path = Path(path)
    size = path.stat().st_size
    if size < TRAILER_SIZE + 4096:
        raise AcartError(f"{path}: too small to be an .acart")
    with open(path, "rb") as f:
        f.seek(size - TRAILER_SIZE)
        raw = f.read(TRAILER_SIZE)
    magic, ver, flags, image_size, sha, mlen, key_id, sig = HEAD.unpack_from(raw)
    if magic != MAGIC:
        raise AcartError(f"{path}: not an .acart (no trailer)")
    if ver > VERSION:
        raise AcartError(f"{path}: trailer version {ver} is newer than this system understands")
    if image_size != size - TRAILER_SIZE or mlen > MANIFEST_MAX:
        raise AcartError(f"{path}: damaged trailer")
    try:
        manifest = raw[HEAD.size:HEAD.size + mlen].decode("utf-8")
    except UnicodeDecodeError:
        raise AcartError(f"{path}: damaged manifest") from None
    return Trailer(image_size, sha, manifest, bool(flags & FLAG_SIGNED), key_id, sig)


def image_sha256(path: str | Path, size: int) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = size
        while left:
            chunk = f.read(min(left, 1 << 20))
            if not chunk:
                raise AcartError(f"{path}: truncated")
            h.update(chunk)
            left -= len(chunk)
    return h.digest()


# ---- keys (ed25519; raw 32-byte public keys, stored as hex)

def key_id(public_raw: bytes) -> bytes:
    return hashlib.sha256(public_raw).digest()


def keygen(path: str | Path) -> Path:
    """Write a private key (PEM, mode 600) to PATH and its public key to PATH.pub."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    path = Path(path)
    k = Ed25519PrivateKey.generate()
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    Path(f"{path}.pub").write_text(f"ed25519 {pub.hex()}\n")
    return Path(f"{path}.pub")


def load_public(path: str | Path) -> bytes:
    kind, hexkey = Path(path).read_text().split()[:2]
    if kind != "ed25519" or len(hexkey) != 64:
        raise AcartError(f"{path}: not an ed25519 public key")
    return bytes.fromhex(hexkey)


def trusted_keys(dirs: list[Path]) -> dict[bytes, bytes]:
    """key id -> raw public key, from *.pub files in the given directories."""
    keys = {}
    for d in dirs:
        for p in sorted(d.glob("*.pub")) if d.is_dir() else []:
            try:
                raw = load_public(p)
            except (AcartError, ValueError, OSError):
                continue
            keys[key_id(raw)] = raw
    return keys


def verify(path: str | Path, keys: dict[bytes, bytes], allow_unsigned: bool) -> Trailer:
    """Check the image hash and the signature. Raises AcartError on any problem."""
    t = read_trailer(path)
    if image_sha256(path, t.image_size) != t.sha256:
        raise AcartError(f"{path}: contents don't match the trailer (damaged or modified)")
    if t.signed:
        raw = keys.get(t.key_id)
        if raw is None:
            raise AcartError(f"{path}: signed with an unknown key {t.key_id.hex()[:16]}")
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(t.signature, t.signed_message())
        except InvalidSignature:
            raise AcartError(f"{path}: bad signature") from None
    elif not allow_unsigned:
        raise AcartError(f"{path}: not signed (unsigned carts need developer mode)")
    return t


# ---- packing

def find_mksquashfs() -> str:
    for p in (shutil.which("mksquashfs"), str(Path(sys.executable).parent / "mksquashfs")):
        if p and Path(p).exists():
            return p
    raise AcartError("mksquashfs not found (conda: squashfs-tools; Debian: squashfs-tools)")


def pack(src: str | Path, out: str | Path, key: str | Path | None = None, comp: str = "zstd") -> Trailer:
    """Pack an unpacked cart directory into an .acart. Reproducible: same input, same bytes."""
    src = Path(src)
    cart = cartlib.load(src)  # validates, including art and entry paths
    if cart.dev:
        raise AcartError(f"{src}: dev carts (cart.dev = true) can't be packed; they run from a directory")
    if comp not in COMPRESSORS:
        raise AcartError(f"compressor {comp} not one of {COMPRESSORS}")
    manifest = (src / cartlib.MANIFEST).read_text(encoding="utf-8")
    if len(manifest.encode()) > MANIFEST_MAX:
        raise AcartError(f"{src}: cart.toml is larger than {MANIFEST_MAX} bytes")
    out = Path(out)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        img = Path(tmp) / "image"
        subprocess.run([find_mksquashfs(), str(src), str(img), "-comp", comp, "-b", "128K", "-noappend",
                        "-all-root", "-no-xattrs", "-mkfs-time", "0", "-all-time", "0", "-quiet"],
                       check=True, stdout=subprocess.DEVNULL)
        size = img.stat().st_size  # mksquashfs pads to 4 KiB
        sha = image_sha256(img, size)
        t = Trailer(size, sha, manifest, False, bytes(32), bytes(64))
        if key is not None:
            from cryptography.hazmat.primitives import serialization
            k = serialization.load_pem_private_key(Path(key).read_bytes(), password=None)
            pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            t.signed, t.key_id, t.signature = True, key_id(pub), k.sign(t.signed_message())
        head = HEAD.pack(MAGIC, VERSION, FLAG_SIGNED if t.signed else 0, size, sha,
                         len(manifest.encode()), t.key_id, t.signature)
        raw = head + manifest.encode()
        with open(img, "ab") as f:
            f.write(raw + bytes(TRAILER_SIZE - len(raw)))
        os.replace(img, out)
    return t
