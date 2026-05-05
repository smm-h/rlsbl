"""Codehome plugin repository target.

Each codehome plugin (or plugin group) lives in its own git repo with a
plugin.json at the root. Version management is standard: bump plugin.json,
tag v1.2.3, push. Push IS delivery -- codehome polls repos for newer tags.

Plugin Registry Format
----------------------
A central registry file (plugins.json) lists all known plugin repos so that
codehome can discover them without scanning GitHub. The schema:

    {
      "plugins": [
        {
          "name": "supervisor",
          "repo": "https://github.com/smm-h/supervisor",
          "description": "Worktree, branch, and git management",
          "plugins_provided": ["supervisor", "worktree", "branch-tools"]
        }
      ]
    }

Fields:
- name: The plugin group name (from plugin.json "name")
- repo: HTTPS URL of the git repository (from git remote "origin")
- description: Human-readable summary (from plugin.json "description")
- plugins_provided: List of individual plugin IDs shipped by this repo
  (from plugin.json "plugins_provided"; falls back to [name] if absent)

Versions are NOT stored in the registry -- they are discovered at runtime
by checking git tags on each repo.
"""

import json
import os
import subprocess

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


def generate_registry_entry(dir_path):
    """Generate a registry entry dict from the current plugin repo.

    Reads plugin.json and returns a dict suitable for inclusion in a
    plugin registry (plugins.json):
    {
        "name": "supervisor",
        "repo": "https://github.com/smm-h/supervisor",
        "description": "Worktree, branch, and git management",
        "plugins_provided": ["supervisor", "worktree"]
    }

    If plugin.json is missing, raises FileNotFoundError.
    If git remote "origin" is not configured, the "repo" field is omitted.
    """
    plugin_path = os.path.join(dir_path, "plugin.json")
    if not os.path.exists(plugin_path):
        raise FileNotFoundError(f"No plugin.json found in {dir_path}")

    with open(plugin_path) as f:
        data = json.load(f)

    entry = {
        "name": data["name"],
        "description": data.get("description", ""),
        "plugins_provided": data.get("plugins_provided", [data["name"]]),
    }

    # Try to get repo URL from git remote origin
    repo_url = _get_git_remote_url(dir_path)
    if repo_url:
        entry["repo"] = repo_url

    return entry


def _get_git_remote_url(dir_path):
    """Get the HTTPS URL of the git remote 'origin', or None.

    Normalizes SSH URLs (git@github.com:user/repo.git) to HTTPS form.
    Strips trailing .git suffix for cleaner URLs.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            cwd=dir_path,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        if not url:
            return None
        # Normalize SSH to HTTPS
        if url.startswith("git@"):
            # git@github.com:user/repo.git -> https://github.com/user/repo
            url = url.replace(":", "/", 1).replace("git@", "https://", 1)
        # Strip trailing .git
        if url.endswith(".git"):
            url = url[:-4]
        return url
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


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
