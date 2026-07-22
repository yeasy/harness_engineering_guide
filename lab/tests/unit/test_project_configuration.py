"""Regression checks for reproducible dependencies and hardened workflows."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

import yaml


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


def test_checkout_never_persists_repository_credentials():
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        workflow = path.read_text(encoding="utf-8")
        lines = workflow.splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/checkout@" not in line:
                continue
            checkout_step = "\n".join(lines[index : index + 12])
            assert re.search(r"persist-credentials:\s*false", checkout_step), (
                f"{path.name}:{index + 1} persists checkout credentials"
            )


def test_artifact_toolchain_versions_and_download_digest_are_pinned():
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.*ml"))
    )
    assert 'MDPRESS_VERSION: "0.7.14"' in workflows
    assert "6819dbc9bb606053afd9d65afb4fc4e58fb066ef6918d8a8e2497af6b528e0cb" in workflows
    assert "@mermaid-js/mermaid-cli@11.16.0" in workflows
    assert "version: 3.10" in workflows


def test_release_artifacts_are_smoke_checked_and_hashed_before_handoff():
    workflow = (WORKFLOWS / "auto-release.yml").read_text(encoding="utf-8")

    assert 'safe_tag_name="${safe_tag_name:-latest}"' in workflow
    assert "tools/verify_artifacts.py" in workflow
    assert "SHA256SUMS" in workflow
    assert "sha256sum" in workflow
    assert not re.search(r"sha256sum[\s\S]{0,240}mermaid/\*\.svg\s*>\s*SHA256SUMS", workflow)
    assert re.search(r"files:\s*\|[^\n]*(?:\n.*){0,6}SHA256SUMS", workflow)
    assert re.search(r"path:\s*\|[^\n]*(?:\n.*){0,8}SHA256SUMS", workflow)


def test_mcp_documentation_authorizes_before_reading_a_checkpoint():
    chapter = (ROOT / "09_mcp" / "9.5_miniharness_mcp.md").read_text(encoding="utf-8")

    assert (
        "1. 执行权限和护栏判断；\n"
        "2. 原子认领相同 `session_id + call_id` 的检查点；"
    ) in chapter
    assert "成功返回后保存可重放结果" in chapter


def test_preview_release_notes_script_preserves_markdown_values_in_real_bash(tmp_path):
    with (WORKFLOWS / "preview-pdf.yml").open(encoding="utf-8") as workflow_file:
        workflow = yaml.safe_load(workflow_file)
    steps = workflow["jobs"]["update-preview-pdf"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Write release notes")

    (tmp_path / "dist").mkdir()
    environment = {
        **os.environ,
        "GITHUB_SHA": "abcdef1234567890",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REPOSITORY": "owner/repository",
        "GITHUB_RUN_ID": "12345",
    }
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    notes = (tmp_path / "dist" / "release-notes.md").read_text(encoding="utf-8")
    assert "Auto-updated preview PDF from `abcdef1`." in notes
    assert "- Branch: `main`" in notes
