"""Go release target for rlsbl.

Go projects use a VERSION file as the source of truth for rlsbl. GoReleaser
handles the build/publish step triggered by the GitHub Release that rlsbl creates.

Libraries (no `package main`) skip GoReleaser scaffolding and rely on tagged
releases being available via `go get`. After each release, the Go module proxy
is notified so the new version is immediately discoverable.
"""

import glob
import os
import re
import shutil
import subprocess

from .base import BaseTarget
from ..utils import run

VERSION_FILE = "VERSION"

_GO_VERSION_RE = re.compile(r"^go\s+(\d+\.\d+(?:\.\d+)?)", re.MULTILINE)


class GoTarget(BaseTarget):
    """Release target for Go projects (go.mod + VERSION file)."""

    @property
    def name(self):
        return "go"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "go.mod"))

    def read_name(self, dir_path):
        """Read the last segment of the module path from go.mod."""
        module_path = self._read_module_path(dir_path)
        if not module_path:
            return None
        return module_path.rsplit("/", 1)[-1] if "/" in module_path else module_path

    def read_metadata(self, dir_path):
        """Go modules have no license/description in go.mod."""
        return {}

    def _read_module_path(self, dir_path):
        """Extract the module path from go.mod, or empty string if unavailable."""
        mod_path = os.path.join(dir_path, "go.mod")
        if not os.path.exists(mod_path):
            return ""
        with open(mod_path, encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
        return match.group(1) if match else ""

    def _is_library(self, dir_path):
        """Return True if the project has no `package main` in root .go files."""
        for go_file in glob.glob(os.path.join(dir_path, "*.go")):
            with open(go_file, encoding="utf-8") as f:
                for line in f:
                    if re.match(r"^package\s+main\b", line):
                        return False
        return True

    def _has_root_main(self, dir_path):
        """Return True if there's a main.go at the project root with `package main`."""
        main_go = os.path.join(dir_path, "main.go")
        if not os.path.exists(main_go):
            return False
        with open(main_go, encoding="utf-8") as f:
            first_line = f.readline()
        return bool(re.match(r"^package\s+main\b", first_line))

    def _has_version_var(self, dir_path):
        """Return True if any root-level .go file declares a Version variable."""
        for go_file in glob.glob(os.path.join(dir_path, "*.go")):
            with open(go_file, encoding="utf-8") as f:
                for line in f:
                    if re.match(r"^var\s+[Vv]ersion\b", line):
                        return True
        return False

    def _has_cmd_main(self, dir_path):
        """Return True if there's a single cmd/*/main.go with `package main`.

        Returns False if there are multiple cmd/ subdirectories (multi-binary
        repos where cmd/ is the correct layout) or no cmd/ entries at all.
        """
        matches = glob.glob(os.path.join(dir_path, "cmd", "*", "main.go"))
        if not matches:
            return False
        # Count distinct cmd/ subdirectories (not just main.go files)
        cmd_dirs = set(os.path.dirname(m) for m in matches)
        if len(cmd_dirs) > 1:
            return False
        # Verify the single match has `package main`
        with open(matches[0], encoding="utf-8") as f:
            first_line = f.readline()
        return bool(re.match(r"^package\s+main\b", first_line))

    def publish(self, dir_path, version):
        """Notify the Go module proxy so the new version is immediately available."""
        module_path = self._read_module_path(dir_path)
        if not module_path:
            print("Warning: could not read module path from go.mod, skipping proxy notification")
            return

        if not shutil.which("go"):
            print("Warning: 'go' not found on PATH, skipping proxy notification")
            return

        ref = f"{module_path}@v{version}"
        env = {**os.environ, "GOPROXY": "proxy.golang.org"}
        try:
            run("go", ["list", "-m", ref], env=env)
            print(f"Notified Go module proxy: {ref}")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"Warning: proxy notification failed for {ref}: {exc}")

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

    def tag_format(self, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "go"
        )

    def template_vars(self, dir_path):
        """Extract template variables from go.mod."""
        name = self._read_module_path(dir_path)

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

        if self._is_library(dir_path):
            publish_setup = "Go library -- no publish step needed. Tagged releases are available via go get."
        else:
            publish_setup = "GoReleaser handles binary publishing via GitHub Actions (no secrets needed)"

        # Determine the main package path for goreleaser
        if self._has_root_main(dir_path):
            goreleaser_main = "."
        elif self._has_cmd_main(dir_path):
            matches = glob.glob(os.path.join(dir_path, "cmd", "*", "main.go"))
            cmd_name = os.path.basename(os.path.dirname(matches[0]))
            goreleaser_main = f"./cmd/{cmd_name}"
        else:
            goreleaser_main = "."

        result = {
            "name": short_name,
            "modulePath": name,
            "version": version,
            "author": author,
            "repoName": repo_name,
            "binCommand": short_name,
            "publishSetup": publish_setup,
            "goreleaserMain": goreleaser_main,
        }

        # Extract minimum required Go version from go.mod
        mod_path = os.path.join(dir_path, "go.mod")
        if os.path.exists(mod_path):
            with open(mod_path, encoding="utf-8") as f:
                mod_content = f.read()
            m = _GO_VERSION_RE.search(mod_content)
            if m:
                result["minRequiredGo"] = m.group(1)

        return result

    def template_mappings(self):
        mappings = [
            {"template": "VERSION.tpl", "target": "VERSION"},
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
        ]
        if not self._is_library("."):
            mappings.extend([
                {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
                {"template": "goreleaser.yml.tpl", "target": ".goreleaser.yml"},
            ])
            if not self._has_version_var("."):
                mappings.append(
                    {"template": "version.go.tpl", "target": "version.go"},
                )
        return mappings

    def check_project_exists(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "go.mod"))

    def get_project_init_hint(self):
        return 'Run "go mod init <module-path>" first'
