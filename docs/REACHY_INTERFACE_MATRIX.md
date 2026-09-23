# Reachy Mini 官方接口验收矩阵

日期：2026-09-23。平台：Windows，Reachy Mini Lite，SDK 1.11.0；真实硬件，COM11，daemon 8000，桥接 8088，no_media=true。此矩阵是覆盖清单，不是“全部功能通过”。

## 结论与证据边界

- **扬声器未修复、未通过。** 用户已明确否定 MME 和此前官方 play_sound 的可闻结果。本轮左右声道各 1 秒的 SDK 测试收到 EOS，现场可闻结果尚未回复。不得据此写“扬声器正常”。
- Reachy render/capture GUID 已重新枚举；均未静音，主音量及左右声道 1.0。WAV 有有效波形，禁止默认电脑扬声器回落。官方 USB 控制这次可读：VERSION=[2,1,2]、USB_BIT_DEPTH=[16,16]、I2S_INACTIVE=[0]、I2S_DAC_DSP_ENABLE=[0]、OP_L/OP_R=[8,0]。**这些寄存器值不是故障诊断，未改写 DSP 或固件。**
- 麦克风通过必要短时 SDK 采集：基线 11168×2 样本，RMS 0.018535、峰值 0.144651，非零 22090。仅证明设备交付非零数据，不证明语音可懂度；未保存或上传录音。播放期间能量变化受环境/AEC影响，不作为扬声器出声证据。
- 触角 +0.05 rad 指令返回完成；等待额外 0.7 秒后实际变化仅 +0.006136 rad，**到位验收失败/原因未定**。取消任务收到对应 UUID move_cancelled，队列清空；恢复初始目标和 disabled。头部/身体运动暂停，避免在已有到位异常时扩大动作。
- daemon stop(false) → stopped → start(false) → running 均有 job done；SDK task 同位置请求收到 finished=true、error=null。仅证明任务链路，不冒充实际运动通过。日志仍见 Serial I/O recovered after 1 retries。
- 相机名可识别；首个默认格式帧 3840×2592 BGR，均值约128、标准差0.04036，近灰帧，不能证明真实成像。官方 MJPEG 1080p60 参数 8 秒无帧；YUY2 1080p5 探测进入原生阻塞，专用 Python 进程已停止。没有保存或上传环境图像。新增脚本有25秒子进程期限。
- **官方 REST 假阳性：** no_media 下 play_sound、stop_sound、clear_incoming_audio、test-sound 返回200；Backend 在没有 media server 时为 no-op。release/acquire 同样不会覆盖 no_media 启动设置。不得将“Test sound played”作为播放证据。
- **协议差异：** `/ws/sdk` 是正确路径，不是 `/api/ws/sdk`。普通命令的 send_response 在 WSServer 被丢弃，查询无单独回复是该实现行为；状态广播和 task_progress 已收到。`/logs/ws/daemon` 仅 wireless 挂载，本机不适用。

## 来源与复现

- [官方 SDK 固定版本源码](https://github.com/pollen-robotics/reachy_mini/tree/9d364df0d8b6c92fbda7a9252fc378e23d4ab47c)，本机实际安装源码与 openapi.json 为运行时依据。
- [官方桌面应用固定源码](https://github.com/pollen-robotics/reachy-mini-desktop-app/tree/f520136ffe9b54ba6e34a6d5b4da4781cfd55ab8)；仅审阅源码，未安装接管。源码 package.json 标记0.9.32。
- [官方故障排查](https://github.com/pollen-robotics/reachy_mini/blob/9d364df0d8b6c92fbda7a9252fc378e23d4ab47c/docs/source/troubleshooting.md)。Lite使用随附7V5A电源；供电是电机错误的检查项，不是本次扬声器根因结论。
- 原始响应在忽略目录 `.runtime/rest-audit.json`、`motion-audit.json`、`lifecycle-audit.json`、`extra-audit.json`、`ws-commands.json`、`sdk-task.json`、`audio-local-probe.json`、`audio-parameters.json`。不提交原始日志、环境音频/影像。
- 可复用工具：`reachy-env\Scripts\python.exe tools/reachy_api_audit.py`（只读白名单）；`tools/reachy_audio_probe.py`（约4秒本地采集及两声测试音）；`tools/reachy_camera_probe.py`（只保留统计）；`tools/reachy_motion_probe.py`（会启用电机、约3°触角动作并恢复模式）。硬件工具只能由唯一操作方顺序执行。

## HTTP：运行时 OpenAPI 全量操作

“已测”指请求/响应已观察；物理结果独立见最后一列。只覆盖所列输入，非所有边界值或全部参数组合。

|接口|适用性 / 状态|响应摘要|硬件证据 / 限制|
|---|---|---|---|
|`GET /api/apps/list-available/{source_kind}`|适用；已测|200 []|软件响应；不单独证明硬件结果|
|`GET /api/apps/list-available`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/install`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/remove/{app_name}`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`GET /api/apps/job-status/{job_id}`|适用；已测|200 {"command":"daemon-start","status":"done","logs":["Job 'daemon-start' completed successfully"]}|软件响应；不单独证明硬件结果|
|`POST /api/apps/start-app/{app_name}`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/start-app/{app_name}/no-evict`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/restart-current-app`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/stop-current-app`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`GET /api/apps/current-app-status`|适用；已测|200 None|软件响应；不单独证明硬件结果|
|`GET /api/apps/startup-app`|适用；已测|200 {"startup_app":null}|软件响应；不单独证明硬件结果|
|`PUT /api/apps/startup-app`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/install-private-space`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`GET /api/apps/check-updates`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/apps/update/{app_name}`|需要真实条件；未测|—|当前无安装应用；不安装随机应用、不修改启动项、不删除用户数据|
|`POST /api/audio/config/apply`|适用；未测写入|—|契约检查；不猜测/改写DSP寄存器|
|`GET /api/audio/config/parameter/{name}`|适用；已测|200 {"name":"DOA_VALUE_RADIANS","values":[1.5533430576324463,0.0]}|软件响应；不单独证明硬件结果|
|`GET /api/camera/specs`|适用；已测|200 {"name":"lite","available_resolutions":[{"name":"R1920x1080at60fps","width":1920,"height":1080,"fps":60,"crop_factor":1.115},|软件响应；不单独证明硬件结果|
|`POST /api/daemon/start`|适用；已测|200 {"job_id":"533f171d-1775-4dbe-916f-b633e5e37334"}|软件响应；不单独证明硬件结果|
|`POST /api/daemon/stop`|适用；已测|200 {"job_id":"36064c92-b303-4ed5-b879-070c7e57baa5"}|软件响应；不单独证明硬件结果|
|`POST /api/daemon/restart`|适用；未测（契约已列出）|—|契约审阅；已测显式stop/start，不重复restart|
|`GET /api/daemon/status`|适用；已测|200 {"type":"daemon_status","robot_name":"reachy_mini","state":"running","wireless_version":false,"desktop_app_daemon":false,"sim|软件响应；不单独证明硬件结果|
|`GET /api/daemon/robot-name`|适用；已测|200 {"name":"reachy_mini"}|软件响应；不单独证明硬件结果|
|`POST /api/daemon/robot-name`|适用；未测（契约已列出）|—|未改用户设备命名|
|`GET /api/daemon/hardware-id`|适用；已测|200 {"hardware_id":null}|软件响应；不单独证明硬件结果|
|`GET /api/daemon/robot-app-lock-status`|适用；已测|200 {"state":"free","holder_name":null}|软件响应；不单独证明硬件结果|
|`POST /api/hf-auth/save-token`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/status`|已测（仅状态）|200 {}|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/relay-status`|已测（仅状态）|200 {}|账号/远程条件；不保存token或身份|
|`DELETE /api/hf-auth/token`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`POST /api/hf-auth/refresh-relay`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/central-robot-status`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/configured`|已测（仅状态）|200 {"configured":true}|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/start`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/begin`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/status/{session_id}`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`DELETE /api/hf-auth/oauth/session/{session_id}`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`POST /api/hf-auth/oauth/device/start`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/device/status/{session_id}`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`DELETE /api/hf-auth/oauth/device/session/{session_id}`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/hf-auth/oauth/callback`|需要真实条件；未测授权流程|—|账号/远程条件；不保存token或身份|
|`GET /api/kinematics/info`|适用；已测|200 {"info":{"engine":"AnalyticalKinematics","collision check":false}}|软件响应；不单独证明硬件结果|
|`GET /api/kinematics/urdf`|适用；已测|200 {"urdf":"<?xml version=\"1.0\" ?>\n<!-- Generated using onshape-to-robot -->\n<!-- Onshape https://cad.onshape.com/documents/|软件响应；不单独证明硬件结果|
|`GET /api/kinematics/stl/{filename}`|适用；未测（契约已列出）|—|静态模型文件；未测，非硬件动作|
|`POST /api/media/release`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/acquire`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`GET /api/media/status`|适用；已测|200 {"available":false,"released":false,"no_media":true}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/play_sound`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/stop_sound`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/clear_incoming_audio`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/wobbling/enable`|需要真实条件；未测|—|需要启用media；文件增删未执行，避免用户数据变动|
|`POST /api/media/wobbling/disable`|适用；已测|200 {"status":"ok"}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/tracking/enable`|需要真实条件；未测|—|需要启用media；文件增删未执行，避免用户数据变动|
|`POST /api/media/tracking/disable`|适用；已测|200 {"status":"ok","enabled":false}|no_media：200可能是no-op，不证明输出|
|`GET /api/media/tracking/face`|适用；已测|200 {"status":"ok","face_target":{"detected":false,"x":null,"y":null,"roll":null,"ts":null}}|no_media：200可能是no-op，不证明输出|
|`POST /api/media/sounds/upload`|需要真实条件；未测|—|需要启用media；文件增删未执行，避免用户数据变动|
|`GET /api/media/sounds`|适用；已测|200 {"files":[]}|no_media：200可能是no-op，不证明输出|
|`DELETE /api/media/sounds/{filename}`|需要真实条件；未测|—|需要启用media；文件增删未执行，避免用户数据变动|
|`GET /api/motors/status`|适用；已测|200 {"mode":"disabled"}|软件响应；不单独证明硬件结果|
|`POST /api/motors/set_mode/{mode}`|适用；已测|200 {"status":"motors changed to MotorControlMode.Disabled mode"}|enabled/disabled已测并恢复；gravity_compensation需Placo，本机Analytical不适用|
|`GET /api/move/running`|适用；已测|200 []|软件响应；不单独证明硬件结果|
|`POST /api/move/goto`|适用；已测|200 {"uuid":"e09d63fc-5f79-46ee-9a97-a4dfba6c4b79"}|触角小幅+停止；到位误差未通过；身体/头部未测|
|`POST /api/move/play/wake_up`|适用；未测|—|内置/录制动作幅度未验，已有到位异常，不自动播放|
|`POST /api/move/play/goto_sleep`|适用；未测|—|内置/录制动作幅度未验，已有到位异常，不自动播放|
|`GET /api/move/recorded-move-datasets/list/{dataset_name}`|需要真实条件；未测|—|需选定可信数据集，未下载|
|`POST /api/move/play/recorded-move-dataset/{dataset_name}/{move_name}`|适用；未测|—|内置/录制动作幅度未验，已有到位异常，不自动播放|
|`POST /api/move/stop`|适用；已测|200 {"message":"Stopped move with UUID: 290b0434-3c09-43fa-a4a5-0f5234888252"}|触角小幅+停止；到位误差未通过；身体/头部未测|
|`POST /api/move/set_target`|适用；已测|200 {"status":"ok"}|触角小幅+停止；到位误差未通过；身体/头部未测|
|`GET /api/state/present_head_pose`|适用；已测|200 {"x":-0.012995267708507098,"y":-0.008254330330741314,"z":-0.048735056404123456,"roll":-0.10016591277680326,"pitch":0.18932164|软件响应；不单独证明硬件结果|
|`GET /api/state/present_body_yaw`|适用；已测|200 -0.6810874698212248|软件响应；不单独证明硬件结果|
|`GET /api/state/present_antenna_joint_positions`|适用；已测|200 [-1.3499030933393643,-0.27765052260730094]|软件响应；不单独证明硬件结果|
|`GET /api/state/doa`|适用；已测|200 None|no_media返回null；USB参数读取另行成功|
|`GET /api/state/imu`|Lite不适用；已测空值|200 None|无wireless IMU|
|`GET /api/state/full`|适用；已测|200 {"control_mode":"disabled","head_pose":{"x":-0.012995267708507098,"y":-0.008254330330741314,"z":-0.048735056404123456,"roll":|软件响应；不单独证明硬件结果|
|`GET /api/volume/current`|适用；已测|200 {"volume":100,"platform":"Windows","device":"回音消除话筒 (Reachy Mini Audio)"}|Reachy GUID核验；原值100写回读100；未静音，不证明有声|
|`POST /api/volume/set`|适用；已测|200 {"volume":100,"platform":"Windows","device":"回音消除话筒 (Reachy Mini Audio)"}|Reachy GUID核验；原值100写回读100；未静音，不证明有声|
|`POST /api/volume/test-sound`|适用；已测|200 {"status":"ok","message":"Test sound played"}|no_media：200可能是no-op，不证明输出|
|`GET /api/volume/microphone/current`|适用；已测|200 {"volume":100,"platform":"Windows","device":"回音消除话筒 (Reachy Mini Audio)"}|Reachy GUID核验；原值100写回读100；未静音，不证明有声|
|`POST /api/volume/microphone/set`|适用；已测|200 {"volume":100,"platform":"Windows","device":"回音消除话筒 (Reachy Mini Audio)"}|Reachy GUID核验；原值100写回读100；未静音，不证明有声|
|`POST /health-check`|适用；已测|200 {"status":"ok"}|软件响应；不单独证明硬件结果|
|`GET /`|适用；未测（契约已列出）|—|未作运行验证|

## WebSocket 与传输面

|接口|状态|响应/硬件证据|
|---|---|---|
|`/ws/sdk`|已测|joint_positions推送；同位置task_progress finished=true；不证明动作到位|
|`/api/state/ws/full`|已测|真实关节、姿态、时间戳|
|`/api/move/ws/updates`|已测|同UUID started/completed、started/cancelled|
|`/api/move/ws/set_target`|已测发送|发送初始触角目标，后续REST读数已记录；无专门ACK|
|`/api/move/ws/raw/write`|未测；契约检查|可直写电机原始包，避免校准/固件或大动作|
|`/api/apps/ws/apps-manager/{job_id}`|已测|daemon start/stop job completed日志|
|`/logs/ws/daemon`|不适用|仅wireless注册；误加/api的403不算端点故障|
|`/update/ws/logs`|不适用/未测|wireless更新任务，不升级|
|WebRTC signaling/video/audio/DataChannel/pose|需要真实条件；未测|no_media无media server；不能借REST200宣称媒体流通过|

## SDK / DataChannel 命令契约全量清单

从已安装 `io/protocol.py` 的 Cmd 类提取。共享schema不意味着每条传输均支持请求响应。此表检查命令存在性；不等于执行所有命令。

|命令|状态 / 适用性|响应及物理限制|
|---|---|---|
|`set_target`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_head_joints`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_body_yaw`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_antennas`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_full_target`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`goto_target`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`wake_up`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`goto_sleep`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`play_sound`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`play_recorded_move`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`preload_dataset`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_motor_mode`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_torque`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`get_motor_mode`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`set_gravity_compensation`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_automatic_body_yaw`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`get_state`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`get_version`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`get_hardware_id`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`get_imu`|SDK WS已发送；无单独响应|Lite无IMU；REST返回null|
|`start_recording`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`stop_recording`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`append_record`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_volume`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`get_volume`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`set_microphone_volume`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`get_microphone_volume`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`get_robot_name`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`set_robot_name`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`delete_hf_token`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`get_first_wake_up`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`set_first_wake_up`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`set_speech_offsets`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_wobbling`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`set_head_tracking`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`get_tracked_face`|SDK WS已发送；无单独响应|WSServer send_response空实现；REST替代查询见上表|
|`subscribe_logs`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`unsubscribe_logs`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`subscribe_pose`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`unsubscribe_pose`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`apply_audio_config`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`read_audio_parameter`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`restart_daemon`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`start_update`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_move_start`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_move_chunk`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_move_finish`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_audio_start`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_audio_chunk`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`upload_audio_finish`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`play_uploaded_move`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`cancel_move`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`stop_move`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`play_uploaded_audio`|未测；已检查契约|不执行更新/账户/持久化/用户数据修改；仅schema检查|
|`cancel_audio`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|
|`clear_incoming_audio`|未测；已检查契约|WebRTC DataChannel需要media；未声称硬件通过|

## 桌面应用 Tauri 注册接口全量清单

桌面客户端未安装运行，因此全部仅做官方源码契约检查，不能冒充HTTP实测；SDK控制保持唯一。UI层调用的HTTP接口见上表。

|Tauri命令|适用性 / 状态|响应 / 条件|
|---|---|---|
|`start_daemon`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`stop_daemon`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`set_daemon_external_mode`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`get_daemon_status`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`get_logs`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`open_external_camera_viewer`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`check_crash_marker`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`usb::check_usb_robot`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`window::apply_transparent_titlebar`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`window::close_window`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`permissions::open_camera_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_microphone_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_wifi_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_files_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_local_network_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::check_local_network_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::request_local_network_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::check_location_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::request_location_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_location_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::check_bluetooth_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::request_bluetooth_permission`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`permissions::open_bluetooth_settings`|桌面功能；未测（契约已查）|系统权限/设置界面；不修改现有权限|
|`wifi::scan_local_wifi_networks`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`wifi::get_current_wifi_ssid`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`update::check_daemon_update`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`update::check_remote_daemon_update`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`update::update_daemon`|桌面功能；未测（契约已查）|排除执行：重置/更新环境；仅契约审阅|
|`reset::reset_apps_venv`|桌面功能；未测（契约已查）|排除执行：重置/更新环境；仅契约审阅|
|`reset::reset_python_env`|桌面功能；未测（契约已查）|排除执行：重置/更新环境；仅契约审阅|
|`get_sidecar_source`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`set_local_proxy_target`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`clear_local_proxy_target`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`get_local_proxy_target`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::discover_robots`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::connect_to_ip`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::add_static_peer`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::remove_static_peer`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::get_static_peers`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|
|`discovery::clear_discovery_cache`|桌面功能；未测（契约已查）|需要桌面Tauri runtime；无实际响应|

## 仍需完成的真实条件

1. 现场回答两声短音是否来自Reachy。即使听到也需再用中文语音验收；没听到则保持失败，不重复EOS试验冒充修复。
2. 断电后按官方装配图检查扬声器插头/线材及音频板连接，并确认随附7V5A电源。当前日志不足以确定哪个部件故障；禁止以推断要求更换部件。若仍无声，携带本矩阵给官方支持，无需上传环境录音。
3. 触角目标与读数偏差、串口重试需独立排查；在此之前不执行大动作、wake/sleep全程、头部/身体扩大测试。
4. 相机原生驱动探测超时需要设备复位/官方驱动链路复检；未更换随机驱动。恢复可用图像后才能验收IPC/WebRTC及真实画面。
5. 当前无安装app，不安装随机代码为凑覆盖率；选定可信无硬件动作测试app后再测start/no-evict/restart/stop。daemon后台job生命周期已测，不等同app生命周期已测。

没有刷固件、恢复出厂、写电机校准、改DSP、删除用户数据、安装桌面客户端。最终daemon恢复running/disabled、move队列空，8000与8088各一个监听进程。

## Python SDK 公共方法索引（安装版本）

除明确列明实测者，均为未测的契约检查；同名方法不代表全部后端通过。排除私有下划线方法。

|类 / 方法|状态与证据|
|---|---|
|`ReachyMini.media`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.media_released`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.release_media`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.acquire_media`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.enable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.disable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.start_head_tracking`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.stop_head_tracking`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.get_tracked_face`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.imu`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.set_target`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.goto_target`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.wake_up`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.goto_sleep`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.look_at_image`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.look_at_world`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.get_current_joint_positions`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.get_present_antenna_joint_positions`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.get_current_head_pose`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.set_target_head_pose`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.set_target_antenna_joint_positions`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.set_target_body_yaw`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.start_recording`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.stop_recording`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.enable_motors`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.disable_motors`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.enable_gravity_compensation`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.disable_gravity_compensation`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.set_automatic_body_yaw`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.cancel_move`|未测；契约已查；依赖相应硬件/媒体条件|
|`ReachyMini.async_play_move`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.close`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_frame`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_frame_jpeg`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.play_sound`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.start_recording`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_audio_sample`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_input_audio_samplerate`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_output_audio_samplerate`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_input_channels`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_output_channels`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.stop_recording`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.start_playing`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.push_audio_sample`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.stop_playing`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.enable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.disable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`MediaManager.get_DoA`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.start_recording`|已调用；采样/EOS见正文，扬声器可闻未通过|
|`GStreamerAudio.stop_recording`|已调用；采样/EOS见正文，扬声器可闻未通过|
|`GStreamerAudio.start_playing`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.stop_playing`|已调用；采样/EOS见正文，扬声器可闻未通过|
|`GStreamerAudio.clear_player`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.play_sound`|已调用；采样/EOS见正文，扬声器可闻未通过|
|`GStreamerAudio.upload_sound`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.list_sounds`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.delete_sound`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.get_DoA`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.enable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.disable_wobbling`|未测；契约已查；依赖相应硬件/媒体条件|
|`GStreamerAudio.cleanup`|已调用；采样/EOS见正文，扬声器可闻未通过|
|`GStreamerCamera.open`|未测IPC后端；no_media无IPC；仅另行直连探测相机|
|`GStreamerCamera.read`|未测IPC后端；no_media无IPC；仅另行直连探测相机|
|`GStreamerCamera.close`|未测IPC后端；no_media无IPC；仅另行直连探测相机|
