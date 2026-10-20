"""配置搜索与外部 coding Agent 提案协议。"""

from __future__ import annotations

import itertools
from pathlib import Path

from .executor import execute
from .knowledge import load_cards, retrieve
from .util import KSEOError, canonical, confined, digest, read_json, write_json


def signature(parameters: dict, base_source: str = "", patch_sha256: str = "") -> str:
    return digest({"parameters": parameters, "base_source": base_source, "patch": patch_sha256})


def grid(config: dict, tried: set[str]) -> dict | None:
    space = config["optimizer"].get("space", {})
    keys = sorted(space)
    for values in itertools.product(*(space[key] for key in keys)):
        parameters = {**config["parameters"], **dict(zip(keys, values))}
        if canonical(parameters) not in tried:
            return {"parameters": parameters, "hypothesis": "受约束的配置搜索", "patch": None}
    return None


def agent(config: dict, state: dict, directory: Path, variables: dict, environment: dict, remaining: float,
          *, workflow: dict | None = None) -> dict | None:
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / "request.json"
    proposal_path = directory / "proposal.json"
    proposal_path.unlink(missing_ok=True)
    extra = Path(config["knowledge"]) if config.get("knowledge") else None
    cards = [c for c in load_cards(extra) if c.get("status") != "NEEDS_REVIEW"]
    learned = Path(variables["run_dir"]) / "learned-experience.json"
    if learned.exists():
        cards += read_json(learned)["cards"]
    from .recipes import for_context
    recipe = for_context(config["context"])
    if recipe is not None:
        # 现行规则由完整 recipe 提供，历史 top-k 保留给实际案例。
        cards = [card for card in cards if card.get("status") != "CURRENT_USER_POLICY"]
    request = {"schema_version": 1, "context": config["context"], "contract": config["validation"],
               "parameters": config["parameters"], "space": config["optimizer"].get("space", {}),
               "history": state["trials"], "best": state.get("best"),
               "source_dir": variables["source_dir"], "proposal_dir": str(directory),
               "experience": retrieve(config["context"], cards),
               "instructions": "只向 proposal_dir 写 proposal.json 和可选 patch.diff。不得修改 source_dir、合同或验收器。每次只提出一个可检验假设。"}
    if workflow is not None:
        request["workflow"] = workflow
    if recipe is not None:
        request["model_recipe"] = recipe
        request["instructions"] += " model_recipe 的现行规则优先于历史案例和 learned-experience；未知阈值不得猜测。recipe 不是已经执行的验收证据，不得据此写 PASS。"
    write_json(request_path, request)
    env = {**environment, "KSEO_AGENT_REQUEST": str(request_path), "KSEO_AGENT_PROPOSAL": str(proposal_path)}
    execute(config["optimizer"], directory / "process", {**variables, "proposal_dir": str(directory)}, env, remaining=remaining)
    proposal = read_json(proposal_path)
    if not isinstance(proposal, dict):
        raise KSEOError("Agent 提案必须是对象")
    if proposal.get("stop") is True:
        return None
    parameters = proposal.get("parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(config["parameters"]):
        raise KSEOError("Agent 必须返回完整参数集合")
    for key, value in parameters.items():
        allowed = config["optimizer"].get("space", {}).get(key, [config["parameters"][key]])
        if canonical(value) not in {canonical(item) for item in allowed}:
            raise KSEOError(f"Agent 参数超出允许空间: {key}")
    if not isinstance(proposal.get("hypothesis"), str) or not proposal["hypothesis"].strip():
        raise KSEOError("Agent 提案必须说明 hypothesis")
    patch = proposal.get("patch")
    if patch:
        if not config["optimizer"].get("allow_source_changes", False):
            raise KSEOError("当前合同未开启源码修改")
        patch = confined(directory, patch)
        if not patch.is_file() or patch.stat().st_size > 2_000_000:
            raise KSEOError("patch 必须是 proposal_dir 下不超过 2MB 的文件")
    return {"parameters": parameters, "hypothesis": proposal["hypothesis"], "patch": patch}
