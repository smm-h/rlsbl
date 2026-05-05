"""PyPI release target for rlsbl."""

import os
import re
import tomllib

from .base import BaseTarget
from ..utils import run


class PypiTarget(BaseTarget):
    """Release target for Python projects (pyproject.toml)."""

    @property
    def name(self):
        return "pypi"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "pyproject.toml"))

    def read_version(self, dir_path):
        """Read the version from pyproject.toml in the given directory."""
        toml_path = os.path.join(dir_path, "pyproject.toml")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        try:
            return data["project"]["version"]
        except KeyError:
            raise ValueError(f"No [project].version in {toml_path}")

    def write_version(self, dir_path, version):
        """Write a new version to pyproject.toml using regex replacement.

        tomllib is read-only (no stdlib TOML writer), so we use a regex to
        replace the version string within the [project] section only,
        preserving all other formatting.
        """
        toml_path = os.path.join(dir_path, "pyproject.toml")
        with open(toml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find [project] section boundaries to avoid matching version keys
        # in other sections (e.g. [tool.something])
        project_match = re.search(r"^\[project\]\s*$", content, re.MULTILINE)
        if not project_match:
            raise ValueError("No [project] section found in pyproject.toml")

        section_start = project_match.end()
        # Find next top-level section header or EOF
        next_section = re.search(r"^\[", content[section_start:], re.MULTILINE)
        section_end = section_start + next_section.start() if next_section else len(content)

        # Replace version only within [project] section
        section = content[section_start:section_end]
        updated_section = re.sub(
            r'^(version\s*=\s*)"[^"]+"',
            rf'\g<1>"{version}"',
            section,
            count=1,
            flags=re.MULTILINE,
        )
        updated = content[:section_start] + updated_section + content[section_end:]

        # Atomic write: write to temp file, then rename
        tmp_path = toml_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_path, toml_path)

    def version_file(self):
        return "pyproject.toml"

    def tag_format(self, name, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "pypi"
        )

    def template_vars(self, dir_path):
        """Extract template variables from the target project's pyproject.toml."""
        toml_path = os.path.join(dir_path, "pyproject.toml")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        name = project.get("name", "")
        version = project.get("version", "0.1.0")

        # Extract author -- fall back to git config
        author = ""
        try:
            author = run("git", ["config", "user.name"])
        except Exception:
            pass

        # Extract repo name from project.urls
        repo_name = ""
        urls = project.get("urls", {})
        for url in urls.values():
            match = re.search(r"github\.com/([^/\s\"]+/[^/\s\"]+)", url)
            if match:
                repo_name = match.group(1).removesuffix(".git")
                break

        # Derive binCommand from project.scripts (CLI entry points)
        bin_command = ""
        scripts = project.get("scripts", {})
        if scripts:
            bin_command = next(iter(scripts))  # first script entry

        # Derive the actual Python import name.
        # 1) Check hatch build config for an explicit packages list.
        import_name = None
        hatch = data.get("tool", {}).get("hatch", {})
        packages = (
            hatch.get("build", {}).get("targets", {}).get("wheel", {}).get("packages")
        )
        if packages and isinstance(packages, list) and len(packages) > 0:
            # Strip src/ prefix (common hatch src layout) and convert path to module name
            first_pkg = packages[0]
            import_name = first_pkg.removeprefix("src/").replace("/", ".")

        # 2) Fall back to filesystem detection, then underscore convention.
        if not import_name:
            underscored = name.replace("-", "_")
            if os.path.isdir(os.path.join(dir_path, underscored)):
                import_name = underscored
            elif os.path.isdir(os.path.join(dir_path, name)):
                import_name = name
            else:
                import_name = underscored  # fallback to convention

        return {
            "name": name,
            "version": version,
            "binCommand": bin_command,
            "author": author,
            "repoName": repo_name,
            "importName": import_name,
            "publishSetup": "Configure Trusted Publishing on pypi.org for automated PyPI releases",
        }

    def template_mappings(self):
        return [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
        ]

    def check_project_exists(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "pyproject.toml"))

    def get_project_init_hint(self):
        return 'Run "uv init" first'
