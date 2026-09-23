# 稳定笑脸 → 现有开心声音（离线候选）

阶段一只响应可见笑脸线索，不推断人的真实情绪。单脸、质量可用、双侧嘴角
系数至少 .55，持续 800 ms 后的 `visual_cue/smile` 才映射已有 `happy`。
完整输入样例见 `tests/test_visual_response.py` 的 `cue()`；视觉 producer
负责至少四帧、持续笑不重复触发和回中性后重新武装。后端额外全局 12 秒冷却，
更换匿名 track 或 producer session 不能绕过冷却。

`face_presence` 和 `visual_unknown` 仅作为短时观察，不触发声音，不改写手部
presence，更不能当作“人不在”。多脸、低质量、低置信、短暂表情、未知规则、
未启用线索都静默。疑似哭/闹尚未接入阶段一策略。

## 真正的输出链

`POST /v1/events`（vision角色认证）→ `PetController` → `visual_response`
→ `HttpProactiveVoice` → 声音 owner 的 `/api/proactive-sound`，播放器仍只有
原来的一个。此路径明确 `motion.status=not_requested`，不调用动作 executor。
普通语音 `/api/agent-result` 不接收伪造的视觉 ASR final。

两进程本地配置同一 `HAIFENG_PROACTIVE_TOKEN`，默认不配置、不连接。
后端显式 `--enable-devices --voice-url http://127.0.0.1:7860 --enable-visual-sounds`
才打开专用认证 WS `/proactive-events`。无需 `--enable-motion`。
PowerShell 对应 `-EnableDevices -VoiceUrl ... -EnableVisualSounds`。
不要把 token 写入命令行、Git 或日志。

WS hello 给 connection/session/epoch，每 500 ms heartbeat，1.5 秒租约。
POST 携原始 `event_timestamp`（Unix秒）、`ttl_ms`（此阶段1500）、当前
session/expected_epoch、connection_id 和源session+event_id的SHA256标识。
发生讲话、新轮次、断连、过期、休息/停止或正在回应时拒绝；失败不重试，断连
不自动重连补播。声音 owner 在 PCM callback 再查活动、采集新鲜度及租约。

声音接受不递增 epoch、不修改 ASR final。专用 WS 的 output_status 绑定
事件ID/session/epoch回写 decision；旧终态不能结束新输出。HTTP accepted
仅表示排队，`completed/last_buffer_submitted` 仅表示缓冲提交，均不证明现场听见。

## 验证与部署边界

Focused tests包含真实本机临时WS握手/heartbeat与ASGI HTTP输出、断连、
拒绝重放、身份/TTL，以及策略质量/冷却/用户优先边界；全部无需设备。
已组合视觉 `fa36bab` 与声音 `0bd88b6`。新增 `tests/test_smile_audio_combined.py`
直接跑 FaceCueEngine → Agent ASGI → 声音实际HTTP/WS服务 → output_callback
非零PCM → completed回执，另测真实讲话打断及连接断开后下一块静默。
声音测试服务明确禁用lifespan并trap模型/音频启动，不连接任何设备。
组合初测105 passed、1 skipped（本隔离环境未下载人脸模型）、6项依赖弃用警告。
声音独立QA发现精确deadline等号仍输出，已交声音owner修复；最终固定组合
须包含该修复再交QA。本记录不把初测当成QA放行。

生产尚未部署：当前视觉启动仍因自动审批拒绝而停止，不能换工具绕过。
软件合并与测试继续；正式维护时先统一部署匹配的三方协议、验证唯一实例和
共享本地凭据，再由正常获准入口启动视觉。现场须观察稳定笑脸实际只响一次、
讲话抢占、无人/多脸静默。完成该验证前不能称“看到笑就会响”。
