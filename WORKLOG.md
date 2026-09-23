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
