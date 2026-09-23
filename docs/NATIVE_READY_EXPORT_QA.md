# Native ready 导出候选独立 QA

2026-09-24，固定 `5370a42f84ed9cacc64248b6830023ea9336387a`。**两行候选能修正已存在字段的导出，无离线阻断项；仅供维护 owner 评审，不是部署或动作放行。** 未修改 native 文件、导入 SDK、访问设备/生产 API、重启或部署。

## 独立证据

- 从权威 native 安装的 `daemon/backend` 只读源码：abstract.py SHA256 `be41653e96dbc8db81d94275a751d867e525de0845018aaecc9cc39a65d65b87`；robot/backend.py `7d799da6de711fae6622ceb296eaf68cd54519c034605067c5ee89f8f273ac87`，与 owner 固定证据一致。
- 固定候选脚本 AST-only 检查独立复跑：**7 checks passed**。原 get_status 只更新 error / motor_control_mode，故 Event 已 set、last_alive 已更新时仍导出初始 false/null。内存加入 `self._status.ready = self.ready.is_set()` 与 `self._status.last_alive = self.last_alive` 后，set/clear 和 None 均按真实字段导出。
- `qa/test_native_ready_export.py` **4 passed，0 skipped，0.28秒**：set仍保留错误/旧时间；set+None不合成时间，clear不抹掉已有时间；真实工作线程完成 set/clear 更新后读取可见；返回对象保持现有共享可变对象语义。测试仅在显式设置 `QA_NATIVE_BACKEND` 为已审源码目录时运行，未设置则跳过。

## 状态与线程语义边界

`ready` 是 abstract 初始化的 `threading.Event`，不是电机属性 getter；本机 CPython3.12 的 is_set 直接读取布尔 flag，set/clear 使用自身条件锁。`last_alive` 初始 None，控制循环在反馈读取/更新段末尾赋值 `time.time()`，所以是墙钟时间，不可与 monotonic 混用。候选读取的是这些已有字段，不发硬件命令，也不应移入严格禁止任意方法调用的 cached telemetry helper。

两项读取以及 error / mode 更新没有共同锁；候选没有提供跨字段一致的原子快照。返回 `_status` 仍是共享可变对象，后续 get_status 会改变此前取得的对象。工作线程 join 后的可见性测试不能证明任意并发时刻都一致，也不能泛化为所有 Python 实现的同步保证。消费者须保留当前诊断一致性、running、error、时间新鲜度及动作互斥检查。

ready 的准确含义更窄：控制循环**曾到达反馈更新段尾部并置位**。捕获的 IK ValueError 仅记录警告，流程仍可到达 last_alive / ready 更新；is_shutting_down 时跳过部分发布也不阻止这两项更新。后续 RuntimeError 没有对应 clear，故 ready=true 不代表 IK 成功、当前电机健康、扭矩开启或目标已跟踪。不存在把未知 timestamp 替换为当前时间、把 ready 固定为 true 的理由。

约10度跟踪误差及历史物理验收失败保持独立阻断；修复 ready 不改变相关结论。摄像头到声音链路不等待此候选。维护 owner 后续若应用，仍须按获授权生命周期检查真实 unset、error、stale 状态；本报告没有执行这些现场步骤。

## 复现

用隔离 Python 设置 `QA_NATIVE_BACKEND` 指向已核对 hash 的 native `daemon/backend` 目录；运行固定提交的 `pet_motion/check_native_semantics.py $env:QA_NATIVE_BACKEND`，再运行本分支 `python -m pytest qa/test_native_ready_export.py -q`。只提取方法 AST并在假对象上调用，不实例化 SDK/backend/controller。
