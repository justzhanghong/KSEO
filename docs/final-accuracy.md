# 优化后的最终精度验收

G-P02 要求在速度优化和最佳产物的 E2E 复验之后，依次验收 **RTLBench → LongBenchv2 → LiveCodeBench**，GSM8K 不能替代这三项。System 的 `final_accuracy` 阶段只在 `phase=final` 运行；baseline/candidate 不重复跑这组昂贵评测。三项缺一、证据缺失或有效性未通过，都不能发布 `COMPLETED`。

0.4.0 起，measured 合同必须声明该阶段、完整三项策略与 `final_accuracy.passed == true` 门禁。旧 measured 合同需要补齐；不能仅把阶段名字或一个 `checks=true` 填进去。synthetic 示例验证控制流，不代表真实数据精度。

真实请求、RTL 编译/仿真、LiveCodeBench 代码执行和语义审阅由独立可信 evaluator/wrapper 完成。KSEO 提供冻结合同、调用 bridge、证据 hash/身份绑定和独立重算，不内置模型部署、Verilog 工具链、OpenCompass 或代码执行沙箱。生成代码必须在评测器自己的隔离环境运行，不在控制器上直接执行。

## 先冻结数据与服务

| 项目 | 要求 |
| --- | --- |
| 数据版本 | 以本地冻结集合为准：RTLBench 160、LongBenchv2 525、LCB code_generation_lite release_v1 400；不换官方版本 |
| 内容身份 | 原文件/数据清单 hash、完整有序 ID、原题、gold/测试 payload；不能只数 ID |
| 最终产物 | 同一源码、镜像、参数、模型、拓扑与实际 runtime；不能为了分数换成另一模型配置 |
| 生成协议 | 每套数据固定 Thinking、输出预算、上下文协议、重试、采样；不能混合 Max/High 或按错题择优 |
| 计分协议 | parser/extractor/evaluator 版本与 hash、原测试和 expected output、失败总分母 |
| 数值线 | 必须由当前合同明确 `min_score` 与 `max_failed_requests`，不继承历史 >0、38%、51.43%、84.15% 等门槛 |
| 有效性 | 检查工具/基准争议和 raw 完整性；分数达线不替代有效性审阅 |

本地 LongBench 的 525 条是 105 条内容各重复 5 次；按用户要求保留全部顺序、ID 和 525 分母，不去重、不替换为官方版本。内容重复作为证据边界披露，成绩不称官方全量。旧 `317/525` 仍是旧合同结果，本轮未请求模型重评。数据和许可证见 [数据清单](datasets.md)。

## 合同字段

`validation.final_accuracy.suites` 必须按 `rtlbench`、`longbench_v2`、`livecodebench_v1` 排列。每项字段如下；当前 A800 profile 中是待补齐草稿，不提供新的通用通过阈值。

| 字段 | 含义 |
| --- | --- |
| `id` / `dataset_id` | suite ID 与 `kseo dataset` 登记的数据版本 |
| `dataset_sha256` | `kseo dataset <id>` 输出的 `dataset_manifest_sha256`；不是随意挑一个源文件 hash |
| `expected_samples` / `manifest` | 完整数量与有序逐样本清单；真实模式还核对登记 ID 和 LongBench 本地 gold |
| `manifest[].prompt_sha256` | 当前 tokenizer/chat template/截断协议下实际完整 prompt 的预先冻结身份 |
| `manifest[].test_payload_sha256` | RTL 原 testbench、LCB 原 public/private tests 与 expected output 的固定身份 |
| `manifest[].gold` | LongBenchv2 本地 A–D 标签 |
| `evaluator_sha256` / `extractor_sha256` | 实际测试器和确定性提取器身份，禁止候选修改 |
| `generation.thinking` | 该 suite 统一的模式标签，逐 attempt 核对 |
| `generation.first_max_output_tokens` / `context_limit` | 当前合同自己的预算和实际上下文限制；必须显式提供 |
| `generation.retry_policy` | `none` 或 `empty_length_once`；后者仅首轮空正文且 length 时再用 context_limit-prompt_tokens 一次 |
| `choice_regex` | LongBench 冻结的单捕获组正则；从 final_content 提取最后一个匹配的 A–D，需符合实际评测协议 |
| `min_score` / `max_failed_requests` | 当前合同的数值与失败门槛 |

不能为满足当前 schema 选择一个会改变原评测语义的 parser；需要别的重试/提取协议时，先扩展版本化 adapter/Validator 并冻结新合同。不得在运行后放宽门槛或改变样本选择。

## 接入三个真实 wrapper

`examples/adapters/final_accuracy_bridge.py` 串行调用已有真实 harness 的三个 wrapper。配置 `KSEO_FINAL_ACCURACY_PLAN` 指向下面结构的 JSON；这是接口示意，路径必须替换为实际审阅过的 wrapper：

```json
{
  "commands": {
    "rtlbench": ["python3", "/path/to/rtl_wrapper.py", "--contract", "{contract_file}", "--out", "{suite_dir}"],
    "longbench_v2": ["python3", "/path/to/longbench_wrapper.py", "--contract", "{contract_file}", "--out", "{suite_dir}"],
    "livecodebench_v1": ["python3", "/path/to/lcb_wrapper.py", "--contract", "{contract_file}", "--out", "{suite_dir}"]
  },
  "timeout_seconds": {"rtlbench": 86400, "longbench_v2": 86400, "livecodebench_v1": 86400}
}
```

上面的超时只演示接口，不是新模型预算承诺。最终阶段和整体预算要覆盖真实测评时长。wrapper 在自己的目录写 `bench-result.json`，bridge 不改答案或运行测试，只规范路径后调用 `emit(benchmarks=...)`。独立包安装后 bridge 可导入 KSEO；所有凭据通过外部环境注入，不写计划文件、日志或 Git。

每个 `bench-result.json` 需要 `id`、冻结的 dataset/evaluator/extractor hash、`generation_policy_sha256`，以及三类产物的相对路径和对应 `<key>_sha256`：

- `attempts_file`：每次真实请求记录 `sample_id`、唯一 `attempt_id`、`prompt_sha256`、完整 `final_content`、`thinking`、`max_output_tokens`、`prompt_tokens`、`finish_reason`。完整原请求/响应另由 harness 留档；严禁仅存提取答案代替原始响应。
- `samples_file`：按冻结 manifest 原顺序，记录 `sample_id`、选定 `attempt_id`、`final_content_sha256`、`status=completed/failed/unparseable`。LongBench 另有 `predicted_choice`；RTL/LCB 有 `test_payload_sha256`、`test_results`。RTL 还需编译/仿真退出码及显式成功/失败标记。
- `validity_review_file`：独立审阅 JSON，含 `status=PASS`、`manifest_sha256=digest(manifest)`、`unresolved_sample_ids=[]`，以及实际审阅依据。不能把“没有检查”写成 PASS；来源缺失或未解决基准问题应保留未通过状态。

KSEO 核对 raw 选择、预算、Thinking、完整 ID/顺序、测试身份和所有 artifact hash，并重算总分母。LongBench 选项只从 final_content 按冻结正则重算；`None of the above` 这类正常但无 A–D 的回答按错计分，不重采样。RTL/LCB 只把严格 bool `true` 的完整测试集合计为通过；`-1/-2` 错误哨兵绝不按 Python 真值计通过。RTL 还要求编译和仿真退出码为 0、有成功标记且无失败标记。

语义审阅和真实测试本身仍信任独立 evaluator，KSEO 不是自动全域正确性证明器。不得为了让有效性审阅通过而创建新的测试期望或按分数改规则。

## 已沉淀的踩坑

| 经验 | 检查原则 | 证据边界 |
| --- | --- | --- |
| B01 数据 ID 与内容重复 | 同时核对内容身份、版本和全量 ID | 本轮证明本地 525→105×5；保留 525 分母，未重测模型 |
| B03 子进程 import 漂移 | 所有 worker 使用冻结 runtime 与 raw hooks | prediction 文件存在不补足缺失 raw |
| B04/B05 RTL fail-open、私改 TB/oracle | 显式终态、原 TB 固定、争议单列 | 旧 148/149 分撤销；旧用户接受 73/160 仅限精确旧版本，不授权新规则 |
| B06 RTL 模块提取 | 完整目标模块、依赖、重复目标与 diff | 不按仿真成败选版本 |
| B07 LCB 首草稿误提取 | 一种确定性 code-generation 规则，全体样本统一重评 | 历史 380→382 不能由单题诊断提前推导 |
| B08 I/O 与错误哨兵 | 文本/二进制共享 buffer；-1/-2 不通过 | 四项预检不是400题模型精度 |
| B09 release_v1 loader | 只读本地冻结 release 文件 | 不因缺 test2 把 v1 判为模型失败 |
| B10/B11 选项、截断、重试 | final-only parser，空 length 才按冻结合同扩容 | 不按低分重采样；历史 131072 等数值不是默认 |
| B12 工具/资源失败 | glibc、编译器、worker、KV 上下文分别归类 | 环境 0 分不是有效模型精度 |
| B13 分数与交付 | 分数、有效性、raw/材料/事件审计分别判定 | 单项和联合达线不消除全历史缺口 |

逐条来源、SHA256 和原结论范围见 [知识手册](knowledge.md) 与 [案例索引](knowledge-cases.md)。本轮参考了所给五类历史目录中的匹配报告，索引扫描到 352 份相关文件，深入核对了与上述规则直接相关的材料；不是全部日志逐行审计。
