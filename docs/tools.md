# 工具：`acart`

`pip install ./python` 安装（Python ≥ 3.11）。打包要系统的 `mksquashfs`（`squashfs-tools`）；签名要 `pip install './python[sign]'`。和设备打交道要 `adb`。

## 1. 不需要设备

```bash
acart check DIR...                          # 校验卡带目录（清单、文件、原生依赖）
acart pack DIR [-o x.acart] [--key KEY] [--comp zstd|gzip]   # 打包，可选签名
acart info x.acart                          # 读尾块：清单、哈希（重新计算）、签名
acart keygen KEY                            # 生成签名密钥：KEY 和 KEY.pub
```

## 2. 设备（经 USB 的 adb）

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

## 3. 调试

- **日志**：卡带的输出在 `adb shell cat .local/share/alia/logs/ID.log`。
- **存档**：`adb shell ls .local/share/alia/saves/ID/`。
- **崩溃**：`watch` 里的 `crashed` 行带日志路径。
- 推上去的目录卡带改了文件后再 `push --launch` 一次就行，不用打包。
