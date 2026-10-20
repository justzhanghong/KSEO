# 本地冻结测试集

当前验收**以本地测试集为准，不替换为官方版本**。数据清单位于 `src/kseo/data/datasets.json`，固定文件 SHA256、样本数、原顺序及来源边界。下列四套测试集的正文已随 Git 和安装包分发；执行 `kseo dataset` 不联网，不执行模型或测试代码。

| 数据 | 本地版本与数量 | 交付方式 |
| --- | --- | --- |
| GSM8K main test | 1319；原文件 SHA256 `752adc99…` | 本地 `test.jsonl` 原字节，附 MIT License；不引入 train |
| RTLBench | 160；本地 manifest 原顺序 | 完整题面与原 testbench JSONL、320 个原文件 hash、MIT License |
| LongBenchv2 | **525 个 ID、105 条非 ID 内容各重复 5 次**；原文件 SHA256 `b31bf65b…` | 本地 `data.json` 无损 gzip，附来源许可说明；不去重、不改 525 分母 |
| LiveCodeBench code_generation_lite | release_v1 本地 400 题；原文件 SHA256 `2bd02b38…` | 24 个无损 gzip 分片，保留本地 README；不加载 test2..test6 |
| 历史长上下文输入 | 六份完整模板生成的 messages | 清除内部模型绝对路径，保留原 messages 和历史 token 数 |
| 业务 68 样本与生产 1200 回放 | 本地冻结文件的元数据、数量和 hash | 含实际业务/隐私/生产字段，正文由运行环境提供，不随公开仓库分发 |

`local_frozen` 表示当前选择依据，不表示本地文件等同于官方原版。RTLBench 发布的是本地题面与原 TB，不混入旧任务的 10 处修改版 TB。旧用户接受的某个评分版本不授权新任务改 TB。

GSM8K、RTLBench 的 MIT 和 LongBench 来源的 Apache-2.0 说明随数据保留。LiveCodeBench 本地数据 README 仅写 `cc`，未注明具体 CC 版本；原标注如实保留，不把评测代码仓库的 MIT 当成数据许可。本轮按用户要求提交本地冻结测试文件，不将其改称新授权或官方同步版本。

## 导出与校验

```bash
kseo dataset
kseo dataset gsm8k-main
kseo dataset gsm8k-main --out ./data/gsm8k
kseo dataset rtlbench-160 --out ./data/rtlbench
kseo dataset longbench-v2 --out ./data/longbench-v2
kseo dataset livecodebench-v1 --out ./data/livecodebench-v1

# 已有本地原文件时直接核对；不会下载或替换数据
kseo dataset longbench-v2 --root /path/to/longbenchv2
kseo dataset livecodebench-v1 --root /path/to/code_generation_lite
kseo dataset business-speed68 --root /path/to/private-materials
kseo dataset production-replay1200 --root /path/to/private-replay
```

`--out` 拒绝覆盖已有目录。LongBench 导出为原 `data.json`，LiveCodeBench 导出为原 `test.jsonl`；解压拼接后的**全部字节和 SHA256 必须与本地原文件一致**，不重新序列化、裁剪 context 或改写 public/private tests。LiveCodeBench 原文件 1252609773 bytes，gzip 分片合计约 915 MB，单片均低于 GitHub 的 100 MiB 限制，无需 Git LFS。

校验输出 `dataset_manifest_sha256`、文件 SHA256、数量和内容身份。它只证明数据身份，不代表真实推理或精度验收通过。外部目录必须提供清单内原文件名，不接受另一个来源或部分样本。

## LongBench 的证据边界

本轮静态审计本地 JSON：525 个不同 `_id`，去掉 `_id` 后为 105 条不同完整 JSON 内容，每条重复 5 次。同目录存在扩增脚本；脚本存在不能单独证明完整生成历史，内容重复则直接由原文件核对。

**当前用户明确选择本地集合，因此保留全部 525 条的原顺序、ID、标签与分母。** 不换官方版本，不按重复内容删题。重复性质属于解释结果时必须披露的边界，不能把该成绩称作官方全量成绩。旧 `317/525` 只属于旧语料、产物与合同，不是本轮或新模型的测试成绩。

审计摘要位于包内 `data/datasets/longbench-historical-audit/audit.json`。可用下列脚本核对 JSON 数组，仅输出数量与 hash：

```bash
PYTHONPATH=src python3 tools/audit_dataset_identity.py /path/to/data.json --id-field _id
```

新模型上下文不足时，精度测试的截断/窗口协议需在当前合同明确并固定 baseline 对照；不能运行后换成短子集。精度协议与速度测试的禁止截断要求分别按各自合同执行。

## 历史长上下文输入

六份输入由三个文本模板及顺序编号生成，不含真实业务请求；历史 token 数依次为 50033、72029、144029、162533、260525、261127。“160K”“256K”是历史标签，不能按文件名当成精确 token 数。新模型需重新 native tokenize，不能静默截断。

这些输入具有相同前缀，不能直接证明正式测速零命中。需按现行规则修改首个用户内容 token、冻结新请求身份、重新核对长度，并实证 cache-read 为 0。数据文件本身不证明 warmup、缓存或性能门禁通过。

[最终精度合同与踩坑](final-accuracy.md)
