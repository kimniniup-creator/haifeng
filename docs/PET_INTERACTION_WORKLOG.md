# 宠物交互软件集成记录

## 首个可测阶段

- 软件owner：Agent服务任务；独立工作树 `D:/haifeng-worktrees/pet-interaction`，分支 `codex/pet-interaction`。单写 pet_interaction、tests/test_pet_interaction*、requirements-pet.txt、专属docs及PROJECT_CONTROL登记；不改其他owner模块内部。
- 统一视觉/语音/操作事件，验证身份、TTL、置信度、来源、去重；实现quiet/attention/thinking/responding/resting与停止/语音抢占、冷却、presence过期。没有长期记忆改写。
- 初次focused测试23项通过；未连接真实服务或设备。纳入动作owner首个模块和QA基线文档；动作自然完成/取消竞态修复仍待其固定提交，首个模块不代表最终动作验收。
- 语音实际接口形状只读核对，兼容整数turn_id和空启动input_id、200 accepted=false；连接必须显式启用，等待语音owner联调窗口。
- 待办：固定本阶段commit交独立QA；纳入动作修复/视觉/语音固定提交；离线组合验收与运行入口复检；集中提交PR。设备共存/现场听感由相应owner与Kim验收。
