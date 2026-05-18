"""Tests for the centralized GitHub Actions version table.

Covers the loader (rlsbl.action_versions) and a consistency check that
every ``uses: <action>@<version>`` line in shipped templates matches the
version pinned in ``rlsbl/data/action_versions.toml``. Without this check,
templates and the central table can silently drift apart.
"""

from __future__ import annotations

import os
import re

import pytest

from rlsbl.action_versions import (
    UnknownActionError,
    format_action,
    get_action_version,
    get_all_versions,
)


TEMPLATES_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "rlsbl", "templates"
)

# Matches a workflow ``uses:`` line. Captures the action name (everything
# before the ``@``) and the version (everything after, until end of line or
# whitespace/comment). Tolerates indentation and an optional list dash.
_USES_RE = re.compile(
    r"^\s*-?\s*uses:\s*([A-Za-z0-9_./-]+)@([A-Za-z0-9_./.-]+)\s*(?:#.*)?$"
)

# Local actions (e.g., ``./.github/workflows/foo.yml``) and templating
# placeholders are skipped. Only third-party ``owner/name`` refs participate.
def _is_third_party(action: str) -> bool:
    return "/" in action and not action.startswith(".")


class TestLoader:
    """Smoke tests for the TOML loader."""

    def test_table_loads(self):
        table = get_all_versions()
        assert isinstance(table, dict)
        assert len(table) > 0

    def test_get_known_action(self):
        assert get_action_version("actions/checkout") == "v6"

    def test_format_known_action(self):
        assert format_action("actions/checkout") == "actions/checkout@v6"

    def test_setup_node_pinned_to_v6(self):
        # Regression: npm_wrapper.py used to hard-code v4 here.
        assert get_action_version("actions/setup-node") == "v6"

    def test_paths_filter_pinned_to_v4(self):
        # Regression: monorepo router used to hard-code v3 here.
        assert get_action_version("dorny/paths-filter") == "v4"

    def test_unknown_action_raises(self):
        with pytest.raises(UnknownActionError) as exc:
            get_action_version("nonexistent/action")
        # The error message must mention both the missing action and the
        # data file so the operator knows where to add the entry.
        assert "nonexistent/action" in str(exc.value)
        assert "action_versions.toml" in str(exc.value)

    def test_unknown_action_is_keyerror(self):
        # UnknownActionError must remain a KeyError subclass so existing
        # ``except KeyError`` callers keep working.
        with pytest.raises(KeyError):
            get_action_version("nonexistent/action")

    def test_get_all_versions_is_copy(self):
        # Mutating the returned dict must not corrupt the cached table.
        snap = get_all_versions()
        snap["foo/bar"] = "vX"
        assert "foo/bar" not in get_all_versions()


class TestTemplateConsistency:
    """Every ``uses:`` reference in shipped templates must match the table.

    This catches drift between templates and the central version table --
    the original bug class that motivated Phase 2.
    """

    def _iter_template_files(self):
        for root, _dirs, files in os.walk(TEMPLATES_ROOT):
            for name in files:
                if name.endswith(".tpl"):
                    yield os.path.join(root, name)

    def _iter_uses(self):
        for path in self._iter_template_files():
            with open(path) as f:
                for lineno, line in enumerate(f, start=1):
                    m = _USES_RE.match(line)
                    if not m:
                        continue
                    action, version = m.group(1), m.group(2)
                    if not _is_third_party(action):
                        continue
                    yield path, lineno, action, version

    def test_templates_match_table(self):
        table = get_all_versions()
        mismatches: list[str] = []
        unpinned: list[str] = []
        for path, lineno, action, version in self._iter_uses():
            if action not in table:
                unpinned.append(f"{path}:{lineno}: {action}@{version}")
                continue
            expected = table[action]
            if version != expected:
                mismatches.append(
                    f"{path}:{lineno}: {action}@{version} "
                    f"(expected {expected})"
                )
        msg_parts = []
        if unpinned:
            msg_parts.append(
                "Actions used in templates but missing from "
                "action_versions.toml:\n  " + "\n  ".join(unpinned)
            )
        if mismatches:
            msg_parts.append(
                "Actions whose template version disagrees with the table:\n  "
                + "\n  ".join(mismatches)
            )
        assert not msg_parts, "\n\n".join(msg_parts)

    def test_at_least_one_uses_found(self):
        # Guard: if the regex breaks, the consistency test would pass
        # vacuously. This ensures the iterator actually finds references.
        found = list(self._iter_uses())
        assert len(found) > 10, "expected to find many uses: lines in templates"
