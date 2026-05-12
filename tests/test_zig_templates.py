"""Tests for Zig CI and publish template files."""

import os

from rlsbl.targets.zig import ZigTarget

TEMPLATE_DIR = ZigTarget().template_dir()

CROSS_TARGETS = [
    "x86_64-linux",
    "aarch64-linux",
    "x86_64-macos",
    "aarch64-macos",
    "x86_64-windows",
    "aarch64-windows",
]


def _read_template(name):
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestTemplateFilesExist:
    """All three template files must be present in the zig template directory."""

    def test_version_tpl_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATE_DIR, "VERSION.tpl"))

    def test_ci_yml_tpl_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATE_DIR, "ci.yml.tpl"))

    def test_publish_yml_tpl_exists(self):
        assert os.path.isfile(os.path.join(TEMPLATE_DIR, "publish.yml.tpl"))


class TestVersionTemplate:
    """VERSION.tpl contains the version placeholder."""

    def test_contains_version_placeholder(self):
        content = _read_template("VERSION.tpl")
        assert "{{version}}" in content


class TestCiTemplate:
    """ci.yml.tpl sets up Zig and runs build + test."""

    def test_contains_setup_zig_action(self):
        content = _read_template("ci.yml.tpl")
        assert "mlugg/setup-zig" in content

    def test_contains_zig_build_test(self):
        content = _read_template("ci.yml.tpl")
        assert "zig build test" in content

    def test_contains_zig_build(self):
        content = _read_template("ci.yml.tpl")
        assert "zig build" in content

    def test_contains_min_zig_version_var(self):
        content = _read_template("ci.yml.tpl")
        assert "{{zig.minRequiredZig}}" in content

    def test_triggers_on_push_and_pr(self):
        content = _read_template("ci.yml.tpl")
        assert "push:" in content
        assert "pull_request" in content


class TestPublishTemplate:
    """publish.yml.tpl cross-compiles for 6 targets and uploads to GitHub Release."""

    def test_contains_all_cross_compilation_targets(self):
        content = _read_template("publish.yml.tpl")
        for target in CROSS_TARGETS:
            assert target in content, f"Missing cross-compilation target: {target}"

    def test_contains_npm_publish_jobs_placeholder(self):
        content = _read_template("publish.yml.tpl")
        assert "{{npmPublishJobs}}" in content

    def test_contains_release_safe_optimization(self):
        content = _read_template("publish.yml.tpl")
        assert "ReleaseSafe" in content

    def test_contains_gh_release_upload(self):
        content = _read_template("publish.yml.tpl")
        assert "gh release upload" in content

    def test_contains_contents_write_permission(self):
        content = _read_template("publish.yml.tpl")
        assert "contents: write" in content

    def test_windows_binaries_have_exe_extension(self):
        content = _read_template("publish.yml.tpl")
        assert "x86_64-windows.exe" in content
        assert "aarch64-windows.exe" in content

    def test_triggers_on_release_published(self):
        content = _read_template("publish.yml.tpl")
        assert "release:" in content
        assert "published" in content

    def test_contains_setup_zig_action(self):
        content = _read_template("publish.yml.tpl")
        assert "mlugg/setup-zig" in content
