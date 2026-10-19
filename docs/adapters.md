# Adapter 接入

KSEO 控制器不硬编码服务器、账号、模型路径或平台 API。可以把已有部署和评测脚本包装为 Python 命令、SSH 命令或平台任务查询命令。

## 输入协议

每个 step 收到以下环境变量，文件路径位于本次 run 内：

| 变量 | 内容 |
| --- | --- |
| `KSEO_STAGE` | 当前阶段名；cleanup 也通过同一接口调用 |
| `KSEO_IDENTITY_PATH` | 本次 run、trial、合同、参数、源码、镜像和负载身份 |
| `KSEO_PARAMETERS_PATH` | 当前候选参数 JSON |
| `KSEO_SOURCE_DIR` | 本次独立源码副本 |
| `KSEO_RUN_DIR`、`KSEO_TRIAL_DIR` | 运行与实验目录 |
| `KSEO_STAGE_DIR` | 原始产物和阶段日志目录 |
| `KSEO_RESULT_PATH` | 需要写入的 result.json |
| `KSEO_MODE` | measured、synthetic 或 replay |

Adapter 的配置可以放在 `steps[].env`；credentials 建议由外部环境注入，避免写进任务合同。子进程继承调用者环境，KSEO 不提供凭据存储。

## 输出协议

已有脚本成功执行后，用辅助函数生成结果：

```python
from kseo.adapter import emit

# 此处的值必须来自实际检查。
emit(checks={"source_identity_match": observed_source == expected_source},
     runtime={"gpu_arch": observed_arch, "image": observed_image})
```

普通阶段需要输出 schema_version、identity、kind、checks 和 runtime。缺少 result.json、身份不匹配或 mode 不匹配都会使实验失效。cleanup 只要求幂等完成并返回退出码 0。

benchmark 输出逐请求记录：

```python
emit(requests=[{
    "request_id": "request-001",
    "case_id": "long_c1",
    "status": "completed",
    "input_tokens": 49891,
    "output_tokens": 256,
    "cache_read_tokens": 0,
    "ttft_ms": measured_ttft_ms,
    "total_ms": measured_last_token_ms,
}])
```

quality 输出逐样本结果：

```python
emit(samples=[{
    "sample_id": "sample-001",
    "correct": actual_correct,
    "failed": request_failed,
    "unparseable": answer_unparseable,
}], checks={"numerics": actual_numerics_pass})
```

Helper 为原始 JSONL 计算 SHA256，Validator 再验证 hash、长度、数量和计分。直接修改 mean 或在报告中写 PASS 不会绕过原始记录重算。

## 真实 HTTP benchmark

已提供 `python -m kseo.http_benchmark`，可对已有 OpenAI-compatible Chat Completions 服务进行 measured 测量。它使用流式响应中的实际 usage，包含 reasoning/tool delta 首次到达，并记录每个 case 的逐请求时间。

配置 benchmark step：

```json
{
  "name": "benchmark",
  "command": ["{python}", "-m", "kseo.http_benchmark"],
  "timeout_seconds": 3600,
  "env": {
    "KSEO_BASE_URL": "http://your-service:8000/v1",
    "KSEO_WORKLOAD_FILE": "{config_dir}/workload.json"
  }
}
```

`KSEO_API_KEY` 可通过调用者环境提供。负载文件形状：

```json
{
  "cases": [{
    "id": "long_c1",
    "concurrency": 1,
    "requests": [{
      "request_id": "r001",
      "input_tokens": 49891,
      "payload": {
        "model": "your-model-id",
        "messages": [{"role": "user", "content": "实际冻结内容"}],
        "max_tokens": 256,
        "temperature": 0
      }
    }]
  }]
}
```

上例仅描述格式，实际内容必须经 tokenizer 核对后与 input_tokens 一致，case 数量也要符合任务合同。HTTP adapter 不自动创建负载、执行 warmup 或增加 retry；这些规则应在 profile 中固定。服务端必须返回 completion_tokens、prompt_tokens 和缓存读取字段，缺少证据时请求会记为失败。

## 旧脚本与平台操作

`examples/adapters/legacy_bridge.py` 标出了包装入口。它故意保留未实现异常，防止把没有实际执行的 preflight、quality 或 stability 当成通过。

推荐先接通已有的单节点部署包，之后增加 AIHub 与 P/D。部署 adapter 使用 `run_id` 和 `trial_id` 作为幂等标识；创建后把 training_id、Pod UID、GPU UUID、镜像和挂载反查结果写入原始产物。cleanup 只停止精确匹配本任务身份的服务，重复调用也应成功。

Adapter 与其依赖的脚本应放在候选源码外，控制器会核对直接命令文件与自身工具的 SHA256。外部服务、间接导入模块、编译器和平台版本仍需由 preflight 固定；直接命令 hash 不等于完整供应链校验。
