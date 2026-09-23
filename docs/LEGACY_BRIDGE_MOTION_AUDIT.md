# 旧 bridge 8088 运动写源只读审计

审计日期：2026-09-24（Asia/Shanghai）。本报告仅包含进程元数据、磁盘源码、配置白名单、现有日志和SQLite只读查询；没有请求任何HTTP/WebSocket API，没有导入生产应用，没有发送事件、停止进程、启动原生app或操作设备。

## 结论

**旧bridge是仍存活、可绕过新MotionExecutor的独立运动写源。** 普通消息得到模型回答后，会自动下发天线两段goto；它不检查新executor的dry-run、mapping/profile批准、会话原点、动作预算或故障锁。仅关闭TTS、关闭网页、保持新executor dry-run，都不能禁用这条写路径。

已有日志证明旧bridge接受过一次消息请求，但**不能证明那次消息确实下发或完成天线运动**。daemon历史日志存在成功接收的goto，但缺少来源PID、请求体、关联业务ID及可用时间戳，不能归因于bridge，也不能据200声称物理到位。当前没有本轮或近期持续写入的直接证据。

## 进程与版本证据

- 本轮fresh查询：PID **33472**，启动时间2026-09-23 13:58:07，监听 **127.0.0.1:8088**；命令为Python 3.12 `-m uvicorn bridge.main:app --host 127.0.0.1 --port 8088`，没有reload参数。
- 父PID **37180** 命令指向 `D:/海风/.venv/Scripts/python.exe`，同一启动时间。`D:/海风/.runtime/bridge.stderr.log`记录Started server process [33472]，与进程吻合；`start.ps1:29`设置项目工作目录并将stdout/stderr重定向到上述runtime目录。
- 审阅磁盘仓库HEAD `6ecdcfcfffa3929d34f96f3b6f7792a0e84fb878`，工作树干净。bridge相关最近提交 `e669660`；adapter/worker/main文件修改时间均早于进程启动。此证据支持代码与启动实例对应，但没有内存代码/进程环境转储，不把磁盘配置等同于已核验进程内部值。
- `.env`白名单只读结果：BRIDGE_HOST=127.0.0.1、BRIDGE_PORT=8088、LUMA_MODE=python、TTS_ENABLED=true；未声明REACHY_HOST/PORT/DATA_DIR时源码默认127.0.0.1:8000及./data。继承环境可能覆盖，未读取敏感进程环境。持久settings仅检查模型配置三字段齐全的布尔值，未输出token、密钥或模型内容。

源码SHA256（不含配置或用户数据）：

| 文件 | SHA256 |
|---|---|
| bridge/robot_adapter.py | b036502c01754dc6cce0b9b542767d32d331330c1d2eca8117668c1acff9afed |
| bridge/worker.py | 9315c6940643b3a5d9205d35008b91ed4dacb8e22772604fef0069a975a59c45 |
| bridge/main.py | 2c8fcb534e29cbd37ec4eb232fa2cfad6285b024400afc475e86640348b22798 |

## 写源及调用链清单

| 入口/触发 | 调用链与写入 | 证据级别/边界 |
|---|---|---|
| 已认证POST /v1/messages；网页message-form submit | main.py:199 → worker.submit(message) → worker.py:110模型回答 → respond(answer):134 → robot_adapter.py:125 acknowledge → _move:46 → POST /api/move/goto | 当前源码可达，消息回答成功后无需再次确认自动触发；日志存在1次202，但没有可归因的下游运动证据 |
| acknowledge内部两段天线动作 | `[0.12,-0.12]`，再`[0,0]`，各duration=1秒；订阅move事件后POST，按UUID等待完成 | 绝对天线目标（约±6.9度），回零不是测得原点；payload没有head_pose但没有证明daemon内部绝不影响其他目标 |
| 请求取消、删除含活动请求的session | main cancel/delete → worker.cancel/cancel_session → robot.stop；若move_id存在则POST /api/move/stop | 代码可达；只处理该adapter记录的UUID，不是新executor的取消/保持协议 |
| acknowledge异常/取消；speak异常/取消 | robot.stop → 同一stop API；还停止自身音频/语音子进程 | 代码可达；stop吞异常、不校验HTTP成功或匹配终态，无保持验证/故障锁 |
| POST /v1/glasses/captures | worker capture分支采集、存图后直接return | 此分支不调用robot；照片随后作为message附件发送才走上面的动作路径 |
| 上传图、列会话、状态、网页bootstrap/刷新 | 存储/读取/状态查询 | 所审代码不触发acknowledge；无定时自动提交消息、视觉事件订阅或语音事件订阅接线 |
| 运行start.ps1（本轮未运行） | 复用/启动8088后调用start_robot.ps1；旧daemon stopped/error时POST daemon/start?wake_up=false，否则可能启动旧reachy-env daemon | 另一路daemon生命周期入口，不经过新executor；不能据no-wake flag保证官方桌面前端无enable/wake回调，后者另行审查 |

RobotAdapter在main.py:24无条件实例化；全仓调用搜索仅发现worker→respond/acknowledge这条生产业务链。RequestWorker的single-consumer队列只串行化8088内部任务，不能与8091新executor、官方桌面应用或其他SDK客户端互斥。

acknowledge仅以daemon state=running且非simulation作为connected条件，不检查motor enabled/error、已有move、当前关节、语音offset、姿态/原点或统一设备lease。POST取消期间也没有新executor的shield/UUID恢复协议；若POST已到达、响应尚未保存move_id时取消，stop可能没有可用UUID。以上为源码风险，不声称本轮实际发生。

## 历史写入证据与缺口

- bridge.stdout.log最后修改2026-09-23 14:03:33，完整内容统计：POST /v1/messages 202一次、POST /v1/glasses/captures 202一次；消息后多次轮询request，捕获后有cancel。日志没有业务终态/robot_json，也没有行级时间戳。
- 对`D:/海风/data/bridge.sqlite3`使用SQLite URI `mode=ro`及query_only查询，requests表当前0行。日志存在历史会话DELETE；因此不能用空表推论过去从未执行，也无法从现存记录恢复那次消息的robot结果。没有读取或上传聊天文本、图片和密钥。
- 历史daemon.stderr.log最后修改2026-09-23 15:15:28，记录POST /api/move/goto 200六次、/api/move/stop 200两次、/api/move/set_target 200两次。邻近还有motor enable及显式天线位置查询，可能来自历史接口排查；来源未被证明。状态200仅证明服务接受请求，不证明执行完成/误差合格。
- 本轮无新API调用、无新请求注入，故没有现场复现或设备状态证据。进程存活与监听不等于它正在写运动。

## 禁用与迁移建议（未执行）

1. **由唯一维护owner隔离旧bridge的硬件输出。** 若旧网页仍需保留，给旧adapter的运动和音频各加默认关闭、fail-closed门禁；关闭时返回明确disabled结果，模型回答/存储可继续。配置TTS_ENABLED=false只影响音频，acknowledge仍先执行，不能作为动作禁用手段。
2. 若旧bridge已无用户用途，由维护owner在协调窗口终止经fresh验证的唯一实例，并禁用旧启动入口自动重建；本QA没有执行停止。仅改源码而不替换长驻uvicorn实例不会改变已加载行为；不要为应用修复启动第二实例。
3. 保留业务时，将动作语义经受认证的统一服务交给唯一MotionExecutor。不要让旧bridge自己创建第二个executor，也不要直接把模型自由文本映射成运动。统一会话/事件期限、批准门、UUID终态、停止失败锁定和设备所有权后再开放。
4. 停用绝对天线回零；若以后确需该动作，使用批准过的相对/原点协议及完整实测验收。迁移前它不能被新look_up的离线通过结论覆盖。
5. 增加不含正文/凭据的审计元数据：UTC时间、组件/进程、业务decision ID、daemon UUID、终态及故障原因。现存日志无法把bridge请求与daemon写入可靠关联；补测应使用假transport，设备验证仍须单独协调。

后续独立项：等待链路owner提供官方桌面自动enable/wake修复的固定提交，审查首次连接、扫描完成、重连及恢复回调；本报告不代替该项，不改变实体动作禁用结论。
