"""Tests for PyPI, Go, and GitHub availability checks in rlsbl.commands.check."""

import subprocess
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock, call
from urllib.error import HTTPError, URLError

from conftest import FakeResponse
from rlsbl.commands.check import (
    _check_single_name,
    _format_single_result,
    _format_table_row,
    _request_with_backoff,
    check_github_availability,
    check_go_availability,
    check_pypi_availability,
    get_pypi_variants,
    run_cmd,
)


class TestCheckPyPI(unittest.TestCase):
    """Tests for check_pypi_availability and get_pypi_variants."""

    @patch("urllib.request.urlopen")
    def test_pypi_available_on_404(self, mock_urlopen):
        """HTTPError with code 404 means the package name is available."""
        mock_urlopen.side_effect = HTTPError(
            "https://pypi.org/simple/nonexistent/", 404, "Not Found", {}, None
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

    @patch("urllib.request.urlopen")
    def test_pypi_registered_but_empty_is_taken(self, mock_urlopen):
        """A registered-but-empty package (no releases) should be 'taken'.

        The JSON API returns 404 for these, but the Simple API correctly
        returns 200. This test verifies we use the Simple API.
        """
        # Simple API returns 200 for registered packages even with no releases
        mock_urlopen.return_value = FakeResponse(b"<html></html>")
        result = check_pypi_availability("cost")
        self.assertEqual(result["status"], "taken")
        # Verify the URL uses the Simple API with normalized name
        called_url = mock_urlopen.call_args[0][0].full_url
        self.assertIn("/simple/cost/", called_url)
        self.assertNotIn("/pypi/", called_url)

    @patch("urllib.request.urlopen")
    def test_pypi_uses_normalized_name_in_url(self, mock_urlopen):
        """The Simple API URL should use PEP 503 normalized names."""
        mock_urlopen.return_value = FakeResponse(b"<html></html>")
        check_pypi_availability("My_Package.Name")
        called_url = mock_urlopen.call_args[0][0].full_url
        # PEP 503: lowercase, runs of [-_.] replaced with single hyphen
        self.assertIn("/simple/my-package-name/", called_url)

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


class TestRequestWithBackoff(unittest.TestCase):
    """Tests for the _request_with_backoff retry helper."""

    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_successful_request_no_retry(self, mock_urlopen):
        """A successful request returns the response without retrying."""
        fake_resp = FakeResponse(b"OK")
        mock_urlopen.return_value = fake_resp
        result = _request_with_backoff("https://example.com/test")
        self.assertIs(result, fake_resp)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_429_with_retry_after_header(self, mock_urlopen, mock_sleep):
        """HTTP 429 with Retry-After header sleeps that many seconds then succeeds."""
        headers_429 = MagicMock()
        headers_429.get.return_value = "3"
        error_429 = HTTPError(
            "https://example.com", 429, "Too Many Requests", headers_429, None
        )
        fake_resp = FakeResponse(b"OK")
        mock_urlopen.side_effect = [error_429, fake_resp]

        result = _request_with_backoff("https://example.com/test", max_retries=3)
        self.assertIs(result, fake_resp)
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(3.0)

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_429_without_retry_after_uses_exponential_backoff(self, mock_urlopen, mock_sleep):
        """HTTP 429 without Retry-After uses exponential backoff (2, 4, ...)."""
        headers_429 = MagicMock()
        headers_429.get.return_value = None
        error_429_first = HTTPError(
            "https://example.com", 429, "Too Many Requests", headers_429, None
        )
        error_429_second = HTTPError(
            "https://example.com", 429, "Too Many Requests", headers_429, None
        )
        fake_resp = FakeResponse(b"OK")
        mock_urlopen.side_effect = [error_429_first, error_429_second, fake_resp]

        result = _request_with_backoff("https://example.com/test", max_retries=3)
        self.assertIs(result, fake_resp)
        self.assertEqual(mock_urlopen.call_count, 3)
        # attempt 0: 2^1 = 2, attempt 1: 2^2 = 4
        self.assertEqual(mock_sleep.call_args_list[0][0][0], 2)
        self.assertEqual(mock_sleep.call_args_list[1][0][0], 4)

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_max_retries_exhausted_raises(self, mock_urlopen, mock_sleep):
        """After exhausting max_retries on 429, raises the last HTTPError."""
        headers_429 = MagicMock()
        headers_429.get.return_value = None
        errors = [
            HTTPError("https://example.com", 429, "Too Many Requests", headers_429, None)
            for _ in range(3)
        ]
        mock_urlopen.side_effect = errors

        with self.assertRaises(HTTPError) as ctx:
            _request_with_backoff("https://example.com/test", max_retries=3)
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check.urllib.request.urlopen")
    def test_non_429_http_error_not_retried(self, mock_urlopen, mock_sleep):
        """Non-429 HTTP errors are raised immediately without retrying."""
        error_500 = HTTPError(
            "https://example.com", 500, "Internal Server Error", {}, None
        )
        mock_urlopen.side_effect = error_500

        with self.assertRaises(HTTPError) as ctx:
            _request_with_backoff("https://example.com/test", max_retries=3)
        self.assertEqual(ctx.exception.code, 500)
        self.assertEqual(mock_urlopen.call_count, 1)
        mock_sleep.assert_not_called()


class TestDelayFlag(unittest.TestCase):
    """Tests for the --delay value flag."""

    def test_delay_parsed_as_value_flag(self):
        """--delay is recognized as a value flag and consumes the next token."""
        from rlsbl import parse_args
        positional, flags = parse_args(["rlsbl", "check", "my-pkg", "--target", "npm", "--delay", "500"])
        self.assertEqual(flags["delay"], "500")
        self.assertIn("my-pkg", positional)

    def test_delay_default_value(self):
        """When --delay is not provided, the default is 200."""
        from rlsbl import parse_args
        positional, flags = parse_args(["rlsbl", "check", "my-pkg", "--target", "npm"])
        # Simulating what run_cmd does
        delay_ms = int(flags.get("delay", "200"))
        self.assertEqual(delay_ms, 200)


class TestMultiNameCheck(unittest.TestCase):
    """Tests for multi-name CLI behavior in run_cmd."""

    @patch("rlsbl.commands.check._format_single_result")
    @patch("rlsbl.commands.check._check_single_name")
    def test_single_name_uses_verbose_format(self, mock_check, mock_format):
        """A single name should use the verbose _format_single_result output."""
        mock_check.return_value = {
            "name": "foo", "registry": "npm", "status": "available",
            "variants": [], "github_count": 0,
        }
        run_cmd("npm", ["foo"], {})
        mock_check.assert_called_once_with("foo", "npm")
        mock_format.assert_called_once_with(mock_check.return_value)

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check._check_single_name")
    def test_multiple_names_prints_table(self, mock_check, mock_sleep):
        """Multiple names should print a compact table with Name and Status columns."""
        mock_check.side_effect = [
            {"name": "foo", "registry": "npm", "status": "available",
             "variants": [], "github_count": 0},
            {"name": "bar", "registry": "npm", "status": "taken",
             "variants": [], "github_count": 5},
            {"name": "baz", "registry": "npm", "status": "available",
             "variants": [], "github_count": 0},
        ]
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            run_cmd("npm", ["foo", "bar", "baz"], {})
        output = mock_stdout.getvalue()
        lines = output.strip().split("\n")
        self.assertEqual(len(lines), 4)  # header + 3 rows
        self.assertIn("Name", lines[0])
        self.assertIn("Status", lines[0])
        self.assertIn("foo", lines[1])
        self.assertIn("available", lines[1])
        self.assertIn("bar", lines[2])
        self.assertIn("taken", lines[2])
        self.assertIn("baz", lines[3])
        self.assertIn("available", lines[3])

    @patch("rlsbl.commands.check.time.sleep")
    @patch("rlsbl.commands.check._check_single_name")
    def test_delay_applied_between_names(self, mock_check, mock_sleep):
        """Delay should be applied between names, not after the last one."""
        mock_check.side_effect = [
            {"name": "a", "registry": "npm", "status": "available",
             "variants": [], "github_count": 0},
            {"name": "b", "registry": "npm", "status": "taken",
             "variants": [], "github_count": 0},
            {"name": "c", "registry": "npm", "status": "available",
             "variants": [], "github_count": 0},
        ]
        with patch("sys.stdout", new_callable=StringIO):
            run_cmd("npm", ["a", "b", "c"], {"delay": "500"})
        # 3 names -> 2 delays between them
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_has_calls([call(0.5), call(0.5)])

    def test_empty_args_prints_error_and_exits(self):
        """No names should print an error to stderr and exit 1."""
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                run_cmd("npm", [], {})
            self.assertEqual(ctx.exception.code, 1)
        self.assertIn("missing package name", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
