"""AST-based library lint module.

Analyzes Python source files for library boundary violations:
entry-point declarations, forbidden imports (CLI/web frameworks),
and stdout/logging usage.
"""

import ast
import os
import re
import sys
import tomllib
from collections import namedtuple
from pathlib import Path

LintResult = namedtuple("LintResult", ["file", "line", "rule", "severity", "message"])

FORBIDDEN_MODULES = frozenset({
    "argparse", "click", "typer",
    "flask", "fastapi", "django",
    "uvicorn", "granian", "starlette",
    "tornado", "bottle",
})

# Patterns for test file exclusion
_TEST_FILENAME_RE = re.compile(r"^(test_.*|.*_test|conftest)\.py$")


def _is_test_file(filepath):
    """Return True if the file should be excluded as a test file."""
    parts = Path(filepath).parts
    # Check if any directory component is 'test' or 'tests'
    for part in parts:
        if part in ("test", "tests"):
            return True
    # Check filename pattern
    return bool(_TEST_FILENAME_RE.match(os.path.basename(filepath)))


def _load_ignore_list(project_path):
    """Load the ignore list from .rlsbl/lint.toml if it exists."""
    lint_toml = os.path.join(project_path, ".rlsbl", "lint.toml")
    if not os.path.isfile(lint_toml):
        return set()
    try:
        with open(lint_toml, "rb") as f:
            data = tomllib.load(f)
        return set(data.get("ignore", []))
    except Exception:
        return set()


def _check_entry_points(project_path, ignore):
    """Check for CLI entry point declarations in pyproject.toml."""
    pyproject_path = os.path.join(project_path, "pyproject.toml")
    if not os.path.isfile(pyproject_path):
        return []

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []

    results = []
    project = data.get("project", {})
    for section_key in ("scripts", "gui-scripts"):
        entries = project.get(section_key, {})
        for name in entries:
            if name not in ignore:
                results.append(LintResult(
                    file=pyproject_path,
                    line=0,
                    rule="entry-point",
                    severity="error",
                    message=f"Library declares CLI entry point '{name}'",
                ))
    return results


class _SourceVisitor(ast.NodeVisitor):
    """AST visitor that collects forbidden-import and stdout violations."""

    def __init__(self, filepath, ignore):
        self.filepath = filepath
        self.ignore = ignore
        self.results = []

    def visit_Import(self, node):
        for alias in node.names:
            top_level = alias.name.split(".")[0]
            if top_level in FORBIDDEN_MODULES and top_level not in self.ignore:
                self.results.append(LintResult(
                    file=self.filepath,
                    line=node.lineno,
                    rule="forbidden-import",
                    severity="error",
                    message=f"Library imports interface module '{top_level}'",
                ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            top_level = node.module.split(".")[0]
            if top_level in FORBIDDEN_MODULES and top_level not in self.ignore:
                self.results.append(LintResult(
                    file=self.filepath,
                    line=node.lineno,
                    rule="forbidden-import",
                    severity="error",
                    message=f"Library imports interface module '{top_level}'",
                ))
        self.generic_visit(node)

    def visit_Call(self, node):
        # print() calls
        if (isinstance(node.func, ast.Name)
                and node.func.id == "print"
                and "print" not in self.ignore):
            self.results.append(LintResult(
                file=self.filepath,
                line=node.lineno,
                rule="stdout",
                severity="error",
                message="Library calls print()",
            ))

        # sys.stdout.write() / sys.stderr.write()
        if (isinstance(node.func, ast.Attribute)
                and node.func.attr == "write"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr in ("stdout", "stderr")
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "sys"
                and "sys" not in self.ignore):
            stream = node.func.value.attr
            self.results.append(LintResult(
                file=self.filepath,
                line=node.lineno,
                rule="stdout",
                severity="error",
                message=f"Library writes to sys.{stream}",
            ))

        # logging.* calls
        if (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logging"
                and "logging" not in self.ignore):
            self.results.append(LintResult(
                file=self.filepath,
                line=node.lineno,
                rule="stdout",
                severity="warning",
                message="Library uses logging directly",
            ))

        self.generic_visit(node)


def _walk_python_files(project_path):
    """Yield relative paths of .py files under project_path, excluding test files."""
    for dirpath, _dirnames, filenames in os.walk(project_path):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, project_path)
            if _is_test_file(rel):
                continue
            yield full


def _check_source_files(project_path, ignore):
    """Parse and lint all non-test .py files under project_path."""
    results = []
    for filepath in _walk_python_files(project_path):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            print(f"Warning: could not parse {filepath}", file=sys.stderr)
            continue

        visitor = _SourceVisitor(filepath, ignore)
        visitor.visit(tree)
        results.extend(visitor.results)
    return results


def lint_library(project_path):
    """Analyze a Python project for library boundary violations.

    Args:
        project_path: path to the project root directory.

    Returns a list of LintResult namedtuples.
    """
    project_path = os.path.abspath(project_path)
    ignore = _load_ignore_list(project_path)

    results = []
    results.extend(_check_entry_points(project_path, ignore))
    results.extend(_check_source_files(project_path, ignore))
    return results
