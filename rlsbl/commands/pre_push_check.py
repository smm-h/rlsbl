"""Pre-push-check command: verify CHANGELOG.md has an entry for the current version."""

import json
import os
import re
import sys


def _detect_version():
    """Detect project type and read the current version.

    Returns (version_string, project_type) or (None, None) if undetectable.
    """
    if os.path.exists("go.mod"):
        # Go projects store version in a VERSION file
        version_path = "VERSION"
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version, "go"
        return None, None

    if os.path.exists("package.json"):
        try:
            with open("package.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version", "")
            if version:
                return version, "npm"
        except Exception:
            pass
        return None, None

    if os.path.exists("pyproject.toml"):
        try:
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version", "")
            if version:
                return version, "pypi"
        except Exception:
            pass
        return None, None

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
