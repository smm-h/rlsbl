"""Register command: print the plugin registry entry for this repo."""

import json
import sys


def run_cmd(registry, args, flags):
    """Print the registry entry JSON for the current plugin repo.

    Reads plugin.json and git remote to produce a snippet suitable for
    inclusion in a central plugins.json registry file.
    """
    from ..targets.codehome import generate_registry_entry

    dir_path = flags.get("scope", ".")

    try:
        entry = generate_registry_entry(dir_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(entry, indent=2))
