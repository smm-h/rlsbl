"""Tests for PyPI, Go, and GitHub availability checks in rlsbl.commands.check."""

import subprocess
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from conftest import FakeResponse
from rlsbl.commands.check import (
    _check_single_name,
    check_github_availability,
    check_go_availability,
    check_pypi_availability,
    get_pypi_variants,
)


class TestCheckPyPI(unittest.TestCase):
    """Tests for check_pypi_availability and get_pypi_variants."""

    @patch("urllib.request.urlopen")
    def test_pypi_available_on_404(self, mock_urlopen):
        """HTTPError with code 404 means the package name is available."""
        mock_urlopen.side_effect = HTTPError(
            "https://pypi.org/pypi/nonexistent/json", 404, "Not Found", {}, None
        )
        result = check_pypi_availability("nonexistent")
        self.assertEqual(result["status"], "available")

    @patch("urllib.request.urlopen")
    def test_pypi_taken_on_200(self, mock_urlopen):
        """A 200 response means the package name is taken."""
        mock_urlopen.return_value = FakeResponse({"info": {"name": "requests"}})
        result = check_pypi_availability("requests")
        self.assertEqual(result["status"], "taken")

    @patch("urllib.request.urlopen")
    def test_pypi_error_on_url_error(self, mock_urlopen):
        """A generic URLError (network failure) returns error status."""
        mock_urlopen.side_effect = URLError("Connection refused")
        result = check_pypi_availability("some-package")
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result)

    def test_pypi_variants(self):
        """get_pypi_variants generates PEP 503 normalized forms."""
        variants = get_pypi_variants("my-package")
        # Should include underscore and no-separator forms
        self.assertIn("my_package", variants)
        self.assertIn("mypackage", variants)
        # The normalized hyphen form is the same as input, so it should
        # be excluded (the function discards the original name)
        self.assertNotIn("my-package", variants)


class TestCheckGo(unittest.TestCase):
    """Tests for check_go_availability."""

    @patch("urllib.request.urlopen")
    def test_go_exists_on_200(self, mock_urlopen):
        """A 200 response means the Go module exists."""
        mock_urlopen.return_value = FakeResponse(b"<html>pkg page</html>")
        result = check_go_availability("github.com/gorilla/mux")
        self.assertEqual(result["status"], "exists")

    @patch("urllib.request.urlopen")
    def test_go_not_found_on_404(self, mock_urlopen):
        """HTTPError with code 404 means the module is not found."""
        mock_urlopen.side_effect = HTTPError(
            "https://pkg.go.dev/github.com/fake/module", 404, "Not Found", {}, None
        )
        result = check_go_availability("github.com/fake/module")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("note", result)

    @patch("urllib.request.urlopen")
    def test_go_error_on_url_error(self, mock_urlopen):
        """A generic URLError (network failure) returns error status."""
        mock_urlopen.side_effect = URLError("DNS resolution failed")
        result = check_go_availability("github.com/some/module")
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result)


class TestCheckGitHub(unittest.TestCase):
    """Tests for check_github_availability."""

    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_github_available_on_zero_count(self, mock_urlopen):
        """Zero total_count means the name is unique on GitHub."""
        mock_urlopen.return_value = FakeResponse({"total_count": 0, "items": []})
        result = check_github_availability("some-unique-name")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["count"], 0)

    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_github_exists_on_nonzero_count(self, mock_urlopen):
        """Non-zero total_count means repos with this name exist."""
        mock_urlopen.return_value = FakeResponse({"total_count": 5, "items": []})
        result = check_github_availability("popular-name")
        self.assertEqual(result["status"], "exists")
        self.assertEqual(result["count"], 5)
        self.assertIn("note", result)
        self.assertIn("5", result["note"])

    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_github_error_on_exception(self, mock_urlopen):
        """A network error returns error status."""
        mock_urlopen.side_effect = URLError("Connection refused")
        result = check_github_availability("some-name")
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result)


class TestCheckSingleName(unittest.TestCase):
    """Tests for the _check_single_name structured result function."""

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_npm_availability")
    def test_npm_available_result(self, mock_npm, mock_gh):
        """Available npm name returns correct structured result."""
        mock_npm.return_value = {"status": "available"}
        mock_gh.return_value = {"status": "available", "count": 0}

        result = _check_single_name("my-new-pkg", "npm")
        self.assertEqual(result["name"], "my-new-pkg")
        self.assertEqual(result["registry"], "npm")
        self.assertEqual(result["status"], "available")
        self.assertIsInstance(result["variants"], list)
        self.assertEqual(result["github_count"], 0)

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_npm_availability")
    def test_npm_taken_result(self, mock_npm, mock_gh):
        """Taken npm name returns correct structured result."""
        mock_npm.return_value = {"status": "taken"}
        mock_gh.return_value = {"status": "exists", "count": 5, "note": "5 repos"}

        result = _check_single_name("express", "npm")
        self.assertEqual(result["status"], "taken")
        self.assertEqual(result["github_count"], 5)

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_npm_availability")
    def test_npm_error_result(self, mock_npm, mock_gh):
        """Error checking npm returns error in result."""
        mock_npm.return_value = {"status": "error", "message": "npm CLI not found"}
        mock_gh.return_value = {"status": "available", "count": 0}

        result = _check_single_name("some-pkg", "npm")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "npm CLI not found")

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_pypi_availability")
    def test_pypi_available_result(self, mock_pypi, mock_gh):
        """Available PyPI name returns correct structured result."""
        mock_pypi.return_value = {"status": "available"}
        mock_gh.return_value = {"status": "available", "count": 0}

        result = _check_single_name("my-new-pkg", "pypi")
        self.assertEqual(result["name"], "my-new-pkg")
        self.assertEqual(result["registry"], "pypi")
        self.assertEqual(result["status"], "available")

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_go_availability")
    def test_go_not_found_result(self, mock_go, mock_gh):
        """Not-found Go module returns correct structured result with note."""
        mock_go.return_value = {
            "status": "not_found",
            "note": "Go modules use repository paths, not a central registry.",
        }
        mock_gh.return_value = {"status": "available", "count": 0}

        result = _check_single_name("github.com/fake/module", "go")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("note", result)
        self.assertEqual(result["registry"], "go")

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_go_availability")
    def test_go_exists_result(self, mock_go, mock_gh):
        """Existing Go module returns 'exists' status."""
        mock_go.return_value = {"status": "exists"}
        mock_gh.return_value = {"status": "exists", "count": 3, "note": "3 repos"}

        result = _check_single_name("github.com/gorilla/mux", "go")
        self.assertEqual(result["status"], "exists")
        self.assertEqual(result["github_count"], 3)

    @patch("rlsbl.commands.check.check_github_availability")
    @patch("rlsbl.commands.check.check_npm_availability")
    def test_github_error_sets_count_none(self, mock_npm, mock_gh):
        """When GitHub check errors, github_count is None."""
        mock_npm.return_value = {"status": "available"}
        mock_gh.return_value = {"status": "error", "message": "Connection refused"}

        result = _check_single_name("some-pkg", "npm")
        self.assertIsNone(result["github_count"])


class TestCheckTargetRequired(unittest.TestCase):
    """Tests verifying that --target is required for the check command."""

    def test_missing_target_prints_error(self):
        """Running 'rlsbl check <name>' without --target should exit with error."""
        from rlsbl import main

        with patch("sys.argv", ["rlsbl", "check", "some-name"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_missing_target_error_message(self):
        """Error message should mention --target is required."""
        from rlsbl import main
        from io import StringIO

        with patch("sys.argv", ["rlsbl", "check", "some-name"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit):
                    main()
                self.assertIn("--target is required", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
