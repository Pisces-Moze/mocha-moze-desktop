# Moze 竖屏启动动画：原头像、纯黑、加载圈、默认日志

`moze-avatar-cutout.png` 是使用内置 imagegen 去除原头像深色背景的透明 PNG，采用原头像的构图与配色。图标不是 SVG、Canvas 或代码拼接图形；代码只编码、播放和合成该图片。生成说明见 [PROMPT.md](PROMPT.md)。画布为 1536×2048 竖屏、纯黑 `#000000`。

按 2026-10-25 最新选择，底部恢复 Android 启动标识式两行层级：上方小号 `powered by`，下方大号 `debian` 配官方旋涡图标，区域为 `(468,1760,600,144)`；最底部另放小号 `Moze`，区域为 `(648,1940,240,60)`。采用官方 Google Sans 字体；字体与图标的来源、版权和许可证见 [BRANDING-LICENSE.md](BRANDING-LICENSE.md)。这是 Android 启动标识风格的 Debian 排版，不宣称与 Android 定制字标逐像素相同。此前底部单行版本已被本次两行布局替换。

头像为 420×420，中心位于 `(768, 640)`；加载圈中心位于 `(768, 1420)`。白色圆头弧线循环伸缩，参考 [Windows WinUI ProgressRing](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.controls.progressring)。这是同类视觉的独立实现，不包含 Windows 二进制或原版动画资产。预览和原生代码使用同一套 120 帧／2.4 秒几何数据。减少动态模式显示固定弧线。加载圈描边为 3.5 像素、半径 27 像素，覆盖度采用 4×4 子像素采样，弧长为 48–252°；首尾沿顺时针持续前进，包括循环接缝，避免伸缩时反向。

只有 64×64 的加载圈需要持续刷新；头像和底部品牌不重复绘制。原生播放器使用 4 位透明度查表，不在启动时进行三角函数、字体加载或视频解码。资产共 523984 字节。U-Boot 每次回调分段绘制十六行以避免阻塞；早期控制台仅随真实日志更新，到原生 fbcon 后由短周期工作更新。不会为了展示动画延迟启动。桌面和充电动画方向独立，本次不改动它们。

## 默认日志直接叠加

不使用日志面板、淡入、分级染色或用户空间 `/dev/kmsg` 重绘服务。

- **U-Boot**：标准 vidconsole 接收的原始字符、16×32 内置字体及 ANSI 前景色，直接显示在整个可见画布。背景重绘时保留现存字体像素，滚屏不拖动角色图。串口输出不变。
- **Linux earlycon**：原 `mocha_fb_write` 负责日志，保留其 8×16 字体、白色、位置、换行及控制字符处理，只给原本的黑色背景增加底图钩子。没有另建消息缓冲或重新排版日志。
- **Linux fbcon**：继续使用默认的 `sys_imageblit`、`sys_fillrect` 和 `sys_copyarea`，因此字体、调色板、光标及控制台滚动仍由原生 fbcon 决定。单独的文字／覆盖平面使图案不会随日志滚动，也不会擦掉文字。仅在已识别的 Mocha `tegradrmfb` 和候选启动参数下启用。

原生 fbcon 的临时平面约为 9 MiB（16 位 framebuffer）或 15 MiB（32 位）；只在启动期间存在。进入 `KD_GRAPHICS` 时停止刷新并释放，45 秒超时恢复纯文字控制台。它不需要桌面启动脚本或额外的 systemd 动画进程。

## 候选与预览

引导仓库的 `animation` 构建配置使用独立测试内核路径。用户已要求持久安装，因此 `emmc` 源码配置也已加入 `earlycon=mochafb,moze mocha_boot_animation=1`，保留原电源键和充电选择逻辑。已安装的引导仍需在 RAM 启动验收后才替换；源码配置与已部署状态分开记录。

`preview.html` 明确标注为浏览器预览；`preview-boot.log` 是当前实机启动日志的原样节选，预览仅回放它，不是实机新引导的验收证据。浏览器文本只能近似内置字体，最终以原生控制台为准。

编码资产：

```sh
python3 boot-animation/render-branding.py
python3 boot-animation/build-assets.py --image boot-animation/moze-avatar-cutout.png
```

此步骤只缩放并编码透明底原头像，不绘制角色；另生成标准 UI 加载圈的透明度查表及预览几何。生成的 `moze-boot-art.h` 和 `moze-boot-assets.h` 要同步到引导仓库和内核串口目录；内核 fbcon 复用同一份资产。

上一版定制日志服务已在实机停用、移入备份，并恢复原 Niri 入口；默认内核和引导保持原样。新版必须通过独立 RAM 启动检查默认日志、图案、旋转及桌面交接后再选择为正式默认。

2026-10-25 已修正 ARM32 earlycon 毫秒转换：使用内核 `div_u64()`，避免依赖不存在的 `__aeabi_uldivmod`。完整 Image 与测试／正式 U-Boot 均已构建，并通过哈希核对；共享取色器的完整竖屏原生快照通过 ASan／UBSan。实机临时启动与持久写入结果在独立验证记录中更新。
