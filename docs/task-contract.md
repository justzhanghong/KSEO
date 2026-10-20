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
| `optimizer` | `pipeline`、`grid` 或 `agent`、参数空间和最小相对改善幅度 |
| `budget` | baseline 与候选次数、累计时间、GPU 小时和有限重试 |
| `resources` | GPU 数量、统一资源标识、共享锁目录 |
| `final_validation` | 新 trial 完整复验；真实模式必须开启 |

可执行示例见 `examples/demo/task-pipeline.json`、`task.json` 和 `task-agent.json`；A800 草稿见包内 `data/profile-a800.json`，也可通过 `kseo init` 输出。

## System 与子流程配置

推荐 `optimizer.kind=pipeline`。System 先执行 Configuration sweep，再根据当前 Profile 调用 Scheduling 或 Kernel。`steps` 描述每个 E2E trial 的验证过程；`optimizer` 描述如何产生下一个候选，两者的职责不同。

| pipeline 字段 | 含义 |
| --- | --- |
| `space` | Configuration 与 Agent 共同遵守的有限参数空间 |
| `max_config_trials` | Configuration 的候选尝试上限，默认 `max(1, min(4, max_trials // 2))` |
| `max_cycles` | 所有子流程调用上限，包含局部失败、无提案和中断；默认 `max_trials × 2` |
| `min_expected_gain` | 热点预计可节省时间比例的下限；只用于路由 |
| `final_reserve_seconds` | 剩余时间达到此值时停止提出新候选，预留最终复验 |
| `scheduling` | 可选的 Scheduling Agent 命令、超时与源码修改权限 |
| `kernel` | 可选的 extractor、proposer、validator 命令及 `min_speedup` |

pipeline 必须配置 `profile` step，其输出遵守 [标准化 Profile 协议](adapters.md#标准化-profile)。Kernel 必须明确开启源码修改，并提供三个独立配置的角色。最小局部加速比 `min_speedup` 默认 1.0；通过它仍须进入 E2E 验收。

完整配置见 `task-pipeline.json`。外部 Agent 与 Kernel 角色的调用方式见 [工作流协议](agent-workflow.md)。

## 阶段和命令

阶段顺序固定为 `preflight`、`build`、`deploy`、`smoke`、`profile`、`benchmark`、`quality`、`api`、`stability`、`multi_turn`、`final_accuracy`。benchmark 必须存在；真实模式还要求 preflight、cleanup、final_accuracy 和最终复验。实际合同的质量、API 和稳定性门禁需明确列入 steps。`final_accuracy` 只在最终 trial 运行，三套本地冻结测试集必须齐全并配置硬门禁；详见 [最终精度](final-accuracy.md)。

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

pipeline 还会在没有可执行热点、达到子流程次数上限或进入最终复验预留时间时停止。Kernel 局部失败消耗时间与子流程预算，不创建 E2E trial；局部通过后发生 E2E 失败时保留原 best。子流程与 E2E 的状态分别写入 `workflows/` 和 `trials/`，并通过 `workflow-tree.json` 关联。


## 新模型默认与阶段目标

0.5.0 提供 `kseo prepare`：TaskBrief 的具体目标生成草稿，外层 Agent 自动发现其余环境信息后冻结真实合同。模型、长度、并发、Thinking、阈值和 milestone 列表每次输入；不继承示例数值。详见 [自举流程](agent-bootstrap.md) 和 [角色协议](roles.md)。

`validation.milestones` 为有序阶段，每项 `name` 唯一且含同一套 `benchmark.*` 数值 gates，阈值逐步收紧，最后一项与正式性能门禁完全一致。`benchmark.failed_requests == 0` 必须声明 `always_required=true`。阶段搜索只暂缓最终性能线，数值、精度、身份、API、稳定性及零请求失败不放宽。搜索 best 记录 `SEARCH_CORRECTNESS_AND_PROGRESS`；目标未达返回 `TARGETS_NOT_MET`，不能 `COMPLETED`。

`selection_metrics` 为各个 shape/并发的 TTFT/TPOT 指标及本次 target，归一化均值生成 `benchmark.mean_goal_ratio`。System 先比较已完成阶段数，再比较 objective；此评分只用于搜索，不能替代各项硬门禁。

`validation.quality_generation` 与 `quality_manifest` 冻结 GSM8K 的完整有序样本、prompt 摘要及 native token 数。启用时，逐题原始记录另需 `prompt_sha256`、`prompt_tokens`、`thinking`、`max_output_tokens` 和 `generation_policy_sha256`。新默认 `context_remaining` 禁止人工短 cap，计分器仍须是独立可信的实际 evaluator。

## 多轮配对验收

按任务目标启用最终阶段 `multi_turn`，并配置 `validation.multi_turn` 及 `multi_turn.passed == true`。manifest 每项含唯一 `request_id`、`session_id`、从 0 连续的 `turn`、`prompt_sha256`、`input_tokens`、`output_tokens`、`concurrency`；每个 session 至少两轮。

adapter 输出 `multi_turn_runs.off/on`，每组含最终候选的 `artifact_identity`、实际完整 `parameters`、`requests_file` 及 SHA256。两组只允许指定 `parameter_key`（默认 `kv_offloading`）不同。原始每行按 manifest 顺序，另含真实 `status`、`ttft_ms`、`cache_read_tokens`、`offload_read_bytes` 和 `offload_write_bytes`。

默认按包括第一轮的全部请求 pooled mean 计算收益，阈值 ≥30%。有失败不使用其余成功样本伪造完整均值；OFF 组无 offload 读写，ON 组必须有实际读和写。不能把每请求百分比降幅的平均值、p95 或只保留后几轮替代整体均值。两组完整历史输入必须相同，不让各自生成的历史造成配对负载漂移。

## 可更新镜像与最终新部署

新自举合同设置 `validation.docker_artifacts=true`。`inputs.image` 冻结用户基础 digest；build 的 `runtime.artifact` 含实际候选 `image`（完整 digest）、`base_image`、`source_revision` 和 `parameters_sha256`。从 deploy 起，各阶段 runtime 必须携带同一 artifact 和同一 `deployment_id`。build 完成后，后续命令可读取 `KSEO_ARTIFACT_PATH`。

最终 deploy 还需实际 `fresh_deployment=true`，部署 ID 不能复用历史搜索实例。完整通过后的 bundle 记录最终复验的实际镜像，不能误用搜索阶段镜像身份。真实构建、部署、元数据采集仍由可信 Backend 完成；程序不会仅凭字符串声明证明远端构建真实发生。
