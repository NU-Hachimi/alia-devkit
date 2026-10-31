/* Hello C: the smallest native cart. SDL3 (in the platform baseline), the gamepad, and a
 * save that counts launches (alia/save.h). START quits; on a PC, Escape too. */
#include <stdio.h>
#include <stdlib.h>
#include <SDL3/SDL.h>
#include "alia/save.h"

/* SDL_GamepadButton -> the Alia Pad's labels (A is on the right, B at the bottom) */
static const char *label(int button)
{
    switch (button) {
    case SDL_GAMEPAD_BUTTON_EAST: return "A";
    case SDL_GAMEPAD_BUTTON_SOUTH: return "B";
    case SDL_GAMEPAD_BUTTON_NORTH: return "X";
    case SDL_GAMEPAD_BUTTON_WEST: return "Y";
    case SDL_GAMEPAD_BUTTON_BACK: return "SELECT";
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return "L";
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return "R";
    case SDL_GAMEPAD_BUTTON_DPAD_UP: return "UP";
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN: return "DOWN";
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT: return "LEFT";
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT: return "RIGHT";
    default: return "?";
    }
}

int main(void)
{
    /* a save: how many times this cart has been started */
    char buf[16] = "0";
    int n = alia_save_read("launches", buf, sizeof buf - 1);
    buf[n > 0 ? n : 1] = '\0';
    int launches = atoi(buf) + 1;
    n = snprintf(buf, sizeof buf, "%d", launches);
    if (alia_save_write("launches", buf, (size_t)n) < 0)
        fprintf(stderr, "save failed\n");

    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD)) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    SDL_Window *win = SDL_CreateWindow("Hello C", 1280, 720, SDL_WINDOW_FULLSCREEN);
    SDL_Renderer *ren = win ? SDL_CreateRenderer(win, NULL) : NULL;
    if (!ren) {
        fprintf(stderr, "window: %s\n", SDL_GetError());
        return 1;
    }
    SDL_SetRenderVSync(ren, 1);

    const char *lang = getenv("ALIA_LANG");
    char title[64], count[32], pressed[32] = "press a button";
    snprintf(title, sizeof title, "Hello, Alia Pad!  (language: %s)", lang ? lang : "en");
    snprintf(count, sizeof count, "launches: %d", launches);
    int hue = 0;
    for (;;) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_EVENT_QUIT: /* also what SIGTERM turns into: the system asks the cart to quit */
                goto out;
            case SDL_EVENT_GAMEPAD_ADDED:
                SDL_OpenGamepad(ev.gdevice.which);
                break;
            case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
                if (ev.gbutton.button == SDL_GAMEPAD_BUTTON_START)
                    goto out;
                snprintf(pressed, sizeof pressed, "pressed: %s", label(ev.gbutton.button));
                hue = (hue + 40) % 240;
                break;
            case SDL_EVENT_KEY_DOWN:
                if (ev.key.scancode == SDL_SCANCODE_ESCAPE)
                    goto out;
                break;
            }
        }
        int w, h;
        SDL_GetRenderOutputSize(ren, &w, &h);
        float scale = h / 180 > 1 ? (float)(h / 180) : 1.0f; /* the debug font is 8x8 pixels */
        SDL_SetRenderScale(ren, scale, scale);
        SDL_SetRenderDrawColor(ren, 20, 24 + hue / 4, 40 + hue / 2, 255);
        SDL_RenderClear(ren);
        SDL_SetRenderDrawColor(ren, 240, 240, 240, 255);
        SDL_RenderDebugText(ren, 16, 16, title);
        SDL_RenderDebugText(ren, 16, 28, count);
        SDL_RenderDebugText(ren, 16, 52, pressed);
        SDL_RenderDebugText(ren, 16, 76, "START: quit");
        SDL_RenderPresent(ren);
    }
out:
    SDL_Quit();
    return 0;
}
