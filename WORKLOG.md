# 海风工作记录

## 2026-09-23 接管
- 用户授权：在 D:\海风 管理项目，寻找产品气质并自主完成实现和交付；常规决策不逐项询问。
- 权威仓库：https://github.com/kimniniup-creator/haifeng （private）；upstream 保留 timesbye/Robot_glasses。
- 已推送初始化提交 4ed0dd4。继承上游 V2 c968c62；上游记录 E06-0055 / S3 / BT 1.4.9 / ISP 1.3.5 真机拍照成功。本机尚未复验。
- 本机观察：Reachy Mini Camera、Reachy Mini Audio 麦克风、CH343 COM11 可见；8000/8088 无监听。D:\海风 原有 MSI 保留且忽略。
- Python 3.12.13 独立环境建立，桥接依赖已安装。Reachy SDK 1.11.0 使用独立 reachy-env。
- 设计 Fable 调用因额度用尽失败；由总控继续收敛，不阻塞交付，不购买额度。
- 分工：硬件只读核查；backend 独立 worktree feat/haifeng-backend；总控负责产品、页面、机器人适配、集成和验收。
- 下一步：确认 daemon/音频、BLE 扫描；实现可靠队列和片段回顾体验；真实设备证据与模拟测试分开记录。

## 验收状态
- Git 远端恢复：通过。
- 真机新照片：待验证。
- 模型真实图像回答：待配置/验证。
- Reachy 真机运动和声音：待验证。
- 桌面/手机页面交互：待实现/验证。
- 20 轮稳定性：待验证。

## 2026-09-23 软件首版集成
- 完成独立审阅并将产品收敛为随时回顾片段，不声称每日习惯已验证。Fable额度耗尽，设计由总控定稿、Terra实现。
- 后端、Python BLE、UI工作分支已集成。取消/串行/归属/重启/设置持久化/Origin检查已修复。
- 19项测试通过；20轮为模拟。真实DeepSeek视觉请求与页面上传/回复/持久化通过。
- Reachy音频MME44100Hz软件输出通过，标记played_unverified；Daemon仍报No motors detected。眼镜现场未发现。
- 桌面/手机真实页面截图已检查，修复长状态挤压按钮、失败清空输入等问题。测试片段已通过应用删除。
- 全硬件交付尚未完成，详见docs/ACCEPTANCE.md及HANDOFF.md。

## 2026-09-23 官方音频接口复核
- 用户纠正：由总控继续接管机器人，子线程查官方接口/GitHub；暂停安装桌面客户端。
- 官方SDK 1.11.0的GStreamerAudio.play_sound已播放“痛痛飞走了”，明确定位Reachy WASAPI render GUID，收到EOS，无ERROR；这只证明软件播放结束，可闻结果仍待现场确认。
- 此前MME播放虽结束，用户明确反馈无声；不能称扬声器正常。Windows输出100%、未静音，语音WAV非静音。
- 子线程确认 --no-media 允许独立音频设备访问，并非直接播放无声的确定原因。PyUSB找不到控制接口，不等于USB Audio不可用；未更换驱动、刷固件或写DSP寄存器。
- 排查期间daemon由running转Motor communication error，COM11仍存在；已请求一次不唤醒重连，运动与音频分开验收。
- 官方来源：https://github.com/pollen-robotics/reachy_mini/blob/9d364df0d8b6c92fbda7a9252fc378e23d4ab47c/docs/source/troubleshooting.md
- 本次不唤醒重连后daemon恢复running、error=null；连接曾中断的原因未确定。

## 2026-09-23 可见官方接口测试任务
- 唯一硬件操作方；按官方SDK 1.11.0、本机OpenAPI和桌面官方源码固定commit整理 docs/REACHY_INTERFACE_MATRIX.md。音频MME与前次官方play_sound均被用户明确反馈无声，撤回旧“可闻待确认”表述：此前两次可闻验收失败。
- 本轮读取音频板成功，VERSION 2.1.2；Reachy输入/输出端点重新核验，双声道100%且未静音。官方SDK短时麦克风有非零样本；两声分声道音EOS仅为软件结果，等待现场反馈，未声称修复。
- no_media下官方REST play_sound/test-sound仍200但源码为空操作；release/acquire不会启用media。已在矩阵纠正。
- 触角+0.05rad、完成、取消UUID及空队列实测；额外等待后实际只变约0.0061rad，不通过到位验收，暂停扩大动作。恢复初始目标/disabled。
- daemon stop(false)/start(false) job done、状态stopped/running；SDK同位置task finished true；SDK普通查询fire-and-forget，不回响应是实现行为。
- 相机默认首帧近灰；MJPEG超时；YUY2原生调用阻塞，已仅停止专用探测进程。相机脚本添加25秒子进程超时；环境图像/录音未保存或上传。
- 未刷固件、改DSP、校准电机、重置、安装客户端或随机驱动、删除用户数据。眼镜不在本轮范围。
- 阻塞：无声仍需现场听感/断电检查连接；相机及电机到位未通过，详见矩阵；不无限重试。

- 收口检查：相机原生阻塞复测被25秒看门狗终止，确认不无限挂起；81个OpenAPI操作覆盖检查通过，4个脚本编译通过。8000/8088各单实例、队列空、disabled。Lucas本机attention-pet命令不可用，现场听感问题已在任务内提出。

## 2026-09-23 官方客户端安装与首次启动修复
- 用户明确要求打开官方软件，后续纠正应自主处理toggle/接口。已安装Reachy Mini Control 0.9.34，Windows管理员授权由用户完成。
- 纠正此前“窗口已打开即可用”：实际仍卡Installing Python runtime。日志明确bootstrap报 Missing expected target directory for Python minor version link；Python 3.12.14本体可执行，uv 0.12.18与本机0.11.24均复现，不能断言仅新uv回归。
- 在客户端自身数据目录用Python绝对路径创建此前不存在的.venv/apps_venv，安装SDK依赖。重开客户端后官方trampoline按内置规则将自身两个环境对齐到reachy-mini==1.8.0，进入USB连接/GStreamer首次预热。项目D:\海风\reachy-env的1.11.0不变。
- 旧8000 daemon已被客户端自身清理；客户端是唯一硬件daemon控制方。后续接口控制必须先核验当前版本与端点，不照搬1.11矩阵作为1.8运行结论。
- 最终验证：完整退出客户端清理媒体残留后重启，UI实际进入Ready / USB，App0.9.34 / Daemon1.8.0，WebRTC DataChannel connected。相机UI仍显示无法播放媒体；扬声器100%不代表可闻已通过。启动初始化问题已解决，不宣称所有硬件正常。用户操作期间UI出现Wake up animation且电机enabled，本轮没有主动下发wake_up或扩大运动。

## 2026-09-23 官方表情自动返回修补
- 证据：官方1.8.0 recorded接口无进入插值/结束返回，原生play_move忙时静默忽略；本地录制表情首尾姿态不同。
- patches/reachy_expression 增加完整单段事务、测量起姿返回、409重复请求保护、取消前后释放、故障中止和到位检查；只修改官方客户端自身recorded接口，有原文件备份及版本/哈希锁定回滚安装器。
- 官方实际SDK环境11项测试通过，包括原生播放循环和安装后路由（假硬件）；补丁已安装并重启客户端，未宣称实机通过。
- 07:41:58 UTC尚未发送表情即再次出现DoA USB Pipe error、相机中断、全部电机读失败；后台error，UI状态不能信。已请用户断电插牢供电及USB、尽量直连，等待物理重连后继续。未校准/固件/重置/强制复位，未启动第二daemon。
- 后续：用户完成物理重连；官方updater在07:42将两个客户端环境升级1.11，覆盖首轮补丁。保留新版，按同一router哈希适配1.8/1.11，新增1.11原生stop flag兼容；12项测试通过，重新安装重启，安装helper与源码SHA256相同。
- 实机小幅验证：要求+0.05rad，实测+0.0276117rad，目标偏差0.0223883rad超过本次0.015rad验收门槛；返回起点编码器值一致。未扩大动作、未做连续完整表情验收。末态running/ready/enabled、error=null、nb_error=0、队列空。精度不达标不能直接判定硬件损坏；语音未回应因客户端暂无对话应用，已向用户说明。
- 收口新增限制：后台/api/daemon/status和/api/state/full均200且真实running/ready，但客户端窗口仍停Connecting/Healthcheck，Ctrl+R后未恢复；日志有远端TURN/HF/updater网络超时或TLS错误。不能把后台恢复等同界面可用；本轮不再反复重启硬件。Git默认TLS推送失败两次后，以单次http.version=HTTP/1.1成功推送e616040，未关闭证书校验或修改全局Git配置。

## 2026-09-23 安装中文情感陪伴助手
- 用户明确要求安装HF情感相关语音助手。比较后选择官方reachy_mini_conversation_app 1.0.1，HF snapshot ddc309630448a664b0283812ff80048c36966c35；不宣称存在已验证的绝对最佳排名。
- 官方安装job done，安装在客户端apps_venv，SDK保持1.11。中文海风人格、Vivian、zh转写、HF Hosted，未添加付费API key。config/conversation与tools/configure_reachy_companion.py可复现非秘密配置，官方人格解析和重复执行通过。
- 首次正常启动再次相机错误+电机全部失联，app error。停止/无唤醒重启daemon后释放媒体，安装严格哈希、可回滚voice-only适配；不启用相机/动作循环/语音摇头。软件仍可接受其他控制方动作，不能称硬件问题解决。
- 第二次启动running；08:07:30 UTC HF实时session initialized，Vivian/haifeng。UI Hosted/Ready/Connected、麦克风开启，主页Listening/Ready；日志有音频增量，一次首段853ms。浏览器页面已保留给用户。询问实际中文可闻回复，尚待回答；不把音频数据当实体扬声器验证。
- daemon真实running/ready/error=null/nb_error=0；先前动作精度失败仍未解决。未启用开机自启动。配置解析与Python语法检查通过，现有表情补丁仍保持安装。

## 2026-09-23 接口地址 / 语音条件 / 情感映射专项
- 交付物为 Word 记录，按用户指示直接提交到 upstream：timesbye/Robot_glasses，docs/Reachy_Mini_接口_语音_情感映射记录.docx，commit 63ae610，远端已核（49511 字节）。本地不另存副本。
- **推翻既往结论（no_media）**：daemon 现为 no_media=false、media available=true、motors enabled、控制环 30–32Hz、nb_error=0、error=null。此前「REST 200 只是 no-op」的前提不再成立，音频与媒体项需按新环境重测，不得沿用旧判定。
- **推翻既往结论（未装对话应用）**：官方 reachy_mini_conversation_app 正在 127.0.0.1:7860 运行（JSON-RPC ws://127.0.0.1:7860/rpc），HF 后端 connected，TTS 音色 9 个、当前 Vivian，人格 user_personalities/haifeng 为当前及开机默认。HANDOFF 里「未装对话应用」已作废。
- 新增端口面：daemon 另在 0.0.0.0:8443（GStreamer WebRTC 信令）与 0.0.0.0:7860（对话应用）监听，非仅回环。旧 README 只约束 8000，需补防火墙约束。
- 官方素材实测：情绪库 pollen-robotics/reachy-mini-emotions-library 85 个动作（84 个自带 .ogg，仅 waiting 无音，时长 2.14–19.76s）、舞蹈库 19 个，均已在本机 HF 缓存。
- 实机实测：yes1 播放产生真实动作（右触角 0.2577 rad ≈14.8°，头部 z ±24mm）；laughing1 与其 .ogg 并发调用跑通，补丁自动复位残差 ≤0.025 rad / ≤2mm；全程 daemon error=null、nb_error=0。
- 实测 POST /api/media/play_sound 固定阻塞 2.65–2.83s 且与音频长度无关（11.78s 的 curious1.ogg 同为 2.71s），是 GStreamer 建流开销；做 A/V 同步必须补偿。
- **自身补丁两处缺陷（实测）**：(1) ReturningMove.__init__ 用 np.nextafter(move.duration,0) 求末态，而 duration=len(trajectory)*dt 可能略大于 timestamps[-1]，导致 confused1/displeased1/furious1/inquiring3/laughing2/proud1/proud3/tired1/welcoming1 共 9 个动作恒返回 500（welcoming1 duration=3.4600000000000004 > last_ts=3.46）；(2) ReturningMove.sound_path 写死 None，使 84 个情绪动作的配音全部不播。两处均为一行修法，已写入文档，未动手改——见下条。
- **阻塞（最高优先级，推断未验证）**：C:\Users\12246\AppData\Local\Reachy Mini Control 目录已从磁盘消失，但 daemon(38256)/对话应用(39340)/helper(36616) 仍从该路径的内存镜像运行。Program Files 安装体仍在。推断重启客户端或电脑后该环境（含补丁）会丢失，需重走 bootstrap。因此本轮不关客户端、不重装补丁，先报告。
- 仍待用户现场确认：扬声器可闻性。本轮已发 impatient1.wav / count.wav / wake_up.wav 及情绪配音，均 200；EOS/200 不是可闻证据。
- 原始响应在 .runtime/：emotion-move-probe.json、emotion-move-probe2.json、emotion-move-validation.json、emotion-with-sound.json、guard-transition-math.json、conversation-app-rpc.json、conversation-app-tools.json（不进 Git）。

## 2026-09-23 《带上她的眼睛》PRD 讨论
- 依据用户新方向编写 docs/带上她的眼睛-PRD-v0.1.md，家中实体为 Reachy Mini，外出反馈由随身 M5 承接。
- 已读取本机 forbetter 的陪伴契约及气质画像，未读取私人记忆。用户确认手机可只提供热点。
- 已确认本仓库 main、origin 为 kimniniup-creator/haifeng、PRIVATE；本轮不另建项目、不改运行程序。
- 已委派唯一 M5 硬件子任务，用户随后授权 S3 真机检查；输出证据待整合。不以串口枚举或上游规格宣称真机输出成功。
- 子任务最终识别为 M5StickS3 K150，与 reading-pet 现有构建对应。显示驱动报告 135×240/ready；600ms 短音请求从 started 到 completed，现场可闻未确认。没有内置震动；未刷机，尚不能显示新的照片回应。结果已并入 PRD 和真机报告。

## 动画脚本首稿
- 用户要求子任务先试写皮克斯式动画、小王子与玫瑰故事。创作简报与60秒脚本已完成，主任务已审看全部分镜、对白及产品真实性边界。
- 主线用围巾串起出发照顾、月亮云影与远端回应；明确手按眼镜腿，M5仅反馈。不生成视频、不刷设备。脚本供讨论，非制作定稿。
- PRD与最小事件协议已按眼镜腿唯一入口、外接震动偏好、唯一固件owner更新并推送54604a3；后续固件调研由M5总控负责。

## 2026-09-23 22:48 Reachy 原生客户端启动修复
- 修复原生 .venv/apps_venv 缺少 haifeng_expression_guard；之前 Codex AppData 隔离副本造成导入检查假阳性。已通过本机 UNC 路径验证原生日志和文件。
- 客户端重试已越过 ModuleNotFoundError，8000 单个 daemon 运行，电机配置检查通过，控制循环 nb_error=0。原生 SDK 为 1.8.0；隔离副本为 1.11.0。
- installer 改为原子替换，避免修改 uv 共享硬链接；新增显式 site 和确切旧补丁恢复。12 项 guard 测试和 1 项硬链接回归通过。
- 系统 Python 防火墙弹窗暂阻 UI 验收，已请用户处理；未发送动作，未修改防火墙。
- 22:52 最终原生 UI 验收：防火墙提示已消失，官方客户端主界面 Ready，摄像头有画面；daemon 持续 running/error=null/nb_error=0。启动崩溃修复验收通过；动作模式未验收。旧对话 app 的两组父子进程仍存在，7860 唯一监听 PID 39340，本轮未中断其会话。

## 动作映射入口与清单
- 按Kim要求拆分可见动作/语音任务，现有Agent任务保持决策与记忆owner；登记PROJECT_CONTROL。
- 当前daemon只读列表成功返回85情绪和19舞蹈，完整ID及首批候选对应落在docs/REACHY_ACTION_CATALOG.md。本轮未触发动作。

## 动作目录范围纠正
- Agent owner回传Kim截图DANCES(34)。原85+19目录仅REST recorded dataset，不能称全机器人动作目录。已在目录顶部纠正并交动作owner核对34入口/ID/调用路径；尚未确认该界面是否使用Conversation App AVAILABLE_MOVES。

- 34入口核对已完成并由总控复查源码/两库GET：20官方+14音乐，33项已枚举，headbanger_combo缺失；统一REST recorded路径。完整对照整合进REACHY_ACTION_CATALOG.md，未播放动作。

## 跨主机动作与表情接口交付
- 用户要求全部同步GitHub用于另一台主机映射，明确表情也要推。新增docs/reachy-mapping，包含121行机器可读目录（85情绪+35已枚举舞蹈/音乐+1缺项）、当前动作/状态OpenAPI子集、WS事件与停止契约、跨主机连接边界。
- 校验唯一键、85情绪、34界面舞蹈、120 listed和schema递归引用通过。未推密钥/IP/原始日志/媒体；未发送动作或修改网络。

## Voice delivery — 2026-09-24
- Isolated codex/voice-response now includes local SenseVoice/Silero WASAPI runner, 啾啾 name and original mechanical calls; old HF app stopped. No daemon/camera/motor/personality/memory edits.
- Session/turn/epoch/input identity is checked at inference completion, output enqueue and audio callback; one final/response per turn, TTL, stale/duplicate rejection. Agent WS subscribe disables local acknowledgment; semantic backend integration remains separate.
- Focused 26 tests and repository 19 tests passed. Desktop/mobile visual and control QA passed. Synthetic Mandarin ASR 453–609 ms; one speaker endpoint loopback interruption tail 47 ms. This is not a claim of physical audibility or full conversational acceptance.
- Runtime environment and models are ignored in D:\海风\.runtime. Local UI http://127.0.0.1:7860/. Run/rollback/contract documented in patches/reachy_companion/README.md. Raw audio/private memories not committed.

### Voice transport recovery follow-up — 2026-09-24
Independent QA found that a failed WebSocket send removed only the event client, leaving its Agent subscription active and disabling the local acknowledgment indefinitely. Unified cleanup now removes both identities, updates connected state and closes the failed socket with a bounded timeout. Added send-failure, send-timeout and remaining-subscriber regressions: all 29 focused tests pass without opening hardware. Runtime restart is coordinated with the owner because audio testing window has already been returned.

## Proactive visual audio — 2026-09-24
- Independent worktree codex/proactive-pet-audio based on origin/main 6ecdcfc; existing production voice untouched.
- Authenticated lease-bound visual short sound transport; no fake ASR final, no new player or sounds. Existing gate reused with non-consuming proactive responses.
- New observations only, 2s event TTL, 1.5s heartbeat expiry, 8s cooldown, voice/quiet/capture priority; callback rechecks lease and activity. Physical AEC and natural onset guarantees are explicitly not claimed.
- Contract in patches/reachy_companion/PROACTIVE_AUDIO.md. Offline no-device tests cover stale, expiry, mute, disconnect, cooldown, pre-VAD activity, response receipts and original behavior. Pending independent QA/integration; no live restart or playback authorized in this implementation phase.
- Independent QA found exact-deadline playback still allowed one block with strict greater-than comparison. Enqueue, callback expiry and reason selection now use >=. Two exact-deadline regressions added; all 49 no-device voice tests pass. No deployment.

## Stable smile integration candidate — 2026-09-24

- PR11 combines face source fa36bab, proactive audio source 0bd88b6 + dbd8bd5,
  and Agent visual policy/real HTTP-WS adapter. Fixed smile code 7db4d40; later
  candidate 624ec3b adds previously accepted maintenance diagnostics and records.
- Three real-protocol combination tests: stable FaceCueEngine cue reaches nonzero
  PCM and completed receipt; speech/lease disconnect stop subsequent buffers.
  Related fixed suite 51 passed; existing interaction integration 11 passed.
- Legacy gate independent24+3, cached gate independent17 accepted; local cached
  helper/installer integration13 passed. Desktop source gate accepted21+3 only;
  full build/visual/Tauri remain pending. No production services were changed.
- Main current outcome still awaits independent combination QA and supervised
  live camera/audibility. Vision startup's previous automatic policy rejection
  remains recorded; no retry through another tool. Use SMILE_MAINTENANCE_PLAN.md.

- Final offline combination QA closed at source162c9c3: independent51+8 pass,
  tests/report imported without unrelated QA branch history. This supersedes the
  pending independent review line above. Supervised live acceptance remains pending;
  no deployment or hardware access was performed during the implementation turn.

## Authorized runtime maintenance — 2026-09-24 03:08

After explicit coordinator authorization, replaced old backend via its operator
shutdown, handed the sole voice owner its maintenance window, then launched main
f08f11e backend with EnableVisualSounds and without EnableMotion. The voice owner
preserved original mute before startup. Verified unique38800/7860 and45516/8091,
voice+proactive subscriptions true, errors null, heartbeat alive beyond2s, capture
fresh/dropped0. No test playback or visual event. Camera remains stopped; denied
producer startup was not retried. Source/runtime/one manual-entry evidence recorded
in SMILE_MAINTENANCE_PLAN; physical perception/audio acceptance still outstanding.

## Upstream photo Agent deployment — 2026-09-24

Imported upstream b078189 local_agent and emotion contract into an isolated branch.
Windows Python 3.12 environment installed with upstream tested constraints. Real E06
capture and DeepSeek Flash photo analysis succeeded via explicitly configured JSON
mode and thinking disabled. Added scene-response emotion evidence and deterministic
head-gesture mapping, none/low-quality suppression, local Python BLE adapter and
mobile layout fixes. 41 tests passed. Desktop/mobile screenshots inspected; no JS
errors or horizontal overflow. Deployment details: local_agent/DEPLOYMENT.md.
Physical execution remains blocked by native ready export plus ~10-degree joint
tracking discrepancy; native runtime untouched and shared motion owner notified.

Follow-up: Kim oriented E06 and authorized a new capture. Model saw a person holding
a playing card; scene response curiosity. Removed blanket limited-quality suppression
when evidence exists and no recapture is needed. Same-photo image job independently
confirmed curiosity -> roll6deg -> neutral, with ROBOT_NOT_READY clearly displayed.
55 regression tests plus one independent motor-gate test passed. Hardware motion
remains disabled independently of future daemon readiness repair. Single PID45980
listens on loopback8765; screenshot QA refreshed for the actual second scene.

## Photo emotion to robot motion closed end to end — 2026-09-24

Kim authorized small physical validation, so the last leg of the upstream photo
Agent is now proven rather than gated. Root cause of ROBOT_NOT_READY was the
readiness predicate, not the robot: native daemon 1.8.0 never refreshes
backend_status.ready, while state=running, motors enabled, error null and the
control loop ran at 32Hz. Readiness now falls back to live control-loop evidence
and reports backend_ready plus ready_basis separately.

Evidence: authorized single segment commanded 3 degrees pitch (0.052360 rad) and
measured 0.052604 rad with move_started then move_completed. Two full runs from a
real E06 photo produced curiosity with visible evidence, mapped head_gesture
[[0,6],[0,0]] and motion completed via daemon_move_events. 63 tests pass.

Added an explicit ROBOT_SPEECH_ENABLED gate, default true upstream and false on
this machine, because robot.play calls /api/media/acquire and would take the
daemon audio lease from the voice owner on 7860. Speech reports suppressed, not
failed. Precision, audibility and wider emotion coverage remain unaccepted.

Operational note: VS Code restarted at 04:12 and took down every service parented
to its old terminals, including the Reachy daemon on 8000, voice 7860,
pet_interaction 8091 and legacy bridge 8088. The photo Agent survived because it
was relaunched detached through Win32_Process Create with the new
start_detached.cmd; the first two end-to-end runs were recorded before that
teardown.

Daemon recovery: launching the official Reachy Mini Control client brought up its
window but no daemon and no listening port for about nine minutes, so that client
was closed again and the daemon was started directly with the command line the
client itself had used. The stored command line carries a \?\ extended-length
prefix that cmd mangles into a relative path; the plain path works. The daemon
came back in about 20 seconds with state running, motors enabled, 32Hz control
loop and backend_status.ready still false, which is the same stale field the
readiness fix handles. A third full run on the restored environment completed in
19.1s: curiosity -> [[0,6],[0,0]] -> motion completed, residual roll +0.003 rad.
Voice 7860, pet_interaction 8091 and legacy bridge 8088 belong to other owners
and were deliberately not restarted here.

## 2026-09-24 客户端 DAEMON_TIMEOUT 排查
- 现象：官方客户端显示 Connection timed out / DAEMON_TIMEOUT / connection: usb。
- **机器人与 daemon 本身健康（实测）**：/api/daemon/status 返回 state=running、error=null；/api/state/motion-diagnostics 返回 stable_read=true 与真实 7 关节编码器值；控制环 32.7Hz、nb_error=0；COM11 存在且被 daemon 正常占用；近一小时 Windows 事件日志无任何 USB/CH343 断连。
- **`backend_status.ready=false` 与 `last_alive=null` 是 1.8.0 的上报缺陷，不是故障**：1.8.0 的 RobotBackend.get_status() 只刷新 error 与 motor_control_mode，从不写回 ready/last_alive（构造值 False/None）；1.11.0 的同一函数才有 `self._status.ready = self.ready.is_set()...`。不要据此判定后端未就绪。
- 客户端就绪判据（源码 useDaemonLifecycle.ts，commit f520136）只有两条：/api/daemon/status 的 state==='running'，且 /api/state/full 返回 200。10:07:16–10:08:18 连续 40 次采样两者全为 200。目标地址为 http://localhost:8000，本机解析正常。
- UI 状态条里的 CAUSE 行不可信：源码注释说明它是「从启动日志里提取的最近一条像错误的行」，本次挑中的是一条 INFO（central_signaling_relay setPeerStatus）。
- 曾存在 daemon 重启循环：10:03:43 与 10:06:07 各观测到一次干净退出（退出前 state=running、error=null、nb_error=0，无任何错误），端口空约 20 秒后由客户端重新拉起，周期约 55–60 秒。当前 PID 3420 已连续运行超过 150 秒，循环已停。判断为客户端启动重试耗尽后停在错误页，daemon 侧无过错。
- 排除项：系统代理 ProxyEnable=0 且绕过 127.*；HuggingFace 0.4 秒可达、数据集缓存完好（--preload-datasets 不阻塞）；scripts/avast_ssl_fix.py 是 Pollen 官方自带的 SSLKEYLOGFILE 清理包装，非异常；health-check 3ms、status 4ms，远低于客户端 2000ms 超时。
- **昨夜 AppData 目录丢失的连带损失已坐实**：目录于 2026-09-23 22:21 重建，.reachy_mini_spec 钉死 reachy-mini==1.8.0，故 SDK 由 1.11.0 退回 1.8.0（接口 81→68 个）；apps_venv 内只剩 reachy_mini，**对话应用 reachy_mini_conversation_app 已不存在**（7860 不再监听）；表情补丁随旧目录一并丢失。HF 缓存不在该目录，未受影响。
- 未做：未重启客户端、未杀 daemon、未改 .reachy_mini_spec、未重装补丁、未启用电机或下发任何动作。

## 2026-09-24 绕开客户端：自有 daemon + 对话应用 + 人脸记忆
- 用户指示：不走官方客户端，找最短路径实现表情映射；随后要求恢复语音助手、保留英文 default 人格（音色 Aiden）、删除海风人格、并让摄像头记住人脸与声纹。
- **自有 daemon 跑通**：reachy-env 1.11.0，media 开启，`ready=true`、`error=null`、`nb_error=0`、控制环 32Hz、电机 enabled。新增 start_robot_media.ps1（相对 start_robot.ps1 去掉 --no-media）。
- **表情映射实测通过**：原生路由无补丁，welcoming1 不再 500。laughing1 实测轨迹真实：触角在 0.17↔0.37 往复、body_yaw 变化 0.164 rad、头部 z 起伏 10.8mm，总幅度 0.336 rad；触角读数回到 [-0.3,0.5] 正常区间（此前 ±2.9 是未唤醒状态的异常值）。
- **摄像头首次验证通过**：get_frame_jpeg 连续出帧，1920×1080，均值 56.3 标准差 41.3，肉眼确认为清晰真实成像（此前多轮只拿到近灰帧/超时）。
- **音频验收闭环**：官方对话应用实时对话中，麦克风转写与 TTS 播放均正常，首个音频 delta 在用户转写后 930ms。扬声器可闻性问题就此解决，不再是待验证项。
- **对话应用脱离客户端运行**：从 HF 缓存的 Space 源码装入独立 conv-env，start_conversation.ps1 启动，UI 127.0.0.1:7860，JSON-RPC ws://127.0.0.1:7860/rpc。复用本机既有 HF token（未回显、未提交）。
- 人格：按用户要求保留内置 default（英文，音色 Aiden）。海风人格已按指示删除（conv-env 内、conversation/external_content、以及 config/conversation/haifeng 全部删净），.env 中 REACHY_MINI_CUSTOM_PROFILE 已移除，startup 现为 default。
- **新增 bio_tools/face_memory.py**：官方外部工具机制（REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY + AUTOLOAD_EXTERNAL_TOOLS）。YuNet 检测 + SFace 识别，均走 opencv-python 内置 API，模型来自 HF 的 OpenCV Zoo 官方镜像。支持 enrol / identify / list / forget，录入取 7 帧平均，余弦阈值 0.363（0.28–0.363 报"不确定"而非猜名字）。只存 128 维特征到 data/face_db.json，不存照片，不出本机。
- 离线验证：在真实抓拍图上检测到 1 张人脸、对齐 112×112、128 维归一化 embedding、自相似度 1.0、随机向量 0.173。应用侧日志确认 `Loaded external tool: face_memory` 且已进入实时会话工具表。实机语音录入待用户验收。
- **声纹未做**：整个栈内无说话人识别能力，音频只有 DOA 与 VAD；且麦克风被对话应用独占，需另起采集通道与说话人 embedding 模型。已向用户说明，等确认后再做。
- 未动：官方客户端未重启（当前未运行）；patches/reachy_expression 保留未安装（客户端旁路后不生效）。

## 2026-09-24 VAD 修复 / 眼镜常驻链路 / 手势交互
- **对话应用"不说话"根因**：日志显示每 0.5–4 秒一次 `User intervention: flushing player queue`，嘈杂会场的环境噪声持续触发 VAD 打断，机器人每次刚开口就被掐断。上游把 `turn_detection=ServerVad(type="server_vad", interrupt_response=True)` 写死且未设阈值。新增 patches/conversation_vad/apply.py（幂等、带 .orig 备份与 --rollback），改为读环境变量，默认 threshold=0.85 / prefix_padding=300ms / silence=900ms / interrupt=off。重启后打断次数 0。代价：不能中途插嘴打断，用 REACHY_VAD_* 可调。
- **眼镜常驻链路**（bridge/luma_daemon.py）：LumaSession 持久连接 + 自动重连退避，AA14/AA15 订阅常驻。实测 E06-0055（D8:53:65:00:00:55）链路建立 9.5s，此后单张 **2.1s**（原 luma_ble 每张都要重新扫描/连接/握手）。握手全部有回应：型号 S3、电量 98%。
- 自查修掉一处自己引入的竞态：run() 循环与 capture() 同时消费 file_updates 队列，导致通知被后台循环吃掉、capture 必然超时。改为 run() 单一消费者，capture 挂 future 等待；未请求而到达的文件走 on_image 回调。
- `listen` 子命令用于实测眼镜自己按快门时是否主动推文件——这是固件属性，代码侧已经能同等处理，待现场按快门验证。
- **手势交互**（bio_tools/gesture_watch.py）：MediaPipe GestureRecognizer（models/gesture_recognizer.task，8.4MB，不进 Git）在后台线程按 10Hz 取帧，复用对话应用自己的 MediaManager，不与摄像头争用。
- 挥手判定为时序特征而非静态姿势：2 秒窗口内手腕 x 方向反转 ≥3 次、总行程 ≥0.10（归一化）、且过半帧为张开手掌。离线用例四项全对：挥手 True；静止 False；单向伸手 False（反转 0）；握拳挥动 False。检出后 6 秒冷却，并直接 REST 播 welcoming1 回应。
- **头部跟手**：用 SDK look_at_image(u,v,duration=0) 走 set_target 流式下发，增益 0.6（只偏向手、不追到画面边缘），EMA 平滑 0.45，死区 0.015；手消失即清空平滑状态避免重新出现时甩头。启用跟手时自动关闭 daemon 人脸跟踪，否则两者抢同一组关节。
- 数据集结论：挥手不需要数据集与训练。若要扩手势词表，HaGRID（静态 18 类）在 HF 有多个镜像；动态类（Jester）需单独获取。已向用户说明。
- 工具启用需带 Origin 头调 RPC（应用对 WebSocket 有 Origin 校验，否则 403）。face_memory 与 gesture_watch 均已在 default 人格启用并进入实时会话工具表。
- 待用户现场验收：挥手识别、头部跟手、人脸录入；眼镜快门主动推送。

## 2026-09-24 接入 9527 中转（gpt-5.6-sol）与眼镜→Agent→Reachy 闭环
- 用户提供 newapi 中转（https://9527.codes）与 key，要求把 Reachy 的后端回答模型换成 gpt-5.6-sol。凭据写入项目 .env（已被 gitignore），未回显、未提交。
- **授权检查通过**：/v1/models 返回 200、53 个模型，gpt-5.6-sol 存在；chat/completions 实测可用。
- **但 realtime 不可用（实测证据）**：模型列表中无任何 realtime 模型；连 wss://9527.codes/v1/realtime 中转虽接受连接，首帧即返回 `dial failed to wss://***: websocket: bad handshake`。对话应用走的是 OpenAI Realtime 协议（语音进语音出 + 服务端 VAD + 工具调用），因此**语音后端无法直接替换**，已向用户说明并给出取舍。语音侧仍用 HF realtime。
- **Cloudflare 1010 坑**：带图请求被拦，纯文本不受影响；根因是默认 urllib User-Agent。改用 openai SDK（自带 UA）后恢复。已写进 scene_agent 的模块注释，避免再踩。
- **gpt-5.6-sol 视觉可用**：真实抓拍图 4.4s 返回准确描述。
- 新增 bridge/scene_agent.py：图片 → 结构化读数 {scene, emotion, intensity, confidence, utterance}。情绪词表固定 8 类，**动作映射留在代码里，模型不指定动作名**，换动作库不必改提示词。置信度 <0.5 不演绎，退回 attentive1。缩图上限长边 768/质量 78（619KB → 40KB）。
- 新增 bridge/glasses_pipeline.py：LumaSession 常驻链路 + scene_agent，串行化反应（间隔 ≥8s）。`once` 单次全链路，`run` 常驻（--interval 0 时只等眼镜主动推图）。
- **端到端实测通过**：眼镜拍照 7088 字节 → 分析 9.6–11.5s → 动作 HTTP 200 + 配音 HTTP 200。两次测试照片均偏暗模糊，模型 confidence 0.18，系统正确退回 attentive1 未硬演——置信度门槛按设计生效。
- 修掉 _sound_path 静默失败：.venv 缺 huggingface_hub 导致配音查找返回 None 而无报错。已安装，并增加不依赖该包的 HF 缓存路径兜底。
- 待现场验收：戴上眼镜对有内容的场景拍照的实际表现；眼镜自身快门是否主动推图（bridge.luma_daemon listen）。

## 2026-09-24 用户反馈三问的实据定位与修正
- 用户反馈：动作看不出针对场景、触角一直晃；它老听不到、不回应；人脸仍未记住。逐条查证据，结论与此前判断有出入，已修正。
- **触角一直晃 ≠ 我的手势模块**。实据：日志中 `Tool call received` 计数为 0，face_memory 与 gesture_watch **从未被调用过**，手势监视器根本没启动。真凶是上游 moves.py 的 `BreathingMove`：`antenna_sway_amplitude=15°`、`antenna_frequency=0.5Hz`、`duration=inf`，任何动作结束 0.3 秒后就无限摆动。idle_policy（3 分钟一次随机 Dance/PlayEmotion）是次要因素，不是持续晃的原因。
- **上一版 VAD 补丁没治到根，且矫枉过正**。打断由 huggingface_realtime.py 收到 `input_audio_buffer.speech_started` 后直接调 `_clear_queue()` 触发，与 `interrupt_response` 参数无关——所以关闭打断参数后仍有 50 次清空播放队列。同时 threshold 从默认拉到 0.85 过高，导致听不到用户说话。两个问题叠加：既听不见、又自己把话掐断。
- 旧 patches/conversation_vad 已回滚并删除，替换为 patches/conversation_tuning（同时改两个文件，各自 .orig 备份，带 --rollback）：
  - VAD 参数可配，默认 threshold 0.6 / silence 700ms / prefix 300ms（不再是 0.85）
  - `speech_started` 的清队列改为受 `REACHY_VAD_INTERRUPT` 控制，默认关闭——这才是真正堵住自我打断的地方
  - 呼吸动画可配，默认触角 ±4°、0.25Hz，z 轴 3mm；`REACHY_BREATH_ANTENNA_DEG=0` 可完全静止
- 补丁自身修掉两处：`import os as _os` 的锚点在 moves.py 不存在导致运行时 `name '_os' is not defined`（呼吸启动失败）；改为通用插入并跳过 `from __future__`（否则 SyntaxError）。已加运行时校验，避免"能编译但运行炸"。
- **实测验收**：重启后无报错，打断次数 0；触角摆幅由设计值峰峰 30° 降到实测 **6.1°**（12 秒采样）。情绪动作摆幅 17°+，现在可与待机动画区分。
- 人脸仍未录入的原因就是上面的"轮次被掐断"，工具从未被触发；两个外部工具在 default 人格下均已启用并在实时工具表中。待用户重试。
- 语音后端维持现状（用户确认）。注意转写语言锁定 en，用户若说中文会被转写成英文乱码。

## 2026-09-24 realtime 会话静默卡死与看门狗
- 现象：转写持续到达、WebSocket 保持打开、无任何报错，但助手不再产生任何回应。用户侧表现为"它不说话/不理我"。
- **实测寿命**：会话 11:01:51 建立，最后一次回应 11:06:48，存活 **4 分 57 秒**。接近 5 分钟整，符合托管 realtime 会话 TTL 到期而客户端未续期的特征；此前归因于自己的 interrupt_response 补丁，证据不足，已撤回该判断。
- 参数两难（实测）：`REACHY_VAD_INTERRUPT=0` 体验最好（转写完整、零打断）但会遇到上述静默卡死；`=1` 恢复上游行为后，嘈杂会场每隔数秒就 `Cleared player queue`，一句完整话都说不完。最终保留 0.6 + 不打断这组，另加自动恢复。
- **扬声器端点澄清**：`/api/volume/current` 返回的设备名是"回音消除话筒"，看似麦克风，实为驱动把 render 与 capture 取了同名。PnP 查询确认存在 RENDER 端点 `{0.0.0.00000000}.{68A77CCF-...}` 且 Status=OK。不是缺少扬声器。
- 新增 tools/conversation_watchdog.py：读应用自身日志，判据为"有用户完整发言（role=user content）但 grace 秒内无任何存活迹象（role=assistant / Turn latency / Tool call received）"，满足即重启应用。只有沉默不触发，避免安静时误杀。默认 grace 30s、轮询 5s、重启冷却 90s。
- 回放验证：对 conversation.wedged.log（未回应 432s）与 conversation.prev2.log（38s）均正确判定需要重启。已在后台运行。
- 用户判断当前转写方案不可行，要求调研成熟语音助手的唤醒/对话对象判定与上下文长度管理，已派子线程调研，结论待回。

## 2026-09-24 调研结论与唤醒词门控落地
- **中转不是 OpenAI**：config.py:69 指向 `pollen-robotics-reachy-mini-realtime-url.hf.space/session`，分配的是 huggingface/speech-to-speech 实例——VAD→STT→LLM→TTS 级联管线，只是对外说 Realtime 协议。据此修正此前多条判断。
- **静默卡死根因（撤回 TTL 判断）**：该中转 `api/openai_realtime/llm_proxy.py` 用 `httpx.Timeout(None, connect=...)`，读取阶段无超时。上游 LLM 一停顿，该 handler 永久阻塞；STT 是独立 handler 所以转写照常，`response_pending` 标志永不清除，`websocket_router.py` 既无 ping/pong 也无空闲超时，服务端亦无看门狗。OpenAI 自身上限为 60 分钟，故 ~5 分钟不是 TTL。
- **上下文长度无需处理**：中转 `runtime_config.py` 固定 `Chat(10)`，只保留 10 轮用户发言并按整轮淘汰（硬上限 2×size）。`conversation.item.delete` 未实现，`conversation.item.truncate` 是空操作。
- **落地：唤醒词门控**（调研排名第一的方案）。新增 voice_gate/wake_gate.py：openWakeWord 0.6.0（ONNX、CPU、无 torch）+ 自带 silero VAD 抑制误触发，1 秒预滚缓冲在开门时回灌以免吃掉首词，命中后保持 8 秒并随说话延长，支持 open_now 按键说话与 close_now。
- 拦截点选在应用自己的 `receive()`（huggingface_realtime.py:961，送 `input_audio_buffer.append` 之前）——音频已在手上，不必与应用争抢麦克风设备。任何异常一律放行原音频，坏掉的门控不能让机器人变聋。
- 离线验证：2 秒环境噪声 0/50 帧放行；预滚封顶 1 秒；强制开启按时自动关闭；唤醒后放行 16640 样本（预滚 16000 + 当前帧 640）。接入后实测会话正常初始化，未说唤醒词时用户发言条数为 0（此前同等时间会产生大量乱码转写）。
- patches/conversation_vad 已并入 patches/conversation_tuning，现含四项：VAD 参数、客户端打断开关、唤醒门控钩子、呼吸动画幅度。修掉两处补丁自身缺陷（`_os` 导入锚点、`from __future__` 必须置顶）。
- 仍待做（调研建议 1/2）：在客户端对 `speech_stopped` 后 10 秒无 `response.created` 做进程内重连并回放上下文，替代当前的日志看门狗进程重启；WebSocket 加 ping_interval。

## 2026-09-24 近场门控（免唤醒词）
- 用户反馈唤醒词方案不好用：它打完招呼后说话就被门控全挡，而 `hey bb` 这个词 openWakeWord 无现成模型。
- 在 wake_gate 增加近场开门：桌面机器人前说话的人比身后整个会场响得多，用"响度相对房间自身底噪的倍数"作为"这句是对我说的"线索，无需任何口令；唤醒词保留给远距离场景。
- 判据必须同时满足人声与响度：silero VAD 判定为语音，且 RMS ≥ 噪声地板 × 倍数（默认 3.0）。地板取最近约 30 秒 RMS 的 20 分位，且**只用非语音块学习**，否则一段长发言会把门槛抬到再也过不去。
- 离线验证（VAD 打桩以单独测响度逻辑）：底噪期放行 0 帧、地板 588；远处人声 2.9 倍 → 放行 0；近距离人声 6.8 倍 → 开门、放行 25 帧；地板未被人声污染仍为 588。白噪声测试不开门属正确行为（VAD 判定非语音）。
- 实机验证：`near-field speech (score 0.00, rms 1506 vs floor 142); opening uplink`，未说唤醒词即开门。
- 可调：REACHY_NEAR_ENABLED / REACHY_NEAR_RATIO / REACHY_NEAR_FLOOR_MIN。
- 澄清用户疑问：9527 中转的 sk- key 仅用于眼镜视觉链路（gpt-5.6-sol，已跑通）；语音链路用的是本机既有 HF token 指向的 pollen-robotics-reachy-mini-realtime-url.hf.space，两者无关。语音无法改用该中转，因其无 realtime 模型且握手失败，已实测。

## 2026-09-24 机器人重启后的断链与看门狗扩容
- 用户反馈"说英文也不理我"。实据并非语音链路：应用日志每秒刷数十条 `Failed to set robot target: Lost connection with the server.`，daemon 自身 `state=error`、`error="Motor communication error! Check connections and power supply."`。用户随后说明 Reachy 刚被重启过。
- 恢复动作：`POST /api/daemon/restart` → 约 6 秒后 `state=running`、`error=None`、`ready=true`；再 `POST /api/motors/set_mode/enabled`；重启对话应用重新接入。事后 `Lost connection` 计数归零，nb_error=0。
- **看门狗扩容**：原先只覆盖对话应用静默卡死，daemon 掉了它管不着——而 daemon 一掉，应用表现同样是"听不见、不回应"，重启应用毫无用处。现新增 daemon 优先检查：`state==error` 时先 `daemon/restart`，等待回到 running 后自动 `motors/set_mode/enabled`，再重启应用；带冷却避免抖动。
- 近场门控实机持续生效，多次记录如 `rms 2772 vs floor 120`、`rms 2015 vs floor 404`，地板随现场噪声自适应上浮。

## 2026-09-24 可对话性的量化自测
- 用户要求"必须听得懂英文、能完整流畅对话，自己测"。服务存活不等于能对话，故新建 tools/conversation_probe.py：用合成语音经门控注入通道送入（与麦克风同一条路径），等待"已提交转写 + 助手回复"，按轮报告成败。配套 tools/synthesize_phrase.ps1（SAPI，16kHz 单声道）。
- 门控新增注入通道（REACHY_GATE_INJECT_WAV + TRIGGER 文件），仅在配置时启用，用于绕开声学路径自测。此前用电脑扬声器外放的声学测试无效：默认播放设备疑似 Reachy 自身，被回声消除抵消，麦克风收不到。
- **修掉一个我自己引入的严重缺陷**：门控关闭时返回 None（完全不发送）。服务端 VAD 需要"听到静音"才能判定一轮结束，被我掐掉后它永远等不到结束——表现为只有零星 partial、永不提交完整转写、更无回应。改为关闭时发送等长静音帧，音频流保持连续。离线验证：200 帧全部为静音、无 None、帧长恒为 160。
- 另修：开门那一帧原本把 1 秒预滚与当前帧拼成 16640 样本的大包一次性上传，与平时 160 样本差异悬殊，可能扰乱上游 VAD。改为按正常帧大小逐帧吐出，关门时清空未吐完的队列。
- **修掉看门狗自杀**：restart() 用 capture_output=True 调用启动脚本，而脚本里 Start-Process 派生的子进程继承管道句柄，communicate() 永远等不到 EOF，120 秒后抛 TimeoutExpired 直接杀死看门狗——它在第一次真正救场时就死了。改为不捕获输出、超时视为已启动，并把整个循环体包进 try/except，保证看门狗比任何单次失败活得久。实测连续两次触发（12:23:21、12:24:58）均成功重启且自身存活。
- 看门狗新增两项：daemon 处于 error 时先恢复机器人后端并重新使能电机；以及"正在发送音频但中转完全无响应"的聋检测（原判据要求先有完整转写，转写整体停摆时反而不触发）。
- **实测结论（三次探测）**：0/4、0/4、1/3。唯一成功的一轮：问"蜘蛛有几条腿"，回答"Eight"，耗时 22 秒——链路本身是通的。失败集中在"完全未被转写"与"已转写但 LLM 级无回应"，与调研指出的中转 LLM 代理无读取超时一致。工具从 17 精简到 7 再恢复到 16，对成功率无改善，排除工具数量为主因。
- 按用户决定调整：新建 user_personalities/reachy_tuned（复制 default 全文与 Aiden 音色，不改人设），加入两条约束——web_search 默认不调用（除非用户明确要求查网），以及记忆为短期不可依赖；移除 idle_do_nothing；其余工具保留。看门狗每 20 轮助手发言清空一次 memory.v1.json。
- VAD 按"交互优先、暂不要求准确度"设为 threshold 0.2、允许打断、silence 600ms、近场倍数降至 1.8。

## 2026-09-24 按用户要求只保留人机沟通组件
- 用户指示：只执行人机沟通的组件，关闭人脸识别。
- 处理：不是仅在人格里禁用，而是把 AUTOLOAD_EXTERNAL_TOOLS 置 0 并移除 REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY，使 bio_tools 下的 face_memory 与 gesture_watch **完全不被加载**。重启后日志中两者出现次数为 0，"external tool" 相关行数为 0。人格文件 reachy_tuned 的 default_tools 同步去掉这两项，重启后不会复活。
- 当前工具表（16 项，含框架自带的 task_status/task_cancel）：play_emotion、stop_emotion、move_head、head_tracking、camera、dance、stop_dance、sweep_look、go_to_sleep、remember、forget、search_web、get_time、get_weather。
- 移除感知组件后重测：1/4（"What colour is the sky" → "Blue"，23 秒）。
- **四次探测累计 0/4、0/4、1/3、1/4 ≈ 成功率 2/15**。已排除的变量：工具数量（17→7→16→14 无变化）、VAD 参数（0.85/0.6/0.2 与打断开关组合）、门控实现缺陷（已修静音连续性与大包问题）、看门狗可靠性（已修自杀）。四轮探测中成功的两轮答案均正确、耗时 22–23 秒，证明链路本身正确，瓶颈在托管中转的 LLM 级。
- 结论：该托管中转无法支撑"完整流畅对话"，且不是本机可调好的。建议转本地 realtime 服务端方案。

## 2026-09-24 M5StickS3 随身分身：照片笑脸与互动（Kim 直接指派）
- 固件在 reading-pet 分支 feat/photo-reactions（独立 worktree D:\reading-pet-worktrees\photo-reactions），build photo-reactions-0.7，应用 SHA256 67240dee…a9604，仅 app 0x10000 写入；刷前整片 8MB 备份在该 worktree 的 .delivery/backup（NVS 与 character-shell-0.6 应用哈希均与记录一致，可原样回滚）。原角色精灵未改，只加姿态编排与周边特效。
- 眼镜链路：bridge/glasses_pipeline.py 每张照片发 photo_event received（快门闪白、拍立得卡片显影、角色好奇张望）→ 模型回复后发 replied（按情绪 delighted/love/wow/curious/gentle/neutral 表演，最后都会哈哈大笑）+ 中文短句气泡。scene_agent 提示词新增 line_zh（≤14 字），bridge/m5_link.py 负责 USB 串口与 24 字校验，超长不截断直接不显示。
- 本机互动：A 戳一下咯咯笑、连戳两下跳起、三下笑翻；长按 A 摸头冒爱心；B 重看上一条照片回复；摇晃会晕然后笑；侧倾会跟着歪；扣过来睡觉；2 分钟无操作打盹。长按 B 打开 9 张卡片的互动菜单，喂零食/一起跳舞/想念 Reachy 为占位预览，屏上标"即将开放"。
- 已验证（实机帧缓冲截图 qa-artifacts/m5，本地不入库）：照片时间线五帧、菜单与占位预览、真实眼镜存图经 gpt-5.6-sol → M5 显示"我还看不清呢"。截图靠 USB 注入手势驱动，已与实体按键计数分开；实体按键/摇晃/侧倾手感、眼镜实拍按快门到 M5 待 Kim 现场验证。
- tools/m5_screen.py：冻结动画时钟抓彩色截图、注入手势、跑照片时间线。
- 刷机坑：esptool 默认 RTS 硬复位会让 S3 停在 ROM 下载模式，需 `--after watchdog_reset`。
