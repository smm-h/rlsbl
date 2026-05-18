"""Tests for rlsbl.utils.require_tool()."""

import pytest

from rlsbl.utils import require_tool


def test_missing_tool_fatal_false_returns_none():
    assert require_tool("definitely-not-a-real-tool-xyz", fatal=False) is None


def test_missing_tool_fatal_true_raises():
    with pytest.raises(FileNotFoundError) as exc_info:
        require_tool("definitely-not-a-real-tool-xyz", fatal=True)
    msg = str(exc_info.value)
    assert "definitely-not-a-real-tool-xyz" in msg
    assert "not found on PATH" in msg


def test_missing_tool_fatal_default_is_true():
    """fatal defaults to True."""
    with pytest.raises(FileNotFoundError):
        require_tool("definitely-not-a-real-tool-xyz")


def test_present_tool_returns_path():
    """python should always be present in the test environment."""
    path = require_tool("python", fatal=False)
    # Either python or python3 must be present somewhere; if neither, the test
    # environment is unusual.
    if path is None:
        path = require_tool("python3", fatal=False)
    assert path is not None
    assert isinstance(path, str)


def test_purpose_included_in_error_message():
    with pytest.raises(FileNotFoundError) as exc_info:
        require_tool("definitely-not-a-real-tool-xyz",
                     purpose="for the widget pipeline", fatal=True)
    msg = str(exc_info.value)
    assert "for the widget pipeline" in msg


def test_purpose_omitted_from_error_when_not_given():
    with pytest.raises(FileNotFoundError) as exc_info:
        require_tool("definitely-not-a-real-tool-xyz", fatal=True)
    msg = str(exc_info.value)
    assert "(needed " not in msg


def test_purpose_ignored_when_not_fatal():
    """Purpose only appears in the error -- non-fatal returns None regardless."""
    assert require_tool("definitely-not-a-real-tool-xyz",
                         purpose="never gonna matter", fatal=False) is None
