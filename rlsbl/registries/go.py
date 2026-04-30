"""Go registry adapter for rlsbl.

Go modules are versioned by git tags, not version files. GoReleaser handles
the build/publish step. rlsbl's role: changelog validation, tagging, GitHub
Release creation.
"""

import os
import re

from ..utils import run

NAME = "go"


def read_version(dir_path):
    """Read version from the latest git tag.

    Go modules have no version file -- the version IS the git tag.
    Returns "0.0.0" if no tags exist yet.
    """
    try:
        tag = run("git", ["describe", "--tags", "--abbrev=0"])
        return tag.lstrip("v")
    except Exception:
        return "0.0.0"


def write_version(dir_path, version):
    """No-op: Go versions are git tags, not file fields."""
    pass


def get_version_file():
    """Go has no version file -- version is the git tag."""
    return None


def get_template_dir():
    """Returns path to the go-specific template directory."""
    return os.path.join(os.path.dirname(__file__), "..", "..", "templates", "go")


def get_shared_template_dir():
    """Returns path to the shared template directory."""
    return os.path.join(os.path.dirname(__file__), "..", "..", "templates", "shared")


def get_template_vars(dir_path):
    """Extract template variables from go.mod."""
    mod_path = os.path.join(dir_path, "go.mod")
    name = ""
    if os.path.exists(mod_path):
        with open(mod_path) as f:
            content = f.read()
        match = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
        if match:
            name = match.group(1)

    # Derive short name from module path (last segment)
    short_name = name.rsplit("/", 1)[-1] if "/" in name else name

    # Derive repo name from module path (e.g. "github.com/user/repo")
    repo_name = ""
    repo_match = re.search(r"github\.com/([^/\s]+/[^/\s]+)", name)
    if repo_match:
        repo_name = repo_match.group(1)

    # Author from git config
    author = ""
    try:
        author = run("git", ["config", "user.name"])
    except Exception:
        pass

    version = read_version(dir_path)

    return {
        "name": short_name,
        "modulePath": name,
        "version": version,
        "author": author,
        "repoName": repo_name,
        "binCommand": short_name,
    }


def get_template_mappings():
    """Returns go-specific template mappings (template file -> target path)."""
    return [
        {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
        {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
        {"template": "goreleaser.yml.tpl", "target": ".goreleaser.yml"},
    ]


def get_shared_template_mappings():
    """Returns shared template mappings."""
    return [
        {"template": "CHANGELOG.md.tpl", "target": "CHANGELOG.md"},
        {"template": "gitignore.tpl", "target": ".gitignore"},
        {"template": "LICENSE.tpl", "target": "LICENSE"},
        {"template": "CLAUDE.md.tpl", "target": "CLAUDE.md"},
        {"template": "check-prs.sh.tpl", "target": "scripts/check-prs.sh"},
        {"template": "claude-settings.json.tpl", "target": ".claude/settings.json"},
        {"template": "record-gif.sh.tpl", "target": "scripts/record-gif.sh"},
        {"template": "pre-release.sh.tpl", "target": "scripts/pre-release.sh"},
        {"template": "pre-push-hook.sh.tpl", "target": "scripts/pre-push-hook.sh"},
    ]


def check_project_exists(dir_path):
    """Returns True if a go.mod exists in the given directory."""
    return os.path.exists(os.path.join(dir_path, "go.mod"))


def get_project_init_hint():
    """Hint for users who haven't initialized their project yet."""
    return 'Run "go mod init <module-path>" first'
