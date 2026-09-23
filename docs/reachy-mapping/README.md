# 另一台主机的动作与表情映射入口

权威仓库：`https://github.com/kimniniup-creator/haifeng`（私有，另一台主机需有仓库访问权限）。拉取最新 main 后，本目录可离线用于设计映射，不需要连接机器人。

## 文件

- `actions.json`：机器可读资产表，包含 85 个情绪/表情、19 个官方舞蹈、16 个音乐舞蹈，共 120 个本次服务可枚举资产；另保留界面上缺失的 `headbanger_combo`，总计 121 行。
- `openapi.motion.json`：当前服务动作、状态、健康检查的 OpenAPI 子集及递归依赖 schema。仅为接口结构快照，不包含主机 IP、密钥、个人记忆或媒体。
- `../REACHY_ACTION_CATALOG.md`：中文语义候选和界面 34 个舞蹈的顺序对照。
- `../../patches/reachy_expression/`：当前主机的录制动作保护补丁、安装与回滚说明。不要在远端盲目安装；原生 SDK 与 Codex 隔离副本曾不一致。

`actions.json` 的唯一键为 `dataset + '/' + action_id`。`listed` 是 2026-09-23 源主机枚举结果，不能作为另一台机器的实时可用性；`physical_verified=false` 表示此交付未完成逐项实体动作验收。`ui_group/ui_order` 保留审阅的桌面源码显示顺序。情绪 UI 常量有 81 项，服务另有 mini-deep-sleep、toc-toc-toc、waiting、wake-mini-up，共 85 项。音乐库另有 2 项没有在 34 个舞蹈入口中显示；没有 UI 入口的行仍保留，不能过滤丢失。

这里的“表情”是 Reachy 的头部/天线/身体情绪动作，不是 M5 屏幕位图；录制资产可能包含声音，但不能当成语音助手 TTS 已接通的证明。

## 最小调用契约

将 `BASE_URL` 配为实际运行机器人 daemon 的地址。另一台电脑上的 `127.0.0.1` 指向它自己，不会指向这台机器人主机。远程映射编辑无需联网；要做实体联调，应先由设备负责人确认可达地址、网络访问及唯一执行窗口。本次没有开放新端口或修改防火墙，也没有验证跨主机直连。不要向公网直接暴露机器人控制服务。

| 方法 | 路径 | 用途与结果 |
|---|---|---|
| GET | `/health-check` | 服务健康检查 |
| GET | `/api/daemon/status` | daemon 与控制循环状态 |
| GET | `/api/motors/status` | 电机模式 |
| GET | `/api/move/recorded-move-datasets/list/{dataset}` | 返回动作 ID 字符串数组；缓存缺失时可能下载资产 |
| POST | `/api/move/play/recorded-move-dataset/{dataset}/{action_id}` | 无需 JSON 请求体，返回 `{"uuid":"..."}` |
| GET | `/api/move/running` | 返回正在执行的 UUID 数组对象 |
| POST | `/api/move/stop` | JSON 请求体 `{"uuid":"实际返回的 UUID"}`；按任务停止，不是全局急停 |
| POST | `/api/move/play/wake_up` | 唤醒动作，返回 UUID |
| POST | `/api/move/play/goto_sleep` | 入睡动作，返回 UUID |
| POST | `/api/move/goto` | 自定义位姿轨迹；字段以 OpenAPI 为准 |
| POST | `/api/move/set_target` | 即时目标；动作正在执行时可能返回 `status=ignored` |

数据集名保留其中的 `/`，例如情绪调用路径：

```text
POST {BASE_URL}/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/attentive1
```

舞蹈用 `pollen-robotics/reachy-mini-dances-library`；音乐用 `Anne-Charlotte/music`，注意大小写。

WebSocket `/api/move/ws/updates`（不在 OpenAPI 中）回传 `type/uuid/details`，事件为 `move_started`、`move_completed`、`move_failed`、`move_cancelled`。先订阅再发动作，按 UUID 关联。HTTP 200 只表示任务创建，不表示完成；断线后任务从 running 消失也不能证明成功，不自动重播物理动作。

缺失数据集/动作返回 404，参数错误通常为 422。当前源主机补丁会对忙碌的录制动作返回 409；其他错误保留状态码与 detail，不用重试循环强行播放。不同主机可能没装补丁，所以调用方必须自行串行化动作、语音驱动运动及 SDK 请求。不要假设 goto/set_target 和录制动作具有完全相同的互斥保护。

## 映射怎么交回

每条规则填写：触发情境、想表达的意思、dataset、action_id、配套回应、优先级、可否打断。不要改动作 ID 或把中文标签当成 API 参数。幅度/时长先作为设计意图记录：录制播放接口没有这两个覆盖参数，需要动作负责人另行适配。

Agent 负责人决定何时选哪条规则，动作负责人维护执行与复位，语音负责人维护声音与时序。实现变更走独立分支/PR；双方不能同时控制实体机器人。

## 验证边界

源主机原生服务报告 SDK 1.8.0。接口与三个数据集通过只读 GET 核对，舞蹈界面常量通过官方桌面源码及截图核对；121 行 JSON 包含 120 行 listed=true 和 1 行 false。未发送动作，未逐个验证轨迹/回位/声音，未验证另一台主机的网络。另一台机器在执行前应重新读取自己的 `/openapi.json` 和三个数据集列表，报告差异，保留缺项状态。
