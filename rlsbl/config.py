"""Project configuration loading with layered precedence: CLI flags override project-level .rlsbl/config.json which overrides user-level defaults."""

import json
import os
import sys


def load_env_file(path):
    """Load KEY=VALUE pairs from a file into os.environ.

    Supports ~ expansion. Ignores comments (#) and blank lines.
    Strips surrounding quotes from values.
    """
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(f"Warning: env file not found: {path}", file=sys.stderr)
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ[key] = value


def _project_config():
    """Resolve project config path at call time (respects cwd changes)."""
    return os.path.join(".rlsbl", "config.json")

USER_CONFIG = os.path.expanduser("~/.rlsbl/config.json")


def read_json_config(path):
    """Safely read a JSON file, returning {} on missing or malformed."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def should_tag(flags):
    """Returns True if tagging is enabled, checking flag > project > user > default."""
    # CLI flag takes highest precedence
    if flags.get("no-tag"):
        return False

    # Project-level config
    project = read_json_config(_project_config())
    if "tag" in project:
        return bool(project["tag"])

    # User-level config
    user = read_json_config(USER_CONFIG)
    if "tag" in user:
        return bool(user["tag"])

    # Default: tagging enabled
    return True


def read_project_config():
    """Read .rlsbl/config.json, return dict or empty dict if missing/malformed."""
    return read_json_config(_project_config())


def read_deploy_config():
    """Read and validate deploy targets from project config. Returns (targets, errors)."""
    from rlsbl.deploy import validate_deploy_config

    config = read_project_config()
    targets = config.get("deploy", [])
    if not targets:
        return [], []
    errors = validate_deploy_config(targets)
    return targets, errors


def write_project_config(key, value):
    """Write or update a key in .rlsbl/config.json (creates dir if needed)."""
    os.makedirs(os.path.dirname(_project_config()), exist_ok=True)
    existing = read_json_config(_project_config())
    existing[key] = value
    with open(_project_config(), "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")
