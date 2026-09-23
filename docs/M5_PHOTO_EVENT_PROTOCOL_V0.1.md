# M5 照片回应最小事件协议 v0.1（评审修订 1）

状态：产品接口提案，供固件总控与采集/Agent 实现方对齐；尚未联调。产品权威为 haifeng，固件实现和恢复包权威为 D:\reading-pet。USB 仅为台架传输，后续 BLE/Wi-Fi 仍待验。

## 1. 职责与事件身份

- 用户按眼镜腿上的实体按键拍照。眼镜采集 worker 负责发现本次拍摄、取得新图并建立一次事件；不能用电脑或 M5 发拍摄命令冒充这一入口。
- 采集 worker/主服务为每次真实拍摄分配唯一 event_id，贯穿传输、生成、展示、重试和取消。按键重复通知去重；两次真实拍摄使用不同 ID。协议尚不能获取物理拍照通知时，须明确接入阻塞，不伪造 capturing 状态。
- 海风主服务是状态与事件记录权威，调度图片理解及同一陪伴 Agent，持久保存本次短回应和表情；推送到 M5，供家中 Reachy 后续接续。
- Agent 返回短回应和受限表情标签，不直接控制设备、不生成传输成功状态、不另建 M5 人格/养成记忆。
- M5 固件消费状态和回应、渲染并回 ACK；可产生重试、取消和重看操作。不会拍照、不会独立推断照片、不会改变心情/疲惫数值。
- 固件总控 01a0c813 统筹；01a0c5c6 为唯一固件集成/COM/烧录负责人；01a0c7df 仅负责美术。眼镜 worker 与 Agent 实现负责人的具体任务 ID 尚待总控派定，不能据此宣称已有人执行。

## 2. 服务到 M5 的消息

拟使用 JSON 消息，兼容方案由固件负责人决定；不覆盖现有 rhythm protocol=2 的命名空间。新消息统一 type=photo_event，schema_version=1。

| 字段 | 规则 |
|---|---|
| event_id | 非空、不含个人数据的唯一字符串，最长 64 ASCII 字符 |
| attempt | 正整数，首次 1；同事件每次获准重试递增 |
| revision | 同一 event_id 内单调递增整数，跨 attempt 不归零 |
| capture_sequence | 配对服务域内持久单调递增的拍摄序号，用于不同事件排序，不使用 event_id 或时间戳排序 |
| delivery_mode | live / snapshot；重连和重启恢复一律 snapshot，静默呈现 |
| state | captured / uploading / received / responding / replied / failed / cancelled |
| captured_at | UTC ISO 8601 拍摄时间；仅接收到图时才知道的时间不能冒充真实拍摄时间，可为空并另记 observed_at |
| observed_at | 服务首次观察到本次事件的 UTC 时间 |
| text | 仅 replied 携带；NFC 规范化后最多 24 个 Unicode code point，严格 UTF-8。只接受固件字形集支持的普通可见字符，不接受 emoji、组合附加符、零宽、双向控制及其他控制字符、换行或 Markdown；原生字体最多三行，不滚动、不裁切。非法或排不下整条拒收 invalid_reply |
| expression | 仅 replied 携带；初版白名单 neutral / curious / delighted / gentle。映射失败降为 neutral，保留原有形象，不挂接旧数值 |
| error_code / retryable | 仅 failed 必须携带；由服务判断是否允许重试 |

不将图片、模型密钥、模型原始长文本发送给仅负责显示的接口。表情和 text 来自同一次已保存回应，以一条消息原子更新。超长/不合法文本由服务重新约束，固件拒收并回错误，不能部分展示后谎报成功。

## 3. 状态含义

captured：完整新图已到采集端；uploading：正在发往陪伴服务；received：服务完整接收；responding：正在生成；replied：有效回应已持久保存，可展示。可跳过瞬时中间状态，不得倒退；failed 和 cancelled 是当前 attempt 的终态。

没有证据的阶段不显示。received 不可使用“她看懂了”的角色表现。replied 是回复生成成功，不等于 M5 已显示，也不等于 Reachy 实体已动作。家中实体在线状态单列，不冒充照片状态。

failed 代码初版：capture_unavailable、transfer_failed、network_unavailable、reply_timeout、reply_failed、invalid_reply。固定本地状态文案与角色回复分开；不得用温柔模板假装成功。照片已保留且可再次发送/生成时才 retryable=true；图像缺失时引导用户重新按眼镜腿拍摄，不用 M5 远程补拍。

## 4. M5 到服务的操作和 ACK

photo_action：schema_version、action_id（唯一）、event_id、expected_revision、action（retry/cancel）。服务根据当前状态串行接受或拒绝，返回 action_ack（accepted/rejected + reason + 当前状态）。同 action_id 重发返回同一结果，不能重复执行。

- retry：仅 failed 且 retryable=true 接受；复用保留的新图，event_id 不变、attempt 增加。已经生成并保存的回应只重送，不重新生成另一句。
- cancel：仅未 replied 的在途事件可接受；停止后续生成/投递，发 cancelled。取消与回应同时到达由服务串行顺序裁决；已 replied 返回 too_late。取消不等于删除已存记录或召回已发送给模型的数据。
- 重看：优先本地重显最近有效回应，不重新调用模型，不再播放提醒或震动。
- photo_ack：schema_version=1、event_id、attempt、revision、result（rendered/rejected）、reason。rendered 只说明绘制流程完成，不声称用户看过或现场视觉验收通过。

M5 忽略旧 revision；相同 revision 重发只补 ACK，不重复提醒。cancelled 后来的旧回应不展示。多个事件保持拍摄顺序，不让较早事件的迟到结果覆盖正在看的较新回应；旧结果保存在服务。重连只恢复当前快照，迟到通知须标识，不能连续补播声音/震动。

## 5. 震动与声音

用户优先希望 M5 能震动。StickS3 无内置马达，先由唯一硬件负责人验证外接模块供电、驱动、体积与触感。通过后，首次实际渲染新回应时触发一次轻短震动，默认强度需现场测试，可关闭。不要用上传成功触发同一种“回应到了”触感。

声音独立可关闭；震动能力尚未配置时屏幕流程仍可验证，不伪报 has_haptics。能力报告至少区分 display、audio、haptics，软件驱动自报与现场可感知验收分开记录。

## 6. 联调验收

用同一真实拍照 event_id 验证：眼镜腿按键 → 新图 → Agent 短回应 → M5 表情/文字 → ACK。另测超长文案、乱序/重复消息、取消竞争、重试、重连、两张不同照片先后返回；不串图、不重复提醒、不复活取消事件。外接震动需现场确认感知，USB 台架通过不代表外出链路通过。

## 7. 固件评审后的有界传输与恢复规则

以下规则为本次提案修订，尚未在固件或服务实现；角色壳停用不依赖此协议。

### 帧边界

USB 台架采用 UTF-8 JSON Lines：每条 JSON 对象的实际编码长度最多 1024 字节，不含末尾单个 LF；发送方使用直接 UTF-8 文本，避免不必要的 Unicode 转义，接收方仍按实际字节计数。完整帧含 LF 最多 1025 字节。RX/TX 均按此上限设计，不继续沿用旧 512/768 缓冲假设。

超限时丢弃直到下一个 LF 重新同步，返回不携带未经完整解析字段的 protocol_error/frame_too_large；不执行半帧。非严格 UTF-8、重复 JSON 键、非法 JSON、错误字段类型、未知必需枚举均拒收。未知顶层字段在总长度内可忽略，不赋予任何行为；schema_version 不支持则拒收 unsupported_schema，不猜测兼容。

### 计数、排序与快照

attempt/revision/capture_sequence 均为 1..2147483647 的整数，不接受小数、字符串或回绕。服务将 event_id、capture_sequence、attempt、revision、状态、回应、动作去重记录事务持久化，重启不重分配或归零。达到计数上限返回协议错误，须显式迁移，不静默回绕。

capture_sequence 在配对服务域内唯一，一次新拍摄取新序号；同事件重试不变。不同 event_id 使用同序号，或同 event_id 改序号均返回 sequence_conflict。M5 选择已收到的最大 capture_sequence 作为当前事件：新事件等待时也不让旧回复覆盖；旧事件仍由服务保存。新服务域须显式重新配对并重建缓存，禁止把另一套计数接到旧设备缓存。

服务以 delivery_mode=snapshot 发送当前权威事件快照；设备启动/重连完成快照前不处理 live 提醒。快照只恢复当前界面，不震动、不发声，若与设备持久计数冲突则请求重新同步，不私自清空高水位。

### 终态与重试

replied 和 cancelled 为事件终态，不允许同事件再次生成/恢复；可按原状态重送回复，渲染失败不改变主服务 replied。failed 为 attempt 终态；仅服务接受 retry 且保留有效原图时，attempt 加一、revision 加一，状态允许回到 uploading/received/responding，这是“不得倒退”的唯一跨 attempt 例外。所有新 revision 都须符合状态机。重复推送相同 revision 的业务内容必须完全相同，delivery_mode 可因重传/快照不同；同 revision 不同业务内容拒绝 revision_conflict。

### 文本与操作确认

服务在发出前做 NFC、24 code point、允许字符集与排版校验；固件按实际装载字形再次检查，任何不支持字符、残留组合附加符或超过三行都拒绝 invalid_reply，不按字节截断。字形白名单由固件能力版本提供，不假定所有中文或 emoji 都可显示；服务不得用删除不支持字符的方式改变回复意思。

action_ack 明确 schema_version、action_id、event_id、expected_revision、actual_revision、attempt、result 及 reason。拒绝原因至少包含 stale_revision、not_retryable、too_late、unknown_event、invalid_action。等待 ACK 超时重发原 action_id 与原请求，不另造新动作；修改请求须新 action_id。服务先持久化动作裁决再 ACK，重启仍可返回同一结果。

### 通知去重与断电

首次渲染 live 新回复前，固件先持久记录该配对域 event_id/attempt/revision 与已消费提醒标志，再触发声音/震动；重复消息只补 photo_ack，不再提醒。此顺序选择“至多一次提醒”：断电可能漏一次提醒，但不得恢复时重复惊扰，回应仍可静默重看。

相同回复的 snapshot、重新绘制、重看都不清除消费标志。设备缺失或损坏去重记录时进入静默同步，不能把所有旧回复当新消息。ACK 仅证明软件渲染或处理，不证明用户已看见、听到或感知震动。
