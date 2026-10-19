"""把现有脚本的结构化输出转换为 KSEO 协议。

此文件应复制到自己的 adapter 工程，并在 stage 函数内调用现有脚本。
只有真实检查通过后才能填写对应 checks，不能用固定 True 代替真实验收。
"""

import os
import subprocess

from kseo.adapter import emit


def main():
    stage = os.environ["KSEO_STAGE"]
    if stage == "cleanup":
        # 按 run_id/trial_id 查询并停止自己的服务；要求幂等。
        raise NotImplementedError("接入现有精确身份清理脚本")
    if stage == "preflight":
        # 查询实际 GPU UUID、SM、image digest、挂载与网络，并与 identity 比较。
        raise NotImplementedError("接入平台查询及 runtime 身份核对")
    if stage in ("build", "deploy", "smoke", "profile", "api", "stability"):
        # subprocess.run([...], check=True)，读取其原始验收 JSON 后再 emit。
        raise NotImplementedError(f"接入现有 {stage} 脚本")
    if stage == "benchmark":
        # 运行现有 harness，转换每条实际请求；不能只搬运 mean TTFT/TPOT。
        # emit(requests=[{request_id, case_id, status, input_tokens, output_tokens,
        #                 cache_read_tokens, ttft_ms, total_ms}, ...])
        raise NotImplementedError("读取现有 benchmark 原始逐请求记录")
    if stage == "quality":
        # emit(samples=[{sample_id, correct, failed, unparseable}, ...], checks=...)
        raise NotImplementedError("读取精度原始逐样本结果")


if __name__ == "__main__":
    main()
