"""Docs target -- thin wrapper delegating to the selfdoc CLI.

Detection is based on the presence of selfdoc.json in the project root.
Build and deploy are delegated entirely to the `selfdoc` CLI tool.
"""

import os
import subprocess

from ..base import BaseTarget


class DocsTarget(BaseTarget):
    """Release target that delegates documentation to selfdoc."""

    @property
    def name(self):
        return "docs"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        """True if selfdoc.json exists in the given directory."""
        return os.path.exists(os.path.join(dir_path, "selfdoc.json"))

    def read_version(self, dir_path):
        """Docs don't have their own version -- return fallback."""
        return "0.0.0"

    def write_version(self, dir_path, version):
        """No-op: docs inherit version from primary target."""
        pass

    def version_file(self):
        """No version file -- docs inherit from primary target."""
        return None

    def tag_format(self, name, version):
        """No separate tag -- uses primary target's tag."""
        return None

    def build(self, dir_path, version):
        """Delegate to selfdoc build."""
        subprocess.run(["selfdoc", "build"], cwd=dir_path, check=True, timeout=300)

    def publish(self, dir_path, version):
        """Delegate to selfdoc deploy."""
        subprocess.run(["selfdoc", "deploy"], cwd=dir_path, check=True, timeout=300)
