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
