"""Tests for rlsbl.tagging."""

import json

import pytest

from conftest import FakeResponse
from rlsbl.tagging import ensure_github_topic, ensure_npm_keyword, ensure_pypi_keyword


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

        def fake_urlopen(req, timeout=None):
            # GET returns topics that already include rlsbl
            return FakeResponse({"names": ["rlsbl", "other"]})

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = ensure_github_topic(quiet=True)
        assert result is False


def _raise_file_not_found(cmd, args):
    raise FileNotFoundError("gh not found")
