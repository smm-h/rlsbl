"""Check command: check package name availability on npm, PyPI, Go (pkg.go.dev), and GitHub."""

import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _HAS_THREADS = True
except ImportError:
    _HAS_THREADS = False


from itertools import product  # noqa: E402

from rlsbl.targets.utils import normalize_pypi  # noqa: E402


def _request_with_backoff(url, timeout=5, max_retries=3):
    """Wrap urllib.request.urlopen with retry logic for HTTP 429 responses.

    On HTTP 429 (Too Many Requests): reads the Retry-After header (seconds).
    If present, sleeps that long. If absent, uses exponential backoff starting
    at 2 seconds (2, 4, 8, ...).

    On other HTTP errors or non-HTTP errors (URLError, timeout): raises
    immediately without retrying.

    Returns the response object on success, or raises the last exception after
    exhausting retries.
    """
    req = urllib.request.Request(url, method="GET")
    # GitHub API requires a User-Agent header
    if "api.github.com" in url:
        req.add_header("User-Agent", "rlsbl-cli")

    last_exc = None
    for attempt in range(max_retries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                last_exc = e
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if retry_after is not None:
                    delay = float(retry_after)
                else:
                    delay = 2 ** (attempt + 1)
                time.sleep(delay)
            else:
                raise
    raise last_exc


def _ultranormalize(name):
    """Ultranormalize a package name for typosquatting detection.

    Strips all separators (-, _, .), replaces visually ambiguous characters
    (l, L, i, I -> 1; o, O -> 0), and lowercases the result.
    """
    stripped = re.sub(r"[-_.]", "", name)
    result = []
    for ch in stripped:
        if ch in ("l", "L", "i", "I"):
            result.append("1")
        elif ch in ("o", "O"):
            result.append("0")
        else:
            result.append(ch.lower())
    return "".join(result)


_ULTRANORM_VARIANT_CAP = 64


def _generate_ultranorm_variants(name):
    """Generate name variants that share the same ultranormalized form.

    Starting from the PEP 503 normalized form (lowercase, separators normalized),
    produces all combinations of ambiguous character substitutions:
      l <-> 1, o <-> 0, i <-> 1
    Returns up to 64 variants, excluding the original name itself.
    """
    normalized = normalize_pypi(name)
    # Build a list of character options per position
    char_options = []
    for ch in normalized:
        if ch in ("l", "1"):
            char_options.append(("l", "1"))
        elif ch in ("o", "0"):
            char_options.append(("o", "0"))
        elif ch == "i":
            char_options.append(("i", "1"))
        else:
            char_options.append((ch,))

    # Count total combinations without materializing
    total = 1
    for opts in char_options:
        total *= len(opts)

    if total > _ULTRANORM_VARIANT_CAP:
        print(
            f"Warning: {total} ultranorm variants for '{name}', "
            f"capping at {_ULTRANORM_VARIANT_CAP}",
            file=sys.stderr,
        )

    variants = []
    for combo in product(*char_options):
        if len(variants) >= _ULTRANORM_VARIANT_CAP:
            break
        variant = "".join(combo)
        if variant != normalized:
            variants.append(variant)

    return variants


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

    Uses the Simple API (PEP 503) which correctly returns 200 for registered
    packages even if they have no releases (unlike the JSON API which 404s).

    Returns {"status": "available"|"taken"|"error", "message"?: str}.
    Distinguishes 404 (truly available) from network/other errors.
    """
    normalized = normalize_pypi(name)
    url = f"https://pypi.org/simple/{normalized}/"
    try:
        with _request_with_backoff(url, timeout=5) as resp:
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
        with _request_with_backoff(url, timeout=5) as resp:
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
        with _request_with_backoff(url, timeout=5) as resp:
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


def _check_stdlib_collision(name):
    """Check if a name collides with a Python standard library module.

    PEP 503 normalizes both the candidate and each stdlib name, then compares.
    Returns the stdlib module name on collision, or None.
    """
    normalized = normalize_pypi(name)
    for module in sys.stdlib_module_names:
        if normalize_pypi(module) == normalized:
            return module
    return None


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
        stdlib_module = _check_stdlib_collision(name)
        if stdlib_module is not None:
            result["status"] = "taken"
            result["note"] = f"conflicts with Python stdlib module '{stdlib_module}'"
        else:
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
        if result.get("note"):
            print(f"  Note: {result['note']}")

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
    Accepts one or more package names as positional arguments.
    """
    names = args if args else []
    if not names:
        print(
            "Error: missing package name(s). Usage: rlsbl check <name> [<name2> ...] --target <npm|pypi|go>",
            file=sys.stderr,
        )
        sys.exit(1)

    delay_ms = int(flags.get("delay", "200"))

    if len(names) == 1:
        result = _check_single_name(names[0], registry)
        _format_single_result(result)
    else:
        rows = []
        for i, name in enumerate(names):
            result = _check_single_name(name, registry)
            rows.append(_format_table_row(result))
            if i < len(names) - 1:
                time.sleep(delay_ms / 1000)

        # Compute column widths for aligned output
        name_width = max(len(row["name"]) for row in rows)
        name_width = max(name_width, len("Name"))

        print(f"{'Name':<{name_width}}  Status")
        for row in rows:
            print(f"{row['name']:<{name_width}}  {row['status']}")
