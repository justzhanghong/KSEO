"""Scheduling 子流程：基于 host、通信或调度热点提出可回退候选。"""

import sys
from pathlib import Path

from .. import optimizer, source


def propose(runner, base: Path, hotspot: dict, directory: Path) -> dict | None:
    config = {**runner.config, "optimizer": {**runner.config["optimizer"],
              **runner.config["optimizer"]["scheduling"], "kind": "agent"}}
    revision = source.git(base, "rev-parse", "HEAD")
    variables = {"run_dir": str(runner.root), "source_dir": str(base),
                 "package_dir": str(Path(__file__).resolve().parents[1]),
                 "config_dir": runner.state["config_dir"], "python": sys.executable}
    proposal = optimizer.agent(config, runner.state, directory / "proposal", variables, {}, runner.remaining(),
                               workflow={"lane": "scheduling", "hotspot": hotspot})
    source.assert_unchanged(base, revision)
    return proposal
