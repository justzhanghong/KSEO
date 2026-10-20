# 历史案例与来源索引

本页是分层知识的 L4。观察、原结论状态和迁移边界分别保存；没有本次 GPU 实测。来源 hash 表示原文件身份，不代表公开仓库包含原文件，也不代表已独立重算全部实验。

[返回原则、方法与规则](knowledge.md)

<a id="c01"></a>
## C01 Flash v2 async 与 DSpark 方案验收

归类规则：[R12](knowledge.md#r12)。归类关系不扩大案例结论。

原状态：`FINAL_ACCEPTED_IN_SOURCE_SUMMARY`；适用条件：model_family=deepseek_v4_1；gpu_arch=sm80；target_verified_speculation。

观察事实：

- 39 条速度请求全部输出 256 tokens，无失败
- GSM8K 1288/1319
- 72K C1/C2/C3 满足该任务的 10s/30ms 门槛

证据基础：FINAL_ACCEPTED_IN_SOURCE_SUMMARY；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能由此推导所有模型应开启 async 或 DSpark
- 摘要中的最终通过不等于本次已重新检查全部 raw
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c02"></a>
## C02 GLM-5.2 IndexShare 与 RDMA 联合优化

归类规则：[R10](knowledge.md#r10)。归类关系不扩大案例结论。

原状态：`OPTIMIZATION_ACCEPTED_IN_SOURCE_SUMMARY`；适用条件：model_family=glm5_2；index_share；mtp。

观察事实：

- 50K C1 TPOT 99.02866686749107ms -> 31.3467781209186ms
- 最终路径为 RDMA、IndexShare、MTP skip-topk，实验 sampled-token P2P 路径已移除
- GSM8K accuracy 0.9643669446550417

证据基础：OPTIMIZATION_ACCEPTED_IN_SOURCE_SUMMARY；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 联合结果不能分摊为单项 RDMA 或 skip-topk 收益
- 不同网络拓扑和新模型需独立校验
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c03"></a>
## C03 同步结束与旋转调度造成 TTFT 回退

归类规则：[V41-P04](knowledge.md#v41-p04)。归类关系不扩大案例结论。

原状态：`REJECTED_PERFORMANCE`；适用条件：model_family=deepseek_v4_1。

观察事实：

- 72K C3 TPOT 从约 39.37ms 降至 21.39ms
- 72K C2 TTFT 从约 5.91s 回退至 36.98s
- 性能硬门槛失败，未执行后续精度/API 验收

证据基础：REJECTED_PERFORMANCE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 该实验不能证明所有同步结束方案都无效
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c04"></a>
## C04 mHC warmup 漏掉 PP0 首层专门化

归类规则：[V41-P02](knowledge.md#v41-p02)。归类关系不扩大案例结论。

原状态：`REJECTED_PERFORMANCE`；适用条件：model_family=deepseek_v4_1；mhc。

观察事实：

- 普通 decoder 层使用 [tokens, hc_mult * hidden_size]，PP0 首层还有 [tokens, hidden_size] 路径
- 正式 50K 请求触发 JIT，报告归因为增加约 4s 延迟

证据基础：REJECTED_PERFORMANCE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 该卡不包含 exp009 修复后的独立收益证明
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c05"></a>
## C05 max_num_seqs 不一致使测量失效

归类规则：[E01](knowledge.md#e01)。归类关系不扩大案例结论。

原状态：`INVALID_MEASUREMENT`；适用条件：通用检查；不含新模型的数值默认或通过承诺。

观察事实：

- retry4 被标记 diagnostic only
- 该 run 的 speed、semantic、GSM8K、output、Feature 不能进入正式 seq16 验收

证据基础：INVALID_MEASUREMENT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 该记录不能说明 seq1 参数本身性能差
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c06"></a>
## C06 splitKV16 加载失败不能作为 TPOT 结论

归类规则：[E03](knowledge.md#e03)。归类关系不扩大案例结论。

原状态：`DEPLOYMENT_FAILURE`；适用条件：通用检查；不含新模型的数值默认或通过承诺。

观察事实：

- 模型加载阶段出现 UntypedStorage shape 异常
- 另一个 splitkv4 分支产生 TP2/PP8 拓扑污染并被移出锁

证据基础：DEPLOYMENT_FAILURE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能对 splitKV16 性能打负分或给出不可行结论
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c07"></a>
## C07 P/D 前置长度校验

归类规则：[R09](knowledge.md#r09)。归类关系不扩大案例结论。

原状态：`FIX_ACCEPTED_IN_SOURCE_REPORT`；适用条件：pd_disaggregation。

观察事实：

- 171274 输入 tokens + 32000 输出预算 = 203274，超过模型长度
- guard-off 出现 IncompleteRead，guard-on 返回 HTTP400 context_length_exceeded
- 报告记录修复后观察窗口为 60s

证据基础：FIX_ACCEPTED_IN_SOURCE_REPORT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 60s 无异常不能证明任意负载下长期稳定
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c08"></a>
## C08 候选验收和最终镜像验收分阶段

归类规则：[E02](knowledge.md#e02)。归类关系不扩大案例结论。

原状态：`CANDIDATE_ACCEPTED_PENDING_FINAL_REVALIDATION_AT_THIS_RECORD`；适用条件：通用检查；不含新模型的数值默认或通过承诺。

观察事实：

- candidate_exp028_acceptance.json 的 decision 为 PASS
- 同一记录要求下一步执行 fresh final-image deployment、完整 speed/API 复验和两轮稳定性
- 该任务的 Feature 与输出相似性门禁已按当时用户策略停用；这是历史合同事实，Feature 启用时按当前 V41-P05 选层，不能从本卡推导所有新任务均应停用

证据基础：CANDIDATE_ACCEPTED_PENDING_FINAL_REVALIDATION_AT_THIS_RECORD；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能从候选 PASS 推断此时整个任务完成
- 此卡不否认 execution_status 中后续另一个 service run 的 final_acceptance PASS
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="c09"></a>
## C09 会话串话初步归因保留为假设

归类规则：[E04](knowledge.md#e04)。归类关系不扩大案例结论。

原状态：`HYPOTHESIS_NOT_CONFIRMED_BY_THIS_SOURCE`；适用条件：prefix_cache。

观察事实：

- 初步报告怀疑请求状态或 KV 状态隔离问题
- 报告说明本地网关日志不能直接证明事故实例

证据基础：HYPOTHESIS_NOT_CONFIRMED_BY_THIS_SOURCE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能将这份初步分析中的怀疑对象记为已证实根因
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。
- 原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。

来源：摘要 provenance；无逐卡直接文件 hash。

<a id="v41-h01"></a>
## V41-H01 单次 warmup 改长度，慢区间随未覆盖位置移动

归类规则：[V41-P02](knowledge.md#v41-p02)。归类关系不扩大案例结论。

原状态：`REJECTED_PERFORMANCE`；适用条件：model_family=deepseek_v4_1（含明确别名）；gpu_arch=sm80。

观察事实：

- 108K warmup 后，144K TTFT 为 15.915s，高于 160K 的 14.099s，候选拒绝。
- 报告观察到超过已执行上下文位置的 chunk 明显变慢；正式阶段无已监控 Triton JIT 告警。

证据基础：REJECTED_PERFORMANCE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 候选是 108K warmup 诊断，不能接受为正式阶段；具体一次性开销算子尚未由该记录定位。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S05](knowledge-cases.md#source-v41-s05)。

<a id="v41-h02"></a>
## V41-H02 PP0 首层 mHC 的输入形态不同，普通层覆盖不能代替

归类规则：[V41-P02](knowledge.md#v41-p02)。归类关系不扩大案例结论。

原状态：`REJECTED_PERFORMANCE`；适用条件：model_family=deepseek_v4_1（含明确别名）；gpu_arch=sm80；mhc。

观察事实：

- 普通 decoder 层是 [tokens, hc_mult * hidden_size]，PP0 入口还有 [tokens, hidden_size]。
- 50K 正式请求在尾块触发专门化编译并增加约 4s；50K TTFT 11.040s 高于 144K 6.656s。

证据基础：REJECTED_PERFORMANCE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S06](knowledge-cases.md#source-v41-s06)。

<a id="v41-h03"></a>
## V41-H03 形状长度通用化还要覆盖 alignment 和 stride 专门化

归类规则：[V41-P02](knowledge.md#v41-p02)。归类关系不扩大案例结论。

原状态：`REJECTED_INFERENCE_JIT`；适用条件：model_family=deepseek_v4_1（含明确别名）；gpu_arch=sm80。

观察事实：

- exp016/017 的 C1 速度与顺序门禁通过，但仍因推理期 JIT 拒绝。
- 记录把下一步定位到 runtime-layout 参数的 alignment 等专门化，不能仅看 M 是否 dynamic。

证据基础：REJECTED_INFERENCE_JIT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 这些记录没有证明所有 dynamic shape 策略无效。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S07](knowledge-cases.md#source-v41-s07)、[v41:S08](knowledge-cases.md#source-v41-s08)。

<a id="v41-h04"></a>
## V41-H04 主矩阵与 API 通过后，68 样本仍可否决候选

归类规则：[V41-P03](knowledge.md#v41-p03)。归类关系不扩大案例结论。

原状态：`REJECTED_SPEED68`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 完整速度矩阵与 API 门禁通过，首轮 68 样本仍失败。
- 报告记录 67 个相邻实际长度比较中 29 个失败，以及一条无可见首 token 的异常响应。

证据基础：REJECTED_SPEED68；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 29 对失败是当时严格规则下的历史结论；本次规则变更后不能无证据重新宣布同一 run 通过。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S09](knowledge-cases.md#source-v41-s09)。

<a id="v41-h05"></a>
## V41-H05 计时口径变更后，缺少服务端字段只能记证据不足

归类规则：[E01](knowledge.md#e01)。归类关系不扩大案例结论。

原状态：`INDETERMINATE_UNDER_AMENDED_RULE`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 历史五个相邻失败由 client TTFT 计算；新合同要求 actual_prefill_s + decode_first_ms/1000。
- 全部 68 条原始记录的 server_metrics 为空，因此不能按新口径接受或拒绝。

证据基础：INDETERMINATE_UNDER_AMENDED_RULE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- INDETERMINATE 不能当作 PASS，也不等同于确认性能退化。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S10](knowledge-cases.md#source-v41-s10)。

<a id="v41-h06"></a>
## V41-H06 零命中不意味着 Prefix Cache 开关对调度没有影响

归类规则：[V41-P01](knowledge.md#v41-p01)。归类关系不扩大案例结论。

原状态：`PROTOCOL_PASS_SPEED_THRESHOLD_NOT_MET`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 首 token 替换且不发送 cache_salt，11 点/39 请求全部完成并零命中。
- 72K C1 TPOT 16.169ms，C3 70.380ms，C8 173.158ms；协议通过但速度门槛未达成。
- 报告中关闭 Prefix Cache 会改变 TTFT/TPOT，不能拿 cache-off 结果替代正式 cache-on 口径。

证据基础：PROTOCOL_PASS_SPEED_THRESHOLD_NOT_MET；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 报告对调度机制的解释是该配置下的归因，不是所有后端的通用根因。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S04](knowledge-cases.md#source-v41-s04)。

<a id="v41-h07"></a>
## V41-H07 旋转调度改善 prefill 后仍须联合约束 TTFT 与 TPOT

归类规则：[V41-P04](knowledge.md#v41-p04)。归类关系不扩大案例结论。

原状态：`STAGE_PASS_FULL_TASK_REJECTED`；适用条件：model_family=deepseek_v4_1（含明确别名）；gpu_arch=sm80。

观察事实：

- full-batch rotation 将 72K C2 TTFT 从约 37.92s 降为 5.91s，C3 从 72.20s 降为 8.50s。
- 阶段 12s/50ms 通过，但 C3 TPOT 39.37ms 且其他 shape 仍异常，整个任务未通过。

证据基础：STAGE_PASS_FULL_TASK_REJECTED；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S11](knowledge-cases.md#source-v41-s11)。

<a id="v41-h08"></a>
## V41-H08 GSM8K 重试超时先区分接收链路与模型计算

归类规则：[R16](knowledge.md#r16)。归类关系不扩大案例结论。

原状态：`REJECTED_GSM_RETRY_TIMEOUT`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 速度与 speed68 通过，但 GSM8K 一条截断后重试在约 900s 超时，完整候选拒绝。
- 原记录要求验证 streamed GSM reception，保持生成、重试、计分和 socket inactivity timeout 不变。

证据基础：REJECTED_GSM_RETRY_TIMEOUT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 该记录不单独证明失败根因是数值精度下降。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S12](knowledge-cases.md#source-v41-s12)。

<a id="v41-h09"></a>
## V41-H09 继承已验收 async/DSpark 配置须同时继承边界与证据

归类规则：[R12](knowledge.md#r12)。归类关系不扩大案例结论。

原状态：`FINAL_ACCEPTED_IN_SOURCE_SUMMARY`；适用条件：model_family=deepseek_v4_1（含明确别名）；target_verified_speculation。

观察事实：

- v2 最终摘要记录 ACCEPTED_FINAL_WITH_USER_SCOPE_UPDATE，且包含明确阶段、质量、runtime 和范围更新来源。
- 摘要列出的通过只适用于它的源码、运行配置、负载和当时合同。

证据基础：FINAL_ACCEPTED_IN_SOURCE_SUMMARY；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能把 v2 cache-off 数据当成 v3 cache-on 的性能参考或最终验收。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S13](knowledge-cases.md#source-v41-s13)、[v41:S02](knowledge-cases.md#source-v41-s02)。

<a id="v41-h10"></a>
## V41-H10 候选 PASS 不能代替最终不可变镜像复验

归类规则：[E02](knowledge.md#e02)。归类关系不扩大案例结论。

原状态：`CANDIDATE_ACCEPTED_PENDING_FINAL_REVALIDATION_AT_THIS_RECORD`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- candidate_exp028_acceptance.json 的 decision 为 PASS，记录仍列出下一步要求。
- v3 要求最终不可变镜像、不外挂源码，并在新部署上完成速度/API 与两轮稳定性。

证据基础：CANDIDATE_ACCEPTED_PENDING_FINAL_REVALIDATION_AT_THIS_RECORD；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 仅说明该记录时间点的阶段边界，不否认后续可能存在独立最终通过。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S14](knowledge-cases.md#source-v41-s14)、[v41:S03](knowledge-cases.md#source-v41-s03)。

<a id="v41-h11"></a>
## V41-H11 KV offloading 专项通过后，真正空流仍能使 Speed68 失败

归类规则：[V41-P06](knowledge.md#v41-p06)。归类关系不扩大案例结论。

原状态：`SCOPED_PASS_AND_SEPARATE_RUN_REJECTED`；适用条件：model_family=deepseek_v4_1（含明确别名）；kv_offloading。

观察事实：

- 冻结 1200 条纯文本 OFF/ON 命中率与配对 effective-TTFT 专项通过。
- 后续 Speed68 中一条 HTTP200、length finish、256 completion tokens 的响应所有 content/reasoning delta 均空且无工具输出，run 被拒绝。

证据基础：SCOPED_PASS_AND_SEPARATE_RUN_REJECTED；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 专项 PASS 不能扩展成模型整体通过；该现象不能从最终 content 为空单独判断。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S15](knowledge-cases.md#source-v41-s15)、[v41:S16](knowledge-cases.md#source-v41-s16)。

<a id="v41-h12"></a>
## V41-H12 shape-padding 与融合优化必须保持真实模型语义

归类规则：[R20](knowledge.md#r20)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CONTRACT_REQUIREMENT`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 合同允许内部执行 shape 改变，但不允许改变真实 token、position、mask、sequence length、KV slot 或 vision 边界。
- 算子等价性要求公式、reference、误差与确定性/near-tie 用例，top-k 不能只比较 cosine。

证据基础：HISTORICAL_CONTRACT_REQUIREMENT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 历史已接受的 TF32/INT8 等路径不构成继续扩大量化范围的授权。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S01](knowledge-cases.md#source-v41-s01)、[v41:S03](knowledge-cases.md#source-v41-s03)。

<a id="v41-h13"></a>
## V41-H13 PP 切分与依赖加载失败不能作为性能负分

归类规则：[E03](knowledge.md#e03)。归类关系不扩大案例结论。

原状态：`DEPLOYMENT_FAILURE`；适用条件：model_family=deepseek_v4_1（含明确别名）；gpu_arch=sm80。

观察事实：

- 索引记录 TP2/PP4 的 10 层切分出现 compressed-KV source layer 缺失，候选在加载前拒绝。
- 另有 Humming 依赖缺失记录，未进入有效速度测量。

证据基础：DEPLOYMENT_FAILURE；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 不能根据加载失败判定该 TP/PP 配置本身性能差或所有模型不支持它。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S17](knowledge-cases.md#source-v41-s17)。

<a id="v41-h14"></a>
## V41-H14 性能改动仍须保持 thinking、vision 与 admission/API 语义

归类规则：[V41-P10](knowledge.md#v41-p10)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CONTRACT_REQUIREMENT`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- V4.1 合同要求 thinking-high 与 vision 实际加载/执行，不能以关闭链路换性能。
- 输入模板、tokenizer、上下文/输出预算和请求状态边界属于验收身份。

证据基础：HISTORICAL_CONTRACT_REQUIREMENT；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 本条来自历史合同；不是本工程已实现对应 GPU/平台 adapter 的声明。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S01](knowledge-cases.md#source-v41-s01)、[v41:S03](knowledge-cases.md#source-v41-s03)。

<a id="v41-h15"></a>
## V41-H15 cache creation 是独立计数，不能再次扣减未命中 input

归类规则：[V41-P08](knowledge.md#v41-p08)。归类关系不扩大案例结论。

原状态：`HISTORICAL_LOCAL_API_TEST`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 历史本地 Messages 单测检查了 cache creation 不减少 uncached input、流式 cache 状态与四字段集合。
- 历史合同明确完整 prompt=input+cache_read；automatic Prefix Cache 无独立 creation 计数时 creation=0。

证据基础：HISTORICAL_LOCAL_API_TEST；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 该来源是本地 API 单测摘要，不是新的 GPU 测量；不能推广到三段互斥计费的其他后端。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S24](knowledge-cases.md#source-v41-s24)、[v41:S21](knowledge-cases.md#source-v41-s21)。

<a id="v41-h16"></a>
## V41-H16 取消/断连先关闭上游，再释放一次全局 reservation

归类规则：[V41-P10](knowledge.md#v41-p10)。归类关系不扩大案例结论。

原状态：`HISTORICAL_LOCAL_API_TEST`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 本地生命周期测试覆盖正常完成、上游异常、客户端取消与断连。
- 测试检查 close 先于 single release，并注入 duplicate release 验证可检测且不重复扣减。

证据基础：HISTORICAL_LOCAL_API_TEST；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 单测主动注入的重复释放错误是检测用例，不应当作生产回放的真实错误计数。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S25](knowledge-cases.md#source-v41-s25)、[v41:S22](knowledge-cases.md#source-v41-s22)。

<a id="v41-h17"></a>
## V41-H17 metrics 代理不能把上游失败掩盖为空的成功响应

归类规则：[V41-P07](knowledge.md#v41-p07)。归类关系不扩大案例结论。

原状态：`HISTORICAL_LOCAL_API_TEST`；适用条件：model_family=deepseek_v4_1（含明确别名）。

观察事实：

- 历史代理单测覆盖可恢复 transport error、持续连接失败及 upstream HTTP500。
- 记录要求保留 upstream HTTP500 状态，持续 transport 失败返回明确 502，不能返回空 HTTP200。

证据基础：HISTORICAL_LOCAL_API_TEST；因果状态：`RETAIN_ORIGINAL_STATUS`。

证据边界：

- 这些是本地代理测试；双公开路径和真实服务可观测性仍需新的 adapter 验收。
- 来源是历史合同/报告，未在本次重跑 GPU；不能把历史结论直接当作新候选通过。
- 未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。

来源：[v41:S27](knowledge-cases.md#source-v41-s27)。

<a id="case-r01"></a>
## case:R01 按真实生产 shape 分布调优，不能只优化一个 micro case：历史案例

归类规则：[R01](knowledge.md#r01)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）。

观察事实：

- GLM-5.1 NVFP4 的 Sparse MLA micro 改善后，50K TTFT 反而达到 36.211/36.786s，劣于该轮约 34.994s 的基准。
- 实际 MQA chunk 包含 (503,50005) 等不整齐形状；v7 相对 v5 在 50K micro 更快，但在 138K micro 没有更快。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 具体 tile、group 阈值和 shape 清单只适用于原模型/版本，不做新模型默认。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S01](knowledge-cases.md#source-cross-s01)、[cross:S02](knowledge-cases.md#source-cross-s02)。

<a id="case-r02"></a>
## case:R02 显存预算同时覆盖 KV 与临时 workspace，KV 预留不是越大越好：历史案例

归类规则：[R02](knowledge.md#r02)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）。

观察事实：

- GLM-5.1 的 group32 micro 变快，但实际请求触发约 3/8GiB 临时 score 分配而 OOM；限制 workspace 后又发生速度回退。
- V4-Flash 的 768K 大 KV 配置在 sparse ragged index 构造中 OOM；1M 最终通过配置同时使用 compact ragged、graphfix 与较小 KV 预留。

证据基础：历史实测/正式报告；因果状态：`COMBINED_CHANGE_NOT_ATTRIBUTED`。

证据边界：

- 不能从组合修复推导某个固定 KV GB 数的单项收益，也不能把首个 warmup 与 hot 请求做直接速度比。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S01](knowledge-cases.md#source-cross-s01)、[cross:S03](knowledge-cases.md#source-cross-s03)、[cross:S04](knowledge-cases.md#source-cross-s04)。

<a id="case-r03"></a>
## case:R03 CUDA Graph capture 与正常执行是两条都要验证的路径：历史案例

归类规则：[R03](knowledge.md#r03)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4（含明确别名）；cuda_graph。

观察事实：

- V4-Flash 1M compact-ragged 首次版本在 capture 内使用 .item() 导致启动失败；graphfix 对捕获路径保留静态宽度，正常执行使用紧凑结构，后续通过。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 旧修复的 dense-width fallback 不是所有新模型的默认；仍要防止该 fallback 造成 OOM。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S03](knowledge-cases.md#source-cross-s03)、[cross:S04](knowledge-cases.md#source-cross-s04)。

<a id="case-r04"></a>
## case:R04 Prefill 与 Decode 的 kernel 参数需要分阶段选择：历史案例

归类规则：[R04](knowledge.md#r04)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）；sparse_attention。

观察事实：

- GLM-5.1 记录显示强制 split-KV 对 decode micro 有利，但 prefill_512 从约 3.667ms 退化到 7.6–8.0ms。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 不能把 split-KV、特定 block size 或 eager/graph 的胜负推广到所有模型。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S01](knowledge-cases.md#source-cross-s01)。

<a id="case-r05"></a>
## case:R05 功能开关不代表可用，先建立精确 backend 能力矩阵：历史案例

归类规则：[R05](knowledge.md#r05)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）。

观察事实：

- GLM-5.1-FP8 Stage55 的 --kv-cache-dtype=fp8 进入配置后仍无可用 sparse MLA backend；SM80 路径不满足另一后端的架构要求。
- 较早 P/D 测试也在该 GLM sparse MLA 组合上遇到同类 backend-selection 拒绝。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 仅证明当时版本的 GLM 路径不支持，不意味着所有 SM80 模型均不支持 FP8 KV。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S05](knowledge-cases.md#source-cross-s05)、[cross:S10](knowledge-cases.md#source-cross-s10)。

<a id="case-r06"></a>
## case:R06 先比较可实现收益上界、测量噪声和目标差距，再投入深度调优：历史案例

归类规则：[R06](knowledge.md#r06)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4（含明确别名）。

观察事实：

- V4-Flash probe191 的理想逐 shape oracle 也只可能回收约 4.69/1.69ms，低于 endpoint 变动量，决策为 REJECT_NO_ACTIONABLE_ENDPOINT_GAIN。
- probe190 在两张关键 GPU 上搜索后仍是当前配置最好，未改生产源码。

证据基础：历史实测/正式报告；因果状态：`SEARCH_UPPER_BOUND_NOT_MEASURED_GAIN`。

证据边界：

- 不能把所有 kernel 都设置相同毫秒阈值；噪声与收益下限取当前合同和重复测量。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S21](knowledge-cases.md#source-cross-s21)、[cross:S22](knowledge-cases.md#source-cross-s22)。

<a id="case-r07"></a>
## case:R07 NCCL/recv 很长可能是等待，最大瓶颈应按依赖关键路径定位：历史案例

归类规则：[R07](knowledge.md#r07)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）；pp。

观察事实：

- GLM-5.1-FP8 trace 中源端 sampled-token broadcast kernel 约 0.024ms，而接收端约 71ms；报告将主要时间归于 readiness wait。
- PP0 cudaGraphLaunch 均值约 65.86ms，其中约 65.01ms 与 NCCL broadcast 重叠。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 该结论不否认真实网络瓶颈；需按当前拓扑重新分解。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S07](knowledge-cases.md#source-cross-s07)、[cross:S08](knowledge-cases.md#source-cross-s08)。

<a id="case-r08"></a>
## case:R08 Profiler 的关联键、时钟和正式计时必须分清：历史案例

归类规则：[R08](knowledge.md#r08)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）。

观察事实：

- PP 分析明确只对同机计算绝对时间差，不直接相减两次跨节点 capture 的绝对时间。
- graph/API 关联同时使用 worker pid 与 correlationId，因为 correlationId 可跨进程重复。
- GLM-5.1 正式 TTFT 为 9984.71ms，profile run 为 10162.18ms；目标判定使用前者。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 未独立重算整份 Nsight SQLite；本轮核对的是原报告的方法与结果。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S07](knowledge-cases.md#source-cross-s07)、[cross:S08](knowledge-cases.md#source-cross-s08)、[cross:S23](knowledge-cases.md#source-cross-s23)。

<a id="case-r09"></a>
## case:R09 P/D 必须证明真实路由，并分解 KV 传输/激活至首 token 的开销：历史案例

归类规则：[R09](knowledge.md#r09)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）；pd_disaggregation。

观察事实：

- GLM-5.1 真 P/D 测量中 prefill 后至首 decode 仍约 1.6–1.8s；多 HCA 确有约 9.4GB 流量，仍不足以达到目标。
- sglang_router 对该 vLLM 路径未提供正式 kv_transfer_params，结果只被当作 diagnostic；直接 Decode 也不算 P/D 正式结果。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- decode_first interval 含多种开销，不能把整个区间都称为纯网线传输；链路吞吐不能从配置带宽推算。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S09](knowledge-cases.md#source-cross-s09)、[cross:S10](knowledge-cases.md#source-cross-s10)。

<a id="case-r10"></a>
## case:R10 模型结构性适配先于性能，IndexShare 的复用范围必须明确：历史案例

归类规则：[R10](knowledge.md#r10)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_2（含明确别名）；index_share。

观察事实：

- GLM-5.2 按 indexer_types 区分完整 Indexer 与 SharedTopKIndexer，避免为共享层加载不存在的权重。
- 无正确 IndexShare 的旧 Feature 参考被归档，在结构正确的 baseline 上重新固定；最终优化还涉及后续 MTP pass 的 top-k 复用。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 仅用于有对应能力的模型；联合 RDMA+IndexShare+MTP 结果不能分摊为单项收益。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S11](knowledge-cases.md#source-cross-s11)。

<a id="case-r11"></a>
## case:R11 远端 KV 首 token 状态与 MTP draft 启动必须分开处理：历史案例

归类规则：[R11](knowledge.md#r11)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）；pd_disaggregation；mtp；pp。

观察事实：

- GLM-5.1 Stage62 中 token_1 已追加，但 num_computed_tokens 仍落后于 prompt；旧 skip-first 条件漏判，首 token 返回前仍做 draft。
- 报告记录修复后 c1/c2 进入通过范围，并保留 target 验证与实际 acceptance 统计。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- output_len<=1 是当时实现的修复条件，不作为所有框架的通用代码。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S12](knowledge-cases.md#source-cross-s12)。

<a id="case-r12"></a>
## case:R12 MTP 通过短 smoke 不代表长输出生命周期正确：历史案例

归类规则：[R12](knowledge.md#r12)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_1（含明确别名）；mtp。

观察事实：

- GLM-5.1 MTP 可完成 50K/4-token smoke；正式 256-token 输出变成 [10,0,0,0,0]，64-token probe 也在 18/21 token 附近失败。
- 原始 Decode 日志可查 sample_tokens RPC timeout 和 EngineDeadError。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 这些是当时候选的失败，不代表后续版本或该算法永远不可用。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S05](knowledge-cases.md#source-cross-s05)、[cross:S06](knowledge-cases.md#source-cross-s06)。

<a id="case-r13"></a>
## case:R13 同请求同 token ordinal 的 accepted-count/correction 在 PP stage 间须一致：历史案例

归类规则：[R13](knowledge.md#r13)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_2（含明确别名）；pp；mtp；async_scheduling。

观察事实：

- GLM-5.2 审阅报告把陈旧 accepted count 导致不同 PP stage correction 分叉，关联到 position/RoPE/KV/Target logits 状态不一致。

证据基础：历史代码因果审阅；未独立重跑；因果状态：`CODE_PATH_SUPPORTED_NOT_REPLAYED`。

证据边界：

- 本轮依据报告中的代码因果分析，没有独立重放全部历史字符损坏请求；不把它写成所有事故的唯一根因。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S13](knowledge-cases.md#source-cross-s13)。

<a id="case-r14"></a>
## case:R14 persistent row 的有效内容长度不能被 chunk 计算进度覆盖：历史案例

归类规则：[R14](knowledge.md#r14)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_2（含明确别名）；persistent_batch；chunked_prefill。

观察事实：

- GLM-5.2 报告区分真实 prompt 40957、bucket active span 92160 和 computed prefix 2048。
- 错误把 active span 92160 写成 2048，condense 仅复制短前缀，目标 row 余段保留旧请求内容。

证据基础：历史代码机制审阅；未独立重跑；因果状态：`CODE_PATH_SUPPORTED_NOT_REPLAYED`。

证据边界：

- 不是要求所有长度都单调增加：MTP rollback 和请求结束/重分配有不同语义，不能一律使用 max() 掩盖问题。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S14](knowledge-cases.md#source-cross-s14)、[cross:S13](knowledge-cases.md#source-cross-s13)。

<a id="case-r15"></a>
## case:R15 跨 Prefill producer 的 KV 复用必须先证明轨迹可互换：历史案例

归类规则：[R15](knowledge.md#r15)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_2（含明确别名）；multi_prefill_producer；pd_disaggregation；prefix_cache。

观察事实：

- GLM-5.2 审阅报告确认可能组合 P0 local prefix 与 P1 remote suffix，且两 producer 的数值轨迹并非 bitwise 可交换。
- 审阅认可 producer-scoped namespace 能阻断混合，但仍指出输出级 same/cross 反事实与正式语义验收缺口。

证据基础：机制报告支持；输出因果尚未完全闭环；因果状态：`OUTPUT_CAUSALITY_OPEN`。

证据边界：

- 确认的是危险混合状态，不把所有字符损坏归因于它；输出闭环仍待补证。
- 不要求用 cache_salt 实现，也不改变现行正式零命中测速无 salt 的规则。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S15](knowledge-cases.md#source-cross-s15)。

<a id="case-r16"></a>
## case:R16 Thinking 模式与输出预算是质量合同，不能把截断直接归因数值精度：历史案例

归类规则：[R16](knowledge.md#r16)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4（含明确别名）；thinking。

观察事实：

- V4-Flash 原 768-token、Thinking High 合同下 128 条长度截断且 final content 为空，整体正确率 1171/1319=88.7794%；可解析子集正确率 98.3207%。
- 原参考关闭 Thinking，不能直接作为同模式精度对照；后来 128K 的新合同与原不可变失败结论分别保存。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- 不自动把 768 或 128K 当新模型默认，也不因该原因豁免质量门禁。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S16](knowledge-cases.md#source-cross-s16)。

<a id="case-r17"></a>
## case:R17 工具消息必须覆盖 tokenizer 的真实对象/序列化边界：历史案例

归类规则：[R17](knowledge.md#r17)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4_1（含明确别名）；tools。

观察事实：

- V4.1 r4 的真实工具回放在 admission 前触发 cannot pickle ValidatorIterator；前 101 次中 41 次 HTTP400。
- 缺陷报告将问题定位到 validated message 容器在转 plain dict 前被 deepcopy；修复后另建候选。

证据基础：历史实测/正式报告；因果状态：`HISTORICAL_RESULT_NOT_INDEPENDENTLY_REPRODUCED`。

证据边界：

- plain dict 是当时修复，不要求所有类型无条件转 dict；必须保留原协议语义。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S17](knowledge-cases.md#source-cross-s17)。

<a id="case-r18"></a>
## case:R18 多模态 cache 同步错误若重试，必须有界且保持一次 admission：历史案例

归类规则：[R18](knowledge.md#r18)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4_1（含明确别名）；multimodal；pp。

观察事实：

- V4.1 r3 合法单图请求因 P0/P1 cache drift 返回 500，同 payload 重试后为 200。
- 缺陷报告要求保留一次外部 admission、关闭首 transport、保存两次 attempt，并在改变 gateway 后用新候选重跑。

证据基础：历史实测/正式报告；因果状态：`MITIGATION_NOT_ROOT_FIX`。

证据边界：

- 一次重试成功只能证明缓解可能，不能声称根治 multimodal cache 同步；禁止把无重试合同静默改成有重试。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S18](knowledge-cases.md#source-cross-s18)。

<a id="case-r19"></a>
## case:R19 部署产物必须按精确服务身份隔离，不能共用 PID/日志/停止标记：历史案例

归类规则：[R19](knowledge.md#r19)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=deepseek_v4（含明确别名）；shared_storage。

观察事实：

- V4-Flash 部署改造将 serve、identity、admission、stop 等按 training_id 隔离；用两个 ID 写 8 类同名文件，路径无交集。
- 报告记录 NFS 集成 10/10、路径单测 4/4，nonce 到 training_id 映射原子发布。

证据基础：历史 NFS 集成与单测报告；因果状态：`LOCAL_TEST_REPORT_ONLY`。

证据边界：

- 报告中的模拟 training ID 不是新真实模型实测；本轮没有执行部署或停止任务。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S19](knowledge-cases.md#source-cross-s19)。

<a id="case-r20"></a>
## case:R20 越界风险要检查真实请求边界；输出根因还须追到真实 query/采样行：历史案例

归类规则：[R20](knowledge.md#r20)。归类关系不扩大案例结论。

原状态：`HISTORICAL_CASE_NOT_RERUN`；适用条件：model_family=glm5_2（含明确别名）；sparse_attention。

观察事实：

- GLM-5.2 审阅发现 block table converter 按行 capacity 而非请求实际长度检查，尾槽风险值得修复。
- 但 max_local=14335 正好来自最后 padding query；最后真实 query 的合法上界是 13342，报告未证实真实采样行读取污染 KV。

证据基础：边界机制代码审阅；输出因果未闭环；因果状态：`OUTPUT_CAUSALITY_OPEN`。

证据边界：

- 修复危险边界不等于已经证明历史输出根因；原审阅也说明部分事故 raw 不可访问。
- 本次仅整理历史知识，未重跑 GPU；迁移建议须在当前合同和实际 runtime 上验证。
- 身份范围：本索引未完整结构化原 GPU、backend commit、拓扑和全部负载；模型/能力匹配只表示案例相关，不代表完整迁移资格。

来源：[cross:S20](knowledge-cases.md#source-cross-s20)。

## 来源记录

本批来源保留已核对的行号锚点与 SHA256；已有 V4.1 索引保留原文件名及 hash。用户规则的 hash 按原文记录，不是性能证据。原有 9 张摘要卡没有逐卡直接 hash，不通过关联其他案例来补造。

<a id="source-cross-s01"></a>
### cross:S01

- 位置：`vllm_a/speed_up_v7/reports/analysis/bottleneck_analysis_30s_20260508.md`，第 50 行；锚点：Discarded Sparse MLA。
- SHA256：`246a17a1838e46c5cd4e39aa084aee84b89aa11db55ddfa1ef0c1f4e78b1c56f`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s02"></a>
### cross:S02

- 位置：`vllm_a/speed_up_v7/logs/build/mqa_logits_v7_correctness_final10_20260514_011903.log`，第 4 行；锚点：case=50k。
- SHA256：`45de60413c654174fc43cfef0ab02e79997aa8c269e59c43d70661afbe9c6cc3`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s03"></a>
### cross:S03

- 位置：`vllm_d/flash0731_speed_up_v3/reports/final_flash0731_speed_up_v3_summary.md`，第 70 行；锚点：Rejected Probes。
- SHA256：`e8608f4e34312229c8d5f976174bfaa3a36df35deddb4234b172b0384712b8ca`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s04"></a>
### cross:S04

- 位置：`vllm_d/flash0731_speed_up_v3/reports/qa/maxlen_1m_shapebucket_min32000_emptycache_compactragged_graphfix_qa.md`，第 54 行；锚点：Earlier 1M probes。
- SHA256：`3486d1bab979835079ddacc148da04c7230d015f22421d038e8d7455e1e48735`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s05"></a>
### cross:S05

- 位置：`vllm_a/fp8_speed_up_v7_tpot/reports/analysis/stage55_mtp_kvcache_findings_20260611.md`，第 45 行；锚点：Formal or longer-output。
- SHA256：`3c1f31b00c93a6d6a461ac400dee581ef9fb82c43eb7ee0ba6402dba6007d73f`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s06"></a>
### cross:S06

- 位置：`vllm_a/fp8_speed_up_v7_tpot/logs/deploy/stage55_mtp_nt1_eager_fastpp_slice_20260612_001658/20260611_161658_decode_rank0.log`，第 4915 行；锚点：RPC call to sample_tokens timed out。
- SHA256：`985acbbcbc05e5082b280ff0e14b49337cfd322fabf88b38eba912039f053679`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s07"></a>
### cross:S07

- 位置：`vllm_a/fp8_speed_up_v6_tpot/reports/analysis/stage50_current_best_token_dependency_timeline_20260606.md`，第 100 行；锚点：Interpretation。
- SHA256：`60f4ed797965d8c0ae6e43acad8119399d9a040af329e1674566052a6b7646df`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s08"></a>
### cross:S08

- 位置：`vllm_a/fp8_speed_up_v6_tpot/reports/analysis/stage50_currentbest_graph_launch_overlap_20260608.md`，第 12 行；锚点：Per-PP Critical-Lane。
- SHA256：`c86b1456a11383aede49115fd243d4535f8fbc0e8247955eb8af7cad6bf94cf1`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s09"></a>
### cross:S09

- 位置：`vllm_a/fp8_speed_up_v4_task_1p1d_v1/reports/analysis/ttft_pd_overhead_diagnosis_20260526.md`，第 5 行；锚点：Current true P/D timing split。
- SHA256：`e8375ed017d35f8719a01d24f7b73e041aa24ace101f7de31df9695941cd57d9`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s10"></a>
### cross:S10

- 位置：`vllm_a/fp8_speed_up_v4_task_1p1d_v1/reports/analysis/glm5_disagg_kv_transfer_diagnosis_20260526.md`，第 31 行；锚点：IB multi-HCA evidence。
- SHA256：`055ad1ce25124710a708445de728df3fd3083031777400cfc4a67aa23b4ff1e2`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s11"></a>
### cross:S11

- 位置：`vllm_a/glm52_speed_up_v1/reports/optimization_summary_20260618_021205.md`，第 38 行；锚点：Source Changes。
- SHA256：`cb428e8f6663583cea6cf09541150f00a70b9dc06cb69553c163ad6463b678b2`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s12"></a>
### cross:S12

- 位置：`vllm_a/fp8_speed_up_v7_tpot/reports/analysis/stage62_tp2pp8_mtp3_skipfirst_splitmerge_fullaccept_20260615_profiler_analysis.md`，第 29 行；锚点：Stage62 observation。
- SHA256：`12504fd99b1f8541789c5a6d4995ca203a1ffba215693d77e6ea4221716d20fe`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s13"></a>
### cross:S13

- 位置：`vllm_a/glm52_speed_up_v2_stable_haproxy_8th_session_error/ok_260824.md`，第 89 行；锚点：根因一：PP Speculative Correction。
- SHA256：`72949afbb88c75cd545cd2361e9f11d928d4537da79bad1d45fea9336ef639d0`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s14"></a>
### cross:S14

- 位置：`vllm_a/glm52_speed_up_v2_stable_haproxy_8th_session_error/ok_260821_v2.md`，第 195 行；锚点：正确逻辑必须让 active length。
- SHA256：`60476bad2d28ecf5c17451637e54266f96cb6ab64c56e9b321f00dbbf0ad3c97`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s15"></a>
### cross:S15

- 位置：`vllm_a/glm52_speed_up_v2_stable_haproxy_8th_session_error/ok_260825.md`，第 10 行；锚点：一句话判断。
- SHA256：`36c9559765c8a9e44f6f3f308fb0cb796a2053f36ddf16ed00977cc5ff500760`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s16"></a>
### cross:S16

- 位置：`vllm_d/flash0731_speed_up_v6_api_2nd/reports/final_failure_report.md`，第 43 行；锚点：GSM8K 失败复核。
- SHA256：`dadb0a12b5d3e74e6055ed8d104f0e4ee45359ad90d691e2c692684b5f2be9e1`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s17"></a>
### cross:S17

- 位置：`vllm_d/flash41_speed_up_v2_api_1st/reports/r4_tool_tokenizer_defect.json`，第 10 行；锚点：cannot pickle。
- SHA256：`da59c5dd195834bb67ac32f754bc0add35e25f8fd6ed2be020cee4ed59fce7b1`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s18"></a>
### cross:S18

- 位置：`vllm_d/flash41_speed_up_v2_api_1st/reports/r3_multimodal_retry_defect.json`，第 9 行；锚点：Multi-modal cache miss。
- SHA256：`3495e08e66486c31086230558b0c8af2bb9441442ad46de296f7d5ad03431e95`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s19"></a>
### cross:S19

- 位置：`vllm_d/flash0731_speed_up_v6_api_2nd/reports/training_id_isolation.md`，第 7 行；锚点：目录合同。
- SHA256：`efa6c52895ba26fee02c726e6c4cba1df289ae1e9415ec02ca35a7787681170b`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s20"></a>
### cross:S20

- 位置：`vllm_a/glm52_speed_up_v2_stable_haproxy_8th_session_error/report_260818_94558_topk_overread_rootcause_response.md`，第 21 行；锚点：决定性问题。
- SHA256：`9913850ed2b083d8751c6088c416f820933ee9df7606d6981dded4e3a18a07ce`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s21"></a>
### cross:S21

- 位置：`vllm_d/flash0731_speed_up_v6/reports/operator/stage6_mqa_physical45_probe191_decision.json`，第 12 行；锚点：gpu4_dynamic_oracle_gain_ms。
- SHA256：`ca1ad85c2759b02d99551f8c565dcb1fe3e06cfc8f86394ae763d485b1177b2b`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s22"></a>
### cross:S22

- 位置：`vllm_d/flash0731_speed_up_v6/reports/operator/stage6_sparse_prefill_physical45_probe190_decision.json`，第 18 行；锚点：REJECT_NO_GAIN。
- SHA256：`18a60e74d120533d7da4c11ba6016a44a04efdae6309d2a576dc709af48e8ed5`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-cross-s23"></a>
### cross:S23

- 位置：`vllm_a/speed_up_v7/reports/stages/stage_10s_summary.md`，第 51 行；锚点：Profile run。
- SHA256：`721ba9bcce06462eeed50eda11772768ef575258f7db650f86507d5391d607c3`。
- 审阅范围：已核对本次整理所引用片段及文件 SHA256；不代表逐行重审全部 raw。

<a id="source-v41-s01"></a>
### v41:S01

- 位置：`flash41_speed_up_v1.md`。
- SHA256：`0edc43bcd28d6aa645a95c692c55134d5724073a9dab6d9627d26091acc526cb`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s02"></a>
### v41:S02

- 位置：`flash41_speed_up_v2.md`。
- SHA256：`603afc76fc179811b11230b824417c1ddae77e6e57445363d9e20f0b988b1ab2`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s03"></a>
### v41:S03

- 位置：`flash41_speed_up_v3.md`。
- SHA256：`f6be01e983f6a9b36fef66faf6825ad8f0683a6aecec299d656ecebe18f19be8`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s04"></a>
### v41:S04

- 位置：`flash41_speed_up_v2_api_1st/reports/speed_first_token_retest.md`。
- SHA256：`75d488e7b1687eb434986b8223f538245247cb628eb018d3c1117c9f59896952`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s05"></a>
### v41:S05

- 位置：`flash41_speed_up_v3/handoff/agent_handoff_20260918_exp015_108k_warmup.md`。
- SHA256：`b8ad871709600ac5709e058850fdbbf35cd7458721ba70b743b63a162e7fdafd`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s06"></a>
### v41:S06

- 位置：`flash41_speed_up_v3/reports/summary/performance_current_v41_mhc_warmup_exp008_rejection.json`。
- SHA256：`4d3bdddca17a3c32eb33f4f0f80ded4ddf0422a62ffd43f0d606830333450315`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s07"></a>
### v41:S07

- 位置：`flash41_speed_up_v3/reports/qa/performance_dynamic_mqa_context_exp016_jit_rejection_9255.json`。
- SHA256：`15d7ebf0874bf089b69c65473b2ad2b2e7cbdfda678c2125f640921599f442a6`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s08"></a>
### v41:S08

- 位置：`flash41_speed_up_v3/reports/qa/performance_length_general_sparse_exp017_jit_rejection_9260.json`。
- SHA256：`fd38cc7cd73156e3459a84e1e92aa8c171567b2d78f510d953d6915cc5a93292`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s09"></a>
### v41:S09

- 位置：`flash41_speed_up_v3/reports/qa/performance_full_matrix_exp019_speed68_rejection_9265.json`。
- SHA256：`32b02badc465bd7cc15e9b93b17aa395ddff74d3ae599de270bafe49942af39b`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s10"></a>
### v41:S10

- 位置：`flash41_speed_up_v3/reports/qa/performance_effective_ttft_exp023_reclassification_9278.json`。
- SHA256：`826698b962fa8d98e998a4b1e8fc99536660ed3c1decfeeb2cc2ca38b7ade623`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s11"></a>
### v41:S11

- 位置：`flash41_speed_up_v3/reports/summary/performance_full_batch_rotation_exp004_stage1_pass.json`。
- SHA256：`91ebcb75609e32fb1c355ed7ca91fbc8539b23c1e1aa57bf4d5964dbb26440e9`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s12"></a>
### v41:S12

- 位置：`flash41_speed_up_v1/reports/qa/v2_grouped_projection_r052_gsm_rejection.json`。
- SHA256：`3353214b81fdad75c5319163dd8291fc327c15187103ea930188a5c2e2c96810`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s13"></a>
### v41:S13

- 位置：`flash41_speed_up_v1/reports/summary/v2_final_acceptance.json`。
- SHA256：`acec7c4ad4cba79fae8d8c647e185b91d1c2bf77b90482f6d54880351505afe5`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s14"></a>
### v41:S14

- 位置：`flash41_speed_up_v3/reports/summary/candidate_exp028_acceptance.json`。
- SHA256：`4155853c0c38ced8b174238786568577ab280509dd5060c601acf54c64a64658`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s15"></a>
### v41:S15

- 位置：`flash41_speed_up_v3/reports/qa/kv_offloading_exp030_r32_original1200_acceptance_9416.json`。
- SHA256：`c976211ac799e657efe527e1b3783ddd4a00bae352fac8dd0816428b51a3f921`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s16"></a>
### v41:S16

- 位置：`flash41_speed_up_v3/reports/qa/kv_offloading_exp030_r32_speed68_rejection_9417.json`。
- SHA256：`beda43cbdcad6edb73d0dd3a7dd26431cf53bb73ae32a0243710ae84a63a222c`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s17"></a>
### v41:S17

- 位置：`flash41_speed_up_v1/autoresearch_results.tsv`。
- SHA256：`75219e5a1c76ef40f3038987b5e3449e82f78f4c1efae573f9a5a4650dd033f5`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s18"></a>
### v41:S18

- 位置：`flash41_speed_up_v3/reports/qa/speed68_adjacent_fluctuation_rule_20260920.json`。
- SHA256：`359625c551dd7f55bfcbb9530a052bdc116ea97604e36300e52c98d7298cda5c`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s19"></a>
### v41:S19

- 位置：`flash41_speed_up_v3/reports/qa/similarity_gates_retirement_20260920.json`。
- SHA256：`c67c2d84fa225cf0794f7a9c140fc7a4845229807bc8dd3d1d6badf631fdb6cb`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s20"></a>
### v41:S20

- 位置：`flash41_speed_up_v2_api_1st.md`。
- SHA256：`73d3ddfc843204c67f1ab3cbaafa83b0c4ca537fecb0e40bdd2075db15616887`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s21"></a>
### v41:S21

- 位置：`flash41_speed_up_v2_api_1st/contracts/api-and-prefix-cache.md`。
- SHA256：`c9eda2bccf8133bfbdc9083ea747f80ff8a3ee981976e14d013772eedebb771a`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s22"></a>
### v41:S22

- 位置：`flash41_speed_up_v2_api_1st/contracts/service-contract-and-rate-limit.md`。
- SHA256：`c1018c53f682d532aa585e4c6fd9ffd9eeca3eccaf4c3e6d3ca7694ac8e4914f`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s23"></a>
### v41:S23

- 位置：`flash41_speed_up_v2_api_1st/configs/metrics_contract.json`。
- SHA256：`36a0a36fc7c60bb118264d1695e3f0f03d8400a55ea6dcf810218d9843c4cb6e`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s24"></a>
### v41:S24

- 位置：`flash41_speed_up_v3/reports/qa/gateway_messages_usage.json`。
- SHA256：`17400141716de78337092069c6d86feafa4d1e821c7f5795688441ea2c129d4b`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s25"></a>
### v41:S25

- 位置：`flash41_speed_up_v3/reports/qa/gateway_admission_lifecycle.json`。
- SHA256：`8d3ff5d8ce6496c7add67d6b9aa299ae74ad03f9d20f179fd24aafc20d3b3143`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s26"></a>
### v41:S26

- 位置：`flash41_speed_up_v3/reports/qa/gateway_image_validation_exp023.json`。
- SHA256：`80a51b4637a288b14441d5ca5142a45707307bef98adc00146bcd5ceb4c49cdd`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-s27"></a>
### v41:S27

- 位置：`flash41_speed_up_v3/reports/qa/gateway_metrics_proxy.json`。
- SHA256：`58cbb4c6d1210ffb392082545810ad2d52d7ee23ba069d87319f2ce281e12468`。
- 审阅范围：已阅读相关合同、结论或索引；未重新执行 GPU 测量或逐项重审全部 raw

<a id="source-v41-u01"></a>
### v41:U01

- 位置：`用户明确指令`。
- SHA256：`7177d3a4d19a5928e3d463f6d8e35caac908933ad0276e575c42707adebdd0fd`。
- 审阅范围：保留原索引的记录范围。

<a id="source-v41-u02"></a>
### v41:U02

- 位置：`用户明确指令`。
- SHA256：`0c2e2c867b90ae23d962fca722d3e1b7ba67cbf646962a59487929e739c4fc4c`。
- 审阅范围：保留原索引的记录范围。

<a id="source-v41-u03"></a>
### v41:U03

- 位置：`用户明确指令`。
- SHA256：`d5f57ef1fff5e355055c13146abbbdfa194a6c05d372c56a86605b371e92e8f0`。
- 审阅范围：保留原索引的记录范围。
