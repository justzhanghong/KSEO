"""标准化 Profile 与 System 层的热点排序。"""

from __future__ import annotations

from .util import KSEOError, finite

KINDS = {"kernel", "scheduling", "communication", "host"}


def normalize(profile: dict) -> dict:
    if not isinstance(profile, dict) or profile.get("scope") not in ("critical_path", "gpu_time"):
        raise KSEOError("Profile 必须声明 scope=critical_path 或 gpu_time")
    rows = profile.get("hotspots")
    if not isinstance(rows, list):
        raise KSEOError("Profile.hotspots 必须是列表")
    seen = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
            raise KSEOError("热点 id 缺失或重复")
        seen.add(row["id"])
        if row.get("kind") not in KINDS:
            raise KSEOError("热点 kind 必须为 kernel、scheduling、communication 或 host")
        share = finite(row.get("share"), "hotspot.share")
        speedup = finite(row.get("achievable_speedup", 1), "hotspot.achievable_speedup")
        if not 0 <= share <= 1 or speedup < 1:
            raise KSEOError("share 必须在 [0,1]，achievable_speedup 必须 >= 1")
        if type(row.get("editable", False)) is not bool:
            raise KSEOError("hotspot.editable 必须是 boolean")
        # Amdahl 只用于预算和路由排序，最终收益始终由 E2E 实测决定。
        saved_fraction = share * (1 - 1 / speedup)
        normalized.append({**row, "share": share, "achievable_speedup": speedup,
                           "expected_saved_fraction": saved_fraction,
                           "estimated_e2e_speedup": 1 / (1 - saved_fraction) if saved_fraction < 1 else None})
    if profile["scope"] == "critical_path" and sum(row["share"] for row in normalized) > 1 + 1e-9:
        raise KSEOError("critical_path 热点占比合计不能超过 1；重叠时间请使用 gpu_time 并说明统计口径")
    return {"scope": profile["scope"], "hotspots": sorted(normalized, key=lambda row: (-row["expected_saved_fraction"], row["id"])),
            "estimate_note": "gpu_time 可能包含重叠和并行时间；Amdahl 估计只用于策略排序，不代表 E2E 收益。"}


def route(profile: dict, configured: set[str], seen: set[str], revision: str, *, min_gain: float = 0) -> dict | None:
    for hotspot in profile["hotspots"]:
        lane = "kernel" if hotspot["kind"] == "kernel" else "scheduling"
        key = f"{revision}:{lane}:{hotspot['id']}"
        if lane not in configured or key in seen or hotspot["expected_saved_fraction"] <= min_gain:
            continue
        if lane == "kernel" and not hotspot.get("editable", False):
            continue
        return {"lane": lane, "hotspot": hotspot, "key": key}
    return None
