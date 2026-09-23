# 啾啾语：离线语言与声音候选 v1

2026-09-24 · P2 研究包 · 未接入生产。现有声音已获 Kim 肯定，动作交互优先。本包不要求延长生产 deadline，不增加 semantic 白名单，不占用设备或其他部门 QA。

目标是让原来的声音形成有起承收尾的短话轮，而不是把一个提示音循环播放。当前只是受约束的拟语言：能表达交际意图与情绪，不承诺传递“月亮”等具体词义。小黄人仅为体验类比，没有使用其素材、发音或关于其语法的假设。

## 实际资产

权威引擎：`patches/reachy_companion/pet_audio.py`，本研究基线 Git `6ecdcfcfffa3929d34f96f3b6f7792a0e84fb878`；文件 SHA256 `46a4808f1b71afc97164f440415c8b710ebf87b737b41f60340209b7e0f32b5b`。语音 owner 已交叉确认参数。仓库未发现跟踪的 AGENTS.md。

|既有 semantic|真实单位 startHz → endHz / ms（从 0 编号）|旧版总长|
|---|---|---|
|ack|520→850/110；740→610/160|330 ms|
|curious|460→680/130；600→1100/200|390 ms|
|happy|650→1000/90；810→1300/90；1000→760/160|430 ms|
|thinking|410→440/100；510→500/130|290 ms|
|uncertain|740→550/130；520→350/180|370 ms|
|sleepy|560→330/230；350→230/160|450 ms|

这 13 个单位是合成滑音，不是实际语音音素。界面拟声标签不是词典。不存在可证明的 /j/、/u/、/a/ 等库存，不能把它们写成已经录好的“啾、咕、哇”。下表音节串采用 `A0` 等技术记号，表示听觉节拍单位，不是 IPA 或汉语读音。

保留音色常量：16 kHz / mono / float32；线性扫频；主波振幅 .11；37 Hz 相位调制、深度 .45；二次谐波 .018；高斯纹理 std .004；seed 7；sin 包络幂 1.5。旧版每单位尾部 30 ms 静音、限幅 ±.16。本原型重新积分变调后的瞬时频率，保持音色公式；只对包络末点的浮点负误差取零，避免非整数幂产生 NaN。旧版对照直接调用原函数，不改源码。

## 文献事实与设计假设

1. **音节结构**：[Maddieson, WALS 第 12 章](https://wals.info/chapter/12) 用 C/V 模板说明自然语言的组合约束。启发是先限制组合再生成；本引擎没有 C/V 发音器官模型，因此不会伪装成 CV 语言。下面的“滑音核 + 边界”是本项目设计。
2. **韵律与话语行为**：[Ward 2004](https://www.isca-archive.org/speechprosody_2004/ward04_speechprosody.html) 检查 316 个英语非词汇话语，讨论时长、音高、响度、斜率等的语用功能；作者也说明研究非系统、证据有限。它支持独立控制多个韵律维度，不证明某个升调能被所有人理解为好奇。
3. **轮次**：[Stivers 等 2009](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705608/) 在十种语言中发现倾向减少轮次间隙与重叠，同时存在时序差异。它研究人类会话，不给机器人规定固定延迟。本设计保留简短回应并让用户随时抢回话轮；不拿该论文证明长句越长越好。
4. **非语言情绪**：[Schröder 2000](https://www.isca-archive.org/speechemotion_2000/schroder00_speechemotion.html) 的德语演员 affect bursts 在预筛选样例的感知实验中平均识别率为 81%。这是人声与特定实验的结果，不能迁移为 FM 啾啾语识别率。
5. **HRI 中的非词汇短语**：[Savery、Zahray、Weinberg 2020 数据集](https://arxiv.org/abs/2010.04839) 提供 4.2 小时即兴情绪发声并做听测；[同作者机器人手臂实验](https://arxiv.org/abs/2009.09048) 比较音乐韵律、单音及无声，报告主观信任差异，但行为上的同意比例没有显著差异。不能据此宣称啾啾会提升信任，也不导入其人声数据改变当前声音身份。

以上为在线一手论文摘要/官方章节可确认的范围。以下所有数值、句法和语义映射均是**待听测的项目设计假设**，不是语言学定律。

## 最小可生成系统

- 单位模板：柔和起音 → 一枚既有滑音核 → 柔和收音 → 0–250 ms 边界。保持连续音高，避免量化为音阶旋律。
- 短语模板：`接触标记? + 主体节拍组 + 收尾`。组内 1–4 单位、30 ms 边界；组间本轮 120 ms；末尾 40 ms。句子可有 1–3 组，不全句等距复读。
- 接触标记通常引用 A0/A1；主体保留目标 semantic 的显著单位；疑问保留 C1 上行，完成用 A1 下行，困倦保留 S0/S1 下行。它们是稳定的意图提示，不是逐词翻译。
- 允许 AB→A′B′ 复现一次，第二组通过节拍、音高或重音变化承接前组；不允许无限循环。v1 使用审核过的静态模板，暂不随机采样任意语法。
- 重音放在主体中部：普通 gain .92、突出单位 1.05；困倦 .8。音高只在既有扫频上做 ±3 半音以内偏移；速度用 duration_scale；句末下降表示收束的效果待听测。
- seed 只影响微小噪声纹理，不能改变意图、模板、单位顺序或档位。结构变体必须另有 candidate_id。

|档位|候选范围/本轮|适用|代价|
|---|---|---|---|
|即时短答|原 0.29–0.45 s 保留；扩展候选 0.6–0.85 s / 0.8 s|叫名、收到、思考一次|较少情绪展开，能快速交还话轮|
|普通回应|1.0–1.3 s / 1.2 s|好奇、修复、收尾|比旧版占用话轮更久|
|情绪长句|1.4–1.8 s / 1.6 s|看月亮、开心等有明确内容的分享|更有展开空间，但可能像音乐或妨碍用户接话|
|静音|0 s|stop、quiet、被打断|不追加“我知道了”声音|

不把所有回应升级为长句。建议未来默认仍用旧版；只有明确分享/情绪场景才选长候选，并由语音 owner 独立评审。当前没有进行上线选择。

## 八个场景及可追溯音节串

记号：A=ack，C=curious，H=happy，T=thinking，U=uncertain，S=sleepy；数字是 note 下标；`|` 为 120 ms 停顿，空格为 30 ms；末尾 40 ms。括号列依次是每单位相对原扫频的半音偏移，精确重音、伸缩和单位内曲线见 JSON。不是需要 TTS 朗读的文字。

|场景 / candidate|音节串|韵律与意图|
|---|---|---|
|叫名字 / name|A0 A1 \| A0 A1|0.8 s；(0,0,+1,-1)；接住呼唤再收尾，“我在”意图|
|看月亮 / moon|A0 A1 \| C0 C1 H0 C0 \| C1 A1|1.6 s；(0,0,-1,+1,+2,+1,0,-2)；接触、注意展开、收束；不编码“月亮”词义|
|开心 / happy|A0 \| H0 H1 H2 \| H0 H1 H2 A1|1.6 s；(0,+1,+2,+1,+2,+3,+1,-1)；第二组抬升后降落|
|好奇 / curious|A0 \| C0 C1 \| C0 C1|1.2 s；(0,-1,+1,0,+2)；末端上行，邀请对方回应|
|没听懂 / uncertain|U0 U1 \| T0 C0 C1|1.2 s；(0,-1,-1,0,+1)；下行犹疑转上行修复请求，不装作理解|
|思考 / thinking|T0 T1 \| T0 T1|0.8 s；(0,-1,0,0)；一次占位，不循环、不每秒补发|
|困倦 / sleepy|A0 \| S0 S1 S1|1.2 s；(0,0,-1,-2)，gain .8；逐步下落、收回话轮|
|被打断 / interrupted|正在播 moon 的前 420 ms → ∅|通过原 TurnGate.advance 清空后续 PCM；示例尾部留静音以便检查；绝无新增打断回答|

## Phrase plan v1 契约

`phrases.json` 是离线候选数组。每个对象含 version=1、candidate_id、semantic_id（既有六项）、intent、emotion、tier、units、total_duration_ms、variant_seed。每 unit 含 motif_id=`kind:index`、pitch_scale、duration_scale、gap_ms、intensity、pitch_curve_st=[start,mid,end]（相对原扫频的半音，线性插值）、role。当前样例每单位曲线三个点相等，整句音高轮廓由跨单位偏移与原滑音共同形成。渲染器提供有限值/边界/实际时长校验，非面向不可信网络请求的完整 schema 校验器。

生成顺序：原单位频率线性轨迹 × pitch_scale × 2^(curve/12) → 相位积分 → 原 FM 音色与包络 → intensity → gap。时长含所有停顿，允许采样取整误差 ≤1 ms，最大 1.8 s。

**运行时信息不在静态文件中保存**：session_id、turn_id=epoch、epoch、input_id 由唯一语音 owner 在已接受 final 的当前轮注入；response_id、expires_at/deadline 也由运行时分配。一个句子就是一个 response 的完整 PCM，不能拆成多个 response 绕过 answered。

当前 `/api/agent-result` 仅接受 mechanical_only + 原 semantic 并自行生成旧音；它不接受此配置。`deadline=min(last_final_at+2.5, monotonic_now+expires_at-Unix_now)` 同时约束入队和每个 20 ms 块；试听路径另有 1 s 上限。因此 1.6 s 文件不保证适配生产，延迟 1 s 后甚至剩不足 1.6 s。未来 owner 应在渲染后按剩余预算选择原短答或丢弃；建议预留至少 100 ms 安全裕量（设计值），不能本研究自行延长 TTL。跨进程不能传递单调时钟值。

原 gate 每块复查 identity/muted/deadline；new speech、stop、恢复等推进 epoch，清空 pending。不得为句末完成而阻止打断。stop/quiet/interrupted 配置均为空，运行时应先执行控制取消，再跳过音频队列，不能把空 PCM 入队。这里的 ack 仅占据既有 semantic 字段，不授权播 ack。已交给语音 owner 评审，尚未接入。

## 生成、试听与验证

在仓库根目录运行（Python + NumPy；本机 NumPy 2.5.0）：

```powershell
python tools/jiujiu_language/render.py
python -m unittest discover -s tools/jiujiu_language -p 'test_*.py'
python -m unittest discover -s patches/reachy_companion -p test_pet_audio.py
```

脚本只读引擎、计算 PCM、写 WAV；不导入 pet_companion、不打开麦克风/扬声器/daemon。14 个 WAV 写入忽略目录 `qa-artifacts/jiujiu-language`：七种候选 + 被打断示例 + 六个原版。文件为可复现输出，不进入公开 Git 仓库。`measurements.json` 记录时长、峰值、RMS、SHA256 和源文件摘要。

已验证：新 4 项测试 + 旧 gate 10 项测试通过；七种候选时长 800–1600 ms（误差 ≤0.063 ms），peak 0.1066–0.1381 < .16；相同 seed 可复现；未知单位/越界/NaN 被拒绝；stop/quiet 不能携带长句；新语音、stop、mute、过期之后下一块全零。被打断示例在 420 ms 后归零。

**真实限制**：本轮无实体播放，无人类听测，也没有主观听感验收；不声称已经“像完整说话”、不声称能准确传意。FM 基底缺乏人声共振峰，可能仍被听成旋律。句长只是相对旧版变长，未生成 3–5 秒长句以免与 P2/期限边界冲突。

后续可做最小盲听：隐藏场景标签、随机新旧顺序，评价“仍是同一个啾啾”“像讲话而不是通知”“打扰程度”各 1–5 分，再从意图集合选项判断；单独记录误判，尤其好奇与没听懂。由 Kim 先选喜欢的候选，再决定是否值得语音 owner 实施。这里不要求现在占用动作 QA。
