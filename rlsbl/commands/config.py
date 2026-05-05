"""Config command: show resolved project configuration and manage config migrations."""

import json
import os
import sys
from pathlib import Path

from ..config import _project_config, USER_CONFIG, read_json_config, should_tag
from ..registries import REGISTRIES


def run_cmd(registry, args, flags):
    """Dispatch to subcommand or show config if no subcommand given."""
    if not args:
        _show_config(registry, flags)
        return

    subcommand = args[0]
    if subcommand == "init":
        _cmd_init(flags)
    elif subcommand == "migrate":
        _cmd_migrate(flags)
    elif subcommand == "status":
        _cmd_status(flags)
    else:
        print(f"Error: unknown config subcommand '{subcommand}'.", file=sys.stderr)
        print("Available: init, migrate, status", file=sys.stderr)
        sys.exit(1)


def _cmd_init(flags):
    """Scaffold config migration infrastructure."""
    base_dir = Path(".")
    created = []

    # Create .rlsbl/config-schema.json
    schema_path = base_dir / ".rlsbl" / "config-schema.json"
    if schema_path.exists():
        print(f"Already exists: {schema_path}")
    else:
        schema_path.parent.mkdir(parents=True, exist_ok=True)
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
        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        created.append(str(schema_path))

    # Create defaults/ directory
    defaults_dir = base_dir / "defaults"
    defaults_dir.mkdir(parents=True, exist_ok=True)

    # Create defaults/config.json
    defaults_config = defaults_dir / "config.json"
    if defaults_config.exists():
        print(f"Already exists: {defaults_config}")
    else:
        with open(defaults_config, "w") as f:
            json.dump({"_schema_version": 0}, f, indent=2)
            f.write("\n")
        created.append(str(defaults_config))

    # Create .rlsbl/migrations/ directory
    migrations_dir = base_dir / ".rlsbl" / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    if not any(migrations_dir.iterdir()):
        created.append(str(migrations_dir) + "/")

    if created:
        print("Created:")
        for path in created:
            print(f"  {path}")
    else:
        print("Config migration infrastructure already exists.")

    print("\nNext steps:")
    print("  1. Edit .rlsbl/config-schema.json to define your config files")
    print("  2. Edit defaults/config.json with your default values")
    print("  3. Add migrations in .rlsbl/migrations/ (e.g. 001_add_field.py)")
    print("  4. Run 'rlsbl config migrate' to apply")


def _cmd_migrate(flags):
    """Run pending config migrations."""
    from ..lib.schema_loader import load_schema
    from ..lib.config_migrator import ConfigMigrator

    dry_run = flags.get("dry-run", False)

    schema = load_schema(".")
    if schema is None:
        print("No config schema found. Run 'rlsbl config init' first.", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("Dry run: checking pending migrations...\n")
        # Show what would happen without writing
        migrator = ConfigMigrator(schema)
        base_dir = Path(".")
        # Report file status
        for file_spec in schema["files"]:
            path = base_dir / file_spec["path"]
            if path.exists():
                print(f"  {file_spec['path']}: exists (would merge defaults)")
            else:
                print(f"  {file_spec['path']}: missing (would create from defaults)")
        # Report pending migrations
        migrations = schema.get("migrations", [])
        if migrations:
            # Determine current version from first file
            first_file = base_dir / schema["files"][0]["path"]
            current_version = 0
            if first_file.exists():
                try:
                    with open(first_file) as f:
                        data = json.load(f)
                    version_key = schema.get("schema_version_key", "_schema_version")
                    current_version = data.get(version_key, 0)
                except (json.JSONDecodeError, OSError):
                    pass
            pending = [m for m in migrations if m["version"] > current_version]
            if pending:
                print(f"\n  Pending migrations ({len(pending)}):")
                for m in pending:
                    print(f"    v{m['version']}: {m['description']}")
            else:
                print("\n  No pending migrations.")
        else:
            print("\n  No migrations defined.")
        return

    # Actually run migrations
    migrator = ConfigMigrator(schema)
    results = migrator.run(Path("."))

    # Report results
    created = [f for f, changed in results.items() if changed]
    unchanged = [f for f, changed in results.items() if not changed]

    if created:
        print("Updated/created:")
        for f in created:
            print(f"  {f}")
    if unchanged:
        print("Unchanged:")
        for f in unchanged:
            print(f"  {f}")

    # Report migrations applied
    migrations = schema.get("migrations", [])
    if migrations:
        print(f"\nMigrations: {len(migrations)} defined")


def _cmd_status(flags):
    """Show config migration status."""
    from ..lib.schema_loader import load_schema

    schema = load_schema(".")
    if schema is None:
        print("No config schema found. Run 'rlsbl config init' first.", file=sys.stderr)
        sys.exit(1)

    base_dir = Path(".")
    files = schema["files"]
    version_key = schema.get("schema_version_key", "_schema_version")

    print(f"Managed files: {len(files)}")

    # Current schema version from the first file
    current_version = 0
    first_file_path = base_dir / files[0]["path"]
    if first_file_path.exists():
        try:
            with open(first_file_path) as f:
                data = json.load(f)
            current_version = data.get(version_key, 0)
        except (json.JSONDecodeError, OSError):
            pass

    print(f"Schema version: {current_version}")

    # Pending migrations
    migrations = schema.get("migrations", [])
    pending = [m for m in migrations if m["version"] > current_version]
    print(f"Pending migrations: {len(pending)}")

    # File listing
    print("\nFiles:")
    for file_spec in files:
        path = base_dir / file_spec["path"]
        exists = path.exists()
        status = "exists" if exists else "missing"
        print(f"  {file_spec['path']}: {status}")


def _show_config(registry, flags):
    """Show resolved project configuration (original behavior)."""
    print("Detected registries:")
    for name, reg in REGISTRIES.items():
        if reg.check_project_exists("."):
            version = reg.read_version(".")
            vfile = reg.get_version_file() or "git tag"
            print(f"  {name}: {vfile} (v{version})")
        else:
            print(f"  {name}: not found")

    print("\nScaffolding:")
    rlsbl_dir = os.path.join(".", ".rlsbl")
    if os.path.isdir(rlsbl_dir):
        version_file = os.path.join(rlsbl_dir, "version")
        if os.path.exists(version_file):
            with open(version_file) as f:
                scaffold_ver = f.read().strip()
            print(f"  Version marker: {scaffold_ver}")
        hashes_file = os.path.join(rlsbl_dir, "hashes.json")
        if os.path.exists(hashes_file):
            with open(hashes_file) as f:
                hashes = json.load(f)
            print(f"  Tracked files: {len(hashes)}")
            for path in sorted(hashes):
                print(f"    {path}")
    else:
        print("  Not scaffolded (run 'rlsbl scaffold')")

    print("\nWorkflows:")
    for wf in ["ci.yml", "publish.yml", "workflow.yml"]:
        path = os.path.join(".github", "workflows", wf)
        print(f"  {wf}: {'yes' if os.path.exists(path) else 'no'}")

    print("\nHooks:")
    pre_release = os.path.join(".rlsbl", "hooks", "pre-release.sh")
    print(f"  pre-release.sh: {'yes' if os.path.exists(pre_release) else 'no'}")
    post_release = os.path.join(".rlsbl", "hooks", "post-release.sh")
    print(f"  post-release.sh: {'yes' if os.path.exists(post_release) else 'no'}")
    pre_push = os.path.join(".git", "hooks", "pre-push")
    print(f"  pre-push hook: {'installed' if os.path.exists(pre_push) else 'not installed'}")

    print("\nEcosystem tagging:")
    enabled = should_tag(flags)
    # Determine why it's enabled/disabled
    project_cfg = read_json_config(_project_config())
    user_cfg = read_json_config(USER_CONFIG)
    if flags.get("no-tag"):
        source = "CLI flag"
    elif "tag" in project_cfg:
        source = f"project config ({_project_config()})"
    elif "tag" in user_cfg:
        source = f"user config ({USER_CONFIG})"
    else:
        source = "default"
    print(f"  Status: {'enabled' if enabled else 'disabled'} ({source})")

    print("\nFiles:")
    for f in ["CHANGELOG.md", "LICENSE", ".gitignore", "CLAUDE.md"]:
        print(f"  {f}: {'yes' if os.path.exists(f) else 'no'}")
