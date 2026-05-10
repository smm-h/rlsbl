"""Docker release target for rlsbl.

Docker projects use a VERSION file as the source of truth. Activation is opt-in
only via .rlsbl/config.json targets array -- detect() merely validates that a
Dockerfile exists. Publishing builds and pushes images to the configured registry.
"""

import os
import shutil

from .base import BaseTarget
from ..config import read_project_config
from ..utils import run

VERSION_FILE = "VERSION"


class DockerTarget(BaseTarget):
    """Release target for Docker projects (Dockerfile + VERSION file)."""

    @property
    def name(self):
        return "docker"

    @property
    def scope(self):
        return "root"

    def detect(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "Dockerfile"))

    def read_version(self, dir_path):
        """Read version from the VERSION file."""
        version_path = os.path.join(dir_path, VERSION_FILE)
        if not os.path.exists(version_path):
            raise FileNotFoundError(
                f"No {VERSION_FILE} file found. Run 'rlsbl scaffold' first."
            )
        with open(version_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def write_version(self, dir_path, version):
        """Write the new version to the VERSION file atomically."""
        version_path = os.path.join(dir_path, VERSION_FILE)
        tmp_path = version_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(version + "\n")
        os.replace(tmp_path, version_path)

    def version_file(self):
        return VERSION_FILE

    def tag_format(self, name, version):
        return f"v{version}"

    def publish(self, dir_path, version):
        """Build and push Docker image to the configured registry."""
        # Token gating: require DOCKER_USERNAME and DOCKER_PASSWORD env vars
        username = os.environ.get("DOCKER_USERNAME")
        password = os.environ.get("DOCKER_PASSWORD")
        if not username or not password:
            print("Skipping local docker publish (no DOCKER_USERNAME/DOCKER_PASSWORD). CI will handle it.")
            return

        config = read_project_config()
        docker_config = config.get("docker", {})
        image = docker_config.get("image")
        registry = docker_config.get("registry")

        if not image or not registry:
            print("Error: docker config missing. Set 'docker.image' and "
                  "'docker.registry' in .rlsbl/config.json")
            return

        if not shutil.which("docker"):
            print("Error: 'docker' not found on PATH, cannot publish")
            return

        full_image = f"{registry}/{image}"
        versioned_tag = f"{full_image}:{version}"
        latest_tag = f"{full_image}:latest"

        # Build
        run("docker", ["build", "-t", versioned_tag,
                       "--build-arg", f"VERSION={version}", "."])
        # Push versioned
        run("docker", ["push", versioned_tag])
        # Tag and push latest
        run("docker", ["tag", versioned_tag, latest_tag])
        run("docker", ["push", latest_tag])

        print(f"Published Docker image: {versioned_tag}")

    def template_dir(self):
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates", "docker"
        )

    def template_vars(self, dir_path):
        """Extract template variables from config and git."""
        config = read_project_config()
        docker_config = config.get("docker", {})
        image = docker_config.get("image", "")
        registry = docker_config.get("registry", "")

        name = os.path.basename(os.path.abspath(dir_path))

        author = ""
        try:
            author = run("git", ["config", "user.name"])
        except Exception:
            pass

        return {
            "image": image,
            "registry": registry,
            "name": name,
            "author": author,
        }

    def template_mappings(self):
        return [
            {"template": "ci.yml.tpl", "target": ".github/workflows/ci.yml"},
            {"template": "publish.yml.tpl", "target": ".github/workflows/docker-publish.yml"},
        ]

    def check_project_exists(self, dir_path):
        return os.path.exists(os.path.join(dir_path, "Dockerfile"))

    def get_project_init_hint(self):
        return 'Create a Dockerfile first'
