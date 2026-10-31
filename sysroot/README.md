# sysroot

- `packages.txt`：顶层的开发包。
- `sysroot.lock`：解出来的完整依赖，每行 `URI 文件名 大小 哈希`，和设备系统的版本对应。随系统更新。
- `fetch.sh`：按锁文件下载、校验、解开到 `out/aarch64`。
- `toolchain-aarch64.cmake`：CMake 工具链文件。

用法见 `../docs/native.md`。
