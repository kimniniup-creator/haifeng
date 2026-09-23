# 笑脸到声音：最小独立验收与fixture接口

状态：2026-09-24准备完成，尚无阶段通过结论。优先声音闭环，不依赖电机验收；QA不占摄像头/音频设备。固定代码交付后运行对应增量，不能以本计划或假fixture冒充实现通过。

## 已确认契约与来源

Agent/链路owner已明确确认，准备时只读核对其 `tests/test_visual_response.py:cue()` 与 `pet_interaction/visual_policy.py` 工作稿；仍须由后续固定SHA锁定版本，不能把未提交工作稿当最终代码。

- schema_version=1、source=vision、kind=visual_cue，原始Unix observed_at、TTL=1.5秒、confidence=.7仅表示configured_detection_floor。
- 第一阶段cue_name=smile；单脸face_count=1、attribution=single_face、临时track_id，quality.usable=true且reasons=[]；stable_ms至少800；face-cues-v1规则两侧mouthSmile至少.55；interpretation=visible_facial_cue、provisional=false。
- face_presence/visual_unknown只观察、不出声、不等同无人情绪；后端全局12秒冷却，换track或camera session不能绕过。
- Agent绑定语音当前session/epoch，专用认证WS proactive-events给connection_id/session_id/epoch与500ms心跳，租约1.5秒。声音POST proactive-sound使用event_id、connection_id、session_id、expected_epoch、event_timestamp、ttl_ms（不超过2000）、semantic_id=happy；保持原事件期限，不伪造语音final，不推进语音epoch。
- output_status用event_id/response_id/session_id/epoch关联；completed只指last_buffer_submitted，不能写成用户已听到。语音owner的固定实现与精确fixture入口尚待交付核对，不臆造取消状态名或内部方法。

准备期间语音owner已交固定 `0bd88b6193a2b3180c777593c65e7c6026d57335`，精确入口在`patches/reachy_companion/PROACTIVE_AUDIO.md`、`proactive_audio.py`和`test_proactive_audio.py`，下一步立即独立审/测。其播放层另设8秒冷却，Agent策略层12秒冷却仍按前述契约，两者不混为同一个阈值；回调检查周期20ms。owner自测47项尚不作为QA通过证据。

## 最小用例

| 用例 | 输入与操作 | 离线通过条件 | 现场剩余项 |
|---|---|---|---|
| S1 稳定笑脸一次声音 | owner真实Observation/Engine持续满足阈值；事件重复提交 | 只产一次有效cue、一次happy请求；真实voice gate输出非零PCM且正确关联终态；NoMotion.calls为空 | 真人面对相机持续笑脸，实际听到一次声音 |
| S2 unknown静默 | 无脸、多脸、模糊/遮挡等低质量、未满800ms、未知cue | producer不发可播放smile，controller不提交声音；真实PCM保持零；unknown不误报absence | 真人离开/多人/低质量画面不乱响 |
| S3 冷却与重新触发 | 持续笑脸、重复event、换track/camera session；12秒内/到期后 | 12秒内不重复；到期后仍需producer真实重新满足稳定规则，不能重放旧event | 持续笑脸无连响，新的合格笑脸按规则响应 |
| S4 用户讲话抢占 | 开始视觉PCM后模拟owner真实speech-start；在用户讲话时再送cue | 原输出在下一音频callback失效；旧视觉事件不排队补播；语音身份不被视觉请求改写 | 用户说话时声音及时让路 |
| S5 TTL | 原始事件延迟到1.5秒边界前/后；在排队与渲染之间越期 | 等于/超过expiry拒绝或丢弃；渲染不出过期PCM；不刷新源时间，不自动重试 | 网络/调度延迟时不突然补响 |
| S6 断连及晚到回执 | 断开或过期proactive租约，再接入新connection/session/epoch，提交旧ID/回执 | 旧输出失效；新连接不重播；旧回执不能改新决策；绑定不靠仅event_id | 实际连接恢复无旧声音回放 |

哭仅作为possible cue，playful表示夸张互动；本轮未启用就应静默，不把它们写成已判定心理/医学状态。阈值是规则配置，不是准确率承诺。

## 可复用fixture

`qa/visual_sound/fixtures.py`不导入网络、相机、音频、SDK或生产应用：

- Clock：可控Unix测试时间，advance不允许回拨。语音monotonic由owner测试入口同步控制，不全局乱改时钟。
- smile_cue：严格使用上面已确认包结构；每次独立深拷贝，payload变化用于边界。不是人脸模型结果或现场证据。
- RecordingProactive：记录deepcopy请求，只供策略层断言，queued仅是假回执。
- NoMotion：submit记录并抛错；必须再检查calls为空，因为controller可能捕获异常。允许cancel等生命周期记账，不调用设备。
- assert_one_happy_request/assert_no_outputs：只验证请求层，不能替代PCM/现场结果。

接入方式：在固定交付快照测试中将Clock、RecordingProactive、NoMotion注入真实PetController；producer测试直接使用owner导出的Observation/Engine，不自行复制识别算法。声音层用owner真实Companion/TurnGate与ASGI/认证WS或MockTransport，拦截一切外部I/O，仅render到内存buffer；无需启动麦克风/扬声器线程。方法名、token初始化与输出回调入口等固定代码到达再绑定。

## 证据分层及交付

1. 规则/策略层：合成Observation与已确认事件证明条件和抑制，不证明相机识别。
2. 组合层：真实producer/Agent/voice代码、假输入与内存PCM证明一次性、抢占、时效和回执，不证明真实听感。
3. 真人现场层：设备owner提供时间窗口、输入场景、实际camera cue及一次可听回应/打断的对应证据；accepted、queued、completed-last-buffer均不能单独替代。

最终结果按固定SHA报告“离线通过/缺陷待修/待现场”，只重测新增或受影响边界，不重复无变化全套。生产配置、设备启动和实机测试由各唯一owner协调，本fixture不授予权限。
