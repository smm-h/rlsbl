"""Tests for rlsbl.registries — npm, pypi, and go adapters."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from rlsbl.registries import go, npm, pypi


class TestNpmReadVersion(unittest.TestCase):
    """Tests for npm.read_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_package_json(self, data):
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def test_reads_version(self):
        self._write_package_json({"name": "my-pkg", "version": "3.1.4"})
        self.assertEqual(npm.read_version(self.tmp_dir), "3.1.4")


class TestNpmWriteVersion(unittest.TestCase):
    """Tests for npm.write_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_package_json(self, content):
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _read_package_json(self):
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_updates_version(self):
        self._write_package_json(
            json.dumps({"name": "my-pkg", "version": "1.0.0"}, indent=2) + "\n"
        )
        npm.write_version(self.tmp_dir, "2.0.0")
        data = self._read_package_json()
        self.assertEqual(data["version"], "2.0.0")

    def test_preserves_other_fields(self):
        self._write_package_json(
            json.dumps(
                {"name": "my-pkg", "version": "1.0.0", "description": "cool"},
                indent=2,
            )
            + "\n"
        )
        npm.write_version(self.tmp_dir, "1.1.0")
        data = self._read_package_json()
        self.assertEqual(data["name"], "my-pkg")
        self.assertEqual(data["description"], "cool")
        self.assertEqual(data["version"], "1.1.0")

    def test_preserves_trailing_newline(self):
        self._write_package_json(
            json.dumps({"name": "my-pkg", "version": "1.0.0"}, indent=2) + "\n"
        )
        npm.write_version(self.tmp_dir, "1.0.1")
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertTrue(raw.endswith("\n"))


class TestNpmCheckProjectExists(unittest.TestCase):
    """Tests for npm.check_project_exists."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_returns_true_when_package_json_exists(self):
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "w") as f:
            json.dump({"name": "x", "version": "0.0.1"}, f)
        self.assertTrue(npm.check_project_exists(self.tmp_dir))

    def test_returns_false_when_no_package_json(self):
        self.assertFalse(npm.check_project_exists(self.tmp_dir))


class TestNpmGetTemplateVars(unittest.TestCase):
    """Tests for npm.get_template_vars."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_package_json(self, data):
        path = os.path.join(self.tmp_dir, "package.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def test_extracts_name_and_version(self):
        self._write_package_json({"name": "my-tool", "version": "2.5.0"})
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["name"], "my-tool")
        self.assertEqual(result["version"], "2.5.0")

    def test_extracts_bin_command_from_bin_object(self):
        self._write_package_json({
            "name": "my-tool",
            "version": "1.0.0",
            "bin": {"mytool": "./bin/mytool.js"},
        })
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["binCommand"], "mytool")

    def test_bin_command_falls_back_to_name_for_string_bin(self):
        self._write_package_json({
            "name": "my-tool",
            "version": "1.0.0",
            "bin": "./bin/my-tool.js",
        })
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["binCommand"], "my-tool")

    def test_bin_command_falls_back_to_name_when_no_bin(self):
        self._write_package_json({"name": "my-tool", "version": "1.0.0"})
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["binCommand"], "my-tool")

    def test_extracts_repo_name_from_repository_url(self):
        self._write_package_json({
            "name": "my-tool",
            "version": "1.0.0",
            "repository": {
                "type": "git",
                "url": "https://github.com/user/my-tool.git",
            },
        })
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["repoName"], "user/my-tool")

    def test_extracts_repo_name_from_repository_string(self):
        self._write_package_json({
            "name": "my-tool",
            "version": "1.0.0",
            "repository": "https://github.com/user/my-tool",
        })
        result = npm.get_template_vars(self.tmp_dir)
        self.assertEqual(result["repoName"], "user/my-tool")


# ---------------------------------------------------------------------------
# PyPI adapter tests
# ---------------------------------------------------------------------------


class TestPypiReadVersion(unittest.TestCase):
    """Tests for pypi.read_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_pyproject(self, content):
        path = os.path.join(self.tmp_dir, "pyproject.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_reads_version(self):
        self._write_pyproject(
            '[project]\nname = "my-pkg"\nversion = "0.4.2"\n'
        )
        self.assertEqual(pypi.read_version(self.tmp_dir), "0.4.2")


class TestPypiWriteVersion(unittest.TestCase):
    """Tests for pypi.write_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_pyproject(self, content):
        path = os.path.join(self.tmp_dir, "pyproject.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _read_pyproject(self):
        path = os.path.join(self.tmp_dir, "pyproject.toml")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_updates_version(self):
        self._write_pyproject(
            '[project]\nname = "my-pkg"\nversion = "1.0.0"\n'
        )
        pypi.write_version(self.tmp_dir, "1.1.0")
        content = self._read_pyproject()
        self.assertIn('version = "1.1.0"', content)

    def test_preserves_other_fields(self):
        self._write_pyproject(
            '[project]\nname = "my-pkg"\nversion = "1.0.0"\n'
            'description = "A cool package"\n'
        )
        pypi.write_version(self.tmp_dir, "2.0.0")
        content = self._read_pyproject()
        self.assertIn('name = "my-pkg"', content)
        self.assertIn('description = "A cool package"', content)
        self.assertIn('version = "2.0.0"', content)


class TestPypiCheckProjectExists(unittest.TestCase):
    """Tests for pypi.check_project_exists."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_returns_true_when_pyproject_exists(self):
        path = os.path.join(self.tmp_dir, "pyproject.toml")
        with open(path, "w") as f:
            f.write('[project]\nname = "x"\nversion = "0.1.0"\n')
        self.assertTrue(pypi.check_project_exists(self.tmp_dir))

    def test_returns_false_when_no_pyproject(self):
        self.assertFalse(pypi.check_project_exists(self.tmp_dir))


class TestPypiGetTemplateVars(unittest.TestCase):
    """Tests for pypi.get_template_vars."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_pyproject(self, content):
        path = os.path.join(self.tmp_dir, "pyproject.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_extracts_name_and_version(self, _mock_run):
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "2.5.0"\n'
        )
        # Create matching package dir so import_name resolves via filesystem
        os.makedirs(os.path.join(self.tmp_dir, "my_tool"))
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["name"], "my-tool")
        self.assertEqual(result["version"], "2.5.0")

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_derives_import_name_from_underscore_convention(self, _mock_run):
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "1.0.0"\n'
        )
        # Create the underscored directory so filesystem detection works
        os.makedirs(os.path.join(self.tmp_dir, "my_tool"))
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["importName"], "my_tool")

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_derives_import_name_from_hatch_packages(self, _mock_run):
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "1.0.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["my_tool"]\n'
        )
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["importName"], "my_tool")

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_strips_src_prefix_from_hatch_packages(self, _mock_run):
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "1.0.0"\n\n'
            "[tool.hatch.build.targets.wheel]\n"
            'packages = ["src/my_tool"]\n'
        )
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["importName"], "my_tool")

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_fallback_import_name_when_no_dir_exists(self, _mock_run):
        """When no matching directory exists, falls back to underscore convention."""
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "1.0.0"\n'
        )
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["importName"], "my_tool")

    @patch("rlsbl.registries.pypi.run", return_value="Test Author")
    def test_extracts_repo_name_from_urls(self, _mock_run):
        self._write_pyproject(
            '[project]\nname = "my-tool"\nversion = "1.0.0"\n\n'
            "[project.urls]\n"
            'Homepage = "https://github.com/user/my-tool"\n'
        )
        result = pypi.get_template_vars(self.tmp_dir)
        self.assertEqual(result["repoName"], "user/my-tool")


# ---------------------------------------------------------------------------
# Go adapter tests
# ---------------------------------------------------------------------------


class TestGoReadVersion(unittest.TestCase):
    """Tests for go.read_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_version(self, content):
        path = os.path.join(self.tmp_dir, "VERSION")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_read_version(self):
        self._write_version("1.2.3\n")
        self.assertEqual(go.read_version(self.tmp_dir), "1.2.3")

    def test_read_version_missing(self):
        with self.assertRaises(FileNotFoundError):
            go.read_version(self.tmp_dir)


class TestGoWriteVersion(unittest.TestCase):
    """Tests for go.write_version."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _read_version_file(self):
        path = os.path.join(self.tmp_dir, "VERSION")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_write_version(self):
        go.write_version(self.tmp_dir, "2.0.0")
        content = self._read_version_file()
        self.assertEqual(content, "2.0.0\n")

    def test_write_version_atomic(self):
        """Verify write_version uses tmp file + os.replace (atomic rename).

        After write_version completes, the .tmp file should not exist --
        it was renamed to VERSION atomically.
        """
        go.write_version(self.tmp_dir, "3.0.0")
        tmp_path = os.path.join(self.tmp_dir, "VERSION.tmp")
        self.assertFalse(os.path.exists(tmp_path))
        # The final file should exist with the correct content
        self.assertEqual(self._read_version_file(), "3.0.0\n")


class TestGoCheckProjectExists(unittest.TestCase):
    """Tests for go.check_project_exists."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_check_project_exists_true(self):
        path = os.path.join(self.tmp_dir, "go.mod")
        with open(path, "w") as f:
            f.write("module github.com/user/myapp\n\ngo 1.22\n")
        self.assertTrue(go.check_project_exists(self.tmp_dir))

    def test_check_project_exists_false(self):
        self.assertFalse(go.check_project_exists(self.tmp_dir))


class TestGoGetTemplateVars(unittest.TestCase):
    """Tests for go.get_template_vars."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_go_mod(self, content):
        path = os.path.join(self.tmp_dir, "go.mod")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_version(self, version):
        path = os.path.join(self.tmp_dir, "VERSION")
        with open(path, "w", encoding="utf-8") as f:
            f.write(version + "\n")

    @patch("rlsbl.registries.go.run", return_value="Test Author")
    def test_get_template_vars(self, _mock_run):
        self._write_go_mod("module github.com/user/myapp\n\ngo 1.22\n")
        self._write_version("0.1.0")
        result = go.get_template_vars(self.tmp_dir)
        self.assertEqual(result["name"], "myapp")
        self.assertEqual(result["modulePath"], "github.com/user/myapp")
        self.assertEqual(result["version"], "0.1.0")
        self.assertEqual(result["repoName"], "user/myapp")


class TestGoGetVersionFile(unittest.TestCase):
    """Tests for go.get_version_file."""

    def test_get_version_file(self):
        self.assertEqual(go.get_version_file(), "VERSION")


if __name__ == "__main__":
    unittest.main()
