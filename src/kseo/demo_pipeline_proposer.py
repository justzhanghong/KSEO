"""分层流水线的确定性提案器；不调用 LLM，不模拟真实 GPU 收益。"""

import difflib
import json
import os
from pathlib import Path

request = json.loads(Path(os.environ["KSEO_AGENT_REQUEST"]).read_text())
output = Path(os.environ["KSEO_AGENT_PROPOSAL"])
workflow = request["workflow"]
source = Path(request["source_dir"]) / "demo_kernel.py"
old = source.read_text()
if workflow["lane"] == "scheduling":
    new = old.replace("SCHEDULER_SCALE = 1.0", "SCHEDULER_SCALE = 0.9")
else:
    new = old.replace("KERNEL_SCALE = 1.0", "KERNEL_SCALE = 0.8")
if new == old:
    proposal = {"stop": True}
else:
    patch = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile="a/demo_kernel.py", tofile="b/demo_kernel.py"))
    (output.parent / "patch.diff").write_text(patch)
    parameters = request["best"]["parameters"] if request.get("best") else request["parameters"]
    proposal = {"parameters": parameters, "patch": "patch.diff",
                "hypothesis": "基于当前 Profile 的 synthetic " + workflow["lane"] + " 子流程候选"}
output.write_text(json.dumps(proposal, ensure_ascii=False))
