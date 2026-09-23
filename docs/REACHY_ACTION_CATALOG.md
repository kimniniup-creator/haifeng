# Reachy 动作映射清单

> 最新范围：初始清单为 85 个情绪与 19 个官方舞蹈资产。界面 DANCES(34) 已核实由 20 个官方舞蹈入口加 14 个音乐舞蹈入口组成，均走 REST recorded 路径；当前其中 33 项可枚举，headbanger_combo 缺失。完整界面对照见本文末节，不要将初始 19 项当作全部舞蹈入口。

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


## 界面 DANCES(34) 逐项对照（已核对）

P = pollen-robotics/reachy-mini-dances-library；M = Anne-Charlotte/music。按界面从左到右、逐行排列。可枚举仅表示当前服务解析了动作名字，不代表完整轨迹有效、持续驻留或实机播放通过。

| 序号 | 动作 ID | 数据集 | 当前服务列表 |
|---|---|---|---|
| 1 | stumble_and_recover | P | 已枚举 |
| 2 | chin_lead | P | 已枚举 |
| 3 | head_tilt_roll | P | 已枚举 |
| 4 | jackson_square | P | 已枚举 |
| 5 | pendulum_swing | P | 已枚举 |
| 6 | side_glance_flick | P | 已枚举 |
| 7 | grid_snap | P | 已枚举 |
| 8 | simple_nod | P | 已枚举 |
| 9 | side_to_side_sway | P | 已枚举 |
| 10 | polyrhythm_combo | P | 已枚举 |
| 11 | interwoven_spirals | P | 已枚举 |
| 12 | uh_huh_tilt | P | 已枚举 |
| 13 | chicken_peck | P | 已枚举 |
| 14 | yeah_nod | P | 已枚举 |
| 15 | headbanger_combo | P | 缺失，暂不可映射为可执行 |
| 16 | side_peekaboo | P | 已枚举 |
| 17 | dizzy_spin | P | 已枚举 |
| 18 | neck_recoil | P | 已枚举 |
| 19 | groovy_sway_and_roll | P | 已枚举 |
| 20 | sharp_side_tilt | P | 已枚举 |
| 21 | beyonce-single-ladies | M | 已枚举 |
| 22 | demon-hunters-1 | M | 已枚举 |
| 23 | eagles-hotel-california | M | 已枚举 |
| 24 | eminem-lose-yourself | M | 已枚举 |
| 25 | feel-the-magic-in-the-air | M | 已枚举 |
| 26 | katy-perry-fireworks | M | 已枚举 |
| 27 | las-ketchup | M | 已枚举 |
| 28 | michael-jackson-thriller | M | 已枚举 |
| 29 | paint-it-black | M | 已枚举 |
| 30 | pharrell-williams-happy | M | 已枚举 |
| 31 | queen-we-will-rock-you | M | 已枚举 |
| 32 | spice-girls | M | 已枚举 |
| 33 | the-fratellis-whistle-for-the-choir | M | 已枚举 |
| 34 | the-white-stripes-seven-nation-army | M | 已枚举 |

调用链：ExpressionsSection.handleAction → getDanceDataset → useRobotCommands.playRecordedMove → POST /api/move/play/recorded-move-dataset/{dataset}/{id} → native RecordedMoves.get → start_expression。34入口不是Conversation App的AVAILABLE_MOVES/DanceQueueMove路径。

音乐库还返回两个未在该界面展示的ID：michael-jackson-thriller-official-video-shortene、queen-we-will-rock-you-official。两舞蹈数据集共35条，界面固定34入口，其中33条可枚举，headbanger_combo缺失。

来源：本地官方桌面源码constants/choreographies.ts、ExpressionsSection.tsx、hooks/robot/useRobotCommands.ts；动作owner核对Kim的34入口截图；当前daemon两库GET列表。未发送实体动作。

