"""Tests for docs Markdown and HTML generation."""

import os
import tempfile

from rlsbl.targets.docs.markdown import generate_markdown
from rlsbl.targets.docs.html import generate_html, md_to_html


# -- Sample page data mimicking extract_python_docs output --

SAMPLE_PAGES = [
    {
        "module": "myproject.core",
        "path": "myproject/core.py",
        "docstring": "Core module providing the main functionality.",
        "classes": [
            {
                "name": "Engine",
                "docstring": "The main processing engine.",
                "methods": [
                    {
                        "name": "run",
                        "docstring": "Execute the engine pipeline.",
                        "signature": "(self, input_data: list) -> dict",
                    },
                    {
                        "name": "stop",
                        "docstring": "Gracefully stop the engine.",
                        "signature": "(self)",
                    },
                ],
            }
        ],
        "functions": [
            {
                "name": "initialize",
                "docstring": "Set up the runtime environment.",
                "signature": "(config: dict, verbose: bool=False) -> None",
            }
        ],
    },
    {
        "module": "myproject.utils",
        "path": "myproject/utils.py",
        "docstring": "Utility helpers.",
        "classes": [],
        "functions": [
            {
                "name": "slugify",
                "docstring": "Convert text to a URL-safe slug.",
                "signature": "(text: str) -> str",
            }
        ],
    },
    {
        "module": "other.lib",
        "path": "other/lib.py",
        "docstring": "A library in a different package.",
        "classes": [],
        "functions": [
            {
                "name": "helper",
                "docstring": "A helper function.",
                "signature": "(x)",
            }
        ],
    },
]

EMPTY_PAGES = []

# Page with no documented items (only a module docstring with empty lists)
PAGE_DOCSTRING_ONLY = [
    {
        "module": "myproject.empty",
        "path": "myproject/empty.py",
        "docstring": "A module with only a docstring.",
        "classes": [],
        "functions": [],
    }
]


class TestMarkdownGeneration:
    """Tests for generate_markdown."""

    def test_generates_module_pages(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        assert "api/myproject.core.md" in md_files
        assert "api/myproject.utils.md" in md_files
        assert "api/other.lib.md" in md_files

    def test_module_page_has_title(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/myproject.core.md"]
        assert content.startswith("# myproject.core")

    def test_module_page_has_docstring(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/myproject.core.md"]
        assert "Core module providing the main functionality." in content

    def test_module_page_has_functions(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/myproject.core.md"]
        assert "### initialize" in content
        assert "def initialize(config: dict, verbose: bool=False) -> None" in content
        assert "Set up the runtime environment." in content

    def test_module_page_has_classes(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/myproject.core.md"]
        assert "### Engine" in content
        assert "The main processing engine." in content

    def test_module_page_has_methods(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/myproject.core.md"]
        assert "#### run" in content
        assert "def run(self, input_data: list) -> dict" in content
        assert "Execute the engine pipeline." in content

    def test_generates_index(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        assert "index.md" in md_files
        content = md_files["index.md"]
        assert "# MyProject" in content
        assert "1.2.3" in content

    def test_generates_api_index(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        assert "api/index.md" in md_files
        content = md_files["api/index.md"]
        assert "API Reference" in content
        assert "myproject.core" in content
        assert "myproject.utils" in content
        assert "other.lib" in content

    def test_api_index_groups_by_package(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["api/index.md"]
        # Should have package group headings
        assert "## myproject" in content
        assert "## other" in content

    def test_index_links_to_modules(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.2.3", "MyProject")
        content = md_files["index.md"]
        assert "api/myproject.core.md" in content
        assert "api/myproject.utils.md" in content

    def test_empty_pages_produces_indexes_only(self):
        md_files = generate_markdown(EMPTY_PAGES, "0.1.0", "Empty")
        assert "index.md" in md_files
        assert "api/index.md" in md_files
        # No module pages
        module_pages = [k for k in md_files if k not in ("index.md", "api/index.md")]
        assert module_pages == []

    def test_docstring_only_module_included(self):
        """A module with just a docstring (no funcs/classes) should still be included."""
        md_files = generate_markdown(PAGE_DOCSTRING_ONLY, "1.0.0", "Test")
        assert "api/myproject.empty.md" in md_files
        content = md_files["api/myproject.empty.md"]
        assert "A module with only a docstring." in content

    def test_default_project_name(self):
        md_files = generate_markdown(SAMPLE_PAGES, "1.0.0")
        content = md_files["index.md"]
        # Default project_name is "Documentation"
        assert "# Documentation" in content


class TestHTMLGeneration:
    """Tests for generate_html and md_to_html."""

    def test_converts_md_paths_to_html(self):
        md_files = {"index.md": "# Hello", "api/module.md": "# Module"}
        html_files = generate_html(md_files, "1.0.0", "TestProject")
        assert "index.html" in html_files
        assert "api/module.html" in html_files

    def test_html_has_doctype(self):
        md_files = {"index.md": "# Hello"}
        html_files = generate_html(md_files, "1.0.0", "TestProject")
        assert html_files["index.html"].startswith("<!DOCTYPE html>")

    def test_html_has_title(self):
        md_files = {"index.md": "# My Page"}
        html_files = generate_html(md_files, "1.0.0", "TestProject")
        assert "<title>My Page - TestProject</title>" in html_files["index.html"]

    def test_html_has_sidebar(self):
        md_files = {"index.md": "# Hello", "api/index.md": "# API"}
        html_files = generate_html(md_files, "1.0.0", "TestProject")
        assert '<nav class="sidebar">' in html_files["index.html"]
        assert "TestProject" in html_files["index.html"]

    def test_html_has_version(self):
        md_files = {"index.md": "# Hello"}
        html_files = generate_html(md_files, "2.5.0", "Proj")
        assert "2.5.0" in html_files["index.html"]

    def test_html_has_css(self):
        md_files = {"index.md": "# Hello"}
        html_files = generate_html(md_files, "1.0.0")
        assert "<style>" in html_files["index.html"]
        assert "font-family" in html_files["index.html"]

    def test_html_has_responsive_meta(self):
        md_files = {"index.md": "# Hello"}
        html_files = generate_html(md_files, "1.0.0")
        assert 'name="viewport"' in html_files["index.html"]

    def test_empty_input(self):
        html_files = generate_html({}, "1.0.0", "Empty")
        assert html_files == {}


class TestMdToHtml:
    """Tests for the built-in Markdown to HTML converter."""

    def test_heading_h1(self):
        result = md_to_html("# Hello World")
        assert "<h1>Hello World</h1>" in result

    def test_heading_h2(self):
        result = md_to_html("## Section")
        assert "<h2>Section</h2>" in result

    def test_heading_h3(self):
        result = md_to_html("### Subsection")
        assert "<h3>Subsection</h3>" in result

    def test_paragraph(self):
        result = md_to_html("This is a paragraph.")
        assert "<p>This is a paragraph.</p>" in result

    def test_multiple_paragraphs(self):
        result = md_to_html("First paragraph.\n\nSecond paragraph.")
        assert "<p>First paragraph.</p>" in result
        assert "<p>Second paragraph.</p>" in result

    def test_code_block(self):
        md = "```python\ndef foo():\n    pass\n```"
        result = md_to_html(md)
        assert "<pre><code" in result
        assert "def foo():" in result
        assert "language-python" in result

    def test_code_block_escapes_html(self):
        md = "```\n<script>alert('xss')</script>\n```"
        result = md_to_html(md)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_inline_code(self):
        result = md_to_html("Use `foo()` here.")
        assert "<code>foo()</code>" in result

    def test_inline_code_escapes_html(self):
        result = md_to_html("Type `<div>` tag.")
        assert "<code>&lt;div&gt;</code>" in result

    def test_link(self):
        result = md_to_html("See [docs](https://example.com) for more.")
        assert '<a href="https://example.com">docs</a>' in result

    def test_bold(self):
        result = md_to_html("This is **important** text.")
        assert "<strong>important</strong>" in result

    def test_italic(self):
        result = md_to_html("This is *emphasized* text.")
        assert "<em>emphasized</em>" in result

    def test_unordered_list(self):
        md = "- Item one\n- Item two\n- Item three"
        result = md_to_html(md)
        assert "<ul>" in result
        assert "<li>Item one</li>" in result
        assert "<li>Item two</li>" in result
        assert "<li>Item three</li>" in result

    def test_list_with_inline_formatting(self):
        md = "- **Bold item**\n- [Link](url)"
        result = md_to_html(md)
        assert "<strong>Bold item</strong>" in result
        assert '<a href="url">Link</a>' in result

    def test_empty_input(self):
        result = md_to_html("")
        assert result == ""

    def test_complex_document(self):
        """Integration test with multiple element types."""
        md = """# Title

Some intro text.

## Functions

### my_func

```python
def my_func(x: int) -> str
```

Does something **useful**.

- Step one
- Step two
"""
        result = md_to_html(md)
        assert "<h1>Title</h1>" in result
        assert "<h2>Functions</h2>" in result
        assert "<h3>my_func</h3>" in result
        assert "<pre><code" in result
        assert "def my_func" in result
        assert "<strong>useful</strong>" in result
        assert "<ul>" in result


class TestEndToEnd:
    """End-to-end test: pages -> markdown -> html -> written files."""

    def test_build_writes_html_files(self):
        """Verify DocsTarget.build() writes HTML to the output directory."""
        from rlsbl.targets.docs import DocsTarget

        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # Set up config
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(
                    '[source]\ntype = "python"\npaths = ["src/"]\n\n'
                    '[output]\ndir = "docs/_build"\n\n'
                    '[deploy]\nprovider = "github-pages"\n'
                )

            # Set up source
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "example.py"), "w") as f:
                f.write(
                    '"""Example module."""\n\n'
                    'def greet(name: str) -> str:\n'
                    '    """Say hello."""\n'
                    '    return f"Hello, {name}"\n'
                )

            target.build(d, "1.0.0")

            # Verify output directory was created
            output_dir = os.path.join(d, "docs", "_build")
            assert os.path.isdir(output_dir)

            # Verify index.html exists
            assert os.path.isfile(os.path.join(output_dir, "index.html"))

            # Verify API index exists
            assert os.path.isfile(os.path.join(output_dir, "api", "index.html"))

            # Verify module page exists
            assert os.path.isfile(os.path.join(output_dir, "api", "src.example.html"))

            # Verify content is valid HTML
            with open(os.path.join(output_dir, "api", "src.example.html")) as f:
                html_content = f.read()
            assert "<!DOCTYPE html>" in html_content
            assert "src.example" in html_content
            assert "greet" in html_content
            assert "Say hello." in html_content
