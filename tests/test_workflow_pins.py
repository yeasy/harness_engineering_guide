#!/usr/bin/env python3
"""Guard the workflow action pins.

This repository had no workflow guard of any kind, and two defects lived in the
pins because of it:

* ``auto-release.yml`` pinned ``softprops/action-gh-release`` at a SHA that no
  longer exists in that repository — the GitHub API answers
  ``422 No commit found for SHA``. CI stayed green only because the release
  workflow runs on ``v*`` tags, so nothing exercised it; the next release would
  have failed. Twelve sibling repositories pin v3.0.2 for the same action.
* A Dependabot upgrade moved ``actions/checkout`` from v6.0.3 to v7.0.1 but left
  the trailing comment reading ``# v6`` at all five call sites. The pin was right
  and the label was wrong, which is worse than either alone — the label is the
  only part a human reads.

Neither is caught by YAML validity or by the build. The checks below are ported
from ai_beginner_guide's ``test_workflow_safety.py``, which caught the second
class in its own repository.

Deliberately NOT ported: a hardcoded (action -> sha) table. That shape is
self-locking, since only Dependabot can trigger the change and it cannot edit the
test, so every upgrade fails by construction. The cross-file consistency check
below keeps the value — catching a half-applied upgrade — without the lock.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github/workflows"
WORKFLOWS = tuple(sorted((*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml"))))

ALLOWED_ACTIONS = frozenset(
    {
        "actions/checkout",
        "actions/setup-python",
        "actions/upload-artifact",
        "browser-actions/setup-chrome",
        "dependabot/fetch-metadata",
        "pandoc/actions/setup",
        "softprops/action-gh-release",
    }
)

USES_RE = re.compile(
    r"uses:\s+(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@"
    r"(?P<sha>[0-9a-f]{40})\s+#\s+(?P<version>v\d+\.\d+\.\d+)\s*$"
)


class WorkflowPinTests(unittest.TestCase):
    def test_workflows_are_present(self) -> None:
        self.assertEqual(
            {w.name for w in WORKFLOWS},
            {
                "auto-release.yml",
                "ci.yaml",
                "dependabot-automerge.yml",
                "identity-guard.yaml",
                "preview-pdf.yml",
            },
            "a workflow was added or removed; decide whether it belongs in these guards",
        )

    def test_every_action_is_sha_pinned_with_a_full_version_comment(self) -> None:
        """A two-part comment like ``# v7`` hides which patch release is pinned.

        It also silently survives a Dependabot bump, which is exactly how ``# v6``
        came to sit next to a v7.0.1 SHA here.
        """
        for workflow in WORKFLOWS:
            text = workflow.read_text(encoding="utf-8")
            for line in (l.strip() for l in text.splitlines() if "uses:" in l):
                with self.subTest(workflow=workflow.name, line=line):
                    match = USES_RE.search(line)
                    self.assertIsNotNone(
                        match,
                        "every `uses:` must be a 40-hex SHA followed by `# vX.Y.Z`",
                    )
                    self.assertIn(match.group("action"), ALLOWED_ACTIONS)

    def test_each_action_is_pinned_identically_across_workflows(self) -> None:
        """Catches the half-applied upgrade: one workflow bumped, the rest stale."""
        observed: dict[str, set[tuple[str, str]]] = {}
        for workflow in WORKFLOWS:
            for line in workflow.read_text(encoding="utf-8").splitlines():
                match = USES_RE.search(line.strip())
                if match:
                    observed.setdefault(match.group("action"), set()).add(
                        (match.group("sha"), match.group("version"))
                    )
        self.assertTrue(observed, "no pinned actions found — the regex or layout changed")
        for action, pins in sorted(observed.items()):
            with self.subTest(action=action):
                self.assertEqual(
                    1,
                    len(pins),
                    f"{action} is pinned inconsistently across workflows: {sorted(pins)}",
                )

    def test_checkout_never_persists_credentials(self) -> None:
        for workflow in WORKFLOWS:
            text = workflow.read_text(encoding="utf-8")
            start = 0
            while (index := text.find("actions/checkout@", start)) != -1:
                with self.subTest(workflow=workflow.name, at=index):
                    self.assertIn(
                        "persist-credentials: false",
                        text[index : index + 240],
                        "checkout must not leave a usable token in the work tree",
                    )
                start = index + 1

    def test_every_workflow_declares_permissions(self) -> None:
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                self.assertIn(
                    "permissions:",
                    workflow.read_text(encoding="utf-8"),
                    "declare permissions explicitly rather than inheriting the repo default",
                )


if __name__ == "__main__":
    unittest.main()
