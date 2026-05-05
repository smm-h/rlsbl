"""Tests for rlsbl.commands.unreleased."""

import json
import subprocess

import pytest

from rlsbl.commands.unreleased import (
    _extract_keywords,
    _get_commits_since,
    _get_last_tag,
    _get_unreleased_changelog_text,
    _is_covered,
    run_cmd,
)


class TestGetLastTag:
    """Tests for _get_last_tag."""

    def test_returns_tag_when_exists(self, mock_git_repo):
        subprocess.run(
            ["git", "tag", "v1.0.0"],
            cwd=str(mock_git_repo), check=True,
        )
        assert _get_last_tag() == "v1.0.0"

    def test_returns_none_when_no_tags(self, mock_git_repo):
        assert _get_last_tag() is None

    def test_returns_latest_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        # Make a new commit and tag it
        (mock_git_repo / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "file.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "second"],
            cwd=str(mock_git_repo), check=True,
        )
        subprocess.run(["git", "tag", "v1.1.0"], cwd=str(mock_git_repo), check=True)
        assert _get_last_tag() == "v1.1.0"


class TestGetCommitsSince:
    """Tests for _get_commits_since."""

    def test_returns_commits_since_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        # Add a commit after the tag
        (mock_git_repo / "new.txt").write_text("new")
        subprocess.run(["git", "add", "new.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: add new feature"],
            cwd=str(mock_git_repo), check=True,
        )
        commits = _get_commits_since("v1.0.0")
        assert len(commits) == 1
        assert commits[0]["subject"] == "feat: add new feature"
        assert len(commits[0]["hash"]) == 40
        assert commits[0]["author"] == "Test"
        assert commits[0]["date"]  # non-empty ISO date

    def test_returns_empty_when_no_commits_since_tag(self, mock_git_repo):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        commits = _get_commits_since("v1.0.0")
        assert commits == []

    def test_returns_all_commits_when_tag_is_none(self, mock_git_repo):
        # When tag is None, should get HEAD (just one commit in our fixture)
        commits = _get_commits_since(None)
        assert len(commits) == 1
        assert commits[0]["subject"] == "initial"


class TestGetUnreleasedChangelogText:
    """Tests for _get_unreleased_changelog_text."""

    def test_extracts_unreleased_section(self, tmp_project):
        changelog = tmp_project / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n"
            "## Unreleased\n\n"
            "- Added new widget\n"
            "- Fixed bug in parser\n\n"
            "## 1.0.0\n\n"
            "- Initial release\n"
        )
        text = _get_unreleased_changelog_text(str(changelog))
        assert "Added new widget" in text
        assert "Fixed bug in parser" in text
        assert "Initial release" not in text

    def test_falls_back_to_first_section(self, tmp_project):
        changelog = tmp_project / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n"
            "## 1.1.0\n\n"
            "- New feature added\n\n"
            "## 1.0.0\n\n"
            "- Initial release\n"
        )
        text = _get_unreleased_changelog_text(str(changelog))
        assert "New feature added" in text
        assert "Initial release" not in text

    def test_returns_empty_when_no_changelog(self, tmp_project):
        text = _get_unreleased_changelog_text(str(tmp_project / "CHANGELOG.md"))
        assert text == ""

    def test_returns_empty_for_empty_changelog(self, tmp_project):
        changelog = tmp_project / "CHANGELOG.md"
        changelog.write_text("")
        text = _get_unreleased_changelog_text(str(changelog))
        assert text == ""


class TestExtractKeywords:
    """Tests for _extract_keywords."""

    def test_strips_conventional_commit_prefix(self):
        keywords = _extract_keywords("fix: resolve parsing bug")
        assert "fix" not in keywords
        assert "resolve" in keywords
        assert "parsing" in keywords
        assert "bug" in keywords

    def test_strips_scoped_prefix(self):
        keywords = _extract_keywords("feat(cli): add new flag")
        assert "feat" not in keywords
        assert "cli" not in keywords
        assert "add" in keywords
        assert "new" in keywords
        assert "flag" in keywords

    def test_filters_short_words(self):
        keywords = _extract_keywords("do it now")
        # "do" and "it" and "now" are all 2-3 chars; "now" is 3 so included
        assert "do" not in keywords
        assert "it" not in keywords
        assert "now" in keywords

    def test_filters_noise_words(self):
        keywords = _extract_keywords("update the parser for this project")
        assert "the" not in keywords
        assert "for" not in keywords
        assert "this" not in keywords
        assert "update" in keywords
        assert "parser" in keywords


class TestIsCovered:
    """Tests for _is_covered."""

    def test_direct_substring_match(self):
        assert _is_covered(
            "fix: resolve parsing bug",
            "- Resolved parsing bug in the scanner",
        )

    def test_keyword_match(self):
        assert _is_covered(
            "feat: add widget support",
            "- Added widget support for dashboard",
        )

    def test_not_covered_when_no_match(self):
        assert not _is_covered(
            "fix: resolve parsing bug",
            "- Added a new feature\n- Improved performance",
        )

    def test_not_covered_when_changelog_empty(self):
        assert not _is_covered("fix: something", "")


class TestRunCmd:
    """Tests for the unreleased run_cmd function."""

    def test_no_unreleased_commits(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No unreleased commits." in captured.out

    def test_shows_unreleased_commits(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        # Add commits
        (mock_git_repo / "a.txt").write_text("a")
        subprocess.run(["git", "add", "a.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: add widget"],
            cwd=str(mock_git_repo), check=True,
        )
        # Create a changelog that covers the commit
        (mock_git_repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## Unreleased\n\n- Add widget support\n\n## 1.0.0\n\n- Init\n"
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Unreleased commits since v1.0.0" in captured.out
        assert "[COVERED]" in captured.out

    def test_shows_missing_coverage(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        (mock_git_repo / "a.txt").write_text("a")
        subprocess.run(["git", "add", "a.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: something completely unrelated xyz"],
            cwd=str(mock_git_repo), check=True,
        )
        # Changelog with no matching content
        (mock_git_repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## Unreleased\n\n- Fixed a typo\n\n## 1.0.0\n\n- Init\n"
        )
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[MISSING]" in captured.out
        assert "Coverage: 0/1" in captured.out

    def test_handles_no_tags_gracefully(self, mock_git_repo, capsys):
        # No tags at all -- should still show commits
        (mock_git_repo / "CHANGELOG.md").write_text("# Changelog\n")
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "(no tags)" in captured.out
        assert "initial" in captured.out

    def test_json_output(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        (mock_git_repo / "b.txt").write_text("b")
        subprocess.run(["git", "add", "b.txt"], cwd=str(mock_git_repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fix: patch thing"],
            cwd=str(mock_git_repo), check=True,
        )
        (mock_git_repo / "CHANGELOG.md").write_text("# Changelog\n\n## 1.1.0\n\n- Patch thing\n")
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {"json": True})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["tag"] == "v1.0.0"
        assert len(data["commits"]) == 1
        assert data["commits"][0]["subject"] == "fix: patch thing"
        assert "covered" in data["commits"][0]
        assert data["coverage"]["total"] == 1
        assert "covered" in data["coverage"]

    def test_json_output_no_commits(self, mock_git_repo, capsys):
        subprocess.run(["git", "tag", "v1.0.0"], cwd=str(mock_git_repo), check=True)
        with pytest.raises(SystemExit) as exc_info:
            run_cmd(None, [], {"json": True})
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["tag"] == "v1.0.0"
        assert data["commits"] == []
        assert data["coverage"] == {"covered": 0, "total": 0}
