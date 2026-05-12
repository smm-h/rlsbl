"""Tests for CI router generation at scale (30 projects).

Validates that _generate_router and _generate_publish_router produce
correct, parseable YAML when given large workspaces.

GitHub Actions has a 256-job limit per workflow, so 30 (or even 100)
projects are well within limits. The dorny/paths-filter action has no
documented limit on filter entries.
"""

import yaml

from rlsbl.commands.monorepo import _generate_router, _generate_publish_router

PROJECT_COUNT = 30


def _make_projects(count, *, watch=False):
    """Build a list of synthetic project dicts."""
    projects = []
    for i in range(1, count + 1):
        proj = {"name": f"project-{i}", "path": f"packages/project-{i}"}
        if watch:
            proj["watch"] = [f"shared/lib-{i}/**"]
        projects.append(proj)
    return projects


class TestCIRouterScale:
    """CI router generation with 30 projects."""

    def test_syntactic_validity(self):
        """Generated ci-router.yml parses as valid YAML."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_job_count(self):
        """ci-router has exactly 30 project jobs + 1 detect job = 31 total."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        jobs = parsed["jobs"]
        assert len(jobs) == PROJECT_COUNT + 1  # 30 projects + detect
        assert "detect" in jobs

    def test_path_filter_entries(self):
        """The dorny/paths-filter filters block has 30 entries."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        for i in range(1, PROJECT_COUNT + 1):
            name = f"project-{i}"
            path = f"packages/project-{i}"
            assert f"{name}: '{path}/**'" in content

    def test_no_duplicate_job_names(self):
        """All job names in ci-router are unique."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        job_names = list(parsed["jobs"].keys())
        assert len(job_names) == len(set(job_names))

    def test_workflow_call_references(self):
        """Each project job calls ./.github/workflows/{name}-ci.yml."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        for proj in projects:
            name = proj["name"]
            job = parsed["jobs"][name]
            assert job["uses"] == f"./.github/workflows/{name}-ci.yml"

    def test_detect_outputs(self):
        """The detect job declares an output for every project."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        detect = parsed["jobs"]["detect"]
        outputs = detect["outputs"]
        for proj in projects:
            assert proj["name"] in outputs

    def test_conditional_expressions(self):
        """Each project job has the correct if-condition on detect output."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        for proj in projects:
            name = proj["name"]
            job = parsed["jobs"][name]
            assert job["if"] == f"needs.detect.outputs.{name} == 'true'"

    def test_with_watch_paths(self):
        """Router with watch paths uses multi-line filter format for all 30 projects."""
        projects = _make_projects(PROJECT_COUNT, watch=True)
        content = _generate_router(projects)
        parsed = yaml.safe_load(content)
        # Still valid YAML and correct job count
        assert len(parsed["jobs"]) == PROJECT_COUNT + 1
        # Each project's path and watch glob appear in the content
        for proj in projects:
            assert f"- '{proj['path']}/**'" in content
            for w in proj["watch"]:
                assert f"- '{w}'" in content


class TestPublishRouterScale:
    """Publish router generation with 30 projects."""

    def test_syntactic_validity(self):
        """Generated publish-router.yml parses as valid YAML."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_job_count(self):
        """publish-router has exactly 30 project jobs (no detect job)."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        jobs = parsed["jobs"]
        assert len(jobs) == PROJECT_COUNT

    def test_no_duplicate_job_names(self):
        """All job names in publish-router are unique."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        job_names = list(parsed["jobs"].keys())
        assert len(job_names) == len(set(job_names))

    def test_tag_matching_conditions(self):
        """Each job has the correct startsWith tag condition."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        for proj in projects:
            name = proj["name"]
            job = parsed["jobs"][name]
            expected = f"startsWith(github.event.release.tag_name, '{name}@v')"
            assert job["if"] == expected

    def test_workflow_call_references(self):
        """Each project job calls ./.github/workflows/{name}-publish.yml."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        for proj in projects:
            name = proj["name"]
            job = parsed["jobs"][name]
            assert job["uses"] == f"./.github/workflows/{name}-publish.yml"

    def test_release_trigger(self):
        """Publish router triggers on release published events."""
        projects = _make_projects(PROJECT_COUNT)
        content = _generate_publish_router(projects)
        parsed = yaml.safe_load(content)
        # YAML parses bare 'on' as boolean True
        assert parsed[True] == {"release": {"types": ["published"]}}
