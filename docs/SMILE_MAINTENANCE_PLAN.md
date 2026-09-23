# 笑脸声音闭环：唯一维护计划与当前边界

本计划由链路维护 owner 执行，当前只整理候选，**没有部署或重启**。
先做笑脸声音，不以电机跟踪误差修复作为声音验收前提。

## 已固定的软件组合

- Agent + 视觉 + 声音组合：`7db4d40e08e7d3d839e6c61602e94c21947ffe0b`。
- 视觉源：`fa36bab`；声音源：`0bd88b6` 加 exact-deadline 修复 `dbd8bd5`。
- 三条组合测试直接验证真实规则事件→Agent HTTP→声音 HTTP/WS→非零PCM/
  完成回执，以及讲话打断、连接断开后下一块静默。修复后相关51项通过。
- 这是合成系数与内存PCM验收。没有表情数据集评估，没有真人相机准确率，
  不支持把哭/闹理解为已识别情绪。独立组合QA仍是合并门槛。

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
