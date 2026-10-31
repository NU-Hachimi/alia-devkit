# 运行时：卡带运行在什么环境里

这里的路径、环境变量、超时和手柄映射，机器可读的版本在 SDK 的 `python/alia/runtime.toml`（`from alia import runtime`）。掌机的启动器和电脑上的模拟器 alia-runtime 都按它运行卡带。

## 1. 沙箱

每张卡带都在沙箱（bubblewrap）里运行，环境变量从零开始，不继承系统的。卡带能看到的只有：

| 路径 | 内容 |
|---|---|
| `/cart` | 卡带自己的文件，只读；游戏文件在 `/cart/content` |
| `/save` | 存档，可写，有配额（§5） |
| `/cache` | 缓存（比如着色器缓存），可写，可能被清掉 |
| `/usr`、`/etc` | 系统本身，只读：平台基线里的库、Mesa、字体 |
| `/dev/dri`、`/dev/input` | GPU 和手柄 |
| Wayland、PipeWire 的 socket | 画面和声音，经 SDL3 直接能用 |

- 看不到用户的家目录和别的卡带。
- 没有网络，除非清单里写了 `[permissions] network = true`。
- 只能用平台基线里的系统库（`platform.md`），其余自己带。

### 环境变量

| 变量 | 内容 |
|---|---|
| `ALIA_CART_ID` | 卡带的 id |
| `ALIA_CART_DIR` | `/cart` |
| `ALIA_SAVE_DIR` | `/save` |
| `ALIA_SAVE_QUOTA_KB` | 清单里的存档配额 |
| `ALIA_LANG` | 系统语言，BCP 47 标签（现在是 `zh-CN` 或 `en`），用来选游戏自己的界面语言 |
| `XDG_CACHE_HOME` | `/cache` |
| `WAYLAND_DISPLAY`、`SDL_VIDEODRIVER=wayland` | 画面 |

`ALIA_LANG` 只在启动时给；游戏运行中用户切换语言，下次启动生效。

## 2. 画面

- 一个全屏窗口（Wayland），由系统的合成器显示。用 SDL3 开窗口就行，建议直接全屏。
- 图形接口：EGL + OpenGL ES（最高 3.1，Mesa freedreno，GPU 是 Adreno 702）。没有桌面 OpenGL 和 Vulkan 的保证。
- 屏幕分辨率还没定（硬件未到），游戏要能适应窗口大小。开发板没有屏幕时，画面经 USB 在电脑上看。

## 3. 输入

系统把掌机的按键做成一个标准手柄，SDL3 的 `SDL_Gamepad` 直接能用（键盘在开发时也能用）：

| 掌机 | SDL3 |
|---|---|
| A（右） | `SDL_GAMEPAD_BUTTON_EAST` |
| B（下） | `SDL_GAMEPAD_BUTTON_SOUTH` |
| X（上） | `SDL_GAMEPAD_BUTTON_NORTH` |
| Y（左） | `SDL_GAMEPAD_BUTTON_WEST` |
| 十字键、L/R、START、SELECT | 对应的按键 |
| Home | **系统保留**，卡带收不到 |

- 系统已经在沙箱里为 SDL 设好了这个手柄的映射（`SDL_GAMECONTROLLERCONFIG`），并让 SDL 在窗口没有键盘焦点时也收手柄事件（`SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1`；掌机没有键盘，窗口不会得到键盘焦点）。游戏不要覆盖这两个设置。
- 不经 SDL、直接读 evdev 的程序：上 `BTN_NORTH`、左 `BTN_WEST`、右 `BTN_EAST`、下 `BTN_SOUTH`（按位置，和 Linux 内核文档一致）。
- 确认键默认是 A（右），返回是 B（下）。清单里的 `[input] confirm` 可以声明游戏自己的习惯。
- 卡带启动前就按着的键，松开之前卡带看不到，不会误触发。
- 振动：`SDL_RumbleGamepad`。现在硬件还没有马达，会返回不支持，游戏要能处理这种情况。

## 4. 挂起和恢复

用户按 Home 回到主页、熄屏、打开快捷菜单（长按 Home）时，系统**冻结**卡带的进程（SIGSTOP），恢复时解冻（SIGCONT）。冻结期间游戏的时间不走，但墙上时间在走：用 `SDL_GetTicks` 这类单调时钟算帧间隔的游戏，恢复后第一帧会看到一个很大的间隔，要做上限。

清单的 `[runtime] pause` 决定恢复时谁来显示暂停画面：

- **`"system"`**（默认）：游戏什么都不用做。恢复时系统在游戏上面盖一层"已暂停 · 按任意键继续"，用户按键后才交还给游戏。
- **`"game"`**：游戏用自己的暂停菜单。冻结前系统先发 **SIGUSR1**，0.3 秒后再冻结；恢复时解冻后发 **SIGUSR2**。游戏在 SIGUSR1 里打开自己的暂停菜单（只设一个标志，在主循环里处理），停在那里，等用户操作。

  SIGUSR1 的默认动作是结束进程，所以**只有装好了信号处理的游戏才能写 `"game"`**。

## 5. 存档

存档放在 `$ALIA_SAVE_DIR`（`/save`）。用 SDK 的存档接口，Python 和 C 读写同一套文件：

```python
from alia import save                  # 沙箱里已经有这个包
save.write("slot1", data)              # bytes；原子写入，保留前两个版本
save.read("slot1")                     # 最新的完好版本；没有就是 None
save.names(); save.versions("slot1"); save.rollback("slot1", 1); save.delete("slot1")
```

```c
#include "alia/save.h"                 // 单头文件，C99 / C++
alia_save_write("slot1", buf, len);    // 0 或 -errno
alia_save_read("slot1", buf, cap);     // 读到的字节数；放不下返回 -EMSGSIZE（先用 alia_save_size 查）
alia_save_list(names, max); alia_save_rollback("slot1", 1); alia_save_delete("slot1");
```

- **断电安全**：写临时文件 → fsync → 旧版本依次改名为 `NAME.~1~`、`NAME.~2~` → 临时文件改名为 `NAME` → fsync 目录。中途断电，读取时退回最新的完好版本。
- **配额**：写完后整个目录超过清单的 `quota_kb`，返回 `ENOSPC`（这次写入不生效）。
- **名字**：字母、数字、`.`、`_`、`-`，最长 64 个字符，不能以 `.` 开头。
- **回滚**本身也是一次写入，所以可以再撤销回来。
- 不用 SDK 也可以直接在 `/save` 里读写文件，配额照样算，但断电安全要自己保证。

## 6. 声音

- 一个输出，**48 kHz 立体声**。用 SDL3 的音频（`SDL_OpenAudioDeviceStream`）或 ALSA 的 `default` 设备都可以；其他采样率会被重采样，最好直接用 48 kHz。
- 延迟：默认缓冲约 21 ms（1024 帧），可以申请更小的（SDL 的 sample frames 提示），最小 32 帧。
- **系统音量**由系统管，游戏看不到也改不了；游戏只调自己内部的比例（音乐、音效）。
- 系统的通知音响起时，游戏的声音会被平滑地压低，播完恢复；按键反馈音直接叠加。游戏不用处理。
- 冻结时声音停止，恢复后接着放。
- 卡带只能播放自己的声音，不能录音，不能改别的程序的音量。

## 7. 退出

- 游戏可以自己退出（正常结束进程），系统回到主页。
- 用户在快捷菜单里选"退出"时，系统先发 SIGTERM，3 秒内没退出就 SIGKILL。要在退出前存档，就处理 SIGTERM（或者 SDL 的 `SDL_EVENT_QUIT`）。
- 卡带的标准输出和标准错误写进设备上的日志：`adb shell cat .local/share/alia/logs/ID.log`（`tools.md`）。
