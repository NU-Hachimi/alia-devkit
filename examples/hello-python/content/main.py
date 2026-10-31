"""Hello Python: the smallest Python cart. SDL3 through ctypes (libSDL3 is in the platform
baseline, so the cart brings nothing native), the gamepad, and a save that counts launches.
START quits; on a PC, Escape too."""
import ctypes
import os
import sys

from alia import save

sdl = ctypes.CDLL("libSDL3.so.0")
P, B, U8, U32, U64, F = ctypes.c_void_p, ctypes.c_bool, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_float
for name, res, args in [
    ("SDL_Init", B, [U32]),
    ("SDL_GetError", ctypes.c_char_p, []),
    ("SDL_CreateWindow", P, [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, U64]),
    ("SDL_CreateRenderer", P, [P, ctypes.c_char_p]),
    ("SDL_SetRenderVSync", B, [P, ctypes.c_int]),
    ("SDL_GetRenderOutputSize", B, [P, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]),
    ("SDL_SetRenderScale", B, [P, F, F]),
    ("SDL_SetRenderDrawColor", B, [P, U8, U8, U8, U8]),
    ("SDL_RenderClear", B, [P]),
    ("SDL_RenderDebugText", B, [P, F, F, ctypes.c_char_p]),
    ("SDL_RenderPresent", B, [P]),
    ("SDL_PollEvent", B, [P]),
    ("SDL_OpenGamepad", P, [U32]),
    ("SDL_Quit", None, []),
]:
    f = getattr(sdl, name)
    f.restype, f.argtypes = res, args

INIT_VIDEO, INIT_GAMEPAD = 0x20, 0x2000
WINDOW_FULLSCREEN = 0x1
EV_QUIT, EV_KEY_DOWN, EV_PAD_DOWN, EV_PAD_ADDED = 0x100, 0x300, 0x651, 0x653
SCANCODE_ESCAPE = 41
BUTTON_START = 6
# SDL_GamepadButton -> the Alia Pad's labels (A is on the right, B at the bottom)
BUTTONS = {0: "B", 1: "A", 2: "Y", 3: "X", 4: "SELECT", 6: "START", 9: "L", 10: "R",
           11: "UP", 12: "DOWN", 13: "LEFT", 14: "RIGHT"}


def main() -> int:
    # a save: how many times this cart has been started (survives reboots and updates)
    launches = int(save.read("launches") or b"0") + 1
    save.write("launches", str(launches).encode())

    if not sdl.SDL_Init(INIT_VIDEO | INIT_GAMEPAD):
        print("SDL_Init:", sdl.SDL_GetError().decode(), file=sys.stderr)
        return 1
    win = sdl.SDL_CreateWindow(b"Hello Python", 1280, 720, WINDOW_FULLSCREEN)
    ren = sdl.SDL_CreateRenderer(win, None)
    if not win or not ren:
        print("window:", sdl.SDL_GetError().decode(), file=sys.stderr)
        return 1
    sdl.SDL_SetRenderVSync(ren, 1)

    lang = os.environ.get("ALIA_LANG", "en")
    lines = [f"Hello, Alia Pad!  (language: {lang})", f"launches: {launches}", "", "press a button", "",
             "START: quit"]
    ev = ctypes.create_string_buffer(128)  # SDL_Event
    w, h = ctypes.c_int(), ctypes.c_int()
    hue = 0
    while True:
        while sdl.SDL_PollEvent(ev):
            kind = int.from_bytes(ev.raw[0:4], "little")
            if kind == EV_QUIT:  # also what SIGTERM turns into: the system asks the cart to quit
                return 0
            if kind == EV_PAD_ADDED:
                sdl.SDL_OpenGamepad(int.from_bytes(ev.raw[16:20], "little"))
            elif kind == EV_PAD_DOWN:
                button = ev.raw[20]
                if button == BUTTON_START:
                    return 0
                lines[3] = f"pressed: {BUTTONS.get(button, button)}"
                hue = (hue + 40) % 240
            elif kind == EV_KEY_DOWN and int.from_bytes(ev.raw[24:28], "little") == SCANCODE_ESCAPE:
                return 0

        sdl.SDL_GetRenderOutputSize(ren, ctypes.byref(w), ctypes.byref(h))
        scale = max(1, h.value // 180)  # the debug font is 8x8 pixels
        sdl.SDL_SetRenderScale(ren, scale, scale)
        sdl.SDL_SetRenderDrawColor(ren, 20, 24 + hue // 4, 40 + hue // 2, 255)
        sdl.SDL_RenderClear(ren)
        sdl.SDL_SetRenderDrawColor(ren, 240, 240, 240, 255)
        for i, line in enumerate(lines):
            sdl.SDL_RenderDebugText(ren, 16, 16 + 12 * i, line.encode())
        sdl.SDL_RenderPresent(ren)


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sdl.SDL_Quit()
