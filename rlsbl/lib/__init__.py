"""Public API for rlsbl's config migration library.

Exports:
    ConfigMigrator: Generic config file migration engine.
    load_schema: Load schema from .rlsbl/config-schema.json.
    SchemaLoadError: Raised when schema/migration files are malformed.
    migrate: Convenience one-liner to load schema and run migrations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_migrator import ConfigMigrator
from .schema_loader import SchemaLoadError, load_schema


def migrate(base_dir: str | Path = ".") -> dict[str, bool] | None:
    """Load schema from base_dir and run all pending migrations.

    Convenience wrapper for:
        schema = load_schema(base_dir)
        if schema:
            return ConfigMigrator(schema).run(base_dir)
        return None

    Args:
        base_dir: Root directory containing .rlsbl/ folder.

    Returns:
        Dict mapping filename -> whether it was written (changed),
        or None if no schema file exists.

    Raises:
        SchemaLoadError: If schema file is malformed.
    """
    schema = load_schema(base_dir)
    if schema:
        return ConfigMigrator(schema).run(base_dir)
    return None


__all__ = ["ConfigMigrator", "load_schema", "SchemaLoadError", "migrate"]
