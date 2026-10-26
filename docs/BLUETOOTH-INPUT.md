# 蓝牙键鼠与配对代理

2026-10-19 实机的 BCM4354 上电握手修复、S102 音频及 ThinkBook BLE 鼠标连接已通过；内核侧 UHID／uinput 已安装并由蓝牙启动服务加载。配对和物理输入边界以驱动仓库 `bluetooth/validation-2026-10-19.json` 为准。

`0019-noctalia-bluetooth-agent-lifecycle.patch` 修复 Noctalia 的三处配对状态问题：

- 监听 BlueZ 的总线所有者变化，守护进程恢复后重新注册 KeyboardDisplay 代理，避免只在桌面初次启动时注册。
- DisplayPinCode 只负责显示数字，立即回复 D-Bus；用户继续在实体键盘输入数字。
- 同一设备的数字显示状态不阻塞随后的 HID 服务授权，实际的确认／密码输入请求继续等待用户操作。

补丁已纳入 `tools/build-noctalia.sh`。在原生产构建目录增量编译并剥离后，新二进制 SHA256 为 `7301de14a8869a8175c26260a9b125b61aa0ac995ccc1ff81c6b260adbe32c51`，已带备份原子安装并只重载 Noctalia；配置检查、实际运行二进制及未锁定状态核对通过。没有重启 Niri，也没有改动壁纸、中文键盘、Dock 或锁屏配置。K480 端到端配对／打字、代理自动重注册的实际守护进程重启测试尚未完成。

配对码应在实体蓝牙键盘上输入并按 Enter；过期后生成新码，不保存或复用。不要通过通用自动接受代理信任任意附近设备。对测试设备临时开启 Pairable 后应恢复原状态，保留已成功绑定的 S102 和鼠标。

## 配对完成流程修复

用户反馈 K480 输入验证码后还需手动点连接、数字仍残留。`0020-noctalia-bluetooth-pair-completion.patch` 让由用户发起的 Pair 成功后，先异步设置信任，再连接 HID／音频 profile；失败不发起连接，已连接设备不重复连接。设备确认 Paired 后清理同一设备的信息性数字显示，保留真正需要用户回答的授权／密码请求；仅 ACL Connected 不能作为认证完成的依据。

最终二进制 SHA256 `6d0d3af9fc27fef489932b154a88c60311cdfda3d8a847c32b7970164e3cf781` 已带备份原子安装并通过实际运行哈希和未锁定状态检查。K480 当前 Paired／Bonded／Trusted／Connected／ServicesResolved 全为 true，存在内核键盘输入节点；鼠标和 S102 绑定连接保留。用户已完成本次配对码输入及此前所需的手动连接，不再删除绑定重复测试。新流程通过真实生产方法的可控 D-Bus 回调回归，包含 trust/Connect 顺序、失败、设备消失、已连接去重、同设备数字清理及保留其他设备／实际确认请求；公开补丁反向检查与最终构建源码相符。

复现回归：`python3 tools/test-bluetooth-pair-completion.py /path/to/patched-noctalia`。构建脚本也会运行它。普通打字、鼠标点击／滚轮与全新配对的完整用户验收仍未重复。
