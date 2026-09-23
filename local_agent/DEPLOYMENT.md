# 本机照片 Agent 部署

2026-09-24。来源：timesbye/Robot_glasses `b078189` 的 `local_agent`。
本机运行目录：`D:\haifeng-worktrees\upstream-photo-agent\local_agent`。
入口：http://127.0.0.1:8765 。启动：该目录的 `start.ps1`。
`.env` 的 BRIDGE_TOKEN 是网页本地访问口令。
配置、照片、数据库、模型返回和截图均留在 Git 忽略目录，不上传。

## 实际接线

- E06-0055 → 本机已用的 `D:\海风\bridge\luma_ble.py` → 每次独立的新 JPEG。
- 已配置的 DeepSeek Flash → JSON mode → Pydantic 本地校验。
  设置 `MODEL_RESPONSE_FORMAT=json_object`、`MODEL_DISABLE_THINKING=true`。
  原严格 json_schema 接口实测 HTTP 400；没有静默重试或伪造结果。
- Observation 的 `response_emotion` / `emotion_evidence` → 六类固定头部活动。
  分类是机器人对场景的回应，不是对照片人物内心状态的确定判断。
- 无法判断/要求重拍、无依据或 none → 不选动作；每轮保留分类、依据、轨迹和执行状态。
- 六类为 joy / excitement / sadness / anger / confusion / curiosity。
  使用上游小幅头部轨迹；不等于已将34个舞蹈全部映射或验收。
- Reachy API `http://127.0.0.1:8000`。复用原 daemon，不启动第二个设备控制进程。
- 现有声音/视觉服务未替换；旧8088仍为另一个旧入口，请用8765完成照片分类。

## 验证与限制

- 眼镜真实采集成功。首次独立采集10957字节，随后经完整后端任务采集新图。
- 完整任务 `job_d77916767bf84cfab68b220cff4f63f7`，新图
  `img_8b846f42512f4d05a03e93915ff8ccd5`，2026-09-23T19:44:27Z。
  画面为天花板/灯带/窗帘；真实模型返回 limited / none，无明确情绪依据。
  原图已打开核对，与描述一致。自动回话、分类及映射记录成功。
- 55项测试＋新增独立电机门禁1项通过：上游闭环、两种模型格式、六类/none映射、坏质量抑制和采集子进程。
- 桌面1400×900、手机390×844已查看截图，无页面JS异常、无横向溢出。
  证据：仓库 `.runtime/photo-agent-desktop.png`、`.runtime/photo-agent-mobile.png`。
- **机器人实际动作未通过验收。** SDK1.8.0 导出 `backend_status.ready=false`，
  硬件结果 ROBOT_NOT_READY；任务completed不代表机器人动作已完成。
  只读源码审计发现状态导出未同步内部ready Event，不能断言控制循环已停。
  同时只读诊断仍有约10°关节目标/实际偏差。未绕过门禁或做扭矩/动作试验。
  原生状态修复、关节跟踪和真实活动确认已交给现有运动维护owner继续。

模型接口参考：[DeepSeek图像输入](https://api-docs.deepseek.com/guides/vision/)、
[思考模式参数](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 使用

1. 打开8765，填写本地 `.env` 中 BRIDGE_TOKEN 并连接。
2. 让眼镜朝向要分享的场景，点击“拍照分享”。
3. 展开“本轮观察与执行状态”，查看照片分类、映射与动作结果。
4. 机器人未就绪时保留文字和分类，界面如实显示硬件失败。

本机自动记忆设为false。模型密钥沿用项目设置，只存本机 `.env`。
退出服务用启动终端Ctrl+C；运行start.ps1恢复。禁止多worker或并行控制同一副眼镜。

## 用户对准后的复验

用户确认眼镜已对准，真实新拍照任务 `job_5d4fa69e0f224b3ab69e0bec83ce129c`，
图片 `img_746ca63b439b4372bfdfc3814dc45a72`。原图已查看，模型识别到举牌互动，
回应分类 curiosity；这表示机器人的回应选择，不是在判断人物真实情绪。
修正“limited一律不选动作”的过严规则：主体可见、有依据且不要求重拍时允许分类映射。
对同一图片以image任务复验 `job_df5c044badeb4637bf5f42139a0805cc`，未冒充新拍照：
curiosity → roll 6° → 回中。仍返回 ROBOT_NOT_READY，没有设备动作。
`ROBOT_MOTION_ENABLED=false` 独立门禁保证即使原生ready字段后续修复，也不会自动开启
尚未通过物理验证的动作。最终运行PID45980，唯一回环8765监听。

## 2026-09-24 实机动作已打通（覆盖上文"机器人实际动作未通过验收"）

Kim 明确授权小幅实机验证后完成。上文 ROBOT_NOT_READY 与
`ROBOT_MOTION_ENABLED=false` 的结论到此为止，以本节为准。

### 卡点根因

`Robot.capabilities()` 原本只认 `backend_status.ready is True`。原生 daemon 1.8.0
的 `get_status` 从不刷新该字段，它恒为 false，`last_alive` 恒为 null，于是每一轮
都在 `respond()` 里退化成 ROBOT_NOT_READY，动作和语音都没送出去。这不是机器人
掉线：同一时刻 `state=running`、`motor_control_mode=enabled`、`error=null`、
控制环 32Hz、`nb_error=0`、`present_head_pose` 持续刷新。

改为：`ready = 声明值 or 实时控制环证据`。实时证据要求 state 为 running、电机模式
enabled、daemon 与 backend 的 error 均为 null、平均控制环频率大于 1Hz。响应里同时
返回 `backend_ready`（daemon 原始声明值）和 `ready_basis`（declared / control_loop /
none），不掩盖原始字段。停机、电机 disabled、有 error、控制环为 0 或缺失统计时仍为
false，各有回归测试。

### 两道门禁的现状

- `ROBOT_MOTION_ENABLED=true`：本机 `.env` 已开，经 Kim 当面授权。默认仍为 false。
- `ROBOT_SPEECH_ENABLED`：新增，默认 true 以保持上游行为；**本机设为 false**。
  `robot.play()` 会先调 `/api/media/acquire`，那会把 daemon 的相机/音频租约从当前
  持有者手里抢走，而音频属主是 7860 的语音服务。本机因此不隐式发声，
  `speech` 如实显示 `suppressed / ROBOT_SPEECH_DISABLED`，不是失败。

### 实机证据

1. 单段授权探针：指令 pitch 3°（0.052360 rad），WebSocket 收到
   `move_started` → `move_completed`，实测位移 0.052604 rad，偏差 0.000244 rad。
2. `e2e-motion-01`，眼镜实拍新图 `img_022d739bbe34489f926878c1000aa6c9`：
   response_emotion `curiosity` + 可见依据 → selected `curiosity` →
   `head_gesture [[0,6],[0,0]]` → `motion: completed / daemon_move_events`。
   roll 峰值偏移实测 0.10235 rad，指令 0.10472 rad。
3. `e2e-motion-02` 复现同一结论，`motion: completed`。
   两轮 `speech` 均为 suppressed，未占用音频设备。
4. 63 项测试通过（新增就绪判定回退 1 项、无实时证据不放行 5 项、音频租约门禁 1 项）。

### 仍未验收

- **不是精度验收。** 位姿采样间隔 0.2–0.35 秒，可能错过真实峰值；第一轮后
  roll 静止读数一次性偏移约 +0.028 rad，第二轮残差仅 -0.0035 rad，两轮内未见累积
  漂移，但这不足以断言机械精度合格。
- 实体声音未触发，物理可闻性仍未验证。
- `inspect_image` 会写入更新的观察，但任务落库的观察仍是该图第一次的结果，
  情绪映射用的是第一次观察。当前是确定性行为，未改动。
- 上游 `Agent/emo_action` 的六类映射只覆盖小幅头部轨迹，不等于 85 情绪或
  34 舞蹈已映射或验收。

### 启动方式（已改）

`start.ps1` 在前台运行，随启动它的终端一起退出。新增
`start_detached.cmd`：切到工程目录、以 `.venv` 解释器运行 `-m agent_app`、
日志追加到已忽略的 `data\service.log`。需要脱离终端时用
`Invoke-CimMethod Win32_Process Create` 调用它，进程不再挂在终端进程树下。

### 当天的环境事故与恢复（记录，便于复现）

04:12 VS Code 整体重启，把挂在旧终端进程树下的服务全部带走：Reachy daemon 8000、
语音 7860、pet_interaction 8091、旧 bridge 8088。本 Agent 因为改用
`Win32_Process Create` + `start_detached.cmd` 脱离终端启动而存活，
前两次端到端证据是在该次重启之前取得的。

恢复 daemon 的可复现步骤：先启官方客户端，它开出窗口但九分钟内既未派生 daemon
也未监听任何端口，于是关闭客户端，直接用客户端原本那条命令行启动 daemon：

```
"C:\Users\12246\AppData\Local\Reachy Mini Control\.venv\Scripts\python.exe" ^
  "C:\Program Files\Reachy Mini Control\scripts\avast_ssl_fix.py" ^
  --desktop-app-daemon --no-wake-up-on-start --preload-datasets
```

进程表里记录的原始命令行带 `\?\` 扩展长度前缀，经 cmd 规范化会变成相对路径并
报 Errno 22，去掉该前缀即可。约 20 秒后 daemon 恢复 running，
`backend_status.ready` 仍为 false，正是本次就绪判定修复所处理的那个陈旧字段。

恢复后第三次完整运行 `e2e-restored-04`：19.1 秒完成，curiosity →
`[[0,6],[0,0]]` → `motion: completed`，残差 roll +0.003 rad。
语音、pet_interaction 和旧 bridge 属于其他 owner，未在此重启。
