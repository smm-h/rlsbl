"""Tests for class-based release targets conforming to the ReleaseTarget Protocol."""

import json
import os
import tempfile

from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets.npm import NpmTarget
from rlsbl.targets.pypi import PypiTarget
from rlsbl.targets.go import GoTarget
from rlsbl.targets import TARGETS, detect_targets


class TestNpmTarget:
    def test_is_release_target(self):
        target = NpmTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = NpmTarget()
        assert target.name == "npm"

    def test_scope(self):
        target = NpmTarget()
        assert target.scope == "root"

    def test_version_file(self):
        target = NpmTarget()
        assert target.version_file() == "package.json"

    def test_detect_true(self):
        target = NpmTarget()
        with tempfile.TemporaryDirectory() as d:
            pkg_path = os.path.join(d, "package.json")
            with open(pkg_path, "w") as f:
                json.dump({"name": "test", "version": "1.0.0"}, f)
            assert target.detect(d) is True

    def test_detect_false(self):
        target = NpmTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_tag_format(self):
        target = NpmTarget()
        assert target.tag_format(None, "1.2.3") == "v1.2.3"


class TestPypiTarget:
    def test_is_release_target(self):
        target = PypiTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = PypiTarget()
        assert target.name == "pypi"

    def test_scope(self):
        target = PypiTarget()
        assert target.scope == "root"

    def test_version_file(self):
        target = PypiTarget()
        assert target.version_file() == "pyproject.toml"

    def test_detect_true(self):
        target = PypiTarget()
        with tempfile.TemporaryDirectory() as d:
            toml_path = os.path.join(d, "pyproject.toml")
            with open(toml_path, "w") as f:
                f.write('[project]\nname = "test"\nversion = "1.0.0"\n')
            assert target.detect(d) is True

    def test_detect_false(self):
        target = PypiTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_tag_format(self):
        target = PypiTarget()
        assert target.tag_format(None, "2.0.0") == "v2.0.0"


class TestGoTarget:
    def test_is_release_target(self):
        target = GoTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = GoTarget()
        assert target.name == "go"

    def test_scope(self):
        target = GoTarget()
        assert target.scope == "root"

    def test_version_file(self):
        target = GoTarget()
        assert target.version_file() == "VERSION"

    def test_detect_true(self):
        target = GoTarget()
        with tempfile.TemporaryDirectory() as d:
            mod_path = os.path.join(d, "go.mod")
            with open(mod_path, "w") as f:
                f.write("module github.com/user/repo\n\ngo 1.21\n")
            assert target.detect(d) is True

    def test_detect_false(self):
        target = GoTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_tag_format(self):
        target = GoTarget()
        assert target.tag_format(None, "0.5.0") == "v0.5.0"


class TestDetectTargets:
    """Integration tests for detect_targets() discovery function."""

    def test_detect_targets_with_package_json(self):
        """detect_targets('.') in a dir with package.json returns 'npm' in results."""
        with tempfile.TemporaryDirectory() as d:
            pkg_path = os.path.join(d, "package.json")
            with open(pkg_path, "w") as f:
                json.dump({"name": "test-pkg", "version": "1.0.0"}, f)
            result = detect_targets(d)
            assert "npm" in result

    def test_detect_targets_empty_directory(self):
        """detect_targets('.') in an empty dir returns []."""
        with tempfile.TemporaryDirectory() as d:
            result = detect_targets(d)
            assert result == []


class TestTargetRegistryIntegration:
    """Tests for the TARGETS registry dict and tag_format behavior."""

    def test_tag_format_none_name(self):
        """TARGETS['npm'].tag_format(None, '1.2.3') returns 'v1.2.3'."""
        assert TARGETS["npm"].tag_format(None, "1.2.3") == "v1.2.3"

    def test_tag_format_with_name_ignored(self):
        """Root scope targets ignore the name argument in tag_format."""
        assert TARGETS["npm"].tag_format("something", "1.2.3") == "v1.2.3"

    def test_build_noop(self):
        """TARGETS['npm'].build() is a no-op that doesn't raise."""
        with tempfile.TemporaryDirectory() as d:
            # Should complete without raising
            TARGETS["npm"].build(d, "1.0.0")

    def test_publish_noop(self):
        """TARGETS['npm'].publish() is a no-op that doesn't raise."""
        with tempfile.TemporaryDirectory() as d:
            # Should complete without raising
            TARGETS["npm"].publish(d, "1.0.0")


class TestBackwardCompat:
    """Tests for backward compatibility with the old registries module."""

    def test_registries_import_and_read_version(self):
        """from rlsbl.registries import REGISTRIES; REGISTRIES['npm'].read_version is callable."""
        from rlsbl.registries import REGISTRIES
        assert callable(REGISTRIES["npm"].read_version)

    def test_targets_read_version_same_object(self):
        """TARGETS['npm'].read_version is callable and same object as REGISTRIES."""
        from rlsbl.registries import REGISTRIES
        assert callable(TARGETS["npm"].read_version)
        # They are the same dict, so same instance
        assert TARGETS["npm"] is REGISTRIES["npm"]
