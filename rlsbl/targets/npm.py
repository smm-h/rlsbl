"""npm release target for rlsbl."""

import json
import os
import re

from .base import BaseTarget


class NpmTarget(BaseTarget):
    """Release target for npm/Node.js projects (package.json)."""

    @property
    def name(self):
        return "npm"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "package.json"))

    def read_version(self, dir_path):
        """Read the version from package.json in the given directory."""
        pkg_path = os.path.join(dir_path, "package.json")
        with open(pkg_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        if "version" not in pkg:
            raise ValueError(f"No 'version' field in {pkg_path}")
        return pkg["version"]

    def write_version(self, dir_path, version):
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
        output = json.dumps(pkg, indent=indent, ensure_ascii=False) + trailing_newline
        # Atomic write: write to temp file, then rename
        tmp_path = pkg_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(output)
        os.replace(tmp_path, pkg_path)

    def version_file(self):
        return "package.json"

    def tag_format(self, name, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "npm"
        )

    def template_vars(self, dir_path):
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
            "publishSetup": "Requires NPM_TOKEN secret on GitHub (Settings > Secrets > Actions)",
        }

    def template_mappings(self):
        return [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
        ]

    def check_project_exists(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "package.json"))

    def get_project_init_hint(self):
        return 'Run "npm init" first'
