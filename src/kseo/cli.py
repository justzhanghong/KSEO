"""中文 CLI。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .config import load
from .demo import task as demo_task
from .knowledge import import_materials, load_cards, retrieve
from .runner import Runner
from .util import KSEOError, read_json, write_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="kseo", description="Kernel、Scheduling 与 End-to-End 推理优化工具")
    result.add_argument("--version", action="version", version=__version__)
    sub = result.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="执行冻结任务合同")
    run.add_argument("task", type=Path, help="任务 JSON 路径")
    run.add_argument("--run-dir", type=Path, required=True, help="独立运行目录")
    resume = sub.add_parser("resume", help="清理中断实验并恢复搜索")
    resume.add_argument("run_dir", type=Path)
    status = sub.add_parser("status", help="查看运行状态与最佳候选")
    status.add_argument("run_dir", type=Path)
    check = sub.add_parser("validate", help="检查任务合同，或重新审计已有实验")
    check.add_argument("task", type=Path)
    check.add_argument("--trial-dir", type=Path, help="独立重算此实验的原始产物")
    demo = sub.add_parser("demo", help="运行不占 GPU 的 synthetic 完整示例")
    demo.add_argument("--run-dir", type=Path, required=True)
    variants = demo.add_mutually_exclusive_group()
    variants.add_argument("--agent", action="store_true", help="演示外部提案与源码补丁接口；提案器不是 LLM")
    variants.add_argument("--pipeline", action="store_true", help="演示 System、Scheduling 和独立 Kernel 子流程")
    init = sub.add_parser("init", help="从 profile 和模型、源码、镜像、服务器生成任务")
    init.add_argument("--model", required=True)
    init.add_argument("--source", required=True, type=Path)
    init.add_argument("--revision", help="完整 Git commit；未提供时读取 source HEAD")
    init.add_argument("--image", required=True)
    init.add_argument("--server", action="append", required=True)
    init.add_argument("--profile", type=Path, help="已建立的完整业务 profile；省略时输出待补齐草稿")
    init.add_argument("--out", type=Path, required=True)
    knowledge = sub.add_parser("knowledge", help="按层浏览知识，或按结构和能力检索经验")
    knowledge.add_argument("--context", type=Path, help="检索 context JSON；未知能力不能假定存在")
    knowledge.add_argument("--extra", type=Path, help="仅用于原有平面卡片检索")
    knowledge.add_argument("--limit", type=int, default=8, help="历史卡片/迁移规则条数；层级中的现行规则完整提供")
    knowledge_modes = knowledge.add_mutually_exclusive_group()
    knowledge_modes.add_argument("--tree", action="store_true", help="列出四层全目录，仅用于导航")
    knowledge_modes.add_argument("--node", help="查看指定节点、上级、子项和来源，例如 R15 或 case:R15")
    knowledge_modes.add_argument("--hierarchy", action="store_true", help="按 context 检索规则，并返回上层方法与匹配案例")
    recipe = sub.add_parser("recipe", help="查看模型经验及现行测量规则；不是部署 adapter")
    recipe.add_argument("name", nargs="?", help="例如 deepseek-v4.1-flash；省略时列出已有经验包")
    recipe.add_argument("--out", type=Path, help="导出 JSON，不覆盖已有文件")
    dataset = sub.add_parser("dataset", help="列出、校验或导出固定版本数据；不运行模型")
    dataset.add_argument("name", nargs="?", help="省略时列出数据清单")
    dataset.add_argument("--root", type=Path, help="校验外部或已导出的数据目录")
    dataset.add_argument("--out", type=Path, help="导出到新目录，拒绝覆盖")
    sub.add_parser("defaults", help="查看默认测速、多轮、精度、资源及 Docker 政策")
    sub.add_parser('roles', help='查看瓶颈分析、开发、验收和 System 的协议与权限')
    prepare = sub.add_parser("prepare", help="从简要任务输入生成默认策略、发现报告和 Agent 自举请求")
    prepare.add_argument("brief", type=Path)
    prepare.add_argument("--out", type=Path, required=True)
    doctor = sub.add_parser("doctor", help="检查自举后的真实合同与直接 adapter；不代替平台实测")
    doctor.add_argument("task", type=Path)
    doctor.add_argument("--brief", type=Path)
    ingest = sub.add_parser("ingest", help="将明确列出的历史材料导入为待审经验")
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument("--out", required=True, type=Path)
    return result


def audit(task_path: Path, directory: Path) -> dict:
    from . import validation
    from .util import digest

    config = load(task_path)
    record = read_json(directory / "trial.json")
    identity = read_json(directory / "identity.json")
    if identity.get("contract_sha256") != digest(config):
        raise KSEOError("任务合同与实验 identity 不符")
    if (config["validation"].get("final_accuracy") or config["validation"].get("multi_turn") or config["validation"].get("milestones")) and identity.get("phase") != record.get("phase"):
        raise KSEOError("实验 phase 与 identity 不符，不能跳过最终精度门禁")
    from .source import assert_unchanged
    assert_unchanged(directory / "source", identity["source_revision"])
    if record.get("kernel_evidence"):
        from .workflows.kernel import audit as audit_kernel
        from .util import confined
        run_root = directory.parent.parent
        evidence = record["kernel_evidence"]
        audit_kernel(confined(run_root, evidence["directory"]), evidence, config["mode"])
        from .source import git
        from .util import file_digest
        if (file_digest(directory / "proposal.diff") != evidence["patch_sha256"]
                or git(directory / "source", "rev-parse", "HEAD^{tree}") != evidence["candidate_tree"]):
            raise KSEOError("E2E 集成源码与 Kernel 独立证据不一致")
    results = {}
    for step in config["steps"]:
        name = step["name"]
        path = directory / "steps" / name / "result.json"
        if path.exists():
            results[name] = validation.ingest_stage(path, identity, config["mode"], name, config["validation"])
    from . import artifacts
    previous = []
    for sibling in directory.parent.glob('*/trial.json'):
        prior = read_json(sibling)
        if prior['id'] != record['id'] and prior.get('started_at','') < record.get('started_at',''):
            previous.append(prior.get('results',{}).get('deploy',{}).get('runtime',{}).get('deployment_id'))
    artifacts.validate(results, identity, config['validation'], phase=record['phase'], previous_deployments=previous)
    decisions = validation.gates(results, config["validation"], phase=record["phase"])
    return {"trial": record["id"], "phase": record["phase"], "acceptance_scope": record.get("acceptance_scope", "FULL_TRIAL_CONTRACT"), "pass": all(gate["pass"] for gate in decisions), "gates": decisions}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == 'roles':
            from .roles import catalog
            print(json.dumps(catalog(), ensure_ascii=False, indent=2))
        elif args.command in ("defaults", "prepare", "doctor"):
            from . import brief
            if args.command == "defaults":value = brief.defaults()
            elif args.command == "prepare":value = brief.prepare(read_json(args.brief), args.out)
            else:value = brief.doctor(args.task, args.brief)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0 if value.get('status') != 'NEEDS_INPUT_OR_ACCESS' else 2
        elif args.command == "validate":
            if args.trial_dir:
                result = audit(args.task, args.trial_dir.resolve())
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result["pass"] else 2
            load(args.task)
            print("任务合同校验通过")
        elif args.command in ("run", "resume", "demo"):
            if args.command == "demo":
                specification = demo_task(agent=args.agent, pipeline=args.pipeline)
                path = args.run_dir.resolve() / "inputs" / "task.json"
                if path.exists():
                    raise KSEOError("示例运行目录已存在，请更换目录或使用 resume")
                write_json(path, specification)
            else:
                path = args.task.resolve() if args.command == "run" else None
            directory = args.run_dir
            state = Runner(directory).run(path)
            print(json.dumps({"状态": state["status"], "结果类型": read_json(directory / "task.json")["mode"],
                              "实验数量": len(state["trials"]), "最佳候选": state.get("best"),
                              "报告": str(directory.resolve() / "report.md")}, ensure_ascii=False, indent=2))
            return 0 if state["status"] in ("COMPLETED", "CANDIDATE_ONLY") else 2
        elif args.command == "status":
            state = read_json(args.run_dir / "state.json")
            print(json.dumps({"状态": state["status"], "累计秒数": state["elapsed_seconds"],
                              "当前实验": state.get("active_trial"), "最佳候选": state.get("best"),
                              "停止原因": state.get("stop_reason")}, ensure_ascii=False, indent=2))
        elif args.command == "knowledge":
            if args.limit < 1:
                raise KSEOError("--limit 必须至少为 1")
            from .knowledge_tree import inspect_node, overview, retrieve_hierarchy
            if args.extra and (args.tree or args.node or args.hierarchy):
                raise KSEOError("--extra 仅支持平面检索；未审阅卡片不能自动成为分层知识")
            if args.tree or args.node:
                if args.context:
                    raise KSEOError("目录/节点用于完整导航，不应用 context；条件筛选请使用 --hierarchy --context")
                value = inspect_node(args.node) if args.node else overview()
            else:
                if not args.context:
                    raise KSEOError("检索需要 --context；浏览目录请使用 --tree")
                context = read_json(args.context)
                if args.hierarchy:
                    value = retrieve_hierarchy(context, args.limit)
                else:
                    cards = [card for card in load_cards(args.extra) if card.get("status") != "NEEDS_REVIEW"]
                    value = retrieve(context, cards, args.limit)
            print(json.dumps(value, ensure_ascii=False, indent=2))
        elif args.command == "recipe":
            from .recipes import catalog, load_recipe
            value = load_recipe(args.name) if args.name else catalog()
            if args.out:
                if args.out.exists():
                    raise KSEOError("输出文件已存在，拒绝覆盖")
                write_json(args.out, value)
                print(f"经验 recipe 已导出：{args.out}；真实部署和验收仍须接入 adapter。")
            else:
                print(json.dumps(value, ensure_ascii=False, indent=2))
        elif args.command == "ingest":
            count = import_materials(args.paths, args.out)
            print(f"已导入 {count} 条待审经验：{args.out}；补齐适用条件并审查后才能进入自动检索。")
        elif args.command == "dataset":
            from . import datasets
            if (args.out or args.root) and not args.name:
                raise KSEOError("操作数据必须指定 name")
            if args.out and args.root:
                raise KSEOError("--out 与 --root 不能同时使用")
            if not args.name:
                value = datasets.catalog()
            elif args.out:
                value = datasets.export(args.name, args.out)
            else:
                value = datasets.verify(args.name, args.root)
            print(json.dumps(value, ensure_ascii=False, indent=2))
        elif args.command == "init":
            if args.out.exists():
                raise KSEOError("输出文件已存在，拒绝覆盖")
            config = read_json(args.profile) if args.profile else json.loads(files("kseo").joinpath("data/profile-a800.json").read_text())
            revision = args.revision
            if not revision:
                result = subprocess.run(["git", "-C", str(args.source), "rev-parse", "HEAD"], capture_output=True, text=True)
                if result.returncode:
                    raise KSEOError("无法读取 source HEAD，请提供 --revision")
                revision = result.stdout.strip()
            config["inputs"].update({"model": args.model, "image": args.image, "servers": args.server})
            config["source"] = {"kind": "git", "path": str(args.source.resolve()), "revision": revision}
            write_json(args.out, config)
            print(f"任务已生成：{args.out}；{'这是待补齐草稿。' if config.get('draft') else '运行前请执行 kseo validate。'}")
        return 0
    except (KSEOError, OSError, KeyError, ValueError) as exc:
        print(f"KSEO 错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
