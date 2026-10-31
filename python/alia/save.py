# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""Saves for carts (the C API is include/alia/save.h, same files and rules).

Saves live in $ALIA_SAVE_DIR (/save inside the sandbox). Each save is a named file:
  write(name, data)   atomic (temp file, fsync, rename, fsync the directory); the two
                      previous versions are kept as NAME.~1~ and NAME.~2~
  read(name)          the newest readable version, or None
  names()             saves that exist
  versions(name)      [(version, size, mtime)], 0 = current
  rollback(name, n)   make version n current (the current one becomes ~1~, so it can be undone)
  delete(name)        all versions
Writes that would take the directory over $ALIA_SAVE_QUOTA_KB (the manifest's
[save] quota_kb) raise OSError(ENOSPC). Names: letters, digits, '.', '_', '-'; up to
64 characters, not starting with '.'.
"""
from __future__ import annotations

import errno
import os
import re
from pathlib import Path

KEEP = 2  # previous versions kept
NAME_MAX = 64
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _dir(base: str | os.PathLike | None) -> Path:
    d = base or os.environ.get("ALIA_SAVE_DIR")
    if not d:
        raise OSError(errno.ENOENT, "ALIA_SAVE_DIR is not set (not running as a cart?)")
    return Path(d)


def _check(name: str):
    if not _NAME.match(name) or name.endswith(".tmp") or "~" in name:
        raise ValueError(f"bad save name {name!r}")


def _version(d: Path, name: str, n: int) -> Path:
    return d / (name if n == 0 else f"{name}.~{n}~")


def _quota() -> int | None:
    q = os.environ.get("ALIA_SAVE_QUOTA_KB")
    return int(q) * 1024 if q else None


def _fsync_dir(d: Path):
    fd = os.open(d, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(name: str, data: bytes, base=None):
    _check(name)
    d = _dir(base)
    q = _quota()
    if q is not None:
        used = sum(p.stat().st_size for p in d.iterdir() if p.is_file())
        dropped = _version(d, name, KEEP)
        if used - (dropped.stat().st_size if dropped.exists() else 0) + len(data) > q:
            raise OSError(errno.ENOSPC, f"save quota of {q // 1024} KB exceeded")
    tmp = d / f".{name}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)
    for n in range(KEEP, 0, -1):  # ~1~ -> ~2~, current -> ~1~
        older = _version(d, name, n - 1)
        if older.exists():
            os.replace(older, _version(d, name, n))
    os.replace(tmp, _version(d, name, 0))  # a crash before this leaves ~1~, which read() falls back to
    _fsync_dir(d)


def read(name: str, base=None) -> bytes | None:
    _check(name)
    d = _dir(base)
    for n in range(KEEP + 1):
        try:
            return _version(d, name, n).read_bytes()
        except FileNotFoundError:
            continue
    return None


def names(base=None) -> list[str]:
    d = _dir(base)
    out = set()
    for p in d.iterdir():
        n = re.sub(r"\.~\d+~$", "", p.name)
        if not p.name.startswith(".") and _NAME.match(n):
            out.add(n)
    return sorted(out)


def versions(name: str, base=None) -> list[tuple[int, int, float]]:
    _check(name)
    d = _dir(base)
    out = []
    for n in range(KEEP + 1):
        p = _version(d, name, n)
        if p.exists():
            st = p.stat()
            out.append((n, st.st_size, st.st_mtime))
    return out


def rollback(name: str, n: int = 1, base=None):
    _check(name)
    data = _version(_dir(base), name, n).read_bytes()  # FileNotFoundError if there's no such version
    write(name, data, base)


def delete(name: str, base=None):
    _check(name)
    d = _dir(base)
    for n in range(KEEP + 1):
        _version(d, name, n).unlink(missing_ok=True)
    _fsync_dir(d)
