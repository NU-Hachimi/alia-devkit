# 刷机：开发版系统

在设备上运行卡带需要 Alia Pad 的系统。开发版镜像（`alia-pad-os-<版本>-unoq.tar.zst`）可以装未签名的卡带，带 adb。镜像不属于这个仓库，从发布页下载；它包含各自许可的第三方组件（见镜像里的 `NOTICE`）。

现在的设备是 **Arduino UNO Q** 开发板（掌机的硬件还没定型）。刷机会清空板子上的所有数据。

需要：一个跳线帽或一根杜邦线，[arduino-flasher-cli](https://github.com/arduino/arduino-flasher-cli)。

1. 板子断电，短接 **JCTL 的 1 脚（GND）和 2 脚（USB_BOOT）**，插上 USB。`lsusb` 能看到 `05c6:9008`。JCTL 是 1.8 V 的，只能接地，不要接别的。
2. ```bash
   arduino-flasher-cli flash unoq alia-pad-os-<版本>-unoq.tar.zst --root-size 16GB --yes
   ```
3. 拔掉跳线，重新上电。第一次开机会扩展分区、生成这块板子自己的 ID 和密钥。
4. `adb devices` 能看到板子。连 Wi-Fi：`adb shell nmcli dev wifi connect <名称> password <密码>`。

默认用户 `alia`，密码 `alia`（adb 登录就是这个用户），请改掉：`adb shell passwd`。

开发板没有屏幕。经 USB 在电脑上看画面、听声音的工具以后加入开发包。
