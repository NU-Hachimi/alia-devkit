"""Cart manifest tests (pytest sdk)."""
from pathlib import Path

import pytest

from alia import cart as cartlib

BASE = """
[cart]
id = "com.example.game"
title = "Game"
version = "1.0.0"
{cart_extra}
[runtime]
type = "{runtime}"
entry = "{entry}"
{extra}
"""


def make(tmp: Path, name="game", runtime="native", entry="game", cart_extra="", extra="", files=()):
    d = tmp / name
    (d / "content").mkdir(parents=True)
    (d / "cart.toml").write_text(BASE.format(runtime=runtime, entry=entry, cart_extra=cart_extra, extra=extra))
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        (d / f).write_bytes(b"x")
    return d


def test_minimal(tmp_path):
    c = cartlib.load(make(tmp_path))
    assert c.id == "com.example.game" and c.runtime == "native" and c.uses == ["gamepad"]
    assert c.art == {} and c.screenshots == []
    assert c.command(["--x"]) == [str(c.content / "game"), "--x"]


def test_art_by_convention_and_explicit(tmp_path):
    d = make(tmp_path, files=["icon.png", "cover.png", "screenshots/2.png", "screenshots/1.png"])
    c = cartlib.load(d)
    assert set(c.art) == {"icon", "cover"}
    assert [p.name for p in c.screenshots] == ["1.png", "2.png"]

    d2 = make(tmp_path, name="g2", files=["art/bg.png", "shots/a.png"],
              extra='[art]\nbackground = "art/bg.png"\nscreenshots = ["shots/a.png"]')
    c2 = cartlib.load(d2)
    assert c2.art["background"].name == "bg.png" and [p.name for p in c2.screenshots] == ["a.png"]


def test_art_named_but_missing_is_an_error(tmp_path):
    with pytest.raises(cartlib.CartError, match="art.logo"):
        cartlib.load(make(tmp_path, extra='[art]\nlogo = "logo.png"'))


def test_paths_stay_inside(tmp_path):
    with pytest.raises(cartlib.CartError, match="outside"):
        cartlib.load(make(tmp_path, entry="../../etc/passwd"))
    with pytest.raises(cartlib.CartError, match="outside"):
        cartlib.load(make(tmp_path, name="g2", extra='[art]\nicon = "/etc/passwd"'))


def test_absolute_entry_only_for_dev_carts(tmp_path):
    with pytest.raises(cartlib.CartError, match="dev"):
        cartlib.load(make(tmp_path, entry="/usr/bin/true"))
    c = cartlib.load(make(tmp_path, name="dev", entry="/usr/bin/true", cart_extra="dev = true"))
    assert c.command() == ["/usr/bin/true"]


def test_unknown_keys_ignored_newer_format_refused(tmp_path):
    c = cartlib.load(make(tmp_path, cart_extra='rating = "E"', extra='[future]\nthing = 1'))
    assert c.title == "Game"
    with pytest.raises(cartlib.CartError, match="newer"):
        cartlib.load(make(tmp_path, name="g2", cart_extra="format = 2"))


def test_validation_messages(tmp_path):
    with pytest.raises(cartlib.CartError, match="reverse domain"):
        d = make(tmp_path)
        (d / "cart.toml").write_text((d / "cart.toml").read_text().replace("com.example.game", "Game"))
        cartlib.load(d)
    with pytest.raises(cartlib.CartError, match="runtime.type"):
        cartlib.load(make(tmp_path, name="g2", runtime="flash"))
    with pytest.raises(cartlib.CartError, match="input.uses"):
        cartlib.load(make(tmp_path, name="g3", extra='[input]\nuses = ["telepathy"]'))


def test_runtime_not_supported_yet(tmp_path):
    c = cartlib.load(make(tmp_path, runtime="retroarch"))
    with pytest.raises(cartlib.CartError, match="not supported"):
        c.command()


def test_scan_reports_problems_and_duplicates(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    make(a, name="one")
    make(b, name="dup")                          # same id as a/one
    make(b, name="bad", runtime="flash")
    (b / "not-a-cart").mkdir()
    carts, problems = cartlib.scan([a, b, tmp_path / "missing"])
    assert list(carts) == ["com.example.game"] and carts["com.example.game"].root.parent == a
    assert len(problems) == 2


def test_repo_carts_are_valid():
    here = Path(__file__).resolve().parent
    root = here.parent / "examples" if (here.parent / "examples").is_dir() else here.parents[1] / "carts"  # devkit | alia-pad
    carts, problems = cartlib.scan([root])
    assert carts and not problems


def test_locales(tmp_path):
    c = cartlib.load(make(tmp_path, cart_extra='title_zh = "游戏"', extra="""
[locale.en]
description = "A game."
[locale.zh-Hant]
title = "遊戲"
"""))
    assert c.titles == {"zh": "游戏", "zh-Hant": "遊戲"}      # title_zh counts as [locale.zh]
    assert c.notes and "old form" in c.notes[0]
    new = cartlib.load(make(tmp_path, name="new", extra='[locale.zh]\ntitle = "新"'))
    assert new.title_zh == "新" and not new.notes             # filled for readers of title_zh
    assert c.descriptions == {"en": "A game."}
    assert c.summary()["titles"]["zh-Hant"] == "遊戲"
    with pytest.raises(cartlib.CartError, match="language tag"):
        cartlib.load(make(tmp_path, name="bad", extra='[locale.Chinese]\ntitle = "x"'))
