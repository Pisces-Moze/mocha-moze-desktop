# Tegra fence 回调修复候选（2026-10-09）

## 根因与改动

历史 native Niri 的 PC=0、LR 位于 `tegra_fence_server_sync`，指向一次空函数指针调用。Mesa `mesa-25.0.7`（commit `742a20f48c59e8649533c84c4d49dd95b403f5da`）源码进一步给出了可复核的原因：Nouveau 的 `nouveau_context_init` / `nvc0_create` 没有设置 `fence_server_sync` 和 `create_fence_fd`，`nouveau_screen_init` 没有设置 `fence_get_fd`；Tegra 包装层却无条件设置对应的转发函数。DRI 的 `dri_server_wait_sync` 检查的是外层非空指针，随后进入包装函数并调用空的底层指针。

`patches/0004-mesa-tegra-optional-fence-callbacks.patch` 只在底层实现回调时注册外层回调，保留 Nouveau 的可选回调约定。它不新增 native sync-file 支持，不修改一直可用的 `fence_reference` / `fence_finish`。下面的实机重现与寄存器确认了同一二进制的空回调调用；修复候选的完整构建与 native Niri 实机验收仍待完成。

源码来源：[Mesa 上游](https://gitlab.freedesktop.org/mesa/mesa/-/tree/mesa-25.0.7)，可使用其 [GitHub 镜像的固定 commit](https://github.com/chaotic-cx/mesa-mirror/tree/742a20f48c59e8649533c84c4d49dd95b403f5da) 对照。补丁保留被修改文件的 MIT 许可与 NVIDIA 版权。

## 已完成的检查

- 对上述固定版本的实际 `tegra_context.c` / `tegra_screen.c` 应用补丁，hunk 检查通过。
- 主机 C 回归测试直接抽取 Mesa 包装函数与注册语句：未修改源码在底层缺少回调时失败，修改后八种有/无回调组合通过；同时验证底层 context、screen、fence 和 fd 的转发参数。
- 原型机现有 Mesa `25.0.7-2+deb13u1`、旧内核 `6.12.111-mocha-experimental-fbdiag`、simpledrm 桌面运行时，Nouveau render node 的 EGL 1.5、NVEA 硬件渲染通过 32 轮跨上下文 fence 等待与交替红/绿像素检查。
- 上一项使用原有系统库，没有装入候选补丁，没有覆盖 Tegra 包装层，也不验证面板输出和 zero-copy。完整 Mesa 交叉构建、候选库运行和原生桌面稳定性仍待完成。
- 同一内核、同一测试进程设置 `MESA_LOADER_DRIVER_OVERRIDE=tegra`，renderer 变为 `tegra`，在 `eglWaitSyncKHR` 触发 SIGSEGV。GDB remote 实际捕获 `PC=0`、`R3=0`，LR 去掉 Thumb bit 后相对 libgallium 的偏移为 `0xd645bc`，前一条调用指令字节 `98 47` 为 Thumb `BLX R3`。运行库 Build ID 为 `fd7dcad10de8c89211ebe69ae8c8dda302f047d0`，与历史 Niri 证据一致。这证明相同包装层的空指针调用，可在 simpledrm 系统中重现；不代表启用 native KMS 或看到 native 面板输出。

## 构建与回归

在 Debian 13 amd64 构建主机上准备固定版本的 Mesa 源码。`tools/install-build-deps.sh` 已包含所需交叉依赖；安装它会执行 APT，先确认使用的是构建主机。

```sh
# 原始源码必须失败；应用补丁后必须通过。
python3 tools/test-mesa-fence-callbacks.py /path/to/mesa-25.0.7
patch -d /path/to/mesa-25.0.7 -p1 < patches/0004-mesa-tegra-optional-fence-callbacks.patch
python3 tools/test-mesa-fence-callbacks.py /path/to/mesa-25.0.7

# 接受原始或已应用补丁的源码；输出目录须是全新目录。
bash tools/build-mesa.sh /path/to/mesa-25.0.7 /path/to/artifacts/mesa-fence
```

构建脚本生成 `stage/opt/mocha-mesa-candidate` 与 `SHA256SUMS`，不会安装到主机或平板的系统库目录。只有完成构建后，才把 stage 中的候选目录放到平板数据分区的独立目录；不要放进仅剩约 41 MB 的 APP 分区。

## 板上验收

先用原有系统库跑对照；脚本只读取 DRM 节点并创建自己的 GBM/EGL 上下文，不取得 DRM master、不 modeset、不终止桌面。默认查找 Nouveau render node，不依赖固定编号：

```sh
timeout 45s python3 tools/probe-egl-fence.py --iterations 32

# 原有 Mesa 的包装层重现：预期在 enter eglWaitSyncKHR 后 SIGSEGV。
# 只影响该诊断进程；不切换内核、不 modeset、不修改现有桌面的环境。
MESA_LOADER_DRIVER_OVERRIDE=tegra timeout 45s python3 tools/probe-egl-fence.py --trace --iterations 1
```

临时 native 引导后，根据 `/sys/class/drm/card*/device/driver` 找到 **tegra** KMS 节点，显式传入它以覆盖包装层。不要拿 Nouveau 的成功结果替代这一步：

```sh
candidate=/srv/mocha-data/mesa-fence-candidate
LD_LIBRARY_PATH="$candidate/lib/arm-linux-gnueabihf" \
LIBGL_DRIVERS_PATH="$candidate/lib/arm-linux-gnueabihf/dri" \
__EGL_VENDOR_LIBRARY_FILENAMES="$candidate/share/glvnd/egl_vendor.d/50_mesa.json" \
timeout 45s python3 tools/probe-egl-fence.py --device /dev/dri/cardTEGRA \
  --require-tegra --iterations 32
```

`cardTEGRA` 是占位符。候选目录应保持 stage 内 prefix 下的完整相对布局，确认 vendor JSON 指向的库能从 `LD_LIBRARY_PATH` 找到；若安装生成的 JSON 使用绝对路径，需在私有候选目录中改成对应绝对候选库路径。通过还需确认 `TEGRA_WRAPPER_TESTED=YES`，保存候选库 SHA256、ELF Build ID 和 `ldd`，不能混用系统 libgallium 与候选 DRI 前端。默认 Nouveau 对照会输出 `TEGRA_WRAPPER_TESTED=NO`。

最后在物理 tty1 上用同一候选库启动 Niri，保存 journal、检查双侧画面、旋转 damage、触控与稳定运行。单独的 fence 测试通过不解决 block-linear TEST_ONLY 的 EINVAL，也不证明原生桌面、控制台位置或音频已修复。通过临时验收后再讨论默认引导和系统库安装。
