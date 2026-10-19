"""确定性提案器，用于测试与演示 Agent 协议；它不是 LLM。"""

import difflib
import json
import os
from pathlib import Path

request = json.loads(Path(os.environ["KSEO_AGENT_REQUEST"]).read_text())
output = Path(os.environ["KSEO_AGENT_PROPOSAL"])
candidates = [trial for trial in request["history"] if trial["phase"] == "candidate"]
if not candidates:
    proposal = {"parameters": {"chunk_tokens": 1024}, "hypothesis": "Scheduling 参数调整，降低 synthetic TTFT"}
elif len(candidates) == 1:
    source = Path(request["source_dir"]) / "demo_kernel.py"
    old = source.read_text()
    new = old.replace("KERNEL_SCALE = 1.0", "KERNEL_SCALE = 0.8")
    patch = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile="a/demo_kernel.py", tofile="b/demo_kernel.py"))
    (output.parent / "patch.diff").write_text(patch)
    proposal = {"parameters": {"chunk_tokens": 1024}, "patch": "patch.diff",
                "hypothesis": "用可回退源码补丁演示 Kernel 层优化；仅为 synthetic 数值"}
else:
    proposal = {"stop": True, "reason": "示例提案完成"}
output.write_text(json.dumps(proposal, ensure_ascii=False))
