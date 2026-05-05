"""Go release target for rlsbl.

Go projects use a VERSION file as the source of truth for rlsbl. GoReleaser
handles the build/publish step triggered by the GitHub Release that rlsbl creates.
"""

import os
import re

from .base import BaseTarget
from ..utils import run

VERSION_FILE = "VERSION"


class GoTarget(BaseTarget):
    """Release target for Go projects (go.mod + VERSION file)."""

    @property
    def name(self):
        return "go"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "go.mod"))

    def read_version(self, dir_path):
        """Read version from the VERSION file."""
        version_path = os.path.join(dir_path, VERSION_FILE)
        if not os.path.exists(version_path):
            raise FileNotFoundError(
                f"No {VERSION_FILE} file found. Run 'rlsbl scaffold' first."
            )
        with open(version_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def write_version(self, dir_path, version):
        """Write the new version to the VERSION file."""
        version_path = os.path.join(dir_path, VERSION_FILE)
        tmp_path = version_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(version + "\n")
        os.replace(tmp_path, version_path)

    def version_file(self):
        return VERSION_FILE

    def tag_format(self, name, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "go"
        )

    def template_vars(self, dir_path):
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
            version = self.read_version(dir_path)
        except FileNotFoundError:
            version = "0.0.0"

        return {
            "name": short_name,
            "modulePath": name,
            "version": version,
            "author": author,
            "repoName": repo_name,
            "binCommand": short_name,
            "publishSetup": "GoReleaser handles binary publishing via GitHub Actions (no secrets needed)",
        }

    def template_mappings(self):
        return [
            {"template": "VERSION.tpl", "target": "VERSION"},
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
            {"template": "goreleaser.yml.tpl", "target": ".goreleaser.yml"},
        ]

    def check_project_exists(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "go.mod"))

    def get_project_init_hint(self):
        return 'Run "go mod init <module-path>" first'
