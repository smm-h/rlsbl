"""Go registry adapter for rlsbl.

Go projects use a VERSION file as the source of truth for rlsbl. GoReleaser
handles the build/publish step triggered by the GitHub Release that rlsbl creates.
"""

import os
import re

from ..utils import run

NAME = "go"

VERSION_FILE = "VERSION"


def read_version(dir_path):
    """Read version from the VERSION file."""
    version_path = os.path.join(dir_path, VERSION_FILE)
    if not os.path.exists(version_path):
        raise FileNotFoundError(f"No {VERSION_FILE} file found. Run 'rlsbl scaffold' first.")
    with open(version_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def write_version(dir_path, version):
    """Write the new version to the VERSION file."""
    version_path = os.path.join(dir_path, VERSION_FILE)
    tmp_path = version_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(version + "\n")
    os.replace(tmp_path, version_path)


def get_version_file():
    """Returns the filename that holds the version for this registry."""
    return VERSION_FILE


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

    try:
        version = read_version(dir_path)
    except FileNotFoundError:
        version = "0.0.0"

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
        {"template": "VERSION.tpl", "target": "VERSION"},
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
        {"template": "post-release.sh.tpl", "target": "scripts/post-release.sh"},
        {"template": "pre-push-hook.sh.tpl", "target": "scripts/pre-push-hook.sh"},
    ]


def check_project_exists(dir_path):
    """Returns True if a go.mod exists in the given directory."""
    return os.path.exists(os.path.join(dir_path, "go.mod"))


def get_project_init_hint():
    """Hint for users who haven't initialized their project yet."""
    return 'Run "go mod init <module-path>" first'
