"""Tagging module: inject "rlsbl" keywords into manifests and GitHub topics."""

import json
import os
import re
import subprocess
import tomllib
import urllib.request
import urllib.error

from .utils import run


def ensure_npm_keyword(dir_path=".", quiet=False):
    """Add "rlsbl" to the keywords array in package.json if not already present."""
    pkg_path = os.path.join(dir_path, "package.json")
    with open(pkg_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Detect indent: look for the first indented line
    indent_match = re.search(r'^( +|\t+)"', raw, re.MULTILINE)
    indent = indent_match.group(1) if indent_match else "  "

    pkg = json.loads(raw)
    keywords = pkg.get("keywords", [])

    if "rlsbl" in keywords:
        return False

    keywords.append("rlsbl")
    pkg["keywords"] = keywords

    # Preserve trailing newline if present
    trailing_newline = "\n" if raw.endswith("\n") else ""
    output = json.dumps(pkg, indent=indent, ensure_ascii=False) + trailing_newline

    # Atomic write: write to temp file, then rename
    tmp_path = pkg_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(output)
    os.replace(tmp_path, pkg_path)

    if not quiet:
        print('Tagged package.json with "rlsbl" keyword')
    return True


def ensure_pypi_keyword(dir_path=".", quiet=False):
    """Add "rlsbl" to the keywords array in pyproject.toml if not already present."""
    toml_path = os.path.join(dir_path, "pyproject.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    # Check if already tagged
    existing = data.get("project", {}).get("keywords", [])
    if "rlsbl" in existing:
        return False

    # Read as text for regex-based editing
    with open(toml_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find [project] section boundaries
    project_match = re.search(r"^\[project\]\s*$", content, re.MULTILINE)
    if not project_match:
        raise ValueError("No [project] section found in pyproject.toml")

    section_start = project_match.end()
    next_section = re.search(r"^\[", content[section_start:], re.MULTILINE)
    section_end = section_start + next_section.start() if next_section else len(content)
    section = content[section_start:section_end]

    # Case 1: keywords field already exists -- add "rlsbl" to the array
    # Use DOTALL to handle multi-line arrays (e.g. keywords = [\n  "foo",\n])
    keywords_match = re.search(r'^(keywords\s*=\s*\[)(.*?)\]', section, re.MULTILINE | re.DOTALL)
    if keywords_match:
        prefix = keywords_match.group(1)
        array_content = keywords_match.group(2)
        # Detect if multi-line (contains newline between brackets)
        if "\n" in array_content:
            # Multi-line: insert before the closing bracket on its own line
            # Find the indent used for existing items
            item_indent_match = re.search(r'\n( +)"', array_content)
            item_indent = item_indent_match.group(1) if item_indent_match else "    "
            # Strip trailing comma to avoid double comma when the list
            # already has a trailing comma before the closing bracket
            stripped = array_content.rstrip()
            stripped = stripped.rstrip(",")
            new_array_content = stripped + f',\n{item_indent}"rlsbl"\n'
        else:
            # Single-line
            if array_content.strip():
                stripped_sl = array_content.rstrip().rstrip(",")
                new_array_content = stripped_sl + ', "rlsbl"'
            else:
                new_array_content = '"rlsbl"'
        new_field = prefix + new_array_content + "]"
        updated_section = section[:keywords_match.start()] + new_field + section[keywords_match.end():]
    else:
        # Case 2: keywords field missing -- insert after the version line
        version_match = re.search(r'^version\s*=\s*"[^"]*"\s*$', section, re.MULTILINE)
        if version_match:
            insert_pos = version_match.end()
        else:
            # Fallback: insert at the beginning of the section
            insert_pos = 0
        updated_section = (
            section[:insert_pos] + '\nkeywords = ["rlsbl"]' + section[insert_pos:]
        )

    updated = content[:section_start] + updated_section + content[section_end:]

    # Atomic write: write to temp file, then rename
    tmp_path = toml_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(updated)
    os.replace(tmp_path, toml_path)

    if not quiet:
        print('Tagged pyproject.toml with "rlsbl" keyword')
    return True


def ensure_github_topic(quiet=False):
    """Add "rlsbl" topic to the GitHub repository if not already present."""
    # Try to get a GitHub token (env var first, then gh CLI)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            token = run("gh", ["auth", "token"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    if not token:
        if not quiet:
            print("No GitHub token available. Run 'gh auth login' or set GITHUB_TOKEN.")
        return False

    # Detect repo name
    repo_name = None
    try:
        repo_name = run("gh", ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if not repo_name:
        # Fallback: parse from git remote
        try:
            remote_url = run("git", ["remote", "get-url", "origin"])
            match = re.search(r"github\.com[/:]([^/]+/[^/.]+)", remote_url)
            if match:
                repo_name = match.group(1).removesuffix(".git")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    if not repo_name:
        if not quiet:
            print("Warning: could not detect GitHub repository name.")
        return False

    owner, repo = repo_name.split("/", 1)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/topics"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "rlsbl-cli",
    }

    # GET existing topics
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        if not quiet:
            print(f"Warning: failed to fetch GitHub topics: {e}")
        return False

    topics = data.get("names", [])
    if "rlsbl" in topics:
        return False

    # PUT with merged topics list
    topics.append("rlsbl")
    payload = json.dumps({"names": topics}).encode("utf-8")
    try:
        req = urllib.request.Request(api_url, data=payload, headers=headers, method="PUT")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()  # consume response
    except (urllib.error.URLError, OSError) as e:
        if not quiet:
            print(f"Warning: failed to set GitHub topics: {e}")
        return False

    if not quiet:
        print('Added "rlsbl" topic to GitHub repository')
    return True


def ensure_tags(registries, dir_path=".", quiet=False):
    """Tag manifests and GitHub repo based on detected registries."""
    if "npm" in registries:
        ensure_npm_keyword(dir_path, quiet=quiet)
    if "pypi" in registries:
        ensure_pypi_keyword(dir_path, quiet=quiet)
    ensure_github_topic(quiet=quiet)
