"""Tests for class-based release targets conforming to the ReleaseTarget Protocol."""

import json
import os
import tempfile
from unittest.mock import patch

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
        """TARGETS['go'].publish() without go.mod is effectively a no-op (prints warning)."""
        with tempfile.TemporaryDirectory() as d:
            # Should complete without raising (prints warning about missing go.mod)
            TARGETS["go"].publish(d, "1.0.0")


class TestDetectTargetsConfig:
    """Tests for config-driven target detection via .rlsbl/config.json."""

    def test_config_targets_override_autodetection(self):
        """Config targets take precedence: only 'npm' returned even if go.mod exists."""
        with tempfile.TemporaryDirectory() as d:
            # Create go.mod so auto-detection would find 'go'
            with open(os.path.join(d, "go.mod"), "w") as f:
                f.write("module example.com/test\n\ngo 1.21\n")
            # Create config that only declares npm
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "config.json"), "w") as f:
                json.dump({"targets": ["npm"]}, f)
            result = detect_targets(d)
            assert result == ["npm"]

    def test_no_config_falls_back_to_autodetection(self):
        """Without config, detect_targets uses auto-detection (backward compat)."""
        with tempfile.TemporaryDirectory() as d:
            pkg_path = os.path.join(d, "package.json")
            with open(pkg_path, "w") as f:
                json.dump({"name": "test", "version": "1.0.0"}, f)
            result = detect_targets(d)
            assert "npm" in result

    def test_empty_targets_array_returns_empty(self):
        """Explicit empty targets array means no targets."""
        with tempfile.TemporaryDirectory() as d:
            # Create package.json so auto-detection would find npm
            with open(os.path.join(d, "package.json"), "w") as f:
                json.dump({"name": "test", "version": "1.0.0"}, f)
            # Config explicitly declares no targets
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "config.json"), "w") as f:
                json.dump({"targets": []}, f)
            result = detect_targets(d)
            assert result == []

    def test_unknown_target_warns_and_skips(self, capsys):
        """Unknown target names produce a warning and are skipped."""
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "config.json"), "w") as f:
                json.dump({"targets": ["npm", "nonexistent"]}, f)
            result = detect_targets(d)
            assert result == ["npm"]
            captured = capsys.readouterr()
            assert "nonexistent" in captured.err
            assert "Warning" in captured.err


class TestNpmPublish:
    """Tests for NpmTarget.publish() hybrid behavior."""

    def test_publish_with_token(self, capsys):
        """NpmTarget.publish() calls npm publish when NPM_TOKEN is set."""
        target = NpmTarget()
        with patch.dict(os.environ, {"NPM_TOKEN": "fake-token"}):
            with patch("rlsbl.targets.npm.run") as mock_run:
                target.publish(".", "1.2.3")
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][0] == "npm"
                assert call_args[0][1] == ["publish", "--provenance", "--access", "public"]
                assert call_args[1]["env"]["NPM_TOKEN"] == "fake-token"
        captured = capsys.readouterr()
        assert "Published to npm: 1.2.3" in captured.out

    def test_publish_without_token(self, capsys):
        """NpmTarget.publish() prints skip message when NPM_TOKEN is absent."""
        target = NpmTarget()
        env = os.environ.copy()
        env.pop("NPM_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            target.publish(".", "1.2.3")
        captured = capsys.readouterr()
        assert "Skipping local npm publish (no NPM_TOKEN). CI will handle it." in captured.out


class TestPypiPublish:
    """Tests for PypiTarget.publish() hybrid behavior."""

    def test_publish_with_pypi_token(self, capsys):
        """PypiTarget.publish() calls uv build + uv publish when PYPI_TOKEN is set."""
        target = PypiTarget()
        with patch.dict(os.environ, {"PYPI_TOKEN": "fake-pypi-token"}, clear=False):
            with patch("rlsbl.targets.pypi.run") as mock_run:
                target.publish(".", "2.0.0")
                assert mock_run.call_count == 2
                # First call: uv build
                first_call = mock_run.call_args_list[0]
                assert first_call[0][0] == "uv"
                assert first_call[0][1] == ["build"]
                # Second call: uv publish
                second_call = mock_run.call_args_list[1]
                assert second_call[0][0] == "uv"
                assert second_call[0][1] == ["publish"]
                assert second_call[1]["env"]["UV_PUBLISH_TOKEN"] == "fake-pypi-token"
        captured = capsys.readouterr()
        assert "Published to PyPI: 2.0.0" in captured.out

    def test_publish_with_twine_password(self, capsys):
        """PypiTarget.publish() also works with TWINE_PASSWORD as fallback."""
        target = PypiTarget()
        env = os.environ.copy()
        env.pop("PYPI_TOKEN", None)
        env["TWINE_PASSWORD"] = "twine-secret"
        with patch.dict(os.environ, env, clear=True):
            with patch("rlsbl.targets.pypi.run") as mock_run:
                target.publish(".", "2.0.0")
                assert mock_run.call_count == 2
                second_call = mock_run.call_args_list[1]
                assert second_call[1]["env"]["UV_PUBLISH_TOKEN"] == "twine-secret"

    def test_publish_without_token(self, capsys):
        """PypiTarget.publish() prints skip message when no token is set."""
        target = PypiTarget()
        env = os.environ.copy()
        env.pop("PYPI_TOKEN", None)
        env.pop("TWINE_PASSWORD", None)
        with patch.dict(os.environ, env, clear=True):
            target.publish(".", "2.0.0")
        captured = capsys.readouterr()
        assert "Skipping local PyPI publish (no PYPI_TOKEN). CI will handle it." in captured.out


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
