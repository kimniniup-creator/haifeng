# 语音与 Agent 最小轮次接口约定

状态：接口提案，待语音负责人核对实际运行版本的 hook 并确认字段映射；不是已实施或实机验收声明。日期：2026-09-23。

## 目标与职责

新一轮输入或打断后，旧轮迟到的识别、模型结果、工具调用和声音不能继续成为当前回应。语音负责人唯一维护轮次权威与播放仲裁；Agent 消费其身份并回传，不另建 epoch 生成器。下述字段可映射到现有等价字段，无须增加第二套实现。

Agent 负责语言/照片理解、回应语义、人格与授权记忆、工具选择；动作负责人负责实际动作 ID 与执行；语音负责人负责 ASR、机械音生成、音频排队、播放和中断。Agent 不直接操作设备。

当前暂定显示名为“啾啾”。仅覆盖 display_name，不改变 companion_id、重写人格或清空历史。可听输出为纯机械种族叫声/轻电流声；内部中文理解和文本推理保留，不把内部文本转成人话 TTS。声音素材、强度、时长与现场验收归语音负责人。

## 最小输入与输出

| 包 | 必需字段与含义 |
|---|---|
| turn_input | schema_version=1、session_id、turn_id、epoch、input_id、revision、kind、phase、observed_at；speech/text 携带 text，photo 携带授权 image_ref |
| agent_result | schema_version=1、原样回传 session_id/turn_id/epoch/input_id、唯一 response_id、semantic_id、audio_mode=mechanical_only；internal_text 可选，仅内部使用 |
| output_status | schema_version=1、原轮次身份、response_id、status、reason（适用时）；状态为 queued/started/completed/interrupted/dropped |

session_id 表示运行会话，不是永久记忆身份。重启或连接重建换新 session_id；epoch 在该会话内单调递增。turn_id 可以直接复用 epoch 的唯一表示，不要求重复计数。input_id 使用 ASR item_id 或照片 event_id；revision 表示同一输入的识别版本。kind 为 speech/text/photo；phase 为 partial/final。observed_at 为 UTC 观察时间，不冒充原始拍摄时间。

semantic_id 是回应意图，不是直接设备命令。具体语义白名单由动作和声音映射共同确定；未知值拒绝或静默，不擅自选随机动作/声音。response_id 是本次逻辑回应标识，与供应商 response_id 的映射必须保留。

## 开始、打断与识别

1. 语音侧在 speech_started、显式 interrupt，或新文本/照片明确取代当前交互时，先串行推进 epoch 使旧轮失效，再尽力取消旧生成、清理待播队列和设备缓冲。照片仅存档不自动打断语音；是否取代当前交互由入口明确指定。
2. 同轮 speech_started 与 final 不能推进两次。供应商 item_id、response_id 在原输入/请求创建时绑定原轮；迟到事件不能用“现在的 epoch”补标签。自动生成响应也必须找到原输入绑定，无法关联则不投递。
3. partial 为最新整段快照。增量式 ASR 先在适配器内按 item_id 累积；partial 仅临时显示/理解，不触发正式声音、工具副作用或长期记忆。
4. 同 input_id/revision 去重，旧 revision 忽略。同版本不同内容按冲突拒绝。非空 final 只启动一次正式决策；final 后的修订必须明确成为新轮，不能重复执行原轮工具。空 final 记为 no_input，保持旧轮失效，不补播旧回应。
5. 更换中文 ASR 时保留上述语义，不让不同提供方的 partial/delta 含义泄漏到 Agent 契约。

## 迟到结果与实际播放门禁

Agent 在接收模型结果、提交本轮回应、执行工具副作用之前校验原轮仍有效。语音侧在声音入队和每次真正提交音频帧之前再次校验 session_id/turn_id/epoch 与 response_id。同一回应重传不得重复入队；流式分块按 response_id 加块序号区分，不能把后续合法块误判为重复回应。

轮次推进和最后播放门禁必须由同一串行仲裁机制协调，避免“校验通过 → 用户打断 → 又提交旧帧”的竞态。清空队列和取消任务只是辅助措施，不能替代身份校验。已经实际播放的音频不能撤回；中断后应尽快停止余下帧，现场停止延迟需独立测量。

旧轮生成的工具结果也不能重新唤起回应。已发生的外部副作用保留真实记录，不能宣称取消撤销了它；尚未执行的副作用在执行边界重新检查。授权记忆写入需幂等并保留来源，partial 或失效的推断不升级为用户偏好。

response.done 只表示模型生成结束。机械音 queued 不等于已播放，started/completed 也不等于用户现场听见。播放回执只能反映对应软件执行阶段；现场可闻性单独验收。未输出的内部文本不能记成“已向用户说过”。

重连只静默恢复历史，不恢复旧声音。过期结果标 dropped，reason 可为 stale_turn、duplicate、expired 或 unbound_response；expired 须有明确的输出有效期规则，不以网络迟到自动生成新轮。用户主动要求重听时创建新的明确请求，不自动重播。

## 只读确认的现有接入点

以下依据仓库本地 `.runtime/conversation-upstream` 源码镜像，不是当前安装副本或语音隔离分支的验证结论。该目录为本机临时材料，不是远程可恢复依赖；实际接线前由语音负责人记录真实版本、路径、hook 与字段对应。

| 源码与位置（审计时行号） | 已观察行为 | 需在实际版本核对 |
|---|---|---|
| huggingface_realtime.py:744 | speech_started 调用清队列 | 推进唯一 epoch、绑定输入、取消旧生成 |
| huggingface_realtime.py:788/809 | partial 与 completed 转写分支 | input_id/revision/phase 贯穿与 final 去重 |
| huggingface_realtime.py:769/780 | response.created/done | 原请求/输入与供应商 response_id 绑定；迟到 done 不改变当前轮 |
| huggingface_realtime.py:841 | audio.delta 以裸 PCM 入 output_queue | 入队携带身份；禁止人话 PCM 流入机械音出口 |
| huggingface_realtime.py 的 response sender、工具调用与结果回调 | 串行发起响应并处理工具 | 排队请求和迟到工具结果保留原轮绑定 |
| console.py:588/843 | interrupt 与 clear_audio_queue 清理输出/设备缓冲 | 清队列之后迟到数据仍须被身份门禁拒绝 |
| console.py:885/924 | play_loop 消费后 push_audio_sample | 最后播放门禁与轮次推进串行化 |

镜像中裸 PCM 队列没有贯穿轮次身份，单独清空不能证明迟到数据不会重新入队。本文件不判断语音负责人当前实现是否已修复，也不要求替换其已存在的等价机制。

## 语音负责人已接受的接线计划

2026-09-23，语音负责人接受 v1 契约，计划使用 SenseVoice 中文 ASR、Silero VAD 与短机械音。以下是负责人提供的实现计划，尚非运行接口验收：

- session_id 启动生成；epoch 在 speech_started、interrupt、手动试听时推进；final 沿用原 epoch 并去重。连接重建也须满足旧连接输出失效规则，具体会话边界待实际 hook 确认。
- `/events` WebSocket 广播 `turn_input` final；局部识别不提交长期记忆。
- `POST /api/agent-result` 接收 v1 轮次身份、input_id、response_id、semantic_id 与 audio_mode=mechanical_only；旧轮、重复和过期结果丢弃。
- 输出 callback 计划每 20 ms 在同锁下检查身份后提交声音。该周期不是现场停止时延保证。
- 暂用本地中性短声确认收到语音；这属于收件状态提示，不能冒充 Agent 语义回应或“理解了”。正式语义处理仍待 Agent 接入。

实际服务监听地址、鉴权、有效期策略、错误/回执格式、语义白名单及可消费 hook 待语音负责人回报；本文件不指定端口或要求部署服务。

## 最小验收

- A 轮被 B 轮打断：A 的迟到 partial/final、模型结果、工具回调和音频均不能成为 B 的输出；B 的 final 只触发一次正式回应。
- partial 乱序、重复 final、相同版本内容冲突、空 final 和同轮多块音频分别覆盖；没有重复副作用或误丢合法音频块。
- 音频已出队但尚未 push 时发生打断：最后门禁拒绝旧帧；设备缓冲停止延迟另做现场测量。
- 重连/重启后的旧 session 消息、未知 response 绑定与过期排队声音静默丢弃，不自动重播。
- 只产生机械叫声/轻电流声，无启动问候、迟到模型 PCM 或错误兜底人话泄漏；仍能理解中文输入，称呼变化不改变历史身份。
- queued、生成 done、播放完成与现场可闻证据分别记录，不以中间状态宣布端到端通过。

本轮只交付文档。暂不新增 Agent 轮次模块。只有实际消费者明确需要纯校验模块，且输入、写权、工作树与验收被限定后才实施；运行版本接线与播放仲裁仍由语音负责人单写。
