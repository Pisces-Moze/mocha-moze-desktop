# Mocha 后台冻结与内存策略

实现复用 systemd 257 / Linux cgroup v2 的 FreezeUnit、ThawUnit，App2Unit 应用隔离，earlyoom 1.8.2，systemd-zram-generator 1.2.1，wl-clipboard 的原生剪贴板事件，以及 Mozilla 签名的 Auto Tab Discard 0.7.7。Mocha 只增加 Niri 的可见性、媒体和恢复策略，不实现自己的冻结器、压缩器或浏览器扩展，也不常驻加载 GTK 界面库。

## 当前行为

- 普通 GUI 应用进入其他工作区 60 秒后冻结独立 `app-*.service` / `app-*.scope`，包含子进程。内存可用量低于 320 MiB 或 memory PSI some avg10 达到 5% 时，宽限期缩为 15 秒。
- 返回窗口时先解冻，再刷新布局；概览打开时解除冻结。熄屏后普通应用也可进入冻结。桌面、输入法、锁屏、音频、网络和 systemd 会话不纳入应用冻结范围。
- 终端、浏览器、媒体播放器、通信应用默认排除。终端可继续跑 LLM、编译和下载；浏览器保留下载、音频和 UI，由标签页机制细分处理。正在播放／录音以及已知剪贴板来源也保持运行。
- 不移动现有应用到别的 cgroup，不冻结整个 `app.slice` 或桌面壳服务。没有独立应用单元的进程跳过，后续从 Noctalia、App2Unit 启动的应用使用独立单元。
- 规则由 systemd 的应用单元处理；冻结自身不等于释放全部 RSS。已有 LZ4 zram0（384 MiB 逻辑）保留，新 zram1 增加 384 MiB 逻辑压缩交换，新增设备最多占 128 MiB 实体内存，按需使用。总逻辑交换约 768 MiB，不是增加 768 MiB 实体 RAM。
- 极低内存时 earlyoom 兜底：可用内存低于约 192 MiB 且剩余交换低于 15% 才请求退出进程，更严重时终止。冻结应用提高 `oom_score_adj`，解冻恢复原值；root 和关键会话进程排除。它不会因单纯存在文件缓存而清理缓存。

当前内核 `6.12.111-moze.1-native-vde2` 未启用 CONFIG_MEMCG，因此没有假装启用 `memory.reclaim` 或 systemd-oomd 的按组内存回收。冻结、zram 和 earlyoom 均可在现有内核运行。没有重编内核、刷写或停用同步保护。

## 标签页

Auto Tab Discard 使用浏览器原生 discard API，闲置 5 分钟后每批最多回收 2 个标签，单任务执行。保留音频、暂停媒体、固定标签、表单和有通知权限的页面；当前活动标签不回收。点击已卸载标签会重新加载，不是无损内存快照。

同时启用 Firefox 自带低内存卸载（最短闲置 60 秒、阈值 256 MiB）作为补充。浏览器自己的紧急内存处理与扩展的常规保留策略不同，不能保证所有页面内容在极端 OOM 下仍保留。没有关闭 Fission、沙箱或硬件解码。

扩展通过 `/etc/firefox/policies/policies.json` 的 ExtensionSettings 安装，保留原有策略，允许用户在附加组件中停用。`3rdparty.Extensions` 提供初始参数，扩展自己的选项页可继续调整。下载来源与哈希见 `config/memory-components.json`。

## 最大化不透明

当窗口铺满可用桌面、仍保留任务栏时，自动调用 Niri 已有的 `toggle-window-rule-opacity` 关闭该窗口的附加规则透明度；还原大小后恢复。不会增加关闭／全屏按钮或修改任务栏布局。窗口自身另外绘制的透明材质仍由应用控制。

## 管理

```sh
mocha-memory status
mocha-memory off  # 解冻并恢复本策略改动的窗口透明度与 OOM 优先级
mocha-memory on
```

用户参数：`~/.config/mocha/memory.json`，每次策略检查重新读取。`opaque_maximized=false` 关闭自动不透明；`exclude_app_ids` 追加需要长期后台运行的应用。状态位于 `$XDG_RUNTIME_DIR/mocha-freezer/state.json`，不记录网页内容或窗口标题。

服务停止／异常退出后，ExecStopPost 根据记录解冻；Niri IPC、音频保护或剪贴板监听不可用时不新增冻结。剪贴板事件监听持续保留，不保存或记录剪贴板内容。没有使用 SIGSTOP 去猜测进程组，也没有全局 drop_caches、禁用交换或在线 swapoff。

## 安装与回退

部署前安装 Debian 的 `earlyoom pulseaudio-utils python3-gi wl-clipboard systemd-zram-generator`。从固定提交取得 App2Unit 脚本及 GPL-3.0 许可证；从 AMO 取得签名 XPI，按 `memory-components.json` 校验。把本目录对应的 `tablet/` 脚本与用户服务、`config/` 默认参数安装到设备，启用 `mocha-app-freezer.service` 与 earlyoom；修改浏览器策略后需正常重启 Firefox。

```sh
sudo python3 tools/install-memory-policy.py --user mocha \
  --app2unit-root /path/to/pinned-app2unit \
  --addon /path/to/auto-tab-discard-0.7.7.xpi --extra-zram
```

安装器先校验固定脚本和 XPI 哈希，备份已有配置，复用系统包；不下载执行未知脚本，不自动重启浏览器，也不重置正在使用的 zram0。

本次备份位于设备数据区 `memory-policy-backup-20261026`，浏览器会话备份为私有目录。回退先 `mocha-memory off`，再禁用对应用户服务并恢复备份配置。新增 zram1 若已使用，不在低内存时强行 swapoff；移除生成器配置后在下一次正常开机退回。

只保留必要验证：独立小型应用单元冻结后计数停止、聚焦后继续、OOM 优先级还原；签名扩展已载入；现有 zram0 保持不变。2026-10-27 同步剪贴板通知修正，连续两次通知后进程未退出，音频和剪贴板保护均可用。没有做填满内存、OOM 破坏性测试或重复启动跑分。记录见 `validation/memory-policy-2026-10-26.json`。

来源：[systemd freezer](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)、[App2Unit](https://github.com/Vladimir-csp/app2unit)、[earlyoom](https://github.com/rfjakob/earlyoom)、[zram-generator](https://github.com/systemd/zram-generator)、[Auto Tab Discard](https://github.com/rNeomy/auto-tab-discard)。
