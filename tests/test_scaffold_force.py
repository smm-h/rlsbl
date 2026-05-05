"""Tests that --force respects USER_OWNED files."""

import os

from rlsbl.commands.init_cmd import USER_OWNED, process_mappings


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
