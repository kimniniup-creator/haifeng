# GENKI 静态评估小范围独立复核

2026-09-24；审查固定提交 `ba1dd0e5bb504e0b9540e0fb4a61ccc2c69df228`（PR12）。结论：采样代码、指标口径和保存的元数据聚合结果一致；不代表重新执行图像推理，也不阻塞 PR11 软件链路交付。

## 已独立核对

- 在 QA 隔离快照运行 `python -m pytest tests/test_pet_vision_evaluation.py -q`：**1 passed，0 skipped，0.32 秒**。该测试覆盖 unknown 不算 TN，以及 decided / all-sample 分母。视觉 owner 的 12 项合计不冒充本轮独立测试数。
- 采样源码使用局部 `random.Random(20260924)`，对原始标签的两类分别无放回抽取 128，再排序处理；没有按预测结果选样。固定双侧 mouthSmile >=0.55，原图直接解码后传入 detector，无放大或替换裁剪。quality 默认仍为 80px、35–225 亮度、25 清晰度、35/30 度姿态及 1% 边缘条件；与冻结 `fa36bab` 的 detector / face 代码无差异。
- 只读现存 ignored 元数据：256 个唯一 sample_id，范围 1..4000，正负各 128。使用独立计数循环以及脚本 confusion 函数分别重算：TP65/FN7/FP0/TN71，unknown 正56/负57。143/256 coverage=55.86%；65/128 全部正例响应召回=50.78%。unknown 共113，没有隐入 TN 或从全部正例召回分母移除。
- 去 quality 的诊断聚合也与元数据一致：TP109/FN15/FP1/TN124，unknown 正4/负3。不能用它替代冻结规则结果。
- 理由计数一致：face_too_small95、no_face7、face_clipped7、exposure2、blur_or_low_texture3；理由可重叠。
- 提交仅四个文本文件（报告、工作记录、脚本、测试），没有原图、tar 或原始评估 JSON；`.runtime` 被 Git 忽略。代码限制下载 32MiB、校验 archive hash，只在内存读 tar/JPEG，输出元数据限定在本 worktree 的 `.runtime`。未对本机其它位置作全盘数据残留审计。

## 证据边界与一处 provenance 缺口

检查时原始元数据文件 SHA256：`61cfc733aca2784ec34ad91ade9fec722a3f166fd53c13632e73b4eca17283c6`。其中模型 hash `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`、archive hash `74776c0a3fac07f1cefc5d8acebf55a71fc870babc68c6b044a87d811b6de999` 与报告一致。

**现存运行 JSON 没有 `detector_source_sha256`，而最终提交脚本会输出它。** 本轮不能用最终脚本的新字段倒推原运行已记录源码版本；仅能事后核对提交中的 detector 未改变。已反馈视觉 owner。模型路径允许参数覆盖，脚本记录模型 hash，但不主动拒绝其它模型；复现时需使用报告指定模型并核对 hash。

本轮未再次下载 archive，未复跑 256 图推理，也没有原始标签表可供独立重放全部抽样 ID；确认的是采样代码机制、保存样本的唯一性/平衡性和聚合结果。保存的 labels/系数由原评估运行提供，未独立证实图像标签配对与系数正确性。

报告已将商用授权写为未确立，提交无数据再分发；本轮未重新作授权法律判断。256 张样本、0/71 已判负例误报不能证明真实零误报。静态评估不覆盖持续800ms、真人摄像头、实际听感、哭闹或逗趣识别；训练仍为0。
