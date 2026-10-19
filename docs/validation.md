# 首版验证记录

本记录描述 KSEO 0.1.0 的工程验证，未启动真实模型或占用 GPU。

| 检查 | 结果 |
| --- | --- |
| Python 3.10 单元与集成测试 | 53 项通过 |
| CPU Grid search 完整闭环 | 通过，拒绝 TPOT 超限候选并执行最终复验 |
| CPU Agent 协议完整闭环 | 通过，应用独立源码 patch 并完成最终复验 |
| 安装后 CLI 示例 | Grid 与 Agent 协议示例通过 |
| Wheel 内容 | CLI、运行代码、经验库、profile 与示例源码均已包含 |
| 本机 setuptools 59 兼容构建 | 正确生成 kseo 0.1.0 wheel |
| Python 语法、JSON、SVG XML、文档链接 | 通过 |

测试覆盖身份不一致、原始结果 hash 被改动、case 和长度不符、缓存证据缺失、质量分母、无效数值、失败清理、资源租约、已完成任务幂等恢复、候选选择恢复和中断重试。

Executor 的超时测试还检查父进程退出后，忽略 SIGTERM 的子进程会被终止。HTTP adapter 的测试使用受控 SSE 响应验证实际 usage、reasoning 内容及缺失证据处理，不构成真实 vLLM 服务兼容性测量。

真实 A800、AIHub、P/D、模型质量、最终镜像固化及长期稳定性需要在用户接好平台 adapter 和模型 profile 后另行验收。
