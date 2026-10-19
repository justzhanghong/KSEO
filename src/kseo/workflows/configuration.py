"""Configuration 子流程：优先探索成本较低的 flags、env 和 backend 参数。"""

from .. import optimizer
from ..util import canonical

RETRYABLE = {"INTERRUPTED", "DEPLOYMENT_FAILED", "EXECUTION_FAILED"}


def next_configuration(config: dict, state: dict) -> dict | None:
    attempts = {}
    for trial in state["trials"]:
        if trial["phase"] != "final":
            attempts.setdefault(canonical(trial["parameters"]), []).append(trial)
    limit = config["budget"].get("max_attempts_per_candidate", 2)
    tried = {key for key, rows in attempts.items()
             if len(rows) >= limit or any(row["status"] not in RETRYABLE for row in rows)}
    return optimizer.grid(config, tried)
