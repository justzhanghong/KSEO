# 任务书与经验转换

现有 Markdown 可以继续承担目标解释、实验叙述和经验说明。KSEO 把其中影响执行的部分移入合同、工具接口和验收代码。

| 原始内容 | 转换结果 | 需要检查的边界 |
| --- | --- | --- |
| 模型、源码、镜像、服务器 | TaskSpec inputs 和 source | 路径不能替代 commit、digest 与实际 runtime 核对 |
| TTFT、TPOT 和并发目标 | validation cases、gates 与 objective | 固定样本、统计口径和测量生命周期 |
| 精度、Feature、API 验收 | quality/API adapter 与门禁 | 当前有效版本、退役规则和失败计分 |
| 部署和 profiling 命令 | Executor steps 与平台 adapter | 幂等提交、精确清理和资源身份 |
| Baseline 与阶段推进 | Runner 和事件账本 | 局部 PASS、候选 PASS 与最终 PASS 分开 |
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

## 扩展路线

先用现有验收过的部署脚本建立可靠 adapter，再导入更多完整证据。GLM 的结构规则应匹配 IndexShare 和 MTP 能力，A800 的算子配置应匹配 SM80。针对单模型得到的成功结果只作为新任务候选，迁移后仍需重测。

当前版本已转换通用执行机制和第一批结构化经验；历史各模型的完整源码补丁、运维脚本与全部实验未被无差别复制进公开工程。它们需要按 adapter 和模型 recipe 分批迁移，并独立审查来源与授权范围。
