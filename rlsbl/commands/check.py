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


def normalize_npm(name):
    """Normalize an npm package name for similarity comparison.

    Strips hyphens, underscores, dots, and lowercases.
    """
    return re.sub(r"[-_.]", "", name.lower())


def normalize_pypi(name):
    """Normalize a PyPI package name per PEP 503.

    Lowercases and replaces runs of [-_.] with a single hyphen.
    """
    return re.sub(r"[-_.]+", "-", name.lower())


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


def _check_name_npm(name):
    """Check npm availability and report similar names."""
    print(f'Checking npm for "{name}"...')

    result = check_npm_availability(name)
    if result["status"] == "error":
        print(f"Error checking npm: {result['message']}", file=sys.stderr)
        sys.exit(1)
    available = result["status"] == "available"
    if available:
        print(f'"{name}" is available on npm.')
    else:
        print(f'"{name}" is taken on npm.')

    # Check variants for similarity in parallel; skip variants that error
    variants = get_npm_variants(name)
    similar = []

    if _HAS_THREADS and variants:
        try:
            with ThreadPoolExecutor(max_workers=len(variants)) as executor:
                future_to_variant = {
                    executor.submit(check_npm_availability, v): v
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
                var_result = check_npm_availability(variant)
                if var_result["status"] == "taken":
                    similar.append(variant)
    else:
        for variant in variants:
            var_result = check_npm_availability(variant)
            if var_result["status"] == "taken":
                similar.append(variant)

    if similar:
        print("\nSimilar names already taken:")
        for s in similar:
            print(f"  {s}")
        if available:
            print(
                "\nYour name is available but has similar existing packages. "
                "Consider if this could cause confusion."
            )


def _check_name_pypi(name):
    """Check PyPI availability and report similar names."""
    print(f'Checking PyPI for "{name}"...')

    result = check_pypi_availability(name)
    if result["status"] == "error":
        print(f"Error checking PyPI: {result['message']}", file=sys.stderr)
        sys.exit(1)
    available = result["status"] == "available"
    if available:
        print(f'"{name}" is available on PyPI.')
    else:
        print(f'"{name}" is taken on PyPI.')

    # Check variants for similarity (PEP 503 normalization) in parallel; skip variants that error
    variants = [v for v in get_pypi_variants(name) if v != name]
    similar = []

    if _HAS_THREADS and variants:
        try:
            with ThreadPoolExecutor(max_workers=len(variants)) as executor:
                future_to_variant = {
                    executor.submit(check_pypi_availability, v): v
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
                var_result = check_pypi_availability(variant)
                if var_result["status"] == "taken":
                    similar.append(variant)
    else:
        for variant in variants:
            var_result = check_pypi_availability(variant)
            if var_result["status"] == "taken":
                similar.append(variant)

    if similar:
        print("\nSimilar names already taken:")
        for s in similar:
            print(f"  {s}")
        if available:
            print(
                "\nYour name is available but has similar existing packages. "
                "Consider if this could cause confusion."
            )


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


def _check_github(name):
    """Show GitHub repo count as informational context (not an availability check)."""
    result = check_github_availability(name)
    if result["status"] == "error":
        return
    count = result.get("count", 0)
    if count == 0:
        print(f"\n  (i) No GitHub repos named \"{name}\")")
    else:
        print(f"\n  (i) {count} GitHub repo(s) named \"{name}\" (informational, not a registry)")


def _check_name_go(name):
    """Check Go module path on pkg.go.dev."""
    print(f'Checking pkg.go.dev for "{name}"...')

    result = check_go_availability(name)
    if result["status"] == "error":
        print(f"Error checking pkg.go.dev: {result['message']}", file=sys.stderr)
        sys.exit(1)
    if result["status"] == "not_found":
        print(f'"{name}" not found on pkg.go.dev.')
    else:
        print(f'"{name}" exists on pkg.go.dev.')
    if result.get("note"):
        print(f"  Note: {result['note']}")


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

    if registry == "npm":
        _check_name_npm(name)
    elif registry == "pypi":
        _check_name_pypi(name)
    elif registry == "go":
        _check_name_go(name)

    # Always check GitHub for repos with this name
    _check_github(name)
