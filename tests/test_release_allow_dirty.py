"""Tests for --allow-dirty flag on rlsbl release."""

import json
import os
import shutil
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch


class TestReleaseAllowDirty(unittest.TestCase):
    """Tests that --allow-dirty skips the clean-tree check."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)
        # Create package.json so npm registry is detected
        with open("package.json", "w") as f:
            json.dump({"name": "test-pkg", "version": "1.0.0"}, f, indent=2)
            f.write("\n")
        # Create CHANGELOG.md with entry for the bumped version
        with open("CHANGELOG.md", "w") as f:
            f.write("# Changelog\n\n## 1.0.1\n\nPatch release with bugfixes and improvements.\n")

    def tearDown(self):
        os.chdir(self.orig_dir)
        shutil.rmtree(self.tmp_dir)

    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    @patch("rlsbl.commands.release.is_clean_tree", return_value=False)
    def test_dirty_tree_without_allow_dirty_exits(self, _clean, _gh_auth, _gh_inst):
        """Without --allow-dirty, a dirty tree should cause SystemExit."""
        from rlsbl.commands.release import run_cmd

        with self.assertRaises(SystemExit) as ctx:
            run_cmd("npm", ["patch"], {"quiet": True})
        self.assertEqual(ctx.exception.code, 1)

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.find_commit_tool", return_value="git")
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=False)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_allow_dirty_skips_clean_tree_check(self, _gh_inst, _gh_auth, _clean,
                                                 _branch, _commit_tool, mock_run, _push):
        """With --allow-dirty, a dirty tree should not block the release (dry-run)."""
        from rlsbl.commands.release import run_cmd

        # 1. git fetch origin --quiet
        # 2. git rev-list --count HEAD..origin/main
        # 3. tag -l for current version (exists -> bump)
        # 4. tag -l for bumped version (doesn't exist -> proceed)
        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with patch("sys.stdout", new_callable=StringIO):
            # Should not raise SystemExit
            run_cmd("npm", ["patch"], {
                "allow-dirty": True,
                "dry-run": True,
                "quiet": False,
            })


if __name__ == "__main__":
    unittest.main()
