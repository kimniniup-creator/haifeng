# 宠物机器人基础交互独立验收

日期：2026-09-23。状态：软件基线已测，新交互实现待固定版本验收，实机未验。本文由独立 QA 单写；不修改实现，不占音频、摄像头、COM/BLE，不启动或重启运行服务。

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
| P01 | 合法语音/视觉事件 | 来源 session/event/turn 身份贯穿决策、唯一行为和执行 ACK；失败不报成功 | 新实现待测；旧 bridge 测试只覆盖 request/UUID |
| P02 | A 轮被 B 打断，随后 A 的 partial/final、模型结果、工具结果、音频迟到 | A 静默丢弃；B final 只执行一次；最后播放/执行边界仍检查原身份 | 新实现待测 |
| P03 | presence 持续、wave 重复、左右手标签抖动、离开后重入 | 防抖和冷却有效；离开清理追踪；重入可重新识别；旧帧不变成新事件 | 合成关键点测试与真实手势必须分开 |
| P04 | 普通动作执行中、队列非空时收到 palm_stop/语音 stop | 停止优先、清理或失效旧队列；停止未确认不得报告 stopped；旧 ACK 不复活动作 | 新实现待测；设备停止延迟单独测 |
| P05 | 执行失败、超时、断连后恢复 | 失败原因对应原执行；过期动作不自动重放；连接恢复不重演旧提醒 | 新实现待测 |
| P06 | 机械音播放与摄像头取帧并行 | 两者持续工作且没有第二媒体 owner；打断仍及时，失败降级真实可见 | 实机未验，mock 不替代 |
| P07 | 同时启动两实例、停止、随后重启 | 唯一设备 owner；第二实例拒绝；停止释放资源；退出后可重新启动 | 新启动器待测；不运行旧 start.ps1，它可能启动 daemon |
| P08 | 无设备、无密钥导入和默认测试 | 不自动连接设备、绑定生产端口、播放、拍摄或派生硬件进程 | 旧 bridge 导入探针见下；新模块待测 |
| P09 | 干净 Python 环境按文档安装 | 依赖检查和 focused tests 通过；模型/资产下载版本及恢复说明明确 | 旧 bridge Python 3.12 重建通过；新 ASR/视觉依赖待测 |

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
