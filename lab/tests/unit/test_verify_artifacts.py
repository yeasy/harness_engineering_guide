"""Tests for publication artifact content and checksum verification."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[3]
VERIFIER = ROOT / "tools" / "verify_artifacts.py"
TITLE = "智能体 Harness 工程指南"


def _fixture_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    book = tmp_path / "book"
    book.mkdir()
    (book / "SUMMARY.md").write_text("- [Chapter](chapter.md)\n", encoding="utf-8")
    (book / "chapter.md").write_text(
        "# Chapter\n\n```mermaid\ngraph TD\nA --> B\n```\n",
        encoding="utf-8",
    )
    (book / "unpublished-notes.md").write_text(
        "```mermaid\ngraph TD\nX --> Y\n```\n",
        encoding="utf-8",
    )
    mermaid = tmp_path / "mermaid"
    mermaid.mkdir()
    (mermaid / "d-1.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><text>A</text></svg>',
        encoding="utf-8",
    )
    html = tmp_path / "guide.html"
    html.write_text(
        f"<!doctype html><title>{TITLE}</title>"
        '<section class="page"><figure class="diagram"><svg></svg></figure></section>',
        encoding="utf-8",
    )
    return book, mermaid, html


def test_verifier_accepts_titled_html_all_mermaid_and_valid_checksum(tmp_path):
    book, mermaid, html = _fixture_artifacts(tmp_path)
    digest = hashlib.sha256(html.read_bytes()).hexdigest()
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{digest}  {html.name}\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--book-dir",
            str(book),
            "--html",
            str(html),
            "--mermaid-dir",
            str(mermaid),
            "--expected-title",
            TITLE,
            "--checksum-manifest",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_verifier_rejects_missing_rendered_mermaid(tmp_path):
    book, mermaid, html = _fixture_artifacts(tmp_path)
    (mermaid / "d-1.svg").unlink()

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--book-dir",
            str(book),
            "--html",
            str(html),
            "--mermaid-dir",
            str(mermaid),
            "--expected-title",
            TITLE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Mermaid" in result.stderr


def test_pdf_smoke_uses_extracted_title_and_rejects_untitled_output(tmp_path):
    pdf = tmp_path / "guide.pdf"
    pdf.write_bytes(b"%PDF-1.7\nbody\n%%EOF\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    extractor = fake_bin / "pdftotext"
    extractor.write_text(
        "#!/bin/sh\nprintf 'unrelated document\\n'\n",
        encoding="utf-8",
    )
    extractor.chmod(0o755)

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--pdf",
            str(pdf),
            "--expected-title",
            TITLE,
        ],
        env={**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "title" in result.stderr.lower()
