# 中文情感陪伴语音

使用官方 [Conversation App](https://huggingface.co/spaces/pollen-robotics/reachy_mini_conversation_app) 1.0.1，HF snapshot `ddc309630448a664b0283812ff80048c36966c35`，客户端 SDK 1.11.0。
HF Hosted 实时后端，默认不需 API key；并非离线语音。人格为 `user_personalities/haifeng`，音色 Vivian，转写语言 zh。没有可验证的“全 HF 情感能力第一”排名；选择依据为机器人官方集成、实时双向语音及人格支持。

## 本机安装与使用

已通过客户端 `/api/apps/install` 安装到其 `apps_venv`。由官方客户端独占 daemon 8000。运行中的对话界面为 http://127.0.0.1:7860/ 。麦克风按钮文字 `Mute microphone` 表示当前已开启，点击才静音。

使用 apps_venv 的 Python 执行 `tools/configure_reachy_companion.py`，可部署仓库中的人格与首次启动设置。既有不同配置拒绝覆盖，既有 `.env` 完整保留。不要将运行时密钥、记忆或对话日志提交仓库。

## 临时语音模式

本机启用相机时曾复现流错误及九电机失联；尚不能判定根因。`install_voice_only.py` 为可回滚、严格上游哈希锁定适配：不开相机，不执行启动唤醒，不启动动作循环，不启用说话摇头；仅初始化官方 GStreamer 音频。

安装或回滚前必须停止对话应用。使用客户端 apps_venv 的 Python 执行本目录安装器；传 `--rollback` 恢复备份。官方更新可能覆盖本补丁，不要向未知版本强行应用。该模式不是整机动作安全隔离：其他客户端仍可发动作；应用正常关闭/管理器停止以及官方超长闲置处理可能执行回位。保留唯一硬件操作者。

当前 daemon 媒体已通过 `POST /api/media/release` 释放，避免相机占用；不要在语音测试期间 acquire。重新启动后若相机又出现异常，先停止应用、检查 daemon 实际状态，再释放媒体并启动应用。不要启动项目的第二个 daemon。未设置开机自动启动。

## 验证边界（2026-09-23）

- 官方人格解析器加载通过，音色 Vivian、普通话指令正确；适配 Python 编译通过。
- 实时后端会话初始化成功，设置页显示 Hosted / Ready / Connected；主页进入 Listening，麦克风已启用。
- 日志已收到音频响应增量（一次首段延迟 853 ms）；不能由此证明实体扬声器可闻。
- 当前 daemon running/ready、error=null、nb_error=0。此前小幅动作精度未通过，不能宣称整机稳定。
- 现场中文回复听感待用户确认。情感风格已配置，情感效果尚未主观验收。
