"""Tests for DocsTarget: protocol conformance and detect() behavior."""

import os
import tempfile

from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets.docs import DocsTarget
from rlsbl.targets import TARGETS


class TestDocsTargetProtocol:
    """Verify DocsTarget satisfies the ReleaseTarget protocol."""

    def test_is_release_target(self):
        target = DocsTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = DocsTarget()
        assert target.name == "docs"

    def test_scope(self):
        target = DocsTarget()
        assert target.scope == "root"

    def test_version_file_none(self):
        target = DocsTarget()
        assert target.version_file() is None

    def test_tag_format_none(self):
        target = DocsTarget()
        assert target.tag_format(None, "1.0.0") is None

    def test_read_version_fallback(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.read_version(d) == "0.0.0"

    def test_write_version_noop(self):
        """write_version should complete without error."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            target.write_version(d, "1.0.0")  # Should not raise

    def test_registered_in_targets(self):
        assert "docs" in TARGETS
        assert isinstance(TARGETS["docs"], DocsTarget)


class TestDocsTargetDetect:
    """Verify detect() looks for selfdoc.json."""

    def test_detect_true_with_selfdoc_json(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "selfdoc.json"), "w") as f:
                f.write("{}")
            assert target.detect(d) is True

    def test_detect_false_empty_dir(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_detect_false_with_old_docs_toml(self):
        """Old .rlsbl/docs.toml should NOT trigger detection anymore."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write("[source]\n")
            assert target.detect(d) is False
