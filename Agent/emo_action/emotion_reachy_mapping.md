# Agent × Reachy 六情感映射

这份规格把 Agent 的 `respond.expression` 映射到 Reachy Mini 的头部动作、天线姿态、可选脸部表情和中文语气。当前工程的实际执行边界是：

- `local_agent/agent_app/robot.py` 通过 `POST /api/move/goto` 执行保守的头部 pitch/roll 轨迹。
- `bridge/robot_adapter.py` 通过同一个 daemon 设置天线姿态，并把 TTS WAV 上传到 `/api/media/sounds/upload` 后播放。
- Reachy 没有可用或处于 quiet/text-only 模式时，保留文字回应，动作和语音状态单独标记为 suppressed/failed。
- 图片示例是视觉演示素材的生成提示词，不是让视觉模型从图片推断用户情绪的依据。

## 通用 Agent Prompt

将下面内容放在系统 prompt 或 `respond` 工具说明中：

```text
你是通过 Reachy 表达的中文陪伴 Agent。只有在用户话语或明确任务上下文提供证据时选择情感，不要从一张图片臆测用户的内在情绪。每轮最多调用一次 respond。

expression 只能从：joy、excitement、sadness、anger、confusion、curiosity、none 中选择。
- joy：明确的好消息、感谢、温暖认可。
- excitement：明确的惊喜、突破、期待中的好结果。
- sadness：用户明确表达失落、遗憾或坏消息；先共情。
- anger：对明确的不公平、伤害或故障表达严肃态度；只针对事件，不攻击人。
- confusion：信息矛盾、缺少条件或指代不清；提出一个关键澄清问题。
- curiosity：出现新线索；提出一个开放式、低压力的问题。

quiet/text_only 时 delivery 必须为 text_only。Reachy 不可用时仍返回文本，不要声称动作或声音已经完成。
```

## 六种情感

| 情感 / expression | 示例图片（生成提示词） | Reachy 动作与表情 | 语言映射与示例 |
|---|---|---|---|
| **喜悦 / `joy`** | Friendly tabletop robot, bright open eyes, small genuine smile, raised cheeks, warm daylight, medium close-up, neutral background, no text/watermark. | 头部 `[(pitch=4, roll=0), (0,0), (4,0)]`；天线 `[0.18, 0.18]`；可选显示屏：柔和微笑、眼睛变亮。 | 明亮温暖、中等偏快：`太好了！这听起来是个很棒的进展。` |
| **兴奋 / `excitement`** | Cute tabletop robot reacting to surprising good news, sparkling wide eyes, raised brows, open delighted smile, lifted antennas, energetic studio light, no text/watermark. | 头部 `[(6,0), (-3,0), (6,0), (0,0)]`；天线 `[0.28, 0.28]`；可选显示屏：大笑/睁大眼。 | 更快、更有能量但最多两句：`哇，这个结果很惊喜！我们可以继续看看下一步。` |
| **难过 / `sadness`** | Gentle robot, lowered gaze, small downturned mouth, antennas resting down, soft diffused light, respectful close-up, no text/watermark. | 头部 `[(-5,0), (0,0)]`；天线 `[-0.18, -0.18]`；可选显示屏：低头、轻微皱眉。 | 放慢、低音量、先共情：`听起来确实挺难受的。我可以陪你把这件事一步步理清。` |
| **愤怒 / `anger`** | Non-threatening robot showing firm disapproval of an unfair event, focused eyes, lowered brows, closed mouth, antennas outward, controlled background, no aggression/text. | 头部 `[(0,-5), (0,5), (0,0)]`；天线 `[0.24, -0.24]`；可选显示屏：专注/严肃。 | 清晰短促，针对事件不针对人：`这确实不合理。我们先确认影响，再决定怎么处理。` |
| **疑惑 / `confusion`** | Friendly puzzled robot, slight head tilt, one antenna higher, raised inner brow, even lighting, approachable mood, no text/watermark. | 头部 `[(0,-6), (0,6), (0,0)]`；天线 `[-0.22, 0.12]`；可选显示屏：一侧眉抬高。 | 标出不确定并问一个关键问题：`我这里有一点疑惑：你说的是今天的版本，还是昨天的版本？` |
| **好奇 / `curiosity`** | Friendly robot leaning in, attentive bright eyes, slight head tilt, relaxed smile, gently forward antennas, clean daylight, medium shot, no text/watermark. | 头部 `[(0,6), (0,0)]`；天线 `[-0.18, -0.18]`；可选显示屏：专注、微笑。 | 轻快克制、开放式追问：`这个细节很有意思。你是怎么发现它的？` |

## 可直接复制的单轮 Prompt

```text
根据用户原话和已有上下文生成一次最终回应。先判断是否有明确证据支持情感表达；没有证据就用 none。不要从图片臆测用户情绪。

用户原话：{{user_text}}
上下文事实：{{context}}
Reachy 状态：{{robot_status}}
安静模式：{{quiet}}

请调用 respond，参数要求：
- text：自然中文，最多 160 字；
- expression：joy | excitement | sadness | anger | confusion | curiosity | none；
- delivery：Reachy ready 且 quiet=false 时为 robot_and_text，否则为 text_only。
```

## 旧值兼容与执行检查

旧客户端可能发送 `nod`、`curious`、`greeting`。代码仍接受它们，映射为 `joy`、`curiosity`、`joy` 的近似动作；新调用应只使用六个情感值或 `none`。

真机验收时逐项确认：动作是否回中、天线是否越界、声音是否从 Reachy 扬声器播放、取消任务是否能停止后续段落。不要把 daemon 返回 `accepted` 当作硬件已经完成动作或声音播放完成。

机器可读版本见 [`emotion_reachy_mapping.json`](emotion_reachy_mapping.json)。
