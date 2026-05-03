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
    BASES_DIR,
    HASHES_FILE,
    _load_base,
    _save_base,
    _three_way_merge,
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


class TestBaseStorage(unittest.TestCase):
    """Tests for _save_base / _load_base helpers."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)

    def tearDown(self):
        os.chdir(self.orig_dir)
        shutil.rmtree(self.tmp_dir)

    def test_save_and_load_roundtrip(self):
        _save_base("foo/bar.txt", "hello world\n")
        self.assertEqual(_load_base("foo/bar.txt"), "hello world\n")

    def test_load_missing_returns_none(self):
        self.assertIsNone(_load_base("nonexistent.txt"))

    def test_save_creates_parent_dirs(self):
        _save_base("a/b/c.txt", "content")
        base_path = os.path.join(BASES_DIR, "a", "b", "c.txt")
        self.assertTrue(os.path.exists(base_path))


class TestThreeWayMerge(unittest.TestCase):
    """Tests for _three_way_merge using git merge-file."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)
        # git merge-file needs to be able to run; init a repo for safety
        os.system("git init -q .")

    def tearDown(self):
        os.chdir(self.orig_dir)
        shutil.rmtree(self.tmp_dir)

    def test_clean_merge_no_conflicts(self):
        # Changes must be non-adjacent so git merge-file resolves them cleanly
        base = "line1\nline2\nline3\nline4\nline5\n"
        ours = "line1\nline2 modified by user\nline3\nline4\nline5\n"
        theirs = "line1\nline2\nline3\nline4 modified by template\nline5\n"
        merged, has_conflicts = _three_way_merge(ours, base, theirs)
        self.assertFalse(has_conflicts)
        self.assertIn("line2 modified by user", merged)
        self.assertIn("line4 modified by template", merged)

    def test_conflict_detected(self):
        base = "line1\nline2\nline3\n"
        ours = "line1\nline2 user version\nline3\n"
        theirs = "line1\nline2 template version\nline3\n"
        merged, has_conflicts = _three_way_merge(ours, base, theirs)
        self.assertTrue(has_conflicts)
        self.assertIn("<<<<<<<", merged)
        self.assertIn("=======", merged)
        self.assertIn(">>>>>>>", merged)

    def test_identical_changes_no_conflict(self):
        base = "line1\nline2\nline3\n"
        ours = "line1\nline2 same change\nline3\n"
        theirs = "line1\nline2 same change\nline3\n"
        merged, has_conflicts = _three_way_merge(ours, base, theirs)
        self.assertFalse(has_conflicts)
        self.assertEqual(merged, "line1\nline2 same change\nline3\n")

    def test_temp_files_cleaned_up(self):
        base = "a\n"
        ours = "a\n"
        theirs = "a\n"
        _three_way_merge(ours, base, theirs)
        # No leftover .ours/.base/.theirs files
        leftover = [f for f in os.listdir(".") if f.endswith((".ours", ".base", ".theirs"))]
        self.assertEqual(leftover, [])


class TestScaffold(unittest.TestCase):
    """Integration tests for the scaffold (init) command."""

    def setUp(self):
        self.orig_dir = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        os.chdir(self.tmp_dir)
        # git init so git merge-file works
        os.system("git init -q .")
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
        self.assertIn("0.1.0", content)
        self.assertNotIn("{{version}}", content)

    def test_unreplaced_variables_emit_warning(self):
        """Scaffold with a template containing unknown vars should warn."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write("Hello {{name}} from {{planet}}")

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        created, skipped, warnings, hashes = process_mappings(
            tpl_dir, mappings, {"name": "test-pkg"}, force=False,
        )
        self.assertIn("output.txt", created)
        self.assertTrue(
            any("planet" in w for w in warnings),
            f"Expected warning about 'planet', got: {warnings}",
        )

    # -- Base storage tests --

    def test_initial_scaffold_saves_bases(self):
        """After initial scaffold, base files should exist in .rlsbl/bases/."""
        self._run_scaffold()
        # CI workflow should have a base stored
        ci_base = _load_base(".github/workflows/ci.yml")
        self.assertIsNotNone(ci_base)
        self.assertGreater(len(ci_base), 0)

    def test_bases_match_generated_files(self):
        """Stored bases should match the rendered template content (identical to file on first scaffold)."""
        self._run_scaffold()
        ci_path = ".github/workflows/ci.yml"
        with open(ci_path) as f:
            file_content = f.read()
        base_content = _load_base(ci_path)
        self.assertEqual(file_content, base_content)

    # -- Three-way merge integration tests --

    def test_update_clean_when_user_did_not_modify(self):
        """When user hasn't modified a file, --update should cleanly overwrite."""
        self._run_scaffold()
        ci_path = ".github/workflows/ci.yml"
        with open(ci_path) as f:
            original = f.read()
        # Re-scaffold (template hasn't changed, so file should be skipped as base==theirs)
        self._run_scaffold()
        with open(ci_path) as f:
            after = f.read()
        self.assertEqual(original, after)

    def test_three_way_merge_preserves_user_additions(self):
        """Three-way merge should preserve user additions when template changes elsewhere."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)

        # Initial template (5 lines so changes are non-adjacent for clean merge)
        tpl_v1 = "line1\nline2\nline3\nline4\nline5\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(tpl_v1)

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        process_mappings(tpl_dir, mappings, {}, force=False)

        # User modifies line2
        with open("output.txt", "w") as f:
            f.write("line1\nline2 user edit\nline3\nline4\nline5\n")

        # Template changes line4 (non-adjacent to user's line2 change)
        tpl_v2 = "line1\nline2\nline3\nline4 template update\nline5\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(tpl_v2)

        created, skipped, warnings, _ = process_mappings(tpl_dir, mappings, {}, force=False)
        with open("output.txt") as f:
            result = f.read()

        # Both changes should be present (clean merge)
        self.assertIn("line2 user edit", result)
        self.assertIn("line4 template update", result)
        self.assertTrue(any("merged" in c for c in created))

    def test_three_way_merge_detects_conflicts(self):
        """Three-way merge should detect conflicts when both sides change the same line."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)

        tpl_v1 = "line1\nline2\nline3\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(tpl_v1)

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        process_mappings(tpl_dir, mappings, {}, force=False)

        # User modifies line2
        with open("output.txt", "w") as f:
            f.write("line1\nline2 user version\nline3\n")

        # Template also modifies line2
        tpl_v2 = "line1\nline2 template version\nline3\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(tpl_v2)

        created, skipped, warnings, _ = process_mappings(tpl_dir, mappings, {}, force=False)
        with open("output.txt") as f:
            result = f.read()

        self.assertIn("<<<<<<<", result)
        self.assertTrue(any("CONFLICTS" in c for c in created))
        self.assertTrue(any("conflict" in w.lower() for w in warnings))

    def test_no_base_skips_with_warning(self):
        """When no base is stored (legacy project), skip with a warning."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)

        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write("template content v2\n")

        # Create target file directly (no base stored)
        with open("output.txt", "w") as f:
            f.write("different content\n")

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        created, skipped, warnings, _ = process_mappings(tpl_dir, mappings, {}, force=False)

        self.assertIn("output.txt", skipped)
        self.assertTrue(
            any("no base stored" in w for w in warnings),
            f"Expected 'no base stored' warning, got: {warnings}",
        )

    def test_no_base_identical_content_skips_silently(self):
        """When no base is stored but file matches template, skip without warning."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)

        content = "identical content\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(content)
        with open("output.txt", "w") as f:
            f.write(content)

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        created, skipped, warnings, _ = process_mappings(tpl_dir, mappings, {}, force=False)

        self.assertIn("output.txt", skipped)
        # No warning because content matches
        self.assertFalse(any("no base stored" in w for w in warnings))

    def test_template_unchanged_skips(self):
        """When template hasn't changed (base == theirs), skip even if user modified file."""
        tpl_dir = os.path.join(self.tmp_dir, "_tpls")
        os.makedirs(tpl_dir)

        tpl_content = "line1\nline2\nline3\n"
        with open(os.path.join(tpl_dir, "test.tpl"), "w") as f:
            f.write(tpl_content)

        mappings = [{"template": "test.tpl", "target": "output.txt"}]
        process_mappings(tpl_dir, mappings, {}, force=False)

        # User modifies the file
        with open("output.txt", "w") as f:
            f.write("line1\nline2 customized\nline3\n")

        # Re-run with same template -- should skip (template unchanged)
        created, skipped, warnings, _ = process_mappings(tpl_dir, mappings, {}, force=False)
        self.assertIn("output.txt", skipped)

        # Verify user customization is preserved
        with open("output.txt") as f:
            self.assertIn("customized", f.read())

    # -- --force tests --

    def test_force_overwrites_existing_files(self):
        """With --force, scaffold overwrites existing files."""
        with open("CHANGELOG.md", "w") as f:
            f.write("# My custom changelog\n")

        self._run_scaffold(force=True)

        with open("CHANGELOG.md") as f:
            content = f.read()
        self.assertNotIn("My custom changelog", content)
        self.assertIn("0.1.0", content)

    def test_force_updates_base(self):
        """With --force, the base should be updated to the new template content."""
        self._run_scaffold()
        ci_base_before = _load_base(".github/workflows/ci.yml")
        self._run_scaffold(force=True)
        ci_base_after = _load_base(".github/workflows/ci.yml")
        # Base should exist after force
        self.assertIsNotNone(ci_base_after)
        # Content should match (template hasn't changed)
        self.assertEqual(ci_base_before, ci_base_after)

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

    def test_update_processes_managed_files(self):
        """--update should still process CI files via three-way merge."""
        self._run_scaffold()

        ci_path = ".github/workflows/ci.yml"
        hashes_before = load_hashes()
        self.assertIn(ci_path, hashes_before)

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            run_cmd("npm", [], {"update": True})

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
