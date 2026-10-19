# 流程与经验迁移

迁移围绕优化流程展开。参考 GEAK 将 System 与 Kernel 分层，再把现有实践归入 Configuration、Scheduling、Kernel、Backend adapters、模型 recipe 和 Knowledge。任务书、源码、原始实验与社区方案都可以提供材料。

## 先拆流程，再迁移实现

| 责任 | 迁入内容 | 验收方式 |
| --- | --- | --- |
| System Workflow | 基线、Profile、策略、集成、best、回退、重采样与最终交付 | 所有候选执行同一 E2E 合同 |
| Configuration | flags、env、backend 参数空间与约束 | 有限 sweep，保留失败类别 |
| Scheduling | host、通信、batch、并发和 launch 等热点的修改 | 单次假设、受约束提案、可回退 patch |
| Kernel | 热点提取、shape/dtype/stride、oracle、局部数值与计时 | 独立局部门禁后再做 E2E |
| Backend adapters | 部署、构建、GPU 采样、评测和精确清理 | 核对实际源码、镜像、负载及资源身份 |
| 模型 recipe 与 profile | 模型结构、能力、业务负载、质量和语义约束 | 换模型后重验，不继承历史 PASS |
| Knowledge | 成功、回退、部署失败、无效测量和待验证假设 | 来源可查，附适用条件和迁移限制 |

已实现前三个优化子流程、System 编排与统一运行基础。真实后端仍需接入 extractor、validator、部署与评测脚本。架构及运行顺序见 [Architecture](architecture.md)。

## 从已有材料提取职责

Markdown 可以继续承担目标解释、实验叙述和经验说明。影响执行的部分应进入合同、工具接口和验收代码；源码补丁与原始 trace 直接进入对应工作流的候选和证据。

| 原始内容 | 转换结果 | 需要检查的边界 |
| --- | --- | --- |
| 模型、源码、镜像、服务器 | TaskSpec inputs 和 source | 路径不能替代 commit、digest 与实际 runtime 核对 |
| TTFT、TPOT 和并发目标 | validation cases、gates 与 objective | 固定样本、统计口径和测量生命周期 |
| 精度、Feature、API 验收 | quality/API adapter 与门禁 | 当前有效版本、退役规则和失败计分 |
| 部署和 profiling 命令 | Executor steps 与平台 adapter | 幂等提交、精确清理和资源身份 |
| Baseline 与阶段推进 | System Workflow、Runner 和事件账本 | 局部 PASS、候选 PASS 与最终 PASS 分开 |
| 热点源码与独立算子测试 | Scheduling/Kernel 子流程 | 局部证据不能替代 E2E 验收 |
| 成功和失败实验 | 带条件的经验卡 | 来源、适用范围、观察事实与迁移假设分开 |

## 内置经验

第一批转换了 9 张代表性经验卡：

- Flash async 与 DSpark 方案的历史验收。
- GLM-5.2 的 IndexShare、MTP 与 RDMA 联合优化。
- 改善 TPOT 却回退 TTFT 的被拒候选。
- PP0 首层 shape 导致 warmup 覆盖缺失。
- max_num_seqs 与合同不符的无效测量。
- splitKV 加载失败与拓扑污染的失败分类。
- P/D 前置长度校验和错误响应。
- 候选、最终镜像复验和退役门禁的版本边界。
- 会话隔离事故的初步假设与证据限制。

数据位于 `src/kseo/data/experience.json`。卡片保留模型结构、SM、拓扑和语义条件，移除了内部主机、账号、绝对路径及原始运维日志。历史摘要不是本项目新跑的 GPU 测量。

## 增量导入

```bash
kseo ingest task.md acceptance.json --out imported.json
```

导入器只读取明确指定的文件，建立带来源 SHA256 的 `NEEDS_REVIEW` 记录。它提取与性能和验收相关的原始行，并做基础脱敏；不会从长篇自然语言自动生成可直接执行的部署或门禁。

审查时补齐 applies_to、requires_capabilities、observations、transfer_hypothesis 和 limits，再将状态改为准确的历史结果类别。仅靠关键词不能判断是否已经完成全部验收，因此待审经验默认不参与自动优化。

## 新模型接入顺序

1. 接好 Backend：以已有验收过的脚本建立部署、cleanup、benchmark 和质量 adapter。
2. 固定模型 recipe：明确结构、能力、Workload、精度、缓存和 API 语义边界。
3. 接入 Profile：提供当前候选的热点、占比、可改善空间和原始 trace；配置有限搜索空间。
4. 接入 Scheduling 和 Kernel 角色：让 Agent 返回提案；extractor 与独立 validator 固定局部问题和验收。
5. 运行 System 流水线：配置优先、按热点调用子流程、E2E 拒绝回退、重新采样并最终复验。
6. 归档来源与经验：保存合同、源码、原始证据及条件化结果，供后续任务检索。

GLM 的结构规则应匹配 IndexShare 和 MTP 能力，A800 的算子配置应匹配 SM80。针对单模型得到的成功结果只作为新任务候选，迁移后仍需重测。

历史各模型的完整源码补丁、运维脚本与全部实验尚未全部迁入公开工程。后续按工作流、adapter 和模型 recipe 分批迁移，核对来源及适用边界。`ingest` 是经验导入辅助工具，核心优化循环可以独立运行。
