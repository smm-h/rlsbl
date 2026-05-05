"""Tests for the codehome plugin release target."""

import os
import tempfile

from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets.codehome import CodehomeTarget
from rlsbl.targets import TARGETS


SAMPLE_PLUGIN_TOML = """\
[plugin]
name = "git-hooks"
version = "0.1.0"
description = "Git hook management"
"""

SAMPLE_PYPROJECT_TOML = """\
[project]
name = "codehome-plugin-git-hooks"
version = "0.1.0"
description = "Guard package for git-hooks plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""


class TestCodehomeTargetProtocol:
    def test_is_release_target(self):
        target = CodehomeTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = CodehomeTarget()
        assert target.name == "codehome"

    def test_scope(self):
        target = CodehomeTarget()
        assert target.scope == "subdir"

    def test_version_file(self):
        target = CodehomeTarget()
        assert target.version_file() == "plugin.toml"


class TestCodehomeDetect:
    def test_detect_true(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.toml"), "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)
            assert target.detect(d) is True

    def test_detect_false(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False


class TestCodehomeReadVersion:
    def test_read_version(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.toml"), "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)
            assert target.read_version(d) == "0.1.0"

    def test_read_version_missing_field(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.toml"), "w") as f:
                f.write("[plugin]\nname = \"test\"\n")
            try:
                target.read_version(d)
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "[plugin].version" in str(e)


class TestCodehomeWriteVersion:
    def test_write_version_plugin_toml(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.toml")
            with open(plugin_path, "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)

            target.write_version(d, "1.2.3")

            with open(plugin_path, "r") as f:
                content = f.read()
            assert 'version = "1.2.3"' in content
            # Name should be unchanged
            assert 'name = "git-hooks"' in content

    def test_write_version_updates_pyproject_toml(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.toml")
            pyproject_path = os.path.join(d, "pyproject.toml")

            with open(plugin_path, "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)
            with open(pyproject_path, "w") as f:
                f.write(SAMPLE_PYPROJECT_TOML)

            target.write_version(d, "2.0.0")

            # Both files should be updated
            with open(plugin_path, "r") as f:
                plugin_content = f.read()
            assert 'version = "2.0.0"' in plugin_content

            with open(pyproject_path, "r") as f:
                pyproject_content = f.read()
            assert 'version = "2.0.0"' in pyproject_content

    def test_write_version_no_pyproject_toml(self):
        """write_version works fine when pyproject.toml does not exist."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.toml")
            with open(plugin_path, "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)

            # Should not raise even without pyproject.toml
            target.write_version(d, "3.0.0")

            with open(plugin_path, "r") as f:
                content = f.read()
            assert 'version = "3.0.0"' in content

    def test_write_version_preserves_other_content(self):
        """write_version preserves all other fields and formatting."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.toml")
            with open(plugin_path, "w") as f:
                f.write(SAMPLE_PLUGIN_TOML)

            target.write_version(d, "4.5.6")

            with open(plugin_path, "r") as f:
                content = f.read()
            assert 'description = "Git hook management"' in content


class TestCodehomeTagFormat:
    def test_tag_format_with_name(self):
        target = CodehomeTarget()
        assert target.tag_format("git-hooks", "1.2.3") == "git-hooks@v1.2.3"

    def test_tag_format_without_name(self):
        target = CodehomeTarget()
        assert target.tag_format(None, "1.2.3") == "v1.2.3"

    def test_tag_format_empty_string_name(self):
        """Empty string name should fall back to plain v-tag."""
        target = CodehomeTarget()
        assert target.tag_format("", "1.2.3") == "v1.2.3"


class TestCodehomeRegistry:
    def test_registered_in_targets(self):
        assert "codehome" in TARGETS

    def test_registered_instance_type(self):
        assert isinstance(TARGETS["codehome"], CodehomeTarget)

    def test_get_project_init_hint(self):
        target = CodehomeTarget()
        hint = target.get_project_init_hint()
        assert "plugin.toml" in hint
