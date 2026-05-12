"""Tests for Zig version read/write helpers."""

import os
import tempfile

import pytest

from rlsbl.targets.zig_version import (
    read_zig_version,
    read_zon_version,
    write_zig_version,
)

SAMPLE_ZON = """\
.{
    .name = "my-project",
    .version = "0.1.0",
    .minimum_zig_version = "0.13.0",
    .paths = .{
        "build.zig",
        "build.zig.zon",
        "src",
    },
}
"""

SAMPLE_ZON_NO_VERSION = """\
.{
    .name = "my-project",
    .minimum_zig_version = "0.13.0",
    .paths = .{
        "src",
    },
}
"""


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestReadZigVersion:
    """read_zig_version: VERSION primary, build.zig.zon fallback."""

    def test_read_from_version_file(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "VERSION"), "1.2.3\n")
            assert read_zig_version(d) == "1.2.3"

    def test_read_from_zon_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            assert read_zig_version(d) == "0.1.0"

    def test_raises_when_neither_exists(self):
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(FileNotFoundError):
                read_zig_version(d)

    def test_version_file_takes_priority(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "VERSION"), "2.0.0\n")
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            assert read_zig_version(d) == "2.0.0"


class TestWriteZigVersion:
    """write_zig_version: VERSION + optional .zon sync."""

    def test_writes_version_file(self):
        with tempfile.TemporaryDirectory() as d:
            write_zig_version(d, "3.0.0")
            assert _read(os.path.join(d, "VERSION")) == "3.0.0\n"

    def test_syncs_zon_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            write_zig_version(d, "1.5.0")
            content = _read(os.path.join(d, "build.zig.zon"))
            assert '.version = "1.5.0"' in content

    def test_zon_content_preserved_except_version(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            write_zig_version(d, "2.0.0")
            content = _read(os.path.join(d, "build.zig.zon"))
            assert '.name = "my-project"' in content
            assert '.minimum_zig_version = "0.13.0"' in content
            assert '.version = "2.0.0"' in content

    def test_warning_when_zon_has_no_version(self, capsys):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON_NO_VERSION)
            write_zig_version(d, "1.0.0")
            # VERSION file should still be written
            assert _read(os.path.join(d, "VERSION")) == "1.0.0\n"
            captured = capsys.readouterr()
            assert "could not sync version to build.zig.zon" in captured.err

    def test_works_without_zon(self):
        with tempfile.TemporaryDirectory() as d:
            write_zig_version(d, "0.5.0")
            assert _read(os.path.join(d, "VERSION")) == "0.5.0\n"
            assert not os.path.exists(os.path.join(d, "build.zig.zon"))

    def test_no_tmp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "build.zig.zon"), SAMPLE_ZON)
            write_zig_version(d, "1.0.0")
            files = os.listdir(d)
            assert "VERSION.tmp" not in files
            assert "build.zig.zon.tmp" not in files


class TestReadZonVersion:
    """read_zon_version: regex extraction from .zon files."""

    def test_extracts_version(self):
        with tempfile.TemporaryDirectory() as d:
            zon = os.path.join(d, "build.zig.zon")
            _write(zon, SAMPLE_ZON)
            assert read_zon_version(zon) == "0.1.0"

    def test_returns_none_without_version(self):
        with tempfile.TemporaryDirectory() as d:
            zon = os.path.join(d, "build.zig.zon")
            _write(zon, SAMPLE_ZON_NO_VERSION)
            assert read_zon_version(zon) is None

    def test_handles_no_whitespace(self):
        with tempfile.TemporaryDirectory() as d:
            zon = os.path.join(d, "build.zig.zon")
            _write(zon, '.{\n.version="3.2.1",\n}\n')
            assert read_zon_version(zon) == "3.2.1"

    def test_handles_extra_whitespace(self):
        with tempfile.TemporaryDirectory() as d:
            zon = os.path.join(d, "build.zig.zon")
            _write(zon, '.{\n    .version   =   "4.0.0"  ,\n}\n')
            assert read_zon_version(zon) == "4.0.0"

    def test_returns_none_for_missing_file(self):
        assert read_zon_version("/nonexistent/build.zig.zon") is None
