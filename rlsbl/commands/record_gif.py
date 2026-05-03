"""Record-gif command: record a demo GIF using vhs."""

import os
import shutil
import subprocess
import sys
import tempfile

from .. import detect_registries
from ..registries import REGISTRIES


def _get_bin_command():
    """Auto-detect the project's binary command name via registry template vars."""
    regs = detect_registries()
    if not regs:
        return None
    # Use the first detected registry
    registry_module = REGISTRIES.get(regs[0])
    if not registry_module:
        return None
    try:
        tvars = registry_module.get_template_vars(".")
        return tvars.get("binCommand") or None
    except Exception:
        return None


def run_cmd(registry, args, flags):
    """Record a demo GIF of '<binCommand> --help' using vhs.

    Requires vhs (https://github.com/charmbracelet/vhs) to be installed.
    Output is saved to assets/demo.gif.
    """
    if not shutil.which("vhs"):
        print("Error: vhs is required.", file=sys.stderr)
        print("Install: go install github.com/charmbracelet/vhs@latest", file=sys.stderr)
        sys.exit(1)

    bin_command = _get_bin_command()
    if not bin_command:
        print("Error: could not detect project binary command.", file=sys.stderr)
        print("Ensure package.json, pyproject.toml, or go.mod exists with a CLI entry point.", file=sys.stderr)
        sys.exit(1)

    assets_dir = "assets"
    os.makedirs(assets_dir, exist_ok=True)

    # Create a temporary VHS tape file in the project directory
    tape_content = (
        'Set FontFamily "monospace"\n'
        "Set FontSize 24\n"
        "Set Width 1200\n"
        "Set Height 600\n"
        "Set TypingSpeed 50ms\n"
        f'Type "{bin_command} --help"\n'
        "Enter\n"
        "Sleep 3s\n"
    )

    tape_fd, tape_path = tempfile.mkstemp(suffix=".tape", dir=".")
    try:
        with os.fdopen(tape_fd, "w") as f:
            f.write(tape_content)

        output_path = os.path.join(assets_dir, "demo.gif")
        print("Recording demo...")

        subprocess.run(
            ["vhs", tape_path, "-o", output_path],
            check=True, timeout=120,
        )

        print(f"Done. GIF saved to {output_path}")
    except subprocess.CalledProcessError:
        print("Error: vhs recording failed.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: vhs recording timed out after 120s.", file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up the temp tape file
        try:
            os.unlink(tape_path)
        except OSError:
            pass
