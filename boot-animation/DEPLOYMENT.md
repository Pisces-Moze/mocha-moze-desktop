# Mocha 启动动画安装与回退

本次用户已明确要求持久刷入。新完整内核应先从独立 RAM 引导验证显示及桌面交接，然后安装配对的 eMMC U-Boot 和内核；不再请求重复的写入授权。

2026-10-25 安装前新备份已在实机和电脑各保留一份，并核对一致：

- 实机目录：`/srv/mocha-data/codex-debian-desktop/backups/boot-animation-20261025-before-install/`
- 电脑目录：任务工作区的 `artifacts/device-backups/20261025-before-boot-animation/`
- `LNX.bin`：20 MiB，SHA-256 `0d4d4aff2d4aa94fa3891e1358113f39f74c688dbcdb65dc2a1a57a56e6fa9a0`
- `uImage-desktop`：23722180 字节，SHA-256 `c46848142f4a43af51b121d67fba3c40728994065a20cd13040c2ae6cb7bfbd5`
- 原 initramfs、当前 DTB 与备份清单一起保存。新 initramfs 仅提前加载已核对的背光模块，并保留原根分区检查；先从独立候选路径测试，通过后与内核一起安装。DTB 保持原样。

安装器在写入前核对 LNX 分区名称、20 MiB 容量、现有系统与备份哈希、候选 uImage 的头部和数据 CRC、实际运行内核的版本及动画符号、RAM 启动参数和验收记录。验收记录同时绑定内核、initramfs 与两种 U-Boot 镜像的哈希。先原子替换默认内核和 initramfs，再写 LNX，并读回验证实际写入的镜像。任何步骤抛错，都用完整备份恢复配对的旧内核、initramfs 和 LNX 后再次核对。

普通开机完成后再记录持久安装验收；只完成候选构建或复制不能记为刷入完成。正式写入状态见 `validation/boot-log-animation-2026-10-25.json`。2026-10-25 最终 #9 内核已完成 RAM 显示与桌面交接确认，原生动画约 1.74 秒挂接，新增的显示更新警告已消失。正式内核、initramfs 与 LNX 已安装并回读核对一致，普通冷启动已验证：实际运行 #9 内核、Niri 桌面与默认启动文件及整段 LNX 哈希一致，用户确认动画、原生日志及进入桌面正常。头像、底部标识保持静止，定时器仅更新 64×64 加载圈；原生日志覆盖区域按需重绘。

需要回退时，在可连接的 Linux／维护系统中，先检查备份目录中的 `SHA256SUMS`，确认 `/dev/mmcblk0p22` 的分区标签仍为 `LNX`。恢复 `uImage-desktop` 和 `initramfs.cpio.gz` 到各自的 `/boot` 路径，再把完整 `LNX.bin` 写回 `/dev/mmcblk0p22`，执行同步并核对文件及分区哈希。不要将镜像写入整盘或其他分区。
