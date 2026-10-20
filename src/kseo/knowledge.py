"""先过滤适用条件，再排序经验；事实与迁移假设分别存储。"""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path

from .util import KSEOError, file_digest, read_json, redact, write_json


def load_cards(extra: Path | None = None) -> list[dict]:
    cards = json.loads(files("kseo").joinpath("data/experience.json").read_text(encoding="utf-8"))["cards"]
    from .recipes import catalog, load_recipe
    for entry in catalog():
        cards += load_recipe(entry["id"])["cards"]
    if extra:
        value = read_json(extra)
        cards += value["cards"] if isinstance(value, dict) else value
    return cards


def retrieve(context: dict, cards: list[dict], limit: int = 8) -> list[dict]:
    selected = []
    for card in cards:
        conditions = card.get("applies_to", {})
        # 有特定条件但调用者没有提供时，不能假定匹配。
        if any(context.get(key) not in (value if isinstance(value, list) else [value])
               for key, value in conditions.items()):
            continue
        required = set(card.get("requires_capabilities", []))
        if not required <= set(context.get("capabilities", [])):
            continue
        score = len(conditions) * 2 + len(required)
        selected.append((score, card))
    return [card for _, card in sorted(selected, key=lambda pair: (-pair[1].get("priority", 0), -pair[0], pair[1]["id"]))[:limit]]


def import_materials(paths: list[Path], output: Path) -> int:
    cards = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in (".md", ".json", ".txt"):
            raise KSEOError(f"只接受明确列出的 Markdown、JSON 或文本文件: {path}")
        content = path.read_text(encoding="utf-8")
        if len(content.encode()) > 2_000_000:
            raise KSEOError(f"单个导入材料不能超过 2MB: {path.name}")
        # 自动导入只建立待审经验，不能把历史 PASS 提升为新任务的已验证收益。
        title = next((line.lstrip("# ") for line in content.splitlines() if line.startswith("#")), path.stem)
        observations = [line.strip() for line in redact(content).splitlines()
                        if re.search(r"PASS|FAIL|REJECT|INVALID|NOT_RUN|失败|通过|无效|TTFT|TPOT|warmup|IndexShare", line, re.I)]
        cards.append({"id": "import-" + file_digest(path)[:16], "title": redact(title),
                      "status": "NEEDS_REVIEW", "applies_to": {},
                      "observations": observations[:35], "transfer_hypothesis": "待人工或独立审查补齐适用条件及迁移假设。",
                      "source": {"filename": redact(path.name), "sha256": file_digest(path)},
                      "provenance": "历史材料导入，未复测；默认不进入自动优化检索。"})
    write_json(output, {"schema_version": 1, "cards": cards})
    return len(cards)
