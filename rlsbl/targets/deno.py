"""Deno release target for rlsbl."""

import json
import os
import re
import subprocess

from .base import BaseTarget
from ..utils import run


class DenoTarget(BaseTarget):
    """Release target for Deno projects (deno.json / deno.jsonc)."""

    @property
    def name(self):
        return "deno"

    def detect(self, dir_path):
        return (
            os.path.exists(os.path.join(dir_path, "deno.json"))
            or os.path.exists(os.path.join(dir_path, "deno.jsonc"))
        )

    def _config_path(self, dir_path):
        """Return the path to deno.json or deno.jsonc, preferring deno.json."""
        json_path = os.path.join(dir_path, "deno.json")
        if os.path.exists(json_path):
            return json_path
        jsonc_path = os.path.join(dir_path, "deno.jsonc")
        if os.path.exists(jsonc_path):
            return jsonc_path
        return None

    def _strip_comments(self, text):
        """Strip single-line and block comments from JSONC text."""
        # Remove single-line comments
        text = re.sub(r'//[^\n]*', '', text)
        # Remove block comments
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        return text

    def read_version(self, dir_path):
        """Read the version from deno.json or deno.jsonc."""
        config_path = self._config_path(dir_path)
        if not config_path:
            raise ValueError(f"No deno.json or deno.jsonc found in {dir_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip comments for jsonc
        cleaned = self._strip_comments(content)
        data = json.loads(cleaned)
        if "version" not in data:
            raise ValueError(f"No 'version' field in {config_path}")
        return data["version"]

    def write_version(self, dir_path, version):
        """Write a new version to deno.json or deno.jsonc.

        For deno.json, uses standard JSON rewrite preserving indent.
        For deno.jsonc, uses regex replacement to preserve comments.
        """
        config_path = self._config_path(dir_path)
        if not config_path:
            raise ValueError(f"No deno.json or deno.jsonc found in {dir_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = f.read()

        if config_path.endswith(".jsonc"):
            # Regex-based replacement to preserve comments
            new_content = re.sub(
                r'("version"\s*:\s*)"[^"]+"',
                f'\\1"{version}"',
                raw,
            )
        else:
            # Standard JSON rewrite
            indent_match = re.search(r'^( +|\t+)"', raw, re.MULTILINE)
            indent = indent_match.group(1) if indent_match else "  "
            data = json.loads(raw)
            data["version"] = version
            trailing_newline = "\n" if raw.endswith("\n") else ""
            new_content = json.dumps(data, indent=indent, ensure_ascii=False) + trailing_newline

        tmp_path = config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp_path, config_path)

    def version_file(self):
        return "deno.json"

    def tag_format(self, version):
        return f"v{version}"

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "deno"
        )

    def template_vars(self, dir_path):
        """Extract template variables from deno.json."""
        config_path = self._config_path(dir_path)
        if not config_path:
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        cleaned = self._strip_comments(content)
        data = json.loads(cleaned)

        # Author from git config
        try:
            author = run("git", ["config", "user.name"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            author = ""

        return {
            "name": data.get("name", ""),
            "version": data.get("version", "0.1.0"),
            "author": author,
            "publishSetup": "Requires DENO_TOKEN or JSR_TOKEN secret on GitHub (Settings > Secrets > Actions)",
        }

    def template_mappings(self):
        return [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
        ]

    def publish(self, dir_path, version):
        """Publish to JSR if DENO_TOKEN or JSR_TOKEN is available, otherwise defer to CI."""
        token = os.environ.get("DENO_TOKEN") or os.environ.get("JSR_TOKEN")
        if not token:
            print("Skipping local Deno publish (no DENO_TOKEN/JSR_TOKEN). CI will handle it.")
            return

        try:
            run("deno", ["publish"], env={
                **os.environ,
                "DENO_TOKEN": token,
            })
            print(f"Published to JSR: {version}")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"deno publish failed: {exc}") from exc

    def check_project_exists(self, dir_path):
        return self.detect(dir_path)

    def get_project_init_hint(self):
        return 'Run "deno init" first'
