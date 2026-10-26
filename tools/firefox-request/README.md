# Firefox 原生 V4L2 Request 候选

`../../patches/0024-firefox-v4l2-request.patch` 接续 Firefox 153 ESR 的 DRM PRIME 路径，为 Mocha 的 stateless V4L2 Request FFmpeg 增加原生接入。它不把现有的 stateful `h264_v4l2m2m` 当成 Tegra VDE。

补丁通过 FFmpeg 自报的 `v4l2request` 硬件配置探测，不硬编码树外硬件设备枚举值。保持 RDD 沙箱和浏览器进程隔离，媒体节点代理只接纳实际标识为 Tegra VDE 的 media 设备，增加有限的 media-request ioctl。默认 `media.ffmpeg.v4l2-request.enabled=false`，候选验收前不在普通用户配置启用。

## 格式与所有权

Tegra VDE 目前只接纳受限的逐行 8-bit 4:2:0 constrained Baseline H.264。CABAC、8×8 变换、隔行、自定义缩放及不兼容几何仍走软件解码。B 站可以发送不兼容流，不能把 MPV 的兼容样片通过当成浏览器或所有网站硬解通过。

`FFmpegV4L2Request.h` 检查三平面 DRM 描述符的对象索引、偏移、stride 和实际对象大小，保留独立 Y/U/V 对象以及交换的 U/V 索引，不复制像素、不接管 FFmpeg fd 的所有权。`test-descriptor.cpp` 直接测试补丁使用的转换函数，使用真实 FFmpeg／Mozilla 类型；27 项 ASan/UBSan 检查已通过。

## 构建状态

2026-10-27：此前完整构建在最终 `gkrust` Rust LTO 链接收到 SIGKILL，容器内存上限约 2.5 GiB；没有据此推断浏览器代码错误。现使用 Debian `rust.mk` 已支持的 `DEBIAN_RUST_LTO=-Clto=off` 单任务重新构建。完整浏览器、实机 RDD/解码器与实际视频路径仍待确认。

最初按 153.4.0esr 文件生成；同一补丁已无 fuzz 应用于签名 Debian security 源索引提供的 **153.5.1esr-1~deb13u1**。`mozconfig.armhf` 的 Clang 19／Rust ARMhf 交叉配置已通过；修正启动配置访问器后，实际使用的 FFmpeg 61 解码模块 ARM C++ 编译也已通过。完整浏览器正在构建。当前实机 Firefox 尚未替换，不能声称已接通实机浏览器硬解。

候选安装需使用独立目录和独立测试 profile，核对实际 FFmpeg 库、RDD 解码器及 DMA-BUF 渲染，再比较同一视频的 CPU／内存。不要通过关闭 RDD 沙箱或站点隔离来绕过调试问题。上次桌面冻结后用户自行重启，没有持久的上一轮日志；故障原因尚未确认。
