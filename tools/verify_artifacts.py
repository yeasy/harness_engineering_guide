#!/usr/bin/env python3
"""Fail closed when publication artifacts are empty, mislabeled, or incomplete."""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path


class ArtifactVerificationError(ValueError):
    """Raised when a publication artifact fails a content or integrity check."""


def _require_nonempty(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise ArtifactVerificationError(f"{label} is missing: {path}")
    content = path.read_bytes()
    if not content:
        raise ArtifactVerificationError(f"{label} is empty: {path}")
    return content


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def verify_pdf(path: Path, expected_title: str) -> None:
    """Check PDF framing and require its extracted text to contain the book title."""
    content = _require_nonempty(path, "PDF")
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
        raise ArtifactVerificationError(f"PDF framing is invalid: {path}")

    extractor = shutil.which("pdftotext")
    if extractor is None:
        raise ArtifactVerificationError("pdftotext is required for PDF content verification")
    result = subprocess.run(
        [extractor, str(path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactVerificationError(
            f"PDF text extraction failed for {path}: {result.stderr.strip()}"
        )
    if _compact_text(expected_title) not in _compact_text(result.stdout):
        raise ArtifactVerificationError(f"PDF title was not found in extracted content: {path}")


def verify_html(path: Path, expected_title: str, expected_mermaid: int | None) -> None:
    """Check the reader title, page structure, and embedded Mermaid output."""
    raw = _require_nonempty(path, "HTML")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactVerificationError(f"HTML is not UTF-8: {path}") from error

    title_match = re.search(r"<title[^>]*>(.*?)</title>", content, flags=re.I | re.S)
    title = html.unescape(title_match.group(1)) if title_match else ""
    if _compact_text(expected_title) not in _compact_text(title):
        raise ArtifactVerificationError(f"HTML title does not match the book title: {path}")
    if not re.search(r'<section\s+class="[^"]*\bpage\b', content):
        raise ArtifactVerificationError(f"HTML contains no reader pages: {path}")
    if re.search(r"MERMAIDZZ\d+ZZ|PGBKZZ", content):
        raise ArtifactVerificationError(f"HTML contains unresolved build placeholders: {path}")

    if expected_mermaid is not None:
        rendered = len(re.findall(r'class="diagram"', content))
        if rendered != expected_mermaid:
            raise ArtifactVerificationError(
                f"HTML Mermaid count mismatch: expected {expected_mermaid}, found {rendered}"
            )
        if expected_mermaid and "<svg" not in content:
            raise ArtifactVerificationError("HTML Mermaid figures do not contain inline SVG")


def count_mermaid_sources(book_dir: Path) -> int:
    """Count fenced Mermaid blocks in unique Markdown files listed by SUMMARY."""
    summary = book_dir / "SUMMARY.md"
    _require_nonempty(summary, "SUMMARY")
    root = book_dir.resolve()
    sources: list[Path] = []
    seen: set[Path] = set()
    for line in summary.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*[-*]\s+\[.*?\]\(([^)]+?)\)", line)
        if match is None or not match.group(1).strip().endswith(".md"):
            continue
        source = (root / match.group(1).strip()).resolve()
        if source.is_relative_to(root) and source.is_file() and source not in seen:
            seen.add(source)
            sources.append(source)

    count = 0
    for path in sources:
        count += len(re.findall(r"^```mermaid\s*$", path.read_text(encoding="utf-8"), re.M))
    return count


def verify_mermaid(book_dir: Path, mermaid_dir: Path) -> int:
    """Require one nonempty, sequential SVG for every Mermaid source block."""
    expected = count_mermaid_sources(book_dir)
    rendered = sorted(
        mermaid_dir.glob("d-*.svg"),
        key=lambda path: int(path.stem.removeprefix("d-")),
    )
    expected_names = [f"d-{index}.svg" for index in range(1, expected + 1)]
    if [path.name for path in rendered] != expected_names:
        raise ArtifactVerificationError(
            f"Mermaid artifact mismatch: expected {expected}, found {len(rendered)}"
        )
    for path in rendered:
        content = _require_nonempty(path, "Mermaid SVG")
        if b"<svg" not in content:
            raise ArtifactVerificationError(f"Mermaid artifact is not SVG: {path}")
    return expected


def verify_checksum_manifest(path: Path) -> None:
    """Recompute every SHA-256 entry without permitting path traversal."""
    _require_nonempty(path, "checksum manifest")
    base = path.parent.resolve()
    entries = 0
    seen: set[Path] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line)
        if match is None:
            raise ArtifactVerificationError(
                f"Invalid checksum line {line_number} in {path}"
            )
        expected, relative_name = match.groups()
        artifact = (base / relative_name).resolve()
        if not artifact.is_relative_to(base) or artifact in seen:
            raise ArtifactVerificationError(
                f"Unsafe or duplicate checksum path on line {line_number}: {relative_name}"
            )
        seen.add(artifact)
        actual = hashlib.sha256(_require_nonempty(artifact, "checksummed artifact")).hexdigest()
        if actual != expected:
            raise ArtifactVerificationError(f"Checksum mismatch for {relative_name}")
        entries += 1
    if entries == 0:
        raise ArtifactVerificationError(f"Checksum manifest has no entries: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--book-dir", type=Path)
    parser.add_argument("--mermaid-dir", type=Path)
    parser.add_argument("--expected-title", required=True)
    parser.add_argument("--checksum-manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not any((args.pdf, args.html, args.mermaid_dir, args.checksum_manifest)):
        raise ArtifactVerificationError("At least one artifact must be supplied")
    if bool(args.book_dir) != bool(args.mermaid_dir):
        raise ArtifactVerificationError("--book-dir and --mermaid-dir must be supplied together")

    expected_mermaid = None
    if args.book_dir and args.mermaid_dir:
        expected_mermaid = verify_mermaid(args.book_dir, args.mermaid_dir)
    if args.pdf:
        verify_pdf(args.pdf, args.expected_title)
    if args.html:
        verify_html(args.html, args.expected_title, expected_mermaid)
    if args.checksum_manifest:
        verify_checksum_manifest(args.checksum_manifest)
    print("Publication artifacts verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactVerificationError as error:
        print(f"Artifact verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
