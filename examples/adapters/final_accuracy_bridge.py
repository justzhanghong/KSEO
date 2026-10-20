"""串行接入已建立的三个真实 benchmark wrapper；不内置部署或代码执行沙箱。"""

import json
import os
import subprocess
from pathlib import Path

from kseo.adapter import emit
from kseo.final_accuracy import SUITES
from kseo.util import KSEOError, confined, read_json, write_json


def main():
    if os.environ["KSEO_STAGE"] != "final_accuracy":
        raise KSEOError("该 bridge 只用于优化完成后的 final_accuracy 阶段")
    plan = read_json(Path(os.environ["KSEO_FINAL_ACCURACY_PLAN"]))
    root = Path(os.environ["KSEO_STAGE_DIR"])
    contract = read_json(Path(os.environ["KSEO_RUN_DIR"]) / "task.json")["validation"]["final_accuracy"]
    outputs = []
    for suite in contract["suites"]:
        sid = suite["id"]
        if sid not in SUITES or sid not in plan["commands"]:
            raise KSEOError("三项精度 wrapper 必须完整配置")
        directory = root / sid
        directory.mkdir()
        frozen = directory / "contract.json"
        write_json(frozen, suite)
        command = plan["commands"][sid]
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command):
            raise KSEOError("benchmark wrapper 必须配置 argv 数组")
        variables = {"suite_dir": str(directory), "contract_file": str(frozen)}
        command = [arg.format_map(variables) for arg in command]
        with (directory / "stdout.log").open("w") as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                           timeout=plan["timeout_seconds"][sid])
        output = read_json(directory / "bench-result.json")
        if output.get("id") != sid:
            raise KSEOError("benchmark wrapper 输出数据集身份不符")
        for key in ("samples_file", "attempts_file", "validity_review_file"):
            output[key] = str(confined(directory, output[key]).relative_to(root))
        outputs.append(output)
    emit(benchmarks=outputs)


if __name__ == "__main__":
    main()
