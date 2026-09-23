# Reachy 动作映射清单

> 范围更正：本表仅覆盖 REST recorded dataset 的 85 个情绪与 19 个舞蹈资产，不是机器人全部动作入口。Kim 的界面显示 DANCES(34)；这 34 项的 ID 和执行路径正在由动作负责人核对。Conversation App 另有 Python AVAILABLE_MOVES → DanceQueueMove 执行路径，尚未确认是否就是该界面的来源。不要将下面 19 项视作那 34 项的完整替代。

2026-09-23 从当前原生 daemon 的只读列表接口取得：85 个情绪资产、19 个舞蹈资产。接口可列出不等于已逐项实机验收；中文语义为映射候选，具体表现需预览确认。本轮未播放动作。

## 第一批对应候选

| 用户想表达的意思 | 情绪库 action_id |
|---|---|
| 我在听 | attentive1 / attentive2 |
| 好奇、想多看看 | curious1 |
| 想一想 | thoughtful1 / thoughtful2 |
| 听懂了、理解你 | understanding1 / understanding2 |
| 同意、肯定 | yes1 |
| 不同意、拒绝 | no1 |
| 没听懂、困惑 | confused1 |
| 不确定 | uncertain1 |
| 欢迎、你回来了 | welcoming1 / welcoming2 |
| 开心 | cheerful1 |
| 惊喜 | surprised1 / surprised2 / amazed1 |
| 安慰 | calming1 |
| 亲近、喜欢 | loving1 |
| 感谢 | grateful1 |
| 放心了 | relief1 / relief2 |
| 安静陪伴 | serenity1 |
| 等待 | waiting |

## 实际调用约定

情绪：POST /api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{action_id}

舞蹈：POST /api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/{action_id}

基础生命周期：POST /api/move/play/wake_up、POST /api/move/play/goto_sleep；POST /api/move/stop 停止。轨迹构造用 POST /api/move/goto，连续目标用 /api/move/set_target；参数以当前 /openapi.json 为准。这不是新增自定义动作已存在的证明。

动作执行只能单一队列；Agent 输出映射 ID，不能与语音或其他 SDK 客户端并发争抢机器人。现有录制动作保护器会拒绝忙碌时的新动作。动作声音不等于语音助手的 TTS，二者需协调。

## 映射填写格式

触发情境 → 想表达的意思 → 动作库/action_id → 强度/时长（待适配器支持） → 配套语句 → 是否允许打断。

例如：收到月亮照片 → 惊喜后安静陪看 → emotions/surprised1，再 serenity1（串行候选，待实机确认） → 轻柔 → “原来你那边的月亮是这样的。” → 可打断。

## 完整情绪库 ID
- `amazed1`
- `anxiety1`
- `attentive1`
- `attentive2`
- `boredom1`
- `boredom2`
- `calming1`
- `cheerful1`
- `come1`
- `confused1`
- `contempt1`
- `curious1`
- `dance1`
- `dance2`
- `dance3`
- `disgusted1`
- `displeased1`
- `displeased2`
- `downcast1`
- `dying1`
- `electric1`
- `enthusiastic1`
- `enthusiastic2`
- `exhausted1`
- `fear1`
- `frustrated1`
- `furious1`
- `go_away1`
- `grateful1`
- `helpful1`
- `helpful2`
- `impatient1`
- `impatient2`
- `incomprehensible2`
- `indifferent1`
- `inquiring1`
- `inquiring2`
- `inquiring3`
- `irritated1`
- `irritated2`
- `laughing1`
- `laughing2`
- `lonely1`
- `lost1`
- `loving1`
- `mini-deep-sleep`
- `no1`
- `no_excited1`
- `no_sad1`
- `oops1`
- `oops2`
- `proud1`
- `proud2`
- `proud3`
- `rage1`
- `relief1`
- `relief2`
- `reprimand1`
- `reprimand2`
- `reprimand3`
- `resigned1`
- `sad1`
- `sad2`
- `scared1`
- `serenity1`
- `shy1`
- `sleep1`
- `success1`
- `success2`
- `surprised1`
- `surprised2`
- `thoughtful1`
- `thoughtful2`
- `tired1`
- `toc-toc-toc`
- `uncertain1`
- `uncomfortable1`
- `understanding1`
- `understanding2`
- `waiting`
- `wake-mini-up`
- `welcoming1`
- `welcoming2`
- `yes1`
- `yes_sad1`

## 完整舞蹈库 ID

- `chicken_peck`
- `chin_lead`
- `dizzy_spin`
- `grid_snap`
- `groovy_sway_and_roll`
- `head_tilt_roll`
- `interwoven_spirals`
- `jackson_square`
- `neck_recoil`
- `pendulum_swing`
- `polyrhythm_combo`
- `sharp_side_tilt`
- `side_glance_flick`
- `side_peekaboo`
- `side_to_side_sway`
- `simple_nod`
- `stumble_and_recover`
- `uh_huh_tilt`
- `yeah_nod`
