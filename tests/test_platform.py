"""Platform baseline and the native-file check (pytest sdk)."""
import struct
from pathlib import Path

from alia import cart as cartlib
from alia import elf, platform

MANIFEST = """[cart]
id = "com.example.native"
title = "Native"
version = "1.0.0"
{extra}
[runtime]
type = "native"
entry = "game"
"""


def make_elf(machine: int, needed: list[str], runpath: str = "") -> bytes:
    """A minimal ELF64 LE: header, .dynstr, .dynamic and a section table; enough for elf.read."""
    strtab = b"\0"
    offsets = []
    for s in needed + ([runpath] if runpath else []):
        offsets.append(len(strtab))
        strtab += s.encode() + b"\0"
    dyn = b"".join(struct.pack("<qQ", elf.DT_NEEDED, o) for o in offsets[:len(needed)])
    if runpath:
        dyn += struct.pack("<qQ", elf.DT_RUNPATH, offsets[-1])
    dyn += struct.pack("<qQ", 0, 0)
    str_off = 64
    dyn_off = str_off + len(strtab)
    sh_off = dyn_off + len(dyn)
    header = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    header += struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 0, sh_off, 0, 64, 0, 0, 64, 3, 0)
    null = bytes(64)
    sh_str = struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0, str_off, len(strtab), 0, 0, 1, 0)
    sh_dyn = struct.pack("<IIQQQQIIQQ", 0, elf.SHT_DYNAMIC, 0, 0, dyn_off, len(dyn), 1, 0, 8, 16)
    return header + strtab + dyn + null + sh_str + sh_dyn


def cart_with(tmp: Path, files: dict, extra="") -> cartlib.Cart:
    root = tmp / "c"
    (root / "content").mkdir(parents=True)
    (root / "cart.toml").write_text(MANIFEST.format(extra=extra))
    for rel, data in files.items():
        p = root / "content" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return cartlib.load(root)


def test_elf_reader():
    data = make_elf(elf.EM_AARCH64, ["libSDL3.so.0", "libc.so.6"], "$ORIGIN/lib")
    import tempfile
    with tempfile.NamedTemporaryFile() as f:
        f.write(data)
        f.flush()
        e = elf.read(Path(f.name))
    assert e.machine == elf.EM_AARCH64 and e.needed == ["libSDL3.so.0", "libc.so.6"] and e.rpath == ["$ORIGIN/lib"]


def test_platform_libs_pass(tmp_path):
    c = cart_with(tmp_path, {"game": make_elf(elf.EM_AARCH64, ["libSDL3.so.0", "libGLESv2.so.2", "libc.so.6"])})
    assert platform.check(c) == ([], [])


def test_missing_lib_and_bundled_lib(tmp_path):
    c = cart_with(tmp_path, {"game": make_elf(elf.EM_AARCH64, ["libfoo.so.1", "libc.so.6"])})
    problems, _ = platform.check(c)
    assert len(problems) == 1 and "libfoo.so.1" in problems[0] and "content/lib" in problems[0]
    # carried in content/lib and found through $ORIGIN/lib: fine (the library is checked too)
    c = cart_with(tmp_path / "b", {"game": make_elf(elf.EM_AARCH64, ["libfoo.so.1"], "$ORIGIN/lib"),
                                   "lib/libfoo.so.1": make_elf(elf.EM_AARCH64, ["libc.so.6"])})
    assert platform.check(c) == ([], [])


def test_wrong_machine_and_outside_runpath(tmp_path):
    c = cart_with(tmp_path, {"game": make_elf(62, ["libc.so.6"])})
    problems, _ = platform.check(c)
    assert problems and "x86-64" in problems[0]
    c = cart_with(tmp_path / "b", {"game": make_elf(elf.EM_AARCH64, ["libc.so.6"], "/home/me/build/lib")})
    problems, notes = platform.check(c)
    assert not problems and "outside the cart" in notes[0]


def test_platform_version():
    assert platform.version() == "1.0" and platform.supports("1.0")
    assert not platform.supports("1.9") and not platform.supports("2.0")
    assert "libSDL3.so.0" in platform.sonames()


def test_cart_platform_field(tmp_path):
    c = cart_with(tmp_path, {}, extra='platform = "2.0"')
    problems, _ = platform.check(c)
    assert problems and "baseline" in problems[0]
