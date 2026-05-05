"""Convert extracted documentation data into Markdown files."""


def generate_markdown(pages, version, project_name=None):
    """Convert extracted page data into Markdown files.

    Args:
        pages: List of page dicts from extract_python_docs.
        version: Version string for display in headers.
        project_name: Project name for the index page title.

    Returns:
        Dict mapping relative file paths to markdown content.
        e.g., {"api/rlsbl.commands.release.md": "# rlsbl.commands.release\\n\\n..."}

        Also generates:
        - "index.md" -- table of contents / navigation
        - "api/index.md" -- API reference overview listing all modules
    """
    if not project_name:
        project_name = "Documentation"

    md_files = {}

    # Generate a page for each module that has documented items
    documented_modules = []
    for page in pages:
        if not _has_documented_items(page):
            continue
        rel_path = f"api/{page['module']}.md"
        md_files[rel_path] = _render_module_page(page)
        documented_modules.append(page)

    # Generate API index (lists all modules)
    md_files["api/index.md"] = _render_api_index(documented_modules, project_name, version)

    # Generate top-level index
    md_files["index.md"] = _render_index(documented_modules, project_name, version)

    return md_files


def _has_documented_items(page):
    """Check if a page has any documented content worth rendering."""
    return bool(page.get("docstring") or page.get("classes") or page.get("functions"))


def _render_module_page(page):
    """Render a single module's documentation as Markdown."""
    lines = []

    # Module title
    lines.append(f"# {page['module']}")
    lines.append("")

    # Module docstring
    if page.get("docstring"):
        lines.append(page["docstring"])
        lines.append("")

    # Functions section
    if page.get("functions"):
        lines.append("## Functions")
        lines.append("")
        for func in page["functions"]:
            lines.append(f"### {func['name']}")
            lines.append("")
            lines.append("```python")
            lines.append(f"def {func['name']}{func['signature']}")
            lines.append("```")
            lines.append("")
            if func.get("docstring"):
                lines.append(func["docstring"])
                lines.append("")

    # Classes section
    if page.get("classes"):
        lines.append("## Classes")
        lines.append("")
        for cls in page["classes"]:
            lines.append(f"### {cls['name']}")
            lines.append("")
            if cls.get("docstring"):
                lines.append(cls["docstring"])
                lines.append("")
            if cls.get("methods"):
                for method in cls["methods"]:
                    lines.append(f"#### {method['name']}")
                    lines.append("")
                    lines.append("```python")
                    lines.append(f"def {method['name']}{method['signature']}")
                    lines.append("```")
                    lines.append("")
                    if method.get("docstring"):
                        lines.append(method["docstring"])
                        lines.append("")

    return "\n".join(lines)


def _render_api_index(modules, project_name, version):
    """Render the API reference index listing all modules grouped by package."""
    lines = []
    lines.append(f"# {project_name} API Reference")
    lines.append("")
    lines.append(f"Version: {version}")
    lines.append("")

    if not modules:
        lines.append("No documented modules found.")
        lines.append("")
        return "\n".join(lines)

    # Group modules by top-level package
    groups = _group_by_package(modules)

    for package, pages in sorted(groups.items()):
        lines.append(f"## {package}")
        lines.append("")
        for page in pages:
            link = f"{page['module']}.md"
            # Brief description: first line of module docstring or empty
            brief = _first_line(page.get("docstring", ""))
            if brief:
                lines.append(f"- [{page['module']}]({link}) -- {brief}")
            else:
                lines.append(f"- [{page['module']}]({link})")
        lines.append("")

    return "\n".join(lines)


def _render_index(modules, project_name, version):
    """Render the top-level documentation index."""
    lines = []
    lines.append(f"# {project_name}")
    lines.append("")
    lines.append(f"Version: {version}")
    lines.append("")
    lines.append("## Contents")
    lines.append("")
    lines.append("- [API Reference](api/index.md)")
    lines.append("")

    if modules:
        lines.append("## Modules")
        lines.append("")
        for page in modules:
            link = f"api/{page['module']}.md"
            lines.append(f"- [{page['module']}]({link})")
        lines.append("")

    return "\n".join(lines)


def _group_by_package(modules):
    """Group modules by their top-level package name.

    e.g., "rlsbl.commands.release" goes into the "rlsbl" group.
    Modules with no dots go into a group named after themselves.
    """
    groups = {}
    for page in modules:
        module_name = page["module"]
        parts = module_name.split(".")
        # Use the first component as the group key
        package = parts[0]
        groups.setdefault(package, []).append(page)
    return groups


def _first_line(text):
    """Extract the first non-empty line from a string."""
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
