# Firefox 原生 V4L2 Request 候选

`../../patches/0024-firefox-v4l2-request.patch` 接续 Firefox 153 ESR 的 DRM PRIME 路径，为 Mocha 的 stateless V4L2 Request FFmpeg 增加原生接入。它不把现有的 stateful `h264_v4l2m2m` 当成 Tegra VDE。

补丁通过 FFmpeg 自报的 `v4l2request` 硬件配置探测，不硬编码树外硬件设备枚举值。保持 RDD 沙箱和浏览器进程隔离，媒体节点代理只接纳实际标识为 Tegra VDE 的 media 设备，增加有限的 media-request ioctl。默认 `media.ffmpeg.v4l2-request.enabled=false`，候选验收前不在普通用户配置启用。

## 格式与所有权

Tegra VDE 目前只接纳受限的逐行 8-bit 4:2:0 constrained Baseline H.264。CABAC、8×8 变换、隔行、自定义缩放及不兼容几何仍走软件解码。B 站可以发送不兼容流，不能把 MPV 的兼容样片通过当成浏览器或所有网站硬解通过。

`FFmpegV4L2Request.h` 检查三平面 DRM 描述符的对象索引、偏移、stride 和实际对象大小，保留独立 Y/U/V 对象以及交换的 U/V 索引，不复制像素、不接管 FFmpeg fd 的所有权。`test-descriptor.cpp` 直接测试补丁使用的转换函数，使用真实 FFmpeg／Mozilla 类型；27 项 ASan/UBSan 检查已通过。

## 构建状态

2026-10-27：此前完整构建在最终 `gkrust` Rust LTO 链接收到 SIGKILL，容器内存上限约 2.5 GiB；没有据此推断浏览器代码错误。后使用 Debian `rust.mk` 已支持的 `DEBIAN_RUST_LTO=-Clto=off` 单任务重新构建，并为旧 FFmpeg ABI 分支补齐 `MOZ_USE_HWDECODE` 条件。2026-10-30 核对完整构建完成，exit 0；实机 RDD/解码器与实际视频路径仍待确认。

最初按 153.4.0esr 文件生成；同一补丁已无 fuzz 应用于签名 Debian security 源索引提供的 **153.5.1esr-1~deb13u1**。`mozconfig.armhf` 的 Clang 19／Rust ARMhf 交叉配置已通过；修正启动配置访问器后，实际使用的 FFmpeg 61 解码模块 ARM C++ 编译也已通过。完整浏览器现已构建成功。当前实机 Firefox 尚未替换，不能声称已接通实机浏览器硬解。

候选安装需使用独立目录和独立测试 profile，核对实际 FFmpeg 库、RDD 解码器及 DMA-BUF 渲染，再比较同一视频的 CPU／内存。不要通过关闭 RDD 沙箱或站点隔离来绕过调试问题。上次桌面冻结后用户自行重启，没有持久的上一轮日志；故障原因尚未确认。

## 2026-11-01 实机进展

以上“待确认”是早期构建记录。当前独立候选已保留 RDD 沙箱，经补丁 `0007-ffmpeg-request-device-node-fallback.patch` 打开真实 VDE 节点并持续输出硬件帧；`0026-firefox-request-direct-import.patch` v2 允许显式启用、验证过的三平面线性 I420 直接导入。帧持有、池压力复制回退和导入失败后的复制保护仍保留。

Baseline 样片的安静稳态样本为 15 秒新增 452 帧、丢 17 帧，浏览器进程组约 1.07 核。测试 profile 设置 `media.ffmpeg.vaapi.force-surface-zero-copy=1`；这不是 VAAPI 设备，也不允许任意格式绕过检查。结果不能外推到 B 站所有视频、Main/High H.264、VP9 或 AV1。

完整 mach package 已完成，包含 omni.ja、匹配 NSS 及浏览器组件。ARMhf 包 SHA256 为 `08467b3d7aea3b7c748f529054cf27b956a9b4ee8990a97e4cfaedd4f9b6bfde`；包内 libxul 为 `c8423ce738c8e6581d5ea42f7dc413fa9adb62da57ea925a9ee9b812d1212027`。与实机手工 strip 候选的文件字节不同，但逐一比较的 35 个已分配 ELF 节区完全相同，差异在打包 strip 处理。

完整包已安装到 `/usr/local/lib/mocha-firefox-153.5.1-request-20261101` 并切换为默认，私有 FFmpeg、NSS 和真实 RDD/VDE 节点已核对。原浏览器目录及回退脚本保留，用户 profile 未删除或替换。

实际启动器的性能复测仍有较高丢帧，不能把独立测试中的最佳样本声称为已经稳定达到的默认性能。真实网站及最终镜像首次启动仍待验收；不能仅把 libxul 复制到旧版本目录，也不能通过删除用户 profile 规避兼容问题。
