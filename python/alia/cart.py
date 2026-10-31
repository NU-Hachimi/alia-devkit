# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""Cart manifests (`cart.toml`, docs/cart.md): parse, validate, resolve art and entry.

A cart is a directory (unpacked: dev carts, and later the mount point of an .acart
SquashFS image) with `cart.toml` at its root. Everything not listed here is ignored, so
newer manifests still load on older systems; `format` only goes up for changes that
would be misread, not for additions.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 1
MANIFEST = "cart.toml"
RUNTIMES = ("native", "python", "qce", "retroarch", "godot", "love")
INPUTS = ("gamepad", "motion", "haptics", "touch", "keyboard")
# [locale.<tag>]: a BCP 47 language tag, language[-Script][-REGION] (zh, zh-Hant, zh-CN, en, pt-BR)
LANG_TAG = re.compile(r"[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?")
# Art kinds, with the file used when [art] doesn't name one. A missing file is fine:
# the Shell falls back to a generated tile.
ART_DEFAULTS = {
    "icon": "icon.png",              # 256x256, shelf tile and system menu
    "cover": "cover.png",            # 1280x720 banner on the shelf
    "background": "background.png",  # 1280x720 home background while the cart is selected
    "logo": "logo.png",              # title artwork with alpha, drawn over cover/background
}
SCREENSHOTS_DIR = "screenshots"     # *.png, sorted, when [art] has no screenshots list
_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){2,}$")  # reverse domain, >= 3 parts


class CartError(ValueError):
    pass


@dataclass
class Cart:
    root: Path
    id: str
    title: str
    version: str
    runtime: str
    entry: str
    args: list[str] = field(default_factory=list)
    title_zh: str = ""  # the old form of [locale.zh] title; filled from it either way (List() readers)
    # translated names and descriptions by BCP 47 tag ([locale.<tag>]; title_zh counts as zh)
    titles: dict = field(default_factory=dict)
    descriptions: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)  # fine, but worth changing (acart check prints them)
    platform: str = "1.0"  # the platform baseline the cart needs (platform.toml, packaging.md §2)
    publisher: str = ""
    description: str = ""
    render: str = ""
    uses: list[str] = field(default_factory=lambda: ["gamepad"])
    confirm: str = "system"
    permissions: dict[str, bool] = field(default_factory=dict)
    quota_kb: int = 1024
    dev: bool = False  # dev cart: entry may be an absolute host path (never in a signed cart)
    pause: str = "system"  # "game": it shows its own pause menu on SIGUSR1/SIGUSR2; "system": the Shell's
    art: dict[str, Path] = field(default_factory=dict)  # kind -> existing file
    screenshots: list[Path] = field(default_factory=list)

    @property
    def content(self) -> Path:
        return self.root / "content"

    def command(self, extra: list[str] | None = None, root: Path | None = None) -> list[str]:
        """argv to start the cart (native and python runtimes); root: where the cart is
        seen from the process (the sandbox's /cart), default its directory."""
        content = (root or self.root) / "content"
        if self.runtime == "native":
            exe = self.entry if self.entry.startswith("/") else str(content / self.entry)
            return [exe, *self.args, *(extra or [])]
        if self.runtime == "python":
            return ["python3", str(content / self.entry), *self.args, *(extra or [])]
        raise CartError(f"{self.id}: runtime '{self.runtime}' is not supported yet")

    def summary(self) -> dict:
        """Plain values for D-Bus (a{sv}) and JSON."""
        return {"id": self.id, "title": self.title, "title_zh": self.title_zh, "version": self.version,
                "titles": dict(self.titles), "descriptions": dict(self.descriptions),
                "publisher": self.publisher, "description": self.description, "runtime": self.runtime,
                "pause": self.pause,
                "path": str(self.root), "art": {k: str(v) for k, v in self.art.items()},
                "screenshots": [str(p) for p in self.screenshots]}


def _inside(root: Path, rel: str, what: str, check_files: bool = True) -> Path:
    if not check_files:
        # Not mounted (an .acart's trailer): judge the path by its text alone, never touch
        # the mount point, which may not exist or may be a dead mount.
        p = Path(os.path.normpath(root / rel))
        if os.path.isabs(rel) or not p.is_relative_to(Path(os.path.normpath(root))):
            raise CartError(f"{what} '{rel}' points outside the cart")
        return p
    p = (root / rel).resolve()
    if not p.is_relative_to(root.resolve()):
        raise CartError(f"{what} '{rel}' points outside the cart")
    return p


def _get(table: dict, key: str, kind: type, default=None, required=False):
    if key not in table:
        if required:
            raise CartError(f"missing '{key}'")
        return default
    v = table[key]
    if not isinstance(v, kind) or (kind is int and isinstance(v, bool)):
        raise CartError(f"'{key}' should be {kind.__name__}")
    return v


def load(root: str | Path) -> Cart:
    root = Path(root)
    try:
        text = (root / MANIFEST).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CartError(f"{root}: no {MANIFEST}") from None
    except UnicodeDecodeError as e:
        raise CartError(f"{root / MANIFEST}: {e}") from None
    return loads(text, root, where=str(root / MANIFEST))


def loads(text: str, root: Path, check_files: bool = True, where: str = MANIFEST) -> Cart:
    """Parse manifest text. check_files=False for an image that isn't mounted (an .acart's
    trailer): paths are still checked to stay inside, but art isn't looked up."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise CartError(f"{where}: {e}") from None
    try:
        return _parse(Path(root), data, check_files)
    except CartError as e:
        raise CartError(f"{where}: {e}") from None


def _parse(root: Path, data: dict, check_files: bool = True) -> Cart:
    c = _get(data, "cart", dict, required=True)
    fmt = _get(c, "format", int, 1)
    if fmt > FORMAT:
        raise CartError(f"format {fmt} is newer than this system understands ({FORMAT})")
    cid = _get(c, "id", str, required=True)
    if not _ID.match(cid):
        raise CartError(f"id '{cid}' should be a reverse domain name like com.example.game")
    rt = _get(data, "runtime", dict, required=True)
    runtime = _get(rt, "type", str, required=True)
    if runtime not in RUNTIMES:
        raise CartError(f"runtime.type '{runtime}' is not one of {', '.join(RUNTIMES)}")
    dev = _get(c, "dev", bool, False)
    entry = _get(rt, "entry", str, required=True)
    if entry.startswith("/"):
        if not dev:
            raise CartError("runtime.entry is an absolute path; only dev carts (cart.dev = true) may do that")
    else:
        _inside(root / "content", entry, "runtime.entry", check_files)
    args = _get(rt, "args", list, [])
    pause = _get(rt, "pause", str, "system")
    if pause not in ("system", "game"):
        raise CartError("runtime.pause should be system or game")
    if not all(isinstance(a, str) for a in args):
        raise CartError("'args' should be a list of strings")

    disp = _get(data, "display", dict, {})
    inp = _get(data, "input", dict, {})
    uses = _get(inp, "uses", list, ["gamepad"])
    bad = [u for u in uses if u not in INPUTS]
    if bad:
        raise CartError(f"input.uses: unknown {bad}")
    confirm = _get(inp, "confirm", str, "system")
    if confirm not in ("system", "east", "south"):
        raise CartError("input.confirm should be system, east or south")
    perms = {k: bool(v) for k, v in _get(data, "permissions", dict, {}).items()}
    save = _get(data, "save", dict, {})

    art_t = _get(data, "art", dict, {})
    art = {}
    for kind, default in ART_DEFAULTS.items():
        rel = _get(art_t, kind, str, default)
        p = _inside(root, rel, f"art.{kind}", check_files)
        if not check_files:
            continue
        if p.is_file():
            art[kind] = p
        elif kind in art_t:
            raise CartError(f"art.{kind}: no file '{rel}'")
    if "screenshots" in art_t:
        shots = _get(art_t, "screenshots", list)
        screenshots = [_inside(root, s, "art.screenshots", check_files) for s in shots]
        missing = [str(s) for s, p in zip(shots, screenshots) if not p.is_file()]
        if missing and check_files:
            raise CartError(f"art.screenshots: no file {missing}")
        if not check_files:
            screenshots = []
    elif not check_files:
        screenshots = []
    else:
        d = root / SCREENSHOTS_DIR
        screenshots = sorted(d.glob("*.png")) if d.is_dir() else []

    titles, descriptions = {}, {}
    for tag, t in _get(data, "locale", dict, {}).items():
        if not LANG_TAG.fullmatch(tag) or not isinstance(t, dict):
            raise CartError(f"locale.{tag}: should be a table under a language tag like zh, zh-Hant or en")
        for key, into in (("title", titles), ("description", descriptions)):
            if key in t:
                into[tag] = _get(t, key, str)
    platform = _get(c, "platform", str, "1.0")
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", platform):
        raise CartError(f"cart.platform: {platform!r} should be a baseline version like \"1.0\"")
    title_zh = _get(c, "title_zh", str, "")
    notes = []
    if title_zh:
        titles.setdefault("zh", title_zh)
        notes.append("title_zh: the old form; use [locale.zh] title")
    title_zh = titles.get("zh", title_zh)

    return Cart(root=root, id=cid, title=_get(c, "title", str, required=True),
                version=_get(c, "version", str, required=True), runtime=runtime, entry=entry, args=args,
                title_zh=title_zh, titles=titles, descriptions=descriptions, notes=notes, platform=platform,
                publisher=_get(c, "publisher", str, ""),
                description=_get(c, "description", str, ""), render=_get(disp, "render", str, ""),
                uses=uses, confirm=confirm, permissions=perms, quota_kb=_get(save, "quota_kb", int, 1024),
                pause=pause,
                dev=dev, art=art, screenshots=screenshots)


def scan(dirs: list[Path]) -> tuple[dict[str, Cart], list[str]]:
    """Every cart in the given directories (one cart per subdirectory). Returns the carts
    by id and the problems found (bad manifests, duplicate ids); first directory wins."""
    carts: dict[str, Cart] = {}
    problems = []
    for d in dirs:
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            if not (sub / MANIFEST).is_file():
                continue
            try:
                cart = load(sub)
            except CartError as e:
                problems.append(str(e))
                continue
            if cart.id in carts:
                problems.append(f"{sub}: id {cart.id} already provided by {carts[cart.id].root}")
                continue
            carts[cart.id] = cart
    return carts, problems
