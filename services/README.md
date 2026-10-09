# 会话服务关系

系统：NetworkManager、BlueZ、UPower、polkit、mocha-usb和GPU/backlight模块加载。用户：DBus、Niri、Noctalia、PipeWire、pipewire-pulse、WirePlumber。
Niri --session导出Wayland/DBus环境；Noctalia polkit_agent启用，权限按本地active seat处理。后台user@1000进程不总被polkit识别为active seat，原机曾使用active-seat白名单辅助授权；公开安装从直接tty1会话开始，先用nmcli general permissions/CanPowerOff验证。
亮度必须同时满足硬件背光驱动、正确的Noctalia设备名和sysfs写权限，注册backlight本身不能证明实际PWM/LP8556变化。
wallpaper专用目录需用户可读；Noctalia的share数据必须完整安装。
现代内核没有完整RT5671声卡，PipeWire运行只证明服务正常。

历史辅助程序源码见 [mocha-active-seat.c](mocha-active-seat.c)，使用 `sd_uid_is_on_seat(1000, 1, "seat0")` 输出 active/inactive。固定 UID 1000 仅对应原始测试用户，不作为默认安装权限策略；不要据此给所有后台进程放行。可在有 libsystemd 开发文件的目标或交叉编译环境中构建：

```sh
cc -O2 -Wall -Wextra mocha-active-seat.c -o mocha-active-seat $(pkg-config --cflags --libs libsystemd)
```

公开参数与服务入口见 [PARAMETERS.md](https://github.com/Pisces-Moze/mocha-moze-debian/blob/main/docs/PARAMETERS.md)。
