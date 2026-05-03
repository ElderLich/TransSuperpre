#!/usr/bin/env python3
import argparse
import subprocess
import sys
from dataclasses import dataclass


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        command = "git " + " ".join(args)
        stderr = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"{command} failed ({result.returncode}): {stderr}")
    return result


def git_stdout(args: list[str]) -> str:
    return run_git(args).stdout.strip()


def git_success(args: list[str]) -> bool:
    return run_git(args, check=False).returncode == 0


def require_inside_repo() -> None:
    run_git(["rev-parse", "--show-toplevel"])


def require_clean_worktree() -> None:
    status = git_stdout(["status", "--porcelain"])
    if status:
        raise SystemExit(
            "Working tree is not clean. Commit/stash your changes before rewriting branch history."
        )


def resolve_current_branch() -> str:
    result = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    branch = (result.stdout or "").strip()
    if result.returncode != 0 or not branch:
        raise SystemExit("Detached HEAD is not supported. Check out a branch first.")
    return branch


def resolve_commit(revision: str) -> str:
    return git_stdout(["rev-parse", "--verify", f"{revision}^{{commit}}"])


def resolve_parent(commit: str) -> str:
    result = run_git(["rev-parse", "--verify", f"{commit}^"], check=False)
    parent = (result.stdout or "").strip()
    if result.returncode != 0 or not parent:
        raise SystemExit("Removing the root commit is not supported by this script.")
    return parent


def list_commits(start: str, end: str) -> list[str]:
    output = git_stdout(["rev-list", "--reverse", "--ancestry-path", f"{start}^..{end}"])
    return [line for line in output.splitlines() if line.strip()]


def ensure_linear_history(base: str, head: str) -> None:
    output = git_stdout(["rev-list", "--parents", f"{base}..{head}"])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) > 2:
            raise SystemExit(
                "This script only supports linear history without merge commits in the rewritten segment."
            )


def prompt_for_confirmation() -> None:
    answer = input("Type DELETE to continue: ").strip()
    if answer != "DELETE":
        raise SystemExit("Aborted.")


@dataclass
class RewritePlan:
    branch: str
    remote: str
    start_commit: str
    end_commit: str
    start_short: str
    end_short: str
    base_commit: str
    head_before: str
    remove_to_head: bool
    push: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete a single commit or a contiguous commit range from the current branch, "
            "then optionally force-push the rewritten branch."
        )
    )
    parser.add_argument(
        "from_commit",
        help="First commit to remove (inclusive).",
    )
    parser.add_argument(
        "to_commit",
        nargs="?",
        help="Last commit to remove (inclusive). Defaults to the same commit as from_commit.",
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Branch to rewrite. Defaults to the currently checked out branch.",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Remote to force-push after rewriting. Default: origin.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Force-push the rewritten branch with --force-with-lease.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rewrite plan without changing anything.",
    )
    return parser


def build_plan(args: argparse.Namespace) -> RewritePlan:
    require_inside_repo()
    require_clean_worktree()

    current_branch = resolve_current_branch()
    target_branch = args.branch or current_branch
    if target_branch != current_branch:
        raise SystemExit(
            f"This script only rewrites the checked out branch. Current branch: {current_branch}, requested branch: {target_branch}."
        )

    head_before = resolve_commit(target_branch)
    start_commit = resolve_commit(args.from_commit)
    end_commit = resolve_commit(args.to_commit or args.from_commit)

    if not git_success(["merge-base", "--is-ancestor", start_commit, end_commit]):
        raise SystemExit(f"{start_commit[:12]} is not an ancestor of {end_commit[:12]}.")

    if not git_success(["merge-base", "--is-ancestor", end_commit, head_before]):
        raise SystemExit(
            f"{end_commit[:12]} is not reachable from the tip of {target_branch} ({head_before[:12]})."
        )

    base_commit = resolve_parent(start_commit)
    range_commits = list_commits(start_commit, end_commit)
    if not range_commits:
        raise SystemExit("Could not resolve any commits in the requested removal range.")
    if range_commits[0] != start_commit or range_commits[-1] != end_commit:
        raise SystemExit("The requested range is not a contiguous ancestry path.")

    ensure_linear_history(base_commit, head_before)

    return RewritePlan(
        branch=target_branch,
        remote=args.remote,
        start_commit=start_commit,
        end_commit=end_commit,
        start_short=start_commit[:12],
        end_short=end_commit[:12],
        base_commit=base_commit,
        head_before=head_before,
        remove_to_head=(end_commit == head_before),
        push=args.push,
    )


def print_plan(plan: RewritePlan) -> None:
    mode = "reset --hard" if plan.remove_to_head else "rebase --onto"
    print("Branch rewrite plan")
    print(f"- Branch: {plan.branch}")
    print(f"- Current HEAD: {plan.head_before[:12]}")
    print(f"- Remove from: {plan.start_short}")
    print(f"- Remove to: {plan.end_short}")
    print(f"- Parent kept: {plan.base_commit[:12]}")
    print(f"- Rewrite mode: {mode}")
    if plan.push:
        print(f"- Remote push: {plan.remote}/{plan.branch} with --force-with-lease")
    else:
        print("- Remote push: disabled")


def execute_plan(plan: RewritePlan) -> None:
    if plan.remove_to_head:
        run_git(["reset", "--hard", plan.base_commit])
    else:
        run_git(["rebase", "--onto", plan.base_commit, plan.end_commit])

    if plan.push:
        run_git(["push", "--force-with-lease", plan.remote, plan.branch])


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    plan = build_plan(args)
    print_plan(plan)

    if args.dry_run:
        return

    if not args.yes:
        prompt_for_confirmation()

    execute_plan(plan)
    new_head = resolve_commit(plan.branch)
    print("")
    print("Rewrite completed")
    print(f"- New HEAD: {new_head[:12]}")
    if plan.push:
        print(f"- Remote updated: {plan.remote}/{plan.branch}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Aborted.")
