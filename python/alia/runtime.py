# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NU Hachimi (Alia Pad cart SDK)
"""The cart runtime (runtime.toml, next to this file): paths, environment, timings, the
gamepad. Read by the system's launcher and by the PC simulator, so both run a cart the same
way (the devkit's docs/runtime.md)."""
import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def rules() -> dict:
    with open(Path(__file__).with_name("runtime.toml"), "rb") as f:
        return tomllib.load(f)


def env(cart_id: str, quota_kb: int, lang: str = "") -> dict[str, str]:
    """The cart's environment, without the display (WAYLAND_DISPLAY...) and the SDK path."""
    r = rules()
    fill = {"{cart.id}": cart_id, "{cart.quota_kb}": str(quota_kb), "{lang}": lang,
            "{gamepad.mapping}": r["gamepad"]["mapping"]}
    out = {}
    for k, v in r["env"].items():
        for key, value in fill.items():
            v = v.replace(key, value)
        if v:
            out[k] = v
    return out


def keyboard() -> dict:
    """The PC keyboard layout ([keyboard]): button -> SDL3 key names, the two sticks as
    {up, down, left, right} -> key name, and half_tilt."""
    return rules()["keyboard"]


def audio() -> dict:
    """The cart's sound output ([audio]): rate, channels, quanta, role."""
    return rules()["audio"]


def display() -> dict:
    """The handheld's screen ([display]): the window size a cart gets, the panel, its
    transform and refresh rate; `verified` is false until the panel is measured."""
    return rules()["display"]
