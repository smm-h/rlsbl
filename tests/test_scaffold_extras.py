"""Tests for scaffold extras: --force USER_OWNED behavior and auto-commit."""

import os
import subprocess

from rlsbl.commands.init_cmd import (
    USER_OWNED,
    _finalize_scaffold,
    process_mappings,
)


def _write_file(path, content):
    """Helper to write a file, creating parent dirs as needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_force_does_not_overwrite_changelog(tmp_project):
    """--force must NOT overwrite CHANGELOG.md if it already exists."""
    assert "CHANGELOG.md" in USER_OWNED

    # Pre-existing user content
    changelog = tmp_project / "CHANGELOG.md"
    changelog.write_text("# My Custom Changelog\n\nUser content here.\n")

    # Set up a template directory with a CHANGELOG.md template
    tpl_dir = tmp_project / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "changelog.tpl").write_text("# Changelog\n\nTemplate content.\n")

    mappings = [{"template": "changelog.tpl", "target": "CHANGELOG.md"}]

    created, skipped, warnings, _ = process_mappings(
        str(tpl_dir), mappings, {}, force=True, update=False,
    )

    # CHANGELOG.md must be skipped as user-owned, not overwritten
    assert changelog.read_text() == "# My Custom Changelog\n\nUser content here.\n"
    skipped_targets = [t for t, _ in skipped]
    assert "CHANGELOG.md" in skipped_targets
    created_targets = [t for t, _ in created]
    assert "CHANGELOG.md" not in created_targets


def test_force_overwrites_non_user_owned(tmp_project):
    """--force DOES overwrite non-user-owned files that already exist."""
    target = ".github/workflows/ci.yml"
    assert target not in USER_OWNED

    # Pre-existing file with old content
    _write_file(target, "old CI content\n")

    # Template with new content
    tpl_dir = tmp_project / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "ci.yml.tpl").write_text("new CI content from template\n")

    mappings = [{"template": "ci.yml.tpl", "target": target}]

    created, skipped, warnings, _ = process_mappings(
        str(tpl_dir), mappings, {}, force=True, update=False,
    )

    # File must be overwritten with template content
    with open(target, "r") as f:
        assert f.read() == "new CI content from template\n"
    created_targets = {t: s for t, s in created}
    assert target in created_targets
    assert created_targets[target] == "overwritten"


# --- Auto-commit tests ---


def test_scaffold_auto_commits_files(mock_git_repo, capsys):
    """After scaffold, created/modified files should be committed (clean tree)."""
    # Set up a template and commit it so it doesn't pollute porcelain output
    tpl_dir = mock_git_repo / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "ci.yml.tpl").write_text("name: CI\n")
    subprocess.run(
        ["git", "add", "templates"], cwd=str(mock_git_repo), check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add test templates"],
        cwd=str(mock_git_repo), check=True,
    )

    mappings = [{"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"}]
    created, skipped, warnings, new_hashes = process_mappings(
        str(tpl_dir), mappings, {}, force=False, update=False,
    )

    assert len(created) == 1
    assert created[0][1] == "created"

    # Run _finalize_scaffold which should auto-commit
    # no-tag prevents tagging side effects in test
    _finalize_scaffold(
        existing_hashes={},
        all_hash_dicts=[new_hashes],
        created=created,
        skipped=skipped,
        warnings=warnings,
        registry=None,
        flags={"no-tag": True},
        registries=[],
    )

    captured = capsys.readouterr()
    assert "Committed scaffold changes." in captured.out

    # Verify working tree is clean (all scaffold files committed)
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(mock_git_repo),
    )
    assert result.stdout.strip() == "", f"Dirty tree: {result.stdout}"


def test_scaffold_no_commit_flag_skips_commit(mock_git_repo, capsys):
    """With --no-commit, scaffold files should remain uncommitted."""
    tpl_dir = mock_git_repo / "templates"
    tpl_dir.mkdir()
    (tpl_dir / "ci.yml.tpl").write_text("name: CI\n")
    subprocess.run(
        ["git", "add", "templates"], cwd=str(mock_git_repo), check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add test templates"],
        cwd=str(mock_git_repo), check=True,
    )

    mappings = [{"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"}]
    created, skipped, warnings, new_hashes = process_mappings(
        str(tpl_dir), mappings, {}, force=False, update=False,
    )

    # Run _finalize_scaffold with --no-commit flag
    _finalize_scaffold(
        existing_hashes={},
        all_hash_dicts=[new_hashes],
        created=created,
        skipped=skipped,
        warnings=warnings,
        registry=None,
        flags={"no-commit": True, "no-tag": True},
        registries=[],
    )

    captured = capsys.readouterr()
    assert "Skipping commit (--no-commit)." in captured.out
    assert "Committed scaffold changes." not in captured.out

    # Verify files are still uncommitted
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(mock_git_repo),
    )
    assert result.stdout.strip() != "", "Tree should be dirty with --no-commit"
