# Niri NVIDIA 显存说明与 Mocha 实测

用户提供的翻译页 `https://docs.akass.cn/niri/Nvidia.html` 抓取超时，改为核对 [Niri 上游原文](https://github.com/niri-wm/niri/blob/main/docs/wiki/Nvidia.md)。其中 `GLVidHeapReuseRatio=0` 是 NVIDIA 驱动的应用 profile，用于限制空闲显存堆的重用；另一项旧 PipeWire 等待参数在 Niri 25.08 后已移除。

2026-10-19 实机读数：Niri 26.04；GPU 为 nouveau，Niri 映射 Mesa `libgallium-25.0.7.so`，没有 NVIDIA 专有内核模块或对应 EGL/GLX 用户态库。该应用 profile 不属于当前 Mesa 驱动路径，不安装无效的专有驱动配置，也不加入已移除的 debug 参数。

实机当前加载的 Gallium SHA256 为 `cc81fe6399af38442a48aa52801400086dcb43008aae292353ebac4d65c57fbe`，与已安装的 Tegra 缓冲引用释放修复一致。六次控制中心开关之前及结束后，系统 DMA-BUF 总量均为 14 个／91,148,288 字节，约 86.9 MiB；关闭面板基线瞬间为 15 个／91,152,384 字节。Niri RSS 为 57,808 KiB。

这些是系统共享 DMA-BUF 和进程 RSS 的不同指标，不能当作单个 Niri 进程的专有显存占用。短测没有观察到逐轮积累；它不排除长时间运行、应用切换或解码器中的其他内存问题。本次没有运行长时间压力测试或改动图形驱动。
