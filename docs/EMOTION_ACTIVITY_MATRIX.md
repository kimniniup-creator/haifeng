# 六类情绪到机器人活动的实机覆盖矩阵

2026-09-24。对象：`local_agent` 的 `EMOTION_TRAJECTORIES`（继承上游
`Agent/emo_action/emotion_reachy_mapping.json`）。全部经真实 Reachy daemon 执行，
`motion.status` 由 daemon 的 `move_completed` 事件确认，不是软件回执。

## 结果

| 情绪 | 轨迹（度） | 触发输入 | 分类结果 | 实机动作 |
|---|---|---|---|---|
| joy | `[[4,0],[0,0],[4,0]]` | 网图：夜间蜡烛庆生，多人微笑 | joy | completed |
| excitement | `[[6,0],[-3,0],[6,0],[0,0]]` | 网图：海面上空烟花 | excitement | completed |
| sadness | `[[-5,0],[0,0]]` | 网图：塑料垃圾覆盖的海滩 | sadness | completed |
| curiosity | `[[0,6],[0,0]]` | 网图：多向路标；眼镜实拍 | curiosity | completed |
| anger | `[[0,-5],[0,5],[0,0]]` | 文字：押金被无理由扣留 | anger | completed |
| confusion | `[[0,-6],[0,6],[0,0]]` | 文字：会议时间前后矛盾 | confusion | completed |
| none | 空 | 网图：枯萎玫瑰 / 蓝屏终端 / 禁左标志 | none | suppressed，正确不动作 |

## 照片路径判不出 anger 和 confusion，这是设计不是缺陷

七张网图里，anger 和 confusion 一次都没有从画面中产生：

- 被砸碎的电话亭（玻璃满地、涂鸦）→ `sadness`，依据写"公共财产被破坏"。
- 塑料垃圾海滩 → `sadness`。
- 公共终端 Windows 蓝屏（属提示词里的"故障"）→ `none`，依据"技术性错误界面，没有可见证据支持特定情绪分类"。
- 禁止左转标志与背景左转专用道牌矛盾 → `none`，模型只描述了前景标志。
- 彭罗斯不可能三角铭牌 → `curiosity`。
- 枯萎玫瑰 → `none`，依据"静态植物，无人物表情或事件线索"。

上游 `selection_policy.evidence_rule` 原文：*Select an emotion only from the user's
words or an explicit task context; do not infer the user's internal emotion from an
image.* anger 的定义是"只针对**明确描述的**不公平、伤害或故障"，confusion 是
"信息相互矛盾、指代不清或缺少关键条件"——两者天然属于对话上下文，不属于画面推断。
视觉提示词还要求"无法确定时不要勉强分类"。

因此这两类改用文字轮验证：`kind='message'` 时 `respond.expression` 由 Agent 选择，
不被观察结果覆盖（`kind` 为 capture/image 时才覆盖）。两次都一次命中目标类。

**结论：照片路径可稳定产出 joy / excitement / sadness / curiosity / none 五种，
anger 与 confusion 需要用户把事件说出来。** 若要让照片也能产出这两类，必须改视觉
提示词的证据规则，那会同时放宽"不从图像推断情绪"的约束，属于产品取舍，未擅自改动。

## joy 的轨迹不回中位

`joy` 是 `[[4,0],[0,0],[4,0]]`，最后一段是 +4°，动作结束后头部停在抬起 4° 的位置，
直到下一个动作才改变。其余五类末段都是 `[0,0]` 回中。这来自上游映射，未改动；
如果不希望 joy 之后保持抬头，需要在映射末尾补一段回中。

## 测量口径与限制

- 位姿按 0.08 秒间隔采样 `present_head_pose`，记录相对基线的带符号极值。
  用它区分轨迹方向：joy/excitement/sadness 以 pitch 为主，
  anger/confusion 为 roll 双向，curiosity 为 roll 单向。方向全部与映射一致。
- **幅度数字不能当精度验收。** 基线在任务提交瞬间采样，上一轮动作可能尚未稳定，
  实测极值因此带基线误差（anger 一轮整体偏移约 0.05 rad 即属此类）。
  真正的精度验收需要独立的静止基线和更高采样率。
- 声音全程 `suppressed`（`ROBOT_SPEECH_ENABLED=false`），未占用音频设备。
- 每类只跑一次，不构成稳定性或重复性结论。
- 图片取自 Wikimedia Commons，仅用于本机分类测试，未入库。

## 复现

在 `local_agent` 目录下运行，服务需已启动。图片目录里按类名放 `<类名>.jpg`：

```powershell
.venv\Scripts\python.exe tools\run_emotions.py <图片目录> joy excitement sadness anger confusion
.venv\Scripts\python.exe tools\run_text_emotions.py
```

逐条原始任务记录在忽略目录 `local_agent/data/emo-*.json`、`text-*.json`，
汇总为 `emotion-matrix.json` 与 `emotion-matrix-text.json`。
