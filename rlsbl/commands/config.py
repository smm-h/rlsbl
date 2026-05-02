"""Config command: show resolved project configuration."""

import os
from ..config import PROJECT_CONFIG, USER_CONFIG, read_json_config, should_tag
from ..registries import REGISTRIES


def run_cmd(registry, args, flags):
    print("Detected registries:")
    for name, reg in REGISTRIES.items():
        if reg.check_project_exists("."):
            version = reg.read_version(".")
            vfile = reg.get_version_file() or "git tag"
            print(f"  {name}: {vfile} (v{version})")
        else:
            print(f"  {name}: not found")

    print("\nScaffolding:")
    rlsbl_dir = os.path.join(".", ".rlsbl")
    if os.path.isdir(rlsbl_dir):
        version_file = os.path.join(rlsbl_dir, "version")
        if os.path.exists(version_file):
            with open(version_file) as f:
                scaffold_ver = f.read().strip()
            print(f"  Version marker: {scaffold_ver}")
        hashes_file = os.path.join(rlsbl_dir, "hashes.json")
        if os.path.exists(hashes_file):
            import json
            with open(hashes_file) as f:
                hashes = json.load(f)
            print(f"  Tracked files: {len(hashes)}")
            for path in sorted(hashes):
                print(f"    {path}")
    else:
        print("  Not scaffolded (run 'rlsbl scaffold')")

    print("\nWorkflows:")
    for wf in ["ci.yml", "publish.yml", "workflow.yml"]:
        path = os.path.join(".github", "workflows", wf)
        print(f"  {wf}: {'yes' if os.path.exists(path) else 'no'}")

    print("\nHooks:")
    pre_release = os.path.join("scripts", "pre-release.sh")
    print(f"  pre-release.sh: {'yes' if os.path.exists(pre_release) else 'no'}")
    pre_push = os.path.join(".git", "hooks", "pre-push")
    print(f"  pre-push hook: {'installed' if os.path.exists(pre_push) else 'not installed'}")

    print("\nEcosystem tagging:")
    enabled = should_tag(flags)
    # Determine why it's enabled/disabled
    project_cfg = read_json_config(PROJECT_CONFIG)
    user_cfg = read_json_config(USER_CONFIG)
    if flags.get("no-tag"):
        source = "CLI flag"
    elif "tag" in project_cfg:
        source = f"project config ({PROJECT_CONFIG})"
    elif "tag" in user_cfg:
        source = f"user config ({USER_CONFIG})"
    else:
        source = "default"
    print(f"  Status: {'enabled' if enabled else 'disabled'} ({source})")

    print("\nFiles:")
    for f in ["CHANGELOG.md", "LICENSE", ".gitignore", "CLAUDE.md"]:
        print(f"  {f}: {'yes' if os.path.exists(f) else 'no'}")
