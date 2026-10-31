"""runtime.toml: the environment it gives a cart, and that its gamepad matches what the
system creates."""
import re
from pathlib import Path

import pytest

from alia import runtime

HERE = Path(__file__).resolve().parent


def test_env_fills_the_cart_in():
    env = runtime.env("com.example.game", 2048, "zh-CN")
    assert env["ALIA_CART_ID"] == "com.example.game"
    assert env["ALIA_SAVE_QUOTA_KB"] == "2048"
    assert env["ALIA_LANG"] == "zh-CN"
    assert env["ALIA_SAVE_DIR"] == runtime.rules()["paths"]["save"]
    assert env["SDL_GAMECONTROLLERCONFIG"] == runtime.rules()["gamepad"]["mapping"]
    assert env["PIPEWIRE_PROPS"] == '{ media.role = "Game" }'
    assert not any("{" in v and "media.role" not in v for v in env.values())


def test_no_language_no_variable():
    assert "ALIA_LANG" not in runtime.env("com.example.game", 1024)


def test_mapping_guid_is_the_gamepad():
    g = runtime.rules()["gamepad"]
    guid = bytes.fromhex(g["mapping"].split(",")[0])
    le16 = lambda o: int.from_bytes(guid[o:o + 2], "little")  # noqa: E731
    assert (le16(0), le16(4), le16(8), le16(12)) == (g["bustype"], g["vendor"], g["product"], g["version"])
    assert g["mapping"].split(",")[1] == g["name"]


def test_inputd_creates_that_gamepad():
    hpp = HERE.parents[1] / "daemons" / "inputd" / "src" / "uinput.hpp"
    if not hpp.exists():
        pytest.skip("not in the system repository")
    m = re.search(r"VENDOR = (0x[0-9a-fA-F]+), PRODUCT = (0x[0-9a-fA-F]+), VERSION = (\d+)", hpp.read_text())
    g = runtime.rules()["gamepad"]
    assert (int(m[1], 16), int(m[2], 16), int(m[3])) == (g["vendor"], g["product"], g["version"])


def test_keyboard_keys_are_unique():
    kb = runtime.keyboard()
    keys = [k for v in kb.values() if isinstance(v, list) for k in v]
    keys += [k for v in kb.values() if isinstance(v, dict) for k in v.values()]
    assert len(keys) == len(set(keys))
    assert set(kb["left_stick"]) == set(kb["right_stick"]) == {"up", "down", "left", "right"}
