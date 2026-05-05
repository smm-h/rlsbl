"""Load config schema from on-disk declaration files.

Reads .rlsbl/config-schema.json and migration files from .rlsbl/migrations/
to build a schema dict suitable for ConfigMigrator.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any


class SchemaLoadError(Exception):
    """Raised when a schema or migration file is malformed."""


def load_schema(base_dir: str | Path) -> dict[str, Any] | None:
    """Load config schema from .rlsbl/config-schema.json and migration files.

    .rlsbl/config-schema.json format:
    {
        "schema_version_key": "_schema_version",
        "files": [
            {
                "path": "config.json",
                "defaults_path": "defaults/config.json",
                "merge_strategy": "deep_recursive"
            },
            {
                "path": "segments.json",
                "defaults_path": "defaults/segments.json",
                "merge_strategy": "list_by_key",
                "match_field": "key"
            }
        ]
    }

    Migrations live in .rlsbl/migrations/ as numbered Python files:
    - 001_description.py
    - 002_description.py
    Each must define: version (int), description (str), apply(configs: dict) -> None

    Args:
        base_dir: Root directory containing .rlsbl/ folder.

    Returns:
        A schema dict ready for ConfigMigrator, or None if no schema file exists.

    Raises:
        SchemaLoadError: If schema file is malformed, defaults are missing,
            or a migration file lacks required attributes.
    """
    base_dir = Path(base_dir)
    schema_path = base_dir / ".rlsbl" / "config-schema.json"

    if not schema_path.exists():
        return None

    # Load the schema declaration
    try:
        with open(schema_path) as f:
            raw_schema = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SchemaLoadError(f"Failed to read {schema_path}: {e}") from e

    # Build file entries with resolved defaults
    files = _load_file_entries(base_dir, raw_schema.get("files", []))

    # Load migrations
    migrations_dir = base_dir / ".rlsbl" / "migrations"
    migrations = _load_migrations(migrations_dir)

    return {
        "schema_version_key": raw_schema.get("schema_version_key", "_schema_version"),
        "files": files,
        "migrations": migrations,
    }


def _load_file_entries(
    base_dir: Path, file_declarations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve defaults_path references into actual default values.

    Each file declaration has a defaults_path relative to base_dir.
    We load that JSON file and inline the contents as "defaults".
    """
    entries = []
    for decl in file_declarations:
        defaults_path = base_dir / decl["defaults_path"]
        try:
            with open(defaults_path) as f:
                defaults = json.load(f)
        except FileNotFoundError as e:
            raise SchemaLoadError(
                f"Defaults file not found: {defaults_path}"
            ) from e
        except (json.JSONDecodeError, OSError) as e:
            raise SchemaLoadError(
                f"Failed to read defaults file {defaults_path}: {e}"
            ) from e

        entry: dict[str, Any] = {
            "path": decl["path"],
            "defaults": defaults,
            "merge_strategy": decl["merge_strategy"],
        }
        # Optional match_field for list_by_key strategy
        if "match_field" in decl:
            entry["match_field"] = decl["match_field"]

        entries.append(entry)

    return entries


# Pattern for migration filenames: NNN_description.py
_MIGRATION_PATTERN = re.compile(r"^(\d+)_.+\.py$")


def _load_migrations(migrations_dir: Path) -> list[dict[str, Any]]:
    """Discover and load migration files from a directory.

    Migration files must be named with a numeric prefix (e.g. 001_add_field.py)
    and define: version (int), description (str), apply(configs) -> None.
    """
    if not migrations_dir.is_dir():
        return []

    migration_files = []
    for entry in migrations_dir.iterdir():
        match = _MIGRATION_PATTERN.match(entry.name)
        if match and entry.is_file():
            # Sort key is the numeric prefix
            migration_files.append((int(match.group(1)), entry))

    # Sort by numeric prefix
    migration_files.sort(key=lambda x: x[0])

    migrations = []
    for _prefix, filepath in migration_files:
        module = _import_migration(filepath)
        migrations.append({
            "version": module.version,
            "description": module.description,
            "apply": module.apply,
        })

    return migrations


def _import_migration(filepath: Path) -> Any:
    """Dynamically import a migration file and validate its exports.

    Raises SchemaLoadError if required attributes are missing.
    """
    module_name = filepath.stem
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise SchemaLoadError(
            f"Cannot load migration module: {filepath}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    # Validate required attributes
    missing = []
    for attr in ("version", "description", "apply"):
        if not hasattr(module, attr):
            missing.append(attr)

    if missing:
        raise SchemaLoadError(
            f"Migration {filepath.name} missing required attributes: "
            f"{', '.join(missing)}"
        )

    if not callable(module.apply):
        raise SchemaLoadError(
            f"Migration {filepath.name}: 'apply' must be callable"
        )

    if not isinstance(module.version, int):
        raise SchemaLoadError(
            f"Migration {filepath.name}: 'version' must be an int"
        )

    return module
