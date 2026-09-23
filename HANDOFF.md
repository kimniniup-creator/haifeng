# 海风交接

## 2026-09-23 产品方向更新：《带上她的眼睛》

- 用户明确家中实体为 Reachy Mini，眼镜无 3D 投影、无麦克风；目标是外出主动拍照分享，并从随身 M5 得到针对照片的角色回应。
- 用户接受手机仅在口袋提供热点，主流程不掏手机。M5 是同一角色的反馈窗口，不只显示上传回执。
- 最新讨论稿：docs/带上她的眼睛-PRD-v0.1.md。旧 PRODUCT.md 是此前桌边回顾原型记录，不代表最新目标；本轮不改运行程序。
- 参考已从 D:\forbetter 的陪伴契约与气质画像读取，不读取私人记忆。
- 用户确认 M5 为“S3”，授权真机检查。唯一硬件子任务 m5_feedback 负责型号、现有固件和可逆输出核验，报告 docs/M5_S3_HARDWARE_CHECK.md；主任务负责 PRD 与统一提交。不得因芯片 USB ID 推定具体 M5 型号，不得把电脑 USB 演示当外出验收。

## 权威位置
- 工作区：D:\海风。origin：https://github.com/kimniniup-creator/haifeng （private）。
- upstream：timesbye/Robot_glasses，继承V2 c968c62。
- 产品与验收：docs/PRODUCT.md、docs/ACCEPTANCE.md。

## 用户授权与边界
Kim授权总控在D盘海风管理项目，寻找具体用途并自主做到交付，中间常规取舍不询问。方向为随时可做的照片片段回顾，未宣称市场需求成立；不做泛化情感陪伴/恋爱/治疗，不做外出自动相册同步。

## 启动
双击start.cmd，或PowerShell执行 .\start.ps1。浏览器 http://127.0.0.1:8088 。启动器复用现有实例；已有Reachy环境时会启动或尝试重连Daemon，不自动唤醒头部。桥接使用.venv，SDK使用reachy-env（1.11.0）。

本机.env已配置真实DeepSeek视觉模型和随机令牌，严禁读取后回显或提交。模型可在页面设置更改。持久化数据位于data/，不进Git。

## 当前硬件
Reachy USB音频和COM11可见。Daemon曾running，但随后报Motor communication error，已请求一次不唤醒重连，不能声称运动已通过。此前MME/44100Hz返回播放结束，用户明确反馈没有声音。系统Reachy输出100%、未静音，WAV有有效波形。随后用官方SDK 1.11.0的GStreamerAudio.play_sound向Reachy WASAPI GUID播放“痛痛飞走了”，收到EOS无ERROR；现场可闻确认仍待完成。audio_status保持played_unverified。PyUSB控制接口未找到并不证明扬声器故障；未刷固件/改驱动/写DSP。官方客户端安装按用户纠正暂停，优先官方SDK接管与接口排查。

Luma没有现场发现；上游有E06-0055真机验证记录，本机未复验。新增Python Bleak CLI，无Rust依赖；LUMA_MODE=python。CLI40秒整体时限，取消杀子进程。眼镜有电且解除手机占用后再测。

## 已验证
19项自动测试、20轮模拟（不是真机）、真实视觉API、真实页面上传/回复/恢复/命名/删除、拍照取消、桌面1400与手机390截图。细节见ACCEPTANCE.md。测试片段已删除，不能恢复成伪造的示例生活。

## 下一步真实终点
1. 供电到位后运行start_robot.ps1，观察Daemon running（非sim）。真实触角小幅动作+UUID完成事件验收。
2. 眼镜拍两个不同物体，核对新图/时间/image_id，不能静默换机器人摄像头。
3. 现场确认中文声音来自Reachy，再完成20轮全硬件验收。
4. 若用户反馈用途不成立，回到PRODUCT.md的产品证伪条件；当前视觉/队列/片段基础可复用。

## 运行日志
.runtime/bridge.stdout.log、bridge.stderr.log、daemon.stdout.log、daemon.stderr.log。PID文件记录启动器进程，Windows虚拟环境可能再派生真实Python进程，停止前需核对监听PID、父子关系和命令行，不能按python名称批量杀进程。

## 2026-09-23 官方接口专项覆盖结果（替代上文过时音频状态）
- 以 docs/REACHY_INTERFACE_MATRIX.md 为本轮验收权威记录。此前MME和官方play_sound用户均反馈无声，扬声器未修复；本轮分声道测试等待用户实际听感，EOS不是通过。
- USB音频板控制现在可读，版本2.1.2；无DSP/固件写入。麦克风短时非零采样通过，语音质量未验。
- 触角3°目标实际偏移仅约0.35°，完成事件不等于到位；停止/取消事件通过；末态disabled、初始触角目标恢复。不要扩大运动。
- 摄像头近灰首帧及MJPEG超时，YUY2诊断原生阻塞；专用探测进程已停止，脚本添加硬期限。不要声称相机可用。
- daemon与SDK任务生命周期有真实响应；媒体REST在no_media时可能200空操作。不要把play_sound/test-sound的200当播放。
- 正式工具在tools/reachy_*_probe.py及reachy_api_audit.py；仅唯一硬件操作方顺序运行。原始日志仅.runtime。当前只允许可逆检查，禁止校准/固件/重置/随机驱动。

## 客户端接管（2026-09-23 后续用户新授权）
用户已要求安装并打开官方客户端，覆盖此前“不安装”的临时指示。Reachy Mini Control 0.9.34已安装；首次Python bootstrap失败已绕过版本链接故障，客户端正在用自身锁定的SDK1.8.0初始化。现有项目SDK1.11.0保留；不要同时启动项目daemon争用COM11。以客户端实际状态为准，音频/运动未通过项不因换客户端自动变成通过。
- 客户端后续实测已进入Ready / USB控制页，WebRTC DataChannel连接成功。相机UI仍有无法播放媒体提示，声音未现场验证；不要重新启动项目daemon覆盖客户端。

## 2026-09-23 表情返回补丁与当前阻塞
- 官方客户端recorded接口已安装 patches/reachy_expression 补丁，SDK1.8.0固定哈希安装/回滚；项目1.11不变。11项软件测试通过；尚无实机复位验收。
- 表情回到本次开始前实测姿态，不是工厂零位。防录制表情叠加，不替代SDK/controller所有通道互斥。官方升级可能覆盖，按README核验，禁止盲装其他版本。
- 重启后未播放表情即USB Pipe error+camera error+九电机失联，daemon error。用户已被请求断电重插供电/USB、直连电脑；收到完成反馈再做有限小幅验证。不要反复重启或强制大动作；不要把UI Ready/HTTP200当作硬件健康。
- 最新状态覆盖前项阻塞：用户完成物理重连，官方updater已升1.11，补丁已重新适配安装，12项软件测试通过且helper安装哈希一致。真实连接恢复running/ready，error=null，队列空；保持官方客户端唯一daemon。
- 小幅+0.05rad实际+0.0276117rad，偏差超过0.015rad探测验收门槛；返回起点成功。未做更大/连续完整表情，不能称整机稳定或精度通过。原始记录.runtime/expression-small-motion.json；下一步仅在明确机械/精度原因后扩展实机验收。用户询问说话无应答，已说明当前未装对话应用，LISTENING不等于语音助手运行。
- 最终UI仍Connecting/Healthcheck，后台state/full与status健康；远端目录/TURN/updater网络异常，刷新未解决，尚待继续客户端启动链排查。不要报告整套界面已稳定可用。补丁提交e616040已推送，后续记录独立提交。

## 最新：中文语音助手已安装（2026-09-23）
- 官方Conversation App 1.0.1已运行，HF Hosted后台已连接；7860界面选Haifeng/Vivian，麦克风已开。UI标签Mute microphone是点击动作，不表示静音。
- 本次首启仍触发相机/九电机错误，故临时采用patches/reachy_companion的voice-only适配，daemon媒体released=true，切勿随手acquire；目前真实daemon健康。仅官方客户端为8000唯一daemon。
- 已有音频响应增量，实际中文听感待用户回复；不能称整机稳定。人格和可逆安装器已保存，详情README。无需新增API key，未设开机启动，官方更新可能覆盖适配。

## 2026-09-23 最新状态（覆盖本文件前面所有音频/对话应用结论）
- 交付：Word 记录已按用户指示提交到 upstream timesbye/Robot_glasses，docs/Reachy_Mini_接口_语音_情感映射记录.docx，commit 63ae610。本地不留副本。
- **no_media=false**。daemon media available=true、motors enabled、error=null、nb_error=0、控制环 30–32Hz。前文「REST 200 是 no-op」「no_media 下播放不算数」已失效，音频判定必须按新环境重做。
- **对话应用在运行**。官方 reachy_mini_conversation_app：http://127.0.0.1:7860，JSON-RPC ws://127.0.0.1:7860/rpc；HF 后端 connected；TTS 9 音色、当前 Vivian；人格 user_personalities/haifeng 为当前及开机默认。前文「当前未装对话应用」作废。
- 端口面：8000 仅回环；**8443（WebRTC 信令）与 7860（对话应用）绑 0.0.0.0**，局域网可达，需补防火墙。8088 为项目桥接。
- 情感映射挂载点已就位但未启用：对话应用内置 play_emotion / stop_emotion / dance / move_head / head_tracking / sweep_look / camera / go_to_sleep；海风人格 enabled_tools 目前仅 remember / forget / idle_do_nothing。人格提示词明写「当前硬件动作还在验收…不请求未提供的动作或摄像头工具」，要接动作必须同步改这句，否则模型会拒绝调用。未擅自改动用户设置。
- 实机已验证：yes1 真实运动（右触角 0.2577 rad）、laughing1 动作+配音并发跑通、补丁复位残差 ≤0.025 rad。
- **补丁两处缺陷待修（未动手）**：9 个情绪动作恒 500（nextafter 越界，含 confused1/laughing2/proud1/welcoming1）；ReturningMove.sound_path=None 使全部情绪配音不响。修法各一行，写在 Word 文档 6.2 / 6.3。
- **最高优先级阻塞**：C:\Users\12246\AppData\Local\Reachy Mini Control 目录已从磁盘消失，daemon/对话应用/helper 仍在跑内存镜像。**重启客户端或电脑前先备份 apps_venv 包清单与人格文件**，否则很可能需要重走 bootstrap 且补丁丢失。本轮因此未关客户端、未重装补丁。
- 唯一未闭环的验收项仍是扬声器现场可闻性，只能由现场的人确认。

## 《带上她的眼睛》M5 核验收口
- 型号已确认为 M5StickS3 K150，现有 reading-pet 固件；135×240 显示驱动 ready，短音软件播放流程完成，实体显示与可闻性未验。
- 无内置震动；照片回应显示命令尚未实现，M5 BLE 眼镜采集与热点上行尚未联调。详见 docs/M5_S3_HARDWARE_CHECK.md。
- 下一步在本项目隔离复用现有模块、备份并核验设备恢复路径后实现回应接口；不直接覆盖 reading-pet 正式源码。当前仅 PRD 与真机核验完成，非外出产品交付。

## M5 最新范围对齐
- Kim 经旧固件任务转达：停掉心情、疲惫、陪读、暂停，保留形象；游戏可留但非 MVP。已写入 PRD，明确后台驱动也停，不仅隐藏界面。
- 已同步任务 01a0c7df-f2a2-7ef3-aca8-dc4f8c8bb26b，由其保持旧固件唯一修改权；本任务未刷机、未改 reading-pet。照片回应短表情不等于恢复心情数值系统。

## 最新输入与协作归属纠正
- 用户确认手动按眼镜腿按键拍照，移除 M5 触发拍摄替代方案；震动优先验证外接方案，可行则纳入 MVP。
- 固件总控 01a0c813；唯一固件/COM/烧录 01a0c5c6；01a0c7df 仅美术，覆盖此前误派。固件与恢复包在 reading-pet，PRD与事件协议在 haifeng，不双写代码；本任务不再操作设备。
- 总控转达用户已确认语音可听、音频修复已合；此前可闻待确认状态作废。最小事件协议见 docs/M5_PHOTO_EVENT_PROTOCOL_V0.1.md，已同步总控。
- 用户新增动画脚本试稿：皮克斯式动画、小王子与玫瑰故事；已产出创作简报并委派唯一文字脚本子任务，不开始视频制作。
