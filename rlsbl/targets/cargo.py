"""Cargo (Rust) release target for rlsbl.

Uses tomlkit for round-trip Cargo.toml editing that preserves comments and
formatting. Supports hybrid publish: if CARGO_REGISTRY_TOKEN is set, runs
`cargo publish` locally; otherwise defers to CI.

Libraries (crates with [lib] or no src/main.rs and no [[bin]]) skip the
publish.yml template since they typically publish via CI only after review.
"""

import os
import subprocess

import tomlkit

from .base import BaseTarget
from ..utils import run


class CargoTarget(BaseTarget):
    """Release target for Rust/Cargo projects (Cargo.toml)."""

    @property
    def name(self):
        return "cargo"

    def detect(self, dir_path):
        """Detect if dir has a Cargo.toml with a [package] section (not workspace-only)."""
        cargo_path = os.path.join(dir_path, "Cargo.toml")
        if not os.path.exists(cargo_path):
            return False
        with open(cargo_path, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())
        return "package" in doc

    def read_version(self, dir_path):
        """Read version from Cargo.toml [package].version."""
        cargo_path = os.path.join(dir_path, "Cargo.toml")
        with open(cargo_path, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())
        if "package" not in doc or "version" not in doc["package"]:
            raise ValueError(f"No [package].version in {cargo_path}")
        return str(doc["package"]["version"])

    def write_version(self, dir_path, version):
        """Write version to Cargo.toml using tomlkit round-trip (preserves comments)."""
        cargo_path = os.path.join(dir_path, "Cargo.toml")
        with open(cargo_path, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())
        doc["package"]["version"] = version
        tmp_path = cargo_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))
        os.replace(tmp_path, cargo_path)

    def version_file(self):
        return "Cargo.toml"

    def tag_format(self, version):
        return f"v{version}"

    def _is_library(self, dir_path):
        """Return True if the crate is a library (no binary target)."""
        cargo_path = os.path.join(dir_path, "Cargo.toml")
        with open(cargo_path, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())
        # Explicit [lib] section means it's a library
        if "lib" in doc:
            return True
        # Explicit [[bin]] section means it's a binary
        if "bin" in doc:
            return False
        # No explicit sections: check for src/main.rs
        main_rs = os.path.join(dir_path, "src", "main.rs")
        return not os.path.exists(main_rs)

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "cargo"
        )

    def template_vars(self, dir_path):
        """Extract template variables from Cargo.toml."""
        cargo_path = os.path.join(dir_path, "Cargo.toml")
        with open(cargo_path, "r", encoding="utf-8") as f:
            doc = tomlkit.parse(f.read())

        pkg = doc.get("package", {})
        name = str(pkg.get("name", ""))

        # Author from Cargo.toml authors[0] or git config
        author = ""
        authors = pkg.get("authors")
        if authors and len(authors) > 0:
            author = str(authors[0])
        if not author:
            try:
                author = run("git", ["config", "user.name"])
            except Exception:
                pass

        version = str(pkg.get("version", "0.0.0"))

        return {
            "name": name,
            "version": version,
            "author": author,
            "publishSetup": "Requires CARGO_REGISTRY_TOKEN secret on GitHub (Settings > Secrets > Actions)",
        }

    def template_mappings(self):
        mappings = [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
        ]
        if not self._is_library("."):
            mappings.append(
                {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
            )
        return mappings

    def publish(self, dir_path, version):
        """Publish to crates.io if CARGO_REGISTRY_TOKEN is set, otherwise skip."""
        token = os.environ.get("CARGO_REGISTRY_TOKEN")
        if not token:
            print("Skipping local cargo publish (no CARGO_REGISTRY_TOKEN). CI will handle it.")
            return

        try:
            run("cargo", ["publish"], env={
                **os.environ,
                "CARGO_REGISTRY_TOKEN": token,
            })
            print(f"Published to crates.io: {version}")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"cargo publish failed: {exc}") from exc

    def check_project_exists(self, dir_path):
        return self.detect(dir_path)

    def get_project_init_hint(self):
        return 'Run "cargo init" or "cargo new <name>" first'
