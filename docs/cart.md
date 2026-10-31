# 卡带：目录、清单、`.acart` 文件

## 1. 目录结构

一张卡带就是一个目录，根上有 `cart.toml`：

```
cart.toml          清单（必需）
icon.png           256×256：主页格子、系统菜单
cover.png          1280×720：详情页的封面
background.png     1280×720：选中这张卡带时主页的背景
logo.png           带透明通道的标题图，叠在封面上
screenshots/*.png  截图，在详情页里翻看（按文件名排序）
content/           游戏文件；运行时在 /cart/content
```

图片都是可选的，缺了用生成的格子或文字代替。

卡带有两种形态：

- **目录**：开发中用 `acart --board push DIR` 直接推到设备上运行。
- **`.acart` 文件**：同一个目录打成只读镜像（`acart pack`），正式安装用这种。

## 2. 清单 `cart.toml`

```toml
[cart]
id          = "com.example.megalith"   # 反向域名，至少三段：小写字母、数字、_（不能有 -）
title       = "Megalith"               # 原名
version     = "1.0.0"
publisher   = "Example Studio"
description = "……"                     # 详情页
# platform  = "1.0"                    # 需要的平台基线，默认 1.0（platform.md）
# format    = 1                        # 清单格式版本，默认 1

[runtime]
type  = "native"        # native | python
entry = "megalith"      # 相对 content/：native 是可执行文件，python 是脚本
args  = ["--fullscreen"]
pause = "system"        # system | game：挂起后谁显示暂停画面（runtime.md §4）

[input]
uses    = ["gamepad"]   # 还可以写 motion、haptics、touch、keyboard
confirm = "system"      # system | east | south：确认键跟随系统，或者固定

[permissions]
network = false         # true：沙箱里有网络

[save]
quota_kb = 1024         # 存档目录的上限

[locale.zh]             # 可选：各语言的译名和说明，按 BCP 47 语言标签（zh、zh-Hant、en、ja …）
title       = "巨构"
description = "……"

[art]                   # 可选：不写就按第 1 节的默认文件名找
icon        = "icon.png"
cover       = "art/cover.png"
background  = "art/bg.png"
logo        = "art/logo.png"
screenshots = ["shots/1.png", "shots/2.png"]
```

### 校验规则

`acart check DIR` 逐条报出问题，`acart pack` 遇到问题不打包：

- 必填：`cart.id`、`title`、`version`，`runtime.type`、`entry`。
- 路径都不能跳出卡带目录：`..` 和绝对路径会被拒绝。
- `[art]` 里写了的文件必须存在；没写的按默认文件名找，找不到不算错。
- 现在能启动的运行时只有 `native` 和 `python`。
- `content/` 里的原生文件（程序、Python 扩展模块、自带的库）必须是 arm64，依赖的库要么在平台基线里，要么在卡带里（`platform.md`）。

### 译名

主页显示当前系统语言的译名，找的顺序是：完全相同的标签（`zh-CN`）→ 只看语言（`zh`）→ 同语言的任意标签（`zh-Hant`）→ 原名（`[cart] title`）。主页格子下面一行是 `publisher`；详情页在译名下面显示原名（两者不同时）。`description` 同理。

### 兼容

不认识的键一律忽略，所以旧系统也能读新清单。只有已有字段的含义变了，`format` 才会加一，旧系统看到会拒绝加载，而不是理解错。

## 3. `.acart` 文件

`acart pack` 生成。一般不需要关心内部结构，这里写出来，给要自己读写它的工具用。

文件前面是卡带目录的 SquashFS 镜像（大小按 4 KiB 对齐，默认 zstd 压缩，也可以 `--comp gzip`），最后 4 KiB 是尾块，小端字节序：

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0 | 4 | 魔数 `ACRT` |
| 4 | 2 | 尾块版本（1） |
| 6 | 2 | 标志：bit 0 表示已签名 |
| 8 | 8 | 镜像大小（尾块之前的字节数） |
| 16 | 32 | 镜像的 SHA-256 |
| 48 | 4 | 清单长度 |
| 52 | 32 | 签名公钥的 SHA-256（未签名时全 0） |
| 84 | 64 | ed25519 签名，签的是 `"alia-acart-v1\0"` + 镜像 SHA-256 + 清单 SHA-256 |
| 148 | … | `cart.toml` 原文（和镜像里的一样），后面补 0 |

- 不挂载就能读清单（`acart info`）。整个文件也可以直接当 SquashFS 挂载，尾块会被忽略。
- 打包结果可复现：时间戳和属主固定为 0，同样的输入每次得到逐字节相同的文件。
- **签名**：开发版系统（开发者模式）可以安装未签名的卡带；正式系统只接受签名卡带。`acart keygen KEY` 生成密钥，`acart pack DIR --key KEY` 签名。

## 4. 安装以后

- 安装时先复制、再校验复制出来的那份（哈希、签名、清单和镜像里的是否一致），提取图片（每张不超过 8 MB），最后替换旧版本。中间出错，已装的版本不受影响。
- 同一个 id 已经有一张推上去的目录卡带时，安装会失败（`Conflict`），先 `acart --board remove ID`。
- 删除卡带时存档默认保留，`--purge` 连存档、缓存、日志一起删。
