"""Tests for the codehome plugin repository target (root-scoped, plugin.json)."""

import json
import os
import tempfile

import pytest

from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets.codehome import CodehomeTarget, PluginValidationError, validate_plugin_json
from rlsbl.targets import TARGETS


SAMPLE_PLUGIN_JSON = {
    "name": "git-hooks",
    "version": "0.1.0",
    "description": "Git hook management for codehome",
}


class TestCodehomeTargetProtocol:
    def test_is_release_target(self):
        target = CodehomeTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = CodehomeTarget()
        assert target.name == "codehome"

    def test_scope_is_root(self):
        target = CodehomeTarget()
        assert target.scope == "root"

    def test_version_file(self):
        target = CodehomeTarget()
        assert target.version_file() == "plugin.json"


class TestCodehomeDetect:
    def test_detect_true_with_plugin_json(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.json"), "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f)
            assert target.detect(d) is True

    def test_detect_false_without_plugin_json(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False


class TestCodehomeReadVersion:
    def test_read_version(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "plugin.json"), "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f)
            assert target.read_version(d) == "0.1.0"


class TestCodehomeWriteVersion:
    def test_write_version_updates_version(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.json")
            with open(plugin_path, "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f, indent=2)
                f.write("\n")

            target.write_version(d, "1.2.3")

            with open(plugin_path) as f:
                data = json.load(f)
            assert data["version"] == "1.2.3"
            # Other fields unchanged
            assert data["name"] == "git-hooks"
            assert data["description"] == "Git hook management for codehome"

    def test_write_version_preserves_indent(self):
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.json")
            # Write with 4-space indent
            with open(plugin_path, "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f, indent=4)
                f.write("\n")

            target.write_version(d, "2.0.0")

            with open(plugin_path) as f:
                content = f.read()
            # Should still use 4-space indent
            assert '    "version": "2.0.0"' in content

    def test_write_version_atomic(self):
        """write_version uses atomic rename (no .tmp file left behind)."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.json")
            with open(plugin_path, "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f, indent=2)
                f.write("\n")

            target.write_version(d, "3.0.0")

            # No leftover .tmp file
            assert not os.path.exists(plugin_path + ".tmp")
            # File exists and is valid JSON
            with open(plugin_path) as f:
                data = json.load(f)
            assert data["version"] == "3.0.0"


class TestCodehomeTagFormat:
    def test_tag_format_standard(self):
        """Root-scoped target produces standard v-prefixed tags, no namespacing."""
        target = CodehomeTarget()
        assert target.tag_format(None, "1.2.3") == "v1.2.3"

    def test_tag_format_ignores_name(self):
        """Even if a name is passed, it's ignored (root-scoped, not namespaced)."""
        target = CodehomeTarget()
        assert target.tag_format("git-hooks", "1.2.3") == "v1.2.3"

    def test_tag_format_empty_name(self):
        target = CodehomeTarget()
        assert target.tag_format("", "1.2.3") == "v1.2.3"


class TestPluginJsonValidation:
    def test_valid_plugin_json(self):
        """Valid plugin.json passes without raising."""
        validate_plugin_json(SAMPLE_PLUGIN_JSON)

    def test_missing_name(self):
        data = {"version": "1.0.0", "description": "A plugin"}
        with pytest.raises(PluginValidationError, match="name"):
            validate_plugin_json(data)

    def test_missing_version(self):
        data = {"name": "test", "description": "A plugin"}
        with pytest.raises(PluginValidationError, match="version"):
            validate_plugin_json(data)

    def test_missing_description(self):
        data = {"name": "test", "version": "1.0.0"}
        with pytest.raises(PluginValidationError, match="description"):
            validate_plugin_json(data)

    def test_missing_multiple_fields(self):
        data = {"version": "1.0.0"}
        with pytest.raises(PluginValidationError, match="name.*description"):
            validate_plugin_json(data)

    def test_bad_semver_too_few_parts(self):
        data = {"name": "test", "version": "1.0", "description": "A plugin"}
        with pytest.raises(PluginValidationError, match="not valid semver"):
            validate_plugin_json(data)

    def test_bad_semver_non_numeric(self):
        data = {"name": "test", "version": "1.x.0", "description": "A plugin"}
        with pytest.raises(PluginValidationError, match="not valid semver"):
            validate_plugin_json(data)

    def test_valid_semver_with_extra_parts(self):
        """Semver with prerelease info (e.g. 1.0.0-rc1) -- only first 3 parts checked."""
        # "1.0.0-rc1" splits to ["1", "0", "0-rc1"] -- "0-rc1" is not all digits
        data = {"name": "test", "version": "1.0.0-rc1", "description": "A plugin"}
        with pytest.raises(PluginValidationError, match="not valid semver"):
            validate_plugin_json(data)


class TestCodehomeBuild:
    def test_build_validates_plugin_json(self):
        """build() calls validation and raises on invalid plugin.json."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.json")
            # Missing description
            with open(plugin_path, "w") as f:
                json.dump({"name": "test", "version": "1.0.0"}, f)

            with pytest.raises(PluginValidationError, match="description"):
                target.build(d, "1.0.0")

    def test_build_passes_valid_plugin_json(self):
        """build() succeeds when plugin.json is valid."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            plugin_path = os.path.join(d, "plugin.json")
            with open(plugin_path, "w") as f:
                json.dump(SAMPLE_PLUGIN_JSON, f)

            # Should not raise
            target.build(d, "0.1.0")

    def test_build_no_plugin_json(self):
        """build() is a no-op if plugin.json doesn't exist."""
        target = CodehomeTarget()
        with tempfile.TemporaryDirectory() as d:
            # Should not raise
            target.build(d, "1.0.0")


class TestCodehomeRegistry:
    def test_registered_in_targets(self):
        assert "codehome" in TARGETS

    def test_registered_instance_type(self):
        assert isinstance(TARGETS["codehome"], CodehomeTarget)

    def test_get_project_init_hint(self):
        target = CodehomeTarget()
        hint = target.get_project_init_hint()
        assert "plugin.json" in hint
