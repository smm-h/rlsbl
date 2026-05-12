"""Tests for monorepo subcommand help registry and dispatch."""

import pytest

from rlsbl.commands.monorepo import run_cmd, SUBCOMMANDS


class TestMonorepoNoArgs:
    def test_no_args_prints_subcommand_list(self, capsys):
        run_cmd(None, [], {})
        captured = capsys.readouterr()
        assert "Usage: rlsbl monorepo <subcommand>" in captured.out
        assert "Subcommands:" in captured.out
        for name in SUBCOMMANDS:
            assert name in captured.out

    def test_help_flag_prints_subcommand_list(self, capsys):
        run_cmd(None, ["--help"], {})
        captured = capsys.readouterr()
        assert "Usage: rlsbl monorepo <subcommand>" in captured.out
        assert "Subcommands:" in captured.out
        for name in SUBCOMMANDS:
            assert name in captured.out


class TestSubcommandHelp:
    def test_status_help(self, capsys):
        run_cmd(None, ["status", "--help"], {})
        captured = capsys.readouterr()
        assert "Show status of all projects" in captured.out
        assert "Usage: rlsbl monorepo status" in captured.out

    def test_add_help(self, capsys):
        run_cmd(None, ["add", "--help"], {})
        captured = capsys.readouterr()
        assert "Add a project to the workspace" in captured.out
        assert "--name" in captured.out
        assert "--watch" in captured.out
        assert "--subtree-remote" in captured.out

    def test_init_help(self, capsys):
        run_cmd(None, ["init", "--help"], {})
        captured = capsys.readouterr()
        assert "Initialize a monorepo workspace" in captured.out
        assert "Usage: rlsbl monorepo init" in captured.out


class TestUnknownSubcommand:
    def test_unknown_prints_error_and_valid_list(self, capsys):
        with pytest.raises(SystemExit):
            run_cmd(None, ["bogus"], {})
        captured = capsys.readouterr()
        assert "unknown monorepo subcommand 'bogus'" in captured.err
        assert "Valid subcommands:" in captured.err
        for name in SUBCOMMANDS:
            assert name in captured.err


class TestSubcommandsRegistry:
    def test_all_subcommands_have_descriptions(self):
        for name, (handler, description, usage) in SUBCOMMANDS.items():
            assert callable(handler), f"{name} handler is not callable"
            assert len(description) > 0, f"{name} has empty description"
            assert usage.startswith("rlsbl monorepo"), f"{name} usage missing prefix"
