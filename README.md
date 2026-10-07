# Mocha Moze Desktop

Niri26.04 + Noctalia5.2.1 + Firefox ESR的Debian armhf横屏桌面，以及竖屏最小充电UI。

```
config/           # 横屏Niri、Noctalia中文配置
patches/          # Smithay旋转damage补丁，旧补丁仅供对照
charging/         # Cairo framebuffer UI、BC1.2政策、按键状态机与systemd
tools/            # 桌面与充电构建/安装
services/         # GPU、USB、用户会话和充电服务说明
Cargo.lock        # Niri26.04实际锁文件，Smithay固定revision
```

上游固定：Niri https://github.com/niri-wm/niri v26.04；Smithay ff5fa7df392cecfba049ffed55cdaa4e98a8e7ef；Noctalia https://github.com/noctalia-dev/noctalia v5.2.1（C++/Meson）。

## 构建

桌面安装在已启动的Debian13 armhf；Niri/Noctalia可以本机编译，也可在Linux主机交叉编译。
推荐在主机构建。ARM依赖通过dpkg --add-architecture armhf后安装；Rust target=armv7-unknown-linux-gnueabihf，linker=arm-linux-gnueabihf-gcc。
工具脚本要求提供已解开的Niri源码与官方vendored dependencies目录，避免在线漂移：

```sh
curl -L https://github.com/niri-wm/niri/archive/refs/tags/v26.04.tar.gz -o niri.tar.gz
curl -L https://github.com/niri-wm/niri/releases/download/v26.04/niri-26.04-vendored-dependencies.tar.xz -o vendor.tar.xz
mkdir -p build/niri
tar xf niri.tar.gz -C build/niri --strip-components=1
# 按官方vendor包内目录结构解压，将vendor/与.cargo/config.toml放入build/niri。
tar tf vendor.tar.xz | head
tar xf vendor.tar.xz -C build/niri
bash tools/build-niri.sh build/niri
```

应用**0003**完整补丁；它包含0002的修改，因此不能把0002和0003串行重复应用。修改vendor后更新.cargo-checksum.json，cargo clean -p smithay，否则Cargo可能复用不可变Git依赖缓存，源码改了实际二进制没变。
交叉构建依赖包：libudev-dev:armhf、libgbm-dev:armhf、libegl1-mesa-dev:armhf、libgles2-mesa-dev:armhf、libinput-dev:armhf、libxkbcommon-dev:armhf、libseat-dev:armhf、libdisplay-info-dev:armhf、libdbus-1-dev:armhf；以Niri构建错误确认缺失库。

Noctalia完整依赖以其固定版本meson.build为准。交叉文件样例noctalia-armhf-cross.ini仅作工具链参考，prefix用/usr/local；执行meson install安装二进制**和数据目录**。只复制noctalia可导致壁纸缩略图不显示。

## 设备安装

在板上先安装运行服务：

```sh
sudo apt install firefox-esr foot mesa-utils libgl1-mesa-dri libegl1 \
  dbus-user-session network-manager bluez upower pipewire wireplumber \
  pipewire-pulse policykit-1 brightnessctl ffmpeg mpv fonts-dejavu-core
sudo install -m755 YOUR_ARMHF_NIRI /usr/local/bin/niri
# 将Noctalia meson install的完整/usr/local产物安装，而不只放一个ELF。
sudo bash tools/install-session.sh mocha
```

APP约1.25GiB，不足以放完整编译缓存。选择已备份的UDA数据文件系统、用自己的PARTUUID挂载，再bind mount桌面安装目录；避免破坏原有数据或无记录地格式化UDA。
用户session需要DBus/runtime环境、NetworkManager、UPower、polkit和PipeWire/WirePlumber。菜单服务连接已修复，但音频仍无硬件声卡，服务正常不能让RT5671自动工作。
默认output名Unknown-1、旋转90、scale1.5；native实验输出名可能DSI-1且无需同样软件旋转。不要复用默认node号码到native环境。

## 性能与显示

默认Nouveau着色器为硬件渲染，但simpledrm扫描输出仍有同步、显存读回/CPU搬运开销，动画约10FPS。当前未把兼容输出声称为最终高性能路线。
0003修复横屏damage导致的贯穿黑条/残影，无法独自消除跨GPU输出复制。
native Tegra + Nouveau线性DMA-BUF色块约29.8FPS实机出图；Niri仍在Mesa tegra_fence_server_sync调用点崩溃，尚未默认启用。
软件H264/Firefox视频已验证；硬件解码/编码尚未完成。Noctalia壁纸需专用可读目录与完整数据文件。

## 最小充电模式

```sh
bash tools/build-charger.sh
sudo bash tools/install-charger.sh
# 先手工限时试运行并确认按住电源2秒进入桌面，再启用自动入口：
sudo touch /boot/mocha-charger.enabled
```

接有线电源开机时generator选择mocha-charger.target，桌面暂停、竖屏Cairo电池动画运行。短按唤醒，15秒熄屏，长按约2秒返回桌面，拔线8秒关机。
systemd-inhibit接管handle-power-key，防止logind在充电UI处理按键时再次关机/重启。
DCP输入上限2A、CDP1.5A、电脑USB/未知500mA；电池侧960mA/4.208V。温度不合范围或health异常回500mA。实测正电流，但电量计跳变仍需完善。
这是最小Linux充电模式，不是SoC完全断电；UI目前直接framebuffer绘制，仅小区域刷新，idle熄屏。它与计划中的原生GPU桌面路线分开。
