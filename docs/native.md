# 原生卡带：在电脑上交叉编译

设备是 arm64 的 Debian 13。在 x86-64 的 Linux 电脑上，用 clang 加一个和设备一致的 sysroot 交叉编译，不需要设备，也不需要在设备上装编译器。

## 1. 准备

需要：`clang`、`lld`、`cmake`、`bsdtar`（Debian / Ubuntu 的 `libarchive-tools`，Arch 的 `libarchive`）、`curl`。

```bash
sysroot/fetch.sh            # -> sysroot/out/aarch64（约 120 MB 的 .deb，解开约 600 MB）
```

`fetch.sh` 按 `sysroot/sysroot.lock` 从 Debian 和 Arduino 的官方源下载固定版本的开发包，逐个校验哈希后解开。锁文件和设备系统的版本对应：`packages.txt` 列出顶层的包（glibc、libstdc++、SDL3、EGL/GLES、Wayland、ALSA 的开发文件），锁文件是解出来的完整依赖。

再运行一次只会补下缺的文件。`SYSROOT_OUT=DIR` 可以换一个输出目录。

## 2. CMake

```bash
cmake -B build -DCMAKE_TOOLCHAIN_FILE=<devkit>/sysroot/toolchain-aarch64.cmake
cmake --build build
```

工具链文件让 `find_package` 和 `pkg-config` 只在 sysroot 里找，`find_package(SDL3)` 直接能用。sysroot 不在默认位置时加 `-DALIA_SYSROOT=DIR`。

例子：`examples/hello-c`。

## 3. 不用 CMake

```bash
S=<devkit>/sysroot/out/aarch64
clang --target=aarch64-linux-gnu --sysroot=$S -fuse-ld=lld -O2 \
    -I<devkit>/include main.c -o hello \
    $(PKG_CONFIG_SYSROOT_DIR=$S PKG_CONFIG_LIBDIR=$S/usr/lib/aarch64-linux-gnu/pkgconfig pkg-config --cflags --libs sdl3)
```

## 4. 注意

- **只链接平台基线里的库**（`platform.md`）。sysroot 里还有一些别的库（它们是开发包的依赖），链接了它们 `acart check` 会报错。
- 自带的库放进 `content/lib/`，程序设 RUNPATH `$ORIGIN/lib`。
- C++：用 sysroot 里的 libstdc++（GCC 14），不要用 libc++，它不在基线里。也可以 `-static-libstdc++`。
- 编好以后 `acart check` 检查一遍，再推到设备上运行（`tools.md`）。
