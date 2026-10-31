# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""Just enough ELF to check a cart's native files (acart check): the machine, the dynamic
section's NEEDED, RPATH and RUNPATH, and the symbol versions it needs from each library
(GLIBC_2.38 from libc.so.6). 64-bit little-endian only, like the board."""
import struct
from dataclasses import dataclass, field
from pathlib import Path

EM_AARCH64, EM_X86_64 = 183, 62
MACHINES = {3: "x86 (32-bit)", 40: "ARM (32-bit)", 62: "x86-64", 183: "arm64"}
SHT_DYNAMIC, SHT_GNU_VERNEED = 6, 0x6ffffffe
DT_NEEDED, DT_RPATH, DT_RUNPATH = 1, 15, 29


class ElfError(Exception):
    pass


@dataclass
class Elf:
    machine: int
    needed: list = field(default_factory=list)
    rpath: list = field(default_factory=list)  # RUNPATH, else RPATH, split on ':'
    versions: dict = field(default_factory=dict)  # library -> the symbol versions it must provide

    @property
    def machine_name(self) -> str:
        return MACHINES.get(self.machine, f"machine {self.machine}")


def is_elf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def read(path: Path) -> Elf:
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        raise ElfError("not an ELF file")
    if data[4] != 2 or data[5] != 1:
        raise ElfError("not a 64-bit little-endian ELF (the board is arm64)")
    machine, = struct.unpack_from("<H", data, 18)
    shoff, = struct.unpack_from("<Q", data, 40)
    shentsize, shnum = struct.unpack_from("<HH", data, 58)
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize) for i in range(shnum)]
    out = Elf(machine)
    for _name, typ, _flags, _addr, off, size, link, info, _align, entsize in sections:
        if typ not in (SHT_DYNAMIC, SHT_GNU_VERNEED):
            continue
        stroff = sections[link][4]

        def string(at):
            end = data.index(b"\0", stroff + at)
            return data[stroff + at:end].decode(errors="replace")

        if typ == SHT_GNU_VERNEED:  # Elf64_Verneed entries, each with Elf64_Vernaux entries
            at = off
            for _ in range(info):
                _ver, cnt, file, aux, nxt = struct.unpack_from("<HHIII", data, at)
                names = out.versions.setdefault(string(file), set())
                a = at + aux
                for _ in range(cnt):
                    _hash, _flags2, _other, name, anext = struct.unpack_from("<IHHII", data, a)
                    names.add(string(name))
                    a += anext
                if not nxt:
                    break
                at += nxt
            continue

        rpath = runpath = None
        for at in range(off, off + size, entsize or 16):
            tag, val = struct.unpack_from("<qQ", data, at)
            if tag == 0:
                break
            if tag == DT_NEEDED:
                out.needed.append(string(val))
            elif tag == DT_RPATH:
                rpath = string(val)
            elif tag == DT_RUNPATH:
                runpath = string(val)
        path = runpath if runpath is not None else rpath
        out.rpath = [p for p in (path or "").split(":") if p]
    return out
