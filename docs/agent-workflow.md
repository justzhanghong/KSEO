# Agent 工作流与提案协议

KSEO 可以接现有 coding Agent。内置 `demo_proposer.py` 是确定性协议示例，不是 LLM，也不声称具备自主源码分析能力。真实 Agent 通过自己的 CLI 或包装脚本读取请求、分析热点并返回提案。

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

request 含当前合同、context、历史结果、最佳候选、源码目录、proposal_dir 及匹配经验。原始 profiling 和各阶段产物可通过 history 中的 trial directory 在 run_dir 下定位。需要更细的瓶颈信息时，应先检查实际 profiling 产物，不从 kernel 名称猜测端到端收益。

## 提案

```json
{
  "parameters": {"chunk_tokens": 1024},
  "hypothesis": "根据 profile 检验当前 Scheduling 参数是否导致 launch 与等待开销",
  "patch": "patch.diff"
}
```

patch 是可选项，相对 proposal_dir 解析，必须位于该目录内。KSEO 在新的源码副本上执行 `git apply --check`、应用并提交补丁；失败不会污染历史源码。未开启 allow_source_changes 时拒绝 patch。

完成探索时输出：

```json
{"stop": true, "reason": "当前预算下没有足够证据支持下一个候选"}
```

## 给外部 Agent 的工作约定

1. 先核对模型结构、硬件和 workload；按当前合同读取允许项和禁止项。
2. 结合实际端到端关键路径提出一个可检验假设，先考虑成本较低的配置和后端调整。
3. 源码或 Kernel 修改只针对有证据的热点，保留模型语义和 fallback 要求。
4. 原始 source_dir、合同、工具和 Validator 保持只读；只向 proposal_dir 写 proposal.json 和 patch。
5. 不得通过更改负载、缓存读取、输出长度、失败样本过滤或质量计分制造收益。
6. 区分无效测量、部署失败、精度失败和真实性能回退；不要把历史假设升级为已证实根因。
7. 不自行宣布通过。提案由 Runner 部署执行，最终以 Validator 的当前合同判定为准。

外部 Agent 的实际权限必须由宿主环境约束。这里的路径限制和事后源码检查是协议校验，并不构成进程级沙箱。
