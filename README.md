# Mocha Moze Desktop

> 为跑 Debian armhf 的小米平板 1 提供两条图形界面：横屏 Niri 桌面，以及只在充电时启动的竖屏电量界面。

[![License: GPL-2.0-only](https://img.shields.io/badge/License-GPL--2.0--only-blue.svg)](LICENSE)

Mocha 是小米平板 1（A0101，NVIDIA Tegra124）的项目代号。本仓库负责把这块板子从「能启动的 Linux」推到「能日常看着用」，范围限定在图形界面层：桌面合成器、桌面外壳、浏览器，以及一个不依赖桌面的最小充电界面。全部产物在 Debian 13 amd64 主机上交叉编译成 armhf，平板只安装运行产物，不在板上编译。

同属这个工程的还有 [mocha-moze-debian](https://github.com/Pisces-Moze/mocha-moze-debian)（总入口、rootfs 与安装/回退文档）、[mocha-moze-boot](https://github.com/Pisces-Moze/mocha-moze-boot)（U-Boot 链式引导）、[mocha-moze-linux](https://github.com/Pisces-Moze/mocha-moze-linux)（6.12.111 内核与两套设备树）和 [mocha-moze-drivers](https://github.com/Pisces-Moze/mocha-moze-drivers)（背光、音频与 GPU 实验）。设备状态与完整安装路线以总入口仓库的文档为准。

桌面这条线要解决的是软件渲染与横屏旋转叠加之后的显示问题：默认 Nouveau 走硬件着色器，但扫描输出仍是 simpledrm，所以有额外的显存搬运开销。充电这条线要解决的是另一件事——插着线开机时用户只想看到电量和能安全地回到桌面，不需要拉起整套会话。

## 现状

| 项目 | 状态 |
| --- | --- |
| 横屏桌面（Niri + Noctalia + Firefox ESR） | 可运行，动画约 10 FPS |
| 横屏旋转 damage | 已用 0003 修复黑条与残影 |
| native Tegra + Nouveau 输出 | 约 29.8 FPS；已有 Mesa 空回调修复候选与回归测试，原生桌面实机验收待完成，未默认启用 |
| 视频播放 | 软件 H.264 / Firefox 已验证 |
| 硬件编解码 | 未完成 |
| 最小充电模式 | 可用，与桌面互斥切换 |
| 音频硬件 | 无完整 RT5671 声卡，PipeWire 只证明服务在跑 |

## 上游固定版本

| 组件 | 版本 / revision | 说明 |
| --- | --- | --- |
| [Niri](https://github.com/niri-wm/niri) | v26.04 | Rust 合成器，仓库内 `Cargo.lock` 的包版本为 26.4.0，两者对应同一发布 |
| [Smithay](https://github.com/Smithay/smithay) | `ff5fa7df392cecfba049ffed55cdaa4e98a8e7ef` | 以 git 依赖固定，`Cargo.lock` 中版本号为 0.7.0 |
| [Noctalia](https://github.com/noctalia-dev/noctalia) | v5.2.1 | C++23 / Meson 工程 |
| Firefox ESR | 由板上 `firefox-esr` 包提供 | 未在本仓库固定具体版本 |
| Rust target | `armv7-unknown-linux-gnueabihf` | linker 为 `arm-linux-gnueabihf-gcc` |

Niri 与 Smithay 的补丁不改上游许可证。本仓库没有附这两个项目的许可正文，具体条款要到各自仓库核对。

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `config/niri.kdl` | Niri 配置：输出 `Unknown-1`、`scale 1.5`、`transform "90"`、触摸映射、按键绑定 |
| `config/noctalia.toml` | Noctalia 基础配置：polkit agent、`zh-Hans`、深色主题、顶部状态栏 |
| `config/cargo-armhf.toml` | Cargo 离线替换与 target linker，需复制成 Niri 源码中的 `.cargo/config.toml` |
| `noctalia-armhf-cross.ini` | Noctalia 的 Meson cross file（位于仓库根目录） |
| `patches/0002-smithay-primary-rotated-damage.patch` | 早期补丁，仅供对照，不再应用 |
| `patches/0003-smithay-complete-rotated-damage.patch` | 当前使用，包含 0002 的全部改动 |
| `patches/0004-mesa-tegra-optional-fence-callbacks.patch` | Mesa 25.0.7 的 Tegra 可选 fence 回调修复候选；单独应用到 Mesa，不能应用到 Smithay |
| `tools/build-mesa.sh`、`tools/probe-egl-fence.py` | 构建独立 Mesa 候选与板上无 modeset 的 fence 回归；验收步骤见 [MESA-FENCE.md](docs/MESA-FENCE.md) |
| `charging/` | Cairo framebuffer UI、BC1.2 探测与输入限流、按键状态机、systemd 单元与 boot generator |
| `tools/` | 桌面与充电模式的构建、安装脚本 |
| `services/README.md` | 系统级与用户级服务的依赖关系说明 |
| `Cargo.lock` | Niri 26.04 的实际锁文件，含 Smithay 的固定 revision |

`build/`、`dist/`、`vendor/` 在 `.gitignore` 中；仓库不包含任何 armhf 二进制，全部需要在主机上编译。

## 主机侧部署

以下命令在 Debian 13 amd64 构建主机上执行，不要在平板的小 APP 分区里跑。

### 依赖

```sh
sudo bash tools/install-build-deps.sh
```

脚本先用 `/etc/os-release` 确认发行版是 Debian trixie，然后启用 armhf multiarch，写入 `/etc/apt/sources.list.d/mocha-build-backports.sources` 以启用 trixie-backports。它装两类东西：主机侧工具（`git curl python3 patch clang libclang-dev meson ninja-build pkg-config cmake g++-arm-linux-gnueabihf wayland-protocols libwayland-bin`）和一批 `:armhf` 交叉开发库（Wayland、GTK 相关、PipeWire/WirePlumber、polkit、qalculate、webp/jxl、libinput/libseat/libdisplay-info/liftoff、systemd、dbus 等），最后从 backports 安装 `rustc cargo libstd-rust-dev:armhf`。

### Niri 与 Smithay 补丁

```sh
curl -L https://github.com/niri-wm/niri/archive/refs/tags/v26.04.tar.gz -o niri.tar.gz
curl -L https://github.com/niri-wm/niri/releases/download/v26.04/niri-26.04-vendored-dependencies.tar.xz -o vendor.tar.xz
mkdir -p build/niri
tar xf niri.tar.gz -C build/niri --strip-components=1
# 官方依赖包自带 vendor/；离线替换配置由本仓库提供。
tar xf vendor.tar.xz -C build/niri
mkdir -p build/niri/.cargo
cp config/cargo-armhf.toml build/niri/.cargo/config.toml
bash tools/build-niri.sh build/niri
```

`tools/build-niri.sh` 在编译前做四件事：校验 `vendor/smithay/.cargo-checksum.json` 与 `.cargo/config.toml` 存在；用 `cmp` 确认传入源码树里的 `Cargo.lock` 与本仓库的锁文件一致（不一致直接退出，避免编出不匹配的依赖图）；把 `0003` 补丁应用到 `vendor/smithay`；重算被改动文件的 SHA256 并写回 `.cargo-checksum.json`。

编译环境由脚本自己设置，与 `config/cargo-armhf.toml` 里的 linker 相互印证：

```
CARGO_TARGET_ARMV7_UNKNOWN_LINUX_GNUEABIHF_LINKER=arm-linux-gnueabihf-gcc
PKG_CONFIG_ALLOW_CROSS=1
PKG_CONFIG_LIBDIR=/usr/lib/arm-linux-gnueabihf/pkgconfig:/usr/share/pkgconfig
BINDGEN_EXTRA_CLANG_ARGS=--target=arm-linux-gnueabihf -I/usr/include/arm-linux-gnueabihf
CARGO_PROFILE_RELEASE_LTO=false CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
```

随后 `cargo clean --offline -p smithay --target armv7-unknown-linux-gnueabihf`，再 `cargo build --locked --offline --release --target armv7-unknown-linux-gnueabihf --no-default-features --features dbus,systemd`。并行度取 `JOBS`，默认 4。

### Noctalia

```sh
curl -L https://github.com/noctalia-dev/noctalia/archive/refs/tags/v5.2.1.tar.gz -o noctalia.tar.gz
mkdir -p build/noctalia
tar xf noctalia.tar.gz -C build/noctalia --strip-components=1
bash tools/build-noctalia.sh build/noctalia build/desktop-package
```

脚本先核对源码 `VERSION` 文件等于 `5.2.1`，再按 `noctalia-armhf-cross.ini` 配置 Meson，`--prefix=/usr/local`，`-Dtests=disabled -Djemalloc=disabled -Dnative_optimizations=false`，构建目标只取 `noctalia`，随后 `DESTDIR` 安装到暂存目录并 `strip`，最后用 `arm-linux-gnueabihf-readelf -d` 打印 `NEEDED` 依赖清单。cross file 里的编译参数是 `-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard`，链接阶段加 `-latomic`。

### 组装桌面包

```sh
stage="$PWD/build/desktop-package"
install -d "$stage/usr/local/bin" "$stage/usr/local/lib/systemd/user"
install -m755 build/niri/target/armv7-unknown-linux-gnueabihf/release/niri "$stage/usr/local/bin/niri"
arm-linux-gnueabihf-strip --strip-unneeded "$stage/usr/local/bin/niri"
sed 's|^ExecStart=niri |ExecStart=/usr/local/bin/niri |' build/niri/resources/niri.service > "$stage/usr/local/lib/systemd/user/niri.service"
install -m644 build/niri/resources/niri-shutdown.target "$stage/usr/local/lib/systemd/user/"
tar -C "$stage" -czf build/desktop-armhf.tar.gz usr/local
sha256sum build/desktop-armhf.tar.gz
```

`build-noctalia.sh` 已经把 `noctalia` 二进制和它的数据目录一起装进 `build/desktop-package`，所以这一步只需要补齐 Niri 的二进制、user 单元和 `niri-shutdown.target`。`/usr/local` 是公开安装的统一路径。

## 平板侧部署

先通过 root SSH 执行 `passwd mocha` 给本地用户设一个自己的密码，之后才能用 `sudo`；SSH 本身仍只接受密钥。

安装前先量空间。原厂 APP 分区约 1.25 GiB，放不下浏览器加全部依赖：

```sh
df -h / /usr /var
apt -s install firefox-esr foot
```

模拟结果确认放得下再动手。只 bind mount `/usr/local` 不会迁走 APT 要写的 `/usr/lib` 和 `/usr/share`。

### 运行依赖

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
```

### 安装与验证

把主机生成的 `desktop-armhf.tar.gz` 和这个仓库一起传到平板，然后：

```sh
sudo tar -xzf desktop-armhf.tar.gz -C /
ldd /usr/local/bin/niri
ldd /usr/local/bin/noctalia
# 两个 ldd 输出都不能有 not found；缺库时先补装对应的 armhf 运行包。
sudo bash tools/install-session.sh mocha
# 首次必须在本机 tty1 上验证自动会话；SSH 会话不能替代 active seat 验证。
```

`tools/install-session.sh` 要求 `/usr/local/bin/niri`、`/usr/local/bin/noctalia` 可执行且两个 user 单元文件已存在，随后它做的事：

- 写入 `~/.config/niri/config.kdl` 与 `~/.config/noctalia/config.toml`，并追加壁纸目录、亮度后端（`mocha-miui-backlight`，`minimum_brightness = 0.03`，关闭 ddcutil）配置；把用户加入 `video`、`render`、`input` 组。
- 若 `/usr/local/share/noctalia/assets/noctalia-wallpaper.png` 存在，复制一份到 `~/Pictures/Wallpapers/Noctalia.png`。
- 写 udev 规则 `90-mocha-backlight.rules`，把背光 `brightness` 的组改为 `video` 并加写权限，然后 reload 并 trigger。
- 启用 `NetworkManager.service`、`bluetooth.service`，新建并启用 `mocha-desktop-hardware.service`（在 `getty@tty1` 之前 `modprobe nouveau` 和 `mocha_miui_backlight`）。
- 给 `getty@tty1.service` 加 drop-in，用 `agetty --autologin mocha` 自动登录；脚本会先把原 `~/.profile` 备份成 `~/.profile.before-mocha`，再追加只在 `/dev/tty1` 且没有 `WAYLAND_DISPLAY` 时执行的 `exec /usr/local/bin/niri --session`。

物理 tty1 上的会话需要 DBus runtime 环境、NetworkManager、UPower、polkit 和 PipeWire/WirePlumber 都正常。可以用 `nmcli general permissions` 和 `CanPowerOff` 先确认 polkit 认出了 active seat——后台 `user@1000` 进程不总被识别成 active seat，原机曾用 active-seat 白名单辅助授权，而公开安装是从直接 tty1 会话开始的。

默认输出名是 `Unknown-1`，旋转 90、scale 1.5，触摸也映射到这个输出。native 实验环境下输出名可能是 `DSI-1` 且不需要同样的软件旋转，不要把默认的 node 编号和输出名直接套过去。

## 最小充电模式

主机侧编译充电 UI（Cairo 直接画 framebuffer，无需 GPU）：

```sh
bash tools/build-charger.sh
```

产物是 `build/mocha-charger-ui`。把它和仓库一起传到平板，确认是 ARM 产物且 `ldd` 没有 `not found`，然后在板上安装：

```sh
sudo bash tools/install-charger.sh
```

脚本要求 `uname -m` 为 `armv7l` 且以 root 运行，把 UI 与三个 Python/shell 组件装进 `/usr/local/libexec/`，把 generator 装进 `/etc/systemd/system-generators/`，把 `mocha-charge-policy.service`、`mocha-charger.service`、`mocha-charger.target` 装进 `/etc/systemd/system/`，然后 `daemon-reload`、`systemd-analyze verify`、`systemctl enable mocha-charge-policy.service`。装完自动入口仍是关闭的。

先手工限时试运行，确认按住电源键约 2 秒能回到桌面，再启用自动入口：

```sh
sudo touch /boot/mocha-charger.enabled
```

### 启动与切换

generator 在开机时读取 `/proc/cmdline`，条件是 `/boot/mocha-charger.enabled` 存在、充电器 `online` 为 1、`/boot/mocha-desktop.once` 不存在、命令行里没有 `systemd.unit=` 也没有 `mocha_native_debug4=1`。四个条件同时成立时，它在 early 目录里把 `default.target` 软链到 `mocha-charger.target`，于是桌面不启动。若存在 `/boot/mocha-desktop.once`，generator 会把它删掉并放行桌面一次。

`mocha-charger.target` 是 `AllowIsolate=yes` 的目标，依赖 `basic.target`、`local-fs.target`。`mocha-charger.service` 与 `getty@tty1.service`、`user@1000.service` 冲突，启动前 `loginctl terminate-user mocha`，再 `modprobe mocha_miui_backlight`，最后用 `systemd-inhibit --what=handle-power-key --mode=block` 包住 `mocha-charger-session`——这样充电界面处理电源键时，logind 不会再抢着关机或重启。

界面进程的退出码就是意图：`10` 由 session 脚本转成 `systemctl --no-block isolate multi-user.target`（回桌面），`20` 转成 `systemctl --no-block poweroff`，其它码原样返回。UI 自身的按键逻辑：

| 行为 | 阈值 |
| --- | --- |
| 短按电源键 | 唤醒并重置 15 秒熄屏计时 |
| 熄屏 | 15 秒无操作后写背光 0、清空 framebuffer（之后 0.1 秒一帧） |
| 长按回桌面 | 持续按住 2 秒，且电量计读数 ≥ 5% |
| 拔线关机 | 检测到离线超过 8 秒 |

UI 用 `cairo_image_surface` 在内存里画 720×520 的电池图形，按 framebuffer 的 `red/green/blue/transp` 位域打包成 16 位或 32 位像素，只把居中这块区域复制到 `/dev/fb0`。入场、脉冲、退场三组动画帧在电量或在线状态变化时一次性预打包，主循环按 1/60 秒的节拍挑一帧贴上去，按住电源键时另外单独刷新底部那 192×4 像素的进度条。framebuffer 少于 16 位或分辨率小于 720×520 会直接以退出码 2 结束。运行期间把 tty1 切到 `KD_GRAPHICS`，退出时恢复原模式。三个可执行模式是 `--snapshot FILE`（导出一张 PNG，固定 67% 且在线）、`--preview`（跑 8 秒后还原屏幕原内容）、`--live`（正式模式）。设 `MOCHA_REDUCED_MOTION=1` 会关掉呼吸与缩放动画。

### BC1.2 输入限流

`mocha-charge-policy.service` 拉起 `mocha-charge-policy.py`，它以 0.5 秒为周期轮询，判定顺序是：

| 情况 | 输入上限 |
| --- | --- |
| 充电器不在线（`online` != 1） | 500 mA |
| UDC state 为 `configured` / `address` / `default` / `suspended` | 500 mA（USB_HOST） |
| 检测为 DCP | 2 A |
| 检测为 CDP | 1.5 A |
| SDP 或未知、PHY runtime 非 active、PHY 时钟无效 | 500 mA |

`mocha-charge-detect.py` 走的是 Tegra124 PHY 的 primary/secondary 检测流程：先通过 `soft_connect` 断开、锁 `/run/mocha-charge-detect.lock` 并 mmap `/dev/mem` 的 `0x7d000000`，做 DCD 接触检测，再按 `0x408` 的 bit 18 判 primary 与 secondary，最后无论成败都会还原 `0x824`、`0x830` 两个寄存器并恢复连接。脚本注释里写明不使用 QC 电压协商。

温度与健康状态在策略进程里二次判断：`bq27520g4-0/temp` 小于 0 或大于等于 450（0.1 ℃ 单位），或者 `bq24190-charger/health` 不是 `Good`，上限一律回落到 500 mA。当前选择同时写进 `/run/mocha-charge-source.json`，状态变化才打印一行 `CHARGE_POLICY` 日志。电池侧的充电参数是 960 mA / 4.208 V，这两个数字见于本仓库说明文字，出处是设备侧的电池充电参数而非本仓库脚本，脚本本身只操作输入侧上限。

实测能读到正电流，但电量计的跳变还需要完善。这个充电模式是最小 Linux 充电模式，不是 SoC 完全断电。

## 关键注意事项

**补丁只能应用 0003。** `0003` 在同一个文件上包含 `0002` 的全部修改，文件是 30 行而不是十几行。把 `0002` 和 `0003` 串行应用会重复打同一处 hunk，直接失败或错位。`0002` 留在仓库里只用于对照。

**改过 vendor 就必须同时做两件事。** `build-niri.sh` 里应用补丁之后有一段内联 Python，重算 `src/backend/drm/compositor/mod.rs` 的 SHA256 并写回 `vendor/smithay/.cargo-checksum.json`；编译前还有 `cargo clean -p smithay`。少了任何一步，Cargo 可能继续复用 Git 依赖的不可变缓存，源码看着改了，实际二进制没变。

**不要在平板上编译。** 主机上的依赖里有一长串 `-dev` 包和交叉工具链，加上 Cargo 缓存，塞不进 1.25 GiB 的 APP 分区。平板只装运行产物。

**Noctalia 要连数据目录一起装。** 只复制 `noctalia` 二进制，壁纸缩略图会显示不出来；`build-noctalia.sh` 用 `meson install` 装整套内容，正是因为这一点。壁纸目录还需要用户可读。

**`/usr/local` 与私有挂载路径不是一回事。** 这里是公开安装的统一路径，原机用的是私有数据挂载路径。改成规范路径之后的整套新安装还没有重新做过实机验收。

亮度要生效得同时满足三件事：硬件背光驱动加载、Noctalia 里的设备名正确、sysfs 有写权限。设备在 sysfs 里注册成功不等于 PWM/LP8556 真的变了。音频同理，现代内核没有完整的 RT5671 声卡，PipeWire 跑起来只说明服务正常。

## 性能与显示

默认 Nouveau 着色器是硬件渲染，但 simpledrm 的扫描输出仍有同步与显存读回/CPU 搬运开销，动画大约 10 FPS。这里没有把兼容输出声称为最终的高性能路线。

`0003` 修掉横屏 damage 造成的贯穿黑条与残影，但它没法单独消除跨 GPU 的输出复制。

native Tegra + Nouveau 线性 DMA-BUF 的色块实机出图约 29.8 FPS。2026-10-10 原始内核＋native5 DTB＋手动分段校正的复测为 29.74 FPS；候选 Mesa 下的 Niri＋终端画面由用户确认正常。主动 DSI 复位候选后续通过自动 CPU/GPU/Niri 与第二次冷 RAM CPU/控制台验收；完整桌面与安装未验收，未默认启用。

软件 H.264 / Firefox 播放已经验证过，硬件解码与编码尚未完成。

## 未实现与计划

| 事项 | 状态 | 出处 |
| --- | --- | --- |
| native 桌面路径 | 候选 Mesa＋主动复位内核的自动分段 RAM Niri 画面正常；完整会话、触控与安装待完成，未默认启用 | 仓库 README 性能章节、`services/README.md` |
| 硬件解码 / 编码 | 未完成，只有软件 H.264 验证过 | 仓库 README 性能章节 |
| 音频硬件 | 现代内核无完整 RT5671 声卡，服务正常不代表出声 | `services/README.md` |
| APP 分区扩容 / 完整桌面 rootfs 迁移 | 尚无通过实机验收的自动方案 | 仓库 README 设备安装章节 |
| 规范路径下的整套新安装 | 尚未重新实机验收 | 仓库 README 构建章节、平板侧部署章节 |
| 电量计读数跳变 | 仍待完善 | 仓库 README 充电章节 |
| SoC 完全断电的充电模式 | 未做，当前是最小 Linux 充电模式 | 仓库 README 充电章节、`charging/mocha-charger.target` |
| 背光实际 PWM/LP8556 变化 | 注册成功不能证明，需分别验证 | `services/README.md` |
| CPU/GPU 调频与超频 | 保持未启用 | `CONTRIBUTING.md` |
| active seat 授权 | 公开安装从 tty1 直接会话开始，后台 `user@1000` 可能不被识别 | `services/README.md` |

`charging/mocha-charger-session` 以 `/usr/local/libexec` 为固定前缀，没有回退路径，前缀变化会让充电界面起不来。

## 许可与来源

本仓库新编写的工具与文档采用 GPL-2.0-only，许可正文见 [LICENSE](LICENSE)；Linux、U-Boot 和厂商 GPL 文件保留各自的 SPDX 标识、版权头和原许可证。Niri、Smithay、Noctalia 等外部项目沿用上游许可，本仓库的补丁不改变上游许可条款，具体条款以各上游仓库为准。参考源码出处见总入口仓库的 `SOURCES.md`。

本仓库不授予 NVIDIA CUDA、MIUI 固件、Wi-Fi/蓝牙固件或 TFA DSP 参数的再分发权，需要开发者自行从合法持有的设备或官方包中提取。另有 [LICENSE-NOTES.md](LICENSE-NOTES.md) 说明同一套边界。
