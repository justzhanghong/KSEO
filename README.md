<p align="center">
  <img src="assets/kseo-logo.png" alt="KSEO LOGO" width="560" />
</p>

# KSEO

**Kernel, Scheduling & End-to-End Optimizer**

内核、调度与端到端推理优化引擎。

KSEO 参考 GEAK 的 System 与 Kernel 分层设计，组织端到端推理优化流水线：建立基线、采集 Profile、诊断与路由、调用优化子流程、集成候选、端到端验收，再根据结果继续迭代或交付。

优化能力分为 **Configuration、Scheduling、Kernel** 三个子流程。共享 Runner 提供执行、状态和资源能力；System 层负责端到端选择。任务书、历史实验、社区知识和 profiling 都是输入来源，工作流按优化职责划分。

当前提供标准化热点与 Amdahl 排序、配置优先搜索、Scheduling 提案、独立 Kernel oracle 与局部验证、可逆集成、E2E 门禁、恢复和交付包。真实模型通过 Backend adapters 和外部 coding Agent 接入，内置 CPU 示例始终标记为 `synthetic`。

## Architecture

分层架构只展示职责与依赖，层内不混入反馈回路。

![KSEO 分层 Architecture](docs/architecture.svg)

## End-to-End Pipeline

System 层负责外部大流程。下图仅保留一条主线和一条位于主线下方的反馈回路。

![System 端到端大流程](docs/system-workflow.svg)

Configuration、Scheduling 和 Kernel 的内部小流程单独展开，见 [Architecture 与子流程说明](docs/architecture.md)。

## 快速开始

要求 Linux、Python 3.10 及以上和 Git。运行时不依赖第三方 Python 包。

```bash
python3 -m pip install -e .

# 推荐：运行分层流水线，全部为 CPU synthetic 数据，不启动模型
kseo demo --pipeline --run-dir ./runs/demo-pipeline

# 独立配置搜索接口
kseo demo --run-dir ./runs/demo-grid

# 提案协议与源码补丁示例，使用确定性提案器演示，不调用 LLM
kseo demo --agent --run-dir ./runs/demo-agent

kseo status ./runs/demo-agent
```

示例请依次运行，它们共用演示资源锁。pipeline 示例依次演示配置搜索、热点变化、Scheduling 修改、Kernel oracle 提取与冻结、独立局部验证、集成和最终 E2E 复验。其他两个示例保留为基础接口演示。

查看结果：

```text
runs/demo-pipeline/
├── task.json                 冻结合同
├── tools_manifest.json       执行工具与本地负载身份
├── source-base/              历史源码的独立只读起点
├── state.json                状态和最佳候选
├── events.jsonl              追加事件日志
├── proposals/                基础 Agent 请求和提案
├── workflows/                子流程请求、oracle、局部验证和候选
├── workflow-tree.json        System 与内部阶段的对应关系
├── learned-experience.json   本次运行形成的带来源经验
├── trials/                   每次源码、原始结果、门禁和日志
├── bundle/                   最佳配置、源码补丁和 Manifest
└── report.md                 中文状态报告
```

## 接入真实模型

先建立一个业务 profile，固定负载、thinking、warmup、缓存政策、验收规则和预算。此后可以用模型、源码、镜像和服务器信息生成任务：

```bash
kseo init \
  --model /path/to/model \
  --source /path/to/vllm \
  --image registry.example.com/vllm@sha256:YOUR_IMAGE_DIGEST \
  --server gpu-host \
  --profile /path/to/your-profile.json \
  --out task.json

kseo validate task.json
kseo run task.json --run-dir ./runs/model-001
```

不提供 `--profile` 时会生成 A800 长上下文任务草稿。草稿含明确占位符，必须补齐实际 adapter、GPU UUID、模型与负载身份及门禁，设置 `draft=false` 后才能运行。示例阈值不是新模型的默认质量承诺。

真实平台操作由 adapter 完成，KSEO 不会仅凭四类输入自动猜测 AIHub、SSH/Docker 或模型架构细节。可直接包装已有脚本，见 [adapter 接入](docs/adapters.md) 和 [任务合同](docs/task-contract.md)。

## Agent 与源码优化

`optimizer.kind=pipeline` 使用分层流水线：先执行有独立预算的 Configuration sweep，再按当前 Profile 选择 Scheduling 或 Kernel。Kernel 子流程包含 extractor、proposer 和独立 validator，只有局部验证通过的 patch 才能进入 System 集成。

`grid` 和 `agent` 仍保留为基础调用模式；`agent` 读取 `request.json` 并返回 `proposal.json` 和可选 `patch.diff`。

外部 Agent 负责分析和提出假设。KSEO 负责限制参数空间、在独立 Git 副本应用补丁、执行验证和维护最佳有效候选。每次修改都要通过完整门禁；候选不能修改合同或 Validator。KSEO 本身不是 OS sandbox，外部 Agent 的文件和命令权限应由调用它的环境控制。

参见 [Agent 工作流和提案协议](docs/agent-workflow.md)。

## 恢复与重新验收

```bash
kseo resume ./runs/model-001
kseo validate ./runs/model-001/task.json \
  --trial-dir ./runs/model-001/trials/t0001
```

恢复时先终止身份匹配的本地残留子进程，再调用幂等 cleanup adapter 清理本任务的远端资源。清理失败会保留资源租约，阻止其他 run 复用同一资源。候选的部署失败和执行失败可在有限次数内重试，不作为有效性能负分；中断实验会保留并重新执行。

跨机器或不同运行入口必须配置同一个共享 `resources.lock_dir`，并使用一致的物理 GPU UUID 标识。默认锁目录位于 run 的父目录，仅保护使用该目录的控制器。

## 经验转换

经验按 **原则 → 方法 → 场景规则 → 案例与来源** 由粗到细组织：6 条原则、12 个方法、35 条规则、46 个案例，关联 53 条来源记录。原有 9 张代表性卡片和 V4.1 专项包均已纳入；本轮增加 GLM-5.1/5.2、V4-Flash 与 V4.1-Flash 的 20 条跨模型经验，覆盖生产 shape、峰值显存、CUDA Graph、最大瓶颈点、真实 P/D、MTP/Batch/KV 状态、API 与证据审查。

每一层都注明证据边界，案例保留历史观察和原状态。跨模型规则是需要当前任务验证的迁移建议；未闭环根因继续保留未闭环。详见 [分层知识手册](docs/knowledge.md) 与 [案例和来源索引](docs/knowledge-cases.md)。

```bash
kseo knowledge --tree
kseo knowledge --node K04
kseo knowledge --node R15
kseo knowledge --node case:R15
kseo knowledge --hierarchy --context examples/knowledge/glm52-pd-context.json --limit 24

# 原有平面检索和模型 recipe 接口继续可用
kseo knowledge --context your-context.json
kseo recipe deepseek-v4.1-flash --out ./v41-experience.json
kseo knowledge --context examples/knowledge/v41-context.json --limit 40
kseo ingest /path/to/task.md /path/to/acceptance.json --out imported.json
```

`ingest` 建立 `NEEDS_REVIEW` 卡片，做基础脱敏，不会把历史 PASS 自动当作新任务成功。补齐适用条件、来源和迁移限制并审查后，才能接入自动检索。见 [流程与经验迁移](docs/conversion.md)。

Agent 请求新增 `knowledge_hierarchy`，携带原则、所选方法、规则、匹配案例、祖先关系与来源。V4.1 的 `model_recipe` 仍完整提供 11 条现行规则，不受 top-k 截断。2048-token 含义、并发增长阈值和计时口径中的未明确项均保留为待确认，不能自动判 PASS。详见 [V4.1-Flash 优化经验](docs/models/deepseek-v4.1-flash.md)。知识和经验包尚未替代真实部署、warmup 审计和 Feature 采集 adapter。

## 验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

测试覆盖原始请求重算、身份、缓存、精度、源码隔离、门禁、资源、恢复，以及分层路由、冻结 oracle 和局部通过但 E2E 回退。CI 在 Python 3.10 和 3.12 上执行测试及三个 CPU 示例。

本地检查与版本演进见 [验证记录](docs/validation.md)。

## 当前边界

- 已实现 System 与三个优化子流程；实际 GPU 采样、Kernel 提取、平台部署及模型特定操作由 adapter 接入。
- Configuration 使用有限网格搜索；Scheduling 与 Kernel 可接外部 Agent。当前没有内置 LLM 服务凭据或厂商 SDK。
- 最终复验在新的 trial 中运行相同完整合同；独立测试集、冷启动和最终镜像验证需由实际 profile 与 adapter 明确实现。
- `bundle/` 输出本地源码与配置交付包。容器镜像构建、签名、发布和实际 runtime 核验由 build/deploy adapter 负责，KSEO 不会假装已生成或验收真实镜像。
- 性能测量依据 adapter 提供的原始记录。可信 adapter、计时语义和外部 Agent 的运行隔离仍是实验可信度的前提。

[LOGO 说明与生成 prompt](assets/LOGO.md)
