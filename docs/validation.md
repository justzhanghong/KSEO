# 验证记录

本记录描述 KSEO 0.2.1 的工程验证，未启动真实模型或占用 GPU。

| 检查 | 结果 |
| --- | --- |
| Python 3.10 单元与集成测试 | 89 项通过；在 0.2.0 的 72 项基础上增加 17 项模型经验接入检查 |
| CPU Grid search 完整闭环 | 通过，拒绝 TPOT 超限候选并执行最终复验 |
| CPU Agent 协议完整闭环 | 通过，应用独立源码 patch 并完成最终复验 |
| CPU pipeline 完整闭环 | 通过，配置搜索、Scheduling、Kernel、E2E 集成与最终复验 |
| 安装后 CLI 示例 | Grid、Agent 与 pipeline 三个入口均通过 |
| Wheel 内容 | CLI、运行代码、经验库、profile 与示例源码均已包含 |
| 本机 setuptools 59 兼容构建 | 正确生成 kseo 0.2.1 wheel，包含完整经验 recipe |
| Python 语法、JSON、SVG XML、文档链接 | 通过 |

测试覆盖身份不一致、原始结果 hash 被改动、case 和长度不符、缓存证据缺失、质量分母、无效数值、失败清理、资源租约、已完成任务幂等恢复、候选选择恢复和中断重试。

0.2.0 新增检查覆盖：

- Profile 数值、统计范围、关键路径重复计时、基于可改善空间的路由。
- Profile adapter 输出经身份校验后供 System 路由。
- Configuration、Scheduling、Kernel 依次运行；接受候选后使用新 Profile。
- oracle 提案期被改写时拒绝局部候选；事后篡改时独立审计失败。
- Kernel 局部加速但 E2E 回退，拒绝集成并保留原 best。
- 真实控制器进程在 Kernel 提取阶段被 SIGKILL 后，恢复清理孤儿进程并重新执行。
- 局部提案已经完成、E2E 尚未开始时中断，恢复后继续使用已冻结的提案。

Executor 的超时测试还检查父进程退出后，忽略 SIGTERM 的子进程会被终止。HTTP adapter 的测试使用受控 SSE 响应验证实际 usage、reasoning 内容及缺失证据处理，不构成真实 vLLM 服务兼容性测量。

0.2.1 新增模型经验检查覆盖：V4.1 精确身份与别名、跨模型/硬件隔离、现行规则优先、规则不受 top-k 截断、来源引用与三次用户原文 hash、阶段结论边界、CLI 导出与覆盖保护，以及外部 Agent 实际读取完整 recipe 并按协议返回 stop。还检查双 metrics 约束、usage 四字段口径、裁剪后预留、旧图片限制不进入现行规则，以及 1200 文本/条件图文两轮回放要求。

安装后的 17 项经验接入检查与三个 CPU 示例也已通过；完整规则和历史案例分别传给 Agent，避免 top-k 挤掉规则或案例。这组测试验证知识接入和协议，不代表真实单机/P/D 部署、warmup 审计、并发平滑性或 Feature 相似度已经实现。2048 阈值语义及其他未明确参数仍保留待确认状态。

CI 在 Python 3.10 与 3.12 上安装工程，运行全部测试，再依次运行三个 CPU 示例。CPU 示例的性能数据、局部加速比及 E2E 收益均为明确标注的 synthetic 数据，只用于检查控制逻辑。

真实 A800、AIHub、P/D、模型质量、最终镜像固化及长期稳定性需要接好平台 adapter 和模型 profile 后另行验收。
