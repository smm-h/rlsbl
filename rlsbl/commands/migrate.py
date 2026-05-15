"""Migrate command that runs configuration schema migrations via the external migrable tool to upgrade project config to newer formats."""

import subprocess
import sys


def run_cmd(registry, args, flags):
    """Migrate command handler.

    Shells out to the external ``migrable`` CLI tool with the appropriate
    subcommand and flags.  Exits with migrable's exit code.
    """
    # Check that migrable is installed
    try:
        subprocess.run(
            ["migrable", "--version"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        print(
            "Error: migrable is not installed. Install with: "
            "go install github.com/smm-h/migrable/cmd/migrable@latest",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build the migrable command
    if flags.get("status"):
        cmd = ["migrable", "status", "--config-dir", ".rlsbl"]
    else:
        cmd = ["migrable", "migrate", "--config-dir", ".rlsbl"]
        if flags.get("dry-run"):
            cmd.insert(2, "--dry-run")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)
