"""Regression tests for strict Mermaid artifact rendering."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[3]
RENDERER = ROOT / "tools" / "render_mermaid.py"


def _book_with_two_diagrams(tmp_path: Path) -> Path:
    book = tmp_path / "book"
    book.mkdir()
    (book / "SUMMARY.md").write_text("- [Chapter](chapter.md)\n", encoding="utf-8")
    (book / "chapter.md").write_text(
        "# Chapter\n\n```mermaid\ngraph TD\nA --> B\n```\n\n"
        "```mermaid\ngraph TD\nC --> D\n```\n",
        encoding="utf-8",
    )
    return book


def _fake_mmdc(tmp_path: Path, *, fail_batches: bool, fail_all: bool = False) -> Path:
    binary = tmp_path / "bin" / "mmdc"
    binary.parent.mkdir()
    binary.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
source = pathlib.Path(args[args.index('-i') + 1]).read_text(encoding='utf-8')
count = source.count('```mermaid')
if FAIL_ALL or (FAIL_BATCHES and count > 1):
    raise SystemExit(1)
output = pathlib.Path(args[args.index('-o') + 1])
for index in range(1, count + 1):
    rendered = output.with_name(f'{output.stem}-{index}{output.suffix}')
    rendered.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding='utf-8')
""".replace("FAIL_BATCHES", repr(fail_batches)).replace("FAIL_ALL", repr(fail_all)),
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary.parent


def _run_renderer(book: Path, output: Path, fake_bin: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["CHROME_BIN"] = sys.executable
    return subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--book-dir",
            str(book),
            "--svg-out",
            str(output),
            "--strict",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_retry_reduces_failed_batch_to_individual_diagrams(tmp_path):
    book = _book_with_two_diagrams(tmp_path)
    output = tmp_path / "svg"

    result = _run_renderer(book, output, _fake_mmdc(tmp_path, fail_batches=True))

    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(path.name for path in output.glob("d-*.svg")) == ["d-1.svg", "d-2.svg"]


def test_strict_mode_fails_when_any_diagram_is_missing(tmp_path):
    book = _book_with_two_diagrams(tmp_path)
    output = tmp_path / "svg"

    result = _run_renderer(
        book,
        output,
        _fake_mmdc(tmp_path, fail_batches=False, fail_all=True),
    )

    assert result.returncode != 0
    assert "STRICT FAILURE" in result.stdout


def test_strict_mode_fails_when_chrome_is_unavailable(tmp_path):
    book = _book_with_two_diagrams(tmp_path)
    output = tmp_path / "svg"
    environment = os.environ.copy()
    environment.pop("CHROME_BIN", None)
    environment["PATH"] = str(tmp_path / "empty-bin")

    result = subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--book-dir",
            str(book),
            "--svg-out",
            str(output),
            "--strict",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "STRICT FAILURE" in result.stdout
