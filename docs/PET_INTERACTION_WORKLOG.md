# 宠物交互软件集成记录

## 首个可测阶段

- 软件owner：Agent服务任务；独立工作树 `D:/haifeng-worktrees/pet-interaction`，分支 `codex/pet-interaction`。单写 pet_interaction、tests/test_pet_interaction*、requirements-pet.txt、专属docs及PROJECT_CONTROL登记；不改其他owner模块内部。
- 统一视觉/语音/操作事件，验证身份、TTL、置信度、来源、去重；实现quiet/attention/thinking/responding/resting与停止/语音抢占、冷却、presence过期。没有长期记忆改写。
- 初次focused测试23项通过；未连接真实服务或设备。纳入动作owner首个模块和QA基线文档；动作自然完成/取消竞态修复仍待其固定提交，首个模块不代表最终动作验收。
- 语音实际接口形状只读核对，兼容整数turn_id和空启动input_id、200 accepted=false；连接必须显式启用，等待语音owner联调窗口。
- 待办：固定本阶段commit交独立QA；纳入动作修复/视觉/语音固定提交；离线组合验收与运行入口复检；集中提交PR。设备共存/现场听感由相应owner与Kim验收。

## 2026-09-24 集成进展

- 已纳入动作4679481停止竞态修复与645c98受限微动作、视觉f450939、语音23a6dc5及前置契约。微动作/profile批准仍关闭。
- QA复现的称呼遮蔽stop与stop_unconfirmed不可见已修复；新35项pet测试通过，包括跨端口进程锁、实际fake TCP往返与生命周期关闭。组合77通过/1真实模型依赖缺失跳过；该轮尚未包含独立micro测试文件，不能将77写成全测试覆盖。
- 实际7860一次WS订阅预检：snapshot accepted、mechanical_only、整数turn_id、semantic_agent_connected=true，退出后已释放；动作调用0、声音调用0。未新开音频进程或注入声音。该证据只说明软件订阅联通。
- 最小规则覆盖唤名/你好/看这里/停止/安静/休息/醒醒，未知语句机械疑惑且不动作。ASR同音别称配置可审阅，原转写不改。
- 后续接口：总控确认事件开始期限与执行budget分离；动作owner在独立提交增加start_deadline/execution_budget_seconds，收到固定SHA后接入，不通过刷新event时间绕过过期。视觉owner正在修角色token、同步consumer例子与presence续租；后端已准备续租无重复动作、断流unknown。

## 最终组合候选

- 视觉71e4706三项接线修复已纳入；语音bc7effd失效订阅恢复已纳入且owner报告live更新。一次真实WS预检后，已启动唯一8091消费者连接既有7860，motion dryrun，不启相机。
- 独立QA已复验12150fc的42项后端/进程/组合测试，包含false租约、两侧停止回执、称呼stop与播放回执身份；动作实体到位测试失败，保持设备动作关闭。
- 动作0b999ac连同前置FK有界归一修正已纳入，pet_motion与owner该SHA逐文件diff一致。Controller传原始start_deadline+10s budget，等待不再按event TTL截断；新增已开始跨事件期限、租约unknown不误取消测试。
- PR #4集中评审；原分支commit与远端一致，阶段文件均在本后台工作树，未抢写共享checkout。等待最终增量QA和总控裁决合main；真人连续语音/手势与动作到位仍独立验收。

- Final follow-up: included motion read-only diagnosis (908810c) and bounded camera-window CLI (c38788d); retained default 15 seconds, explicit maximum 60. Focused vision suite: 25 passed, 1 skipped (real model absent in integration env); no camera opened by these tests. Corrected mapping handoff repository visibility to user-confirmed public. Backend PID46292 stays on tested software; these changes do not require its restart.
