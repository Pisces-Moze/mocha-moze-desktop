# Tegra124 视频解码与动态壁纸

当前实现使用 V4L2 Request 解码 H.264 逐行 CAVLC，驱动把 Tegra124 分块 DPB 转成线性三平面 YUV420M，再通过 DRM_PRIME / DMA-BUF 交给 GPU。仍有 CPU 布局转换，不是端到端零拷贝。CABAC、交错、自定义缩放矩阵和 8×8 transform 未开放；播放器列出的其他 Request 编码器名称也不代表 Tegra124 驱动支持这些格式。

## 构建和安装边界

`tools/build-vde-ffmpeg.py` 使用 FFmpeg 7.1.5 官方源包，回移植 Request API 并补齐三平面 Capture、DRM 描述和线性下载。`tools/build-vde-mpv.py` 使用 MPV 0.40.0，保留 Lua 5.2 以运行 Nyxuri 的壁纸配色钩子。两者使用独立 prefix，系统 libavcodec / libmpv 保持原样。源码及补丁哈希写入构建记录；这不是对 Debian 包补丁集的完整重建。

跨编译依赖使用 Debian trixie 的 armhf 开发包，包括 libdrm、libudev、libplacebo、libass、Wayland、EGL 和 Lua 5.2。私有 sysroot 同时需要 `usr/include/lua5.2` 和 `usr/include/arm-linux-gnueabihf`，不能只复制 Lua 主头文件。构建脚本不自动下载或升级系统依赖。

`tools/build-mpvpaper-fullscreen.py` 构建标准名称的 `mpvpaper` 和配套 `mpvpaper-holder`。`0009-mpvpaper-fractional-scale.patch` 支持 Fractional Scale / Viewporter；1.5 倍缩放下，实机缓冲由 2730×2048 改为物理尺寸 2048×1536。协议来源是 [Wayland fractional-scale](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/staging/fractional-scale/fractional-scale-v1.xml) 和 [Viewporter](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/blob/main/stable/viewporter/viewporter.xml)，生成的协议代码保留上游版权头。缺少协议时沿用整数缩放。

实机安装先执行 `tools/install-mpvpaper-runtime.py --check`，再使用相同参数安装：

```sh
python3 tools/install-mpvpaper-runtime.py \
  --binary /path/to/mpvpaper \
  --holder /path/to/mpvpaper-holder \
  --decoder-runtime /path/to/verified/runtime \
  --backup-dir /path/to/private/backups \
  --check
```

运行时目录必须有 `build-manifest.json`，列出的文件和符号链接逐一校验，拒绝额外文件。安装器保留标准进程名，备份入口和二进制，将匹配的解码库放入 root 所有的版本目录。入口先经 `mocha-native-app` 选择已有 Mesa，再选择独立解码库。当前内核没有匹配 VDE 设备时，保留原系统播放器库，并把 Request 选项回退为 `auto`。

`0007-noctalia-fullscreen-decoder-release.patch` 增加解码后端和全屏资源释放设置。`hwdec=auto` 的安全列表不会选择此实验 Request 后端，需要在已验证的内核上显式选择 `v4l2request`。`0008-nyxuri-wallpaper-hook-stock-codecs.patch` 保留原 Lua 钩子，并让它调用的系统 FFmpeg 使用系统库，避免缩略图生成继承仅用于解码的私有库。

## 壁纸生命周期

2026-10-20：`0012-wallpaper-static-handover.patch` 让静态切换与旧播放器退出由插件统一管理，通过选择代次拒绝迟到的启动／抽帧回调；显式静态选择清除旧视频恢复状态。实机单次切换已通过，播放器及 holder 退出，VDE 挂起且模块引用归零。

`0013-wallpaper-resource-pressure.patch` 在插件现有的 1 Hz 更新中读取 MemAvailable 与 memory／CPU PSI。默认低阈值 128 MiB、恢复 256 MiB，持续压力等待 3 秒、稳定恢复等待 15 秒；低于 64 MiB 立即释放。CPU PSI some 的持续等待阈值为 85%，恢复低于 25%。它退出播放器、释放解码资源并保留播放位置，恢复有滞回，用户选择静态后不会重新拉起旧视频。各项设置有中文／英文标签；没有额外轮询守护进程，也不因弹窗或概览本身暂停。

实机通过临时提高检测阈值触发释放，没有分配大量内存或制造 OOM；确认持续停止、VDE suspend／引用归零，以及恢复后的 Request 硬解。播放位置保留、短暂压力忽略与旧异步回调由实际服务源码的 Lua 回归覆盖。`0015-wallpaper-pressure-reconfigure.patch` 补齐压力期间设置重载保留进度，以及关闭 CPU 策略后的恢复；回归通过，已带备份安装并核对最终源码。

安装器现在处理 `0010`、`0011`、`0012`、`0013`、`0015`、`0017`、`0019` 的完整顺序，在临时目录中反向识别已有前缀后重放。`--check` 不修改目标；安装同时备份插件、清单、两份翻译和选择器，拒绝冲突源码。八种前缀、重复检查、备份和冲突拒绝已通过隔离测试。

`0014-mpvpaper-render-update-flags.patch` 只在 libmpv 返回 `MPV_RENDER_UPDATE_FRAME` 时提交新画面；初始化／尺寸变化的显式绘制保持原路径。已带备份安装并通过真实硬解播放，但短 CPU 对照没有显示下降，不能将它算作卡顿修复。最初的实际遮挡策略保留透明窗口后仍可见的动态背景；下述工作区策略另外满足占满桌面时释放资源的要求。

`0016-niri-wallpaper-visibility.patch` 在 Niri 的 X-Ray 感知可见性更新后发布每个输出的背景状态。通过 `MOCHA_WALLPAPER_VISIBILITY=1` 构建启用；只在状态变化时原子写入会话运行目录，包含当前 Niri PID，未知背景保留播放。它沿用背景及 X-Ray render-element 的真实展示结果，透明窗口不会被误判为完全遮挡。

`0017-noctalia-wallpaper-occlusion.patch` 在已有的 1 Hz 更新中读取对应会话的状态。默认持续遮挡 2 秒后退出播放器并保留进度；多输出的通配选择须全部隐藏才释放。概览和 Noctalia 弹窗始终保持播放，缺失／旧会话信号继续播放；露出桌面时仍服从内存压力与用户静态选择。设置提供遮挡释放开关和等待时间。

两项已带备份持久安装。实机临时关闭旧的前台全屏策略后，独立确认全屏及两个不透明窗口联合覆盖均使播放器／holder 归零、VDE suspended／引用 0；概览、控制中心及露出桌面均恢复 `v4l2request`。诊断窗口和临时配置已撤销，恢复用户原静态选择。单屏实机结果与多输出沙箱边界见 [遮挡释放验证](../validation/wallpaper-occlusion-2026-10-20.json)。这项验证不代表动态桌面卡顿已修复。

本轮证据与限制见 [生命周期与压力检查](../validation/wallpaper-lifecycle-2026-10-20.json)。以下为此前的前台全屏检查；不能据此声称已支持所有窗口组合。

2026-10-21：用户所说的全屏包括任务栏仍显示的占满工作区。`0018-niri-workarea-coverage.patch` 因此在 schema 2 中增加独立的 `workarea_covered`，按当前输出、活动工作区的窗口矩形联合判断，排除任务栏占用区，容纳最大 32 逻辑像素的配置间距及 2 逻辑像素的分数缩放取整误差。背景真实可见性 `visible` 仍单独保留。交互拖动、概览及工作区切换时不判定为覆盖；计算限制矩形和碎片数，异常状态继续播放。

`0019-noctalia-workarea-coverage.patch` 复用遮挡释放开关和等待时间，工作区占满后退出播放器，缓存背景继续供透明和毛玻璃效果使用。打开弹窗／概览、露出桌面后恢复硬解，仍服从内存压力和用户静态选择。首个候选在实机通过占满工作区释放与概览恢复；两个半宽窗口留下的分数缩放细边导致未释放，已追加真实几何回归并构建取整修复。最终候选已持久安装，恢复 USB 连接后通过集中实机检查：占满工作区与两列各半宽均为播放器／holder 0、VDE suspended／引用 0；部分露出、概览和控制中心保持播放，露出桌面恢复 `v4l2request`。前次黑屏没有留下上一轮日志或 pstore，原因尚未确定。进展见 [工作区覆盖验证](../validation/wallpaper-workarea-2026-10-21.json)。

仅前台全屏窗口触发 FULL 模式。开启资源释放时，播放器保存进度后 exec 配套 holder，释放视频设备、DMA-BUF 和大部分驻留内存；离开全屏后恢复。弹窗、概览、后台工作区中的全屏窗口和帧回调延迟均不触发此策略。

实机三轮资源释放验证中，播放器驻留内存从约 47～52 MiB 降至约 1.3 MiB，视频设备和 DMA-BUF 句柄归零，VDE 进入 runtime suspend，恢复后仍使用 Request。开发模块、完整内核、独立播放器、正式插件和分数缩放的结果分别记录，不能把某一阶段通过外推到整个桌面。

原始壁纸保留，另生成硬件兼容的 1536×1086 / 30 fps CAVLC 版本。短 GOP 版本每 30 帧提供恢复点，避免全屏退出后从过远的关键帧追赶。用户媒体、密码和整盘备份均不进入仓库。模糊纹理池和区域裁剪候选没有解决弹窗卡顿，实机已恢复原合成器。

2026-10-18 确认 Nyxuri 的面板规则只匹配旧 `nyxuri/clavis` 命名空间，Noctalia 的 `noctalia-panel` / `noctalia-osd` 因此选择默认 X-Ray 路径，处理整个动态背景。适配器现在将实际命名空间匹配到上游已有的面板策略；用户反馈稍有改善，但 CPU 占用仍高。复查时播放器未运行、选择状态为空，性能对照条件不完整，不能把这轮帧时间差作为完整动态桌面的收益。

`0018-noctalia-hidden-spectrum-idle.patch` 修复频谱组件隐藏后仍保留待更新标志、持续请求帧的问题。真实调度方法的 CPU 测试替身在旧代码上复现断言失败，修复后通过 ASan / UBSan。首次离线构建缺少实机已有的 Dock 图标兼容补丁，未用于安装；补齐该补丁后重新构建，保留 ARM 插件对齐、锁屏键盘与主题，已在实机安装并重载。静态桌面两次短采样中，整机 CPU 由旧版 4.27%／5.37% 变为 4.67%／4.64%，没有证明显著降耗。组件的可见动画、编辑器预览与音频唤醒路径保留。

`0010-noctalia-picker-managed-video.patch` 与 `0011-nyxuri-picker-plugin-lifecycle.patch` 将 Nyxuri 视频选择交给官方插件，避免另起播放器绕过硬解和全屏设置；保留选择器写入时的插件元数据，并将 holder 纳入进程清理。使用 `tools/install-nyxuri-wallpaper-bridge.py --check` 同时核对插件与选择器源码，确认后才安装配套修改；目标系统需要 `patch` 工具。安装器保留备份，不自动重启桌面或更改壁纸选择。Python 选择器测试及实际服务源码的 Lua 沙箱测试已通过；实机配套源码安装、重载及受管 IPC 硬解选择通过，完整选择器界面、锁屏和重启恢复仍待验收。浏览器硬解、蓝牙和扬声器也仍待验收。

第二次 VDE2 RAM 冷启动保持内置驱动关闭，由 root 所有的独立模块经过显式检查后绑定；GStreamer／FFmpeg 各 96 帧比较、低频硬件读回均通过，解码后无锁或 IOMMU 警告。受管壁纸在三轮弹窗／概览期间保持 Request 播放，采样的视频及解码丢帧计数均为零；该短测试不能替代长期流畅性或旧新版本的性能对照。已按授权删除三份测试视频，保留原片和当前高画质版本；释放约 6.14 MiB，本机核验副本仍保留。

第二次启动的三轮全屏检查也确认内存由约 52 MiB 降至 1.3 MiB，视频／DMA-BUF 句柄和模块引用归零，VDE 挂起，退出后恢复 Request。恢复阶段仍有显示丢帧，不能宣称全程无丢帧。VDE2 启动文件、匹配加载器和保留 DFLL 校验的 CPU／LZ4 交换策略已带备份持久安装，普通启动验收已通过。充电转桌面时由 root 硬件服务写入精确 release 标记，避免只依赖不可改变的启动命令行；充电目标本身不加载 VDE。

验证记录见 [独立壁纸验证](../validation/vde-wallpaper-2026-10-17.json)、[正式插件验证](../validation/vde-wallpaper-official-2026-10-17.json)、[桌面优化跟进](../validation/desktop-idle-candidates-2026-10-18.json) 和 Linux 仓库的 `moze/validation/vde-player-2026-10-17.json`、`vde-full-kernel-2026-10-17.json`、`vde-default-install-2026-10-18.json`。

## 2026-10-20 布局转换候选结论

按行展开每个 GOB 的四个 16 字节片段，保持连续的目标写入，缓存内存微基准中亮度／色度约快 1.55／1.74 倍；54 种几何及 ASan／UBSan 边界检查通过。匹配 VDE2 的单独模块只改变该转换头文件，实际 Request 硬解的 96 帧与软件参考逐帧相同。

但两组各两次 120 帧的实际硬解对照没有收益：中位耗时由约 2.66 秒变为 2.75 秒，整机忙碌 CPU 采样也未下降。频率未固定，整机 CPU 包含后台工作，不能精确归因；结果足以拒绝将该候选作为已证实的性能优化。原模块及生产转换头文件已恢复，静态壁纸选择保持。候选和微基准仅归档在 Linux 仓库 tests/candidates，详见 `moze/validation/vde-row64-candidate-2026-10-20.json`。继续排查真实 DMA／缓存维护与 GPU 合成开销，不能从缓存微基准外推桌面流畅性。

## 2026-10-22 命令缓冲上传

`0023-mesa-gk20a-command-upload.patch` 为 GK20A GART 命令 ring 使用内核支持的 WC 映射，初始分配与增长使用同一策略；不跳过内核同步，不改变导入 DMA-BUF、读回或 fence 分配。构建器执行 8 项设备／域／ABI／增长策略回归和既有五套检查。候选已持久安装，用户确认卡顿减轻，画质和效果保持原设置；有限短采样不代表完整帧时间或全部卡顿已解决。见 [实机记录](../validation/mesa-command-upload-2026-10-22.json)。
