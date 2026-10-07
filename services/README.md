# 会话服务关系

系统：NetworkManager、BlueZ、UPower、polkit、mocha-usb和GPU/backlight模块加载。用户：DBus、Niri、Noctalia、PipeWire、pipewire-pulse、WirePlumber。
Niri --session导出Wayland/DBus环境；Noctalia polkit_agent启用，权限按本地active seat处理。后台user@1000进程不总被polkit识别为active seat，原机曾使用active-seat白名单辅助授权；公开安装从直接tty1会话开始，先用nmcli general permissions/CanPowerOff验证。
亮度必须同时满足硬件背光驱动、正确的Noctalia设备名和sysfs写权限，注册backlight本身不能证明实际PWM/LP8556变化。
wallpaper专用目录需用户可读；Noctalia的share数据必须完整安装。
现代内核没有完整RT5671声卡，PipeWire运行只证明服务正常。
