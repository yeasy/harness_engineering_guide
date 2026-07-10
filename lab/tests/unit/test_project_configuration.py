"""Regression checks for reproducible dependencies and hardened workflows."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[3]
LAB = ROOT / "lab"
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION_USE = re.compile(r"^\s*-?\s*uses:\s*[^\s@]+@([^\s#]+)", re.MULTILINE)


def test_runtime_and_dev_dependencies_are_exactly_pinned():
    with (LAB / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    build_requirements = project["build-system"]["requires"]
    runtime = project["project"]["dependencies"]
    development = project["project"]["optional-dependencies"]["dev"]

    assert all("==" in requirement for requirement in build_requirements)
    assert all("==" in requirement for requirement in runtime)
    assert all("==" in requirement for requirement in development)
    assert "mcp==1.28.1" in runtime
    assert "build==1.5.1" in development
    assert "types-PyYAML==6.0.12.20260518" in development


def test_ci_matrix_covers_supported_and_current_python_with_all_quality_gates():
    workflow = (WORKFLOWS / "ci.yaml").read_text(encoding="utf-8")

    assert 'python-version: ["3.11", "3.14"]' in workflow
    assert "--cov-fail-under=80" in workflow
    assert "python -m mypy mini_harness" in workflow
    assert "python -m pylint mini_harness" in workflow
    assert "python -m build" in workflow
    assert "test_mcp_lifecycle.py" in workflow
    assert "tools/render_mermaid.py" in workflow
    assert "tools/render_mermaid.py --book-dir . --svg-out dist/mermaid --strict" in workflow
    assert "tools/build_html_reader.py" in workflow


def test_all_workflow_actions_are_immutable_and_failures_are_not_suppressed():
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        workflow = path.read_text(encoding="utf-8")
        references = ACTION_USE.findall(workflow)
        assert references, f"{path.name} has no action references"
        assert all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in references), path.name
        assert "continue-on-error: true" not in workflow
        assert "timeout-minutes:" in workflow


def test_artifact_toolchain_versions_and_download_digest_are_pinned():
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.*ml"))
    )
    assert 'MDPRESS_VERSION: "0.7.13"' in workflows
    assert "eeb96ff27b76f7e2eab7a7c61d4c7d3793e6e632e4322f1d13c7d248d702c4fa" in workflows
    assert "@mermaid-js/mermaid-cli@11.16.0" in workflows
    assert "version: 3.10" in workflows
