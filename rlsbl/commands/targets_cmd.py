"""Targets command: list available release targets and their detection status."""

import sys

from ..targets import TARGETS, detect_targets


def run_cmd(registry, args, flags):
    """List all available targets with their scope, detection status, and version file."""
    dir_path = flags.get("scope", ".")
    detected = detect_targets(dir_path)

    # Column headers
    headers = ("Target", "Scope", "Detected", "Version file")

    # Build rows
    rows = []
    for name, target in TARGETS.items():
        is_detected = "yes" if name in detected else "no"
        vfile = target.version_file() or "(none)"
        rows.append((name, target.scope, is_detected, vfile))

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Format and print
    def fmt_row(cells):
        return "   ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(fmt_row(headers))
    for row in rows:
        print(fmt_row(row))
