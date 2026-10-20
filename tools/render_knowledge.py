"""从运行时知识目录生成分层手册、案例索引和无交叉箭头的层级图。"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from kseo.knowledge_tree import load_hierarchy


ROOT = Path(__file__).resolve().parents[1]


def link(node: dict, cases: bool = False) -> str:
    filename = "knowledge-cases.md" if cases else "knowledge.md"
    return f"[{node['id']}]({filename}#{node['id'].replace(':', '-').lower()})"


def conditions(node: dict) -> str:
    parts = []
    for key, value in node.get("applies_to", {}).items():
        parts.append(f"{key}={value[0] + '（含明确别名）' if isinstance(value, list) else value}")
    parts += node.get("requires_capabilities", [])
    return "；".join(parts) or "通用检查；不含新模型的数值默认或通过承诺"


def evidence_links(node: dict) -> str:
    return "、".join(f"[{s}](knowledge-cases.md#source-{s.replace(':', '-').lower()})"
                    for s in node.get("source_ids", [])) or "摘要 provenance；无逐卡直接文件 hash"


def render() -> None:
    data = load_hierarchy()
    nodes = data["nodes"]
    counts = {level: sum(node["level"] == level for node in nodes) for level in range(1, 5)}
    index = {node["id"]: node for node in nodes}
    children: dict = {}
    for node in nodes:
        children.setdefault(node["parent_id"], []).append(node)
    doc = ["# 分层优化知识", "",
           "先从原则选择方法，再按当前能力筛选场景规则，最后下钻到历史案例和来源。目录关系用于导航，不把案例归类解释为对父节点全部表述的因果证明。", "",
           "![由粗到细的知识层级](knowledge-layers.svg)", "",
           "| 层级 | 内容 | 数量 | 证据边界 |", "| --- | --- | --- | --- |",
           f"| L1 | 优化原则 | {counts[1]} | 跨案例概括，不构成任意模型上的收益证明 |",
           f"| L2 | 诊断与优化方法 | {counts[2]} | 决定检查和实验步骤，尚需实际工具与证据 |",
           f"| L3 | 带条件的场景规则 | {counts[3]} | 全模型数学等价/最终精度规则、V4.1 现行规则、跨模型与评测迁移规则 |",
           f"| L4 | 历史案例与来源 | {counts[4]} | 历史观察与本轮离线数据审计分别记录；均不代表本轮 GPU 实测 |", "",
           f"关联 {len(data['sources'])} 条来源记录，包括历史材料、用户规范和本轮静态数据身份审计。来源记录数不等于独立复现次数。原有 9 张代表性摘要卡未保存逐卡直接来源 hash，明确保留此缺口，不补造引用。", "",
           "**通用前提 G-P01：速度优化必须数学等价。** 允许的差异限于浮点表示、舍入、等价运算重排或并行归约带来的微小误差，并满足搜索前冻结的容差。数学等价不要求 bitwise 一致；数值接近或质量分数通过也不能单独证明数学等价。该规则对所有模型和优化路径生效，不受 top-k 限制。", "",
           "**最终精度 G-P02：优化完成后验收 RTLBench、LongBenchv2、LiveCodeBench。** 三项全量与证据有效性均须通过。详见 [最终精度合同与踩坑](final-accuracy.md)。数据按本地冻结集合：RTLBench 160、LongBenchv2 525、LiveCodeBench 400；LongBench 保留 105 条内容各重复 5 次的原顺序和 525 分母，不换官方版本、不去重。", "",
           "## 组织与证据边界", "",
           "本批材料抽查 GLM-5.1 NVFP4/FP8、GLM-5.2、V4-Flash 和 V4.1-Flash 的报告、故障分析及部分原始日志。整理前核对新增 23 份原文件的 SHA256；没有逐行审计全部历史日志，没有重跑 GPU，也没有新增真实单机或 P/D 部署 adapter。用户授权整理不提升原证据等级。", "",
           "| 证据类型 | 可以支持 | 不能直接支持 |", "| --- | --- | --- | --- |",
           "| 当前用户规则 | 当前任务应遵守的合同要求 | 功能已经实现、门禁已经执行或通过 |",
           "| 历史实测/正式报告 | 原版本、负载和合同内的观察结果 | 新模型收益、组合变化中单项收益 |",
           "| 原始日志片段 | 该片段内的形状、错误或事件 | 全量请求通过、唯一事故根因 |",
           "| 代码机制审阅 | 可达路径、状态不变量和危险条件 | 未重放请求的输出级因果闭环 |",
           "| 本地/NFS 集成测试报告 | 该测试范围内的隔离或协议行为 | 真实 GPU 性能、长期稳定性 |",
           "| 假设/因果未闭环 | 排查方向和待补证项目 | 已证实根因、无需验证的修复 |", "",
           "特别保留：R02 组合修复不能拆分收益；R08 未独立重算整份 Nsight SQLite；R13/R14 依据历史代码审阅，未独立重放事故；R15/R20 的输出因果未闭环；R18 是可能缓解，不是根治证明；R19 是本地集成测试报告。", "",
           "## 按层使用", "",
           "```bash", "# 全目录包含所有条件，仅用于导航", "kseo knowledge --tree", "",
           "# 从原则逐层下钻，也可以直接定位规则或案例", "kseo knowledge --node K04", "kseo knowledge --node M08", "kseo knowledge --node R15", "kseo knowledge --node case:R15", "",
           "# 按模型和明确能力筛选；同时返回祖先、匹配案例和来源", "kseo knowledge --hierarchy --context examples/knowledge/glm52-pd-context.json --limit 24", "```", "",
           "`--tree`/`--node` 是完整导航，不隐含条件已满足；不能同时传 `--context`。`--hierarchy` 才筛选条件，缺少能力或硬件字段不假定匹配。示例 context 只演示筛选，不证明该部署已经支持相应能力。", "",
           "旧 `knowledge --context ...` 继续返回原有平面卡片；新分层接口覆盖本次跨模型规则。`--extra` 只用于旧接口，未审阅导入不会自动进入层级。", "",
           "外部 Agent 的 `knowledge_hierarchy` 始终带 6 条原则、全模型 G-P01/G-P02/G-P03 及所选方法、规则、匹配案例、祖先 ID 和来源。`--limit`/top-k 只截断迁移规则；匹配 V4.1 时，11 条模型现行规则完整保留，`model_recipe` 仍完整提供。当前合同和用户规则优先，旧参数、learned-experience 和历史案例不得覆盖；未知阈值仍待确认，不能自动 PASS。", "",
           "## 原则 → 方法 → 规则", ""]
    for principle in children[None]:
        doc += [f"<a id=\"{principle['id'].lower()}\"></a>", f"### {principle['id']} {principle['title']}", "", principle["summary"], ""]
        for method in children[principle["id"]]:
            doc += [f"<a id=\"{method['id'].lower()}\"></a>", f"#### {method['id']} {method['title']}", ""]
            doc += [f"{i}. {step}" for i, step in enumerate(method["procedure"], 1)]
            doc += ["", "所需证据：" + "；".join(method["required_evidence"]) + "。", "",
                    "场景规则：" + "、".join(link(rule) + " " + rule["title"] for rule in children[method["id"]]) + "。", ""]
    doc += ["G-P03 固定测量语义与自举约定；模型及全部目标数值来自本次任务。详见 [自举与默认口径](agent-bootstrap.md)。", ""]
    doc += ["## 场景规则细目", "", "G-P01 是本轮明确补充的全模型前提。V4.1 原规则完整内容见模型 recipe；本表不重写它的阈值、停用项或计数语义。", ""]
    for rule in sorted((n for n in nodes if n["level"] == 3), key=lambda n: n["id"]):
        doc += [f"<a id=\"{rule['id'].lower()}\"></a>", f"### {rule['id']} {rule['title']}", "",
                "上层方法：" + link(index[rule["parent_id"]]) + "。", "",
                "适用条件：" + conditions(rule) + "。", ""]
        if rule["kind"] == "current_policy":
            if rule["id"].startswith("G-P"):
                doc += ["类别：**全模型通用的当前用户规则**。规则不是已经执行的真实模型验收证据。", ""]
            else:
                doc += ["类别：**当前用户规则**；具体操作、待确认参数和 adapter 要求以 `kseo recipe deepseek-v4.1-flash` 为准。", ""]
            doc += ["- " + step for step in rule["policy"].get("procedure", rule.get("recommended_actions", []))]
            if rule["id"].startswith("G-P"):
                doc += ["", "完整规则：`kseo knowledge --node " + rule["id"] + "`；各项具体证据及实现边界见 policy。当前规则不重新启用已退役的输出文本相似度门禁。", ""]
            else:
                doc += ["", "完整解释：[V4.1-Flash 专项经验](models/deepseek-v4.1-flash.md)。", ""]
        else:
            doc += ["类别：**需要当前任务验证的迁移规则**。" + rule["summary"], ""]
        doc += ["证据基础：" + rule["evidence_boundary"]["basis"] + "。", ""]
        doc += ["- 边界：" + limit for limit in rule["evidence_boundary"]["not_established"]]
        doc += ["", "下钻案例：" + ("、".join(link(index[i], True) for i in rule["navigation_case_ids"]) or "规则声明；无独立经验案例") + "。", ""]
    doc += ["## 能力标签", "",
            "`context.capabilities` 是显式筛选标签；声明不等于后端已支持或验收已通过。下表列出本批跨模型规则使用的标签，原模型 recipe 另有 `mhc`、`kv_offloading` 等能力。没有提供标签时，对应专门规则不会进入自动检索。", "",
            "| 标签 | 含义 |", "| --- | --- |"]
    doc += [f"| `{key}` | {value} |" for key, value in data["capability_vocabulary"].items()]
    doc += ["", "案例筛选只判断索引已声明的模型/硬件/能力字段。本批新案例未完整结构化原 GPU、backend commit、拓扑与全部负载，因此同模型案例被返回只表示相关，完整迁移资格仍须通过 M01 能力与身份核对。", "",
            "## 数据与维护", "",
            "主体是 `src/kseo/data/knowledge-hierarchy.json`，最终精度经验位于 `experience-final-accuracy.json`；现有规则/卡片通过 `legacy_links` 引用原始 recipe。层级加载检查 ID、连续层级、引用闭合与证据边界；来源使用 `cross:`/`v41:`/`accuracy:` 命名空间。", "",
            "公开来源只保留相对实验路径或文件名、行号（本批来源）、SHA256 和审阅范围。原文件未随仓库公开，无法只靠 hash 在公开环境复算历史结果。证据不足项必须补齐后另建结论，不能回写历史失败为通过。", "",
            "```bash", "# 改动数据后重建本手册、案例页和层级图", "PYTHONPATH=src python3 tools/render_knowledge.py", "```", "",
            "[完整案例与来源索引](knowledge-cases.md) · [经验转换](conversion.md) · [Agent 接口](agent-workflow.md)", ""]
    (ROOT / "docs/knowledge.md").write_text("\n".join(doc), encoding="utf-8")

    cases = ["# 历史案例与来源索引", "",
             "本页是分层知识的 L4。观察、原结论状态和迁移边界分别保存；没有本次 GPU 实测。来源 hash 表示原文件身份，不代表公开仓库包含原文件，也不代表已独立重算全部实验。", "",
             "[返回原则、方法与规则](knowledge.md)", ""]
    for case in sorted((n for n in nodes if n["level"] == 4), key=lambda n: n["id"]):
        cases += [f"<a id=\"{case['id'].replace(':', '-').lower()}\"></a>", f"## {case['id']} {case['title']}", "",
                  "归类规则：" + link(index[case["parent_id"]]) + "。归类关系不扩大案例结论。", "",
                  "原状态：`" + case["status"] + "`；适用条件：" + conditions(case) + "。", "",
                  "观察事实：", ""]
        cases += ["- " + item for item in case.get("observations", [])]
        boundary = case["evidence_boundary"]
        cases += ["", "证据基础：" + boundary["basis"] + "；因果状态：`" + boundary["causal_status"] + "`。", "",
                  "证据边界：", ""]
        cases += ["- " + item for item in boundary["not_established"]]
        if boundary.get("identity_coverage"):
            cases += ["- 身份范围：" + boundary["identity_coverage"]]
        cases += ["", "来源：" + evidence_links(case) + "。", ""]
    cases += ["## 来源记录", "",
              "本批来源保留已核对的行号锚点与 SHA256；已有 V4.1 索引保留原文件名及 hash。用户规则的 hash 按原文记录，不是性能证据。原有 9 张摘要卡没有逐卡直接 hash，不通过关联其他案例来补造。", ""]
    for source in data["sources"]:
        cases += [f"<a id=\"source-{source['id'].replace(':', '-').lower()}\"></a>", f"### {source['id']}", ""]
        location = source.get("relative_path", source.get("filename", "用户明确指令"))
        cases += [f"- 位置：`{location}`" + (f"，第 {source['line']} 行；锚点：{source['anchor']}。" if "line" in source else "。"),
                  f"- SHA256：`{source['sha256']}`。", "- 审阅范围：" + source.get("review", "保留原索引的记录范围。"), ""]
    (ROOT / "docs/knowledge-cases.md").write_text("\n".join(cases), encoding="utf-8")

    labels = [("L1 · 优化原则", "6 条原则：数学等价与合同、最大瓶颈点、真实负载、状态一致性、服务能力、证据边界"),
              ("L2 · 诊断与优化方法", "12 个方法：明确检查步骤、工具输入与所需证据"),
              ("L3 · 带条件的场景规则", f"{counts[3]} 条规则：数学等价与最终精度为前提；其他规则按模型 / 能力匹配"),
              ("L4 · 历史案例与来源", f"{counts[4]} 个案例 · {len(data['sources'])} 条来源记录：保留观察、原状态、SHA256 与未闭环项")]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="670" viewBox="0 0 1080 670" role="img" aria-labelledby="title desc">',
           '<title id="title">KSEO 由粗到细的分层知识</title>',
           '<desc id="desc">四层自上而下，每层只连接相邻下一层，无交叉线。目录导航关系不等于因果证明。</desc>',
           '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="none" stroke="#64748b" stroke-width="1.5"/></marker></defs>',
           '<rect width="1080" height="670" fill="#f8fafc"/>',
           '<g font-family="Noto Sans CJK SC,Microsoft YaHei,sans-serif">',
           '<text x="540" y="48" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">KSEO · 分层优化知识</text>']
    for i, (title, detail) in enumerate(labels):
        y = 82 + i * 133
        svg += [f'<rect x="64" y="{y}" width="952" height="101" rx="12" fill="{["#e0f2fe","#e0e7ff","#e0f2fe","#ecfdf5"][i]}" stroke="#94a3b8"/>',
                f'<text x="90" y="{y+35}" font-size="23" font-weight="700" fill="#0f172a">{escape(title)}</text>',
                f'<text x="90" y="{y+73}" font-size="18" fill="#334155">{escape(detail)}</text>']
        if i < 3:
            svg += [f'<path d="M540,{y+103} L540,{y+126}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>']
    svg += ['<text x="540" y="636" text-anchor="middle" font-size="18" fill="#475569">全层保留证据边界 · 历史知识须在当前合同验证 · 本次未重跑 GPU</text>', '</g></svg>']
    (ROOT / "docs/knowledge-layers.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")


if __name__ == "__main__":
    render()
