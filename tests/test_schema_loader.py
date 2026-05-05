"""Tests for rlsbl.lib.schema_loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlsbl.lib.schema_loader import SchemaLoadError, load_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_schema(tmp_path: Path, schema_json: dict, defaults: dict[str, object] | None = None):
    """Create .rlsbl/config-schema.json and any defaults files."""
    rlsbl_dir = tmp_path / ".rlsbl"
    rlsbl_dir.mkdir(parents=True, exist_ok=True)
    (rlsbl_dir / "config-schema.json").write_text(json.dumps(schema_json, indent=2))

    if defaults:
        for rel_path, data in defaults.items():
            full_path = tmp_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(json.dumps(data, indent=2))


def _create_migration(tmp_path: Path, filename: str, content: str):
    """Write a migration Python file in .rlsbl/migrations/."""
    mig_dir = tmp_path / ".rlsbl" / "migrations"
    mig_dir.mkdir(parents=True, exist_ok=True)
    filepath = mig_dir / filename
    filepath.write_text(content)


# ---------------------------------------------------------------------------
# Missing schema file returns None
# ---------------------------------------------------------------------------


class TestMissingSchema:
    def test_returns_none_when_no_schema_file(self, tmp_path):
        """load_schema returns None if .rlsbl/config-schema.json doesn't exist."""
        result = load_schema(tmp_path)
        assert result is None

    def test_returns_none_when_rlsbl_dir_missing(self, tmp_path):
        """Returns None even if .rlsbl/ directory doesn't exist."""
        result = load_schema(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Loading a valid schema with files
# ---------------------------------------------------------------------------


class TestLoadValidSchema:
    def test_loads_two_files(self, tmp_path):
        """Loads a schema with 2 file entries and resolves defaults."""
        config_defaults = {"theme": "dark", "debug": False}
        segments_defaults = [
            {"key": "main", "color": "blue"},
            {"key": "sidebar", "color": "gray"},
        ]

        schema_json = {
            "schema_version_key": "_schema_version",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                },
                {
                    "path": "segments.json",
                    "defaults_path": "defaults/segments.json",
                    "merge_strategy": "list_by_key",
                    "match_field": "key",
                },
            ],
        }

        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": config_defaults,
            "defaults/segments.json": segments_defaults,
        })

        result = load_schema(tmp_path)
        assert result is not None
        assert result["schema_version_key"] == "_schema_version"
        assert len(result["files"]) == 2

        # First file entry
        f0 = result["files"][0]
        assert f0["path"] == "config.json"
        assert f0["defaults"] == config_defaults
        assert f0["merge_strategy"] == "deep_recursive"
        assert "match_field" not in f0

        # Second file entry
        f1 = result["files"][1]
        assert f1["path"] == "segments.json"
        assert f1["defaults"] == segments_defaults
        assert f1["merge_strategy"] == "list_by_key"
        assert f1["match_field"] == "key"

    def test_uses_default_schema_version_key(self, tmp_path):
        """If schema_version_key is omitted, defaults to _schema_version."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {"a": 1},
        })

        result = load_schema(tmp_path)
        assert result is not None
        assert result["schema_version_key"] == "_schema_version"

    def test_empty_migrations_when_no_dir(self, tmp_path):
        """If .rlsbl/migrations/ doesn't exist, migrations list is empty."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        result = load_schema(tmp_path)
        assert result is not None
        assert result["migrations"] == []


# ---------------------------------------------------------------------------
# Defaults loading
# ---------------------------------------------------------------------------


class TestDefaultsLoading:
    def test_loads_dict_defaults(self, tmp_path):
        """Defaults can be a JSON object."""
        defaults_data = {"key1": "value1", "nested": {"a": 1, "b": 2}}
        schema_json = {
            "files": [
                {
                    "path": "app.json",
                    "defaults_path": "defaults/app.json",
                    "merge_strategy": "deep_recursive",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/app.json": defaults_data,
        })

        result = load_schema(tmp_path)
        assert result["files"][0]["defaults"] == defaults_data

    def test_loads_list_defaults(self, tmp_path):
        """Defaults can be a JSON array."""
        defaults_data = [{"id": "a", "val": 1}, {"id": "b", "val": 2}]
        schema_json = {
            "files": [
                {
                    "path": "items.json",
                    "defaults_path": "defaults/items.json",
                    "merge_strategy": "list_by_key",
                    "match_field": "id",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/items.json": defaults_data,
        })

        result = load_schema(tmp_path)
        assert result["files"][0]["defaults"] == defaults_data

    def test_raises_on_missing_defaults_file(self, tmp_path):
        """SchemaLoadError if a defaults_path points to a nonexistent file."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/nonexistent.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json)

        with pytest.raises(SchemaLoadError, match="Defaults file not found"):
            load_schema(tmp_path)

    def test_raises_on_malformed_defaults_file(self, tmp_path):
        """SchemaLoadError if defaults file is not valid JSON."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/bad.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json)
        # Create a malformed JSON file
        defaults_path = tmp_path / "defaults" / "bad.json"
        defaults_path.parent.mkdir(parents=True, exist_ok=True)
        defaults_path.write_text("not valid json {{{")

        with pytest.raises(SchemaLoadError, match="Failed to read defaults file"):
            load_schema(tmp_path)


# ---------------------------------------------------------------------------
# Loading migrations
# ---------------------------------------------------------------------------


class TestLoadMigrations:
    def test_loads_numbered_migrations(self, tmp_path):
        """Discovers and loads migrations sorted by numeric prefix."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_add_field.py", '''
version = 1
description = "Add new_field to config"

def apply(configs):
    configs["config.json"]["new_field"] = "hello"
''')

        _create_migration(tmp_path, "002_rename_field.py", '''
version = 2
description = "Rename new_field to renamed_field"

def apply(configs):
    data = configs["config.json"]
    if "new_field" in data:
        data["renamed_field"] = data.pop("new_field")
''')

        result = load_schema(tmp_path)
        assert result is not None
        assert len(result["migrations"]) == 2

        m0 = result["migrations"][0]
        assert m0["version"] == 1
        assert m0["description"] == "Add new_field to config"
        assert callable(m0["apply"])

        m1 = result["migrations"][1]
        assert m1["version"] == 2
        assert m1["description"] == "Rename new_field to renamed_field"
        assert callable(m1["apply"])

    def test_migrations_sorted_by_prefix(self, tmp_path):
        """Migrations are returned in numeric order regardless of filesystem order."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        # Create in reverse order
        _create_migration(tmp_path, "010_last.py", '''
version = 10
description = "Last migration"

def apply(configs):
    pass
''')
        _create_migration(tmp_path, "003_middle.py", '''
version = 3
description = "Middle migration"

def apply(configs):
    pass
''')
        _create_migration(tmp_path, "001_first.py", '''
version = 1
description = "First migration"

def apply(configs):
    pass
''')

        result = load_schema(tmp_path)
        versions = [m["version"] for m in result["migrations"]]
        assert versions == [1, 3, 10]

    def test_migration_apply_is_callable(self, tmp_path):
        """The loaded apply function actually works."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {"value": 0},
        })

        _create_migration(tmp_path, "001_increment.py", '''
version = 1
description = "Increment value"

def apply(configs):
    configs["config.json"]["value"] += 1
''')

        result = load_schema(tmp_path)
        # Actually call the migration function
        test_configs = {"config.json": {"value": 5}}
        result["migrations"][0]["apply"](test_configs)
        assert test_configs["config.json"]["value"] == 6

    def test_ignores_non_matching_files(self, tmp_path):
        """Files without numeric prefix or non-.py are ignored."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_valid.py", '''
version = 1
description = "Valid"

def apply(configs):
    pass
''')
        # These should be ignored
        mig_dir = tmp_path / ".rlsbl" / "migrations"
        (mig_dir / "README.md").write_text("# Migrations")
        (mig_dir / "helper.py").write_text("# no numeric prefix")
        (mig_dir / "__pycache__").mkdir(exist_ok=True)

        result = load_schema(tmp_path)
        assert len(result["migrations"]) == 1
        assert result["migrations"][0]["version"] == 1


# ---------------------------------------------------------------------------
# Malformed migrations
# ---------------------------------------------------------------------------


class TestMalformedMigrations:
    def test_missing_apply_raises(self, tmp_path):
        """SchemaLoadError when migration is missing 'apply' function."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_bad.py", '''
version = 1
description = "Missing apply"
# no apply function defined
''')

        with pytest.raises(SchemaLoadError, match="missing required attributes.*apply"):
            load_schema(tmp_path)

    def test_missing_version_raises(self, tmp_path):
        """SchemaLoadError when migration is missing 'version'."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_no_version.py", '''
description = "No version"

def apply(configs):
    pass
''')

        with pytest.raises(SchemaLoadError, match="missing required attributes.*version"):
            load_schema(tmp_path)

    def test_missing_description_raises(self, tmp_path):
        """SchemaLoadError when migration is missing 'description'."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_no_desc.py", '''
version = 1

def apply(configs):
    pass
''')

        with pytest.raises(SchemaLoadError, match="missing required attributes.*description"):
            load_schema(tmp_path)

    def test_non_callable_apply_raises(self, tmp_path):
        """SchemaLoadError when 'apply' is not callable."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_bad_apply.py", '''
version = 1
description = "Apply is not callable"
apply = "not a function"
''')

        with pytest.raises(SchemaLoadError, match="'apply' must be callable"):
            load_schema(tmp_path)

    def test_non_int_version_raises(self, tmp_path):
        """SchemaLoadError when 'version' is not an int."""
        schema_json = {
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "flat_dict",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": {},
        })

        _create_migration(tmp_path, "001_str_version.py", '''
version = "one"
description = "Version is a string"

def apply(configs):
    pass
''')

        with pytest.raises(SchemaLoadError, match="'version' must be an int"):
            load_schema(tmp_path)


# ---------------------------------------------------------------------------
# Integration: loaded schema works with ConfigMigrator
# ---------------------------------------------------------------------------


class TestIntegrationWithConfigMigrator:
    def test_loaded_schema_is_compatible(self, tmp_path):
        """Schema produced by load_schema works with ConfigMigrator."""
        from rlsbl.lib.config_migrator import ConfigMigrator

        config_defaults = {"theme": "dark", "version": 1}
        schema_json = {
            "schema_version_key": "_sv",
            "files": [
                {
                    "path": "config.json",
                    "defaults_path": "defaults/config.json",
                    "merge_strategy": "deep_recursive",
                },
            ],
        }
        _setup_schema(tmp_path, schema_json, defaults={
            "defaults/config.json": config_defaults,
        })

        _create_migration(tmp_path, "001_add_debug.py", '''
version = 1
description = "Add debug flag"

def apply(configs):
    configs["config.json"]["debug"] = True
''')

        schema = load_schema(tmp_path)
        assert schema is not None

        # Create a config dir to run migrations on
        config_dir = tmp_path / "project"
        config_dir.mkdir()

        migrator = ConfigMigrator(schema)
        result = migrator.run(config_dir)

        assert result["config.json"] is True
        data = json.loads((config_dir / "config.json").read_text())
        assert data["theme"] == "dark"
        assert data["debug"] is True
        assert data["_sv"] == 1
