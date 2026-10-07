# 协作方式

通用规则（证据要求、断言口径、不要提交的东西、许可与来源）见总入口的 [CONTRIBUTING.md](https://github.com/Pisces-Moze/mocha-moze-debian/blob/main/CONTRIBUTING.md)。这里只写本仓库特有的验收口径。

## 本仓库的验收口径

- 桌面改动要在平板的物理 tty1 上验证。SSH 会话不能替代 active seat 验证，也不能证明自动登录与用户会话真的起来了。
- 附两次 `ldd`（`niri` 与 `noctalia`）的结果，不能有 `not found`；缺库时补装的是 armhf 运行包，不是主机上的 `-dev` 包。
- 补丁只应用 `0003`，它已经包含 `0002` 的修改，串行重复应用会打重同一处 hunk。改过 `vendor/` 之后要重算 `.cargo-checksum.json` 并 `cargo clean -p smithay`，PR 里说明这两步是否做过。
- 性能数字要写清条件：分辨率、scale、走的是 simpledrm 还是 native 路径、测了多久、用什么程序测。桌面动画帧率与 DMA-BUF 色块帧率不是一回事。
- 充电模式的改动要说明是限时试运行还是已经启用 `/boot/mocha-charger.enabled`，并附按键退出（约 2 秒回桌面）、拔线关机与限流结果。
- Noctalia 要连数据目录一起安装，只复制二进制会让壁纸缩略图不显示；这类看起来像显示问题的现象，先确认安装是否完整。

## 提交前自查

- 没有把 armhf 二进制、`build/`、`dist/`、`vendor/` 带进提交。
- 上游固定版本没有被改动：Niri v26.04、Smithay `ff5fa7df392cecfba049ffed55cdaa4e98a8e7ef`、Noctalia v5.2.1。要换版本就单独开一次改动并说明原因。
- 写清这次是主机侧交叉编译通过，还是在板上装过、起过会话。
