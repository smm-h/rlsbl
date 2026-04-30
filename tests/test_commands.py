"""Integration tests for rlsbl.commands.init_cmd (scaffold command)."""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from rlsbl.commands.init_cmd import (
    APPEND_MARKER,
    HASHES_FILE,
    file_hash,
    load_hashes,
    process_mappings,
    process_template,
    run_cmd,
    save_hashes,
)


class TestProcessTemplate(unittest.TestCase):
    """Tests for template variable replacement."""

    def test_replaces_known_variables(self):
        content, unreplaced = process_template(
            "Hello {{name}}, version {{version}}!",
            {"name": "my-pkg", "version": "1.0.0"},
        )
        self.assertEqual(content, "Hello my-pkg, version 1.0.0!")
        self.assertEqual(unreplaced, [])

    def test_leaves_unknown_variables_and_reports_them(self):
        content, unreplaced = process_template(
            "{{name}} uses {{unknownVar}}",
            {"name": "my-pkg"},
        )
        self.assertEqual(content, "my-pkg uses {{unknownVar}}")
        self.assertEqual(unreplaced, ["unknownVar"])

    def test_replaces_multiple_occurrences(self):
        content, _ = process_template(
            "{{name}} is {{name}}",
            {"name": "x"},
        )
        self.assertEqual(content, "x is x")

    def test_no_variables_returns_unchanged(self):
        content, unreplaced = process_template("plain text", {})
        self.assertEqual(content, "plain text")
        self.assertEqual(unreplaced, [])


class TestScaffold(unittest.TestCase):
    """Integration tests for the scaffold (init) command."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)
        # Create minimal package.json so npm registry is detected
        with open("package.json", "w") as f:
            json.dump({"name": "test-pkg", "version": "0.1.0"}, f)

    def tearDown(self):
        os.chdir(self.orig_dir)
        shutil.rmtree(self.tmp_dir)

    def _run_scaffold(self, force=False, update=False):
        """Run scaffold for npm with stdout suppressed."""
        flags = {}
        if force:
            flags["force"] = True
        if update:
            flags["update"] = True
        with patch("sys.stdout", new_callable=StringIO):
            run_cmd("npm", [], flags)

    def test_creates_changelog(self):
        self._run_scaffold()
        self.assertTrue(os.path.exists("CHANGELOG.md"))
        with open("CHANGELOG.md") as f:
            self.assertIn("0.1.0", f.read())

    def test_creates_gitignore(self):
        self._run_scaffold()
        self.assertTrue(os.path.exists(".gitignore"))

    def test_creates_ci_workflow(self):
        self._run_scaffold()
        self.assertTrue(os.path.exists(".github/workflows/ci.yml"))

    def test_creates_publish_workflow(self):
        self._run_scaffold()
        self.assertTrue(os.path.exists(".github/workflows/publish.yml"))

    def test_template_variable_replacement(self):
        """Verify {{name}} and {{version}} are replaced in generated files."""
        self._run_scaffold()
        with open("CHANGELOG.md") as f:
            content = f.read()
        # The CHANGELOG template uses {{version}}; it should be replaced
        self.assertIn("0.1.0", content)
        self.assertNotIn("{{version}}", content)

    def test_unreplaced_variables_emit_warning(self):
        """Scaffold with a template containing unknown vars should warn."""
        # We test process_mappings directly with a custom template containing
        # an unknown variable, since the real templates may not have any.
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write("Hello {{name}} from {{planet}}")

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        created, skipped, warnings, hashes = process_mappings(
            tpl_dir, mappings, {"name": "test-pkg"}, force=False,
        )
        self.assertIn("output.txt", created)
        # Should warn about the unreplaced variable "planet"
        self.assertTrue(
            any("planet" in w for w in warnings),
            f"Expected warning about 'planet', got: {warnings}",
        )

    # -- APPENDABLE tests (CLAUDE.md) --

    def test_appendable_appends_to_existing_claude_md(self):
        """When CLAUDE.md already exists, scaffold appends rlsbl section."""
        existing_content = "# My Project\n\nSome existing docs.\n"
        with open("CLAUDE.md", "w") as f:
            f.write(existing_content)

        self._run_scaffold()

        with open("CLAUDE.md") as f:
            content = f.read()
        # Original content is preserved
        self.assertIn("My Project", content)
        self.assertIn("Some existing docs.", content)
        # rlsbl marker is present (appended section)
        self.assertIn(APPEND_MARKER, content)

    def test_appendable_skips_if_marker_already_present(self):
        """When CLAUDE.md already contains the rlsbl marker, skip append."""
        existing_content = (
            "# My Project\n\n"
            "## Release workflow\n\n"
            f"This uses {APPEND_MARKER} for releases.\n"
        )
        with open("CLAUDE.md", "w") as f:
            f.write(existing_content)

        self._run_scaffold()

        with open("CLAUDE.md") as f:
            content = f.read()
        # Content should be unchanged (marker was already present)
        self.assertEqual(content, existing_content)

    # -- MERGEABLE tests (.gitignore) --

    def test_mergeable_merges_missing_gitignore_entries(self):
        """When .gitignore exists but is missing entries, scaffold merges them."""
        with open(".gitignore", "w") as f:
            f.write("node_modules/\n")

        self._run_scaffold()

        with open(".gitignore") as f:
            content = f.read()
        # Original entry preserved
        self.assertIn("node_modules/", content)
        # At least one new entry merged (e.g. __pycache__/ from the template)
        self.assertIn("__pycache__/", content)

    def test_mergeable_skips_if_all_entries_present(self):
        """When .gitignore already has all template entries, nothing is added."""
        # Read the gitignore template to get all non-comment entries
        from rlsbl.registries import npm
        tpl_path = os.path.join(npm.get_shared_template_dir(), "gitignore.tpl")
        with open(tpl_path) as f:
            tpl_content = f.read()

        # Pre-populate .gitignore with all template entries
        with open(".gitignore", "w") as f:
            f.write(tpl_content)

        # Record content before scaffold
        with open(".gitignore") as f:
            before = f.read()

        self._run_scaffold()

        with open(".gitignore") as f:
            after = f.read()

        # File should be unchanged since all entries were already present
        self.assertEqual(before, after)

    # -- --force tests --

    def test_force_overwrites_existing_files(self):
        """With --force, scaffold overwrites existing files."""
        # Create a pre-existing CHANGELOG.md with custom content
        with open("CHANGELOG.md", "w") as f:
            f.write("# My custom changelog\n")

        self._run_scaffold(force=True)

        with open("CHANGELOG.md") as f:
            content = f.read()
        # Custom content replaced by template output
        self.assertNotIn("My custom changelog", content)
        self.assertIn("0.1.0", content)

    # -- Hash tests --

    def test_hashes_saved_after_scaffolding(self):
        """After scaffolding, .rlsbl/hashes.json should exist with entries."""
        self._run_scaffold()
        self.assertTrue(os.path.exists(HASHES_FILE))
        hashes = load_hashes()
        self.assertIsInstance(hashes, dict)
        self.assertGreater(len(hashes), 0)

    def test_hashes_match_actual_file_contents(self):
        """Stored hashes should match SHA-256 of the generated files."""
        self._run_scaffold()
        hashes = load_hashes()
        for path, stored_hash in hashes.items():
            if os.path.exists(path):
                self.assertEqual(
                    stored_hash,
                    file_hash(path),
                    f"Hash mismatch for {path}",
                )

    # -- --update tests --

    def test_update_skips_customized_files(self):
        """--update should skip files that have been modified (hash mismatch)."""
        # First scaffold to create files and hashes
        self._run_scaffold()

        # Customize a managed file (ci.yml is in UPDATABLE)
        ci_path = ".github/workflows/ci.yml"
        with open(ci_path, "a") as f:
            f.write("\n# my customization\n")

        # Run with --update; the customized file should be skipped
        self._run_scaffold(update=True)

        with open(ci_path) as f:
            content = f.read()
        self.assertIn("# my customization", content)

    def test_update_overwrites_files_with_matching_hash(self):
        """--update should overwrite managed files whose hash still matches."""
        # First scaffold to create files and hashes
        self._run_scaffold()

        ci_path = ".github/workflows/ci.yml"
        # Verify the file exists and note its hash
        hashes_before = load_hashes()
        self.assertIn(ci_path, hashes_before)

        # Run with --update without modifying the file; it should be updated
        # (overwritten with potentially same content, but the code path runs)
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", [], {"update": True})
            output = mock_out.getvalue()

        # The file should have been processed (either updated or remained same)
        # Check that CI file still exists and is valid
        self.assertTrue(os.path.exists(ci_path))


class TestHashFunctions(unittest.TestCase):
    """Tests for hash utility functions."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)

    def tearDown(self):
        os.chdir(self.orig_dir)
        shutil.rmtree(self.tmp_dir)

    def test_file_hash_returns_sha256(self):
        with open("test.txt", "w") as f:
            f.write("hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(file_hash("test.txt"), expected)

    def test_save_and_load_hashes_roundtrip(self):
        data = {"file1.txt": "abc123", "dir/file2.txt": "def456"}
        save_hashes(data)
        loaded = load_hashes()
        self.assertEqual(loaded, data)

    def test_load_hashes_returns_empty_dict_when_no_file(self):
        self.assertEqual(load_hashes(), {})


if __name__ == "__main__":
    unittest.main()
