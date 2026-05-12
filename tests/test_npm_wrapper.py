"""Tests for rlsbl.npm_wrapper platform models and helpers."""

from rlsbl.npm_wrapper import (
    DEFAULT_PLATFORMS,
    PlatformArtifact,
    PlatformSpec,
    build_artifacts,
    load_platform_config,
)


class TestDefaultPlatforms:
    """Tests for the DEFAULT_PLATFORMS constant."""

    def test_has_six_entries(self):
        assert len(DEFAULT_PLATFORMS) == 6

    def test_correct_npm_platform_values(self):
        names = [spec.npm_platform for spec in DEFAULT_PLATFORMS]
        assert names == [
            "linux-x64",
            "linux-arm64",
            "darwin-x64",
            "darwin-arm64",
            "win32-x64",
            "win32-arm64",
        ]

    def test_all_are_platform_spec_instances(self):
        for spec in DEFAULT_PLATFORMS:
            assert isinstance(spec, PlatformSpec)


class TestPlatformArtifact:
    """Tests for PlatformArtifact construction."""

    def test_construction(self):
        artifact = PlatformArtifact(
            npm_platform="linux-x64",
            os_constraint="linux",
            cpu_constraint="x64",
            asset_pattern="myapp_1.0.0_linux_amd64.tar.gz",
            extract_cmd="tar xzf",
            binary_name="myapp",
        )
        assert artifact.npm_platform == "linux-x64"
        assert artifact.os_constraint == "linux"
        assert artifact.cpu_constraint == "x64"
        assert artifact.asset_pattern == "myapp_1.0.0_linux_amd64.tar.gz"
        assert artifact.extract_cmd == "tar xzf"
        assert artifact.binary_name == "myapp"

    def test_extract_cmd_can_be_none(self):
        artifact = PlatformArtifact(
            npm_platform="win32-x64",
            os_constraint="win32",
            cpu_constraint="x64",
            asset_pattern="myapp.exe",
            extract_cmd=None,
            binary_name="myapp.exe",
        )
        assert artifact.extract_cmd is None


class TestLoadPlatformConfig:
    """Tests for load_platform_config."""

    def test_no_config_returns_all_six(self):
        result = load_platform_config({})
        assert len(result) == 6

    def test_empty_npm_wrapper_returns_all_six(self):
        result = load_platform_config({"npm_wrapper": {}})
        assert len(result) == 6

    def test_filter_to_subset(self):
        config = {"npm_wrapper": {"platforms": ["linux-x64", "darwin-arm64"]}}
        result = load_platform_config(config)
        assert len(result) == 2
        names = [spec.npm_platform for spec in result]
        assert names == ["linux-x64", "darwin-arm64"]

    def test_filter_preserves_order(self):
        # Even if the config lists them in a different order, the result
        # follows DEFAULT_PLATFORMS ordering.
        config = {"npm_wrapper": {"platforms": ["darwin-arm64", "linux-x64"]}}
        result = load_platform_config(config)
        names = [spec.npm_platform for spec in result]
        assert names == ["linux-x64", "darwin-arm64"]

    def test_filter_with_unknown_platform_ignored(self):
        config = {"npm_wrapper": {"platforms": ["linux-x64", "freebsd-x64"]}}
        result = load_platform_config(config)
        assert len(result) == 1
        assert result[0].npm_platform == "linux-x64"

    def test_returns_copies_not_originals(self):
        result = load_platform_config({})
        assert result is not DEFAULT_PLATFORMS


class TestBuildArtifacts:
    """Tests for build_artifacts."""

    def test_combines_specs_with_archive_fn(self):
        specs = [
            PlatformSpec("linux-x64", "linux", "x64"),
            PlatformSpec("darwin-arm64", "darwin", "arm64"),
        ]

        def archive_fn(spec, name):
            ext = ".exe" if spec.os_constraint == "win32" else ""
            return (
                f"{name}_1.0.0_{spec.os_constraint}_{spec.cpu_constraint}.tar.gz",
                "tar xzf",
                f"{name}{ext}",
            )

        artifacts = build_artifacts(specs, "myapp", archive_fn)

        assert len(artifacts) == 2
        assert all(isinstance(a, PlatformArtifact) for a in artifacts)

        linux = artifacts[0]
        assert linux.npm_platform == "linux-x64"
        assert linux.os_constraint == "linux"
        assert linux.cpu_constraint == "x64"
        assert linux.asset_pattern == "myapp_1.0.0_linux_x64.tar.gz"
        assert linux.extract_cmd == "tar xzf"
        assert linux.binary_name == "myapp"

        darwin = artifacts[1]
        assert darwin.npm_platform == "darwin-arm64"
        assert darwin.asset_pattern == "myapp_1.0.0_darwin_arm64.tar.gz"

    def test_archive_fn_can_return_none_extract_cmd(self):
        specs = [PlatformSpec("win32-x64", "win32", "x64")]

        def archive_fn(spec, name):
            return (f"{name}.exe", None, f"{name}.exe")

        artifacts = build_artifacts(specs, "tool", archive_fn)
        assert len(artifacts) == 1
        assert artifacts[0].extract_cmd is None
        assert artifacts[0].binary_name == "tool.exe"

    def test_empty_specs_returns_empty(self):
        artifacts = build_artifacts([], "myapp", lambda s, n: ("", None, ""))
        assert artifacts == []
