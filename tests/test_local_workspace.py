"""Regression coverage for the local translator workspace helper."""

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Tools"))
import local_workspace


class RefreshParserTests(unittest.TestCase):
    def test_refresh_pulls_latest_main_by_default(self):
        args = local_workspace.build_parser().parse_args(["refresh", "--lang", "en"])
        self.assertTrue(args.pull_first)

    def test_refresh_can_explicitly_skip_pull(self):
        args = local_workspace.build_parser().parse_args(
            ["refresh", "--lang", "en", "--no-pull-first"]
        )
        self.assertFalse(args.pull_first)


class RefreshCommandTests(unittest.TestCase):
    def test_pull_happens_before_refresh_and_mapping_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo_root = root / "repo"
            local_dir = root / "translations" / "EN"
            source_dir = local_dir / "raw2"
            events = []

            def record_run(cmd, cwd, **kwargs):
                events.append(("run", cmd, cwd))

            def record_mapping_copy(repo, local, **kwargs):
                events.append(("mappings", repo, local))

            args = Namespace(
                lang="en",
                local_root=str(root / "translations"),
                repo_root=str(repo_root),
                source_dir="raw2",
                pull_first=True,
            )

            with (
                patch.object(
                    local_workspace,
                    "local_paths",
                    return_value=(local_dir, source_dir, repo_root / "EN" / "Workspace"),
                ),
                patch.object(local_workspace, "run", side_effect=record_run),
                patch.object(
                    local_workspace,
                    "sync_shared_mappings_to_local",
                    side_effect=record_mapping_copy,
                ),
            ):
                local_workspace.command_refresh(args)

            self.assertEqual(events[0], ("run", ["git", "pull", "--ff-only", "origin", "main"], repo_root))
            self.assertEqual(events[1][0], "run")
            self.assertEqual(events[2], ("mappings", repo_root, local_dir))


if __name__ == "__main__":
    unittest.main()
