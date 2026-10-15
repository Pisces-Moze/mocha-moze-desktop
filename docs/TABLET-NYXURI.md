# 实机触屏与完整 Nyxuri 桌面（2026-10-13）

实机默认运行 `6.12.111-moze.1-native`、Tegra DSI、Nouveau GK20A、native-sync Mesa、Niri 26.04 和 Noctalia 5.2.1。显示为 `scale 1.5 / transform 270`；正常开机、GPU 色块、桌面、触屏和密码解锁已有维护者验收。完整 Nyxuri 模式保留上游毛玻璃、X-Ray 开关、弹簧动画、窗口规则、Material You、Orbit、壁纸工具和插件设置，不按机型自动削减效果。此前低特效配置保留作历史回退。

## 触屏操作

| 入口 | 操作 |
| --- | --- |
| 实体返回键 | 先收起键盘，再关闭外壳弹窗或概览；浏览器返回历史，其他应用收到 Escape |
| 实体主页键 | 收起键盘和弹窗，切到空工作区显示桌面 |
| 实体菜单键 | 打开／关闭 Niri 多任务概览 |
| 任务栏键盘按钮 | 手动打开／收起键盘；不随文本框焦点自动弹出 |
| 任务栏 × | 请求关闭当前窗口，应用仍可显示未保存提示 |
| 三指横滑／竖滑 | 移动视图／切换工作区 |
| 三指点按／四指点按 | 最大化当前列／切换概览 |
| 四指上滑／下滑 | 切换全屏／请求关闭当前窗口 |
| 三指按住后拖动 | 左右搬移列、上下搬移窗口到工作区 |
| 底部／顶部边缘向内滑 | 概览／控制中心 |
| 左右边缘向内滑 | 切换列焦点 |
| 左下／右下角向内滑 | 启动器／键盘开关 |
| 右上角向内滑 | 切换全屏 |

不把返回、桌面、概览加到任务栏，不强制添加窗口标题栏。普通一指、双指操作交给应用；识别出的系统手势会取消客户端触摸序列。手势来自固定的 `GGEZUS/niri-tablet` 20 补丁，来源、许可证和哈希在 `patches/tablet/`。

maXTouch 同时提供触摸与键盘事件。三个实体键为 `KEY_HOME=102 / KEY_MENU=139 / KEY_BACK=158`；菜单键在板上 XKB 中实际是 **XF86MenuKB**，不能绑定成 Compose 键的 `Menu`。配置位于 `tablet/touch-nav.kdl`。不独占 maXTouch，不创建另一个触屏事件注入器。

## 按键背光与设置

PH1 已由设备树配置为 PWM1，且 Tegra PWM 通道 1 无其他消费者。`mocha-touch-key-lights.service` 通过 PWM sysfs 控制背光，默认 10% 亮度、触摸后点亮 8 秒、熄屏关闭。它非独占读取 maXTouch 的触摸起始及三个导航键事件，不记录输入、坐标或候选文本。设置位于 `~/.config/mocha/touch-keys.json`；图形设置可调亮度 0–30%、时长 0–60 秒，0 秒表示亮屏期间常亮。

服务启动前检查 PH1 的实际 pinmux；若 PWM1 已被别的消费者使用，退出而不修改其状态。退出时只释放自己导出的通道。文件系统读取限制在每 250 ms 一次，避免逐帧触摸引发重复 sysfs 查询。

“Nyxuri 效果与触屏设置”提供模糊次数、半径、噪点、饱和度、窗口透明度、X-Ray、弹簧阻尼／刚度、动画时长、缩放、多指触发数量和按键背光设置。写入前在临时目录验证完整 Niri 配置，备份后原子替换；不重置 Noctalia 中的用户设置。两枚开关实机分配为 60×34，外围触摸区至少 64×44，避免被数值输入列拉成大椭圆。

## 中文输入与锁屏

键盘保留原版四行布局、独立中文候选浮窗和即时按下反馈。Fcitx5 Pinyin 在 Wayland text-input-v3 应用中提交中文；候选区可以横向滑动／翻页。Ctrl 快捷键和英文走虚拟键盘回退。运行时文件只保存进程号与显示状态，供实体返回键判断是否先收起键盘。

Noctalia 的锁屏键盘使用同样的按键外观，位于可信的 session-lock 表面。密码由本地输入窗口设置，LF 传输避免 Windows CRLF 成为密码的一部分；不在仓库存储密码。`mocha-buttons.service` 独占 **gpio-keys** 的电源／音量事件，短按释放后锁屏并实际关闭背光，同一次事件不会再唤醒。音量动作与 Noctalia OSD 联动；真实 RT5671 音频仍未验证。

电源唤醒同时检查 DRM DPMS 和实际背光：输入可能让 DPMS 显示 On，但背光仍为零。自动熄屏也按真实状态唤醒，不只依赖上次按键操作。安装器禁用 logind 的默认短按关机，覆盖用户服务接管前的间隙；只记录按键处理结果的日志限额 64 KiB，不记录触摸／密码。11 项按键回归通过；用户再次确认熄屏、唤醒与触控密码解锁正常。此项仅处理运行中 Linux 的按键。

## 上游与安装边界

| 组件 | 固定来源 |
| --- | --- |
| Nyxuri | `ech678/Nyxuri@ebafe03c9bdf1291eeb83d0f8c368d40a63ccdfd`，GPL-3.0 |
| 官方插件目录 | `noctalia-dev/official-plugins@9aec34181e46789b281263942092ac552f661d1a` |
| mpvpaper | 1.9 / `131a52c266d25262c62b85f52a4a978cafae6ee2`，GPL-3.0 |
| Fisher | `791da644d33d392216f6b1a9b5fc1e470db6d7f2` |
| autopair.fish | `4d1752ff5b39819ab58d7337c69220342e9de0e2` |
| fzf.fish | `6a6136998879dcc1f29a405dfdd6b92c5f229c39` |

Nyxuri 默认只启用 `noctalia/mpvpaper`；完整官方插件目录可供设置中选择，并非所有插件都自动激活。Fisher 三个固定插件已离线安装。静态／动态壁纸工具、Fcitx 主题、GTK 主题和工具入口已部署；外部壁纸全集、可选应用、实验 NyxuriShell 和 Arch/AUR 包管理不属于已验证的 Debian 功能。Nyxuri 全效果桌面通过用户观察，但不据此承诺完整桌面固定达到 60 FPS。

构建应用 `0012-noctalia-touch-lock-keyboard.patch` 和 `0013-noctalia-arm-luau-alignment.patch`。0013 修复 ARM glibc 8 字节分配与 Luau 16 字节对齐要求之间的 SIGBUS：ARM 路径用 `posix_memalign`，扩缩容保留内容，失败不释放原块，维持原内存上限和记账。其他架构保持 realloc。`tools/test-noctalia-arm-luau.py` 使用真实 patched allocator 和 Luau 库生成回归程序，实机 1,000 次状态创建／释放通过。

## 2026-10-14 细节与性能修复

亮度配置将 `DSI-1` 与旧名称 `Unknown-1` 显式映射到 `mocha-miui-backlight`，保留 Noctalia 的亮度界面。实机设置 65% 后 sysfs 为 166/255；用户无需编辑驱动寄存器。

浮动键盘读取 GTK 主题语义颜色，用文件变化通知更新深浅色，不增加逐帧轮询。普通键、修饰键、文字和即时按下反馈分别使用主题颜色，关闭阴影、渐变及高光。原四行布局与独立中文候选窗保持原样；深浅色截图与实际 GTK 配色均已核对。

实体导航通过 Niri 与 Noctalia 的本地 socket 查询状态，空桌面的返回／主页跳过无效输入和重复工作区切换；工作区按稳定 ID 且同一输出选择。菜单键仍切换概览。20 次返回和 20 次主页的对照检查未见退出后 CPU 持续增加；这不替代长期压力测试。`tools/test-touch-navigation.py` 覆盖空操作、键盘优先收起、同输出工作区选择和浏览器返回。

`0014-noctalia-native-dock-icons.patch` 提供 `MOCHA_DOCK_LINEAR_ICONS=1` 的原生 GK20A 兼容路径，仅让 Dock 图标使用峰值分辨率解码与线性采样，保留缩放、悬浮、毛玻璃及其他图片的 mipmap 路径。图标 mipmap 采样失真已在实机对照中重现；CPU 生成 mipmap 和改为 POT 解码均未消除失真，不作为成功修复发布。兼容版本已在实机安装，全局 mipmap 保持开启，新概览截图的底部 Kitty 图标完整，没有碎条；长期多应用仍需观察。

设置新增 CPU 上限、GPU 均衡／流畅档位与 swappiness。缺少 CPUFreq 的已验收 native 内核会禁用 CPU／内存参数；GPU 仍受供电和温度保护约束。CPUFreq、DFLL、LZ4 zram 与 MGLRU 属于另行构建的 `native-runtime` 候选，当前不能宣称已完成实机调频、降压或长期内存优化。

`mocha-native-app` 让 Noctalia、Kitty、mpvpaper 使用相匹配的 EGL/DRI/GBM 库。完整外壳由 `mocha-nyxuri-shell.service` 管理，失败自动重启；默认仍启用 EGL robustness。旧应用版本、配置和 SHA256 清单有备份，配置热更新不要求重启平板。

按顺序安装：编译并验证 ARM bundle → `tools/install-tablet-input.sh` → `tools/install-tablet-desktop.py` → 准备固定 Nyxuri／插件源码 → 以桌面用户运行 `tools/install-nyxuri.py --source … --adapter …` → 离线 Fisher 安装。现有完整 Nyxuri 用户可以单独运行 `tools/install-touch-navigation.py`，它保留效果参数及其他任务栏项目。不要把历史低特效安装脚本再次覆盖到正在使用的完整 Nyxuri 用户配置上。

关机充电的冷启动验收、原厂前级引导的短按启动门控、实际音频与硬件视频解码仍未完成。Linux 桌面按键处理不能证明已改变关机时 PMIC／原厂引导器的启动行为。
