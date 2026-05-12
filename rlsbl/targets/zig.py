"""Zig release target for rlsbl.

Zig projects use a VERSION file as the source of truth for rlsbl. The
.version field in build.zig.zon is synced on write. CI handles
cross-compilation; GitHub Release handles distribution.
"""

import os
import re

from .base import BaseTarget
from .zig_version import read_zig_version, write_zig_version

VERSION_FILE = "VERSION"
ZON_FILE = "build.zig.zon"
BUILD_ZIG_FILE = "build.zig"

_ZON_NAME_RE = re.compile(r'\.name\s*=\s*"([^"]+)"')
_ZON_MIN_ZIG_RE = re.compile(r'\.minimum_zig_version\s*=\s*"([^"]+)"')
_BUILD_EXE_RE = re.compile(r'(?:exe\(|addExecutable\()')


class ZigTarget(BaseTarget):
    """Release target for Zig projects (build.zig.zon + VERSION file)."""

    @property
    def name(self):
        return "zig"

    def detect(self, dir_path):
        """Return True if build.zig.zon exists, or build.zig as secondary."""
        if os.path.exists(os.path.join(dir_path, ZON_FILE)):
            return True
        return os.path.exists(os.path.join(dir_path, BUILD_ZIG_FILE))

    def read_version(self, dir_path):
        """Read version, delegating to zig_version helpers."""
        return read_zig_version(dir_path)

    def write_version(self, dir_path, version):
        """Write version, delegating to zig_version helpers."""
        write_zig_version(dir_path, version)

    def version_file(self):
        return VERSION_FILE

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "zig"
        )

    def read_name(self, dir_path):
        """Extract .name from build.zig.zon, or None."""
        return self._read_zon_field(dir_path, _ZON_NAME_RE)

    def _read_zon_field(self, dir_path, pattern):
        """Read a single regex-captured field from build.zig.zon."""
        zon_path = os.path.join(dir_path, ZON_FILE)
        if not os.path.exists(zon_path):
            return None
        with open(zon_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = pattern.search(content)
        return match.group(1) if match else None

    def _is_library(self, dir_path):
        """Heuristic: library if build.zig doesn't contain exe( or addExecutable(."""
        build_path = os.path.join(dir_path, BUILD_ZIG_FILE)
        if not os.path.exists(build_path):
            return True
        with open(build_path, "r", encoding="utf-8") as f:
            content = f.read()
        return not bool(_BUILD_EXE_RE.search(content))

    def template_vars(self, dir_path):
        """Extract template variables from build.zig.zon and build.zig."""
        name = self._read_zon_field(dir_path, _ZON_NAME_RE)
        if not name:
            name = os.path.basename(os.path.abspath(dir_path))

        try:
            version = self.read_version(dir_path)
        except FileNotFoundError:
            version = "0.0.0"

        min_zig = self._read_zon_field(dir_path, _ZON_MIN_ZIG_RE)
        if not min_zig:
            min_zig = "0.14.0"

        is_library = self._is_library(dir_path)

        return {
            "name": name,
            "version": version,
            "zig.minRequiredZig": min_zig,
            "zig.projectName": name,
            "zig.isLibrary": is_library,
        }

    def template_mappings(self):
        return [
            {"template": "VERSION.tpl", "target": "VERSION"},
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/publish.yml"},
        ]

    def check_project_exists(self, dir_path):
        return self.detect(dir_path)

    def get_project_init_hint(self):
        return 'Run "zig init" first, or create a build.zig.zon manually'
