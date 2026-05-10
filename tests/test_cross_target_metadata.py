"""Tests for cross-target metadata consistency (Phases 1-4).

Covers: process_template dotted vars, normalize functions, min-version extraction,
read_name/read_metadata, _merge_template_vars, and doctor metadata checks.
"""

import json
from unittest.mock import patch

import pytest

from rlsbl.commands.init_cmd import process_template, _merge_template_vars
from rlsbl.targets import TARGETS
from rlsbl.targets.utils import normalize_npm, normalize_pypi, normalize_go


# ---------------------------------------------------------------------------
# Test class 1: process_template with dotted variable support
# ---------------------------------------------------------------------------


class TestProcessTemplateDotted:
    """Unit tests for the updated process_template regex supporting dotted names."""

    def test_simple_var(self):
        content, unreplaced = process_template("Hello {{name}}", {"name": "foo"})
        assert content == "Hello foo"
        assert unreplaced == []

    def test_dotted_var(self):
        content, unreplaced = process_template(
            "v={{pypi.minRequiredPython}}", {"pypi.minRequiredPython": "3.11"}
        )
        assert content == "v=3.11"
        assert unreplaced == []

    def test_dotted_var_unreplaced(self):
        content, unreplaced = process_template("v={{pypi.minRequiredPython}}", {})
        assert content == "v={{pypi.minRequiredPython}}"
        assert "pypi.minRequiredPython" in unreplaced

    def test_goreleaser_not_matched(self):
        """GoReleaser's {{.Version}} must not be matched."""
        content, unreplaced = process_template("{{.Version}}", {"Version": "1.0"})
        assert content == "{{.Version}}"  # unchanged

    def test_goreleaser_spaced_not_matched(self):
        content, unreplaced = process_template("{{ .ProjectName }}", {})
        assert content == "{{ .ProjectName }}"

    def test_multi_level_dotted(self):
        content, unreplaced = process_template("{{a.b.c}}", {"a.b.c": "val"})
        assert content == "val"

    def test_mixed_simple_and_dotted(self):
        content, unreplaced = process_template(
            "{{name}} uses {{pypi.minRequiredPython}}",
            {"name": "foo", "pypi.minRequiredPython": "3.11"},
        )
        assert content == "foo uses 3.11"


# ---------------------------------------------------------------------------
# Test class 2: normalize functions
# ---------------------------------------------------------------------------


class TestNormalizeFunctions:
    """Unit tests for name-normalization utilities in targets/utils.py."""

    def test_normalize_npm_strips_special(self):
        assert normalize_npm("my-pkg") == normalize_npm("my_pkg") == normalize_npm("my.pkg")

    def test_normalize_npm_lowercases(self):
        assert normalize_npm("MyPkg") == "mypkg"

    def test_normalize_pypi_pep503(self):
        assert normalize_pypi("My_Pkg") == "my-pkg"
        assert normalize_pypi("my--pkg") == "my-pkg"

    def test_normalize_go_last_segment(self):
        assert normalize_go("github.com/user/my-repo") == "my-repo"
        assert normalize_go("my-repo") == "my-repo"

    def test_normalize_go_lowercases(self):
        assert normalize_go("github.com/User/MyRepo") == "myrepo"


# ---------------------------------------------------------------------------
# Test class 3: min-version extraction from template_vars
# ---------------------------------------------------------------------------


class TestMinVersionExtraction:
    """Test the min-version regex extraction from target template_vars."""

    def test_pypi_min_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\nrequires-python = ">=3.11"\n'
        )
        vars_ = TARGETS["pypi"].template_vars(str(tmp_path))
        assert vars_["minRequiredPython"] == "3.11"

    def test_pypi_min_python_with_upper_bound(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\nrequires-python = ">=3.11,<4"\n'
        )
        vars_ = TARGETS["pypi"].template_vars(str(tmp_path))
        assert vars_["minRequiredPython"] == "3.11"

    def test_pypi_no_requires_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
        )
        vars_ = TARGETS["pypi"].template_vars(str(tmp_path))
        assert "minRequiredPython" not in vars_

    def test_npm_min_node(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0", "engines": {"node": ">=18"}}'
        )
        vars_ = TARGETS["npm"].template_vars(str(tmp_path))
        assert vars_["minRequiredNode"] == "18"

    def test_npm_min_node_with_minor(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0", "engines": {"node": ">=18.0.0"}}'
        )
        vars_ = TARGETS["npm"].template_vars(str(tmp_path))
        assert vars_["minRequiredNode"] == "18.0.0"

    def test_npm_no_engines(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0"}'
        )
        vars_ = TARGETS["npm"].template_vars(str(tmp_path))
        assert "minRequiredNode" not in vars_

    def test_go_min_version(self, tmp_path):
        (tmp_path / "go.mod").write_text("module github.com/user/test\n\ngo 1.21\n")
        (tmp_path / "VERSION").write_text("1.0.0")
        vars_ = TARGETS["go"].template_vars(str(tmp_path))
        assert vars_["minRequiredGo"] == "1.21"

    def test_cargo_min_rust(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "test"\nversion = "1.0.0"\n'
            'rust-version = "1.70"\nedition = "2021"\n'
        )
        vars_ = TARGETS["cargo"].template_vars(str(tmp_path))
        assert vars_["minRequiredRust"] == "1.70"
        assert vars_["edition"] == "2021"


# ---------------------------------------------------------------------------
# Test class 4: read_name and read_metadata
# ---------------------------------------------------------------------------


class TestReadNameAndMetadata:
    """Test read_name() and read_metadata() on key targets."""

    def test_pypi_read_name(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-package"\nversion = "1.0.0"\n'
        )
        assert TARGETS["pypi"].read_name(str(tmp_path)) == "my-package"

    def test_pypi_read_metadata_string_license(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
            'license = "MIT"\ndescription = "A test"\n'
        )
        meta = TARGETS["pypi"].read_metadata(str(tmp_path))
        assert meta["license"] == "MIT"
        assert meta["description"] == "A test"

    def test_pypi_read_metadata_table_license(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n\n'
            "[project.license]\n"
            'text = "MIT"\n'
        )
        meta = TARGETS["pypi"].read_metadata(str(tmp_path))
        assert meta["license"] == "MIT"

    def test_npm_read_name(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "@scope/pkg", "version": "1.0.0"}'
        )
        assert TARGETS["npm"].read_name(str(tmp_path)) == "@scope/pkg"

    def test_npm_read_metadata(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0", "license": "ISC", "description": "Hello"}'
        )
        meta = TARGETS["npm"].read_metadata(str(tmp_path))
        assert meta["license"] == "ISC"
        assert meta["description"] == "Hello"

    def test_go_read_name(self, tmp_path):
        (tmp_path / "go.mod").write_text("module github.com/user/myrepo\n\ngo 1.21\n")
        assert TARGETS["go"].read_name(str(tmp_path)) == "myrepo"

    def test_read_name_missing_file(self, tmp_path):
        assert TARGETS["pypi"].read_name(str(tmp_path)) is None
        assert TARGETS["npm"].read_name(str(tmp_path)) is None

    def test_read_metadata_missing_file(self, tmp_path):
        assert TARGETS["pypi"].read_metadata(str(tmp_path)) == {}
        assert TARGETS["npm"].read_metadata(str(tmp_path)) == {}


# ---------------------------------------------------------------------------
# Test class 5: _merge_template_vars
# ---------------------------------------------------------------------------


class TestMergeTemplateVars:
    """Test the _merge_template_vars function from init_cmd.py."""

    def test_merge_primary_unnamespaced(self, tmp_path):
        # Create both package.json and pyproject.toml
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0"}'
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
            'requires-python = ">=3.11"\n'
        )
        merged = _merge_template_vars(["npm", "pypi"], "npm", str(tmp_path))
        # Primary (npm) vars are un-namespaced
        assert "name" in merged
        # All vars are namespaced
        assert "npm.name" in merged
        assert "pypi.name" in merged
        assert "pypi.minRequiredPython" in merged

    def test_merge_year_not_included(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"name": "test", "version": "1.0.0"}'
        )
        merged = _merge_template_vars(["npm"], "npm", str(tmp_path))
        # year is added by the caller, not _merge_template_vars
        assert "year" not in merged


# ---------------------------------------------------------------------------
# Test class 6: doctor metadata consistency checks
# ---------------------------------------------------------------------------


class TestDoctorMetadataChecks:
    """Test the new doctor check functions for name/license/description consistency."""

    def test_name_consistency_pass(self, tmp_project):
        """Two targets returning the same name should PASS."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "mypackage", "version": "1.0.0"})
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "mypackage"\nversion = "1.0.0"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_name_consistency

        status, message = _check_name_consistency()
        assert status == "PASS"
        assert "mypackage" in message

    def test_name_consistency_warn_mismatch(self, tmp_project):
        """Targets with different normalized names should WARN."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "alpha", "version": "1.0.0"})
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "beta"\nversion = "1.0.0"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_name_consistency

        status, message = _check_name_consistency()
        assert status == "WARN"
        assert "mismatch" in message

    def test_name_consistency_warn_no_targets(self, tmp_project):
        """No targets detected should WARN."""
        # No project files, no config -> detect_targets returns []
        from rlsbl.commands.doctor import _check_name_consistency

        status, message = _check_name_consistency()
        assert status == "WARN"
        assert "no targets" in message

    def test_license_consistency_pass(self, tmp_project):
        """Two targets with the same license should PASS."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0", "license": "MIT"})
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\nlicense = "MIT"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_license_consistency

        status, message = _check_license_consistency()
        assert status == "PASS"
        assert "MIT" in message

    def test_license_consistency_warn_mismatch(self, tmp_project):
        """Targets with different licenses should WARN."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0", "license": "MIT"})
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\nlicense = "Apache-2.0"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_license_consistency

        status, message = _check_license_consistency()
        assert status == "WARN"
        assert "mismatch" in message

    def test_license_fewer_than_two(self, tmp_project):
        """Only one target reporting a license should PASS."""
        (tmp_project / "package.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0", "license": "MIT"})
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm"]}))

        from rlsbl.commands.doctor import _check_license_consistency

        status, message = _check_license_consistency()
        assert status == "PASS"

    def test_description_consistency_warn(self, tmp_project):
        """Targets with different descriptions should WARN."""
        (tmp_project / "package.json").write_text(
            json.dumps({
                "name": "test",
                "version": "1.0.0",
                "description": "An npm package",
            })
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
            'description = "A Python package"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_description_consistency

        status, message = _check_description_consistency()
        assert status == "WARN"
        assert "mismatch" in message

    def test_description_consistency_pass(self, tmp_project):
        """Targets with the same description should PASS."""
        (tmp_project / "package.json").write_text(
            json.dumps({
                "name": "test",
                "version": "1.0.0",
                "description": "A cool tool",
            })
        )
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
            'description = "A cool tool"\n'
        )
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        (rlsbl_dir / "config.json").write_text(json.dumps({"targets": ["npm", "pypi"]}))

        from rlsbl.commands.doctor import _check_description_consistency

        status, message = _check_description_consistency()
        assert status == "PASS"
        assert "A cool tool" in message
