"""Base class for release targets with shared defaults."""

import os


class BaseTarget:
    """Concrete base providing defaults for optional Protocol methods."""

    @property
    def scope(self):
        return "root"

    def version_file(self):
        return None

    def tag_format(self, name, version):
        return f"v{version}"

    def template_dir(self):
        return None

    def shared_template_dir(self):
        templates = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "shared"
        )
        return templates

    def template_vars(self, dir_path):
        return {}

    def template_mappings(self):
        return []

    def shared_template_mappings(self):
        return [
            {"template": "CHANGELOG.md.tpl", "target": "CHANGELOG.md"},
            {"template": "gitignore.tpl", "target": ".gitignore"},
            {"template": "LICENSE.tpl", "target": "LICENSE"},
            {"template": "CLAUDE.md.tpl", "target": "CLAUDE.md"},
            {"template": "hooks/pre-release.sh.tpl", "target": ".rlsbl/hooks/pre-release.sh"},
            {"template": "hooks/post-release.sh.tpl", "target": ".rlsbl/hooks/post-release.sh"},
            {"template": "claude-settings.json.tpl", "target": ".claude/settings.json"},
        ]

    def check_project_exists(self, dir_path):
        return self.detect(dir_path)

    def get_project_init_hint(self):
        return ""

    def build(self, dir_path, version):
        pass

    def publish(self, dir_path, version):
        pass
