"""只读历史源码，在运行目录内冻结和修改独立副本。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .util import KSEOError, confined, file_digest, write_json


def git(directory: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KSEOError(f"Git 操作无法完成: {exc}") from exc
    if result.returncode:
        raise KSEOError(f"Git 操作失败: {result.stderr.strip()[:700]}")
    return result.stdout.rstrip("\n")


def commit(directory: Path) -> str:
    git(directory, "add", "--all")
    git(directory, "-c", "user.name=KSEO", "-c", "user.email=kseo@localhost", "-c", "commit.gpgsign=false",
        "commit", "--quiet", "--allow-empty", "-m", "冻结 KSEO 实验源码")
    return git(directory, "rev-parse", "HEAD")


def freeze(config: dict, target: Path, config_dir: Path) -> str:
    specification = config.get("source")
    if target.exists():
        if (target.parent / "source_manifest.json").exists():
            return git(target, "rev-parse", "HEAD")
        shutil.rmtree(target)  # 仅清理本 run 内尚未完整冻结的副本。
    if not shutil.which("git"):
        raise KSEOError("需要安装 Git 才能冻结实验源码")
    target.parent.mkdir(parents=True, exist_ok=True)
    if specification and specification["kind"] == "git":
        source = Path(specification["path"])
        if not source.is_absolute():
            source = config_dir / source
        # 初始 clone 不依赖历史仓库的可回收对象，也不向历史仓库写入 worktree。
        git(target.parent, "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(source), str(target))
        git(target, "checkout", "--quiet", "--detach", specification["revision"])
    else:
        target.mkdir()
        if specification:
            base = (config_dir / specification["path"]).resolve()
            for name in specification["include"]:
                origin = confined(base, name)
                if origin.is_symlink() or not origin.is_file():
                    raise KSEOError(f"source.include 只接受常规文件: {name}")
                destination = confined(target, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, destination)
        git(target, "init", "--quiet")
        commit(target)
    revision = git(target, "rev-parse", "HEAD")
    write_json(target.parent / "source_manifest.json", {"revision": revision, "tree": git(target, "rev-parse", "HEAD^{tree}")})
    return revision


def fork(base: Path, target: Path, patch: Path | None = None) -> str:
    # shared clone 的对象源也在本次 run 内，保留整个 run 即可恢复。
    git(target.parent, "clone", "--quiet", "--shared", str(base), str(target))
    if patch:
        git(target, "apply", "--check", str(patch))
        git(target, "apply", str(patch))
        return commit(target)
    return git(target, "rev-parse", "HEAD")


def assert_unchanged(directory: Path, expected: str) -> None:
    if git(directory, "rev-parse", "HEAD") != expected or git(directory, "status", "--porcelain", "--untracked-files=normal"):
        raise KSEOError("adapter 执行期间修改了实验源码；本次测量失效")


def export_patch(baseline: Path, candidate: Path, destination: Path) -> str:
    # candidate 共享了 baseline 对象，可直接生成完整累积 diff。
    patch = git(candidate, "diff", "--binary", git(baseline, "rev-parse", "HEAD"), "HEAD")
    destination.write_text(patch + ("\n" if patch else ""), encoding="utf-8")
    return file_digest(destination)
