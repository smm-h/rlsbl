"""Tests for ZigTarget: detection, version delegation, template vars, and registration."""

import os
import tempfile

from rlsbl.targets.zig import ZigTarget
from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets import TARGETS


SAMPLE_ZON = """\
.{
    .name = "my-zig-project",
    .version = "0.1.0",
    .minimum_zig_version = "0.13.0",
    .paths = .{
        "build.zig",
        "build.zig.zon",
        "src",
    },
}
"""

SAMPLE_ZON_NO_NAME = """\
.{
    .version = "0.2.0",
    .minimum_zig_version = "0.13.0",
}
"""

SAMPLE_ZON_NO_MIN_ZIG = """\
.{
    .name = "minless",
    .version = "0.3.0",
}
"""

SAMPLE_ZON_MALFORMED = """\
this is not valid zon at all
"""

BUILD_ZIG_BINARY = """\
const std = @import("std");

pub fn build(b: *std.Build) !void {
    const exe = b.addExecutable(.{
        .name = "my-zig-project",
        .root_source_file = b.path("src/main.zig"),
    });
    b.installArtifact(exe);
}
"""

BUILD_ZIG_LIBRARY = """\
const std = @import("std");

pub fn build(b: *std.Build) !void {
    const lib = b.addStaticLibrary(.{
        .name = "my-zig-lib",
        .root_source_file = b.path("src/root.zig"),
    });
    b.installArtifact(lib);
}
"""

BUILD_ZIG_EXE_CALL = """\
const std = @import("std");

pub fn build(b: *std.Build) !void {
    const target = b.standardTargetOptions(.{});
    _ = b.exe("app", "src/main.zig", target);
}
"""


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestZigTargetDetect:
    """ZigTarget.detect() checks for build.zig.zon (primary) and build.zig (secondary)."""

    def test_detect_with_zon(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            assert target.detect(d) is True

    def test_detect_with_build_zig_only(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig"), BUILD_ZIG_BINARY)
            assert target.detect(d) is True

    def test_detect_false_empty_dir(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_detect_prefers_zon(self):
        """Both files present -- detect via build.zig.zon (primary)."""
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "build.zig"), BUILD_ZIG_BINARY)
            assert target.detect(d) is True


class TestZigTargetReadVersion:
    """read_version delegates to read_zig_version."""

    def test_read_from_version_file(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "VERSION"), "1.2.3\n")
            assert target.read_version(d) == "1.2.3"

    def test_read_from_zon_fallback(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            assert target.read_version(d) == "0.1.0"

    def test_raises_when_no_version_source(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            try:
                target.read_version(d)
                assert False, "Expected FileNotFoundError"
            except FileNotFoundError:
                pass


class TestZigTargetWriteVersion:
    """write_version delegates to write_zig_version."""

    def test_writes_version_file(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            target.write_version(d, "2.0.0")
            assert _read(os.path.join(d, "VERSION")) == "2.0.0\n"

    def test_syncs_zon(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            target.write_version(d, "1.5.0")
            content = _read(os.path.join(d, "build.zig.zon"))
            assert '.version = "1.5.0"' in content


class TestZigTargetProperties:
    """Static properties and method return values."""

    def test_name(self):
        target = ZigTarget()
        assert target.name == "zig"

    def test_version_file(self):
        target = ZigTarget()
        assert target.version_file() == "VERSION"

    def test_is_release_target(self):
        target = ZigTarget()
        assert isinstance(target, ReleaseTarget)

    def test_tag_format_inherited(self):
        target = ZigTarget()
        assert target.tag_format("1.2.3") == "v1.2.3"

    def test_template_dir(self):
        target = ZigTarget()
        td = target.template_dir()
        assert td is not None
        assert td.endswith(os.path.join("templates", "zig"))

    def test_get_project_init_hint(self):
        target = ZigTarget()
        assert "zig init" in target.get_project_init_hint()


class TestZigTargetTemplateVars:
    """template_vars extracts name, version, minRequiredZig, isLibrary."""

    def test_extracts_name_from_zon(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["name"] == "my-zig-project"
            assert vars["zig.projectName"] == "my-zig-project"

    def test_extracts_min_required_zig(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["zig.minRequiredZig"] == "0.13.0"

    def test_fallback_name_to_dirname(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["name"] == os.path.basename(d)

    def test_fallback_version(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            vars = target.template_vars(d)
            assert vars["version"] == "0.0.0"

    def test_fallback_min_zig_version(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON_NO_MIN_ZIG)
            vars = target.template_vars(d)
            assert vars["zig.minRequiredZig"] == "0.14.0"

    def test_detects_binary(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "build.zig"), BUILD_ZIG_BINARY)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["zig.isLibrary"] is False

    def test_detects_library(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "build.zig"), BUILD_ZIG_LIBRARY)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["zig.isLibrary"] is True

    def test_detects_binary_exe_call(self):
        """exe( shorthand also detects a binary target."""
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "build.zig"), BUILD_ZIG_EXE_CALL)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["zig.isLibrary"] is False

    def test_library_when_no_build_zig(self):
        """No build.zig means library (no executable detected)."""
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            _write(os.path.join(d, "VERSION"), "0.1.0\n")
            vars = target.template_vars(d)
            assert vars["zig.isLibrary"] is True

    def test_malformed_zon_uses_fallbacks(self):
        target = ZigTarget()
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON_MALFORMED)
            vars = target.template_vars(d)
            assert vars["name"] == os.path.basename(d)
            assert vars["version"] == "0.0.0"
            assert vars["zig.minRequiredZig"] == "0.14.0"


class TestZigTargetTemplateMappings:
    """template_mappings returns expected list for CI/publish workflows."""

    def test_returns_expected_mappings(self):
        target = ZigTarget()
        mappings = target.template_mappings()
        templates = [m["template"] for m in mappings]
        targets = [m["target"] for m in mappings]
        assert "VERSION.tpl" in templates
        assert "ci.yml.tpl" in templates
        assert "publish.yml.tpl" in templates
        assert "VERSION" in targets
        assert ".github/workflows/ci.yml" in targets
        assert ".github/workflows/publish.yml" in targets

    def test_mappings_are_list_of_dicts(self):
        target = ZigTarget()
        mappings = target.template_mappings()
        assert isinstance(mappings, list)
        for m in mappings:
            assert isinstance(m, dict)
            assert "template" in m
            assert "target" in m


class TestZigTargetRegistered:
    """ZigTarget is registered in TARGETS."""

    def test_registered_in_targets(self):
        assert "zig" in TARGETS
        assert isinstance(TARGETS["zig"], ZigTarget)

    def test_auto_detects_zon(self):
        """Auto-detection finds zig target when build.zig.zon is present."""
        from rlsbl.targets import detect_targets
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            found = detect_targets(d)
            names = [t.name for t in found]
            assert "zig" in names
