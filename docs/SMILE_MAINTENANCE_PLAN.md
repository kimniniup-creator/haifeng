# 笑脸声音闭环：唯一维护计划与当前边界

本计划由链路维护 owner 执行。2026-09-24 03:08声音/后端匹配部署已完成，
视觉启动仍未执行；本节运行记录取代此前“全部仅离线候选”的状态。
先做笑脸声音，不以电机跟踪误差修复作为声音验收前提。

## 当前运行检查（2026-09-24 03:08 +08:00）

声音与后端均来自main `f08f11e1417820d363f21a1737fd01099164bc06`。
旧后端通过已有operator shutdown正常退出；唯一声音owner替换已确认的旧声音
树，新声音在lifespan之前即保持原来的muted=true，随后启动匹配后端。

- 7860唯一listener38800（launcher46204），listening/error=null/muted=true；
  capture_age=16ms、capture_frames=2609、dropped_frames=0。
- 8091唯一listener45516，正式 `.runtime/pet-env`；voice_connected=true、
  proactive_connected=true、两link_error=null，跨越2秒复查仍保持连接。
  该进程到7860有两条Established连接，对应普通事件订阅与认证主动声音租约。
- 声音session为 `a3b66bf8-cc1e-43c7-8a5c-f4d867af0c10`，语义订阅已连接。
  声音入口从main导入，源码SHA256为
  `cf23cf7874486406d6896c75fadd249aec5a3c3c323cc0cf66a27b0d323e462c`。
- `HAIFENG_PROACTIVE_TOKEN` 从ignored `.runtime/proactive-audio-token.json`
  读取到两进程环境，未打印、未写命令参数。过滤后的本地快照位于ignored
  `.runtime/smile-service-deployment.json`，不含转写、原始音频或凭据。
- vision producer数量0；未重试被拒启动，没有发送视觉/试听测试事件。
  没有EnableMotion，未动原生daemon或扭矩。旧8088仍未更替。

这些检查证明匹配协议已在线及租约维持，不证明现场camera→smile→扬声器。
静音是维护前已有状态，已保留；现场可听环节需用户通过原声音界面正常解除
静音，再使用下述单次正常视觉入口。PID只适用于此快照，后续操作前重新核对。

## 已固定的软件组合

- Agent + 视觉 + 声音组合：`7db4d40e08e7d3d839e6c61602e94c21947ffe0b`。
- 视觉源：`fa36bab`；声音源：`0bd88b6` 加 exact-deadline 修复 `dbd8bd5`。
- 三条组合测试直接验证真实规则事件→Agent HTTP→声音 HTTP/WS→非零PCM/
  完成回执，以及讲话打断、连接断开后下一块静默。修复后相关51项通过。
- 这是合成系数与内存PCM验收，本轮组合测试不包含表情数据集评估或真人
  相机准确率，不支持把哭/闹理解为已识别情绪。独立组合QA已通过51+8项，
  见 `VISUAL_SOUND_QA_RESULTS.md`；现场验收仍未完成。

## 最少部署步骤（待获准维护窗口）

1. 先合并固定候选与独立QA证据，统一使用正式 `D:\海风` 的已提交代码。
   保存原声音/后端代码SHA和进程命令，确认端口7860、8091各只有一个实例。
   不改现有机械音色，不启动第二播放器。
2. 本地生成共享 `HAIFENG_PROACTIVE_TOKEN`，只放忽略目录/进程环境，在7860和
   8091各加载同一值，不打印、不放命令参数。不与 operator/vision token 混用。
3. 由唯一维护owner正常停止/替换声音和后端。声音沿原
   `patches/reachy_companion/pet_companion.py --models .runtime/voice-models`入口；
   后端沿 `tools/run_pet_interaction.ps1 -EnableDevices -VoiceUrl http://127.0.0.1:7860 -EnableVisualSounds`
   入口，保留motion dry-run，**不传 EnableMotion**。验证普通语音订阅及专用
   proactive lease均连接、采集新鲜、无错误。旧协议进程不能与新后端混用。
4. 视觉启动先前被自动审批拒绝，仍是现场闭环的明确阻塞。不能换shell/工具/
   owner绕过，也不能把本计划当作重新执行授权。只保留正常人工入口供之后
   的可观察维护窗口使用。模型准备脚本与本地推理可离线核验。
5. 未来获准启动时，唯一相机producer切到 `--mode face`，使用已校验人脸模型：
   `tools/run_pet_vision.py --mode face --provider pet_vision.ipc:leased_opencv_frames --continuous --send --model .runtime/models/face_landmarker.task`。
   `PET_VISION_TOKEN` 从本地既有token文件读入环境；不在命令行传值。
   保持官方media已释放，确认只一条相机reader链。不同时启动旧hand reader。
6. 现场逐点验收：稳定笑脸只响一次；持续笑不重复；回中性再笑且冷却后可再响；
   无脸/多脸/暗糊图不误响；用户开口抢占；断连/重启不重放旧事件。核对事件ID、
   decision及真实终态，再由现场听感确认可听，不拿HTTP200或PCM提交代替。

任一步生命周期被系统拒绝，记录动作与原始拒绝原因并停止该步，保留已运行
正式版本。代码可继续离线修改，不用反复重启试探。

## 用户回来后的单次正常入口

这段只供之后的正常人工维护窗口使用，**本轮没有执行**，也不是绕过先前
自动审批拒绝的备用启动器。先由维护owner完成上述声音/后端的匹配部署，
准备共享proactive凭据并核对官方media已释放。声音/后端部署现已完成；现场
需要发声时通过原声音界面解除静音一次。用户不用反复开关机器人。
若前置检查失败，先处理提示的维护缺项，不反复启动相机。

在 PowerShell 一次粘贴以下原有runner入口；不创建新服务或自动重连：

```powershell
Set-Location -LiteralPath 'D:\海风'
$ErrorActionPreference = 'Stop'
$smileTokens = Get-Content -LiteralPath '.runtime/pet-local-tokens.json' -Raw | ConvertFrom-Json
$smileVoiceState = Invoke-RestMethod 'http://127.0.0.1:7860/api/state' -TimeoutSec 3
if ($smileVoiceState.muted -ne $false) { throw '声音当前静音；在准备现场发声验收时，通过原声音界面解除静音。' }
$smileState = Invoke-RestMethod 'http://127.0.0.1:8091/v1/state' -Headers @{ Authorization = "Bearer $($smileTokens.operator)" } -TimeoutSec 3
if ($smileState.proactive_connected -ne $true -or $smileState.voice_connected -ne $true -or $smileState.stopped -or $smileState.closed) {
    throw '声音/后端的主动回应连接尚未就绪；先由维护owner处理，不启动相机。'
}
$smileModel = '.runtime/models/face_landmarker.task'
if ((Get-FileHash -LiteralPath $smileModel -Algorithm SHA256).Hash.ToLowerInvariant() -ne '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff') {
    throw '人脸模型校验失败；不启动相机。'
}
$smileExisting = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'run_pet_vision.py|run_pet_vision_camera.py' })
if ($smileExisting.Count) { throw '已有视觉reader；先由维护owner确认唯一实例，不重复启动。' }
$smilePreviousToken = $env:PET_VISION_TOKEN
try {
    $env:PET_VISION_TOKEN = $smileTokens.vision
    & '.\.runtime\vision-env\Scripts\python.exe' tools/run_pet_vision.py --mode face --provider pet_vision.ipc:leased_opencv_frames --continuous --send --model $smileModel --event-log .runtime/face-events.ndjson
} finally {
    $env:PET_VISION_TOKEN = $smilePreviousToken
}
```

启动后由维护owner核对一个producer/reader子树、fresh frame、face_presence或
visual_unknown得到后端回执；用户稳定笑一次、保持笑、回中性后等冷却再笑，
观察happy声音只在有效事件时出现。再试说话打断和退出后不补播。
事件/decision/声音终态与人耳听感都要核对；没有观测笑脸不能报告通过。

2026-09-24准备核验：正式vision-env依赖import通过；同一官方人脸模型已复制到
上述ignored路径，3758596字节/hash匹配；正式环境实际构造、空白图推理和close
成功，blank faces=0/quality=false，没有打开camera。默认pet-env原先缺失，已按
requirements-pet.txt准备并做仅import检查，未启动后端。现有旧声音/后端服务
随后已完成上述匹配换版；唯一已发生的执行拒绝仍是视觉producer启动。
更高分辨率研究不是前置。

## 与声音链并行、但尚未部署的动作维护候选

- 旧8088硬件门禁 `a52236e`：独立24+3通过；当前旧PID未替换，不能声称已禁用。
  正常维护只替换桥，不重启机器人，health必须明确返回false。见LEGACY_OUTPUT_GATE。
- 缓存遥测 `af70363` + 修复 `7f1de63`：独立17项通过，新增字段避免descriptor。
  已有native helper仍是旧版本。安装器会拒绝覆盖不同的现有补丁，这是预期保护；
  新helper只在后续有回滚与重载安排的单独维护窗口安装。当前不热改，不重启daemon。
- 桌面自动唤醒 `2e263d3`：源码/mock独立21+3通过，完整build/typecheck、桌面/
  窄屏视觉和真实Tauri首连/重连无写验收仍未完成。运行中桌面尚未更改。
- 原生no-wake启动参数只约束daemon，前端StartingView可另发enable/wake；之前
  “重开桌面不会唤醒”的判断已撤回。日志序列与前端吻合，历史客户端PID未证实。
- 关节跟踪最大约10.058°偏差未解决，不能由cached正常或HTTP200推定物理通过。
  所有未验映射保持false，不进行任何动作/扭矩试验。

历史现场恢复记录：用户手动重开后native PID41652、SDK1.8.0，新增只读GET已200；
随后声音和后端恢复连接，视觉恢复遭拒而停止。PID及状态只代表当时快照，后续
维护必须fresh核查，不照旧PID操作。恢复记录和软件候选不可混写成“整机已就绪”。
