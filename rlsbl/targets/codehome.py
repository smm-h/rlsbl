"""Codehome plugin repository target.

Each codehome plugin (or plugin group) lives in its own git repo with a
plugin.json at the root. Version management is standard: bump plugin.json,
tag v1.2.3, push. Push IS delivery -- codehome polls repos for newer tags.
"""

import json
import os

from .base import BaseTarget


class PluginValidationError(Exception):
    pass


REQUIRED_FIELDS = ("name", "version", "description")


def validate_plugin_json(data):
    """Validate plugin.json has required fields."""
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise PluginValidationError(
            f"plugin.json missing required fields: {', '.join(missing)}"
        )
    # Validate version is semver-like (at least X.Y.Z)
    version = data["version"]
    parts = version.split(".")
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        raise PluginValidationError(
            f"plugin.json version '{version}' is not valid semver (expected X.Y.Z)"
        )


class CodehomeTarget(BaseTarget):
    @property
    def name(self):
        return "codehome"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "plugin.json"))

    def read_version(self, dir_path):
        plugin_path = os.path.join(dir_path, "plugin.json")
        with open(plugin_path) as f:
            data = json.load(f)
        return data["version"]

    def write_version(self, dir_path, version):
        plugin_path = os.path.join(dir_path, "plugin.json")
        with open(plugin_path) as f:
            content = f.read()
            data = json.loads(content)

        # Detect indent
        indent = 2
        for line in content.splitlines()[1:]:
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                break

        data["version"] = version

        # Atomic write
        tmp_path = plugin_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=indent)
            f.write("\n")
        os.replace(tmp_path, plugin_path)

    def version_file(self):
        return "plugin.json"

    def tag_format(self, name, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "codehome")

    def template_vars(self, dir_path):
        plugin_path = os.path.join(dir_path, "plugin.json")
        if os.path.exists(plugin_path):
            with open(plugin_path) as f:
                data = json.load(f)
            return {
                "name": data.get("name", ""),
                "version": data.get("version", "0.1.0"),
                "description": data.get("description", ""),
            }
        return {"name": "", "version": "0.1.0", "description": ""}

    def template_mappings(self):
        return [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
        ]

    def check_project_exists(self, dir_path):
        return self.detect(dir_path)

    def get_project_init_hint(self):
        return 'Create a plugin.json with "name", "version", and "description" fields'

    def build(self, dir_path, version):
        """Validate plugin.json schema before release."""
        plugin_path = os.path.join(dir_path, "plugin.json")
        if not os.path.exists(plugin_path):
            return
        with open(plugin_path) as f:
            data = json.load(f)
        validate_plugin_json(data)

    def publish(self, dir_path, version):
        pass  # Push IS the publish -- git push happens in the release flow
