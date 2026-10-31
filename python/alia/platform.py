# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""The platform baseline (platform.toml, next to this file) and the check of a cart's native
files against it (acart check, acart pack; the devkit's docs/platform.md).

A cart's native file (its program, a Python extension module, a bundled library) may need:
  - a library of the baseline the cart asks for (cart.toml [cart] platform, default 1.0);
  - or one the cart carries itself, found through the file's RUNPATH (or RPATH) inside the
    cart: $ORIGIN/lib, say. The sandbox sets no LD_LIBRARY_PATH.
Every native file must be arm64.
"""
import tomllib
from functools import lru_cache
from pathlib import Path

from . import elf

DEFAULT = "1.0"


def parse_version(v: str) -> tuple[int, int]:
    major, _, minor = str(v).partition(".")
    return int(major), int(minor or 0)


@lru_cache(maxsize=1)
def baseline() -> dict:
    with open(Path(__file__).with_name("platform.toml"), "rb") as f:
        return tomllib.load(f)


def version() -> str:
    return baseline()["version"]


def sonames(at: str = None) -> dict[str, str]:
    """soname -> the baseline version that added it, for every library up to `at`."""
    at = parse_version(at or version())
    return {lib["soname"]: lib["since"] for lib in baseline()["lib"] if parse_version(lib["since"]) <= at}


def supports(wanted: str) -> bool:
    """Whether this system's baseline covers a cart asking for `wanted`."""
    have, want = parse_version(version()), parse_version(wanted)
    return want[0] == have[0] and want <= have


def _resolve(lib: str, f: Path, rpath: list[str], root: Path) -> bool:
    for entry in rpath:
        d = Path(entry.replace("${ORIGIN}", str(f.parent)).replace("$ORIGIN", str(f.parent)))
        try:
            d.resolve().relative_to(root.resolve())
        except ValueError:
            continue  # outside the cart: noted separately
        if (d / lib).exists():
            return True
    return False


# a PC build (acart check --pc, for the PC simulator) loads through x86-64's loader instead
TARGETS = {"board": (elf.EM_AARCH64, {}),
           "pc": (elf.EM_X86_64, {"ld-linux-x86-64.so.2": "ld-linux-aarch64.so.1"})}


def _too_new(version: str) -> bool:
    """GLIBC_2.43 when the baseline provides up to 2.41 (platform.toml [symbol_versions])."""
    family, _, number = version.partition("_")
    top = baseline().get("symbol_versions", {}).get(family)
    if not top or not number[:1].isdigit():
        return False
    num = lambda v: tuple(int(x) for x in v.split(".") if x.isdigit())  # noqa: E731
    return num(number) > num(top)


def check(cart, target: str = "board") -> tuple[list[str], list[str]]:
    """Problems (the cart won't run as built) and notes, for a loaded cart (alia.cart).
    target: "board" (arm64, the handheld) or "pc" (x86-64, a PC build for the simulator)."""
    machine, aliases = TARGETS[target]
    problems, notes = [], []
    want = cart.platform
    if not supports(want):
        problems.append(f"platform {want}: this SDK knows baseline {version()}")
        return problems, notes
    have = sonames(want)
    newer = sonames()
    root = cart.root
    content = cart.content if cart.content.is_dir() else root
    for f in sorted(p for p in content.rglob("*") if p.is_file() and not p.is_symlink()):
        if not elf.is_elf(f):
            continue
        rel = f.relative_to(root)
        try:
            e = elf.read(f)
        except (elf.ElfError, IndexError, ValueError) as err:
            problems.append(f"{rel}: unreadable ELF ({err})")
            continue
        if e.machine != machine:
            problems.append(f"{rel}: built for {e.machine_name}; "
                            + ("the board needs arm64" if target == "board" else "a PC build needs x86-64"))
            continue
        for entry in e.rpath:
            if "$ORIGIN" not in entry and "${ORIGIN}" not in entry:
                notes.append(f"{rel}: RUNPATH {entry} points outside the cart (use $ORIGIN/...)")
        for lib in e.needed:
            if aliases.get(lib, lib) in have:
                too_new = sorted(v for v in e.versions.get(lib, ()) if _too_new(v))
                if too_new:
                    problems.append(f"{rel}: needs {', '.join(too_new)} from {lib}, newer than the platform's "
                                    "(built on a newer system: build on Debian 13, or the devkit's sysroot)")
                continue
            if _resolve(lib, f, e.rpath, root):
                continue
            if lib in newer:
                problems.append(f"{rel}: needs {lib}, which the platform has from {newer[lib]} on; "
                                f"set [cart] platform = \"{newer[lib]}\"")
            else:
                problems.append(f"{rel}: needs {lib}, which isn't in the platform ({want}); "
                                "carry it in content/lib with RUNPATH $ORIGIN/lib")
    return problems, notes
