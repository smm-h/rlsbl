"""Tests for rlsbl.lib.config_migrator."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rlsbl.lib.config_migrator import ConfigMigrator


# ---------------------------------------------------------------------------
# deep_merge_missing
# ---------------------------------------------------------------------------


class TestDeepMergeMissing:
    def test_adds_missing_top_level_key(self):
        target = {"a": 1}
        defaults = {"a": 99, "b": 2}
        changed = ConfigMigrator.deep_merge_missing(target, defaults)
        assert changed is True
        assert target == {"a": 1, "b": 2}

    def test_does_not_overwrite_existing(self):
        target = {"a": 1, "b": 2}
        defaults = {"a": 99, "b": 100}
        changed = ConfigMigrator.deep_merge_missing(target, defaults)
        assert changed is False
        assert target == {"a": 1, "b": 2}

    def test_recurses_into_nested_dicts(self):
        target = {"outer": {"existing": "yes"}}
        defaults = {"outer": {"existing": "no", "new_key": "added"}}
        changed = ConfigMigrator.deep_merge_missing(target, defaults)
        assert changed is True
        assert target == {"outer": {"existing": "yes", "new_key": "added"}}

    def test_deeply_nested(self):
        target = {"a": {"b": {"c": 1}}}
        defaults = {"a": {"b": {"c": 99, "d": 2}, "e": 3}}
        changed = ConfigMigrator.deep_merge_missing(target, defaults)
        assert changed is True
        assert target == {"a": {"b": {"c": 1, "d": 2}, "e": 3}}

    def test_no_change_returns_false(self):
        target = {"a": {"b": 1}}
        defaults = {"a": {"b": 99}}
        changed = ConfigMigrator.deep_merge_missing(target, defaults)
        assert changed is False

    def test_deep_copies_defaults(self):
        """Ensure added values are deep-copied, not shared references."""
        nested_default = {"inner": [1, 2, 3]}
        target = {}
        defaults = {"key": nested_default}
        ConfigMigrator.deep_merge_missing(target, defaults)
        # Mutating the result should not affect the original default
        target["key"]["inner"].append(4)
        assert nested_default["inner"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# flat_merge_missing
# ---------------------------------------------------------------------------


class TestFlatMergeMissing:
    def test_adds_missing_keys(self):
        target = {"a": 1}
        defaults = {"a": 99, "b": 2, "c": 3}
        changed = ConfigMigrator.flat_merge_missing(target, defaults)
        assert changed is True
        assert target == {"a": 1, "b": 2, "c": 3}

    def test_does_not_overwrite_existing(self):
        target = {"a": 1, "b": 2}
        defaults = {"a": 99, "b": 100}
        changed = ConfigMigrator.flat_merge_missing(target, defaults)
        assert changed is False
        assert target == {"a": 1, "b": 2}

    def test_does_not_recurse(self):
        """flat_merge only adds top-level keys, does not merge nested dicts."""
        target = {"nested": {"x": 1}}
        defaults = {"nested": {"x": 99, "y": 2}}
        changed = ConfigMigrator.flat_merge_missing(target, defaults)
        assert changed is False
        # nested dict is NOT merged -- the existing value is preserved as-is
        assert target == {"nested": {"x": 1}}

    def test_empty_target(self):
        target = {}
        defaults = {"a": 1, "b": 2}
        changed = ConfigMigrator.flat_merge_missing(target, defaults)
        assert changed is True
        assert target == {"a": 1, "b": 2}

    def test_no_change_returns_false(self):
        target = {"a": 1}
        defaults = {"a": 99}
        changed = ConfigMigrator.flat_merge_missing(target, defaults)
        assert changed is False


# ---------------------------------------------------------------------------
# list_merge_by_key
# ---------------------------------------------------------------------------


class TestListMergeByKey:
    def test_adds_missing_attrs(self):
        target = [{"key": "foo", "color": "red"}]
        defaults = [{"key": "foo", "color": "blue", "size": 10}]
        changed = ConfigMigrator.list_merge_by_key(target, defaults, "key")
        assert changed is True
        assert target == [{"key": "foo", "color": "red", "size": 10}]

    def test_does_not_overwrite_existing_attrs(self):
        target = [{"key": "foo", "color": "red", "size": 5}]
        defaults = [{"key": "foo", "color": "blue", "size": 10}]
        changed = ConfigMigrator.list_merge_by_key(target, defaults, "key")
        assert changed is False
        assert target == [{"key": "foo", "color": "red", "size": 5}]

    def test_does_not_add_removed_items(self):
        """Items in defaults but not in target are skipped (user removed them)."""
        target = [{"key": "foo", "color": "red"}]
        defaults = [
            {"key": "foo", "color": "blue", "size": 10},
            {"key": "bar", "color": "green", "size": 20},
        ]
        changed = ConfigMigrator.list_merge_by_key(target, defaults, "key")
        assert changed is True
        # "bar" was NOT added back
        assert len(target) == 1
        assert target[0]["key"] == "foo"
        assert target[0]["size"] == 10

    def test_multiple_items(self):
        target = [
            {"id": "a", "val": 1},
            {"id": "b", "val": 2},
        ]
        defaults = [
            {"id": "a", "val": 99, "new": "x"},
            {"id": "b", "val": 99, "new": "y"},
        ]
        changed = ConfigMigrator.list_merge_by_key(target, defaults, "id")
        assert changed is True
        assert target[0] == {"id": "a", "val": 1, "new": "x"}
        assert target[1] == {"id": "b", "val": 2, "new": "y"}

    def test_empty_target(self):
        target = []
        defaults = [{"key": "foo", "size": 10}]
        changed = ConfigMigrator.list_merge_by_key(target, defaults, "key")
        assert changed is False
        assert target == []


# ---------------------------------------------------------------------------
# _apply_migrations
# ---------------------------------------------------------------------------


class TestApplyMigrations:
    def test_skips_already_applied(self):
        """Migrations at or below current schema_version are skipped."""
        apply_calls = []

        def migration_fn(configs):
            apply_calls.append(True)
            configs["config.json"]["mutated"] = True

        schema = {
            "files": [{"path": "config.json", "defaults": {}, "merge_strategy": "flat_dict"}],
            "migrations": [
                {"version": 1, "description": "test", "apply": migration_fn},
            ],
        }
        migrator = ConfigMigrator(schema)
        configs = {"config.json": {"_schema_version": 1}}
        changed = migrator._apply_migrations(configs, "_schema_version")
        assert changed == set()
        assert apply_calls == []
        assert "mutated" not in configs["config.json"]

    def test_applies_pending_and_bumps_version(self):
        def migration_fn(configs):
            configs["config.json"]["new_field"] = "added"

        schema = {
            "files": [{"path": "config.json", "defaults": {}, "merge_strategy": "flat_dict"}],
            "migrations": [
                {"version": 1, "description": "add field", "apply": migration_fn},
            ],
        }
        migrator = ConfigMigrator(schema)
        configs = {"config.json": {"_schema_version": 0}}
        changed = migrator._apply_migrations(configs, "_schema_version")
        assert "config.json" in changed
        assert configs["config.json"]["_schema_version"] == 1
        assert configs["config.json"]["new_field"] == "added"

    def test_applies_multiple_in_order(self):
        order = []

        def mig1(configs):
            order.append(1)
            configs["config.json"]["step1"] = True

        def mig2(configs):
            order.append(2)
            configs["config.json"]["step2"] = True

        schema = {
            "files": [{"path": "config.json", "defaults": {}, "merge_strategy": "flat_dict"}],
            "migrations": [
                {"version": 2, "description": "second", "apply": mig2},
                {"version": 1, "description": "first", "apply": mig1},
            ],
        }
        migrator = ConfigMigrator(schema)
        configs = {"config.json": {}}
        migrator._apply_migrations(configs, "_schema_version")
        # Should run in version order regardless of list order
        assert order == [1, 2]
        assert configs["config.json"]["_schema_version"] == 2

    def test_detects_changes_in_secondary_files(self):
        def mig(configs):
            configs["other.json"]["touched"] = True

        schema = {
            "files": [
                {"path": "config.json", "defaults": {}, "merge_strategy": "flat_dict"},
                {"path": "other.json", "defaults": {}, "merge_strategy": "flat_dict"},
            ],
            "migrations": [
                {"version": 1, "description": "touch other", "apply": mig},
            ],
        }
        migrator = ConfigMigrator(schema)
        configs = {"config.json": {}, "other.json": {}}
        changed = migrator._apply_migrations(configs, "_schema_version")
        assert "other.json" in changed
        # config.json changed because schema version was bumped
        assert "config.json" in changed


# ---------------------------------------------------------------------------
# Full run() integration
# ---------------------------------------------------------------------------


class TestRun:
    def test_creates_files_from_defaults_when_missing(self, tmp_path):
        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {"theme": "dark", "version": 1},
                    "merge_strategy": "flat_dict",
                },
            ],
            "migrations": [],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["config.json"] is True
        # File should exist with defaults
        data = json.loads((tmp_path / "config.json").read_text())
        assert data == {"theme": "dark", "version": 1}

    def test_merges_missing_keys_into_existing(self, tmp_path):
        # Pre-create a config file with partial data
        (tmp_path / "config.json").write_text(json.dumps({"theme": "light"}))
        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {"theme": "dark", "debug": False},
                    "merge_strategy": "flat_dict",
                },
            ],
            "migrations": [],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["config.json"] is True
        data = json.loads((tmp_path / "config.json").read_text())
        assert data == {"theme": "light", "debug": False}

    def test_no_write_when_nothing_changed(self, tmp_path):
        existing = {"theme": "dark", "debug": False}
        (tmp_path / "config.json").write_text(json.dumps(existing))
        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {"theme": "dark", "debug": False},
                    "merge_strategy": "flat_dict",
                },
            ],
            "migrations": [],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["config.json"] is False

    def test_runs_migrations_after_merge(self, tmp_path):
        (tmp_path / "config.json").write_text(json.dumps({"flag": True}))

        def flip_flag(configs):
            configs["config.json"]["flag"] = False

        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {"flag": True},
                    "merge_strategy": "flat_dict",
                },
            ],
            "migrations": [
                {"version": 1, "description": "flip flag", "apply": flip_flag},
            ],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["config.json"] is True
        data = json.loads((tmp_path / "config.json").read_text())
        assert data["flag"] is False
        assert data["_schema_version"] == 1

    def test_deep_recursive_strategy(self, tmp_path):
        existing = {"ui": {"color": "blue"}}
        (tmp_path / "theme.json").write_text(json.dumps(existing))
        schema = {
            "files": [
                {
                    "path": "theme.json",
                    "defaults": {"ui": {"color": "red", "font_size": 14}, "version": 1},
                    "merge_strategy": "deep_recursive",
                },
            ],
            "migrations": [],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["theme.json"] is True
        data = json.loads((tmp_path / "theme.json").read_text())
        assert data == {"ui": {"color": "blue", "font_size": 14}, "version": 1}

    def test_list_by_key_strategy(self, tmp_path):
        existing = [{"key": "a", "val": 1}, {"key": "b", "val": 2}]
        (tmp_path / "items.json").write_text(json.dumps(existing))
        # Need a dict file first for schema_version storage
        (tmp_path / "config.json").write_text(json.dumps({}))
        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {},
                    "merge_strategy": "flat_dict",
                },
                {
                    "path": "items.json",
                    "defaults": [
                        {"key": "a", "val": 99, "extra": "x"},
                        {"key": "b", "val": 99, "extra": "y"},
                        {"key": "c", "val": 3, "extra": "z"},
                    ],
                    "merge_strategy": "list_by_key",
                    "match_field": "key",
                },
            ],
            "migrations": [],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["items.json"] is True
        data = json.loads((tmp_path / "items.json").read_text())
        assert data == [
            {"key": "a", "val": 1, "extra": "x"},
            {"key": "b", "val": 2, "extra": "y"},
        ]

    def test_multi_file_migration(self, tmp_path):
        (tmp_path / "config.json").write_text(json.dumps({"mode": "old"}))
        (tmp_path / "state.json").write_text(json.dumps({"count": 0}))

        def mig(configs):
            configs["config.json"]["mode"] = "new"
            configs["state.json"]["count"] = 1

        schema = {
            "files": [
                {"path": "config.json", "defaults": {"mode": "old"}, "merge_strategy": "flat_dict"},
                {"path": "state.json", "defaults": {"count": 0}, "merge_strategy": "flat_dict"},
            ],
            "migrations": [
                {"version": 1, "description": "upgrade", "apply": mig},
            ],
        }
        migrator = ConfigMigrator(schema)
        result = migrator.run(tmp_path)
        assert result["config.json"] is True
        assert result["state.json"] is True
        config = json.loads((tmp_path / "config.json").read_text())
        state = json.loads((tmp_path / "state.json").read_text())
        assert config["mode"] == "new"
        assert config["_schema_version"] == 1
        assert state["count"] == 1


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_save_json_creates_file(self, tmp_path):
        path = tmp_path / "out.json"
        ConfigMigrator._save_json(path, {"hello": "world"})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data == {"hello": "world"}

    def test_save_json_no_leftover_tmp(self, tmp_path):
        """After save, no .tmp file should remain."""
        path = tmp_path / "out.json"
        ConfigMigrator._save_json(path, {"x": 1})
        tmp_file = path.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_save_json_overwrites_existing(self, tmp_path):
        path = tmp_path / "out.json"
        path.write_text(json.dumps({"old": True}))
        ConfigMigrator._save_json(path, {"new": True})
        data = json.loads(path.read_text())
        assert data == {"new": True}

    def test_save_json_trailing_newline(self, tmp_path):
        """Output should end with a newline for POSIX compliance."""
        path = tmp_path / "out.json"
        ConfigMigrator._save_json(path, {"a": 1})
        assert path.read_text().endswith("\n")


# ---------------------------------------------------------------------------
# _load_json
# ---------------------------------------------------------------------------


class TestLoadJson:
    def test_loads_valid_json(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text(json.dumps({"key": "value"}))
        result = ConfigMigrator._load_json(path)
        assert result == {"key": "value"}

    def test_returns_none_on_missing(self, tmp_path):
        result = ConfigMigrator._load_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_returns_none_on_malformed(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        result = ConfigMigrator._load_json(path)
        assert result is None

    def test_loads_list(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]))
        result = ConfigMigrator._load_json(path)
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_double_run_is_noop(self, tmp_path):
        """Running twice produces the same result; second run writes nothing."""
        schema = {
            "files": [
                {
                    "path": "config.json",
                    "defaults": {"a": 1, "b": 2},
                    "merge_strategy": "flat_dict",
                },
            ],
            "migrations": [
                {
                    "version": 1,
                    "description": "set c",
                    "apply": lambda configs: configs["config.json"].update({"c": 3}),
                },
            ],
        }
        migrator = ConfigMigrator(schema)

        # First run: creates and migrates
        result1 = migrator.run(tmp_path)
        assert result1["config.json"] is True

        # Second run: nothing to do
        result2 = migrator.run(tmp_path)
        assert result2["config.json"] is False


# ---------------------------------------------------------------------------
# Custom schema_version_key
# ---------------------------------------------------------------------------


class TestCustomSchemaVersionKey:
    def test_uses_custom_key(self, tmp_path):
        (tmp_path / "cfg.json").write_text(json.dumps({}))

        def mig(configs):
            configs["cfg.json"]["migrated"] = True

        schema = {
            "files": [
                {"path": "cfg.json", "defaults": {}, "merge_strategy": "flat_dict"},
            ],
            "schema_version_key": "__version__",
            "migrations": [
                {"version": 1, "description": "test", "apply": mig},
            ],
        }
        migrator = ConfigMigrator(schema)
        migrator.run(tmp_path)
        data = json.loads((tmp_path / "cfg.json").read_text())
        assert data["__version__"] == 1
        assert data["migrated"] is True
        # Default key should not be present
        assert "_schema_version" not in data
