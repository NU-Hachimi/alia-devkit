""".acart packing, trailer, signatures (pytest sdk). Needs mksquashfs (conda squashfs-tools)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from alia import acart_file as af

pytestmark = pytest.mark.skipif(
    not (shutil.which("mksquashfs") or (Path(sys.executable).parent / "mksquashfs").exists()),
    reason="mksquashfs not installed")

MANIFEST = """[cart]
id = "com.example.packed"
title = "Packed"
version = "1.2.0"
[runtime]
type = "python"
entry = "main.py"
"""


@pytest.fixture
def cart_dir(tmp_path):
    d = tmp_path / "src"
    (d / "content").mkdir(parents=True)
    (d / "content" / "main.py").write_text("print('hello')\n")
    (d / "icon.png").write_bytes(b"\x89PNG fake")
    (d / "cart.toml").write_text(MANIFEST)
    return d


def test_pack_and_read(cart_dir, tmp_path):
    out = tmp_path / "x.acart"
    t = af.pack(cart_dir, out)
    r = af.read_trailer(out)
    assert r.manifest == MANIFEST and not r.signed and r.image_size == out.stat().st_size - af.TRAILER_SIZE
    assert r.image_size % 4096 == 0 and r.sha256 == t.sha256
    af.verify(out, {}, allow_unsigned=True)
    with pytest.raises(af.AcartError, match="developer mode"):
        af.verify(out, {}, allow_unsigned=False)


def test_reproducible(cart_dir, tmp_path):
    a, b = tmp_path / "a.acart", tmp_path / "b.acart"
    af.pack(cart_dir, a)
    (cart_dir / "content" / "main.py").touch()  # a new mtime alone must not change the image
    af.pack(cart_dir, b)
    assert a.read_bytes() == b.read_bytes()


def test_tampering_detected(cart_dir, tmp_path):
    out = tmp_path / "x.acart"
    af.pack(cart_dir, out)
    raw = bytearray(out.read_bytes())
    raw[100] ^= 0xFF
    out.write_bytes(bytes(raw))
    with pytest.raises(af.AcartError, match="don't match"):
        af.verify(out, {}, allow_unsigned=True)
    out.write_bytes(b"\0" * 20000)
    with pytest.raises(af.AcartError, match="not an .acart"):
        af.read_trailer(out)


def test_signed(cart_dir, tmp_path):
    key = tmp_path / "dev.key"
    pub = af.keygen(key)
    assert oct(key.stat().st_mode & 0o777) == "0o600"
    out = tmp_path / "s.acart"
    af.pack(cart_dir, out, key=key)
    keys = af.trusted_keys([tmp_path])
    t = af.verify(out, keys, allow_unsigned=False)
    assert t.signed and t.key_id == af.key_id(af.load_public(pub))
    with pytest.raises(af.AcartError, match="unknown key"):
        af.verify(out, {}, allow_unsigned=False)
    # a different manifest under the same signature is rejected
    raw = bytearray(out.read_bytes())
    i = raw.rindex(b"1.2.0")
    raw[i:i + 5] = b"9.9.9"
    out.write_bytes(bytes(raw))
    with pytest.raises(af.AcartError, match="bad signature"):
        af.verify(out, keys, allow_unsigned=False)


def test_dev_carts_are_not_packed(tmp_path, cart_dir):
    (cart_dir / "cart.toml").write_text(MANIFEST.replace('version = "1.2.0"', 'version = "1"\ndev = true'))
    with pytest.raises(af.AcartError, match="dev carts"):
        af.pack(cart_dir, tmp_path / "x.acart")


@pytest.mark.skipif(not (shutil.which("squashfuse") or (Path(sys.executable).parent / "squashfuse").exists())
                    or not shutil.which("fusermount3"), reason="squashfuse / fusermount3 missing")
def test_image_mounts(cart_dir, tmp_path):
    out = tmp_path / "x.acart"
    af.pack(cart_dir, out)
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    sqfuse = shutil.which("squashfuse") or str(Path(sys.executable).parent / "squashfuse")
    subprocess.run([sqfuse, str(out), str(mnt)], check=True)
    try:
        assert (mnt / "cart.toml").read_text() == MANIFEST
        assert (mnt / "content" / "main.py").read_text() == "print('hello')\n"
    finally:
        subprocess.run(["fusermount3", "-u", str(mnt)], check=True)
