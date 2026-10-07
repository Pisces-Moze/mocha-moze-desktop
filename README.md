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

桌面安装在已启动的Debian13 armhf。下列命令在Debian13 amd64 Linux主机运行，板上只安装运行产物。
`install-build-deps.sh`启用armhf multiarch和trixie-backports，安装实际交叉构建使用的依赖；Rust target=armv7-unknown-linux-gnueabihf，linker=arm-linux-gnueabihf-gcc。
工具脚本要求提供已解开的Niri源码与官方vendored dependencies目录，避免在线漂移：

```sh
sudo bash tools/install-build-deps.sh
curl -L https://github.com/niri-wm/niri/archive/refs/tags/v26.04.tar.gz -o niri.tar.gz
curl -L https://github.com/niri-wm/niri/releases/download/v26.04/niri-26.04-vendored-dependencies.tar.xz -o vendor.tar.xz
mkdir -p build/niri
tar xf niri.tar.gz -C build/niri --strip-components=1
# 官方依赖包包含vendor/；Cargo的离线替换配置由本仓库提供。
tar xf vendor.tar.xz -C build/niri
mkdir -p build/niri/.cargo
cp config/cargo-armhf.toml build/niri/.cargo/config.toml
bash tools/build-niri.sh build/niri
```

应用**0003**完整补丁；它包含0002的修改，因此不能把0002和0003串行重复应用。修改vendor后更新.cargo-checksum.json，cargo clean -p smithay，否则Cargo可能复用不可变Git依赖缓存，源码改了实际二进制没变。
完整主机依赖列表保存在`tools/install-build-deps.sh`，不要把几十个-dev包和Cargo缓存直接装入平板的小APP分区。

Noctalia 5.2.1是C++23/Meson工程。交叉文件使用ARMv7 NEON硬浮点和`-latomic`；关闭主机原生指令优化、jemalloc和测试。安装二进制**和数据目录**，只复制noctalia可导致壁纸缩略图不显示。

```sh
curl -L https://github.com/noctalia-dev/noctalia/archive/refs/tags/v5.2.1.tar.gz -o noctalia.tar.gz
mkdir -p build/noctalia
tar xf noctalia.tar.gz -C build/noctalia --strip-components=1
bash tools/build-noctalia.sh build/noctalia build/desktop-package
stage="$PWD/build/desktop-package"
install -d "$stage/usr/local/bin" "$stage/usr/local/lib/systemd/user"
install -m755 build/niri/target/armv7-unknown-linux-gnueabihf/release/niri "$stage/usr/local/bin/niri"
arm-linux-gnueabihf-strip --strip-unneeded "$stage/usr/local/bin/niri"
sed 's|^ExecStart=niri |ExecStart=/usr/local/bin/niri |' build/niri/resources/niri.service > "$stage/usr/local/lib/systemd/user/niri.service"
install -m644 build/niri/resources/niri-shutdown.target "$stage/usr/local/lib/systemd/user/"
tar -C "$stage" -czf build/desktop-armhf.tar.gz usr/local
sha256sum build/desktop-armhf.tar.gz
```

`/usr/local`是公开安装统一路径，和原机私有数据挂载路径不同；规范化路径的整套新安装尚未重新实机验收。

## 设备安装

在板上先安装运行服务：

先通过root SSH执行`passwd mocha`为本地用户设置自己的密码，之后可使用sudo；SSH仍只接受密钥。以下APT步骤要求根文件系统有足够空间，先用`df -h / /usr /var`和`apt -s install ...`评估。原厂APP约1.25GiB，不能保证放下浏览器与全部依赖；只bind mount `/usr/local`不会迁走APT的`/usr/lib`、`/usr/share`。数据分区上的完整桌面rootfs迁移与APP扩容尚未提供通过实机验收的自动方案，不要在空间不足时强行执行。

```sh
sudo apt install firefox-esr foot mesa-utils libgl1-mesa-dri libegl1 \
  dbus-user-session network-manager bluez upower pipewire wireplumber \
  pipewire-pulse policykit-1 brightnessctl ffmpeg mpv fonts-dejavu-core \
  libsdbus-c++2 libwayland-client0 libfreetype6 libfontconfig1 libcairo2 \
  libpango-1.0-0 libpangocairo-1.0-0 libharfbuzz0b librsvg2-2 libxkbcommon0 \
  libglib2.0-0t64 libsecret-1-0 libsodium23 libpolkit-agent-1-0 \
  libpolkit-gobject-1-0 libpipewire-0.3-0t64 libwireplumber-0.5-0 \
  libcurl3t64-gnutls libqalculate23 libxml2 libmd4c0 libtomlplusplus3t64 \
  libical3t64 libgles2 libepoxy0 libwebp7 libwebpdemux2 libwebpmux3 \
  libjxl0.11 libsndfile1 libinput10 libseat1 libdisplay-info2 libliftoff0 \
  libsystemd0 libdbus-1-3 libgbm1 libudev1
# 将主机生成的desktop-armhf.tar.gz及desktop源码目录传到平板。
sudo tar -xzf desktop-armhf.tar.gz -C /
ldd /usr/local/bin/niri
ldd /usr/local/bin/noctalia
# 两个ldd输出均不能有not found；缺库时先安装对应armhf运行包。
sudo bash tools/install-session.sh mocha
# 首次在本机tty1检查自动会话；SSH会话不能替代active seat验证。
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
# 在Linux交叉构建主机运行；把生成的build/mocha-charger-ui连同仓库传到平板。
bash tools/build-charger.sh
# 以下在平板上执行，要求build/mocha-charger-ui是ARM产物且ldd没有not found。
sudo bash tools/install-charger.sh
# 先手工限时试运行并确认按住电源2秒进入桌面，再启用自动入口：
sudo touch /boot/mocha-charger.enabled
```

接有线电源开机时generator选择mocha-charger.target，桌面暂停、竖屏Cairo电池动画运行。短按唤醒，15秒熄屏，长按约2秒返回桌面，拔线8秒关机。
systemd-inhibit接管handle-power-key，防止logind在充电UI处理按键时再次关机/重启。
DCP输入上限2A、CDP1.5A、电脑USB/未知500mA；电池侧960mA/4.208V。温度不合范围或health异常回500mA。实测正电流，但电量计跳变仍需完善。
这是最小Linux充电模式，不是SoC完全断电；UI目前直接framebuffer绘制，仅小区域刷新，idle熄屏。它与计划中的原生GPU桌面路线分开。
