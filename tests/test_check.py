"""Tests for PyPI, Go, and GitHub availability checks in rlsbl.commands.check."""

import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from conftest import FakeResponse
from rlsbl.commands.check import (
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


if __name__ == "__main__":
    unittest.main()
