# 笑脸到声音：独立离线验收

2026-09-24。软件离线链路通过；真人识别准确率、现场扬声器听感和生产部署均未验收。

## 固定版本与结果

- 组合源码：`7db4d40e08e7d3d839e6c61602e94c21947ffe0b`。
- 独立复跑仓库测试：**51 passed，0 skipped**（5.48 秒）。包含组合链路 3、视觉决策 21、专用语音连接 7、主动音频 20。
- QA 增量：**8 passed，0 skipped**（4.33 秒）。三项经过真实规则引擎、Agent ASGI、认证 HTTP/WebSocket、声音输出回调，验证无人脸、多脸、低质量输入无决策、无动作、无 PCM；五项验证 HTTP 到完整 PCM 与回执不改变原有 final/answered 身份，以及租约过期、回执发送失败、语音活动、精确 deadline 后下一缓冲归零。
- 上游语音旧版 `0bd88b6` 曾在精确截止时刻继续输出 PCM；独立检查发现后，由语音 owner 在 `dbd8bd5` 修复，本组合已包含该修复并通过回归。
- 视觉 `fa36bab` 此前独立 **42 passed，0 skipped**，含真实模型空白帧。该证据仅证明模型加载和空白帧路径，不代表真人表情准确率。
- `7db4d40..624ec3b4273544c1c034e874eb7daab55a232e06` 文件差异仅为诊断/维护文档、motion 遥测及其测试；笑脸、Agent、声音源码未变。PR11 可引用上述固定组合证据，无需重复跑无关测试。

仓库测试中的持续笑脸由合成 blendshape 系数输入，真实协议链路收到一次 queued，输出非零 PCM 后通过 WebSocket 收到 completed；语音打断和断连分支停止后续 PCM。`completed / last_buffer_submitted` 表示缓冲已提交，不能等同人耳听到。

## 可复现方式

在隔离目录解包上述 Git SHA，使用具备项目依赖的 Python 3.12。将本分支 `qa/visual_sound/test_qa_smile_negative.py` 复制到解包目录 `tests/`，将 `qa/visual_sound/test_qa_proactive_pcm.py` 复制到 `patches/reachy_companion/`。这些测试明确面向隔离快照，不在 QA 文档分支根直接收集。

从**解包目录**运行：

```powershell
python -m pytest tests/test_smile_audio_combined.py tests/test_visual_response.py tests/test_proactive_link.py patches/reachy_companion/test_proactive_audio.py -q
python -m pytest tests/test_qa_smile_negative.py patches/reachy_companion/test_qa_proactive_pcm.py -q
```

本轮首次误从 QA 根收集遇到 `ModuleNotFoundError: pet_interaction`，改为快照根执行后通过；没有通过改源码消除环境错误。出现 Starlette/WebSocket 弃用警告，无运行失败。

所有服务仅为测试自建随机 localhost 端口，voice lifespan 关闭，硬件及模型启动方法设为禁止调用。未访问生产 API，未启动/停止/重启生产进程，未打开摄像头、麦克风、扬声器或运动设备。

## 仍需现场证据

真人持续微笑能否稳定产生正确视觉事件、不同光照/姿态下误触发情况，以及声音是否实际可听且舒适，必须另行验收。电机物理安全与音频链路分开；此报告不批准电机动作，也不以电机未通过阻止软件音频链路结论。
