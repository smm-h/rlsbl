"""Tests for docs deploy providers (Cloudflare Pages and GitHub Pages)."""

import os
import subprocess
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from rlsbl.targets.docs.deploy import (
    deploy_cloudflare_pages,
    deploy_github_pages,
    DeployError,
)
from rlsbl.targets.docs import DocsTarget


# -- Cloudflare Pages tests --


class TestDeployCloudflarePages:
    """Tests for the Cloudflare Pages deploy provider."""

    def test_missing_wrangler_raises(self):
        """Should raise DeployError when wrangler is not installed."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(DeployError, match="wrangler CLI not found"):
                deploy_cloudflare_pages("/tmp/out", "my-project", "1.0.0")

    def test_correct_command_constructed(self):
        """Should call wrangler with the correct arguments."""
        with patch("shutil.which", return_value="/usr/bin/wrangler"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                deploy_cloudflare_pages("/path/to/output", "my-docs", "2.1.0")

                mock_run.assert_called_once()
                call_args = mock_run.call_args
                cmd = call_args[0][0]
                assert cmd == [
                    "wrangler",
                    "pages",
                    "deploy",
                    "/path/to/output",
                    "--project-name=my-docs",
                    "--commit-message=v2.1.0",
                ]
                assert call_args[1]["timeout"] == 120
                assert call_args[1]["capture_output"] is True

    def test_nonzero_exit_raises(self):
        """Should raise DeployError on non-zero exit code."""
        with patch("shutil.which", return_value="/usr/bin/wrangler"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="Authentication failed",
                )
                with pytest.raises(DeployError, match="deploy failed"):
                    deploy_cloudflare_pages("/out", "proj", "1.0.0")

    def test_timeout_raises(self):
        """Should raise DeployError on timeout."""
        with patch("shutil.which", return_value="/usr/bin/wrangler"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd="wrangler", timeout=120
                )
                with pytest.raises(DeployError, match="timed out"):
                    deploy_cloudflare_pages("/out", "proj", "1.0.0")


# -- GitHub Pages tests --


class TestDeployGitHubPages:
    """Tests for the GitHub Pages deploy provider."""

    def test_missing_remote_raises(self):
        """Should raise DeployError when git remote is not configured."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git remote get-url origin"
            )
            with pytest.raises(DeployError, match="remote URL"):
                deploy_github_pages("/out", "1.0.0")

    def test_git_commands_called_in_order(self):
        """Should call git commands in the correct sequence."""
        with tempfile.TemporaryDirectory() as output_dir:
            # Create some dummy output content
            with open(os.path.join(output_dir, "index.html"), "w") as f:
                f.write("<html></html>")
            os.makedirs(os.path.join(output_dir, "api"))
            with open(os.path.join(output_dir, "api", "ref.html"), "w") as f:
                f.write("<html>api</html>")

            calls = []

            def mock_run(cmd, **kwargs):
                calls.append((cmd, kwargs.get("cwd")))
                result = MagicMock()
                result.returncode = 0
                result.stdout = "git@github.com:user/repo.git\n"
                result.stderr = ""
                return result

            with patch("subprocess.run", side_effect=mock_run):
                deploy_github_pages(output_dir, "3.0.0")

            # Extract just the git commands (not cwd)
            git_cmds = [c[0] for c in calls]

            # First call: get remote URL
            assert git_cmds[0] == ["git", "remote", "get-url", "origin"]

            # Second: init in temp dir
            assert git_cmds[1] == ["git", "init"]

            # Third: create gh-pages branch
            assert git_cmds[2] == ["git", "checkout", "-b", "gh-pages"]

            # Fourth: add all files
            assert git_cmds[3] == ["git", "add", "."]

            # Fifth: commit
            assert git_cmds[4] == ["git", "commit", "-m", "docs: v3.0.0"]

            # Sixth: force-push
            assert git_cmds[5][:3] == ["git", "push", "--force"]
            assert "gh-pages" in git_cmds[5]

    def test_nojekyll_file_created(self):
        """Should create a .nojekyll file in the deployed content."""
        with tempfile.TemporaryDirectory() as output_dir:
            with open(os.path.join(output_dir, "index.html"), "w") as f:
                f.write("<html></html>")

            # Track what files exist when git add is called
            added_files = []

            def mock_run(cmd, **kwargs):
                cwd = kwargs.get("cwd")
                if cmd == ["git", "add", "."] and cwd:
                    # Record that .nojekyll exists at add time
                    nojekyll = os.path.join(cwd, ".nojekyll")
                    added_files.append(os.path.exists(nojekyll))
                result = MagicMock()
                result.returncode = 0
                result.stdout = "git@github.com:user/repo.git\n"
                result.stderr = ""
                return result

            with patch("subprocess.run", side_effect=mock_run):
                deploy_github_pages(output_dir, "1.0.0")

            # .nojekyll should have existed when git add was called
            assert added_files == [True]

    def test_output_files_copied(self):
        """Should copy all output files into the temp deploy directory."""
        with tempfile.TemporaryDirectory() as output_dir:
            # Create files and subdirectory
            with open(os.path.join(output_dir, "index.html"), "w") as f:
                f.write("<html>root</html>")
            sub = os.path.join(output_dir, "sub")
            os.makedirs(sub)
            with open(os.path.join(sub, "page.html"), "w") as f:
                f.write("<html>sub</html>")

            # Track files present at commit time
            committed_files = []

            def mock_run(cmd, **kwargs):
                cwd = kwargs.get("cwd")
                if cmd[0:2] == ["git", "commit"] and cwd:
                    # Walk tmp dir to see what was staged
                    for root, dirs, files in os.walk(cwd):
                        # Skip .git directory
                        dirs[:] = [d for d in dirs if d != ".git"]
                        for f in files:
                            rel = os.path.relpath(
                                os.path.join(root, f), cwd
                            )
                            committed_files.append(rel)
                result = MagicMock()
                result.returncode = 0
                result.stdout = "git@github.com:user/repo.git\n"
                result.stderr = ""
                return result

            with patch("subprocess.run", side_effect=mock_run):
                deploy_github_pages(output_dir, "1.0.0")

            assert "index.html" in committed_files
            assert os.path.join("sub", "page.html") in committed_files
            assert ".nojekyll" in committed_files

    def test_push_timeout_raises(self):
        """Should raise DeployError if push times out."""
        with tempfile.TemporaryDirectory() as output_dir:
            with open(os.path.join(output_dir, "index.html"), "w") as f:
                f.write("<html></html>")

            call_count = [0]

            def mock_run(cmd, **kwargs):
                call_count[0] += 1
                # The push is the 6th call; make it timeout
                if "push" in cmd:
                    raise subprocess.TimeoutExpired(cmd="git push", timeout=120)
                result = MagicMock()
                result.returncode = 0
                result.stdout = "git@github.com:user/repo.git\n"
                result.stderr = ""
                return result

            with patch("subprocess.run", side_effect=mock_run):
                with pytest.raises(DeployError, match="timed out"):
                    deploy_github_pages(output_dir, "1.0.0")

    def test_push_failure_raises(self):
        """Should raise DeployError if push fails."""
        with tempfile.TemporaryDirectory() as output_dir:
            with open(os.path.join(output_dir, "index.html"), "w") as f:
                f.write("<html></html>")

            def mock_run(cmd, **kwargs):
                if "push" in cmd:
                    raise subprocess.CalledProcessError(
                        128, cmd, stderr="Permission denied"
                    )
                result = MagicMock()
                result.returncode = 0
                result.stdout = "git@github.com:user/repo.git\n"
                result.stderr = ""
                return result

            with patch("subprocess.run", side_effect=mock_run):
                with pytest.raises(DeployError, match="Failed to push"):
                    deploy_github_pages(output_dir, "1.0.0")


# -- DocsTarget.publish() integration tests --


class TestDocsTargetPublish:
    """Tests for DocsTarget.publish() dispatch logic."""

    def test_publish_no_config_returns_none(self):
        """publish() should exit early when no docs.toml exists."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # No .rlsbl/docs.toml -- should not raise
            target.publish(d, "1.0.0")

    def test_publish_missing_output_dir_warns(self, capsys):
        """publish() should warn when output directory doesn't exist."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # Create config pointing to non-existent output dir
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(
                    '[source]\ntype = "python"\npaths = ["src/"]\n\n'
                    '[output]\ndir = "docs/_build"\n\n'
                    '[deploy]\nprovider = "github-pages"\n'
                )

            target.publish(d, "1.0.0")
            captured = capsys.readouterr()
            assert "output directory not found" in captured.err

    def test_publish_cloudflare_dispatches(self):
        """publish() should call deploy_cloudflare_pages for cloudflare provider."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # Config
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(
                    '[source]\ntype = "python"\npaths = ["src/"]\n\n'
                    '[output]\ndir = "out"\n\n'
                    '[deploy]\nprovider = "cloudflare-pages"\nproject = "my-proj"\n'
                )
            # Create output dir
            os.makedirs(os.path.join(d, "out"))

            with patch(
                "rlsbl.targets.docs.deploy.deploy_cloudflare_pages"
            ) as mock_cf:
                target.publish(d, "2.0.0")
                mock_cf.assert_called_once_with(
                    os.path.join(d, "out"), "my-proj", "2.0.0"
                )

    def test_publish_github_pages_dispatches(self):
        """publish() should call deploy_github_pages for github-pages provider."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # Config
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(
                    '[source]\ntype = "python"\npaths = ["src/"]\n\n'
                    '[output]\ndir = "site"\n\n'
                    '[deploy]\nprovider = "github-pages"\n'
                )
            # Create output dir
            os.makedirs(os.path.join(d, "site"))

            with patch(
                "rlsbl.targets.docs.deploy.deploy_github_pages"
            ) as mock_gh:
                target.publish(d, "1.5.0")
                mock_gh.assert_called_once_with(
                    os.path.join(d, "site"), "1.5.0"
                )
