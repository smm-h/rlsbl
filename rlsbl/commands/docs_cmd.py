"""Docs command: init, build, serve, and deploy documentation."""

import os
import sys

DOCS_HELP = """\
rlsbl docs -- Documentation generation and deployment

Subcommands:
  init     Create .rlsbl/docs.toml with a template config
  build    Extract docs from source and generate HTML
  serve    Start a local preview server (Ctrl+C to stop)
  deploy   Deploy docs to configured provider

Examples:
  rlsbl docs init
  rlsbl docs build
  rlsbl docs serve --port 3000
  rlsbl docs deploy"""

# Template for .rlsbl/docs.toml created by `docs init`
_CONFIG_TEMPLATE = """\
[source]
type = "python"
paths = [{paths}]

[output]
dir = "docs/_build"

[deploy]
provider = "github-pages"
"""


def _detect_source_paths():
    """Auto-detect likely source directories for documentation extraction."""
    candidates = []
    # Check for src/ layout
    if os.path.isdir("src"):
        candidates.append("src/")
    # Check for a package directory matching pyproject.toml project name
    project_name = _detect_project_name()
    if project_name:
        # Convert dashes to underscores for Python package dirs
        pkg_dir = project_name.replace("-", "_")
        if os.path.isdir(pkg_dir):
            candidates.append(f"{pkg_dir}/")
    # Fallback: look for any top-level directory containing __init__.py
    if not candidates:
        for entry in sorted(os.listdir(".")):
            if entry.startswith(".") or entry.startswith("_"):
                continue
            init_path = os.path.join(entry, "__init__.py")
            if os.path.isdir(entry) and os.path.isfile(init_path):
                candidates.append(f"{entry}/")
                break
    return candidates if candidates else ["src/"]


def _detect_project_name():
    """Auto-detect project name from pyproject.toml or package.json."""
    if os.path.isfile("pyproject.toml"):
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]
        try:
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("name")
        except Exception:
            pass
    if os.path.isfile("package.json"):
        import json
        try:
            with open("package.json") as f:
                data = json.load(f)
            return data.get("name", "").lstrip("@").replace("/", "-")
        except Exception:
            pass
    return None


def _cmd_init(args, flags):
    """Create .rlsbl/docs.toml with a template configuration."""
    config_path = os.path.join(".rlsbl", "docs.toml")
    if os.path.exists(config_path):
        print(f"Error: {config_path} already exists.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(".rlsbl", exist_ok=True)

    source_paths = _detect_source_paths()
    paths_str = ", ".join(f'"{p}"' for p in source_paths)
    content = _CONFIG_TEMPLATE.format(paths=paths_str)

    with open(config_path, "w") as f:
        f.write(content)

    project_name = _detect_project_name() or os.path.basename(os.path.abspath("."))
    print(f"Created {config_path}")
    print(f"  Project: {project_name}")
    print(f"  Source paths: {source_paths}")
    print()
    print("Next steps:")
    print("  1. Review and edit .rlsbl/docs.toml")
    print("  2. Run: rlsbl docs build")
    print("  3. Run: rlsbl docs serve")


def _cmd_build(args, flags):
    """Run the full documentation build pipeline."""
    from ..targets.docs import DocsTarget
    from ..targets.docs.config import load_docs_config
    from .. import detect_registries

    config = load_docs_config(".")
    if not config:
        print("Error: no .rlsbl/docs.toml found. Run 'rlsbl docs init' first.",
              file=sys.stderr)
        sys.exit(1)

    # Get version from primary detected registry
    version = "0.0.0"
    regs = detect_registries()
    if regs:
        from ..targets import TARGETS
        primary = TARGETS.get(regs[0])
        if primary:
            version = primary.read_version(".")

    target = DocsTarget()
    pages = target.build(".", version)

    if pages is None:
        print("Error: build failed (no config or sources).", file=sys.stderr)
        sys.exit(1)

    output_dir = config["output"]["dir"]
    print(f"Built documentation: {len(pages)} module(s)")
    print(f"Output: {output_dir}/")


def _cmd_serve(args, flags):
    """Start a local HTTP server for previewing built docs."""
    from ..targets.docs.config import load_docs_config
    import http.server
    import functools

    config = load_docs_config(".")
    if not config:
        print("Error: no .rlsbl/docs.toml found. Run 'rlsbl docs init' first.",
              file=sys.stderr)
        sys.exit(1)

    output_dir = config["output"]["dir"]
    if not os.path.isdir(output_dir):
        print(f"Error: output directory '{output_dir}' not found. "
              "Run 'rlsbl docs build' first.", file=sys.stderr)
        sys.exit(1)

    port = int(flags.get("port", 8000))

    # Use a partial to set the directory for the handler
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=output_dir
    )

    print(f"Serving docs from {output_dir}/ at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        with http.server.HTTPServer(("", port), handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def _cmd_deploy(args, flags):
    """Deploy docs to the configured provider."""
    from ..targets.docs import DocsTarget
    from .. import detect_registries

    # Get version from primary detected registry
    version = "0.0.0"
    regs = detect_registries()
    if regs:
        from ..targets import TARGETS
        primary = TARGETS.get(regs[0])
        if primary:
            version = primary.read_version(".")

    target = DocsTarget()
    target.publish(".", version)


def run_cmd(registry, args, flags):
    """Dispatch docs subcommands."""
    if not args:
        print(DOCS_HELP)
        return

    subcommand = args[0]
    sub_args = args[1:]

    dispatch = {
        "init": _cmd_init,
        "build": _cmd_build,
        "serve": _cmd_serve,
        "deploy": _cmd_deploy,
    }

    handler = dispatch.get(subcommand)
    if not handler:
        print(f"Error: unknown docs subcommand '{subcommand}'.\n", file=sys.stderr)
        print(DOCS_HELP, file=sys.stderr)
        sys.exit(1)

    handler(sub_args, flags)
