# Firefox 视频与内存（2026-10-23）

实机 B 站最低画质仍使用 AV1：`dav1d-worker` 两个线程在一次 4 秒采样中合计占约 61% 单核 CPU，Firefox 另有网页、渲染及合成开销，VDE 当时休眠。不能用“最低画质”或“GPU 硬件渲染”推断视频已硬解。此前 V4L2 Request 的 MPV 硬解也不等于 Firefox 支持同一接口。

内核报告约 1664 MiB 可用物理内存。首次读取 MemAvailable 约 309 MiB，随后约 442 MiB；384 MiB LZ4 交换已占用大半。进程 RSS 包含共享页，不能直接相加当作实际独占量；MemFree 很低也不能单独证明内存耗尽。本轮不清除系统页缓存、不关闭站点隔离／沙箱、不增添磁盘交换，也不把压缩交换容量当作新增物理内存。

## 已安装的可调整默认值

| 项目 | 默认值 | 作用与限制 |
|---|---|---|
| AV1／HEVC | 关闭 | 避开这块硬件不支持的解码格式，让提供备选流的网站使用 AVC；AV1／HEVC 独占资源会无法播放，可在 about:config 调回 |
| 备用内容进程 | 不预分配 | 减少尚无页面的常驻内存，首次打开页面可能略慢 |
| 普通／同源隔离进程上限 | 2／1 | 保留站点隔离，不是限制整个浏览器只有两个进程 |
| HTTP 内存缓存 | 16 MiB | 不禁用缓存，保留磁盘缓存 |
| 图片 surface cache | 64 MiB | 限制可复用图片缓存，活跃视频与网页分配另计 |
| 媒体内存缓存合计 | 32 MiB | 约束可用的 memory-backed cache，不是整个播放器的硬性内存上限 |
| 前进／后退页面快照 | 2 | 较久的历史页面可能需要重新加载 |

值见 [默认首选项](../config/firefox-mocha-low-memory.js) 与 [启动策略默认值](../config/firefox-mocha-low-memory-policies.json)，可用 about:config 覆盖，不锁定设置。浏览器重启后生效。网页分辨率、帧率、桌面动画与壁纸文件未调整。

Linux 的这版 Firefox 会在缺乏支持时将 `browser.tabs.unloadOnLowMemory` 改回 false；本轮核对到了该行为，因此没有把自动卸载标签列为可用优化，也没有强制关闭后台标签。

## 安装、保留已有策略与回退

实机浏览器位于数据区，`/usr/lib/firefox-esr` 指向 `/srv/mocha-data/codex-debian-desktop/firefox-esr`。仅把文件放进 `/etc/firefox-esr` 不保证这套独立运行树会读取它：

1. 将 JS 安装为 `/etc/firefox-esr/mocha-low-memory.js`，在实际浏览器的 `defaults/pref/mocha-low-memory.js` 建立指向它的符号链接。
2. 将 JSON 中的 `policies.Preferences` 合并到 `/etc/firefox/policies/policies.json`。有同名既有策略时先检查冲突，保留其他策略；不整文件覆盖。进程预分配值需要这一步，避免稍后加载的浏览器默认值覆盖 GRE 默认值。
3. 从浏览器菜单正常退出，备份 profile 的会话与 prefs，再重新打开。安装不修改密码、Cookie、书签或视频清晰度。

本轮在独立临时浏览器实例读取实际首选项：十项默认值均生效、未成为锁定用户值，MediaSource 对 AV1／HEVC 为 false、对 AVC 为 true。该无界面检查仅验证配置与格式协商，不作为 GPU 渲染或视频帧率测试。临时自动化进程已停止，用户浏览器没有启用调试端口。

回退时恢复安装前备份；只移除本项目创建的链接和 JS，从策略文件中撤销本项目的 `dom.ipc.processPrelaunch.enabled` 默认值，保留其他条目，然后正常重启 Firefox。已保存原始“文件不存在”的状态，不能用中间试验配置代替最初备份。

## 同一视频恢复播放后的短采样

用户恢复 B 站同一视频、同一最低画质后，6 秒采样看到了 `av:h264:df0/df1`，不再出现 `dav1d-worker`。RDD 解码进程约占单核 25%，Firefox 主进程约 92%，视频页面约 72.3%；CPU 总开销仍明显，不能把解码格式切换当成浏览器整体性能已解决。这些百分比以一个核心为 100%，不是整机百分比。

当时 MemAvailable 为 457084 KiB（约 446 MiB），最近 10 秒 memory PSI 的 some/full 均为 0。前后页面加载、缓存和交换状态不同，这只是播放中的快照，不能据此宣称精确节省了多少内存或达到长期稳定。十项默认值及格式协商通过独立实例读取，生产实例则通过实际 H.264 线程和播放音频确认；未声称直接读取生产实例全部运行时首选项。用户浏览器已正常恢复，临时诊断进程及调试端口均关闭。摘要见 [实机记录](../validation/browser-low-memory-2026-10-23.json)。

## 尚未解决

本轮避开 AV1 软解并限制缓存，没有为 Firefox 新增 V4L2 Request 后端。H.264 CABAC、浏览器硬解集成以及长期多标签压力仍需独立开发与验收；不能通过强开 VA-API、修改 blocklist 或关闭 RDD 沙箱宣称解决。

参数语义以 [Mozilla 首选项源码](https://github.com/mozilla-firefox/firefox/blob/main/modules/libpref/init/StaticPrefList.yaml)、[内容进程配置](https://github.com/mozilla-firefox/firefox/blob/main/modules/libpref/init/all.js) 和 [官方策略说明](https://firefox-admin-docs.mozilla.org/) 为依据；实际生效结果以本机读取为准。
