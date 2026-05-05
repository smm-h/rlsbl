"""Target discovery and registry."""

from .npm import NpmTarget
from .pypi import PypiTarget
from .go import GoTarget
from .protocol import ReleaseTarget
from .base import BaseTarget

# Instantiated targets dict (replaces the old module-based REGISTRIES)
TARGETS = {
    "npm": NpmTarget(),
    "pypi": PypiTarget(),
    "go": GoTarget(),
}

# Backward compat alias
REGISTRIES = TARGETS


def detect_targets(dir_path="."):
    """Detect which targets are applicable in the given directory.

    Returns list of target name strings, ordered by priority.
    """
    found = []
    for name, target in TARGETS.items():
        if target.detect(dir_path):
            found.append(name)
    return found
