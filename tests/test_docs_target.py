"""Tests for the docs target: config loading and Python extraction."""

import os
import tempfile

from rlsbl.targets.protocol import ReleaseTarget
from rlsbl.targets.docs import DocsTarget
from rlsbl.targets.docs.config import load_docs_config, DocsConfigError
from rlsbl.targets.docs.extract import extract_python_docs, _path_to_module
from rlsbl.targets import TARGETS


# -- Sample configs for testing --

VALID_DOCS_TOML = """\
[source]
type = "python"
paths = ["src/"]

[output]
dir = "docs/_build"

[deploy]
provider = "cloudflare-pages"
project = "my-docs"
domain = "docs.example.com"
"""

VALID_GITHUB_PAGES_TOML = """\
[source]
type = "python"
paths = ["lib/", "pkg/"]

[output]
dir = "site/"

[deploy]
provider = "github-pages"
"""

MISSING_SOURCE_TOML = """\
[output]
dir = "docs/_build"

[deploy]
provider = "github-pages"
"""

INVALID_TYPE_TOML = """\
[source]
type = "javascript"
paths = ["src/"]

[output]
dir = "docs/_build"

[deploy]
provider = "github-pages"
"""

INVALID_PROVIDER_TOML = """\
[source]
type = "python"
paths = ["src/"]

[output]
dir = "docs/_build"

[deploy]
provider = "netlify"
"""

CLOUDFLARE_MISSING_PROJECT_TOML = """\
[source]
type = "python"
paths = ["src/"]

[output]
dir = "docs/_build"

[deploy]
provider = "cloudflare-pages"
"""

EMPTY_PATHS_TOML = """\
[source]
type = "python"
paths = []

[output]
dir = "docs/_build"

[deploy]
provider = "github-pages"
"""

# -- Sample Python source for extraction testing --

SAMPLE_MODULE = '''\
"""A sample module for testing documentation extraction."""


def public_function(x, y=None):
    """Do something useful with x and y."""
    return x


def _private_no_doc(a):
    return a


def _private_with_doc(a):
    """This private function has a docstring so it should be included."""
    return a


class PublicClass:
    """A documented public class."""

    def method_one(self):
        """First method."""
        pass

    def method_two(self, arg: str) -> bool:
        """Second method with annotations."""
        return True

    def _private_method(self):
        pass


class _PrivateClass:
    """A private class with a docstring -- should be included."""

    def helper(self):
        """Helper method."""
        pass


class UndocumentedClass:
    def undocumented_method(self):
        pass
'''

SAMPLE_INIT = '''\
"""Package init module."""
'''

SAMPLE_EMPTY = """\
# No docstrings here
x = 1
"""

SAMPLE_SIGNATURES = '''\
"""Module with various function signatures."""


def simple():
    """No args."""
    pass


def positional(a, b, c):
    """Positional args only."""
    pass


def defaults(a, b=10, c="hello"):
    """Args with defaults."""
    pass


def varargs(*args, **kwargs):
    """Variadic."""
    pass


def annotated(x: int, y: str = "world") -> bool:
    """Annotated function."""
    return True


def keyword_only(a, *, key: str, flag: bool = False):
    """Keyword-only args."""
    pass


async def async_func(data: list) -> None:
    """An async function."""
    pass
'''


class TestDocsConfig:
    """Tests for .rlsbl/docs.toml loading and validation."""

    def test_load_valid_config(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(VALID_DOCS_TOML)

            config = load_docs_config(d)
            assert config is not None
            assert config["source"]["type"] == "python"
            assert config["source"]["paths"] == ["src/"]
            assert config["output"]["dir"] == "docs/_build"
            assert config["deploy"]["provider"] == "cloudflare-pages"
            assert config["deploy"]["project"] == "my-docs"
            assert config["deploy"]["domain"] == "docs.example.com"

    def test_load_github_pages_config(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(VALID_GITHUB_PAGES_TOML)

            config = load_docs_config(d)
            assert config is not None
            assert config["deploy"]["provider"] == "github-pages"
            assert config["source"]["paths"] == ["lib/", "pkg/"]

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            result = load_docs_config(d)
            assert result is None

    def test_missing_source_section_raises(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(MISSING_SOURCE_TOML)

            try:
                load_docs_config(d)
                assert False, "Should have raised DocsConfigError"
            except DocsConfigError as e:
                assert "[source]" in str(e)

    def test_invalid_source_type_raises(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(INVALID_TYPE_TOML)

            try:
                load_docs_config(d)
                assert False, "Should have raised DocsConfigError"
            except DocsConfigError as e:
                assert "javascript" in str(e)

    def test_invalid_provider_raises(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(INVALID_PROVIDER_TOML)

            try:
                load_docs_config(d)
                assert False, "Should have raised DocsConfigError"
            except DocsConfigError as e:
                assert "netlify" in str(e)

    def test_cloudflare_missing_project_raises(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(CLOUDFLARE_MISSING_PROJECT_TOML)

            try:
                load_docs_config(d)
                assert False, "Should have raised DocsConfigError"
            except DocsConfigError as e:
                assert "deploy.project" in str(e)

    def test_empty_paths_raises(self):
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(EMPTY_PATHS_TOML)

            try:
                load_docs_config(d)
                assert False, "Should have raised DocsConfigError"
            except DocsConfigError as e:
                assert "paths" in str(e)


class TestPythonExtraction:
    """Tests for Python docstring extraction."""

    def test_extract_module_docstring(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            assert len(pages) == 1
            page = pages[0]
            assert page["module"] == "src.sample"
            assert page["docstring"] == "A sample module for testing documentation extraction."

    def test_extract_public_function(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            func_names = [f["name"] for f in page["functions"]]
            assert "public_function" in func_names

    def test_skip_private_without_doc(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            func_names = [f["name"] for f in page["functions"]]
            assert "_private_no_doc" not in func_names

    def test_include_private_with_doc(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            func_names = [f["name"] for f in page["functions"]]
            assert "_private_with_doc" in func_names

    def test_extract_class_and_methods(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            class_names = [c["name"] for c in page["classes"]]
            assert "PublicClass" in class_names

            pub_class = next(c for c in page["classes"] if c["name"] == "PublicClass")
            assert pub_class["docstring"] == "A documented public class."
            method_names = [m["name"] for m in pub_class["methods"]]
            assert "method_one" in method_names
            assert "method_two" in method_names
            # Private method without docstring should be skipped
            assert "_private_method" not in method_names

    def test_private_class_with_doc_included(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            class_names = [c["name"] for c in page["classes"]]
            assert "_PrivateClass" in class_names

    def test_undocumented_class_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sample.py"), "w") as f:
                f.write(SAMPLE_MODULE)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            class_names = [c["name"] for c in page["classes"]]
            assert "UndocumentedClass" not in class_names

    def test_empty_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "empty.py"), "w") as f:
                f.write(SAMPLE_EMPTY)

            pages = extract_python_docs(["src/"], d)
            assert len(pages) == 0

    def test_init_file_module_name(self):
        with tempfile.TemporaryDirectory() as d:
            pkg_dir = os.path.join(d, "src", "mypkg")
            os.makedirs(pkg_dir)
            with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
                f.write(SAMPLE_INIT)

            pages = extract_python_docs(["src/"], d)
            assert len(pages) == 1
            assert pages[0]["module"] == "src.mypkg"

    def test_nonexistent_path_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            pages = extract_python_docs(["nonexistent/"], d)
            assert pages == []

    def test_multiple_paths(self):
        with tempfile.TemporaryDirectory() as d:
            src1 = os.path.join(d, "src")
            src2 = os.path.join(d, "lib")
            os.makedirs(src1)
            os.makedirs(src2)
            with open(os.path.join(src1, "a.py"), "w") as f:
                f.write('"""Module A."""\n')
            with open(os.path.join(src2, "b.py"), "w") as f:
                f.write('"""Module B."""\n')

            pages = extract_python_docs(["src/", "lib/"], d)
            modules = [p["module"] for p in pages]
            assert "src.a" in modules
            assert "lib.b" in modules


class TestSignatureExtraction:
    """Tests for function signature building."""

    def test_simple_signature(self):
        with tempfile.TemporaryDirectory() as d:
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "sigs.py"), "w") as f:
                f.write(SAMPLE_SIGNATURES)

            pages = extract_python_docs(["src/"], d)
            page = pages[0]
            funcs = {f["name"]: f for f in page["functions"]}

            assert funcs["simple"]["signature"] == "()"
            assert funcs["positional"]["signature"] == "(a, b, c)"
            assert funcs["defaults"]["signature"] == "(a, b=10, c='hello')"
            assert funcs["varargs"]["signature"] == "(*args, **kwargs)"
            assert funcs["annotated"]["signature"] == "(x: int, y: str='world') -> bool"
            assert funcs["keyword_only"]["signature"] == "(a, *, key: str, flag: bool=False)"
            assert funcs["async_func"]["signature"] == "(data: list) -> None"


class TestPathToModule:
    """Tests for path-to-module-name conversion."""

    def test_regular_file(self):
        assert _path_to_module("rlsbl/commands/release.py") == "rlsbl.commands.release"

    def test_init_file(self):
        assert _path_to_module("rlsbl/__init__.py") == "rlsbl"

    def test_single_file(self):
        assert _path_to_module("main.py") == "main"

    def test_nested_init(self):
        assert _path_to_module("a/b/c/__init__.py") == "a.b.c"


class TestDocsTargetProtocol:
    """Tests for DocsTarget class conformance and behavior."""

    def test_is_release_target(self):
        target = DocsTarget()
        assert isinstance(target, ReleaseTarget)

    def test_name(self):
        target = DocsTarget()
        assert target.name == "docs"

    def test_scope(self):
        target = DocsTarget()
        assert target.scope == "root"

    def test_version_file_none(self):
        target = DocsTarget()
        assert target.version_file() is None

    def test_tag_format_none(self):
        target = DocsTarget()
        assert target.tag_format(None, "1.0.0") is None

    def test_read_version_fallback(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.read_version(d) == "0.0.0"

    def test_write_version_noop(self):
        """write_version should complete without error."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            target.write_version(d, "1.0.0")  # Should not raise

    def test_detect_true(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(VALID_DOCS_TOML)
            assert target.detect(d) is True

    def test_detect_false(self):
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            assert target.detect(d) is False

    def test_registered_in_targets(self):
        assert "docs" in TARGETS
        assert isinstance(TARGETS["docs"], DocsTarget)

    def test_build_with_no_config(self):
        """build() should return None gracefully when no config exists."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            result = target.build(d, "1.0.0")
            assert result is None

    def test_build_extracts_pages(self):
        """build() should extract pages when config and sources exist."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            # Set up config
            rlsbl_dir = os.path.join(d, ".rlsbl")
            os.makedirs(rlsbl_dir)
            with open(os.path.join(rlsbl_dir, "docs.toml"), "w") as f:
                f.write(VALID_DOCS_TOML)

            # Set up source
            src_dir = os.path.join(d, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "example.py"), "w") as f:
                f.write('"""Example module."""\n\ndef foo():\n    """A function."""\n    pass\n')

            pages = target.build(d, "1.0.0")
            assert pages is not None
            assert len(pages) == 1
            assert pages[0]["module"] == "src.example"

    def test_publish_noop(self):
        """publish() should complete without error."""
        target = DocsTarget()
        with tempfile.TemporaryDirectory() as d:
            target.publish(d, "1.0.0")  # Should not raise
