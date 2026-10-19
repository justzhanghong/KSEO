# 任务合同

合同使用 JSON，`schema_version` 为 1。运行时将完整配置保存为 `task.json` 并计算 SHA256。恢复时拒绝修改过的合同。

| 字段 | 说明 |
| --- | --- |
| `name` | 英文、数字、下划线和连字符组成的任务标识 |
| `mode` | 必须明确选择 `measured`、`synthetic` 或 `replay` |
| `inputs` | 模型、模型 revision、镜像、负载与 SHA256；真实模式要求 image digest |
| `context` | 经验检索条件，例如 model_family、gpu_arch、backend、capabilities |
| `source` | `git` 加 revision，或小型示例的 `files` 加 include 列表 |
| `parameters` | 完整 baseline 参数 |
| `steps` | 依次执行的命令阶段，每步要求 argv 数组和超时 |
| `cleanup` | 按 run_id/trial_id 精确查找和清理服务的幂等命令 |
| `validation` | case、质量样本数、硬门禁和 objective |
| `optimizer` | `grid` 或 `agent`、参数空间和最小相对改善幅度 |
| `budget` | baseline 与候选次数、累计时间、GPU 小时和有限重试 |
| `resources` | GPU 数量、统一资源标识、共享锁目录 |
| `final_validation` | 新 trial 完整复验；真实模式必须开启 |

可执行示例见 `examples/demo/task.json` 和 `task-agent.json`；A800 草稿见包内 `data/profile-a800.json`，也可通过 `kseo init` 输出。

## 阶段和命令

阶段顺序固定为 `preflight`、`build`、`deploy`、`smoke`、`profile`、`benchmark`、`quality`、`api`、`stability`。只有 benchmark 必须存在；真实模式还要求 preflight 和 cleanup。实际合同需要哪些精度、API 和稳定性门禁，应明确列入 steps。

命令中支持 `{python}`、`{config_dir}`、`{package_dir}`、`{run_dir}`、`{trial_dir}`、`{source_dir}`、`{stage_dir}`。替换后的每个元素仍是一个 argv，不隐式执行 shell。敏感配置通过环境注入，日志默认不记录 argv 或 env；adapter 自身也应避免输出 credentials。

源码 path 相对任务文件目录解析。Git 输入按明确 revision 复制，未提交内容不会进入候选。适配和构建步骤不能修改被冻结的候选源码；如果需要源码修改，应通过 Agent patch 或准备新的 baseline commit 完成。编译产物请写入 run 下的其他目录。

## 性能原始记录与计时

每条完成请求需要 request_id、case_id、status、input_tokens、output_tokens、cache_read_tokens、ttft_ms 和 total_ms。输入输出长度、case 请求数和请求 ID 唯一性必须符合合同。失败请求必须记录，不能通过过滤失败样本提高分数。

TTFT 是合同所规定的首个有效生成 token 到达时间。TPOT 按 `(total_ms - ttft_ms) / (output_tokens - 1)` 重算，因此速度测试至少需要两个输出 token。流式 chunk 不一定对应一个 token，adapter 应使用服务端实际 usage，而不能直接把 chunk 数当作 token 数。

`total_ms` 应使用最后一个生成 token 的时间；若原始 harness 只能提供整个 HTTP 请求结束时间，需要在合同中说明尾部开销并保持所有实验一致。缓存证据缺失不能默认为零。

按 case 计算 mean/min/max 和 nearest-rank p95。样本数较少时 p95 只是该样本集合的顺序统计量，不构成稳定尾延迟结论。

## 质量记录与门禁

quality 可从逐样本 `sample_id`、`correct`、`failed`、`unparseable` 重算准确率，失败与不可解析样本均保留在分母中。retry、截断和答案解析规则由 adapter 固定，不从历史任务自动继承。

门禁示例：

```json
{"name":"长上下文 TPOT","stage":"benchmark","field":"benchmark.cases.long_c1.tpot_ms.mean","op":"<=","value":30}
```

field 以阶段名开头。缺少字段、错误类型和无效数值均不能通过。baseline 性能目标未达成时仍执行后续质量验证，允许进入优化；baseline 的非性能门禁失败会停止优化。

Feature hook、GSM8K 门槛和样本数是模型与合同特定规则。早期层 Feature 相似不能替代完整语义验证；历史上被明确退役的门禁不应自动重新启用。

## 预算和结束语义

`max_trials` 包含 baseline、候选和中断尝试，不包括最后一次复验。`max_attempts_per_candidate` 默认 2，限制配置搜索对部署或执行失败的重试。清理阶段有独立超时，即使优化预算耗尽仍执行。

GPU 小时按声明 GPU 数量乘控制器计费时间保守估算，包含加载、构建、等待和失败开销，并非平台账单。正常中断期间不计费；进程崩溃后不确定是否释放资源的时间保守计入预算。最终复验也消耗预算，预算不足时保留最佳候选并报告未完成复验。

Grid search 在空间耗尽或预算到达后停止。Agent 可以显式 stop。相同源码、patch 和参数的有效重复提案会停止循环；缺少可行候选、资源清理失败和最终验证失败都有独立状态。
