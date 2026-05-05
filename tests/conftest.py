"""Shared pytest fixtures for the rlsbl test suite."""

import json
import os
import subprocess

import pytest


class FakeResponse:
    """Fake HTTP response for mocking urllib.request.urlopen.

    Supports context-manager protocol, .read(), and .getheader().
    ``data`` can be bytes (used as-is) or a dict (auto-JSON-encoded).
    """

    def __init__(self, data, status=200, headers=None):
        if isinstance(data, bytes):
            self._data = data
        else:
            # Assume dict/list — JSON-encode it
            self._data = json.dumps(data).encode()
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._data

    def getheader(self, name):
        # Case-insensitive header lookup
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Create a temporary directory and chdir into it.

    Returns the Path object for the temp directory.
    Automatically restores the original cwd on teardown via monkeypatch.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def mock_git_repo(tmp_project):
    """Create a minimal git repo with an initial commit in a temp directory.

    Builds on tmp_project (already chdir'd into tmp_path).
    Returns the Path object for the repo root.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_project),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.local"],
        cwd=str(tmp_project),
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_project),
        check=True,
    )
    # Create an initial commit so HEAD exists
    readme = tmp_project / "README.md"
    readme.write_text("# test\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=str(tmp_project),
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=str(tmp_project),
        check=True,
    )
    return tmp_project


@pytest.fixture
def mock_gh(monkeypatch):
    """Patch common gh/GitHub-related calls to prevent real API access.

    Patches:
    - GITHUB_TOKEN env var set to a fake value
    - urllib.request.urlopen returns FakeResponse with empty JSON object
    - subprocess.run for 'gh' commands returns a no-op CompletedProcess

    Returns a dict with references to the patches for further customization:
        {"urlopen_calls": list, "subprocess_calls": list}
    """
    monkeypatch.setenv("GITHUB_TOKEN", "fake-test-token")

    urlopen_calls = []
    subprocess_calls = []

    def fake_urlopen(req, timeout=None):
        urlopen_calls.append(req)
        return FakeResponse({})

    def fake_subprocess_run(cmd, *args, **kwargs):
        subprocess_calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    return {"urlopen_calls": urlopen_calls, "subprocess_calls": subprocess_calls}
