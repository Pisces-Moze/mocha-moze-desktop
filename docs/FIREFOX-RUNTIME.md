# Firefox 运行库与 Request 候选

2026-11-01，实机的 Firefox 153.4.0esr 在独立 profile 下通过 headless 页面截图和
Wayland 页面 JavaScript 检查。进程映射确认加载了 Firefox 自带 NSS 和已修复 Tegra Mesa。
直接对 libxul 执行 ldd 得到的系统 NSS 缺版本信息，不能单独证明实际 Firefox 进程使用了
那个系统库；应核对进程 maps 与启动环境。

## 正常启动器

`tools/mocha-firefox` 先调用已安装的 `mocha-native-app` 选择配套 Mesa，再把 Firefox
自带库目录置于 `LD_LIBRARY_PATH` 首位。顺序不可颠倒，否则 native-app 会覆盖该变量。
该启动器不改变浏览器沙箱或用户 profile。

在源码目录以 root 执行 `python3 tools/install-firefox-launcher.py`，会安装启动器并更新
现有系统和用户 Firefox desktop 项，保留 URL 参数与翻译。修改前的文件保存在
`/var/backups/mocha-firefox-launcher/<时间>/`。不会替换 Firefox 二进制。

## 硬解候选的实际状态

153.5.1 Request 候选已完成 ARM 构建并取回；独立 profile 页面正常。2026-11-01 已安装为原型机默认浏览器，但真实网站播放与性能验收仍未通过，不能据此宣称网站硬解。
完整候选需要携带自带 NSS，并使用配套 FFmpeg 61，不能只复制 libxul。

早期实测 RDD 沙箱保持开启时，Request codec 能打开，但首次 get_format 后初始化失败，
`avcodec_send_packet` 返回 InvalidData，浏览器随即回退软件解码。因此不能用
`IsHardwareAccelerated=true` 的初始化日志声称硬解已通过。

沙箱诊断已看到 `/dev/media0`、`/dev/video0` 被授权，同时首次媒体初始化出现目录遍历被拒绝：

- 单独允许根目录只读仍失败：broker 的 AllowOpen 过滤掉了 `O_PATH`。
- 增加仅限已有读权限目录的 `O_PATH` 句柄支持后，根目录拒绝消失，下一处拒绝变为
  `/proc/<RDD pid>/fdinfo/<fd>`，这是该进程自身目录句柄的元数据读取。
- `0025-firefox-request-root-directory.patch` 组合了根目录本身只读、受限目录句柄和仅该
  RDD 自身 fdinfo 子树的访问；不放开整个根文件系统或其它进程的 `/proc`。

正式 mach package 的系统调用跟踪随后定位到 `OpenAtTrap` 拒绝 libudev 的 fd-relative
`openat`。这不等于设备节点缺权限，继续放宽路径白名单也不能解决它。

## 设备节点回退：已硬解出图，播放性能尚未通过

`patches/vde/0007-ffmpeg-request-device-node-fallback.patch` 保留正常 udev 路径；枚举失败
后扫描 `/dev/media[0-9]+`，通过内核 media topology 的 major/minor 匹配
`/dev/video[0-9]+`。忽略符号链接，打开后再用 fstat 校验字符设备及设备号，并复用原有
解码能力、格式、Request controls 检查。未关闭 RDD 沙箱或增加设备授权。
`tools/build-vde-ffmpeg.py` 已纳入该补丁；实机试验库放在独立候选目录，未覆盖默认播放器。

2026-11-01 实机已持续输出 300 多帧 V4L2 图像，RDD 同时持有 media0/video0；日志包含
VDE 驱动、YM12 CAPTURE 和每帧输出，截图颜色正常。不是仅凭初始化标志判断成功。
但关闭详细日志后的短样本仍有严重丢帧：1440×1080/30fps 下 458 帧计数中丢帧 426，
整组浏览器约 1.82 核。软件对照约 2.61 核、574 帧计数中丢帧 144；采样启动时间存在
差异，这些数值仅用于定位瓶颈，不能宣称总体性能提升。强制 WebRender 未改善结果。
当前候选仍不满足替换默认浏览器的门槛；下一步应排查硬解帧送入合成显示后的瓶颈。

### 直接导入候选

`0026-firefox-request-direct-import.patch` 已完成 ARM 构建，并只更新独立候选。共享平台
硬解能力测试尚未正确识别 Request，导致已有显式零拷贝设置仍无法生效；补丁只对实际
`v4l2request`、已校验的 I420 三平面 LINEAR 缓冲及显式
`media.ffmpeg.vaapi.force-surface-zero-copy=1` 提供直接导入。保留 FFmpeg 引用生命周期，
持有/渲染缓冲达到已知池容量 3/4 时仍复制；直接导入或纹理验证失败时回退复制，并关闭
该池后续的直接导入尝试。其它后端与默认设置不变。

实机日志记录 585 次直接导入、0 次逐帧复制，未观察到导入失败。冷启动单次样本总帧
536、丢帧 103；不能把启动加载的丢帧直接当成稳态播放表现。随后关闭诊断日志、等待
20 秒再采样：15 秒内总帧从 238 增至 690，丢帧从 80 增至 97，即新增 452 帧中丢 17 帧
（约 3.8%），浏览器进程组约 1.07 核。样本跨过一次视频循环，进程正常退出，未改 owner
profile。仍有少量丢帧；实际网站与其它编码档次、完整打包和持久安装验收尚未完成，默认
浏览器未替换。候选 libxul SHA256：
`f4c30cb7827e8aea6560056929ff49ec0143dce9de6eb35467f70f715fa4808d`。

验收状态见 `validation/firefox-runtime-2026-11-01.json`。最终镜像仍须以实际硬件帧输出、
受支持 Baseline 视频连续播放、RDD 不回退软件解码为准。

## 2026-11-01 部署状态与 2026-11-05 复核

- 已装默认：完整包 153.5.1esr，包 SHA256 `08467b3d7aea…b6bfde`，libxul `c8423ce738c8…12027`；启动器 `/usr/local/bin/mocha-firefox` 先选配套 Mesa，再把包内 NSS 与 `codecs/` 放到 `LD_LIBRARY_PATH` 首位；用户原 profile 未删除或替换，回退脚本在 `/var/backups/mocha-firefox/activation-20261101-161053/rollback.py`。
- 硬解链路：RDD 沙箱保持开启；`media.ffmpeg.v4l2-request.enabled=true`、`media.ffmpeg.vaapi.force-surface-zero-copy=1` 生效；RDD 同时持有 `/dev/media0`、`/dev/video0`；设备节点回退补丁（`patches/vde/0007-ffmpeg-request-device-node-fallback.patch`）绕过 libudev fd-relative 枚举，直接导入记录 585 次、逐帧复制 0 次、导入失败 0 次。
- 性能证据（同一 1440×1080/30fps Constrained Baseline 样片，不是最终验收）：安静稳态 15 秒新增 452 帧、丢 17 帧（约 3.8%），浏览器进程组约 1.07 核；软件对照约 2.61 核。冷启动与不同窗口/桌面覆盖层条件下丢帧更高，**不能把最佳样本当作默认表现**。
- 未完成：真实视频网站最低画质的实际硬解与性能验收；丢帧/CPU 根因（视频缩放/合成、复制路径、帧同步）排查；完整候选打包与镜像首次启动验收。2026-11-05 复核时工作站到平板/构建主机的 SSH 在 kex 阶段被远端关闭，无法重跑实机项。
- 下一步（一次只改一个变量）：同视频、同画质、同供电条件下依次比较窗口尺寸/缩放、桌面覆盖层与动态壁纸、`force-surface-zero-copy`、合成器帧时序；同步记录 CPU/GPU/内存/掉帧与帧计数后再决定是否接受该候选。不要通过关闭 RDD 沙箱或站点隔离绕过问题。
