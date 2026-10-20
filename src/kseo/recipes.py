"""按明确模型身份加载经验 recipe；不把经验包伪装成部署适配。"""

from __future__ import annotations

import json
from importlib.resources import files

from .util import KSEOError


def catalog() -> list[dict]:
    return json.loads(files("kseo").joinpath("data/recipes.json").read_text(encoding="utf-8"))["recipes"]


def load_recipe(name: str) -> dict:
    entry = next((entry for entry in catalog() if name == entry["id"] or name in entry["aliases"]), None)
    if entry is None:
        raise KSEOError(f"没有内置该模型的经验 recipe：{name}")
    return json.loads(files("kseo").joinpath("data/" + entry["file"]).read_text(encoding="utf-8"))


def for_context(context: dict) -> dict | None:
    family = context.get("model_family")
    entry = next((entry for entry in catalog() if family == entry["id"] or family in entry["aliases"]), None)
    if entry is None:
        return None
    recipe = load_recipe(entry["id"])
    # 现行规则完整交给 Agent，不受经验 top-k 截断；历史案例仍按条件检索。
    return {key: value for key, value in recipe.items() if key != "cards"}
