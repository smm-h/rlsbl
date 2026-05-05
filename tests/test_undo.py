"""Tests for rlsbl.commands.undo — happy-path full flow."""

import unittest
from io import StringIO
from unittest.mock import patch, call

from rlsbl.commands.undo import run_cmd


class TestUndoHappyPath(unittest.TestCase):
    """Verify the full undo flow succeeds when all subprocess calls pass."""

    @patch("rlsbl.commands.undo.push_if_needed")
    @patch("rlsbl.commands.undo.get_current_branch", return_value="main")
    @patch("rlsbl.commands.undo.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.undo.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.undo.check_gh_installed", return_value=True)
    @patch("rlsbl.commands.undo.run")
    def test_full_undo_flow(self, mock_run, _gh_inst, _gh_auth, _clean,
                            mock_branch, mock_push):
        """Happy path: all steps succeed, exits cleanly with no exception."""

        # Map each run() call to its expected return value.
        # The undo command calls run() in this order:
        #   1. git describe --tags --abbrev=0 -> tag name
        #   2. gh release delete <tag> --yes -> success (return value ignored)
        #   3. git push origin :<tag> -> success
        #   4. git tag -d <tag> -> success
        #   5. git log -1 --format=%s -> HEAD commit message (matches tag)
        #   6. git revert --no-edit HEAD -> success
        mock_run.side_effect = [
            "v1.0.0",   # git describe --tags --abbrev=0
            "",         # gh release delete v1.0.0 --yes
            "",         # git push origin :v1.0.0
            "",         # git tag -d v1.0.0
            "v1.0.0",  # git log -1 --format=%s
            "",         # git revert --no-edit HEAD
        ]

        # Run with --yes to skip interactive prompts; suppress stdout
        with patch("sys.stdout", new_callable=StringIO):
            run_cmd("npm", [], {"yes": True})

        # Verify all expected subprocess commands were issued
        expected_calls = [
            call("git", ["describe", "--tags", "--abbrev=0"]),
            call("gh", ["release", "delete", "v1.0.0", "--yes"]),
            call("git", ["push", "origin", ":v1.0.0"], timeout=120),
            call("git", ["tag", "-d", "v1.0.0"]),
            call("git", ["log", "-1", "--format=%s"]),
            call("git", ["revert", "--no-edit", "HEAD"]),
        ]
        mock_run.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(mock_run.call_count, 6)

        # Verify push_if_needed was called with the current branch
        mock_push.assert_called_once_with("main")


if __name__ == "__main__":
    unittest.main()
