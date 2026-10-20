# Agent 工作流与提案协议

KSEO 的 System 调用 Configuration、Scheduling 和 Kernel 子流程。后两个子流程可以接现有 coding Agent。内置 proposer 是确定性 CPU 协议示例；真实 Agent 通过自己的 CLI 或包装脚本读取请求、分析热点并返回提案。

## 分层流水线

`optimizer.kind=pipeline` 的完整例子见 `examples/demo/task-pipeline.json`，可执行 `kseo demo --pipeline`。内部顺序和产物见 [Architecture](architecture.md)。

- Configuration 先搜索受约束参数，有独立候选次数上限。
- Scheduling 接收 `workflow.lane=scheduling` 和选定 `workflow.hotspot`，返回参数或源码 patch。
- Kernel 先提取独立任务并冻结 oracle，再调用 proposer，最后调用独立 validator；仅将局部通过的 patch 交回 System。
- System 对每个候选执行完整 E2E 合同，更新 best 和 Profile，再决定下一轮。

以下提案协议同时供基础 `agent` 模式和上述两个 proposer 使用。

## 配置

```json
{
  "kind": "agent",
  "command": ["/path/to/your-agent-wrapper"],
  "timeout_seconds": 600,
  "allow_source_changes": true,
  "space": {"chunk_tokens": [512, 1024, 2048]},
  "min_relative_improvement": 0.005
}
```

命令从 `KSEO_AGENT_REQUEST` 读取 request.json，向 `KSEO_AGENT_PROPOSAL` 指定的位置写 proposal.json。允许参数来自合同 space；未列入 space 的参数保持 baseline 值。

request 含当前合同、context、历史结果、最佳候选、源码目录、proposal_dir 及匹配经验。本次流水线已形成的 `learned-experience.json` 也参与检索。原始 profiling 和各阶段产物可通过 history 中的 trial directory 在 run_dir 下定位。需要更细的瓶颈信息时，应先检查实际 profiling 产物，不从 kernel 名称猜测端到端收益。

明确匹配 V4.1-Flash 时，request 还包含完整 `model_recipe`：现行测量原则、规则版本、来源索引、所需证据和未明确参数。它不受经验 top-k 截断；历史案例与 learned-experience 不得覆盖当前规则。Feature 的条件选层不等于重新启用已退役门禁，未知增长倍率、2048 阈值语义和计时口径不得猜测。recipe 是执行约束与建议，不是已经完成的验收证据。

`knowledge_hierarchy` 提供由粗到细的知识：6 条原则始终携带，按明确条件选中迁移规则，再返回其方法、完整祖先链、匹配模型/硬件/能力的案例和来源。现行规则在该字段中也完整保留，迁移规则默认 top-8；原 `experience` 平面检索接口不变。`navigation_case_ids` 只用于下钻导航，不表示那些案例已经匹配本次上下文。

Agent 必须保留 `evidence_boundary`，区分当前用户规范、历史实测、代码审阅、本地测试与输出因果未闭环。祖先概括、来源 hash、规则命中和历史 PASS 均不能作为当前任务 PASS。未知能力不假定匹配，旧阈值和修复代码不能直接变成新模型默认。参见 [分层知识](knowledge.md)。

Kernel proposer 还会收到 `workflow.oracle_dir`、`oracle_sha256`、`cases` 和 `editable_files`。oracle 只读，patch 必须只修改 editable_files；直接修改 source_dir 或 oracle 会使候选失效。

## 提案

```json
{
  "parameters": {"chunk_tokens": 1024},
  "hypothesis": "根据 profile 检验当前 Scheduling 参数是否导致 launch 与等待开销",
  "patch": "patch.diff"
}
```

patch 是可选项，相对 proposal_dir 解析，必须位于该目录内。KSEO 在新的源码副本上执行 `git apply --check`、应用并提交补丁；失败不会污染历史源码。未开启 allow_source_changes 时拒绝 patch。

`parameters` 必须包含合同的完整参数集合；上例假定合同只有 `chunk_tokens`。Kernel proposer 必须提供实际 patch。参数未列入 space 时，其值必须保持合同 baseline 值。

完成探索时输出：

```json
{"stop": true, "reason": "当前预算下没有足够证据支持下一个候选"}
```

## Kernel extractor 与 validator

三个角色分别配置在 `optimizer.kernel.extractor`、`proposer`、`validator`，每个都使用 `command` 数组和 `timeout_seconds`。`kernel.min_speedup` 控制局部收益下限。extractor 与 validator 接口见 [Kernel adapter](adapters.md#kernel-局部接口)。

extractor 负责从选中热点建立实际调用、输入输出和测试 case。KSEO 随后冻结 oracle 文件集合与 SHA256。proposer 返回 patch 后，控制器在新的 Git 副本应用它，核对修改文件范围，再启动独立 validator。validator 必须核对真实执行路径、数值结果、完整 case 和局部加速比，不能让 proposer 自己写 PASS 代替验证。

局部证据绑定 oracle、patch 与候选 tree。System 集成同一 patch 时重查身份并执行 E2E 验收。局部通过而 E2E 不通过记为 `LOCAL_PASS_E2E_REJECTED`。配置恢复时可继续使用已持久化的待集成提案；执行中断则先清理并重试子流程。

## 给外部 Agent 的工作约定

1. 先核对模型结构、硬件和 workload；按当前合同读取允许项和禁止项。
2. 结合实际端到端关键路径提出一个可检验假设，先考虑成本较低的配置和后端调整。
3. 源码或 Kernel 修改只针对有证据的热点，保留模型语义和 fallback 要求。
4. 原始 source_dir、合同、工具和 Validator 保持只读；只向 proposal_dir 写 proposal.json 和 patch。
5. 不得通过更改负载、缓存读取、输出长度、失败样本过滤或质量计分制造收益。
6. 区分无效测量、部署失败、精度失败和真实性能回退；不要把历史假设升级为已证实根因。
7. 不自行宣布通过。提案由 Runner 部署执行，最终以 Validator 的当前合同判定为准。

外部 Agent 的实际权限必须由宿主环境约束。这里的路径限制和事后源码检查是协议校验，并不构成进程级沙箱。
