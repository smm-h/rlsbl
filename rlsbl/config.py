"""Config reading for the tag feature (ecosystem discoverability).

Precedence (highest to lowest):
  1. CLI flag (--no-tag)
  2. Project-level: .rlsbl/config.json
  3. User-level: ~/.rlsbl/config.json
  4. Default: True (tagging enabled)
"""

import json
import os


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


def write_project_config(key, value):
    """Write or update a key in .rlsbl/config.json (creates dir if needed)."""
    os.makedirs(os.path.dirname(_project_config()), exist_ok=True)
    existing = read_json_config(_project_config())
    existing[key] = value
    with open(_project_config(), "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")
