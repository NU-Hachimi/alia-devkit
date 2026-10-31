"""alia.save tests, and that the C header (sdk/include/alia/save.h) reads the same files."""
import errno
import shutil
import subprocess
from pathlib import Path

import pytest

from alia import save

HERE = Path(__file__).resolve().parent
# the C header and its test: sdk/include and sdk/save here, include/ and tests/ in the devkit
INCLUDE = HERE.parent / "include"
C_TEST = next(p for p in (HERE / "test_save.c", HERE.parent / "save" / "test_save.c") if p.exists())


@pytest.fixture
def d(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIA_SAVE_DIR", str(tmp_path))
    monkeypatch.delenv("ALIA_SAVE_QUOTA_KB", raising=False)
    return tmp_path


def test_versions_and_fallback(d):
    assert save.read("slot") is None
    for v in (b"one", b"two", b"three", b"four"):
        save.write("slot", v)
    assert save.read("slot") == b"four"
    assert [v for v, _, _ in save.versions("slot")] == [0, 1, 2]
    assert (d / "slot.~2~").read_bytes() == b"two"
    (d / "slot").unlink()                        # a crash between the renames
    assert save.read("slot") == b"three"
    save.rollback("slot", 1)
    assert save.read("slot") == b"three"
    assert save.names() == ["slot"]
    save.delete("slot")
    assert save.read("slot") is None and list(d.iterdir()) == []


def test_names_and_quota(d, monkeypatch):
    for bad in ("../x", ".hidden", "a.tmp", "a~b", "x" * 65, ""):
        with pytest.raises(ValueError):
            save.write(bad, b"")
    monkeypatch.setenv("ALIA_SAVE_QUOTA_KB", "1")
    with pytest.raises(OSError) as e:
        save.write("big", b"\0" * 2048)
    assert e.value.errno == errno.ENOSPC
    save.write("small", b"\0" * 100)


def test_no_dir(monkeypatch):
    monkeypatch.delenv("ALIA_SAVE_DIR", raising=False)
    with pytest.raises(OSError):
        save.read("x")


@pytest.mark.skipif(not shutil.which("cc"), reason="no C compiler")
def test_c_reads_python_and_back(d, tmp_path_factory):
    exe = tmp_path_factory.mktemp("bin") / "test_save"
    subprocess.run(["cc", "-std=c99", "-O1", f"-I{INCLUDE}", "-o", str(exe), str(C_TEST)], check=True)
    save.write("from-py", b"hello C")
    assert subprocess.run([exe, "read", str(d), "from-py"], capture_output=True, text=True).stdout == "hello C"
    for v in ("a", "b", "c"):
        subprocess.run([exe, "write", str(d), "from-c", v], check=True)
    assert save.read("from-c") == b"c" and [v for v, _, _ in save.versions("from-c")] == [0, 1, 2]
    assert save.names() == ["from-c", "from-py"]
