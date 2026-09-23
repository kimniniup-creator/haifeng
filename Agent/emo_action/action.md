# Reachy 网关动作清单

更新时间：2026-09-23 23:09（Asia/Shanghai）
目标：`http://192.168.8.188:8000`
来源：对目标服务的 `GET /openapi.json` 实测结果，以及 `Agent/port.md` 中约定的 WebSocket 通道。

## 端口验证

端口 `TCP/8000` 已开放并由 Reachy daemon 提供 HTTP 服务。验证命令：

```powershell
curl --noproxy "*" --connect-timeout 3 --max-time 8 -i http://192.168.8.188:8000/openapi.json
```

实测结果：`HTTP/1.1 200 OK`，`server: uvicorn`，`content-type: application/json`，OpenAPI 文档大小 `55197` 字节。

OpenAPI 统计：`67` 个 HTTP 路由，其中 `GET 33`、`POST 31`、`DELETE 3`。这次只读取了 OpenAPI 文档，没有调用下方的运动、媒体、音量、daemon 控制或写入型接口。

> `192.168.8.188` 是本次测试地址，不能写死到长期配置；会场 LAN 地址应通过运行时环境变量提供。

## 安全分级

- **查询**：GET 路由通常只读取状态、模型或文件；仍应注意 `GET /api/hf-auth/oauth/start` 会创建 OAuth 会话。
- **状态/配置写入**：应用、daemon、认证、媒体、马达模式、音量和音频配置相关 POST/DELETE 会改变设备或服务状态。
- **运动/声音**：`/api/move/*`、`/api/move/ws/updates`、媒体播放/停止和音量测试可能直接影响机器人或扬声器，未经确认不要调用。
- **文件/凭据**：上传/删除声音、Hugging Face token、应用安装/更新会产生持久化或外部网络副作用。

## HTTP 路由

### 应用管理（`/api/apps`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/apps/list-available/{source_kind}` | 按来源列出可用应用（含未安装） | `source_kind` 路径参数 |
| GET | `/api/apps/list-available` | 列出所有可用应用（含未安装） | 无 |
| POST | `/api/apps/install` | 安装应用，后台返回 `job_id` | JSON `AppInfo` |
| POST | `/api/apps/remove/{app_name}` | 删除已安装应用，后台返回 `job_id` | `app_name` 路径参数 |
| GET | `/api/apps/job-status/{job_id}` | 查询安装/删除/更新任务状态和日志 | `job_id` 路径参数 |
| POST | `/api/apps/start-app/{app_name}` | 启动指定应用 | `app_name` 路径参数 |
| POST | `/api/apps/restart-current-app` | 重启当前应用 | 无 |
| POST | `/api/apps/stop-current-app` | 停止当前应用 | 无 |
| GET | `/api/apps/current-app-status` | 查询当前运行应用状态 | 无 |
| POST | `/api/apps/install-private-space` | 安装私有 Hugging Face Space | JSON `PrivateSpaceInstallRequest` |
| GET | `/api/apps/check-updates` | 检查已安装应用的更新（结果缓存约 5 分钟） | `force` 查询参数，可选 bool |
| POST | `/api/apps/update/{app_name}` | 将已安装应用更新到最新版本 | `app_name` 路径参数 |

### 音频配置（`/api/audio`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| POST | `/api/audio/config/apply` | 批量写入 XVF3800 音频参数并可校验 | JSON `ApplyAudioConfigRequest` |
| GET | `/api/audio/config/parameter/{name}` | 读取单个 XVF3800 参数 | `name` 路径参数 |

### 摄像头、运动学与模型文件

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/camera/specs` | 读取摄像头名称、分辨率、内参 `K` 和畸变参数 `D` | 无 |
| GET | `/api/kinematics/info` | 读取运动学信息 | 无 |
| GET | `/api/kinematics/urdf` | 获取 URDF | 无 |
| GET | `/api/kinematics/stl/{filename}` | 获取指定 STL 文件 | `filename` 路径参数 |

### Daemon 控制与状态（`/api/daemon`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| POST | `/api/daemon/start` | 启动 daemon | 必填查询参数 `wake_up: bool` |
| POST | `/api/daemon/stop` | 停止 daemon，可选择进入睡眠 | 必填查询参数 `goto_sleep: bool` |
| POST | `/api/daemon/restart` | 重启 daemon | 无 |
| GET | `/api/daemon/status` | 读取 daemon、后端和机器人状态 | 无 |
| GET | `/api/daemon/hardware-id` | 读取机器人硬件 ID（Pollen 音频设备 USB 序列号） | 无 |
| GET | `/api/daemon/robot-app-lock-status` | 读取 managed-app 锁状态及持有者 | 无 |

### Hugging Face 认证与中继（`/api/hf-auth`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| POST | `/api/hf-auth/save-token` | 保存并校验 Hugging Face token | JSON `TokenRequest` |
| GET | `/api/hf-auth/status` | 查询 Hugging Face 登录状态 | 无 |
| GET | `/api/hf-auth/relay-status` | 查询中央信令中继连接状态 | 无 |
| DELETE | `/api/hf-auth/token` | 删除已保存 token | 无 |
| POST | `/api/hf-auth/refresh-relay` | 请求中央信令中继重连 | 无 |
| GET | `/api/hf-auth/central-robot-status` | 查询中央服务中的机器人占用状态 | 无 |
| GET | `/api/hf-auth/oauth/configured` | 查询 OAuth 是否已配置 | 无 |
| GET | `/api/hf-auth/oauth/start` | 创建 OAuth 授权会话并返回授权 URL | `use_localhost` 查询参数，可选 bool |
| GET | `/api/hf-auth/oauth/status/{session_id}` | 查询 OAuth 会话状态 | `session_id` 路径参数 |
| DELETE | `/api/hf-auth/oauth/session/{session_id}` | 取消 OAuth 会话 | `session_id` 路径参数 |
| GET | `/api/hf-auth/oauth/callback` | 处理 OAuth 回调 | `code`、`state`、`error`、`error_description` 查询参数，均可选 |

### 媒体与声音（`/api/media`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| POST | `/api/media/release` | 释放媒体资源 | 无 |
| POST | `/api/media/acquire` | 获取媒体资源 | 无 |
| GET | `/api/media/status` | 查询媒体资源状态 | 无 |
| POST | `/api/media/play_sound` | 播放已上传声音 | JSON `PlaySoundRequest` |
| POST | `/api/media/stop_sound` | 停止声音播放 | 无 |
| POST | `/api/media/wobbling/enable` | 启用 wobbling 音频效果 | 无 |
| POST | `/api/media/wobbling/disable` | 禁用 wobbling 音频效果 | 无 |
| POST | `/api/media/sounds/upload` | 上传声音文件 | `multipart/form-data`，字段 `file` |
| GET | `/api/media/sounds` | 列出声音文件 | 无 |
| DELETE | `/api/media/sounds/{filename}` | 删除指定声音文件 | `filename` 路径参数 |

### 马达（`/api/motors`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/motors/status` | 读取马达控制模式 | 无 |
| POST | `/api/motors/set_mode/{mode}` | 设置马达控制模式 | `mode`：`enabled`、`disabled` 或 `gravity_compensation` |

### 运动（`/api/move`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/move/running` | 查询正在运行的运动任务 | 无 |
| POST | `/api/move/goto` | 提交头部/天线/身体 yaw 目标运动 | JSON `GotoModelRequest`，必填 `duration` |
| POST | `/api/move/play/wake_up` | 播放唤醒动作 | 无 |
| POST | `/api/move/play/goto_sleep` | 播放入睡动作 | 无 |
| GET | `/api/move/recorded-move-datasets/list/{dataset_name}` | 列出录制动作数据集 | `dataset_name` 路径参数 |
| POST | `/api/move/play/recorded-move-dataset/{dataset_name}/{move_name}` | 播放录制动作 | `dataset_name`、`move_name` 路径参数 |
| POST | `/api/move/stop` | 停止指定运动任务 | JSON `MoveUUID`，必填 `uuid` |
| POST | `/api/move/set_target` | 设置完整身体目标状态 | JSON `FullBodyTarget` |

### 当前状态（`/api/state`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/state/present_head_pose` | 读取当前头部位姿 | `use_pose_matrix` 查询参数，可选 bool |
| GET | `/api/state/present_body_yaw` | 读取当前身体 yaw | 无 |
| GET | `/api/state/present_antenna_joint_positions` | 读取当前天线关节位置 | 无 |
| GET | `/api/state/doa` | 读取麦克风阵列声源方向（DoA） | 无 |
| GET | `/api/state/full` | 读取完整机器人状态 | 多个可选字段开关：`with_control_mode`、`with_head_pose`、`with_target_head_pose`、`with_head_joints`、`with_target_head_joints`、`with_body_yaw`、`with_target_body_yaw`、`with_antenna_positions`、`with_target_antenna_positions`、`with_passive_joints`、`with_doa`、`use_pose_matrix` |

### 音量（`/api/volume`）

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| GET | `/api/volume/current` | 读取扬声器音量 | 无 |
| POST | `/api/volume/set` | 设置扬声器音量 | JSON `VolumeRequest`，`volume` 为 0–100 整数 |
| POST | `/api/volume/test-sound` | 播放音量测试声音 | 无 |
| GET | `/api/volume/microphone/current` | 读取麦克风音量 | 无 |
| POST | `/api/volume/microphone/set` | 设置麦克风音量 | JSON `VolumeRequest`，`volume` 为 0–100 整数 |

### 其他

| 方法 | 路径 | 用途 | 参数/请求体 |
|---|---|---|---|
| POST | `/health-check` | 重置 daemon 健康检查计时器 | 无 |
| GET | `/` | 返回 daemon dashboard | 无 |

## 请求模型速查

以下是 OpenAPI 中被动作接口直接引用的主要请求模型：

| 模型 | 字段 |
|---|---|
| `AppInfo` | 必填 `name`、`source_kind`；可选 `description`、`url`、`extra` |
| `PrivateSpaceInstallRequest` | 必填 `space_id` |
| `ApplyAudioConfigRequest` | 必填 `config`（`AudioParamPair[]`）；可选 `verify`，默认 `true` |
| `AudioParamPair` | 必填 `name`、`values: number[]` |
| `TokenRequest` | 必填 `token` |
| `PlaySoundRequest` | 必填 `file` |
| `GotoModelRequest` | 必填 `duration`；可选 `head_pose`、`antennas`、`body_yaw`、`interpolation` |
| `MoveUUID` | 必填 `uuid`（UUID） |
| `FullBodyTarget` | 可选 `target_head_pose`、`target_antennas`、`target_body_yaw`、`timestamp` |
| `VolumeRequest` | 必填 `volume`，范围 0–100 |

`head_pose` 可使用 `XYZRPYPose`（`x`、`y`、`z`、`roll`、`pitch`、`yaw`，单位分别为米和弧度）或 16 元素的 `Matrix4x4Pose.m`。`interpolation` 可取 `linear`、`minjerk`、`ease_in_out`、`cartoon`。

应用来源 `source_kind` 可取 `hf_space`、`dashboard_selection`、`local`、`installed`。daemon 状态枚举为 `not_initialized`、`starting`、`running`、`stopping`、`stopped`、`error`；应用状态枚举为 `starting`、`running`、`done`、`stopping`、`error`。

## WebSocket 通道

`port.md` 约定运动更新通道与 HTTP 共用 TCP 8000：

```text
ws://192.168.8.188:8000/api/move/ws/updates
```

HTTPS 场景对应 `wss://.../api/move/ws/updates`。该通道用于订阅运动事件（例如 `move_completed`、`move_failed`、`move_cancelled`），不在本次 OpenAPI `paths` 中登记；连接本身不应提交运动，但通常与 `POST /api/move/goto` 配合使用。

## 结论

当前 `TCP/8000` 已开放，HTTP daemon 正常响应，OpenAPI 可读取并公布 67 个 HTTP 路由。由于本次任务只做能力查询，所有会改变机器人、daemon、媒体、音量、认证或应用状态的接口均未执行。
