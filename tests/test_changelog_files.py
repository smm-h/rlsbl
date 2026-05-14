"""Tests for rlsbl.changelog.files."""

import json
import os
import stat

import pytest

from rlsbl.changelog.files import (
    append_entry,
    changes_dir_exists,
    finalize_version,
    get_changes_dir,
    is_read_only,
    list_versioned_files,
    read_unreleased,
)
from rlsbl.changelog.schema import ChangelogEntry, parse_jsonl


class TestGetChangesDir:
    """Tests for get_changes_dir."""

    def test_returns_expected_path(self, tmp_path):
        result = get_changes_dir(str(tmp_path))
        assert result == os.path.join(str(tmp_path), ".rlsbl", "changes")


class TestChangesDirExists:
    """Tests for changes_dir_exists."""

    def test_returns_false_when_missing(self, tmp_path):
        assert changes_dir_exists(str(tmp_path)) is False

    def test_returns_true_when_present(self, tmp_path):
        (tmp_path / ".rlsbl" / "changes").mkdir(parents=True)
        assert changes_dir_exists(str(tmp_path)) is True


class TestListVersionedFiles:
    """Tests for list_versioned_files."""

    def test_empty_directory(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        assert list_versioned_files(str(changes)) == []

    def test_nonexistent_directory(self, tmp_path):
        assert list_versioned_files(str(tmp_path / "nope")) == []

    def test_sorts_by_semver_descending(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        # Create files in non-sorted order
        for name in ["0.1.0.jsonl", "1.0.0.jsonl", "0.2.0.jsonl", "0.1.1.jsonl", "2.0.0.jsonl"]:
            (changes / name).write_text("")

        result = list_versioned_files(str(changes))
        versions = [ver for ver, _ in result]
        assert versions == ["2.0.0", "1.0.0", "0.2.0", "0.1.1", "0.1.0"]

    def test_ignores_non_versioned_files(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        (changes / "1.0.0.jsonl").write_text("")
        (changes / "unreleased.jsonl").write_text("")
        (changes / "notes.txt").write_text("")
        (changes / ".validated").write_text("")

        result = list_versioned_files(str(changes))
        assert len(result) == 1
        assert result[0][0] == "1.0.0"

    def test_returns_full_paths(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        (changes / "1.2.3.jsonl").write_text("")

        result = list_versioned_files(str(changes))
        assert result[0][1] == str(changes / "1.2.3.jsonl")


class TestReadUnreleased:
    """Tests for read_unreleased."""

    def test_returns_empty_when_file_missing(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        assert read_unreleased(str(changes)) == []

    def test_reads_entries(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        path = changes / "unreleased.jsonl"
        lines = [
            json.dumps({"commits": ["a"], "user_facing": False}),
            json.dumps({"commits": ["b"], "user_facing": True, "description": "X", "type": "fix"}),
        ]
        path.write_text("\n".join(lines) + "\n")
        entries = read_unreleased(str(changes))
        assert len(entries) == 2
        assert entries[0].commits == ["a"]
        assert entries[1].type == "fix"


class TestAppendEntry:
    """Tests for append_entry."""

    def test_creates_dir_and_file(self, tmp_path):
        changes = str(tmp_path / ".rlsbl" / "changes")
        entry = ChangelogEntry(commits=["abc"], user_facing=False)
        append_entry(changes, entry)

        assert os.path.isdir(changes)
        entries = read_unreleased(changes)
        assert len(entries) == 1
        assert entries[0].commits == ["abc"]

    def test_appends_to_existing(self, tmp_path):
        changes = str(tmp_path / ".rlsbl" / "changes")
        entry1 = ChangelogEntry(commits=["abc"], user_facing=False)
        entry2 = ChangelogEntry(
            commits=["def"],
            user_facing=True,
            description="Feature",
            type="feature",
        )
        append_entry(changes, entry1)
        append_entry(changes, entry2)

        entries = read_unreleased(changes)
        assert len(entries) == 2
        assert entries[0].commits == ["abc"]
        assert entries[1].description == "Feature"

    def test_no_temp_files_left(self, tmp_path):
        changes = str(tmp_path / ".rlsbl" / "changes")
        entry = ChangelogEntry(commits=["abc"], user_facing=False)
        append_entry(changes, entry)

        files = os.listdir(changes)
        assert all(not f.endswith(".tmp") for f in files)


class TestFinalizeVersion:
    """Tests for finalize_version."""

    def test_renames_and_creates_new_unreleased(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        unreleased = changes / "unreleased.jsonl"
        unreleased.write_text(
            json.dumps({"commits": ["abc"], "user_facing": False}) + "\n"
        )

        finalize_version(str(changes), "1.0.0")

        versioned = changes / "1.0.0.jsonl"
        assert versioned.exists()
        assert not unreleased.read_text().strip()  # new empty file
        # Original content moved to versioned file
        entries = parse_jsonl(str(versioned))
        assert len(entries) == 1
        assert entries[0].commits == ["abc"]

    def test_versioned_file_is_read_only(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()
        (changes / "unreleased.jsonl").write_text(
            json.dumps({"commits": ["abc"], "user_facing": False}) + "\n"
        )

        finalize_version(str(changes), "2.0.0")

        versioned = changes / "2.0.0.jsonl"
        mode = os.stat(str(versioned)).st_mode
        assert not (mode & stat.S_IWUSR)
        assert not (mode & stat.S_IWGRP)
        assert not (mode & stat.S_IWOTH)

    def test_raises_when_no_unreleased(self, tmp_path):
        changes = tmp_path / "changes"
        changes.mkdir()

        with pytest.raises(FileNotFoundError, match="unreleased.jsonl not found"):
            finalize_version(str(changes), "1.0.0")


class TestIsReadOnly:
    """Tests for is_read_only."""

    def test_nonexistent_file(self, tmp_path):
        assert is_read_only(str(tmp_path / "nope")) is False

    def test_writable_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert is_read_only(str(f)) is False

    def test_read_only_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        os.chmod(str(f), 0o444)
        assert is_read_only(str(f)) is True
