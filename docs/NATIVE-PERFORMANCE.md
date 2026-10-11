# 原生显示性能候选与复现（2026-10-11）

完整设备状态、未完成问题和跨仓库锁定见 [远端交接](https://github.com/Pisces-Moze/mocha-moze-debian/blob/codex/mocha-diagnostics-2026-10-09/docs/HANDOFF-2026-10-11.md)。本分支是候选源码，不自动安装或替换默认引导。

## 补丁顺序与用途

| 补丁 | 对象 | 状态 |
|---|---|---|
| 0003 | Smithay 完整横屏 damage | 已有有限实机显示验收 |
| 0004 | Mesa Tegra 可选 fence 回调 | 消除底层 NULL 转发；已有回归/实机证据 |
| 0005 | Mesa reset/scissor | 对缺失 reset 回调返回正常状态，修复旋转损伤的 scissor；已有实机检查 |
| 0006 | Mesa Tegra scanout modifier alias | 精确映射既有线性/块布局表示；格式边界仍需扩展验证 |
| 0007 | Mesa GK20A WC GPU BO | 图片、GPU 私有堆及 CPU-write/GPU-read 上传缓冲使用 coherent BO 接口；保留 CPU readback staging cached |
| 0008 | Mesa GK20A native sync_file | 实验，构建和运行均 opt-in；独立 EGL/KMS 通过，完整合成器待测 |
| 0009 | Smithay Tegra explicit fence 检测 | 新候选，按驱动名而非厂商描述识别闭源 NVIDIA；完整构建/实机验证待完成 |
| 0010 | Noctalia 可选 EGL robustness 开关 | 默认保持原逻辑；环境变量 `NOCTALIA_DISABLE_EGL_ROBUSTNESS=1` 才禁用 |
| 0011 | Niri frame profile | 可选插桩，`MOCHA_FRAME_PROFILE=1` 才打印帧记录 |

0007 的 `NOUVEAU_BO_COHERENT` 在该非一致性 SoC 上选择 write-combined 映射，减少每次提交全页 cache maintenance。不是把所有 CPU 映射都变成 cached，也不改变 firmware/电压表。现有公开 WC 补丁与实测源码的三个文件逐字节核对。

0008 的每个输出 fence 使用独立 BO 导出其 dma_resv sync_file，不在 CPU 上等待输出完成。导入 FD 拷贝/所有权处理已验证，导入 server_sync 仍是 CPU wait；不要描述为彻底移除全部同步。开关仅限 GK20A 0xea 并探测 ioctl 支持。

0009 的原因可直接在固定 Smithay 源码复核：`description` 的 `NVIDIA Tegra graphics` 命中了旧闭源 NVIDIA 分支，`nvidia_drm_version()` 对主线 Tegra 返回 fallback，关闭 IN_FENCE_FD。修改保留真实 NVIDIA 的版本排除。不应通过删除 `needs_sync` 或无条件忽略 fence 代替修复。

## 构建

按 README 准备固定 Niri/Smithay vendored 源码和 Mesa 25.0.7。不同测试组合使用独立源码树，避免已应用实验补丁残留污染对照；环境变量是请求应用补丁，不会自动撤回旧源码补丁。

```sh
# WC 对照：0004..0007，独立输出目录，不安装系统库。
bash tools/build-mesa.sh /path/to/mesa-baseline /path/to/artifacts/mesa-wc

# 输出 native-sync 候选：增加 0008；运行还需要 MOCHA_NATIVE_FENCE=1。
MOCHA_NATIVE_FENCE_BUILD=1 bash tools/build-mesa.sh /path/to/mesa-sync /path/to/artifacts/mesa-native-sync

# 原生 fencing + 帧统计候选；固定 Cargo.lock，刷新 vendor checksum。
MOCHA_TEGRA_EXPLICIT_FENCE=1 MOCHA_FRAME_PROFILE_BUILD=1 \
  bash tools/build-niri.sh /path/to/niri-candidate
bash tools/build-noctalia.sh /path/to/noctalia-5.2.1 /path/to/artifacts/noctalia
bash tools/build-native-probes.sh /path/to/artifacts/probes
```

Cargo 对 vendored dependency 可能错误地复用 release 缓存，脚本清理 Smithay 的 **release** 包后重新构建。构建虚拟机中断后也要核对二进制；包含 `KMS explicit fence capability` 与 `MOCHA_FRAME` 只证明新代码编入，不证明实机成功。记录 SHA256、ELF Build ID 和实际 `/proc/PID/maps`。

## 板上测试

保持已验证的内核/模块、主线 Tegra 显示和独立候选库路径，先读取电源/温度。频率策略见 drivers 的 `gpu/README.md`。测试不能同时运行两个策略，也不要热卸载 Nouveau。

```sh
candidate=/absolute/path/to/mesa-native-sync/opt/mocha-mesa-candidate
export LD_LIBRARY_PATH="$candidate/lib/arm-linux-gnueabihf"
export LIBGL_DRIVERS_PATH="$candidate/lib/arm-linux-gnueabihf/dri"
export GBM_BACKENDS_PATH="$candidate/lib/arm-linux-gnueabihf/gbm"
export MOCHA_NATIVE_FENCE=1
export MESA_LOADER_DRIVER_OVERRIDE=tegra MESA_DRI_DRIVER_OVERRIDE=tegra
timeout 45s /absolute/path/native-fence-test /dev/dri/renderDTEGRA
```

节点是占位符，用 libdrm driver name 确认 Tegra 与 Nouveau；不能写死枚举顺序。此测试用单像素 `glReadPixels` 校验等待后的结果，不用于证明桌面零读回。

`atomic-fence-scanout` 必须在临时原生文字模式、桌面已停止时运行，会 modeset；保留已有控制台并在结束恢复。明确传入 Tegra card 和 Nouveau render 节点：

```sh
export MESA_LOADER_DRIVER_OVERRIDE=nouveau MESA_DRI_DRIVER_OVERRIDE=nouveau
MOCHA_FENCE_CPU_WAIT=1 timeout 20s ./atomic-fence-scanout /dev/dri/cardTEGRA /dev/dri/renderDNOUVEAU
timeout 20s ./atomic-fence-scanout /dev/dri/cardTEGRA /dev/dri/renderDNOUVEAU
```

第二次不要继承 `MOCHA_FENCE_CPU_WAIT`。两组都应有 pending exports，保存内核日志和屏幕观察。程序不进行 CPU 像素 map/readback/copy，但一次 KMS 成功不代表完整 Niri 通过。

完整原型机会话可使用 `performance/profile-installed-prototype.sh`，它依赖已安装候选目录、UID1000/mocha 和 niri.service，运行时替换并恢复用户服务。新 Niri 及新 Mesa 预先分别放 `/tmp/niri-native-fencing` 与 `/tmp/native-sync-stage`，保持后者 `lib/arm-linux-gnueabihf` 和 `dri` 布局；重启后 /tmp 消失，应重新准备。

```sh
MOCHA_PROFILE_NIRI=/tmp/niri-native-fencing MOCHA_PROFILE_BENCH_FRAMES=600 \
  sh performance/profile-installed-prototype.sh native-sync
python3 performance/summarize-frame-profile.py /path/to/profile-native-sync.log
```

需要核对 `driver=tegra supports_fencing=true legacy=false`、合成帧的 `needs_sync=false` 与 wait_ms=0、真实候选 Gallium/EGL/GBM 映射、无同步/queue 错误，并比较 render/queue/total/P95/P99。仅 FPS 或 EGL 扩展名不够。debug/Profile 输出本身也有开销，随后关闭逐帧日志再做帧时间对照。

已验证 WC+852MHz 的 600 帧窗口测试约 60.042FPS，P95 17.014ms，P99 17.469ms，无 >25ms；旧 Smithay 完整 UI profile 全部仍需要 CPU wait。新 Smithay 候选尚未通过实机，此分支保留为草稿。原型机的真实版本哈希以总入口 JSON 为准。

功耗/温度采样使用 `python3 performance/sample-power-thermal.py --seconds 120 > power-thermal.jsonl`，单进程读取 sysfs，避免高频 fork 的观测开销。逐帧 profile 与无 profile 帧时间对照分别保存。
