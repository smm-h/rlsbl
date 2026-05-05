"""Tests for rlsbl.commands.discover."""

import json

import pytest

from conftest import FakeResponse
from rlsbl.commands.discover import (
    MAX_PAGES,
    _fetch_all_repos,
    _parse_next_link,
    _relative_time,
    run_cmd,
)


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

        def fake_urlopen(req, timeout=None):
            return FakeResponse(
                {"total_count": 0, "items": []},
                headers={},
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        run_cmd(None, [], {})
        captured = capsys.readouterr()
        assert "No rlsbl-tagged repositories found" in captured.out


class TestFetchAllReposPageCap:
    """Tests for pagination page-count cap in _fetch_all_repos."""

    def test_stops_at_max_pages(self, monkeypatch):
        """Verify pagination stops after MAX_PAGES even if more pages are available."""
        call_count = 0

        def fake_make_request(url, token):
            nonlocal call_count
            call_count += 1
            # Return 1 item per page with a next link, simulating infinite pages
            data = {
                "total_count": 9999,
                "items": [{"full_name": f"user/repo-{call_count}"}],
            }
            headers = {
                "Link": '<https://api.github.com/search/repositories?q=topic:rlsbl&page=next>; rel="next"'
            }
            return data, headers

        monkeypatch.setattr(
            "rlsbl.commands.discover._make_request", fake_make_request
        )

        repos = _fetch_all_repos("fake-token")

        # Should have stopped at MAX_PAGES, not continued indefinitely
        assert call_count == MAX_PAGES
        assert len(repos) == MAX_PAGES
