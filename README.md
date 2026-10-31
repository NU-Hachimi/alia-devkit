# Alia Pad devkit

The cart SDK, tools and docs for making games ("carts") for **Alia Pad**, a handheld built
on the Arduino UNO Q. MIT licensed. *(Docs are in Chinese for now.)*

Alia Pad 的开发包：给 Alia Pad 掌机（基于 Arduino UNO Q）做游戏（"卡带"）需要的 SDK、工具和文档。MIT 许可。

## 里面有什么

| | |
|---|---|
| `docs/` | 卡带格式（`cart.md`）、运行时约定（`runtime.md`）、平台基线（`platform.md`）、原生卡带交叉编译（`native.md`）、工具（`tools.md`）、刷机（`flashing.md`） |
| `python/` | Python SDK `alia-sdk`：卡带清单、存档（`alia.save`）、`.acart` 文件，命令行工具 `acart` |
| `include/alia/save.h` | C/C++ 存档接口，单头文件，和 Python 的 `alia.save` 读写同一套文件 |
| `sysroot/` | 原生卡带交叉编译用：按版本锁从 Debian / Arduino 官方源下载与设备一致的库，CMake 工具链文件 |
| `examples/` | 两个最小卡带：`hello-python`（纯 Python）、`hello-c`（C + SDL3） |

想用游戏引擎做卡带：见 [alia-engine](https://github.com/NU-Hachimi/alia-engine)，它在这个开发包之上提供项目结构、渲染、声音和资源管线。

## 五分钟上手

```bash
pip install ./python                      # 得到 acart（打包要系统的 squashfs-tools）
acart check examples/hello-python         # 检查清单和原生文件
acart pack examples/hello-python          # -> com.example.hellopython-0.1.0.acart

# 设备经 USB 连到电脑（adb），系统是开发版镜像（docs/flashing.md）
acart --board install com.example.hellopython-0.1.0.acart
acart --board launch com.example.hellopython
```

一张卡带就是一个目录：`cart.toml` 加上 `content/` 里的游戏文件，打包成 `.acart`。卡带在沙箱里运行，能用的系统库是固定的一组（平台基线），其余自己带。从 `docs/cart.md` 读起。

## 许可

本仓库：MIT（`LICENSE`）。设备的系统镜像不属于本仓库，它包含各自许可的第三方组件，见镜像里的 `NOTICE`。
