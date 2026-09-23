# 宠物机器人基础交互独立验收

日期：2026-09-23起，最终软件审查2026-09-24。状态：最终固定代码软件可合，实体动作未通过；QA未执行实机。本文由独立 QA 单写；不修改实现，不占音频、摄像头、COM/BLE，不启动或重启运行服务。

## 最终软件合并结论

**[PR #4](https://github.com/kimniniup-creator/haifeng/pull/4) 固定代码 `32676f26ff9b7b064bb53916eb3bf09a02311832` 没有已知软件合并阻断，可以合主线，但不能开放实体自动动作。** 远端分支已核对为同一SHA。独立最终执行：

```text
python -m pytest tests/test_pet_interaction.py tests/test_pet_interaction_integration.py tests/test_pet_interaction_process.py tests/test_pet_motion.py tests/test_pet_motion_micro.py tests/test_pet_vision.py -q
107 passed, 1 warning in 42.12s
```

无skip；真实模型空白帧、真实模块ASGI与内存PCM组合均实际执行。唯一warning为Starlette/AnyIO弃用提示，未影响结果。测试在QA固定源码快照、隔离TEMP/TMP和自建Python3.12环境执行，未接生产8091/7860/8000或硬件。语音修复bc7effd另在干净语音环境29项通过；这些计数存在范围重叠，不相加冒充总用例数。

最终增量确认：保留原始observed_at/start_deadline；过期排队和预检零下发；开始后的执行预算10秒，上层wait_for也同步拆分；换轮/停止仍取消；缺失手部状态只变unknown，不误取消已开始动作。所有mapping和micro profile仍approved=false；默认fake，接真实语音时motion仍dry-run，默认不开camera、不另启daemon或音频服务。

合并后允许集成owner按总控授权只更新其8091服务；本QA不代为部署。仍未通过：微动作实机到位/保持（第二次probe失败），真人中文识别/连续打断与可闻结果、真人wave/palm_stop及最终反馈、音频摄像头持续共存。摄像头采到帧、语音订阅恢复均按owner转达单列，不能替代这些验收。眼镜实体键照片→M5→回家接续属于另一条仍待实现/联调的链路，不因本次软件通过自动关闭。

下文保留各固定版本的证据和修复过程；较早“待修/待复验”状态以上述最终结论及后续修复记录为准。

## 基线与证据口径

- 海风基线：`21a1747d375b63e54dcca451a837425a6a6fc1db`。
- QA 分支：`codex/pet-interaction-qa`；独立后台工作树。集成后由集成负责人纳入本文；保留工作树直到总控确认无需复验。
- 仓库当前为 PUBLIC。总控已转达 Kim 明确确认是本人设置并授权继续，覆盖旧 private 记录。本文不含私人输入、环境录音/影像、凭据或原始设备日志。
- 旧语音审查版本：`191c1aa936695e0cf4e2fae09a25a839554a1a4b`；只是旧音频恢复补丁和接口文档，不等于新中文 ASR/机械音实现。
- M5 最新转达基线为 reading-pet `b0c77f3` / `character-shell-0.6`，非旧 numeric-v2。此次不复核固件或扩展照片验收。
- 分开记录：静态审阅、mock 软件测试、真实进程/服务测试、现场硬件感知。HTTP 200、queued、SDK completion、rendered ACK 均不能单独证明动作到位、声音可闻或手势识别可用。

## 最小验收矩阵

| ID | 输入与故障 | 必须观察的结果 | 当前证据/缺口 |
|---|---|---|---|
| P01 | 合法语音/视觉事件 | 来源 session/event/turn 身份贯穿决策、唯一行为和执行 ACK；失败不报成功 | 最终32676f2软件组合及TTL接线通过；实体反馈未通过 |
| P02 | A 轮被 B 打断，随后 A 的 partial/final、模型结果、工具结果、音频迟到 | A 静默丢弃；B final 只执行一次；最后播放/执行边界仍检查原身份 | bc7effd及12150fc纯软件身份门/内存PCM通过；现场停止延迟未验 |
| P03 | presence 持续、wave 重复、左右手标签抖动、离开后重入 | 防抖和冷却有效；离开清理追踪；重入可重新识别；旧帧不变成新事件 | 71e4706合成关键点/空白模型及12150fc组合通过；真人手势未验 |
| P04 | 普通动作执行中、队列非空时收到 palm_stop/语音 stop | 停止优先、清理或失效旧队列；停止未确认不得报告 stopped；旧 ACK 不复活动作 | 动作0b999ac和后端12150fc假设备通过；实体到位/保持未通过 |
| P05 | 执行失败、超时、断连后恢复 | 失败原因对应原执行；过期动作不自动重放；连接恢复不重演旧提醒 | 0b999ac假设备与bc7effd失败订阅恢复通过；不作实机声明 |
| P06 | 机械音播放与摄像头取帧并行 | 两者持续工作且没有第二媒体 owner；打断仍及时，失败降级真实可见 | 实机未验，mock 不替代 |
| P07 | 同时启动两实例、停止、随后重启 | 唯一设备 owner；第二实例拒绝；停止释放资源；退出后可重新启动 | 12150fc真实fake TCP进程、跨端口lease、受权shutdown通过；隔离生产lease |
| P08 | 无设备、无密钥导入和默认测试 | 不自动连接设备、绑定生产端口、播放、拍摄或派生硬件进程 | 新后端导入测试及fake进程通过，未导入旧bridge/硬件库 |
| P09 | 干净 Python 环境按文档安装 | 依赖检查和 focused tests 通过；模型/资产下载版本及恢复说明明确 | bridge/pet/vision/voice干净包环境重建通过；不等于全部ASR模型下载验证 |

## 已执行的软件验收

| 版本/范围 | 实际运行 | 结果与边界 |
|---|---|---|
| 基线 bridge + 安装隔离测试 | `python -m pytest -q tests patches/reachy_expression/test_install.py`，既有 Python 3.12.13 | 20 passed；mock，无设备/API请求 |
| 干净 QA 环境 | Python 3.12.13，`uv pip install --python <qa-python> -r requirements-dev.txt`；`uv pip check --python <qa-python>` | 安装44包，兼容性通过；只修改 QA 隔离环境 |
| 干净环境重复基线 | 同上20项 | 20 passed；验证依赖可解析，不证明长期逐字节可复现 |
| 旧语音补丁固定源码快照 | `python -m pytest -q <snapshot>/patches/reachy_companion/test_voice_runtime.py -k "not second_process"` | 8 passed，1 deselected；静音零样本、采集非阻塞、重试退避、安装原子写入等 mock 通过 |
| 表情补丁组 | 首次同时收集 `patches/reachy_expression` | 未执行：桥接环境缺少 `reachy_mini` 导致收集失败；不得把整组记为通过 |

导入探针使用 `PYTHON_DOTENV_DISABLED=1`、QA 本地 `DATA_DIR`、`TTS_ENABLED=false`，并通过 Python audit hook 拒绝 `socket.connect`、`socket.bind`、`subprocess.Popen`。这只覆盖被审计的 Python 通道，不能证明任意原生库没有设备调用。`bridge.main` 有本地 settings/database bootstrap 写入，不能称为无副作用导入。

初次额外尝试 `uv pip sync` 只安装直接列出的13包，产生26项缺依赖、pytest 缺 pluggy。该命令不是项目启动器约定；按启动器的 install 方式重建后通过。`requirements.lock.txt` 未锁定全部传递依赖及哈希，因此记录为“当日可重建”，不称为完整冻结锁。QA 未修改依赖文件。

旧语音 `test_second_process_cannot_acquire_audio` 会申请生产命名互斥锁 `Local\\HaifengConversationAudio`，本轮主动排除，避免影响真实音频 owner。应由 owner 提供可注入独立测试锁名或经总控安排停机窗口后验证；不能以此跳过项宣称单实例已验。

## 实机最小步骤（未执行，等待总控排窗）

1. 冻结四模块提交、模型/资产版本与配置；由唯一 owner 启动，确认无第二实例。
2. 现场说简短中文，记录 final 文本是否正确、行为语义、执行 ACK、实际机械短声/动作；内部中文不得转成人话 TTS。
3. A 回应中插入 B，观察旧声/旧动作停止及 B 正确回应；测停止延迟，不把20ms软件帧周期当实测延迟。
4. 人进入、持续停留、挥手、举掌停止、离开再进入；确认不连发、不误复活旧帧。拒绝用人工发 JSON 冒充视觉识别。
5. 同时语音与取帧，再注入已获准的断连/恢复；确认无音频互抢、相机卡死、旧动作补播。故障方式由设备 owner 选定，不自行拔设备或重启 daemon。
6. 停止服务再启动，验证资源释放和新 session；旧 session 结果全部丢弃。

每例记录版本、输入身份、时间、预期、决策/执行 ACK、实际现场结果及故障原因。默认不保存私人原始音视频。必须现场参与的说话、挥手、听感步骤由总控协调；本轮没有占用设备窗口。

## 后续交接

集成负责人接收本文和可测分支；QA在固定提交上审查及运行 focused tests。各模块软件通过后才能进入受控实机窗口。本文的待测项仍是未验，不能因为基线测试通过或模块 owner 自报完成而自动放行。

## 动作 PR #1 独立审查

审查版本 `4204150a49e77b108779664519f56cf0b91be725`，PR：<https://github.com/kimniniup-creator/haifeng/pull/1>。在 QA 忽略目录解出完整固定提交，以隔离 Python 3.12.13 运行 `python -m pytest -q tests/test_pet_motion.py`：**25 passed**。没有设备连接。

- 默认 dry_run、未批准映射、串行有界队列、UUID相关终态、POST返回前取消及停止未确认锁定已有 mock 覆盖。静态源码确认 transport 先建立 WebSocket 上下文再 POST；实际 daemon 订阅时序与网络断连仍未实机验证。
- **P2已修并软件复验：自然完成与取消竞态导致误锁定。** `MotionExecutor._stop` 在 stop HTTP 失败后不读取已缓冲的匹配 `move_completed`，直接永久标 `stop_unconfirmed`。所审阅的本地 SDK `stop_move_task` 对已完成并移除的 UUID 抛 KeyError，因此完成后恰好取消是合理触发路径。
- 独立假设备复现：正常 start；stop(uuid) 先将匹配 `move_completed` 放进订阅队列，再抛 HTTP等价异常；cancel 后得到 `failed / stop_unconfirmed`、`available=False`，队列仍保留那条可信完成事件。复现只操作内存，不调用真实接口。
- 修复要求：stop POST异常时，仍在明确期限内核对已订阅的匹配终态；没有确认则保持锁定，不能把HTTP错误一概视为成功。补测完成与取消交叉、无终态及错误UUID；交动作 owner 修改后复验。
- 修复版本 `4679481b6aee580e5ce3148c6d63e837212d901e`：在同一个 stop_timeout 内，POST异常后继续等待匹配终态。独立运行该固定版本 **26 passed**；新增竞态用例通过，原无终态/失败/失联锁定用例仍通过。此项关闭，不覆盖后续新增微动作 profile，也未修改 approved。

## 后端第一阶段审查（2026-09-24）

固定版本 `443d3dc`：独立运行 `tests/test_pet_interaction.py tests/test_pet_motion.py` 得到 **48 passed**（包含旧动作4204150的25项，不能据此覆盖动作修复版本）。另有两项由独立补测发现、已交集成负责人修复：

1. 带称呼的“啾啾停一下”被 `consume_voice` 分类为 wake_word，进而执行 attention，`stopped=False`。要求仅对匹配文本去称呼/标点，优先 stop/rest 后 wake，原始转写不改；停止状态下同句不得解除停止。
2. 假设备停止失败时，MotionExecutor 已锁定 `stop_unconfirmed`，控制层仍只返回 `accepted / reason=stop / state=quiet`，状态也只显示 stopped=true。要求分列接收结果与 motion/voice 停止回执，公开执行器故障；未确认不能呈现为成功停止。

以上均为内存假设备复现，没有访问运行中的 daemon 或语音服务。修复版本 `7e1407d` 独立运行 `tests/test_pet_interaction.py tests/test_pet_interaction_process.py`：**35 passed**，两项关闭。停止回执分列motion/voice，故障出现在state；带称呼停止先于唤醒判断。进程测试用QA独立TEMP/TMP隔离全局文件lease，验证跨端口重复实例拒绝，不争用生产lease。

另在443d3dc通过真实 fake CLI 子进程与随机回环端口完成：首实例健康、同端口第二实例拒绝、首实例保持健康、正常lifespan关闭、端口可重新绑定、没有硬件模块导入。正常关闭由仅QA包装器设置 uvicorn.should_exit 驱动，不声称验证 Windows Ctrl+C 信号链；只终止自己创建的进程。

## 视觉与语音固定版本审查（2026-09-24）

视觉 `f4509397ad15bda5a19fbe76733faf08d004224f` / [PR #2](https://github.com/kimniniup-creator/haifeng/pull/2)：独立focused结果 **16 passed, 1 skipped**，缺本QA环境的模型/依赖而跳过真实模型用例；owner的17项及官方样图证据单列为转达，不合并为QA亲测。组合合成用例发现以下三项，交视觉/集成owner修复：

- 连续6秒手可见只发一次presence(true)，视觉仍present=True，后端1.5秒TTL后present=False；需续租且不重复触发动作。
- 默认sink读PET_API_TOKEN，后端该角色为operator；应使用PET_VISION_TOKEN，否则正常双token配置下视觉事件403。
- README把async controller.handle直接传同步Pipeline；调用未await，因此不投递。需要明确异步管线或正确同步接线示例。

修复 `71e4706a5d3fc8696d3f09f44ceb450136b78752` 独立 **20 passed**，三项模块缺陷关闭。QA新建Python3.12视觉环境按requirements-vision安装，26包兼容性检查通过；本地模型复制到忽略目录并核对SHA256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`，真实模型空白帧测试本次实际执行通过。没有开摄像头。后端“续租不重复行为、断流为unknown”组合仍待集成新版本；不能只凭视觉20测宣称跨模块通过。owner在71e4706文档记录DirectShow采到62帧，这是转达的现场证据，仍不等于真人wave/palm识别通过。

语音 `23a6dc5d5a5706f6cbda9e7e14a211c0196d11ae`：从固定源码快照用既有独立voice环境运行 `python -m unittest discover -s patches/reachy_companion -p 'test_*.py' -q`，**26 tests OK**，不打开音频；新版mutex用例使用独立测试名。静态检查TurnGate入队与每个输出块复制共用身份锁，completed仍只指最后buffer提交，不证明可闻性。

发现失败订阅清理缺口：Companion.emit发送异常/超时后只从clients移除，agent_clients和semantic_agent_connected仍保留。确定性假连接send_json抛异常后，两集合成员分别False/True；识别侧持续禁用local ack却不再向该连接发送final。已交语音owner修复统一清理/关闭失败连接并补异常与超时用例。

修复版本 `bc7effdfbae2fdbc7d189d2c975cca9747ea91f9` 独立复验 **29 tests OK**，失败/超时清理与存在其他订阅者三项新增用例通过，缺口软件关闭。随后语音owner报告已在协调窗口将运行实例更新至bc7effd，并完成两轮真实订阅/断开重连，断开恢复local ack资格；这是owner转达证据，不是QA亲测，也不等于真人连续语音/重复回应通过。QA没有更新运行实例。

语音干净重建另验：QA新建Python3.12.13环境，仅按该固定版本requirements-pet.txt安装，24包兼容性检查通过，重新运行同组 **29 tests OK**。未下载或加载中文ASR模型、未开音频；此项证明包依赖和离线测试可重建，不证明真人ASR或AEC。

## 1.5度微动作软件审查（2026-09-24）

固定 `645c98efbb38867cf23287306b86acb6259e9683`：分别独立运行 `tests/test_pet_motion.py` **26 passed** 与 `tests/test_pet_motion_micro.py` **11 passed**。审查局部Y相对测量矩阵、配置1.5度/硬上限2度、最小1.5秒minjerk、独立映射及profile批准门、两段UUID串行与到位测量、取消只hold不回程、hold失败锁定；没有发现阻断总控计划的单次10秒TTL受限探测的软件问题。结论不等于实体通过，不授权生产approved或自动映射；实际设备窗口仍归总控和唯一动作owner。

发现自动集成TTL冲突：该微动作默认最低完整预算6.75秒，语音事件最多2.5秒、视觉1.5秒直接传给submit会拒绝。总控已明确后续契约为保留原事件start deadline，另设execution_budget=10秒；旧事件不得刷新时间，新epoch/stop仍中断。须在后续固定版本验证三项：新鲜短TTL事件可在期限内开始并完成去回；排队过期事件不开始；开始后stop/epoch仍取消且不补回程。本版本未据此放行自动链路。

动作owner后续报告第一次探测在snapshot矩阵校验阶段中止，没有goto/UUID。原始遥测的正交误差约6e-4，高于旧1e-4阈值；这不是动作到位失败，也不是微动作通过。矩阵容差及受限SO(3)投影将随新固定提交独立复验，QA不自行重试设备。

姿态修正 `03a24f9026f85807922505eebcb9b9000b359fd3` 独立 **39 passed**。先约束原始正交及det误差≤.001，再SVD投影；投影差≤.001且det正，保留原平移且不改输入，scale/shear/reflection/坏末行拒绝。未发现阻断总控条件授权的第二次同样1.5度、10秒TTL、唯一一次受限探测的软件问题；TTL分离不在本版本，自动映射仍不放行。

## 集成 PR #4 审查

[PR #4](https://github.com/kimniniup-creator/haifeng/pull/4) 固定 `a155a33b55fbc07ed93fc67bac76b91103ebb75c`，独立运行 `tests/test_pet_interaction.py tests/test_pet_interaction_process.py tests/test_pet_interaction_integration.py`：**38 passed**。QA桥接环境新增sherpa-onnx 1.13.8供ASGI组合导入，实际执行语音owner HTTP→规则→机械PCM内存块→打断→旧结果拒绝，不skip，不播放。视觉真实GestureEngine→真实dry-run MotionExecutor的组合用例通过；true presence续租不重复动作、断流unknown已覆盖。

另新建干净Python3.12.13环境，只安装该版本requirements-pet.txt和pytest9.1.1：22包兼容性检查通过，单元及process组 **35 passed**，证明独立fake后端按自身依赖可重建。不会把加过ASR/视觉依赖的环境当作这个干净环境证据。

额外发现 **P2 false presence租约不过期**：最后一次present=False把presence_until置0，tick只检查truthy present；10秒后仍not_visible，不转unknown。已交集成owner修true/false统一期限并补回归；本版本暂不给最终可合结论。生产动作继续dry-run，摄像头runner不开；最终TTL改动仍须增量验收。

修复 `12150fc85bdc68c224e3f26eb5620242ce60821d` 独立 **42 passed**：false/true租约过期unknown、播放回执绑定原轮次、迟到回执不改新轮、手部状态不覆盖当前语音、operator仅关闭本服务及自然退出均通过。该固定版本在保持motion dry-run、映射未批准、无默认相机runner前提下没有已知软件合并阻断；结论不自动延伸到未来TTL接线。

动作预算分离 `0b999acbdaefcc534a776139ff43411d2efe4e24` 独立 **44 passed**，排队和预检越原始start deadline不下发、开始后可跨事件期限完成回程、换轮取消不回程通过。尚待后端将原event deadline和10秒execution budget正确传入，并将等待期限同步拆分；不能仅更改adapter却保留上层按2.5秒取消。

第二次实机探测为动作owner转达：仅一个UUID完成，实测目标误差约1.081度，随后hold也有变化。实体目标到位/保持未通过，禁止据软件44测解除自动动作门禁。没有第三次设备操作授权，本QA不执行动作。

启动脚本 `tools/run_pet_interaction.ps1` 静态审查不启动daemon/音频进程，显式开关控制设备/运动/语音订阅；令牌落在忽略目录、不在命令行回显。在线8091/7860状态均为owner报告，QA不访问或重启生产实例。

## 视觉限时窗口 PR #5 增量审查（2026-09-24）

[PR #5](https://github.com/kimniniup-creator/haifeng/pull/5) 固定提交 `df7db0dbfd04489cc5d12e2e1f6399944c0cfeba`，基于已合入的 main `5d8e66780b345aadcd66951b8ceae50f13d0c52c`。视觉实现与先前已审的 `c38788d` 一致；最终提交增加边界测试和诊断文档。独立源码快照执行 `python -m pytest -q tests/test_pet_vision.py tests/test_qa_seconds.py`：**48 passed，0 skipped，5.05秒**，其中仓库视觉测试26项、QA忽略目录内独立补测22项；真实模型空白帧用例实际运行。此前PR #4固定版本107项通过，本次按增量范围未重跑全套。

- 默认窗口仍15秒，三个内置provider均支持显式60秒；0、负数、超过60、NaN、无穷值在启动子进程前拒绝。自定义provider不带seconds的既有调用保持兼容，显式seconds仅允许内置provider。
- 独立补测通过mock验证时长传递、提前关闭、EOF、截断帧、watchdog回调及异常退出后的自有子进程清理、stdout关闭和timer取消；CLI退出关闭stream与detector。没有启动实际摄像头子进程。
- 父进程watchdog为窗口时长加30秒，即默认45秒、60秒窗口对应90秒，包含启动余量；不能把60秒采集窗口描述成整个进程必在60秒内结束。
- 动作诊断文档保持实测偏差与hold未通过的结论，没有新增动作实现或放宽approved。仓库public表述与Kim已授权状态一致。

**结论：该固定版本无已知软件合并阻断，可由集成负责人按已有授权合并。** 本次不证明真人wave/palm识别、物理运动或hold通过，不改变motion dry-run、映射/profile未批准、相机默认关闭的边界；未访问设备、生产API，未重启8091服务。

## 持续视觉 PR #6 增量审查（2026-09-24）

[PR #6](https://github.com/kimniniup-creator/haifeng/pull/6) 固定 `26466cd4e8ac8eeb5543dfa5298ca3f943febf7d`，base `43c68cce056403aa67c4553cd66f1fb7a05caf2a`。独立快照运行 `python -m pytest -q tests/test_pet_vision.py tests/test_qa_seconds.py tests/test_qa_continuous.py`：**57 passed，0 skipped，8.60秒**，包括31项仓库测试、22项既有独立时长检查、4项独立持续模式及日志检查。真实模型空白帧和随机测试名的Windows mutex实际执行；所有采集/投递均为mock，没有打开相机或访问后端。

- 持续入口只接受DirectShow provider，拒绝同时指定seconds；无总时长timer但保留父30秒无完整帧进度监控，源20秒无读取进度监控。父watchdog仅清理其创建的子进程树；错误退出不自动重连。独立mock触发父stall回调，验证终止、报错、关闭管道和停止guard。
- Windows命名mutex重复申请拒绝、释放后可重新申请通过；该锁覆盖采用本guard的DirectShow reader，不代表能约束任意外部相机软件或其他Windows会话。唯一producer仍由协调窗口和部署负责人管理。
- 合成3000条事件实际触发1 MiB轮转，只有一个backup，两文件均低于1 MiB且逐行JSON有效；回执仅保留status/reason/decision_id，额外测试secret字段不落日志。测试未产生图片或真实凭据。
- 源码审查确认读取失败立即退出、finally释放采集句柄与lease；原生卡死使用自身进程退出兜底。软件检查不等于真实长期运行、真人手势识别或实体动作通过。

**结论：该固定版本无已知软件合并/已授权唯一producer部署阻断。** 交集成负责人合并、视觉owner在协调窗口部署；QA不部署、不操作设备、不重跑107项。motion dry-run及映射/profile未批准边界保持。owner报告的60秒实采264不同帧、66 accepted及backend状态转换仅作转达证据，不计入QA亲测。
