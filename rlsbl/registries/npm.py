"""npm registry adapter for rlsbl."""

import json
import os
import re

NAME = "npm"


def read_version(dir_path):
    """Read the version from package.json in the given directory."""
    pkg_path = os.path.join(dir_path, "package.json")
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)
    if "version" not in pkg:
        raise ValueError(f"No 'version' field in {pkg_path}")
    return pkg["version"]


def write_version(dir_path, version):
    """Write a new version to package.json, preserving formatting."""
    pkg_path = os.path.join(dir_path, "package.json")
    with open(pkg_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Detect indent: look for the first indented line
    indent_match = re.search(r'^( +|\t+)"', raw, re.MULTILINE)
    indent = indent_match.group(1) if indent_match else "  "

    pkg = json.loads(raw)
    pkg["version"] = version

    # Preserve trailing newline if present
    trailing_newline = "\n" if raw.endswith("\n") else ""
    output = json.dumps(pkg, indent=indent) + trailing_newline
    # Atomic write: write to temp file, then rename
    tmp_path = pkg_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(output)
    os.replace(tmp_path, pkg_path)


def get_version_file():
    """Returns the filename that holds the version for this registry."""
    return "package.json"


def get_template_dir():
    """Returns path to the npm-specific template directory."""
    return os.path.join(os.path.dirname(__file__), "..", "..", "templates", "npm")


def get_shared_template_dir():
    """Returns path to the shared template directory."""
    return os.path.join(os.path.dirname(__file__), "..", "..", "templates", "shared")


def get_template_vars(dir_path):
    """Extract template variables from the target project's package.json."""
    pkg_path = os.path.join(dir_path, "package.json")
    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    # Derive binCommand from the bin field (first key if object, or package name)
    bin_command = pkg.get("name", "")
    bin_field = pkg.get("bin")
    if isinstance(bin_field, dict) and bin_field:
        bin_command = next(iter(bin_field))
    elif isinstance(bin_field, str):
        bin_command = pkg.get("name", "")

    # Derive repoName from repository field
    repo_name = ""
    repository = pkg.get("repository")
    if repository:
        url = repository if isinstance(repository, str) else (repository.get("url") or "")
        match = re.search(r"github\.com[/:]([^/]+/[^/.]+)", url)
        if match:
            repo_name = match.group(1)

    return {
        "name": pkg.get("name", ""),
        "version": pkg.get("version", "0.1.0"),
        "binCommand": bin_command,
        "author": pkg.get("author", ""),
        "repoName": repo_name,
    }


def get_template_mappings():
    """Returns npm-specific template mappings (template file -> target path)."""
    return [
        {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
        {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
    ]


def get_shared_template_mappings():
    """Returns shared template mappings."""
    return [
        {"template": "CHANGELOG.md.tpl", "target": "CHANGELOG.md"},
        {"template": "gitignore.tpl", "target": ".gitignore"},
        {"template": "LICENSE.tpl", "target": "LICENSE"},
        {"template": "CLAUDE.md.tpl", "target": "CLAUDE.md"},
        {"template": "check-prs.sh.tpl", "target": "scripts/check-prs.sh"},
        {"template": "record-gif.sh.tpl", "target": "scripts/record-gif.sh"},
        {"template": "pre-release.sh.tpl", "target": "scripts/pre-release.sh"},
        {"template": "post-release.sh.tpl", "target": "scripts/post-release.sh"},
        {"template": "pre-push-hook.sh.tpl", "target": "scripts/pre-push-hook.sh"},
        {"template": "claude-settings.json.tpl", "target": ".claude/settings.json"},
    ]


def check_project_exists(dir_path):
    """Returns True if a package.json exists in the given directory."""
    return os.path.exists(os.path.join(dir_path, "package.json"))


def get_project_init_hint():
    """Hint for users who haven't initialized their project yet."""
    return 'Run "npm init" first'
