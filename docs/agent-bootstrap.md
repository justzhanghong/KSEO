# 从简要输入到新模型优化

KSEO 的全局默认只定义测量语义和工作约定。模型、输入/输出长度、并发、Thinking、速度/精度阈值和阶段列表属于本次任务，不能继承示例或上一个模型。`K` 标签默认十进制；结构化输入直接使用整数 token、毫秒和 [0,1] 得分。

## 入口与状态

外层 coding Agent 将用户自然语言归一化为 TaskBrief。可参考 [通用输入示例](../examples/brief/model-a.json)，其中数值仅为该示例的任务目标。

```bash
kseo defaults
kseo roles
kseo prepare brief.json --out /path/to/task/intake
# 外层 Agent 读取 intake/bootstrap-request.json，执行下述自举，生成实际 task.json。
kseo doctor /path/to/task/task.json --brief /path/to/task/intake/brief.json
kseo run /path/to/task/task.json --run-dir /path/to/task/run
```

`prepare` 检查本地模型配置、源码引用、平台与凭据文件引用、用户基础镜像，输出规范化 brief、发现报告、不可运行的合同草稿和结构化自举请求。它不读取凭据内容、不启动 GPU、不把配置声明当成模型已支持的证据。

`READY_TO_BOOTSTRAP` 表示输入检查通过；`NEEDS_INPUT_OR_ACCESS` 明确缺少的关键输入。`doctor` 检查合同、brief 绑定及直接 Python adapter 文件，返回 `READY_TO_PREFLIGHT`；这仍是静态检查。真实平台权限、资源、模型 bring-up、服务功能和性能必须由后续真实运行验证。

当前不内置自然语言解析器、LLM 凭据或能适配所有模型的平台执行器。自举请求由外层 coding Agent 执行；不能把生成草稿称为已完成新模型优化。

## 可补全信息与冻结顺序

1. 拉取用户基础源码，将 branch/tag 解析为 commit；读取模型结构、权重文件清单、tokenizer/processor 和量化配置。模型能力声明需由实际 smoke 验证。
2. 读取用户平台文档，探测可用 GPU 型号、UUID、显存、驱动、节点、拓扑、存储和配额。按当前模型选择最小可行的单机或 PD 方案；搜索前冻结 GPU/节点与拓扑。不能把上个模型的 8 GPU、A800 或 PD 设置当默认。
3. 解析用户基础镜像 digest。默认允许更新 Dockerfile、依赖和候选镜像；基础身份保持可追溯，每个候选 build 输出实际镜像 digest、源码和参数摘要。精度/计时/Kernel 验证器位于候选源码以外。
4. 建立可信的 build/deploy/profile/benchmark/quality/API/stability/cleanup adapters、外部开发 Agent 和可选瓶颈分析员。先做 bring-up；任何 `checks=true` 必须来自实际检查，不得用固定布尔值填充 measured 结果。
5. 对本次速度请求使用 native tokenizer 和真实模板，冻结 prompt/token 身份、长度、输出总预算、Thinking、warmup、缓存政策和并发波次。第一次正文 token 的修改必须导致实际 cache-read=0，不能只按字符串不同认定。
6. 使用随仓库交付的本地 GSM8K/RTLBench/LongBenchv2/LiveCodeBench。冻结完整有序 manifest、native prompt token 数、gold/原始测试 payload、extractor/evaluator 摘要。精度线来自本次任务；若需要以基线定线，应先独立完成完整基线并明确形成新任务数值，当前 `prepare` 不会凭空生成质量线。
7. 若要求多轮 KVOffloading，冻结共享历史消息及每次配对请求。两组使用同一候选源码/镜像/模型/拓扑，除 OFF/ON 外参数一致；不能将两组各自生成的不同历史当同一输入。验证实际 offload 读写，不能只看开关。
8. 将探测结果写入真实合同并运行 `doctor --brief`。预算默认 24h、64 次 trial、每候选至多 2 次执行尝试，预留 6h 最终验收；GPU 小时按实际 GPU 数乘总时长确定。用户可以修改操作预算；预算不足不能自动放宽目标。
9. 搜索阶段按阶段目标保留有效进展，但正确性、请求失败和身份门禁始终执行。达到最终速度后，新建部署实例复验全部目标；交付源码 patch、真实镜像身份、配置、证据和平台实际部署/停止/回滚入口。

所有任务文件、构建缓存、数据导出、日志与临时目录应位于本次 `workdir`。凭据只保留外部文件/环境引用，不能进入 Git、镜像层或 Agent 输出。没有用户交付地址时只生成本地 bundle；不能猜测其他仓库地址。

## 统一默认口径

| 项目 | 默认 |
| --- | --- |
| 测速输出总量 | reasoning + final 合计；任务给 256 就合计 256 |
| TTFT | 首个生成的 reasoning 或正文 token；不把 metadata/tool-call 声明当首 token |
| 测速统计 | 每个 shape/并发分别按请求 mean 验收，同时报告 p95/min/max；默认每并发 5 个波次 |
| Prefix-Cache | 开启；冷缓存速度 case 要求实际 cache-read=0；复用场景按独立 case 冻结 |
| Shape warmup | 只选一个 forward shape；其他 shape 的收益必须另测 |
| 多轮收益 | `1 - mean(TTFT_ON) / mean(TTFT_OFF)`，全部冻结请求 pooled mean，包含第一轮；默认 ≥30%，失败不丢弃 |
| 精度输出 | 不加人工 cap；显式请求实际上下文余量，默认不重采样；不能省略参数而落入服务短默认值 |
| 数据 | 本地固定快照；LongBenchv2 保留 525 条及重复，不换官方集、不去重 |
| 稳定性 | 1200 纯文本；实际支持图文时另回放 1200 图文并随机插入图片数 |
| API | 等价 `/metrics` 与 `/v1/metrics`；TTFT、TPOT/说明口径的 ITL、Running、Waiting；核对四项 cache usage 语义 |
| Router / 限流 | 输入超上下文拒绝；输入可容纳时裁剪输出预算并正常返回；全局请求数/token 队列限制，不私加图片尺寸、像素或格式限制 |

数学等价是所有速度优化的前提，允许浮点本身导致的微小差异。2048-token 小 shape、Feature 选层等 V4.1 专项规则仍按适用范围检索，不自动升级为新模型验收阈值。

## AIHub 支持边界

`kseo.aihub.Client` 提供标准库 REST 调用，包含任务/Pod/存储/配额查询，以及带归属检查、资源上限和 ledger 的创建/停止。调用方从外部 token 文件读取身份；集群 ID、GPU/SKU、节点数必须通过当前平台探测确定。

创建请求结果不确定时 ledger 标记 `UNKNOWN`，不盲目重发 POST。先查询远端并按精确名称、description、owner 摘要及请求内容核对，再恢复；未确认归属不能停止其他任务。仅有开关、Pod 记录或 HTTP 成功不能替代真实测速。

该 client 已通过本地 HTTP fixture 检查协议、幂等、资源限制与归属；尚未在用户集群实测，也不包含自动选择资源、Docker registry、远端命令执行、PD 网络及新模型专用 harness 的完整 Backend。外层 Agent 需要根据给定平台文档实现并实测这些 adapters。当前版本的能力边界必须随交付记录保留。
