# 旧桥硬件输出默认关闭

本次只做离线代码交付，没有替换当前 8088 进程，没有停止音频或向机器人发送请求。

旧路径 `POST /v1/messages → respond → acknowledge → goto` 不经过新动作
执行器；仅关闭 TTS 不能关闭它。新增 `LEGACY_ROBOT_OUTPUT_ENABLED=false`
作为进程启动配置，默认禁用旧 adapter 的动作和音频输出。`respond`、
`acknowledge`、`speak`、底层 `_move` 和 `stop` 都有门禁。禁用时取消请求
不会调用全局 `sounddevice.stop()`，以免影响独立语音服务。

消息仍调用模型并保存回答，结果明确记录 motion/audio `disabled`，正常完成；
拍照仍由原眼镜采集链路处理。没有更改 7860 机械声音、8091 动作批准或扭矩。
`Settings` 将配置明确传给 adapter；直接实例化 adapter 也默认关闭。

`GET /v1/health` 的 `legacy_robot_output_enabled` 是当前进程实际值，不访问
硬件；`/v1/status` 的 robot 下同时报告 `hardware_output_enabled`。
启动器发现旧进程缺失字段就拒绝复用，不自行重启；禁用时不启动旧 daemon。

## 后续唯一维护窗口

1. 合并独立 QA 通过的固定版本。先确认现有 8088 请求无活动工作，保存代码版本
   与本地配置；不上传 token、数据库或照片。
2. 由维护 owner 采用已获准的正常服务生命周期替换旧 8088 进程，只替换桥，
   不用此步骤重启原生 daemon。若启动/停止被系统拒绝，记录拒绝并停止该操作，
   不换 shell、工具或 owner 绕过。
3. 保持默认 false，读取 health 验证明确布尔 false、确认端口只有一个监听实例。
   缺字段不能算部署成功。验证消息保存/取消及照片流程；真实眼镜照片需设备窗口。
4. 该门禁只覆盖新进程的旧 adapter，不证明其他 SDK/UI 客户端无动作权限。
   原桌面 auto-wake 需另行部署经审查的桌面补丁。

回滚只恢复代码仍可能恢复旧的无门禁硬件路径；优先修复前进，若必须回滚，
先由维护 owner 暂停旧桥硬件入口。未经新独占窗口不要设置 true。

验收命令（全为 fake/mock，不访问设备）：

```powershell
python -m pytest tests/test_legacy_output_gate.py tests/test_robot_adapter.py tests/test_backend_reliability.py -q
```

测试覆盖默认/非法配置关闭、显式 opt-in、TTS 两种值均不绕过、底层调用禁用、
取消不停止其他声音、health 实际值，以及真实 worker + 禁用 adapter 的模型回答/
照片流程。保留原显式开启模式的 UUID 回执测试。它不等于现有 PID 已更新。
