# 啾啾宠物交互后端

独立 `pet_interaction` 包，保留原 `bridge`。默认 fake 输出，无麦克风、摄像头、模型、daemon 启动或设备连接；导入不加载硬件库。当前是有界规则行为闭环，不是通用语言模型聊天或照片理解已交付。旧眼镜按键照片、M5 短回应与共享记忆目标继续保留，未恢复 M5 心情/疲惫机制。

## 启动与停止

CPython 3.12，安装 `requirements-pet.txt`；测试另需 `pytest==9.1.1`。已有项目环境可运行：

```powershell
# 从该集成工作树根运行。令牌仅在当前进程环境，不写入Git。
$env:PET_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:PET_VISION_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python -m pet_interaction --port 8091
```

绑定固定回环地址，先取得跨端口/工作树进程锁并独占监听端口，再进入生命周期；第二实例即使更换端口也会失败，不触碰设备。Ctrl+C 只关闭本实例任务、自己的动作执行器与连接，不停止其他 daemon/语音服务。不运行旧 `start.ps1`（它可能另启动 daemon）。

显式 `--enable-devices --enable-motion` 才构造 live 动作执行器；动作映射仍需动作负责人逐项 `approved:true`，默认全部未批准，服务不改批准状态。仅 `--enable-devices --voice-url http://127.0.0.1:7860` 可接语音owner，动作仍dry_run；该订阅会关闭语音侧本地自动确认声，必须在 owner 交回联调窗口后启用。没有该参数不会访问7860。不得公开监听或代理这些控制接口。

闲置微动作当前关闭；rest 是行为静默，不调用实体睡眠。没有添加摸头传感器或移动底盘能力。机械语音不朗读中文；原转写仅用于短时规则判断，不写长期记忆。

## 生产者事件契约

`POST /v1/events`，`Authorization: Bearer <role token>`。`PET_VISION_TOKEN` 只能写 source=vision；`PET_API_TOKEN` 只能写 source=operator。语音事件仅从显式连接的语音 WS 接入，不向任意 HTTP 生产者开放 epoch 更新。

```json
{
  "schema_version": 1,
  "source": "vision",
  "session_id": "camera-process-uuid",
  "event_id": "source-event-uuid",
  "kind": "wave",
  "observed_at": 1790179200.0,
  "ttl_seconds": 3,
  "confidence": 0.7,
  "payload": {"basis": "hand", "confidence_basis": "configured_detection_floor"}
}
```

示例时间须替换为真实采集时间，不能用当前时间给旧帧续命。允许 TTL 0.001–30秒，未来偏差至多2秒，服务启动前事件拒绝。停止优先级最高；容量满也不阻止有效停止。事件ID在生产者会话内唯一，重复保留原ID；同ID改内容拒绝。有限缓存保留到事件过期，满时拒绝普通新事件，不淘汰仍有效的去重身份；服务重启从静默开始，不恢复排队输出。

vision wire kind 为 presence/wave/palm_stop；产品含义为 `hand_presence`（手部可见性）。presence 必须携带 `payload.present` 布尔值；`basis:hand`只代表手可见，不代表人体在场、人脸或用户身份。false只表示未见合格手。当前三类事件最低confidence=0.7；MediaPipe配置下限不是校准概率，稳定窗口由视觉owner实现。服务再次做TTL、乱序、去重与冷却（presence 10秒、wave 3秒）；稳定心跳仅续租不重触动作。缺失更新超过事件TTL变unknown/null，不能说人离开了。状态提供hand_presence与hand_visibility；present字段仅为兼容别名。

operator kind 为 stop/rest/wake；`POST /v1/stop` 是 operator 紧急停止入口。停止后保持安静，仅明确唤醒或新语音轮解除，视觉存在不自动解除停止。张掌停止同时请求语音owner的interrupt，使其自己推进epoch。

`GET /health` 为进程健康；带任一角色令牌读取 `/v1/state`、`/v1/decisions/{decision_id}`。accepted/scheduled/dispatched 不是设备完成；motion/voice 子回执及 `voice_receipt` 分别记录。当前决策缓存有界、不含原转写、原图或长期记忆，旧decision淘汰后返回404。

## 语音与动作装配

语音owner保持唯一session/epoch。连接 `/events`，先接收state快照，发送 `{"type":"subscribe","consumer":"pet-agent"}`；消费turn_changed、speech_started、turn_input final和output_status。支持当前 `turn_id` 整数并原样回传，初始空input_id不会被当成有效final。partial不触发输出；一个final只决策一次，无法绑定当前会话的迟到final拒绝。断连清动作且不自动重连，旧会话不重新激活。

语音回应走 `POST /api/agent-result`，原身份+response_id+semantic_id+`audio_mode=mechanical_only`+Unix expires_at。目前最多final之后2.5秒；HTTP200且accepted=false也记为拒绝。语义音色白名单由语音owner维护（ack/curious/happy/thinking/uncertain/sleepy）。`pet_interaction/rules.json` 明示唤名别称和命令：你好→happy、看这里→curious、停下/安静→取消动作声音、休息→静默等待唤醒、醒醒/唤名→关注、未知语句→uncertain且不动作，不声称理解复杂语义。称呼和标点仅在匹配副本规范化，stop/rest优先于wake；原转写不改写。

动作直接使用动作owner的 `pet_motion.MotionExecutor`：set_turn(opaque token)、submit(semantic,token,剩余TTL,request_id)、wait(request_id)、cancel/close。语音token取真实session/epoch；视觉token在独立命名空间，是动作取消上下文而非语音epoch。新语音和停止抢占视觉；不会绕过该执行器直接调用SDK。

## 验证与边界

```powershell
python -m pytest tests/test_pet_interaction.py tests/test_pet_interaction_process.py tests/test_pet_motion.py -q
```

测试仅用合成事件、fake动作和HTTP MockTransport。覆盖身份类型、TTL、重复冲突、容量、视觉乱序与存在状态过期、打断、迟到终态、最终转写重复、机械输出、角色鉴权、JSON重复键/超限、无设备导入。真实中文噪声识别、手势召回、动作形态、音频与摄像头共存仍由设备窗口验收，软件测试不能代替。

组合测试另见 `tests/test_pet_interaction_integration.py`：实际GestureEngine→规则后端→实际dry_run执行器，以及实际语音ASGI接口→内存PCM callback。后者需要独立测试环境中的numpy/sherpa-onnx/sounddevice，仅导入模块，不打开设备、加载模型或进入音频lifespan。可用`uv venv .runtime/pet-integration-env --python 3.12`，再按requirements-pet.txt加numpy==2.5.3、sherpa-onnx==1.13.8、sounddevice==0.5.6、pytest==9.1.1安装；不得将语音/视觉依赖强行同步进原生SDK环境。

Windows便捷启动为 `tools/run_pet_interaction.ps1 -Python <独立环境python路径>`；脚本仅在忽略目录`.runtime/pet-local-tokens.json`生成本机角色令牌，不显示令牌。视觉独立进程须读取该文件vision字段设置PET_VISION_TOKEN，不能使用operator令牌。脚本默认fake，只有显式EnableDevices/VoiceUrl/EnableMotion才启用对应出口。文件含本机凭据，不上传。

官方依据（2026-09-23读取）：[Conversation App](https://github.com/pollen-robotics/reachy_mini_conversation_app)以工具队列连接语音、视觉与动作；[SDK Quickstart](https://github.com/pollen-robotics/reachy_mini/blob/main/docs/source/SDK/quickstart.md)区分实机/模拟使用。这里只复用有证据的输入和队列分工，不宣称新增传感器。行为规则、独立epoch消费与防重放策略属于本项目实现。
