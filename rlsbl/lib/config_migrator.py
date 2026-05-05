"""Generic config file migration engine.

Supports merging defaults into existing config files and running versioned
migrations that mutate config values. All writes are atomic (tmp + rename).

Designed to be reusable across projects that need schema evolution for
JSON config files.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Callable


class ConfigMigrator:
    """Generic config file migration engine.

    Supports three merge strategies:
    - deep_recursive: add missing keys recursively (for nested dicts)
    - flat_dict: add missing top-level keys only
    - list_by_key: match list items by a key field, add missing attrs

    Usage:
        schema = {
            "files": [
                {"path": "config.json", "defaults": {...}, "merge_strategy": "flat_dict"},
                {"path": "theme.json", "defaults": {...}, "merge_strategy": "deep_recursive"},
                {"path": "segments.json", "defaults": [...], "merge_strategy": "list_by_key", "match_field": "key"},
            ],
            "schema_version_key": "_schema_version",
            "migrations": [
                {"version": 1, "description": "...", "apply": some_callable},
            ],
        }
        migrator = ConfigMigrator(schema)
        changes = migrator.run(Path("/path/to/config/dir"))
    """

    def __init__(self, schema: dict[str, Any]) -> None:
        """Initialize with a schema describing files, defaults, and migrations.

        Args:
            schema: dict with:
              - files: list of {path, defaults, merge_strategy, match_field?}
              - schema_version_key: str (default "_schema_version")
              - migrations: list of {version: int, description: str, apply: callable}
                where apply receives a dict of all loaded configs keyed by filename
                and mutates in place.
        """
        self.files = schema["files"]
        self.schema_version_key = schema.get("schema_version_key", "_schema_version")
        self.migrations = sorted(
            schema.get("migrations", []), key=lambda m: m["version"]
        )

    def run(self, base_dir: Path) -> dict[str, bool]:
        """Run migrations on all files in base_dir.

        Returns dict mapping filename -> whether it was written (changed).
        """
        base_dir = Path(base_dir)
        # Load all config files
        configs: dict[str, Any] = {}
        newly_created: set[str] = set()
        for file_spec in self.files:
            path = base_dir / file_spec["path"]
            data = self._load_json(path)
            if data is None:
                # File missing or malformed: start from defaults
                data = copy.deepcopy(file_spec["defaults"])
                newly_created.add(file_spec["path"])
            configs[file_spec["path"]] = data

        # Apply merge strategies (add missing defaults)
        merge_changed: dict[str, bool] = {}
        for file_spec in self.files:
            filename = file_spec["path"]
            strategy = file_spec["merge_strategy"]
            defaults = file_spec["defaults"]
            data = configs[filename]

            if strategy == "deep_recursive":
                changed = self.deep_merge_missing(data, defaults)
            elif strategy == "flat_dict":
                changed = self.flat_merge_missing(data, defaults)
            elif strategy == "list_by_key":
                match_field = file_spec["match_field"]
                changed = self.list_merge_by_key(data, defaults, match_field)
            else:
                changed = False

            merge_changed[filename] = changed

        # Apply versioned migrations
        migration_changed = self._apply_migrations(configs, self.schema_version_key)

        # Determine which files actually changed and save them
        result: dict[str, bool] = {}
        for file_spec in self.files:
            filename = file_spec["path"]
            changed = (
                merge_changed.get(filename, False)
                or (filename in migration_changed)
                or (filename in newly_created)
            )
            result[filename] = changed
            if changed:
                path = base_dir / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                self._save_json(path, configs[filename])

        return result

    @staticmethod
    def deep_merge_missing(target: dict, defaults: dict) -> bool:
        """Add missing keys from defaults recursively. Returns True if changed."""
        changed = False
        for key, default_value in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(default_value)
                changed = True
            elif isinstance(target[key], dict) and isinstance(default_value, dict):
                if ConfigMigrator.deep_merge_missing(target[key], default_value):
                    changed = True
        return changed

    @staticmethod
    def flat_merge_missing(target: dict, defaults: dict) -> bool:
        """Add missing top-level keys. Returns True if changed."""
        changed = False
        for key, value in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(value)
                changed = True
        return changed

    @staticmethod
    def list_merge_by_key(
        target_list: list[dict], defaults_list: list[dict], match_field: str
    ) -> bool:
        """For each default item, find match in target by match_field, add missing attrs.

        Only enriches existing items in target_list. Does not add items that the
        user has removed (respects user deletions). Does not overwrite existing attrs.
        """
        target_by_key = {
            item[match_field]: item
            for item in target_list
            if match_field in item
        }
        changed = False
        for default_item in defaults_list:
            key_value = default_item.get(match_field)
            if key_value is None or key_value not in target_by_key:
                # Skip items the user intentionally removed
                continue
            user_item = target_by_key[key_value]
            for attr, value in default_item.items():
                if attr not in user_item:
                    user_item[attr] = copy.deepcopy(value)
                    changed = True
        return changed

    def _apply_migrations(
        self, configs: dict[str, Any], schema_version_key: str
    ) -> set[str]:
        """Apply pending versioned migrations.

        Returns set of filenames that were mutated by migrations.
        The schema version is stored in the first file in the schema's files list.
        """
        if not self.migrations:
            return set()

        # Schema version lives in the first file
        version_file = self.files[0]["path"]
        version_data = configs[version_file]

        # For dict configs, schema version is a key in the dict
        # For list configs, we cannot store schema version inline (caller
        # should ensure version_file is a dict)
        if not isinstance(version_data, dict):
            return set()

        current_version = version_data.get(schema_version_key, 0)
        highest_applied = current_version
        changed_files: set[str] = set()

        for migration in self.migrations:
            if migration["version"] <= current_version:
                continue

            # Snapshot all configs to detect mutations
            snapshots = {
                filename: json.dumps(data, sort_keys=True, default=str)
                for filename, data in configs.items()
            }

            # Apply the migration -- receives all configs keyed by filename
            migration["apply"](configs)

            # Detect which files changed
            for filename, data in configs.items():
                after = json.dumps(data, sort_keys=True, default=str)
                if after != snapshots[filename]:
                    changed_files.add(filename)

            highest_applied = max(highest_applied, migration["version"])

        # Bump schema version if any migration ran
        if highest_applied > current_version:
            version_data[schema_version_key] = highest_applied
            changed_files.add(version_file)

        return changed_files

    @staticmethod
    def _save_json(path: Path, data: Any) -> None:
        """Atomic write: tmp file + rename."""
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        # os.replace is atomic on POSIX and works cross-platform
        os.replace(tmp, path)

    @staticmethod
    def _load_json(path: Path) -> Any | None:
        """Load JSON file, return None on missing/malformed."""
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
