# 启动与硬件输出维护补丁独立验收

2026-09-24；独立QA worktree。仅使用固定源码、隔离checkout、mock网络与临时文件；没有启动生产桌面、daemon、媒体或实机，没有发送生产API请求。

## 官方桌面自动唤醒补丁

交付固定 `2e263d3dc7597facd3874c6f840ea46a8ff2d4d4`，官方0.9.32上游固定 `f520136ffe9b54ba6e34a6d5b4da4781cfd55ab8`。在QA忽略目录创建独立离线clone，运行guarded apply的默认dry-run和显式apply，核对源码hash后执行实际patched TSX：**21 tests passed，0 skipped**。另独立检查**3项通过**：重复apply不写、本地源码修改拒绝、错误HEAD拒绝；测试后恢复QA checkout的固定HEAD与已审补丁。

源码追踪覆盖：Rust USB `--no-wake-up-on-start`；WiFi/external `daemon/start?wake_up=false`；StartupView的daemon-ready/scan门及postReadyStartedRef；usePostReadySequence同步状态/目录后调用onScanComplete；webview恢复设置STARTING，再由useViewRouter进入同一个StartingView。最终完成回调仅改变UI状态，不调用显式click handler。

离线TSX测试覆盖disabled/enabled/unknown/其他mode、重复完成、显式按钮、并发双击和两处HTTP失败。仅显式click在disabled状态下enable再wake；enabled点击只打开controls；unknown及HTTP失败不推进。全src的wake/enable搜索还包含原有useWakeSleep和SettingsDaemonCard用户入口，本补丁不是全局运动禁用器。

**结论：该固定补丁在自动完成回调无运动写入这一源码/mock范围通过，未发现本范围阻断。** 所谓首次连接/重连/恢复测试是共享完成回调矩阵，完整路径另以源码追踪核对，不是Tauri E2E。完整依赖typecheck/build、桌面/窄屏视觉QA、真实连接/重连/恢复的零写入验证仍未通过；生产未部署，不能声称重开原生app已经安全。

手动wake保留上游既有动画等待逻辑，包括move_failed/move_cancelled及超时后可能进入ready；ready不证明物理完成。本次不批准按钮实机使用，不覆盖其他客户端或旧bridge。此前仅用native no-wake flag推论完整桌面重开不动作的结论不成立。

## Cached遥测初审

固定 `af7036382887e1a5523be0fe07ffb7af91c83003` 原5项focused测试独立通过，但4项独立property测试失败：为`_torque_enabled`、`_current_head_operation_mode`、`_current_antennas_operation_mode`、`last_alive`分别提供会记录调用并抛异常的property，snapshot的getattr实际执行getter。原controller哨兵测试只证明不访问controller，不能证明无descriptor调用。

该复现不声称当前native字段实际为property，也未导入/探测生产SDK。按本次“禁止隐式property/controller访问”的明确要求，交动作owner改成安全缓存读取，缺失/descriptor应拒绝或unknown，不执行getter。**该固定版本暂不通过该项门禁，等待修复SHA复验**；schema1、cached不等于设备物理回读、missing=null等边界保持。
