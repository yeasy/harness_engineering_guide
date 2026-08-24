#!/usr/bin/env python3
"""Guard the half-width space between Chinese and Latin letters/digits.

The book carried both spellings at once — ``Harness的定义`` next to
``Harness 的定义`` — and not merely in different chapters: ``09_mcp/9.1``
alone held 87 unspaced against 79 spaced. A one-off sweep fixed 1489 places
across 90 files, but nothing stopped the next paragraph from drifting back,
because neither ``check_project_rules.py`` nor ``check_emphasis.py`` looks at
intra-line spacing at all.

What is checked: no CJK ideograph may sit directly against ``[A-Za-z0-9]``.

What is deliberately NOT checked, because the book's own majority says
otherwise:

* Half-width parentheses hugging Chinese (``项目(Agent)的经验``) — the
  baseline is 226 hugged against 9 spaced, so that is the house style.
* Chinese punctuation against Latin (``（如 UI、监控服务）``) — full-width
  punctuation already carries its own visual padding.

Everything a reader never sees as prose is masked out before the scan, using
Private Use Area characters so a placeholder can never itself be mistaken for
a letter, a digit, or an ideograph.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "_book", "node_modules", ".obsidian", "output", ".agent", "_site"}

PUA_FIRST = 0xE000          # placeholders live in the Private Use Area
CJK = r"一-鿿㐀-䶿"
LATIN = r"A-Za-z0-9"
FENCE = re.compile(r"^\s*(?:```|~~~)")
LINK_DEF = re.compile(r"^\s*\[[^\]]+\]:\s*\S+")

MASKS = (
    re.compile(r"<!--.*?-->"),
    re.compile(r"``[^`]+``"),
    re.compile(r"`[^`]*`"),
    re.compile(r"\$\$[^$]*\$\$"),
    re.compile(r"\$[^$\n]*\$"),
    re.compile(r"!?\]\([^)\s]*(?:\s+\"[^\"]*\")?\)"),
    re.compile(r"<[^<>\s][^<>]*>"),
    re.compile("(?<![\\w/])(?:https?|ftp)://[^\\s\\ue000-\\uf8ff]+"),
)

ADJACENT = re.compile(f"[{CJK}][{LATIN}]|[{LATIN}][{CJK}]")


def mask(line: str) -> str:
    counter = [0]

    def repl(_match: re.Match[str]) -> str:
        counter[0] += 1
        return chr(PUA_FIRST + counter[0] - 1)

    for pattern in MASKS:
        line = pattern.sub(repl, line)
    return line


def prose_lines(text: str):
    lines = text.split("\n")
    in_front = bool(lines) and lines[0].strip() == "---"
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if in_front:
            if number > 1 and line.strip() == "---":
                in_front = False
            continue
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or LINK_DEF.match(line):
            continue
        yield number, line


def markdown_files():
    for path in sorted(ROOT.rglob("*.md")):
        if SKIP_DIRS.isdisjoint(part for part in path.relative_to(ROOT).parts):
            yield path


def violations(text: str):
    for number, line in prose_lines(text):
        for match in ADJACENT.finditer(mask(line)):
            yield number, match.group(0), line.strip()[:100]


class CjkLatinSpacingTests(unittest.TestCase):
    def test_every_markdown_file_keeps_cjk_and_latin_apart(self) -> None:
        found = []
        for path in markdown_files():
            text = path.read_text(encoding="utf-8")
            for number, hit, snippet in violations(text):
                rel = path.relative_to(ROOT)
                found.append(f"{rel}:{number}: {hit!r} in {snippet}")
        self.assertEqual(
            [],
            found,
            "缺少中文与拉丁字符之间的半角空格：\n" + "\n".join(found[:40]),
        )

    def test_the_check_can_actually_fail(self) -> None:
        """A check that cannot fail is not evidence."""
        self.assertEqual([], list(violations("使用 Harness 的记忆子系统。\n")))
        self.assertEqual(
            [(1, "s的", "使用 Harness的记忆子系统。")],
            list(violations("使用 Harness的记忆子系统。\n")),
        )
        self.assertEqual([(1, "第4", "第4 章")], list(violations("第4 章\n")))

    def test_html_text_content_is_still_prose(self) -> None:
        """Tags are masked; the words between them are not."""
        self.assertEqual(
            [(1, "文a", "<span>中文abc</span> 属于 HTML。")],
            list(violations("<span>中文abc</span> 属于 HTML。\n")),
        )

    def test_masked_regions_are_left_alone(self) -> None:
        for sample in (
            "见 `mini_harness/核心.py` 说明。",
            "参考 [第 4 章的运行时](04_runtime/README.md)。",
            "地址是 https://example.com/中文path 这一条。",
            # a bare URL must not swallow the placeholder of a masked neighbour
            "见 [文档](a.md) https://example.com/x 结束。",
            '<img src="a.png" alt="第4章示意图"> 的属性不算正文。',
        ):
            self.assertEqual([], list(violations(sample + "\n")), sample)

    def test_house_style_exceptions_are_not_flagged(self) -> None:
        self.assertEqual([], list(violations("多个生产级智能体项目(Agent)的经验表明。\n")))
        self.assertEqual([], list(violations("平台原生沙箱（Linux 上为 Bubblewrap）。\n")))


if __name__ == "__main__":
    unittest.main()
