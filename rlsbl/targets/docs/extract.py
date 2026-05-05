"""Python source extraction -- docstrings and signatures via stdlib ast."""

import ast
import os


def extract_python_docs(paths, base_dir="."):
    """Extract documentation from Python source files.

    Walks each path (relative to base_dir), finds .py files, parses with ast,
    and extracts module/class/function docstrings preserving hierarchy.

    Args:
        paths: List of directory paths to scan (relative to base_dir).
        base_dir: Root directory for resolving relative paths.

    Returns:
        List of page dicts, one per module:
        [
            {
                "module": "rlsbl.commands.release",
                "path": "rlsbl/commands/release.py",
                "docstring": "Release command...",
                "classes": [
                    {"name": "...", "docstring": "...", "methods": [...]}
                ],
                "functions": [
                    {"name": "run_cmd", "docstring": "...", "signature": "..."}
                ]
            }
        ]

    Items without docstrings are skipped. Private members (names starting with
    '_') are included only if they have a docstring.
    """
    pages = []
    for search_path in paths:
        abs_path = os.path.join(base_dir, search_path)
        if not os.path.exists(abs_path):
            continue

        for root, _dirs, files in os.walk(abs_path):
            for filename in sorted(files):
                if not filename.endswith(".py"):
                    continue
                filepath = os.path.join(root, filename)
                page = _extract_file(filepath, base_dir)
                if page:
                    pages.append(page)

    return pages


def _extract_file(filepath, base_dir):
    """Extract documentation from a single Python file.

    Returns a page dict, or None if the file has no documentable content.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None

    module_doc = ast.get_docstring(tree)
    classes = []
    functions = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls = _extract_class(node)
            if cls:
                classes.append(cls)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = _extract_function(node)
            if func:
                functions.append(func)

    # Skip files with no documentation at all
    if not module_doc and not classes and not functions:
        return None

    # Compute module name from relative path
    rel_path = os.path.relpath(filepath, base_dir)
    module_name = _path_to_module(rel_path)

    return {
        "module": module_name,
        "path": rel_path,
        "docstring": module_doc,
        "classes": classes,
        "functions": functions,
    }


def _extract_class(node):
    """Extract class info including its methods.

    Skips private classes unless they have a docstring.
    """
    docstring = ast.get_docstring(node)

    # Skip private classes without docstrings
    if node.name.startswith("_") and not docstring:
        return None

    methods = []
    for item in ast.iter_child_nodes(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method = _extract_function(item)
            if method:
                methods.append(method)

    # Skip undocumented classes with no documented methods
    if not docstring and not methods:
        return None

    return {
        "name": node.name,
        "docstring": docstring,
        "methods": methods,
    }


def _extract_function(node):
    """Extract function/method info.

    Skips private functions unless they have a docstring.
    """
    docstring = ast.get_docstring(node)

    # Skip private functions without docstrings
    if node.name.startswith("_") and not docstring:
        return None

    # Skip undocumented public functions too
    if not docstring:
        return None

    signature = _build_signature(node)

    return {
        "name": node.name,
        "docstring": docstring,
        "signature": signature,
    }


def _build_signature(node):
    """Build a human-readable function signature from ast.arguments.

    Produces something like: (self, x, y=None, *args, **kwargs)
    """
    args = node.args
    parts = []

    # Positional-only args (before /)
    posonlyargs = getattr(args, "posonlyargs", [])

    # Regular positional args
    all_positional = posonlyargs + args.args

    # Defaults are right-aligned to args
    num_defaults = len(args.defaults)
    num_positional = len(all_positional)

    for i, arg in enumerate(all_positional):
        name = arg.arg
        annotation = _annotation_str(arg.annotation)
        if annotation:
            part = f"{name}: {annotation}"
        else:
            part = name

        # Check if this arg has a default
        default_idx = i - (num_positional - num_defaults)
        if default_idx >= 0:
            default = _literal_repr(args.defaults[default_idx])
            part += f"={default}"

        parts.append(part)

    # Insert / separator for positional-only args
    if posonlyargs:
        parts.insert(len(posonlyargs), "/")

    # *args
    if args.vararg:
        annotation = _annotation_str(args.vararg.annotation)
        if annotation:
            parts.append(f"*{args.vararg.arg}: {annotation}")
        else:
            parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        # Bare * separator when there are keyword-only args but no *args
        parts.append("*")

    # Keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        annotation = _annotation_str(arg.annotation)
        if annotation:
            part = f"{name}: {annotation}"
        else:
            part = name

        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = _literal_repr(args.kw_defaults[i])
            part += f"={default}"

        parts.append(part)

    # **kwargs
    if args.kwarg:
        annotation = _annotation_str(args.kwarg.annotation)
        if annotation:
            parts.append(f"**{args.kwarg.arg}: {annotation}")
        else:
            parts.append(f"**{args.kwarg.arg}")

    # Return annotation
    ret = _annotation_str(node.returns)
    sig = f"({', '.join(parts)})"
    if ret:
        sig += f" -> {ret}"

    return sig


def _annotation_str(node):
    """Convert an annotation AST node to a string, or empty string if None."""
    if node is None:
        return ""
    return ast.unparse(node)


def _literal_repr(node):
    """Convert a default-value AST node to a readable string."""
    if node is None:
        return "None"
    return ast.unparse(node)


def _path_to_module(rel_path):
    """Convert a relative file path to a dotted module name.

    'rlsbl/commands/release.py' -> 'rlsbl.commands.release'
    'rlsbl/__init__.py' -> 'rlsbl'
    """
    # Normalize separators
    rel_path = rel_path.replace(os.sep, "/")

    # Strip .py extension
    if rel_path.endswith(".py"):
        rel_path = rel_path[:-3]

    # Strip trailing /__init__
    if rel_path.endswith("/__init__"):
        rel_path = rel_path[: -len("/__init__")]

    return rel_path.replace("/", ".")
