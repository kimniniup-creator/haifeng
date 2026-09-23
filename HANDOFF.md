# 海风交接

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
