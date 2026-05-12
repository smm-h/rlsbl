# PyPI Name Availability Check: Accuracy Gaps

Status: Proposed
Priority: High

## Context

`rlsbl check <name> --target pypi` reports names as "available" that PyPI will actually reject. The check uses the JSON API (`pypi.org/pypi/{name}/json`) which returns 404 for empty/yanked projects and has no awareness of PyPI's multi-layered name validation. Real-world false positives discovered:

- `cli`: reported "available" but PyPI rejects as "too similar to an existing project" (ultranormalization collision with `cl1` and `cll`)
- `queue`: reported "available" but PyPI rejects as "conflict with Python standard library module name"
- `cost`: reported "available" but PyPI rejects as "project already exists" (project registered with no releases — JSON API returns 404, Simple API returns 200)
- `svg`: would report "available" but PyPI rejects as "isn't allowed" (prohibited names blocklist)
- `api`: reported "available" but PyPI rejects as "too similar" (ultranormalization: `api` → `ap1` collides with `ap1` and `APL`)

## PyPI's Validation Pipeline

PyPI's `check_project_name()` in `warehouse/packaging/services.py` runs 6 sequential checks. A name must pass ALL of them:

### Step 1: Format validation

Regex: `^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$` (case-insensitive). Must start and end with alphanumeric, only alphanumerics/dots/underscores/hyphens in between.

**Can we replicate?** Yes, trivially. Pure regex.

### Step 2: Standard library collision

Canonical name checked against all Python stdlib module names across all Python versions (using the `stdlib-list` package). Blocks names like `queue`, `email`, `html`, `json`, `io`, `os`, etc.

**Can we replicate?** Yes. `sys.stdlib_module_names` (Python 3.10+) gives the current version's set. For completeness, use the `stdlib-list` package which covers all Python versions.

### Step 3: Existing project (exact match)

PEP 426 normalized name checked against existing projects.

**Can we replicate?** Yes, but must use the **Simple API** (`pypi.org/simple/{name}/`), not the JSON API (`pypi.org/pypi/{name}/json`). The JSON API returns 404 for projects with no releases (like `cost`), while the Simple API correctly returns 200. This is the fix for the `cost` false positive.

### Step 4: Prohibited names blocklist

PEP 426 normalized name checked against a `prohibited_project_names` database table. This is managed by PyPI admins through a private admin interface. Contains manually blocked names like `svg` and likely other common technology terms.

**Can we replicate?** No. The table is not in the source code, not in BigQuery public datasets, not exposed via any API. Only discoverable by attempting to register and getting the "isn't allowed" error. Best we can do: warn that the name may be on the prohibited list.

### Step 5: Ultranormalization similarity

`ultranormalize_name(candidate)` compared against `ultranormalize_name(existing)` for all existing projects. The algorithm:

1. Strip all `.`, `_`, `-` characters
2. Replace `l`/`L`/`i`/`I` → `1` (visual similarity: l/I/1)
3. Replace `o`/`O` → `0` (visual similarity: O/0)
4. Lowercase

Examples:
- `cli` → `c11` (collides with `cl1` → `c11` and `cll` → `c11`)
- `api` → `ap1` (collides with `ap1` → `ap1` and `APL` → `ap1`)

**Can we replicate?** Yes. Download the Simple Index (`pypi.org/simple/`, ~40MB, lists all ~805K package names), ultranormalize every name, build a lookup set, check the candidate. Cache with a TTL (e.g., 24 hours) to avoid re-downloading.

### Step 6: Typo-squatting check

Five pattern-based checks against a hardcoded list of the top 200 most-depended-upon PyPI packages:

1. Repeated characters: `reequests` → `requests`
2. Omitted characters: insert allowed chars at each position (names 4+ chars only)
3. Swapped characters: transpose adjacent pairs (`spihnx` → `sphinx`)
4. Swapped words: permute hyphen-separated tokens (up to 8 tokens)
5. Common typos: keyboard-locality substitution map (QWERTY adjacency + visual similarity)

The top 200 list includes: numpy, requests, pytest, pandas, django, flask, fastapi, click, boto3, torch, etc. Full list is in `warehouse/packaging/typosnyper.py`.

**Can we replicate?** Yes. The algorithm and the top-200 corpus are in the open source warehouse code. We can port the 5 checks directly.

## Implementation Plan

### Immediate fixes (high impact, low effort)

1. **Switch from JSON API to Simple API** for the base availability check. `HEAD https://pypi.org/simple/{normalized_name}/` — 200 means taken, 404 means available at the basic level. Fixes the `cost` false positive.

2. **Add stdlib collision check.** Use `sys.stdlib_module_names` to check if the canonicalized name matches a stdlib module. Fixes the `queue` false positive.

### Medium-effort additions

3. **Add ultranormalization check.** Download and cache the Simple Index. Extract all package names, ultranormalize each, build a set. Ultranormalize the candidate and check for collisions. Report which existing package(s) conflict. Fixes the `cli` and `api` false positives.

4. **Add typo-squatting check.** Port the 5 pattern checks and the top-200 corpus from warehouse. Run them against the candidate name. Report which top package would be confused.

### Cannot replicate

5. **Prohibited names blocklist.** Not accessible. After all other checks pass, add a caveat: "Note: PyPI may still reject this name if it appears on the prohibited names list. This list is not publicly available."

## Affected Files

- `rlsbl/commands/check.py` — `check_pypi_availability()` function: switch to Simple API, add new checks
- `rlsbl/commands/check.py` — new helper functions for ultranormalization, stdlib check, typo-squatting
- `tests/test_check.py` — tests for each new validation step

## Effort Estimate

- Fixes 1-2: Small (switch URL + add stdlib set lookup)
- Fix 3: Medium (Simple Index download, caching, ultranormalization)
- Fix 4: Medium (port 5 pattern checks + 200-name corpus from warehouse)
- Total: Medium-large
