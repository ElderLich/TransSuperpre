#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local helper for uploading translator workspace files to TransSuperpre.

The GitHub Actions workflows own the real build now. This helper only copies the
local translator files into the repo Workspace folder and optionally commits and
pushes those Workspace changes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GH_REPO = os.environ.get("TRANSSUPERPRE_GH_REPO", "ElderLich/TransSuperpre")


@dataclass(frozen=True)
class LangConfig:
    key: str
    folder: str


LANGS = {
    "de": LangConfig("de", "DE"),
    "en": LangConfig("en", "EN"),
    "es": LangConfig("es", "ES"),
    "fr": LangConfig("fr", "FR"),
    "it": LangConfig("it", "IT"),
    "jp": LangConfig("jp", "JP"),
    "kr": LangConfig("kr", "KR"),
    "pt": LangConfig("pt", "PT"),
}

REQUIRED_WORKSPACE_FILES = ("test-release.cdb", "test-strings.conf")
OPTIONAL_ROOT_FILES = ("Mappings.csv",)
LOCAL_ROOT_ENV = "SUPER_PRE_LOCAL_ROOT"


def log(message: str) -> None:
    print(f"[local-workspace] {message}")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def looks_like_local_root(path: Path) -> bool:
    return any((path / config.folder / "raw2").is_dir() for config in LANGS.values())


def discover_local_root(lang: str | None = None) -> Path | None:
    env_value = os.environ.get(LOCAL_ROOT_ENV)
    if env_value:
        return Path(env_value).expanduser()

    cwd = Path.cwd().resolve()
    candidates = [cwd, *cwd.parents]
    folder = LANGS[lang].folder if lang in LANGS else None
    for candidate in candidates:
        if folder and candidate.name.lower() == folder.lower() and (candidate / "raw2").is_dir():
            return candidate.parent
        if looks_like_local_root(candidate):
            return candidate
    return None


def resolve_local_root(value: str | None, lang: str) -> Path:
    if value:
        return Path(value).expanduser()
    discovered = discover_local_root(lang)
    if discovered:
        return discovered
    fail(
        "local translation root was not found. Pass --local-root, set SUPER_PRE_LOCAL_ROOT, "
        "or run through the locale AutoPR.py wrapper."
    )


def local_paths(args: argparse.Namespace, config: LangConfig) -> tuple[Path, Path, Path]:
    local_root = resolve_local_root(args.local_root, config.key)
    repo_root = Path(args.repo_root).expanduser()
    local_dir = local_root / config.folder
    source_dir = local_dir / args.source_dir
    workspace_dir = repo_root / config.folder / "Workspace"
    if not local_dir.exists():
        fail(f"local locale folder not found: {local_dir}")
    if not source_dir.exists():
        fail(f"source folder not found: {source_dir}")
    if not repo_root.exists():
        fail(f"TransSuperpre repo not found: {repo_root}")
    return local_dir, source_dir, workspace_dir


def copy_workspace(args: argparse.Namespace) -> list[Path]:
    config = LANGS[args.lang]
    local_dir, source_dir, workspace_dir = local_paths(args, config)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    changed_paths: list[Path] = []
    for filename in REQUIRED_WORKSPACE_FILES:
        source = source_dir / filename
        target = workspace_dir / filename
        if not source.exists():
            fail(f"required file missing: {source}")
        if args.dry_run:
            log(f"would copy {source} -> {target}")
        else:
            shutil.copy2(source, target)
            log(f"copied {source} -> {target}")
        changed_paths.append(target)

    if not args.no_mappings:
        for filename in OPTIONAL_ROOT_FILES:
            source = local_dir / filename
            target = workspace_dir / filename
            if not source.exists():
                log(f"optional file not found, skipping: {source}")
                continue
            if args.dry_run:
                log(f"would copy {source} -> {target}")
            else:
                shutil.copy2(source, target)
                log(f"copied {source} -> {target}")
            changed_paths.append(target)

    return changed_paths


def ensure_no_staged_changes(repo_root: Path) -> None:
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_root))
    if result.returncode != 0:
        fail("repo already has staged changes; commit or unstage them before using --push")


def commit_and_push(args: argparse.Namespace, paths: list[Path]) -> None:
    repo_root = Path(args.repo_root).expanduser()
    ensure_no_staged_changes(repo_root)
    rel_paths = [repo_relative(repo_root, path) for path in paths]
    run(["git", "add", "-A", "--", *rel_paths], repo_root)

    diff_result = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *rel_paths], cwd=str(repo_root))
    if diff_result.returncode == 0:
        log("no workspace changes to commit")
        return

    message = args.message or f"Update {LANGS[args.lang].folder} workspace"
    run(["git", "commit", "-m", message], repo_root)
    run(["git", "push", "origin", "main"], repo_root)


def command_upload(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser()
    if args.pull_first:
        run(["git", "pull", "--ff-only", "origin", "main"], repo_root)
    changed_paths = copy_workspace(args)
    if args.push:
        commit_and_push(args, changed_paths)
    elif args.dry_run:
        log("dry run completed; no files were copied")
    else:
        log("copied files only; run with --push to commit and push")


def command_pull(args: argparse.Namespace) -> None:
    run(["git", "pull", "--ff-only", "origin", "main"], Path(args.repo_root).expanduser())


def command_status(args: argparse.Namespace) -> None:
    repo_root = Path(args.repo_root).expanduser()
    run(["git", "status", "--short", "--branch"], repo_root, check=False)
    command_actions(args)


def command_actions(args: argparse.Namespace) -> None:
    gh = shutil.which("gh")
    if not gh:
        log("GitHub CLI not found; open https://github.com/ElderLich/TransSuperpre/actions")
        return
    cmd = [
        gh,
        "run",
        "list",
        "--repo",
        args.gh_repo,
        "--limit",
        str(args.limit),
        "--json",
        "databaseId,name,status,conclusion,headSha,event,createdAt",
        "--jq",
        '.[] | [.databaseId,.name,.event,.status,(.conclusion//""),.headSha[0:7],.createdAt] | @tsv',
    ]
    log("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(Path(args.repo_root).expanduser()), text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        log("GitHub Actions status unavailable; check network/proxy/auth or open the Actions page manually")
        if result.stderr:
            print(result.stderr.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT), help="Path to the TransSuperpre repo")
    parser.add_argument(
        "--local-root",
        help="Path to the local translation workspace root. Defaults to SUPER_PRE_LOCAL_ROOT or auto-discovery from the current folder.",
    )
    parser.add_argument("--gh-repo", default=DEFAULT_GH_REPO, help="GitHub repo for gh run list")

    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="Copy local files into <lang>/Workspace")
    upload.add_argument("--lang", choices=sorted(LANGS), required=True)
    upload.add_argument("--source-dir", default="raw2", help="Local source folder inside the locale folder")
    upload.add_argument("--no-mappings", action="store_true", help="Do not copy Mappings.csv")
    upload.add_argument("--push", action="store_true", help="Commit and push copied Workspace files")
    upload.add_argument("--pull-first", action="store_true", help="Run git pull --ff-only before copying")
    upload.add_argument("--message", help="Commit message when --push is used")
    upload.add_argument("--dry-run", action="store_true", help="Show what would be copied")
    upload.set_defaults(func=command_upload)

    pull = subparsers.add_parser("pull", help="Fast-forward local TransSuperpre main")
    pull.set_defaults(func=command_pull)

    status = subparsers.add_parser("status", help="Show git status and recent GitHub Actions")
    status.add_argument("--lang", choices=sorted(LANGS), help="Accepted for wrapper compatibility")
    status.add_argument("--limit", type=int, default=8)
    status.set_defaults(func=command_status)

    actions = subparsers.add_parser("actions", help="Show recent GitHub Actions")
    actions.add_argument("--lang", choices=sorted(LANGS), help="Accepted for wrapper compatibility")
    actions.add_argument("--limit", type=int, default=12)
    actions.set_defaults(func=command_actions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
