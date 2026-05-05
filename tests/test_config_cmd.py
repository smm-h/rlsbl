"""Tests for rlsbl config subcommands (init, migrate, status)."""

import json
import os
from pathlib import Path

import pytest

from rlsbl.commands.config import run_cmd


class TestConfigInit:
    """Tests for 'rlsbl config init'."""

    def test_creates_expected_files(self, tmp_project):
        """config init creates schema, defaults, and migrations dir."""
        run_cmd("npm", ["init"], {})

        schema_path = tmp_project / ".rlsbl" / "config-schema.json"
        assert schema_path.exists()
        schema = json.loads(schema_path.read_text())
        assert schema["schema_version_key"] == "_schema_version"
        assert len(schema["files"]) == 1
        assert schema["files"][0]["path"] == "config.json"
        assert schema["files"][0]["merge_strategy"] == "deep_recursive"

        defaults_config = tmp_project / "defaults" / "config.json"
        assert defaults_config.exists()
        defaults = json.loads(defaults_config.read_text())
        assert defaults == {"_schema_version": 0}

        migrations_dir = tmp_project / ".rlsbl" / "migrations"
        assert migrations_dir.is_dir()

    def test_idempotent_does_not_overwrite(self, tmp_project):
        """Running config init twice does not overwrite existing files."""
        run_cmd("npm", ["init"], {})

        # Modify the schema file
        schema_path = tmp_project / ".rlsbl" / "config-schema.json"
        schema = json.loads(schema_path.read_text())
        schema["custom_key"] = "custom_value"
        schema_path.write_text(json.dumps(schema))

        # Run init again
        run_cmd("npm", ["init"], {})

        # Verify custom content preserved
        schema = json.loads(schema_path.read_text())
        assert schema.get("custom_key") == "custom_value"


class TestConfigMigrate:
    """Tests for 'rlsbl config migrate'."""

    def test_no_schema_exits_with_error(self, tmp_project, capsys):
        """config migrate with no schema prints error and exits 1."""
        with pytest.raises(SystemExit) as exc_info:
            run_cmd("npm", ["migrate"], {})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No config schema found" in captured.err

    def test_runs_migrations_and_creates_files(self, tmp_project, capsys):
        """config migrate creates missing config files from defaults."""
        # Set up schema infrastructure
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        schema = {
            "schema_version_key": "_schema_version",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                }
            ],
        }
        (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema))

        # Create defaults
        defaults_dir = tmp_project / "defaults"
        defaults_dir.mkdir()
        (defaults_dir / "config.json").write_text(
            json.dumps({"_schema_version": 0, "setting_a": True})
        )

        # Run migrate -- config.json doesn't exist yet, should be created
        run_cmd("npm", ["migrate"], {})

        config_path = tmp_project / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["_schema_version"] == 0
        assert data["setting_a"] is True

        captured = capsys.readouterr()
        assert "config.json" in captured.out

    def test_dry_run_does_not_write(self, tmp_project, capsys):
        """config migrate --dry-run reports but does not create files."""
        # Set up schema
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        schema = {
            "schema_version_key": "_schema_version",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                }
            ],
        }
        (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema))

        defaults_dir = tmp_project / "defaults"
        defaults_dir.mkdir()
        (defaults_dir / "config.json").write_text(
            json.dumps({"_schema_version": 0, "key": "val"})
        )

        run_cmd("npm", ["migrate"], {"dry-run": True})

        # config.json should NOT have been created
        assert not (tmp_project / "config.json").exists()

        captured = capsys.readouterr()
        assert "Dry run" in captured.out

    def test_merges_defaults_into_existing(self, tmp_project, capsys):
        """config migrate merges new default keys into existing config."""
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        schema = {
            "schema_version_key": "_schema_version",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                }
            ],
        }
        (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema))

        defaults_dir = tmp_project / "defaults"
        defaults_dir.mkdir()
        (defaults_dir / "config.json").write_text(
            json.dumps({"_schema_version": 0, "new_key": "new_val", "existing": "default"})
        )

        # Pre-existing config with user customization
        (tmp_project / "config.json").write_text(
            json.dumps({"_schema_version": 0, "existing": "user_val"})
        )

        run_cmd("npm", ["migrate"], {})

        data = json.loads((tmp_project / "config.json").read_text())
        # new_key should be added from defaults
        assert data["new_key"] == "new_val"
        # existing should preserve user value
        assert data["existing"] == "user_val"


class TestConfigStatus:
    """Tests for 'rlsbl config status'."""

    def test_no_schema_exits_with_error(self, tmp_project, capsys):
        """config status with no schema prints error and exits 1."""
        with pytest.raises(SystemExit) as exc_info:
            run_cmd("npm", ["status"], {})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No config schema found" in captured.err

    def test_shows_correct_info(self, tmp_project, capsys):
        """config status reports managed files, version, pending migrations."""
        rlsbl_dir = tmp_project / ".rlsbl"
        rlsbl_dir.mkdir(parents=True, exist_ok=True)
        schema = {
            "schema_version_key": "_schema_version",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                },
                {
                    "path": "theme.json",
                    "defaults_path": "defaults/theme.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema))

        defaults_dir = tmp_project / "defaults"
        defaults_dir.mkdir()
        (defaults_dir / "config.json").write_text(json.dumps({"_schema_version": 0}))
        (defaults_dir / "theme.json").write_text(json.dumps({"color": "blue"}))

        # Create config.json with version 0
        (tmp_project / "config.json").write_text(json.dumps({"_schema_version": 0}))
        # theme.json does not exist

        # Add a migration
        mig_dir = rlsbl_dir / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_add_feature.py").write_text(
            'version = 1\ndescription = "Add feature flag"\n'
            'def apply(configs):\n    configs["config.json"]["feature"] = True\n'
        )

        run_cmd("npm", ["status"], {})

        captured = capsys.readouterr()
        assert "Managed files: 2" in captured.out
        assert "Schema version: 0" in captured.out
        assert "Pending migrations: 1" in captured.out
        assert "config.json: exists" in captured.out
        assert "theme.json: missing" in captured.out


class TestConfigUnknownSubcommand:
    """Test unknown subcommand handling."""

    def test_unknown_subcommand_exits(self, tmp_project, capsys):
        """Unknown subcommand prints error and exits 1."""
        with pytest.raises(SystemExit) as exc_info:
            run_cmd("npm", ["bogus"], {})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "unknown config subcommand" in captured.err


class TestConfigNoSubcommand:
    """Test that no subcommand prints help listing available subcommands."""

    def test_no_args_shows_help(self, tmp_project, capsys):
        """config with no args prints help with available subcommands."""
        run_cmd("npm", [], {})
        captured = capsys.readouterr()
        assert "Usage: rlsbl config <subcommand>" in captured.out
        assert "show" in captured.out
        assert "init" in captured.out
        assert "migrate" in captured.out
        assert "status" in captured.out


class TestConfigShow:
    """Test that 'rlsbl config show' displays project configuration."""

    def test_show_displays_config(self, tmp_project, capsys):
        """config show displays resolved project configuration output."""
        # Create a minimal pyproject.toml so registries detect something
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "0.1.0"\n'
        )
        run_cmd("pypi", ["show"], {})
        captured = capsys.readouterr()
        assert "Detected registries:" in captured.out
