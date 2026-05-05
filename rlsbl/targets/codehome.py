"""Codehome plugin release target for rlsbl.

Handles plugins that live in subdirectories of a monorepo (plugins/<name>/).
Each plugin has a plugin.toml manifest with a [plugin] section containing
name and version fields. Publishing is just pushing to GitHub -- codehome
pulls updates on the consumer side. Tags are namespaced: plugin-name@v1.2.3.
"""

import os
import re
import tomllib

from .base import BaseTarget


class CodehomeTarget(BaseTarget):
    """Release target for codehome/super plugins (plugin.toml)."""

    @property
    def name(self):
        return "codehome"

    @property
    def scope(self):
        return "subdir"

    def detect(self, dir_path):
        """True if plugin.toml exists in the given directory."""
        return os.path.exists(os.path.join(dir_path, "plugin.toml"))

    def read_version(self, dir_path):
        """Read the version from plugin.toml in the given directory."""
        toml_path = os.path.join(dir_path, "plugin.toml")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        try:
            return data["plugin"]["version"]
        except KeyError:
            raise ValueError(f"No [plugin].version in {toml_path}")

    def write_version(self, dir_path, version):
        """Write a new version to plugin.toml and pyproject.toml (if present).

        Uses regex replacement since there is no stdlib TOML writer.
        Writes are atomic (temp file + rename).
        """
        self._write_plugin_toml_version(dir_path, version)
        self._write_pyproject_toml_version(dir_path, version)

    def _write_plugin_toml_version(self, dir_path, version):
        """Update version in plugin.toml within the [plugin] section."""
        toml_path = os.path.join(dir_path, "plugin.toml")
        with open(toml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find [plugin] section boundaries
        plugin_match = re.search(r"^\[plugin\]\s*$", content, re.MULTILINE)
        if not plugin_match:
            raise ValueError("No [plugin] section found in plugin.toml")

        section_start = plugin_match.end()
        # Find next top-level section header or EOF
        next_section = re.search(r"^\[", content[section_start:], re.MULTILINE)
        section_end = (
            section_start + next_section.start() if next_section else len(content)
        )

        # Replace version only within [plugin] section
        section = content[section_start:section_end]
        updated_section = re.sub(
            r'^(version\s*=\s*)"[^"]+"',
            rf'\g<1>"{version}"',
            section,
            count=1,
            flags=re.MULTILINE,
        )
        updated = content[:section_start] + updated_section + content[section_end:]

        # Atomic write
        tmp_path = toml_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_path, toml_path)

    def _write_pyproject_toml_version(self, dir_path, version):
        """Update version in pyproject.toml (guard package) if it exists."""
        toml_path = os.path.join(dir_path, "pyproject.toml")
        if not os.path.exists(toml_path):
            return

        with open(toml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find [project] section boundaries
        project_match = re.search(r"^\[project\]\s*$", content, re.MULTILINE)
        if not project_match:
            # No [project] section -- nothing to update
            return

        section_start = project_match.end()
        next_section = re.search(r"^\[", content[section_start:], re.MULTILINE)
        section_end = (
            section_start + next_section.start() if next_section else len(content)
        )

        section = content[section_start:section_end]
        updated_section = re.sub(
            r'^(version\s*=\s*)"[^"]+"',
            rf'\g<1>"{version}"',
            section,
            count=1,
            flags=re.MULTILINE,
        )
        updated = content[:section_start] + updated_section + content[section_end:]

        # Atomic write
        tmp_path = toml_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_path, toml_path)

    def version_file(self):
        return "plugin.toml"

    def tag_format(self, name, version):
        """Namespaced tags: plugin-name@v1.2.3, or v1.2.3 if no name."""
        if name:
            return f"{name}@v{version}"
        return f"v{version}"

    def get_project_init_hint(self):
        return "Create a plugin.toml with [plugin] name and version fields"
