# 软件验证报告

日期：2026-09-23
环境：Linux，Python 3.12，版本约束见 constraints-tested.txt。

执行命令：`python -m pytest -q`

结果：**23 passed，1 warning，5.34 秒。**

warning 来自 Starlette TestClient 对 AnyIO 旧别名的使用，是测试依赖的弃用提示，不是硬件成功或失败的证据。

## 已验证

- 从用户拍照请求到图片登记、结构化观察、Agent 工具调用、表达回执、共同记忆的应用闭环（外部硬件与模型使用测试替身）。
- 同请求幂等、不同请求同一场景仍独立保存、冲突请求拒绝。
- 同一张图追问不重新拍照、跨会话图片访问拒绝。
- 上传图片路径与损坏图片拒绝。
- 安静模式、模型调用期间取消，不产生迟到硬件表达。
- 跨会话记忆、更正、删除、持久化重启读取、非法证据拒绝。
- 机器人离线时保留文字并报告失败；动作失败不重复语音。
- 非法工具参数不会导致动作；队列满时明确拒绝。
- 崩溃恢复把在途副作用标记 unknown，不自动重播。
- 本地API访问口令与Origin检查。
- 实际 OpenAI Python SDK 的图片请求构造、严格结构化解析、usage记录（HTTP MockTransport提供响应，未调用真实模型）。
- Reachy适配器的上传、播放、停止HTTP路径和accepted回执（HTTP MockTransport，未连接真机）。
- 超时子进程回收后能继续启动下一次进程。
- 所有Python文件语法解析通过；网页JavaScript经node --check通过。

## 需要在用户主机完成

- Windows PowerShell安装与启动脚本执行。
- pyttsx3 / SAPI5 中文声音生成。
- E06真实BLE连接、拍照与新图片传输。
- 用户实际API账号或中转对GPT-4o-mini图片、结构化输出、工具调用的支持。
- 实际Reachy版本的HTTP/动作WebSocket接口、动作和扬声器输出。
- 连续10轮真机分享、停止、安静、断线与恢复。

测试替身仅存在tests中，正式应用没有自动模拟回退。上述待验收项不能被本报告的23个测试替代。
