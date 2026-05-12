"""Check command: check package name availability on npm, PyPI, Go (pkg.go.dev), and GitHub."""

import json
import re
import subprocess
import sys
import urllib.request
import urllib.error

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _HAS_THREADS = True
except ImportError:
    _HAS_THREADS = False


from rlsbl.targets.utils import normalize_pypi  # noqa: E402


def check_npm_availability(name):
    """Check if an npm package name is available.

    Returns {"status": "available"|"taken"|"error", "message"?: str}.
    Distinguishes 404 (truly available) from network/other errors.
    """
    try:
        subprocess.run(
            ["npm", "view", name, "name"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        return {"status": "taken"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "npm view timed out"}
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if "E404" in stderr or "404" in stderr:
            return {"status": "available"}
        return {"status": "error", "message": stderr.strip() or "Unknown error checking npm"}
    except FileNotFoundError:
        return {"status": "error", "message": "npm CLI not found"}


def get_npm_variants(name):
    """Generate common npm name variants for similarity checking."""
    variants = set()
    lower = name.lower()
    variants.add(lower)
    variants.add(lower.replace("_", "-"))
    variants.add(lower.replace("-", "_"))
    variants.add(re.sub(r"[-_]", "", lower))
    variants.add(re.sub(r"[-_]", ".", lower))

    # Remove the original name itself from the set
    variants.discard(name)

    return list(variants)


def check_pypi_availability(name):
    """Check if a PyPI package name is available.

    Returns {"status": "available"|"taken"|"error", "message"?: str}.
    Distinguishes 404 (truly available) from network/other errors.
    """
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"status": "taken"}
            return {"status": "error", "message": f"Unexpected status {resp.status}"}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "available"}
        return {"status": "error", "message": f"Unexpected status {e.code}"}
    except Exception as e:
        return {"status": "error", "message": str(e) or "Network error"}


def get_pypi_variants(name):
    """Generate common PyPI name variants for similarity checking."""
    normalized = normalize_pypi(name)
    lower = name.lower()
    variants = set()
    variants.add(normalized)
    variants.add(re.sub(r"[-_.]+", "_", lower))
    variants.add(re.sub(r"[-_.]+", "-", lower))
    variants.add(re.sub(r"[-_.]+", "", lower))

    # Remove the original name itself
    variants.discard(name)

    return list(variants)


def check_go_availability(name):
    """Check if a Go module path exists on pkg.go.dev.

    Returns {"status": "not_found"|"exists"|"error", "message"?: str, "note"?: str}.

    Go modules use repository paths (e.g. github.com/user/repo), not a flat
    claimable namespace, so we report "not found" / "exists" rather than the
    "available" / "taken" language used for npm and PyPI.
    """
    url = f"https://pkg.go.dev/{name}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"status": "exists"}
            return {"status": "error", "message": f"Unexpected status {resp.status}"}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "not_found",
                "note": "Go modules use repository paths, not a central registry.",
            }
        return {"status": "error", "message": f"Unexpected status {e.code}"}
    except Exception as e:
        return {"status": "error", "message": str(e) or "Network error"}


def check_github_availability(name):
    """Check if a repository name exists on GitHub.

    Searches the GitHub API for repositories with the given name.
    Returns {"status": "available"|"exists"|"error", "count": int, ...}.
    """
    url = f"https://api.github.com/search/repositories?q={name}+in:name"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "rlsbl-cli")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            count = data.get("total_count", 0)
            if count == 0:
                return {"status": "available", "count": 0}
            return {
                "status": "exists",
                "count": count,
                "note": f"{count} repos with this name on GitHub",
            }
    except Exception as e:
        return {"status": "error", "message": str(e) or "Network error"}


def _check_variants(name, check_fn, get_variants_fn):
    """Check name variants for similarity using the given availability checker.

    Returns a list of variant names that are taken/exist.
    """
    variants = [v for v in get_variants_fn(name) if v != name]
    similar = []

    if _HAS_THREADS and variants:
        try:
            with ThreadPoolExecutor(max_workers=len(variants)) as executor:
                future_to_variant = {
                    executor.submit(check_fn, v): v
                    for v in variants
                }
                for future in as_completed(future_to_variant):
                    variant = future_to_variant[future]
                    try:
                        var_result = future.result()
                        if var_result["status"] == "taken":
                            similar.append(variant)
                    except Exception:
                        pass  # Skip variants that error
        except Exception:
            # Fall back to sequential on any thread pool error
            similar = []
            for variant in variants:
                var_result = check_fn(variant)
                if var_result["status"] == "taken":
                    similar.append(variant)
    else:
        for variant in variants:
            var_result = check_fn(variant)
            if var_result["status"] == "taken":
                similar.append(variant)

    return similar


def _check_single_name(name, registry):
    """Check a single name on a given registry, returning a structured result.

    Returns a dict with keys:
        - name: the package name checked
        - registry: which registry was checked
        - status: "available", "taken", "exists", "not_found", or "error"
        - variants: list of similar names that are taken (npm/pypi only)
        - github_count: number of GitHub repos with this name (or None on error)
        - error: error message if status is "error" (absent otherwise)
        - note: informational note (go only, absent otherwise)
    """
    result = {"name": name, "registry": registry, "variants": []}

    # Registry-specific availability check
    if registry == "npm":
        check_result = check_npm_availability(name)
        result["status"] = check_result["status"]
        if check_result["status"] == "error":
            result["error"] = check_result["message"]
        else:
            result["variants"] = _check_variants(name, check_npm_availability, get_npm_variants)

    elif registry == "pypi":
        check_result = check_pypi_availability(name)
        result["status"] = check_result["status"]
        if check_result["status"] == "error":
            result["error"] = check_result["message"]
        else:
            result["variants"] = _check_variants(name, check_pypi_availability, get_pypi_variants)

    elif registry == "go":
        check_result = check_go_availability(name)
        result["status"] = check_result["status"]
        if check_result["status"] == "error":
            result["error"] = check_result["message"]
        if check_result.get("note"):
            result["note"] = check_result["note"]

    # GitHub informational check
    gh_result = check_github_availability(name)
    if gh_result["status"] != "error":
        result["github_count"] = gh_result.get("count", 0)
    else:
        result["github_count"] = None

    return result


def _format_single_result(result):
    """Print the verbose output for a single name check result.

    Reproduces the original detailed output format with variant warnings and
    GitHub info.
    """
    name = result["name"]
    registry = result["registry"]
    status = result["status"]

    # Registry-specific status output
    if registry == "npm":
        print(f'Checking npm for "{name}"...')
        if status == "error":
            print(f"Error checking npm: {result['error']}", file=sys.stderr)
            sys.exit(1)
        if status == "available":
            print(f'"{name}" is available on npm.')
        else:
            print(f'"{name}" is taken on npm.')

    elif registry == "pypi":
        print(f'Checking PyPI for "{name}"...')
        if status == "error":
            print(f"Error checking PyPI: {result['error']}", file=sys.stderr)
            sys.exit(1)
        if status == "available":
            print(f'"{name}" is available on PyPI.')
        else:
            print(f'"{name}" is taken on PyPI.')

    elif registry == "go":
        print(f'Checking pkg.go.dev for "{name}"...')
        if status == "error":
            print(f"Error checking pkg.go.dev: {result['error']}", file=sys.stderr)
            sys.exit(1)
        if status == "not_found":
            print(f'"{name}" not found on pkg.go.dev.')
        else:
            print(f'"{name}" exists on pkg.go.dev.')
        if result.get("note"):
            print(f"  Note: {result['note']}")

    # Variant warnings (npm/pypi only)
    available = status in ("available", "not_found")
    variants = result.get("variants", [])
    if variants:
        print("\nSimilar names already taken:")
        for s in variants:
            print(f"  {s}")
        if available:
            print(
                "\nYour name is available but has similar existing packages. "
                "Consider if this could cause confusion."
            )

    # GitHub informational
    github_count = result.get("github_count")
    if github_count is not None:
        if github_count == 0:
            print(f"\n  (i) No GitHub repos named \"{name}\")")
        else:
            print(f"\n  (i) {github_count} GitHub repo(s) named \"{name}\" (informational, not a registry)")


def _format_table_row(result):
    """Return a compact one-line dict suitable for table rendering.

    Keys: name, status. The status is a short human-readable string.
    """
    name = result["name"]
    status = result["status"]
    registry = result["registry"]

    if status == "error":
        display_status = "error"
    elif registry == "go":
        display_status = "not found" if status == "not_found" else "exists"
    else:
        display_status = status  # "available" or "taken"

    return {"name": name, "status": display_status}


def run_cmd(registry, args, flags):
    """Check command handler.

    Checks package name availability on npm, PyPI, or Go, and warns about similar names.
    """
    name = args[0] if args else None
    if not name:
        print(
            "Error: missing package name. Usage: rlsbl check <name>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = _check_single_name(name, registry)
    _format_single_result(result)
