# V4.1-Flash 优化经验

本页聚焦 DeepSeek-V4.1-Flash，保留 11 条现行测量/API/稳定性规则和 17 张历史案例卡，关联 27 份历史合同、报告、配置或实验索引，以及原三次用户指令。原有 9 张跨模型代表性经验保留；后续跨模型整理另见 [分层知识](../knowledge.md)。

全部模型还须遵守 [G-P01 数学等价前提](../knowledge.md#g-p01)：速度优化必须数学等价，只允许浮点自身引入的微小差异，并满足预先冻结的数值容差。该通用规则通过 Agent 的 `knowledge_hierarchy` 完整提供；不重新启用本模型已退役的输出文本相似度门禁。

经验包是可供 Agent 读取的结构化 JSON，不是部署 adapter，也不代表本次重新测量了模型。包内 `implementation_status` 明确区分已实现与仍需后端接入的能力。

## 读取与使用

```bash
# 查看已有模型经验包
kseo recipe

# 完整导出当前规则、历史边界、来源与案例
kseo recipe deepseek-v4.1-flash --out ./v41-experience.json

# 按硬件与能力检索；默认 top-8，查全可增加 limit
kseo knowledge --context examples/knowledge/v41-context.json --limit 40
```

任务的 `context.model_family=deepseek_v4_1` 时，Agent 请求自动增加 `model_recipe`，完整包含 11 条规则，不受经验 top-k 截断。历史案例仍按模型、硬件与 capabilities 过滤。Scheduling、Kernel proposer 和基础 Agent 模式共用这一入口。现有部署合同不会被静默改写。

数据位于 [experience-v41.json](../../src/kseo/data/experience-v41.json)。所有新增卡片仅适用于明确匹配的 V4.1-Flash 模型身份；不会因名字包含 Flash 就迁移到 V4-Flash 或 GLM。

## 现行测量与验收规则

| 规则 | 如何执行 | 必须保留的证据 |
| --- | --- | --- |
| V41-P01：Prefix Cache on、首 token 隔离、零命中 | 固定 50K/72K/144K/160K/256K 等长度与 C1-C4；在测试端只换首个用户内容 token，确认 rendered token 只变一处、长度不变且首 block 不同；不发送 cache_salt | 实际开关、tokenizer/template 身份、token diff、首 block 身份、reset 与逐请求 cache usage |
| V41-P02：只 Warmup 一个 shape | 每次正式服务启动后只允许一个预声明 model-forward warmup；其他 forward 也计入；逐个检查非 warmup shape 对 Baseline 的收益 | 从启动起的 forward ledger、唯一 warmup 声明、逐 shape 比较、各 rank 首次路径日志 |
| V41-P03：短输入 TTFT 不反向变慢 | 同服务、同并发、同输出预算下，按实际长度分组；包括冻结 68 样本 | 逐样本长度、时间、完整反向对与计时口径 |
| V41-P04：C1-C4 不应出现 TTFT/TPOT 突增 | 同时看两项指标、相邻档增长率与逐请求分布，定位排队、prefill/decode phase、通信及 KV 压力 | 同步提交证据、逐请求数据和完整并发曲线 |
| V41-P05：Feature 取首个 MoE 下一层的输入 | 仅在合同启用 Feature 时，按实际结构选全局 `first_moe_layer + 1` 的 `layer_input_prenorm`；首个 MoE 在 Layer_0 则取 Layer_1 输入 | 模型结构、完整模块路径、tensor 语义、PP 全局层号与 reference 身份 |
| V41-P06：不验收输出文本相似度 | 不因空字符串的文本相似度为零而拒绝；质量、算子/reference、API 与完成性检查仍按合同执行 | 原始 content/reasoning/tool 流、usage、finish reason、质量失败和不可解析记录 |
| V41-P07：双 metrics 路径 | 对外 `/metrics` 与 `/v1/metrics` 功能等价，返回真实 TTFT、TPOT/decode latency、Running、Waiting | 两路径 idle/load/completed 抓取、指标类型/单位/labels、计数增量与失败响应 |
| V41-P08：Messages usage 四字段 | 逐项区分未读缓存输入、实际输出、独立新建缓存量和实际缓存读取量，流式/非流式一致 | 原始 usage、完整 prompt 计数、服务端缓存计数与 cold/warm/control |
| V41-P09：Router 上下文与输出预算 | 输入超长直接拒绝；输入可容纳但 input+output 越界时裁剪输出，正常调用；裁剪先于 reservation | 实际完整 prompt、requested/effective output、上游调用与 admission 账本 |
| V41-P10：全局双限流，不新增图片限制 | 约束 running+waiting 请求数与 reserved tokens，不额外限制单图高宽/像素或格式白名单 | 全局原子 admission/release、高水位、取消/断连释放与合法图片正例 |
| V41-P11：1200 文本与条件性的 1200 图文回放 | 纯文本 1200 条必跑；图文模型再跑 1200 条随机插图样本，随机结果测试前冻结 | 两轮完整 manifest、首次结果、图片/seed、真实 vision 执行与服务监控 |

首 token 替换必须发生在首个 cache block 中。只改字符、只验证 token 数不变，或只看到 reset 成功都不够；最终仍需真实 usage 的 cache read=0。该变换只用于冻结的性能测试，不能改写真实业务请求。真实 warm-cache、cache 功能和 offloading 命中率实验有独立合同，不套用正式冷缓存速度的零命中要求。

长度标签不能替代实际 tokenizer 计数。256K 输入还要容纳模板和输出预算；超过模型上下文时明确记 BLOCKED，不能静默截断、换短输入或跳过后宣称通过。

## API 与稳定性细则

现有正式接口为 `/v1/messages`；用户原文使用 `/v1/message`。若部署另提供单数兼容入口，它也必须采用相同的 usage 规则。四字段按本 V4.1 自动 Prefix Cache 合同解释：

| 字段 | 含义 |
| --- | --- |
| `input_tokens` | 未从读缓存满足的输入量，等于完整 `server_prompt_tokens - cache_read_input_tokens` |
| `output_tokens` | 实际生成输出，按合同包含 reasoning/tool 生成，不能填请求上限 |
| `cache_creation_input_tokens` | 后端明确报告的独立 cache creation 计数；自动 Prefix Cache 无此独立计数时为 0，不能把 miss 当作 creation |
| `cache_read_input_tokens` | 本次实际缓存读取量，不是写入量或估计值 |

本合同 `server_prompt_tokens = input_tokens + cache_read_input_tokens`，命中率为 `cache_read_input_tokens / server_prompt_tokens`。例如完整输入 1000、读取缓存 600、没有独立 creation 计数时，input=400、creation=0、read=600，命中率 60%。**不能再次把 creation 加进或扣出这个 prompt 公式。** 其他后端若使用三段互斥计费，须显式采用另一合同，不混用字段语义。字段未知不能伪填零，流式累计值与非流式均需核验。

两个 metrics 路径共用真实指标来源与错误语义，不要求不同时间抓取的动态值字节相同。历史后端暴露 ITL histogram，不能仅改名字就宣称等于逐请求 TPOT；映射、单位、类型和口径必须明确。只有路径返回 200 而没有负载中的 Running/Waiting 与 TTFT/decode 样本，不构成验收。

Router 的顺序为：**原生完整 token 计数 → 上下文判断 → 输出预算裁剪 → 全局 reservation → 上游执行 → 终态释放**。输入小于上限时，`effective_max_output_tokens=min(requested_max_output_tokens,max_model_len-prompt_tokens)`。输入已超过上限直接拒绝；输入恰好等于上限且无生成空间时返回明确容量错误，不截断输入或伪造正常生成。缓存命中的输入仍计入 reservation。

限流上限与拒绝响应按当前合同明确，不能默认复制旧的 16 请求/4M token。正常、错误、超时、取消和断连均先终止/关闭上游，再恰好释放一次。旧的单图 1920×1080、像素上限和图片数量默认不继续继承；不自设格式白名单。损坏 base64、无法解码或协议非法仍是输入错误，模型原生 processor 的实际能力也须如实报告。

稳定性执行两个独立验收轮次：

| 轮次 | 数量与条件 | 负载准备 |
| --- | --- | --- |
| 纯文本 | 所有模型都必须回放 1200 条 | 冻结 source_id、顺序、内容、参数和首次尝试，失败留在分母 |
| 图文 | 具备图文能力的模型额外回放 1200 条 | 可以复用同一 1200 文本 source_id，随机插入图片；冻结每条数量、图片 SHA256、顺序、格式、尺寸及 seed |

图文轮每条至少一张有效图，必须证明 vision 路径实际执行，不能人为关闭 vision 以跳过。随机数量的分布/上界是测试集设计参数，不是 API 图片数量限制；不默认复制旧的 1～10 张。两轮分别报告成功/失败、有效输出、超时、崩溃/重启、延迟和 admission 释放。回放并发、成功率等门槛另由当前合同声明，不因跑完 1200 条就自动判 PASS，也不默认增加第三轮。

## 待明确的参数

- **2048 token**：用户已给出阈值；“两个输入的长度差”与“输入总长”的含义仍在确认。包内保留 2048 原值和 `PENDING_USER_CLARIFICATION`，暂按长度差记录，不生成自动硬门禁。
- **缓慢增长**：未给出 C1-C4 的倍率或加速度阈值。保留为诊断原则，不编造 1.1 倍、2 倍等阈值，也不据此宣称自动通过。
- **计时与收益口径**：client TTFT、服务端 effective TTFT，以及逐 shape 的收益定义须由当前任务明确。不同口径不能混用。
- **Feature**：启用状态、阈值与重复次数取当前合同；选层原则不等于自动重新启用历史退役门禁。
- **admission 与回放**：全局请求数/token 额度、拒绝响应，以及随机图片数的分布/上界/seed、回放并发和稳定性阈值仍须明确，不复制历史数值为默认。

## 历史案例与可迁移教训

| 案例 | 历史结果 | 沉淀的教训 |
| --- | --- | --- |
| V41-H01：108K 唯一 warmup 诊断 | 144K TTFT 15.915s，高于 160K 14.099s，拒绝 | 慢区间会随未覆盖的上下文位置移动；Prefix Cache reset 不会清空所有运行时状态；具体算子仍需定位 |
| V41-H02：PP0 mHC 首层 | 50K 触发额外专门化编译，TTFT 高于 144K | 普通层 `[tokens, hc_mult * hidden_size]` 不能代表 PP0 `[tokens, hidden_size]`；修复首次路径，不逐 shape forward 预热规避规则 |
| V41-H03：dynamic MQA 与 sparse 路径 | C1 速度通过，仍因推理期 JIT 拒绝 | 长度动态化之外，还要检查 alignment、stride、relay 数量与专门化 key |
| V41-H04：主矩阵与 API 通过 | 首次 68 样本仍失败 | 规则矩阵不能替代全部 68 样本，不能挑选重测拼接 |
| V41-H05：计时规则修订 | 缺少 server_metrics，结论不确定 | 没有服务端原始时间就不能按服务端新公式重新判 PASS/FAIL |
| V41-H06：首 token 零命中重测 | 协议通过，速度门槛未达成 | 零命中不等于 Prefix Cache 开关对调度无影响，不能拿 cache-off 结果替代正式 cache-on |
| V41-H07：full-batch rotation | prefill 大幅改善，阶段通过但整体未过 | 同时约束 TTFT、TPOT、跨长度顺序与并发曲线 |
| V41-H08：GSM8K 截断后重试超时 | 速度通过但质量候选拒绝 | 区分模型计算与接收链路问题；修复流式接收也要保持生成、重试和计分政策 |
| V41-H09：v2 async/DSpark 最终验收 | 当时合同范围内通过 | 连同 runtime、完整 diff、target verification 和范围版本继承，不能只复制开关名称 |
| V41-H10：exp028 候选 | 候选 PASS，记录仍要求最终镜像复验 | 阶段 PASS 与最终镜像、冷启动及稳定性结果分别记录 |
| V41-H11：KV offloading | 1200 条专项通过，另一个 Speed68 run 因真正空流拒绝 | 命中率/专项 TTFT 通过不代表整个任务通过；停用文本相似度不等于忽略异常响应 |
| V41-H12：shape-padding 与融合 | 历史合同要求 | 内部 padded shape 不能改变真实 token、position、mask、KV slot 与 top-k 语义 |
| V41-H13：PP 跨层依赖和环境 | 加载前失败，未形成有效速度数据 | 检查共享 KV 来源层、PP 切分和依赖版本；不能给未测候选打性能负分 |
| V41-H14：thinking、vision、API | 历史合同要求 | 优化不能绕过实际模型能力；合法请求、超限、取消与状态释放一起回归 |
| V41-H15：usage 四字段 | 历史本地 API 单测 | creation 不应重复扣减 input；流式 cache 状态与字段集合都需检查，不代表真实服务已验收 |
| V41-H16：admission 生命周期 | 历史本地 API 单测 | 取消/断连先关闭上游再释放一次；故意注入的 duplicate release 用于验证检测能力 |
| V41-H17：metrics 代理失败 | 历史本地 API 单测 | upstream HTTP500 或持续 transport 失败要保留明确错误，不能伪装为空 HTTP200 |

数字均来自对应历史报告摘要；本轮没有重新执行 GPU 推理，也没有复核全部 raw。历史建议只有在当前规则允许时才可采用。

## 规则版本和冲突处理

v1/v2 曾在 Prefix Cache off 下测量并要求 Feature/输出相似度；v3 改为 Cache on、无 salt、首 token 隔离，后期又退役两种相似度门禁。68 样本出现过严格顺序、4096-token/0.100s 容差，以及后续任务书中的 4096-token/0.800s 服务端计时规则。

这些都是有版本的历史事实，不能合并成一个通用默认。现行用户规则优先；历史被拒的 run 也不会因本次规则整理而自动翻成 PASS。Feature 启用时遵守本次选层原则，输出文本相似度按本次要求不验收。旧图片宽高/像素和默认数量约束由 P10 覆盖，稳定性两轮由 P11 明确。C04 旧 warmup 建议已经补充单 shape 约束，避免检索时产生相反指令。

每张卡片有 status、适用条件、observations、recommended_actions、required_evidence、source_ids 和 limits。来源索引只公开脱敏相对名称与 SHA256，原始运维日志、内网连接信息和绝对路径不进入公开仓库。

## 当前代码执行到了哪里

已实现：打包加载、条件检索、现行规则优先、Agent 完整注入、CLI 导出；原始 benchmark Validator 已有逐请求 token/缓存证据校验。

仍需真实 Backend adapter 与明确合同：Prefix Cache runtime/首 block 检查、forward ledger 审计、跨 shape 收益与单调性、并发增长阈值、Feature 结构解析和数值采集，以及双 metrics、Messages usage、Router/admission 和两轮 1200 回放。这些尚未完成的检查不会因为 recipe 存在就被标记 PASS。本轮没有增加单机或 P/D 部署 adapter。
