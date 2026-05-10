"""Tests for rlsbl doctor command."""

import json
import os
import subprocess
from unittest.mock import patch

import pytest

from rlsbl.commands.doctor import (
    _check_changelog,
    _check_local_tag,
    _check_stale_lock,
    _check_version_consistency,
    _check_workflows_synced,
    _check_router_exists,
    _check_project_targets,
    _apply_fixes,
)


class TestDoctorChecks:
    """Tests for individual diagnostic check functions."""

    def test_stale_lock_pass(self, mock_git_repo):
        """No lock file exists -- should PASS."""
        status, message = _check_stale_lock()
        assert status == "PASS"
        assert "no lock file" in message

    def test_stale_lock_warn(self, mock_git_repo):
        """Stale lock file exists (written but not flocked) -- should WARN."""
        lock_dir = mock_git_repo / ".rlsbl"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "lock"
        lock_file.write_text("")

        status, message = _check_stale_lock()
        assert status == "WARN"
        assert "stale" in message

    def test_version_consistency_pass(self, mock_git_repo):
        """Single npm project with a version -- should PASS."""
        pkg = {"name": "test-pkg", "version": "1.2.3"}
        (mock_git_repo / "package.json").write_text(json.dumps(pkg))

        status, message = _check_version_consistency()
        assert status == "PASS"
        assert "1.2.3" in message

    def test_local_tag_pass(self, mock_git_repo):
        """Git tag exists -- should PASS."""
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=str(mock_git_repo),
            check=True,
        )
        status, message = _check_local_tag("v1.0.0")
        assert status == "PASS"
        assert "v1.0.0" in message

    def test_local_tag_warn(self, mock_git_repo):
        """No git tag -- should WARN."""
        status, message = _check_local_tag("v9.9.9")
        assert status == "WARN"
        assert "not found" in message

    def test_changelog_pass(self, mock_git_repo):
        """CHANGELOG.md with a matching version entry -- should PASS."""
        changelog = mock_git_repo / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## 2.0.0\n\nSome changes.\n")

        status, message = _check_changelog("2.0.0")
        assert status == "PASS"
        assert "2.0.0" in message

    def test_changelog_warn(self, mock_git_repo):
        """No CHANGELOG.md -- should WARN."""
        status, message = _check_changelog("2.0.0")
        assert status == "WARN"


class TestDoctorFix:
    """Tests for --fix auto-repair functionality."""

    def test_fix_removes_stale_lock(self, mock_git_repo):
        """Stale lock file should be removed when fix=True."""
        lock_dir = mock_git_repo / ".rlsbl"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "lock"
        lock_file.write_text("")

        # Build results dict matching what run_cmd would produce
        results = {
            "Lock file": ("WARN", "stale lock file exists"),
            "Version files": ("PASS", "1.0.0 across 1 target(s)"),
            "Local tag": ("PASS", "v1.0.0 exists"),
            "Remote tag": ("PASS", "v1.0.0 on origin"),
            "GitHub Release": ("PASS", "v1.0.0 exists"),
            "Branch sync": ("PASS", "up to date with origin/main"),
            "Changelog": ("PASS", "entry for 1.0.0"),
        }

        _apply_fixes(results, "v1.0.0", "1.0.0")
        assert not lock_file.exists()


class TestDoctorRegistration:
    """Tests for command registration in rlsbl."""

    def test_doctor_in_commands(self):
        """'doctor' should be in the COMMANDS tuple."""
        from rlsbl import COMMANDS
        assert "doctor" in COMMANDS

    def test_doctor_in_help(self):
        """'doctor' should appear in the HELP text."""
        from rlsbl import HELP
        assert "doctor" in HELP


class TestDoctorMonorepo:
    """Tests for monorepo workspace checks in doctor."""

    def _setup_monorepo(self, root, projects, create_workflows=True,
                        create_router=True, create_targets=True):
        """Helper to set up a monorepo structure.

        Creates workspace.toml, project dirs, and optionally workflows/targets.
        """
        ws_dir = root / ".rlsbl-monorepo"
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Build workspace.toml content
        lines = []
        for proj in projects:
            lines.append("[[projects]]")
            lines.append(f'path = "{proj["path"]}"')
            lines.append(f'name = "{proj["name"]}"')
            lines.append("")
        (ws_dir / "workspace.toml").write_text("\n".join(lines))

        # Create project directories and optional target files
        for proj in projects:
            proj_dir = root / proj["path"]
            proj_dir.mkdir(parents=True, exist_ok=True)
            if create_targets:
                pkg = {"name": proj["name"], "version": "1.0.0"}
                (proj_dir / "package.json").write_text(json.dumps(pkg))

        # Create workflow files
        if create_workflows:
            wf_dir = root / ".github" / "workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            for proj in projects:
                (wf_dir / f"{proj['name']}-ci.yml").write_text("on: push\n")

        if create_router:
            wf_dir = root / ".github" / "workflows"
            wf_dir.mkdir(parents=True, exist_ok=True)
            (wf_dir / "ci-router.yml").write_text("on: push\n")

    def test_monorepo_synced_pass(self, tmp_project):
        """All projects have synced workflows -- should PASS."""
        projects = [
            {"path": "packages/alpha", "name": "alpha"},
            {"path": "packages/beta", "name": "beta"},
        ]
        self._setup_monorepo(tmp_project, projects)

        proj_dicts = [{"path": str(tmp_project / p["path"]), "name": p["name"]}
                      for p in projects]

        status, message = _check_workflows_synced(str(tmp_project), proj_dicts)
        assert status == "PASS"
        assert "2 project(s)" in message

    def test_monorepo_missing_router_warn(self, tmp_project):
        """No ci-router.yml -- should WARN."""
        projects = [{"path": "packages/alpha", "name": "alpha"}]
        self._setup_monorepo(tmp_project, projects, create_router=False)

        status, message = _check_router_exists(str(tmp_project))
        assert status == "WARN"
        assert "not found" in message

    def test_no_monorepo_skips_checks(self, mock_git_repo, capsys):
        """When not in a monorepo, monorepo checks should not appear."""
        # mock_git_repo has no .rlsbl-monorepo/, so monorepo checks should be skipped
        pkg = {"name": "solo", "version": "1.0.0"}
        (mock_git_repo / "package.json").write_text(json.dumps(pkg))

        # We need to mock out the network-dependent checks
        with patch("rlsbl.commands.doctor._check_remote_tag",
                    return_value=("PASS", "v1.0.0 on origin")), \
             patch("rlsbl.commands.doctor._check_github_release",
                    return_value=("PASS", "v1.0.0 exists")), \
             patch("rlsbl.commands.doctor._check_branch_sync",
                    return_value=("PASS", "up to date")):
            from rlsbl.commands.doctor import run_cmd
            run_cmd(None, [], {})

        captured = capsys.readouterr()
        assert "Monorepo:" not in captured.out
