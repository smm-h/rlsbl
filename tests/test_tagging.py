"""Tests for rlsbl.config, rlsbl.tagging, and rlsbl.commands.discover."""

import json
import os

import pytest

from rlsbl.config import read_json_config, should_tag, write_project_config
from rlsbl.tagging import ensure_github_topic, ensure_npm_keyword, ensure_pypi_keyword
from rlsbl.commands.discover import _parse_next_link, _relative_time, run_cmd


# ---------------------------------------------------------------------------
# Tests for config.py
# ---------------------------------------------------------------------------


class TestShouldTag:
    """Tests for should_tag precedence logic."""

    def test_returns_true_with_empty_flags_and_no_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No config files exist, empty flags -> default True
        monkeypatch.setattr("rlsbl.config.USER_CONFIG", str(tmp_path / "nope.json"))
        assert should_tag({}) is True

    def test_returns_false_when_no_tag_flag_set(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert should_tag({"no-tag": True}) is False

    def test_reads_project_config_tag_false(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("rlsbl.config.USER_CONFIG", str(tmp_path / "nope.json"))
        # Create project config with tag: false
        config_dir = tmp_path / ".rlsbl"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"tag": False}))
        monkeypatch.setattr("rlsbl.config.PROJECT_CONFIG", str(config_dir / "config.json"))
        assert should_tag({}) is False

    def test_reads_user_config_as_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No project config
        monkeypatch.setattr("rlsbl.config.PROJECT_CONFIG", str(tmp_path / "no_project.json"))
        # User config says tag: false
        user_config = tmp_path / "user_config.json"
        user_config.write_text(json.dumps({"tag": False}))
        monkeypatch.setattr("rlsbl.config.USER_CONFIG", str(user_config))
        assert should_tag({}) is False

    def test_project_config_overrides_user_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Project config says tag: true
        config_dir = tmp_path / ".rlsbl"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"tag": True}))
        monkeypatch.setattr("rlsbl.config.PROJECT_CONFIG", str(config_dir / "config.json"))
        # User config says tag: false
        user_config = tmp_path / "user_config.json"
        user_config.write_text(json.dumps({"tag": False}))
        monkeypatch.setattr("rlsbl.config.USER_CONFIG", str(user_config))
        assert should_tag({}) is True


class TestReadJsonConfig:
    """Tests for read_json_config edge cases."""

    def test_returns_empty_dict_on_missing_file(self, tmp_path):
        assert read_json_config(str(tmp_path / "missing.json")) == {}

    def test_returns_empty_dict_on_malformed_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json!!")
        assert read_json_config(str(bad_file)) == {}


class TestWriteProjectConfig:
    """Tests for write_project_config."""

    def test_creates_dir_and_file_and_preserves_existing_keys(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_path = str(tmp_path / ".rlsbl" / "config.json")
        monkeypatch.setattr("rlsbl.config.PROJECT_CONFIG", config_path)

        # First write
        write_project_config("tag", False)
        data = json.loads(open(config_path).read())
        assert data == {"tag": False}

        # Second write should preserve "tag" key
        write_project_config("other_key", "hello")
        data = json.loads(open(config_path).read())
        assert data == {"tag": False, "other_key": "hello"}


# ---------------------------------------------------------------------------
# Tests for tagging.py
# ---------------------------------------------------------------------------


class TestEnsureNpmKeyword:
    """Tests for ensure_npm_keyword."""

    def test_adds_keyword_to_existing_keywords_array(self, tmp_path):
        pkg = {"name": "my-pkg", "version": "1.0.0", "keywords": ["cli"]}
        (tmp_path / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
        result = ensure_npm_keyword(str(tmp_path), quiet=True)
        assert result is True
        data = json.loads((tmp_path / "package.json").read_text())
        assert "rlsbl" in data["keywords"]
        assert "cli" in data["keywords"]

    def test_creates_keywords_array_if_missing(self, tmp_path):
        pkg = {"name": "my-pkg", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
        result = ensure_npm_keyword(str(tmp_path), quiet=True)
        assert result is True
        data = json.loads((tmp_path / "package.json").read_text())
        assert data["keywords"] == ["rlsbl"]

    def test_returns_false_if_already_present(self, tmp_path):
        pkg = {"name": "my-pkg", "version": "1.0.0", "keywords": ["rlsbl"]}
        (tmp_path / "package.json").write_text(json.dumps(pkg, indent=2) + "\n")
        result = ensure_npm_keyword(str(tmp_path), quiet=True)
        assert result is False

    def test_preserves_indent_and_trailing_newline(self, tmp_path):
        pkg = {"name": "my-pkg", "version": "1.0.0"}
        # Use 4-space indent and trailing newline
        (tmp_path / "package.json").write_text(json.dumps(pkg, indent=4) + "\n")
        ensure_npm_keyword(str(tmp_path), quiet=True)
        raw = (tmp_path / "package.json").read_text()
        assert raw.endswith("\n")
        # The indent should still be 4 spaces (look for 4-space-indented key)
        assert '    "name"' in raw


class TestEnsurePypiKeyword:
    """Tests for ensure_pypi_keyword."""

    def test_adds_to_single_line_keywords_array(self, tmp_path):
        content = '[project]\nname = "my-pkg"\nversion = "1.0.0"\nkeywords = ["cli"]\n'
        (tmp_path / "pyproject.toml").write_text(content)
        result = ensure_pypi_keyword(str(tmp_path), quiet=True)
        assert result is True
        updated = (tmp_path / "pyproject.toml").read_text()
        assert '"rlsbl"' in updated
        assert '"cli"' in updated

    def test_adds_to_multi_line_keywords_array(self, tmp_path):
        content = (
            '[project]\n'
            'name = "my-pkg"\n'
            'version = "1.0.0"\n'
            'keywords = [\n'
            '    "cli",\n'
            '    "tool"\n'
            ']\n'
        )
        (tmp_path / "pyproject.toml").write_text(content)
        result = ensure_pypi_keyword(str(tmp_path), quiet=True)
        assert result is True
        updated = (tmp_path / "pyproject.toml").read_text()
        assert '"rlsbl"' in updated
        assert '"cli"' in updated
        assert '"tool"' in updated

    def test_inserts_keywords_field_when_missing(self, tmp_path):
        content = '[project]\nname = "my-pkg"\nversion = "1.0.0"\n'
        (tmp_path / "pyproject.toml").write_text(content)
        result = ensure_pypi_keyword(str(tmp_path), quiet=True)
        assert result is True
        updated = (tmp_path / "pyproject.toml").read_text()
        assert 'keywords = ["rlsbl"]' in updated
        # Should be after the version line
        lines = updated.splitlines()
        version_idx = next(i for i, l in enumerate(lines) if l.startswith("version"))
        keywords_idx = next(i for i, l in enumerate(lines) if "keywords" in l)
        assert keywords_idx > version_idx

    def test_returns_false_if_already_present(self, tmp_path):
        content = '[project]\nname = "my-pkg"\nversion = "1.0.0"\nkeywords = ["rlsbl"]\n'
        (tmp_path / "pyproject.toml").write_text(content)
        result = ensure_pypi_keyword(str(tmp_path), quiet=True)
        assert result is False


class TestEnsureGithubTopic:
    """Tests for ensure_github_topic."""

    def test_returns_false_when_no_token_available(self, monkeypatch):
        # No GITHUB_TOKEN env var
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        # Mock run() to raise FileNotFoundError (gh not installed)
        monkeypatch.setattr("rlsbl.tagging.run", _raise_file_not_found)
        result = ensure_github_topic(quiet=True)
        assert result is False

    def test_adds_topic_via_api(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        # Mock run() for repo detection
        monkeypatch.setattr("rlsbl.tagging.run", lambda cmd, args: "owner/repo")

        # Track urlopen calls
        calls = []

        class FakeResponse:
            def __init__(self, data):
                self._data = json.dumps(data).encode()

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=None):
            calls.append(req)
            if req.get_method() == "GET":
                return FakeResponse({"names": ["existing-topic"]})
            else:
                # PUT request
                return FakeResponse({"names": ["existing-topic", "rlsbl"]})

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = ensure_github_topic(quiet=True)
        assert result is True
        # Should have made a GET then a PUT
        assert len(calls) == 2
        assert calls[0].get_method() == "GET"
        assert calls[1].get_method() == "PUT"
        # Verify PUT payload contains rlsbl
        payload = json.loads(calls[1].data.decode())
        assert "rlsbl" in payload["names"]

    def test_returns_false_if_topic_already_present(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.setattr("rlsbl.tagging.run", lambda cmd, args: "owner/repo")

        class FakeResponse:
            def __init__(self, data):
                self._data = json.dumps(data).encode()

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=None):
            # GET returns topics that already include rlsbl
            return FakeResponse({"names": ["rlsbl", "other"]})

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = ensure_github_topic(quiet=True)
        assert result is False


def _raise_file_not_found(cmd, args):
    raise FileNotFoundError("gh not found")


# ---------------------------------------------------------------------------
# Tests for commands/discover.py
# ---------------------------------------------------------------------------


class TestRelativeTime:
    """Tests for _relative_time."""

    def test_returns_empty_string_for_empty_input(self):
        assert _relative_time("") == ""

    def test_returns_days_ago_for_recent_timestamps(self):
        from datetime import datetime, timezone, timedelta

        # 3 days ago
        ts = datetime.now(timezone.utc) - timedelta(days=3)
        iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _relative_time(iso)
        assert result == "3d ago"


class TestParseNextLink:
    """Tests for _parse_next_link."""

    def test_extracts_next_url_from_link_header(self):
        headers = {
            "Link": '<https://api.github.com/search/repositories?q=topic:rlsbl&page=2>; rel="next", '
                    '<https://api.github.com/search/repositories?q=topic:rlsbl&page=5>; rel="last"'
        }
        result = _parse_next_link(headers)
        assert result == "https://api.github.com/search/repositories?q=topic:rlsbl&page=2"

    def test_returns_none_when_no_next_link(self):
        # Only a "last" link, no "next"
        headers = {
            "Link": '<https://api.github.com/search/repositories?q=topic:rlsbl&page=5>; rel="last"'
        }
        assert _parse_next_link(headers) is None

    def test_returns_none_when_no_link_header(self):
        assert _parse_next_link({}) is None


class TestRunCmd:
    """Tests for the discover run_cmd function."""

    def test_prints_no_repos_found_when_api_returns_empty(self, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        # Mock _get_github_token to return a fake token
        monkeypatch.setattr(
            "rlsbl.commands.discover._get_github_token", lambda: "fake-token"
        )

        class FakeResponse:
            def __init__(self):
                self._data = json.dumps({"total_count": 0, "items": []}).encode()
                self.headers = {}

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=None):
            return FakeResponse()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        run_cmd(None, [], {})
        captured = capsys.readouterr()
        assert "No rlsbl-tagged repositories found" in captured.out
