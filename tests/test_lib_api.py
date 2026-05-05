"""Tests for the rlsbl.lib public API."""

import json
from pathlib import Path


def test_public_imports():
    """All public symbols are importable from rlsbl.lib."""
    from rlsbl.lib import ConfigMigrator, SchemaLoadError, load_schema, migrate

    # Verify they are the real classes/functions, not None
    assert ConfigMigrator is not None
    assert load_schema is not None
    assert SchemaLoadError is not None
    assert migrate is not None


def test_migrate_returns_none_without_schema(tmp_path):
    """migrate() returns None when no .rlsbl/config-schema.json exists."""
    from rlsbl.lib import migrate

    result = migrate(tmp_path)
    assert result is None


def test_migrate_runs_with_schema(tmp_path):
    """migrate() loads schema and runs migrations when schema file exists."""
    from rlsbl.lib import migrate

    # Set up .rlsbl/config-schema.json
    rlsbl_dir = tmp_path / ".rlsbl"
    rlsbl_dir.mkdir()

    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()

    # Write a defaults file
    defaults = {"name": "test", "version": 1, "new_key": "default_value"}
    (defaults_dir / "config.json").write_text(json.dumps(defaults))

    # Write the schema declaration
    schema_decl = {
        "schema_version_key": "_schema_version",
        "files": [
            {
                "path": "config.json",
                "defaults_path": "defaults/config.json",
                "merge_strategy": "flat_dict",
            }
        ],
    }
    (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema_decl))

    # Write an existing config file missing the new_key
    existing_config = {"name": "test", "version": 1}
    (tmp_path / "config.json").write_text(json.dumps(existing_config))

    # Run migrate
    result = migrate(tmp_path)

    # Should return a dict indicating config.json was changed
    assert isinstance(result, dict)
    assert result["config.json"] is True

    # Verify the file was updated with the missing default key
    updated = json.loads((tmp_path / "config.json").read_text())
    assert updated["new_key"] == "default_value"
    assert updated["name"] == "test"  # existing key preserved


def test_migrate_no_changes_needed(tmp_path):
    """migrate() returns dict with False when config already matches defaults."""
    from rlsbl.lib import migrate

    # Set up .rlsbl/config-schema.json
    rlsbl_dir = tmp_path / ".rlsbl"
    rlsbl_dir.mkdir()

    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()

    # Defaults and existing config are identical
    config_data = {"name": "test", "version": 1}
    (defaults_dir / "config.json").write_text(json.dumps(config_data))

    schema_decl = {
        "files": [
            {
                "path": "config.json",
                "defaults_path": "defaults/config.json",
                "merge_strategy": "flat_dict",
            }
        ],
    }
    (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema_decl))
    (tmp_path / "config.json").write_text(json.dumps(config_data))

    result = migrate(tmp_path)

    assert isinstance(result, dict)
    assert result["config.json"] is False
