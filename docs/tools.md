# 工具：`acart`

`pip install python/` 安装（Python 3.13，最低 3.12）。只有打包（`acart pack`）要系统的 `mksquashfs`（`squashfs-tools`，Linux 上有；`acart run` 和 `acart check` 不需要）；签名要 `pip install 'python/[sign]'`。和设备打交道要 `adb`。

## 1. 不需要设备

```bash
acart check DIR...                          # 校验卡带目录（清单、文件、原生依赖、符号版本）
acart check --pc DIR                        # 校验电脑版（x86-64，给 acart run 用）
acart pack DIR [-o x.acart] [--key KEY] [--comp zstd|gzip]   # 打包，可选签名
acart info x.acart                          # 读尾块：清单、哈希（重新计算）、签名
acart keygen KEY                            # 生成签名密钥：KEY 和 KEY.pub
```

## 2. 在电脑上运行：`acart run`

```bash
acart run DIR [ARGS...]          # 按掌机的规则在电脑上运行卡带目录
acart run DIR --fresh            # 用一个空存档目录，用完丢掉
acart run DIR --lang en          # 系统语言（zh-CN、en）；默认沿用上次，或者按 $LANG
acart run DIR --software         # 软件渲染（没有能用的 GPU 时）
acart run DIR --no-audio         # 不出声（电脑的声音有问题时）
acart run DIR --browser          # 在浏览器里运行（没有 Wayland 桌面时自动用）
```

需要 Docker（或 Podman）。在 Linux 的 Wayland 桌面上，卡带开在一个窗口里；没有 Wayland 的桌面上自动改用**浏览器模式**：画面、声音和手柄都在浏览器的一个页面里（`http://localhost:7300`，页面就绪后自动打开），第一次要点一下页面才有声音。也可以用 `--browser` 指定，`--port` 换端口，`--no-open` 不自动打开浏览器。

卡带的手柄：有 `/dev/uinput` 的电脑（Linux）用它；Docker Desktop（Windows、macOS）的虚拟机没有，模拟器就在用户空间模拟同一个手柄，游戏看到的完全一样。Windows、macOS 还在实机验证中。卡带在 alia-runtime 镜像里运行：Debian 13，只有平台基线里的库，环境变量、挂起和退出的规则都和掌机一样（`python/alia/runtime.toml`）。卡带目录直接挂进去，改完重新运行就行，不用推送。存档在 `~/.local/share/alia-runtime/saves/<id>`（Windows：`%LOCALAPPDATA%\alia-runtime\saves\<id>`；macOS：`~/Library/Application Support/alia-runtime/saves/<id>`）。

- 原生卡带：在 x86_64 的电脑上要放一份 x86_64 的程序（在 Debian 13 或更旧的 glibc 上编译）。
- 游戏收不到键盘，和掌机一样只有手柄：键盘和电脑上的手柄都变成一个 Alia Pad 手柄（按位置：Xbox 手柄下面的键是 Alia Pad 的 B）。

### 键盘

所有电脑上的工具（`acart run`、引擎的 `alia run`）都用这一套，来源是 `runtime.toml` 的 `[keyboard]`（`alia.runtime.keyboard()`）：

| 键 | 掌机 | 键 | 掌机 |
|---|---|---|---|
| 方向键 | 十字键 | `W A S D` | 左摇杆（按住 Shift 推一半） |
| `X` / `Z` | A（右） / B（下） | `I J K L` | 右摇杆 |
| `C` / `V` | X（上） / Y（左） | `F` / `N` | L3 / R3 |
| `E` / `Q` | L / L2 | `Enter` / `Backspace` | START / SELECT |
| `U` / `O` | R / R2 | `H` | Home（长按：快捷菜单） |

Home 短按：游戏被冻结（模拟回到主页），再按一次回到游戏，不是 `pause = "game"` 的卡带先看到"已暂停"。长按：快捷菜单（继续、语言、熄屏、退出）。

### 在镜像里跑命令：`acart exec`

```bash
acart exec DIR -- pytest -q                      # 在模拟器镜像里跑测试
acart exec --env PYTHONPATH=build/dev DIR -- python3 tools/make_shots.py
```

给测试和工具用，不是给卡带用：`DIR` 可读写地挂进去并作为工作目录，以当前用户运行（写出的文件归你），没有窗口、手柄、声音，也没有沙箱和网络限制。镜像里有 `pytest` 和 `pyflakes`（单独的环境，卡带看不到），Python 是和掌机一样的 3.13。不需要 `/dev/uinput`，所以 Windows、macOS 上也能用。

## 3. 设备（经 USB 的 adb）

加 `--board`：`acart` 经 adb 在设备上运行设备自己的 `acart`。

```bash
acart --board push DIR [--launch]           # 推一个卡带目录上去（开发时最快的循环）
acart --board install x.acart               # 复制过去再安装
acart --board list [--json]                 # 设备上的卡带，以及加载失败的清单
acart --board launch [--replace] ID [ARGS...]   # 启动；--replace：先结束前台的卡带（ID 后面的都传给游戏）
acart --board status                        # 前台是什么
acart --board stop [--force]                # 结束前台的卡带（SIGTERM，3 秒后 SIGKILL）
acart --board suspend | resume              # 冻结 / 解冻前台的卡带（测试挂起）
acart --board home                          # 等于按 Home 键
acart --board remove ID [--purge]           # 删除；--purge 连存档一起删
acart --board verify ID                     # 重新检查已安装卡带的哈希和签名
acart --board watch                         # 每个事件一行：启动、退出、崩溃……
```

`watch` 的输出：`foreground ID|- STATE`、`started ID`、`exited ID CODE`、`crashed ID LOG`、`carts-changed`。退出码是负数时表示被信号结束（`-9` 是 SIGKILL）。

## 4. 调试

- **日志**：卡带的输出在 `adb shell cat .local/share/alia/logs/ID.log`。
- **存档**：`adb shell ls .local/share/alia/saves/ID/`。
- **崩溃**：`watch` 里的 `crashed` 行带日志路径。
- 推上去的目录卡带改了文件后再 `push --launch` 一次就行，不用打包。
