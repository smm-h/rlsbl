"""Pre-push-check command: verify CHANGELOG.md has an entry for the current version."""

import os
import re
import sys

from ..registries import REGISTRIES


def _detect_version():
    """Detect version using registry adapters.

    Returns (version_string, registry_name) or (None, None) if undetectable.
    """
    for name in ("go", "npm", "pypi"):
        reg = REGISTRIES[name]
        if reg.check_project_exists("."):
            return reg.read_version("."), name
    return None, None


def run_cmd(registry, args, flags):
    """Check that CHANGELOG.md has an entry for the current project version.

    Exits 1 if no changelog entry is found; exits 0 silently on success.
    """
    version, _project_type = _detect_version()
    if not version:
        # Cannot detect version -- nothing to check
        sys.exit(0)

    if not os.path.exists("CHANGELOG.md"):
        # No changelog file -- nothing to check
        sys.exit(0)

    with open("CHANGELOG.md", "r", encoding="utf-8") as f:
        content = f.read()

    # Look for a heading like "## <version>"
    pattern = re.compile(r"^## " + re.escape(version) + r"\s*$", re.MULTILINE)
    if pattern.search(content):
        sys.exit(0)

    print(f"Error: CHANGELOG.md has no entry for version {version}.", file=sys.stderr)
    print(f"Add a '## {version}' section before pushing.", file=sys.stderr)
    sys.exit(1)
