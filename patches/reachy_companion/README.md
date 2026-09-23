# 啾啾：本地中文识别与机械短叫声

当前入口是 `pet_companion.py`，替代本机原有官方 Conversation App 的 7860 界面。识别使用 SenseVoice int8 + sherpa-onnx，断句使用 Silero VAD；回应是自行合成的 FM 啾鸣与轻微电流质感，无 TTS、无云端音频上传。没有专用唤醒词，开启时持续聆听。尚未接入语义服务时，只用一个短叫声表示听到，不宣称理解了情绪。

## 安装和启动（Windows / Reachy Mini）

需要 Python 3.12（由 uv 管理）、uv、机器人 WASAPI 音频设备。运行 `setup_pet.ps1` 创建隔离环境并从 sherpa-onnx 官方 release 下载、校验模型；约 155 MB 压缩包。模型和环境放在被 Git 忽略的 `.runtime`，不提交录音、转写或模型。

```powershell
.\patches\reachy_companion\setup_pet.ps1
& .\.runtime\voice-env\Scripts\python.exe .\patches\reachy_companion\pet_companion.py --models .\.runtime\voice-models
```

启动前停止旧 Conversation App，勿同时开两个音频操作者。命名互斥锁阻止新版程序和已打补丁的旧应用重复运行。界面是 http://127.0.0.1:7860/ ，浏览器已有旧页面时刷新。仅选取名称含 Reachy Mini Audio 的 Windows WASAPI 输入/输出，不回退到电脑默认设备。不启动或改动 daemon、相机、动作、人格和记忆。

本机环境位于 `D:\海风\.runtime\voice-env`，模型在 `D:\海风\.runtime\voice-models`。当前运行代码来自独立工作树 `D:\haifeng-worktrees\voice-response`。未设置开机启动。回退时先停止此进程，再按原入口启动官方 Conversation App；两套依赖隔离。

## 轮次和语义服务接口

新语音开始、暂停、停止、设备恢复、队列溢出均推进 epoch，立即清除旧 PCM。识别线程、入队和 20 ms 输出回调逐层检查 session_id / turn_id / epoch / input_id；每轮只接受一次 final 和一次输出，过期或重复结果不播放。VAD 的最短静音是 550 ms；尚未引入语义断句或回声消除，嘈杂场景和播音自激仍需现场验证。

- `GET /api/state`：收音状态、设备延迟、当前一句转写及耗时。
- `POST /api/mute`：`{"muted":true}`；`POST /api/interrupt` 立即作废当前轮。
- `POST /api/audition`：kind 为 ack / curious / happy / thinking / uncertain / sleepy。界面附带 expected_epoch，迟到的试听不能恢复已停止的声音。
- `WS /events`：首次 state，随后 turn_changed、speech_started、turn_input、output_status。语义服务发送 `{"type":"subscribe","consumer":"pet-agent"}` 后，禁用自动 ack，由服务选择叫声。
- `POST /api/agent-result`：回传原始四项轮次身份、唯一 response_id、audio_mode=mechanical_only、白名单 semantic_id，以及可选 Unix 秒 expires_at。有效期最多到当前 final 后 2.5 秒，拒绝陈旧、重复、已静音或没有 final 的结果。没有任意 PCM/TTS 入口。

`output_status` 的 completed/last_buffer_submitted 表示最后缓冲已交给音频回调，不代表实体听感证明。显示的“停顿至入队”是 VAD 静音窗口加识别阶段估算，不是扬声器实测端到端延迟。接口的详细身份约定见 `docs/VOICE_AGENT_TURN_CONTRACT.md`。目前只有本机访问与 Origin 检查，不用于公开托管。

## 验证（2026-09-24）

```powershell
& .\.runtime\voice-env\Scripts\python.exe -m unittest discover -s patches/reachy_companion -p 'test_*.py' -q
```

26 项针对性测试通过，均不打开音频设备；互斥锁测试使用独立测试名。覆盖旧轮淘汰、回调最后检查、重复 final / response、过期、静音、迟到试听、合成波形、旧应用异步收音恢复。项目原有测试另有 19 项通过。桌面 1400×1000 和手机 390×844 页面已检查，无横向溢出/JS 异常；暂停、继续、试听、停止通过。

三条合成普通话短句识别用时 453 / 531 / 609 ms；“啾啾”被转为“揪揪”，语义服务应按别名处理，不篡改原始转写。一次真实设备 WASAPI 扬声器回环测试中，停止后最后非零样本约 47 ms。回环仅证明输出端数据路径，实体可闻音量、真实环境准确率、自然插话与完整语义交互仍需现场验收。没有证明语义服务完整联调通过。

## 保留的官方应用修复

原程序来自 [Pollen Robotics 官方 Conversation App](https://github.com/pollen-robotics/reachy_mini_conversation_app)，使用 HF Hosted 云端；不是自行冒充的完整助手。`install_voice_runtime.py` 是严格哈希锁定、原子替换、可回滚的收音修复：同步读取移出 asyncio 主循环，静音仍送零帧维持服务端断句，缩短采集积压并检测断流。安装或 `--rollback` 前必须停止旧应用；未知文件哈希拒绝覆盖。`install_voice_only.py` 是更早的无相机/动作适配，现有本地宠物程序不依赖它。

参考与实际使用：[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)、[SenseVoice](https://github.com/FunAudioLLM/SenseVoice)、[Silero VAD](https://github.com/snakers4/silero-vad)。研究过 [Pipecat Smart Turn](https://github.com/pipecat-ai/smart-turn) 的语义断句思路，尚未集成，不能把静音检测当成理解插话时机。
