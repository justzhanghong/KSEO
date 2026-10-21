"""由原则下钻到证据；导航关系不等于因果证明，经验检索不等于验收。"""

from __future__ import annotations

import json
from importlib.resources import files

from .recipes import load_recipe
from .util import KSEOError


def _read(name: str) -> dict:
    return json.loads(files("kseo").joinpath("data/" + name).read_text(encoding="utf-8"))


def matches(context: dict, node: dict) -> bool:
    conditions = node.get("applies_to", {})
    return (all(key in context and context[key] in (value if isinstance(value, list) else [value])
                for key, value in conditions.items())
            and set(node.get("requires_capabilities", [])) <= set(context.get("capabilities", [])))


def load_hierarchy() -> dict:
    """引用现有 recipe/card 原文，避免层级副本覆盖现行规则或旧状态。"""
    data = _read("knowledge-hierarchy.json")
    accuracy = _read("experience-final-accuracy.json")
    data["nodes"] += accuracy["nodes"]
    data["sources"] += accuracy["sources"]
    data["capability_vocabulary"]["final_accuracy"] = "当前任务已声明最终三项精度验收；不代表评测已通过"
    autonomy = _read("autonomy-policy.json")
    autonomy["nodes"][0]["policy"]["defaults"] = _read("defaults.json")
    data["nodes"] += autonomy["nodes"]
    data["sources"] += autonomy["sources"]
    methods = _read("optimization-methods-rsi.json")
    data["nodes"] += methods["nodes"]
    data["sources"] += methods["sources"]
    data["global_boundary"] += methods["global_boundary"]
    # 目录用于发现和下钻；未知成本条件不能被当成已匹配的优化场景。
    data["optimization_methods"] = {
        "selection": "NAVIGATION_ONLY_REQUIRES_COST_EVIDENCE",
        "instructions": methods["navigation_instructions"],
        "guidance": methods["nodes"][0],
        "sources": methods["sources"],
        "directions": [{key: node[key] for key in ("id", "method_id", "title", "lanes", "trigger")}
                       for node in methods["nodes"] if node["level"] == 3],
    }
    recipe = load_recipe("deepseek-v4.1-flash")
    base = {card["id"]: card for card in _read("experience.json")["cards"]}
    v41 = {card["id"]: card for card in recipe["cards"]}
    for link in data.pop("legacy_links"):
        original = base[link["id"]] if link["record"] == "base_card" else v41[link["id"]]
        policy = link["record"] == "v41_policy"
        node = {**original, **link, "kind": "current_policy" if policy else "historical_case"}
        node["source_ids"] = ["v41:" + source for source in original.get("source_ids", [])]
        node["evidence_boundary"] = {
            "basis": "CURRENT_USER_POLICY" if policy else original["status"],
            "claim_scope": "仅按原适用条件和当前有效合同解释；分层归类不改变原记录状态。",
            "causal_status": "NORMATIVE_NOT_EMPIRICAL" if policy else "RETAIN_ORIGINAL_STATUS",
            "revalidated_in_kseo": False,
            "not_established": original.get("limits", []) + [
                "规则声明不代表对应真实 adapter 已实现或验收已通过。" if policy else
                "未在本次重跑 GPU；历史摘要、局部 PASS 或本地测试不能替代当前任务验收。",
            ],
        }
        if policy:
            node["policy"] = recipe["rules"][link["id"]]
        elif not node["source_ids"]:
            node["evidence_boundary"]["not_established"].append(
                "原始代表性卡片只保留摘要 provenance，无逐卡原文件 SHA256；不补造直接来源。")
        data["nodes"].append(node)
    data["sources"] += [{**source, "id": "v41:" + source["id"]} for source in recipe["sources"]]
    validate(data)
    index = {node["id"]: node for node in data["nodes"]}
    for node in data["nodes"]:
        if node["level"] < 4:
            node["navigation_case_ids"] = [case["id"] for case in data["nodes"] if case["level"] == 4
                                           and node["id"] in [a["id"] for a in _ancestors(case, index)]]
    return data


def validate(data: dict) -> None:
    nodes = {node["id"]: node for node in data["nodes"]}
    sources = {source["id"] for source in data["sources"]}
    if len(nodes) != len(data["nodes"]) or len(sources) != len(data["sources"]):
        raise KSEOError("知识节点或来源 ID 重复")
    for node in nodes.values():
        level = node["level"]
        parent = nodes.get(node.get("parent_id"))
        if level not in (1, 2, 3, 4) or (level == 1 and node.get("parent_id") is not None):
            raise KSEOError(f"知识层级不合法：{node['id']}")
        if level > 1 and (parent is None or parent["level"] != level - 1):
            raise KSEOError(f"知识父子层级不连续：{node['id']}")
        if not set(node.get("source_ids", [])) <= sources:
            raise KSEOError(f"知识来源缺失：{node['id']}")
        if not node.get("evidence_boundary"):
            raise KSEOError(f"知识证据边界缺失：{node['id']}")


def _ancestors(node: dict, index: dict) -> list[dict]:
    result = []
    while node.get("parent_id"):
        node = index[node["parent_id"]]
        result.insert(0, node)
    return result


def _brief(node: dict) -> dict:
    keys = ("id", "level", "title", "kind", "status", "applies_to", "requires_capabilities", "evidence_boundary")
    return {key: node[key] for key in keys if key in node}


def _metadata(data: dict) -> dict:
    return {key: value for key, value in data.items() if key not in ("nodes", "sources")}


def overview(data: dict | None = None) -> dict:
    """展示所有知识的导航目录，不代表目录中条件已经匹配。"""
    data = data if data is not None else load_hierarchy()
    children: dict = {}
    for node in data["nodes"]:
        children.setdefault(node.get("parent_id"), []).append(node)

    def branch(node: dict) -> dict:
        return {**_brief(node), "children": [branch(child) for child in children.get(node["id"], [])]}

    return {**_metadata(data), "selection": "ALL_CONTEXTS_NAVIGATION_ONLY",
            "counts": {str(level): sum(n["level"] == level for n in data["nodes"]) for level in range(1, 5)},
            "tree": [branch(node) for node in children[None]]}


def inspect_node(node_id: str, data: dict | None = None) -> dict:
    """精确下钻并携带边界、原规则和所引来源；不做隐含上下文授权。"""
    data = data if data is not None else load_hierarchy()
    index = {node["id"]: node for node in data["nodes"]}
    if node_id not in index:
        raise KSEOError(f"没有该知识节点：{node_id}")
    node = index[node_id]
    descendants = [item for item in data["nodes"]
                   if node_id in [ancestor["id"] for ancestor in _ancestors(item, index)]]
    source_ids = {source for item in [node, *descendants] for source in item.get("source_ids", [])}
    return {**_metadata(data), "selection": "EXPLICIT_NODE_NAVIGATION_ONLY", "node": node,
            "ancestors": [_brief(item) for item in _ancestors(node, index)],
            "children": [_brief(item) for item in descendants if item["parent_id"] == node_id],
            "case_ids": [item["id"] for item in descendants if item["level"] == 4],
            "sources": [source for source in data["sources"] if source["id"] in source_ids]}


def retrieve_hierarchy(context: dict, limit: int = 8, data: dict | None = None) -> dict:
    """先筛选场景规则，再带回祖先和匹配案例；现行规则不受 top-k 截断。"""
    if limit < 1:
        raise KSEOError("--limit 必须至少为 1")
    data = data if data is not None else load_hierarchy()
    index = {node["id"]: node for node in data["nodes"]}
    policies = [node for node in data["nodes"] if node["kind"] == "current_policy" and matches(context, node)]
    rules = [node for node in data["nodes"] if node["level"] == 3 and node["kind"] != "current_policy"
             and matches(context, node)]
    rules.sort(key=lambda node: (-node.get("priority", 0),
                                -len(node.get("applies_to", {})) * 2 - len(node.get("requires_capabilities", [])), node["id"]))
    selected = [*policies, *rules[:limit]]
    selected_ids = {node["id"] for node in selected}
    ancestor_ids = {ancestor["id"] for node in selected for ancestor in _ancestors(node, index)}
    # 原则始终提供，方法仅随所选规则提供；不会靠 top-k 丢失上层约束。
    ancestors = [node for node in data["nodes"] if node["level"] == 1 or node["id"] in ancestor_ids]
    cases = [node for node in data["nodes"] if node["level"] == 4 and node["parent_id"] in selected_ids
             and matches(context, node)]
    result_nodes = [*ancestors, *selected, *cases]
    source_ids = {source for node in result_nodes for source in node.get("source_ids", [])}
    return {**_metadata(data), "selection": "CONTEXT_FILTERED_GUIDANCE_NOT_ACCEPTANCE",
            "context": context, "transfer_rule_limit": limit, "current_rule_ids": [n["id"] for n in policies],
            "nodes": [{**node, "ancestor_ids": [a["id"] for a in _ancestors(node, index)]} for node in result_nodes],
            "sources": [source for source in data["sources"] if source["id"] in source_ids]}
