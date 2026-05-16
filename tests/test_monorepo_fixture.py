"""Smoke tests for the monorepo_fixture conftest helper."""

import subprocess

import tomlkit


def test_workspace_toml_exists_with_two_projects(monorepo_fixture):
    ws_file = monorepo_fixture.root / ".rlsbl-monorepo" / "workspace.toml"
    assert ws_file.exists()
    data = tomlkit.loads(ws_file.read_text())
    assert len(data["projects"]) == 2


def test_both_tags_exist(monorepo_fixture):
    result = subprocess.run(
        ["git", "tag", "-l"],
        cwd=str(monorepo_fixture.root),
        capture_output=True,
        text=True,
        check=True,
    )
    tags = result.stdout.strip().splitlines()
    assert "mypylib@v0.1.0" in tags
    assert "mygolib@v0.1.0" in tags


def test_unreleased_jsonl_files_exist(monorepo_fixture):
    assert (monorepo_fixture.python_dir / ".rlsbl" / "changes" / "unreleased.jsonl").exists()
    assert (monorepo_fixture.go_dir / ".rlsbl" / "changes" / "unreleased.jsonl").exists()
