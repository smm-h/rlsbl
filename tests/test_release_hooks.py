"""Tests for pre-release and post-release hook output streaming."""

import json
import os
import subprocess
from unittest.mock import patch

import pytest

from rlsbl.utils import get_hook_timeout


def _setup_project(tmp_path, hook_name, hook_body):
    """Create a minimal project with a hook script.

    Returns the path to the hook script.
    """
    # package.json so npm registry is detected
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "test-pkg", "version": "1.0.0"}) + "\n"
    )
    # Changelog with bumped version entry
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.0.1\n\nPatch release with improvements.\n"
    )
    # Hook script
    hooks_dir = tmp_path / ".rlsbl" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_script = hooks_dir / hook_name
    hook_script.write_text(hook_body)
    hook_script.chmod(0o755)
    return str(hook_script)


class TestPreReleaseHookOutput:
    """Tests for pre-release hook streaming and error handling."""

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_hook_streams_output(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
    ):
        """A successful hook is called via subprocess.run without capture_output."""
        _setup_project(tmp_project, "pre-release.sh", "#!/bin/bash\necho hello\n")
        # mock_run side effects: fetch, rev-list, tag -l current, tag -l bumped
        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with patch("rlsbl.commands.release.subprocess") as mock_sp:
            mock_sp.run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            # dry-run to avoid needing full release mocks
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": True, "yes": True})

            # Verify subprocess.run was called for the hook
            assert mock_sp.run.call_count == 1
            call_args = mock_sp.run.call_args
            # Should NOT have capture_output in kwargs
            assert "capture_output" not in call_args.kwargs
            # Should have check=True
            assert call_args.kwargs.get("check") is True

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_hook_exit_code_in_error_message(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
        capsys,
    ):
        """A hook exiting with code 2 produces an error mentioning 'exited with code 2'."""
        _setup_project(tmp_project, "pre-release.sh", "#!/bin/bash\nexit 2\n")
        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with patch("rlsbl.commands.release.subprocess") as mock_sp:
            mock_sp.run.side_effect = subprocess.CalledProcessError(2, "bash")
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            with pytest.raises(SystemExit) as exc_info:
                run_cmd("npm", ["patch"], {"quiet": True, "yes": True})

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "exited with code 2" in captured.err

    def test_missing_hook_is_skipped(self, tmp_project):
        """When no pre-release hook exists, release does not error on it."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test-pkg", "version": "1.0.0"}) + "\n"
        )
        (tmp_project / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 1.0.1\n\nPatch release.\n"
        )
        # No .rlsbl/hooks/pre-release.sh created

        with (
            patch("rlsbl.commands.release.push_if_needed"),
            patch("rlsbl.commands.release.run") as mock_run,
            patch("rlsbl.commands.release.commit_files", return_value=True),
            patch("rlsbl.commands.release.get_current_branch", return_value="main"),
            patch("rlsbl.commands.release.is_clean_tree", return_value=True),
            patch("rlsbl.commands.release.check_gh_auth", return_value=True),
            patch("rlsbl.commands.release.check_gh_installed", return_value=True),
            patch("rlsbl.commands.release.subprocess") as mock_sp,
        ):
            mock_run.side_effect = ["", "0", "v1.0.0", ""]
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            # dry-run: should complete without subprocess.run being called for hooks
            run_cmd("npm", ["patch"], {"dry-run": True, "quiet": True, "yes": True})
            mock_sp.run.assert_not_called()


class TestPostReleaseHookOutput:
    """Tests for post-release hook streaming and error handling."""

    @patch("rlsbl.commands.release.read_deploy_config", return_value=([], []))
    @patch("rlsbl.commands.release.should_tag", return_value=False)
    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_failed_hook_is_non_fatal(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        _push,
        _should_tag,
        _deploy,
        tmp_project,
        capsys,
    ):
        """A failing post-release hook prints a warning but does not abort."""
        _setup_project(tmp_project, "post-release.sh", "#!/bin/bash\nexit 3\n")

        def fake_run(cmd, args=None, timeout=120, env=None):
            """Return sensible defaults for all run() calls in the release flow."""
            full = [cmd] + (args or [])
            joined = " ".join(full)
            if "rev-list" in joined:
                return "0"
            if "tag" in joined and "-l" in joined:
                # First tag check (current version): exists; second (bumped): does not
                if "v1.0.0" in joined:
                    return "v1.0.0"
                return ""
            if "rev-parse" in joined:
                return "abc123"
            if "status --porcelain" in joined:
                return ""
            if "diff --name-only" in joined:
                return ""
            return ""

        def fake_subprocess_run(cmd, **kwargs):
            script = cmd[1] if len(cmd) > 1 else ""
            if "post-release.sh" in script:
                raise subprocess.CalledProcessError(3, "bash")
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        with (
            patch("rlsbl.commands.release.run", side_effect=fake_run),
            patch("rlsbl.commands.release.subprocess") as mock_sp,
        ):
            mock_sp.run.side_effect = fake_subprocess_run
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            # Should NOT raise -- post-release hook failure is non-fatal
            run_cmd("npm", ["patch"], {"quiet": True, "yes": True})

        captured = capsys.readouterr()
        assert "exited with code 3" in captured.err


class TestWatchSHABeforePostHook:
    """Test that the watch SHA is captured before post-release hooks run."""

    @patch("rlsbl.commands.release.read_deploy_config", return_value=([], []))
    @patch("rlsbl.commands.release.should_tag", return_value=False)
    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_watch_sha_is_pre_hook_commit(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        _push,
        _should_tag,
        _deploy,
        tmp_project,
        capsys,
    ):
        """Watch SHA should be the pushed commit, not HEAD after post-release hook."""
        _setup_project(tmp_project, "post-release.sh", "#!/bin/bash\necho ok\n")

        pre_hook_sha = "aaa111"
        post_hook_sha = "bbb222"
        rev_parse_call_count = 0

        def fake_run(cmd, args=None, timeout=120, env=None):
            nonlocal rev_parse_call_count
            full = [cmd] + (args or [])
            joined = " ".join(full)
            if "rev-list" in joined:
                return "0"
            if "tag" in joined and "-l" in joined:
                if "v1.0.0" in joined:
                    return "v1.0.0"
                return ""
            if "rev-parse" in joined:
                # First call (after push, before post-release hook): return pre-hook SHA
                # Any subsequent call would return post-hook SHA
                rev_parse_call_count += 1
                if rev_parse_call_count == 1:
                    return pre_hook_sha
                return post_hook_sha
            if "status --porcelain" in joined:
                return ""
            if "diff --name-only" in joined:
                return ""
            return ""

        def fake_subprocess_run(cmd, **kwargs):
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        with (
            patch("rlsbl.commands.release.run", side_effect=fake_run),
            patch("rlsbl.commands.release.subprocess") as mock_sp,
        ):
            mock_sp.run.side_effect = fake_subprocess_run
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            run_cmd("npm", ["patch"], {"yes": True})

        captured = capsys.readouterr()
        # The watch message must use the SHA captured before the post-release hook
        assert f"rlsbl watch {pre_hook_sha}" in captured.out
        assert post_hook_sha not in captured.out


class TestHookTimeout:
    """Tests for RLSBL_HOOK_TIMEOUT integration with hooks."""

    def test_get_hook_timeout_no_env(self, monkeypatch):
        monkeypatch.delenv("RLSBL_HOOK_TIMEOUT", raising=False)
        assert get_hook_timeout() is None

    def test_get_hook_timeout_valid(self, monkeypatch):
        monkeypatch.setenv("RLSBL_HOOK_TIMEOUT", "60")
        assert get_hook_timeout() == 60

    def test_get_hook_timeout_invalid_warns(self, monkeypatch, capsys):
        monkeypatch.setenv("RLSBL_HOOK_TIMEOUT", "abc")
        assert get_hook_timeout() is None
        captured = capsys.readouterr()
        assert "invalid RLSBL_HOOK_TIMEOUT" in captured.err

    @patch("rlsbl.commands.release.push_if_needed")
    @patch("rlsbl.commands.release.run")
    @patch("rlsbl.commands.release.commit_files", return_value=True)
    @patch("rlsbl.commands.release.get_current_branch", return_value="main")
    @patch("rlsbl.commands.release.is_clean_tree", return_value=True)
    @patch("rlsbl.commands.release.check_gh_auth", return_value=True)
    @patch("rlsbl.commands.release.check_gh_installed", return_value=True)
    def test_pre_release_timeout_message_includes_seconds(
        self,
        _gh_inst,
        _gh_auth,
        _clean,
        _branch,
        _commit_files,
        mock_run,
        _push,
        tmp_project,
        monkeypatch,
        capsys,
    ):
        """When a pre-release hook times out, the error message includes the configured seconds."""
        monkeypatch.setenv("RLSBL_HOOK_TIMEOUT", "45")
        _setup_project(tmp_project, "pre-release.sh", "#!/bin/bash\nsleep 999\n")
        mock_run.side_effect = ["", "0", "v1.0.0", ""]

        with patch("rlsbl.commands.release.subprocess") as mock_sp:
            mock_sp.run.side_effect = subprocess.TimeoutExpired("bash", 45)
            mock_sp.CalledProcessError = subprocess.CalledProcessError
            mock_sp.TimeoutExpired = subprocess.TimeoutExpired

            from rlsbl.commands.release import run_cmd

            with pytest.raises(SystemExit) as exc_info:
                run_cmd("npm", ["patch"], {"quiet": True, "yes": True})

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "timed out after 45s" in captured.err
