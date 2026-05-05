"""Docs target -- generates documentation from source code docstrings.

This is an optional target that doesn't manage its own version or tag.
It hooks into the build/publish lifecycle to extract docs from Python sources,
generate Markdown/HTML, and deploy to Cloudflare or GitHub Pages.
"""

import os

from ..base import BaseTarget


class DocsTarget(BaseTarget):
    """Release target for documentation generation and deployment."""

    @property
    def name(self):
        return "docs"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        """True if .rlsbl/docs.toml exists in the given directory."""
        return os.path.exists(os.path.join(dir_path, ".rlsbl", "docs.toml"))

    def read_version(self, dir_path):
        """Docs don't have their own version -- return fallback.

        This target is never the primary target; it piggybacks on the
        primary target's version. Return "0.0.0" as a safe default.
        """
        return "0.0.0"

    def write_version(self, dir_path, version):
        """No-op: docs inherit version from primary target."""
        pass

    def version_file(self):
        """No version file -- docs inherit from primary target."""
        return None

    def tag_format(self, name, version):
        """No separate tag -- uses primary target's tag."""
        return None

    def build(self, dir_path, version):
        """Extract documentation from Python source files.

        Currently performs extraction only. Markdown and HTML generation
        will be added in later phases (3c-3d).
        """
        # Lazy imports to keep heavy deps optional
        from .config import load_docs_config
        from .extract import extract_python_docs

        config = load_docs_config(dir_path)
        if not config:
            return

        pages = extract_python_docs(config["source"]["paths"], dir_path)
        # For now, just extract -- MD/HTML generation comes later
        return pages

    def publish(self, dir_path, version):
        """Deploy docs to configured provider. Not yet implemented (Phase 3e)."""
        pass
