"""Tests for rlsbl.commands.record_gif integer flag validation."""

import sys
import unittest

from rlsbl.commands.record_gif import _parse_int_flag


class TestParseIntFlag(unittest.TestCase):
    """Tests for _parse_int_flag helper."""

    def test_valid_integer_string(self):
        flags = {"width": "800"}
        self.assertEqual(_parse_int_flag(flags, "width", 1200), 800)

    def test_valid_integer_value(self):
        flags = {"height": 400}
        self.assertEqual(_parse_int_flag(flags, "height", 600), 400)

    def test_uses_default_when_flag_absent(self):
        flags = {}
        self.assertEqual(_parse_int_flag(flags, "width", 1200), 1200)

    def test_invalid_string_exits_with_error(self):
        flags = {"width": "abc"}
        with self.assertRaises(SystemExit) as ctx:
            _parse_int_flag(flags, "width", 1200)
        self.assertEqual(ctx.exception.code, 1)

    def test_invalid_string_prints_clear_message(self, ):
        flags = {"font-size": "big"}
        # Capture stderr to verify the error message
        import io
        from unittest.mock import patch

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            with self.assertRaises(SystemExit):
                _parse_int_flag(flags, "font-size", 24)
        self.assertIn("Invalid value for --font-size", mock_err.getvalue())
        self.assertIn("expected integer", mock_err.getvalue())
        self.assertIn("'big'", mock_err.getvalue())

    def test_invalid_float_string_exits(self):
        # "3.5" is not a valid int
        flags = {"duration": "3.5"}
        with self.assertRaises(SystemExit) as ctx:
            _parse_int_flag(flags, "duration", 10)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
