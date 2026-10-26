# Nyxuri 实机功能审计（2026-10-17）

平板运行 `6.12.111-moze.1-native-runtime`、原生 Tegra/Nouveau、匹配的 native-sync Mesa、Niri 26.04 和 Noctalia 5.2.1。APP 已扩为 3 GiB，正常启动验收通过。

结论：13 个已部署的官方插件均由运行中的 Noctalia 报告为 enabled；这不等于它们的所有外部功能均可使用。以下分别记录实际条件，不以配置文件存在或诊断命令返回 0 代替验收。

## 来源与范围

- 实机 Nyxuri 固定为 `ech678/Nyxuri@ebafe03c9bdf1291eeb83d0f8c368d40a63ccdfd`。
- 本轮对照上游 `8183767da4cf7438871cd9c6af1ab0ef3f22402e`。新增 Mango 适配、实验 Shell 的变化及配置引擎修订尚未整体部署；不能把当前实机称为最新上游的全部实现。
- 官方插件目录固定为 `noctalia-dev/official-plugins@9aec34181e46789b281263942092ac552f661d1a`。
- 继续使用 Noctalia。实验 Nyxuri Shell、其他窗口管理器、Arch/AUR 包管理和可选应用清单不属于本 Debian 触屏会话的运行验收。

## 核心桌面

| 功能 | 本轮证据与限制 |
| --- | --- |
| Niri / Noctalia | 物理 tty1 的既有用户会话保持运行；IPC 状态 unlocked，任务栏可见 |
| Nyxuri 工具 | Orbit、壁纸选择器、翻译、触屏效果设置入口存在，相关脚本可执行；GtkLayerShell Python 绑定通过导入检查 |
| 中文输入 / NyxMellow | Fcitx5 服务运行；Nyxuri 诊断确认 NyxMellow 启用 |
| GTK 主题 | 已渲染；Noctalia 5.2.1 有内置 palette generator。另已交叉构建并安装 Matugen 4.2.0 CLI，不能把诊断中可选 CLI 缺失等同于内置取色失效 |
| Fish / Fisher / nyxhelp | Fish 内确认 `fisher`、`nyxhelp` 函数存在；`nyxhelp` 不是独立 PATH 可执行文件，不能据此误判缺失 |
| 护眼 / Scratchpad | wlsunset、tmux 存在，脚本可执行；本轮未重新验收所有交互 |
| 桌面门户 | 主门户及 GTK 后端运行；文档门户失败，日志为缺少 `/dev/fuse`，当前内核 `CONFIG_FUSE_FS` 未启用 |
| 蓝牙 / 扬声器 | 蓝牙 HCI Read Local Version 超时，ALSA 尚无声卡；继续适配，不能以 BlueZ / PipeWire 服务运行代替硬件通过 |

## 官方插件

以下 13 项在该轮运行时插件列表中均为 enabled。本文保留分阶段记录；最新进展与限制见 [VDE-PLAYER.md](VDE-PLAYER.md)，早期软件播放数据不代表当前硬解路径。

| 插件 | 运行条件与限制 |
| --- | --- |
| mpvpaper | 已实际循环播放用户视频；修复播放器进程名，切换／禁用可以结束原进程，持久配置保留单播放器 |
| world_clock | 服务注册；面板及实际时间显示仍需独立验证 |
| timer | 服务及闹钟资源加载；扬声器未适配，不能验收声音提醒 |
| notes | 已启用；不读取用户笔记内容 |
| kaomoji | 启动器 provider 已启用；未以内容读取代替用户使用验收 |
| bongocat | 组件可用但需用户放置到任务栏，不擅自增加任务栏项目 |
| example | 示例服务注册；示例项目不是必要桌面功能 |
| wallhaven | 已启用；在线查询依赖网络，账户限制内容需要用户配置 |
| translator | 已启用；Google / DeepL 后端需要可达网络，DeepL 密钥由用户自行设置 |
| bitwarden | 服务注册，明确报告 `bw not found`；缺命令行依赖及用户登录，未声称密码库可用 |
| screen_recorder | 服务注册，明确报告缺少 `gpu-screen-recorder`；已安装 slurp / wf-recorder，后者不等于原插件的后端，仍未通过原插件录屏验收 |
| wallpaper_depth | 已启用；模型与专用 Python 推理环境未完成安装或推理验证，不能声称已有深度遮罩 |
| umbriel-companion | 已启用；当前会话为 Niri，没有 Umbriel compositor / socket，功能不适用 |

## 动态壁纸与资源占用

用户原片仅保存在实机和本地私有目录，不提交视频或截图至仓库。原片 4092×2894 / 60fps / 46,331,454 字节保持完整；另生成 1536×1086 / 30fps 和 1024×724 / 24fps 的独立 H.264 无音轨版本，均完整解码并校验传输与实机回读 SHA256。

默认选择 1024 宽版本并为 mpvpaper 设置 `profile=fast`；原片和两个转换版本都可在 Nyxuri 壁纸选择器选择。参数保留在 Noctalia → 插件 → mpvpaper 设置，不关闭用户的桌面模糊、X-Ray 或动画。

实际发现旧 ELF 名为 `mocha-mpvpaper`，不匹配上游 `(^|/)mpvpaper …` / `pkill -x mpvpaper`，导致切换后旧播放器残留。现在 ELF 路径为 `/usr/local/libexec/mocha-mpvpaper-runtime/mpvpaper`，入口仍经 `mocha-native-app` 使用匹配图形库。工具 `tools/install-mpvpaper-runtime.py` 保留这一命名约束并备份原入口。

单播放器、全屏原生桌面、`scale 1.5 / transform 270`、无应用窗口条件下，两个版本各 12 秒连续采样未新增显示丢帧；CPU 分别约 161% / 254%（单核 100%，四核总量 400%）。这仅是短时壁纸采样，不能外推整个桌面固定帧率。MPV `hwdec-current=no`，当前仍是软件解码，硬件视频解码尚未验收。

本轮通过签名校验的清华 Debian trixie / security 镜像补装 `socat`、`curl`、`slurp`、`wf-recorder`、`inotify-tools`；不整体升级运行中的图形库或桌面版本。

用户实际观察到播放壁纸后任务栏动画卡顿，这项仍未解决。弹窗及概览打开时不暂停壁纸；本轮暂停试验已撤回，原播放器恢复。全屏应用遮挡时释放播放器内存的策略尚未实现，不把上游自动暂停等同于释放内存。

已安装 GStreamer 1.26.2 的 stateless V4L2 插件用于驱动验收；当前默认内核未提供可用的 Tegra124 解码设备。后续 RAM 内核加独立开发模块已完成 GStreamer 与 FFmpeg 各四组 96 帧 I420 对照，显式 Request 解码、三平面 DRM_PRIME / DMA-BUF GPU 显示已在 MPV 中由用户确认正常。20 秒采样没有新增 decoder / VO 丢帧，进程 CPU 约单核 26.45%；此值不包含内核 worker / 合成器，不能与前述不同条件的软件壁纸测试直接计算整机收益。

独立 FFmpeg 7.1.5 / MPV 0.40.0 候选保留系统全局库，尚未替换默认引导。新增源码补丁提供仅由前台全屏窗口驱动的播放器退出／恢复，以及可选 Request 解码后端；弹窗和概览不触发暂停。实际官方插件安装、全屏内存释放、恢复播放和动画流畅度仍待逐项验收。浏览器硬解尚未完成。
