# 平台基线：卡带能依赖什么

卡带只能依赖平台基线里的东西，其余都自己带进 `content/`。基线有版本号（现在是 **1.0**），完整清单在 `python/alia/platform.toml`，`acart check` 就按它检查。

## 1. 1.0 里有什么

| 类别 | 保证有的 |
|---|---|
| 系统 | Debian 13 arm64 的 glibc（≥ 2.41）、libstdc++ / libgcc（GCC 14） |
| 图形 | EGL、OpenGL ES 2.0–3.1（Mesa）、libgbm、Wayland 客户端库、SDL3（≥ 3.2.10） |
| 输入 | 经 SDL3 的手柄（`runtime.md` §3） |
| 声音 | 经 SDL3，或者 ALSA（`libasound`）的 `default` 设备 |
| Python | `python3`（3.13）和标准库，`alia` SDK 包（`alia.save` 等） |

按 soname 列出（卡带的程序可以链接这些）：

```
libc.so.6  libm.so.6  libpthread.so.0  libdl.so.2  librt.so.1  ld-linux-aarch64.so.1
libgcc_s.so.1  libstdc++.so.6
libEGL.so.1  libGLESv2.so.2  libgbm.so.1  libwayland-client.so.0  libwayland-egl.so.1
libSDL3.so.0  libasound.so.2
```

最低版本按 Debian 13 本身的版本写；设备上实际的版本可能更新（比如 Mesa），但不要依赖更新版本才有的功能。

## 2. 不在基线里的怎么办

- **原生库**：静态链接，或者放进 `content/lib/`，程序设置 RUNPATH `$ORIGIN/lib`（CMake：`set(CMAKE_INSTALL_RPATH "$ORIGIN/lib")`；直接链接：`-Wl,-rpath,'$ORIGIN/lib'`）。沙箱不设 `LD_LIBRARY_PATH`。
- **纯 Python 的包**：复制进 `content/`，入口脚本所在目录就在 `sys.path` 里。
- **Python 扩展模块**：同原生库，按 arm64 编译（`native.md`），依赖的库也放进卡带。
- **游戏引擎**：现在不在基线里，随卡带带。

`acart check` 扫描 `content/` 里所有 ELF 文件：必须是 arm64；每个依赖（NEEDED）要么在卡带要求的基线里，要么能沿这个文件的 RUNPATH 在卡带里找到。指向卡带外面的 RUNPATH 会提示。`acart pack` 遇到问题不打包。

## 3. Python 卡带

- 设备上是 Debian 13 的 `python3`，**3.13**，属于基线 1.0：所有 1.x 的系统都保证是 3.13（Debian 13 整个生命周期都不换 Python 小版本，只出补丁版本）。清单里不用另写 Python 版本，`platform = "1.0"` 就包含了。
- 只能用标准库和 `alia` SDK 包（`alia.save` 等，设备上已经装好）。其他纯 Python 的包放进 `content/`。
- **在电脑上开发也用 3.13**（工具最低 3.12），这样在电脑上能跑的代码到设备上也能跑：比 3.13 新的语法和标准库在设备上没有，`acart check` 也查不出来。
- **扩展模块**（`.so`）建议按稳定 ABI（abi3，`Py_LIMITED_API`）编译，文件名是 `*.abi3.so`。只对 3.13 编译的（`*.cpython-313-aarch64-linux-gnu.so`）现在也能用，但设备换 Python 小版本时就失效了。
- 以后系统换了 Python 小版本（下一个 Debian），基线升大版本（2.0），写 `platform = "1.0"` 的卡带不会被当成兼容的来启动。纯 Python 和 abi3 的卡带一般只需要改一下 `platform` 重新打包。

## 4. 版本

- 卡带在清单里写需要的基线：`[cart] platform = "1.0"`（不写就是 1.0）。
- 系统的基线不够时（大版本不同，或小版本更旧），卡带不会启动。
- **规则**：基线只加东西时升小版本（1.0 → 1.1，新条目标 `since`）；拿掉东西才升大版本。所以写 `1.0` 的卡带在之后所有 1.x 的系统上都能运行。
