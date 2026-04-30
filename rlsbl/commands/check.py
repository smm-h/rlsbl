"""Check command: check package name availability on npm or PyPI."""

import re
import subprocess
import sys
import urllib.request
import urllib.error


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
            capture_output=True, text=True, check=True,
        )
        return {"status": "taken"}
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

    # Check variants for similarity; skip variants that error
    variants = get_npm_variants(name)
    similar = []
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

    # Check variants for similarity (PEP 503 normalization); skip variants that error
    variants = get_pypi_variants(name)
    similar = []
    for variant in variants:
        if variant == name:
            continue
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


def run_cmd(registry, args, flags):
    """Check command handler.

    Checks package name availability on npm or PyPI, and warns about similar names.
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
    else:
        _check_name_pypi(name)
