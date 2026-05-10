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
