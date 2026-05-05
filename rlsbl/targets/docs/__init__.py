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
        """Extract docs from Python sources, generate Markdown and HTML."""
        # Lazy imports to keep heavy deps optional
        from .config import load_docs_config
        from .extract import extract_python_docs
        from .markdown import generate_markdown
        from .html import generate_html

        config = load_docs_config(dir_path)
        if not config:
            return

        pages = extract_python_docs(config["source"]["paths"], dir_path)
        project_name = config.get(
            "project_name", os.path.basename(os.path.abspath(dir_path))
        )

        md_files = generate_markdown(pages, version, project_name)
        html_files = generate_html(md_files, version, project_name)

        # Write HTML output to configured directory
        output_dir = os.path.join(dir_path, config["output"]["dir"])
        os.makedirs(output_dir, exist_ok=True)
        for rel_path, content in html_files.items():
            out_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w") as f:
                f.write(content)

        return pages

    def publish(self, dir_path, version):
        """Deploy docs to configured provider (Cloudflare Pages or GitHub Pages)."""
        import sys

        from .config import load_docs_config
        from .deploy import deploy_cloudflare_pages, deploy_github_pages

        config = load_docs_config(dir_path)
        if not config or "deploy" not in config:
            return

        output_dir = os.path.join(dir_path, config["output"]["dir"])
        if not os.path.isdir(output_dir):
            print(
                "Warning: docs output directory not found. "
                "Run 'rlsbl docs build' first.",
                file=sys.stderr,
            )
            return

        provider = config["deploy"]["provider"]
        if provider == "cloudflare-pages":
            deploy_cloudflare_pages(
                output_dir, config["deploy"]["project"], version
            )
        elif provider == "github-pages":
            deploy_github_pages(output_dir, version)
