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
