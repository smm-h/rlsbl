"""Target discovery and registry."""

import os
import sys

from .npm import NpmTarget
from .pypi import PypiTarget
from .go import GoTarget
from .docs import DocsTarget
from .protocol import ReleaseTarget
from .base import BaseTarget
from ..config import read_json_config

# Instantiated targets dict (replaces the old module-based REGISTRIES)
TARGETS = {
    "npm": NpmTarget(),
    "pypi": PypiTarget(),
    "go": GoTarget(),
    "docs": DocsTarget(),
}


def detect_targets(dir_path="."):
    """Detect which targets are applicable in the given directory.

    If .rlsbl/config.json has a "targets" array, use that (opt-in config).
    Otherwise, fall back to auto-detection based on project file presence.

    Returns list of target name strings.
    """
    config_path = os.path.join(dir_path, ".rlsbl", "config.json")
    config = read_json_config(config_path)
    configured = config.get("targets")

    if configured is not None and isinstance(configured, list):
        # Config-declared targets take precedence
        result = []
        for name in configured:
            if name in TARGETS:
                result.append(name)
            else:
                print(f"Warning: unknown target '{name}' in .rlsbl/config.json, skipping",
                      file=sys.stderr)
        return result

    # Fallback: auto-detect from project files
    found = []
    for name, target in TARGETS.items():
        if target.detect(dir_path):
            found.append(name)
    return found
