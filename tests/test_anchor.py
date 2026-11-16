#!/usr/bin/env python3
"""Offline tests. No network calls.

Covers the anchor verifier (which decides whether a Gemini item reaches the reader),
the hard path block, and the content-scan hints.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import guard                           # noqa: E402
from anchor import anchor, norm, partition   # noqa: E402

DOC = (HERE / "planted_defects.md").read_text(encoding="utf-8")
HAY = norm(DOC)

cases = [
    ("verbatim quote from the document",
     {"quoted_text": "A total of 240 participants were randomized"}, True),

    ("fabricated quote, plausible but absent",
     {"quoted_text": "The geometric mean clearance was 0.34 L/day in the elderly"}, False),

    ("real sentence with a number silently altered",
     {"quoted_text": "A total of 260 participants were randomized"}, False),

    ("too short to verify",
     {"quoted_text": "0.21 L/h"}, False),

    ("benign whitespace and case drift",
     {"quoted_text": "a total of 240   participants were\nrandomized"}, True),

    ("unicode hyphen variant tolerated (invisible drift, not fabrication)",
     {"quoted_text": "two-compartment model with first‐order elimination"}, True),

    ("good primary quote, fabricated second quote",
     {"quoted_text": "A total of 240 participants were randomized",
      "second_quoted_text": "Median overall survival was 19.1 months"}, False),

    ("both quotes real",
     {"quoted_text": "The geometric mean clearance was 0.21 L/day",
      "second_quoted_text": "The geometric mean clearance of RO9999999 was 0.21 L/h"}, True),
]

fails = 0
for name, finding, expected in cases:
    got = anchor(finding, HAY)
    ok = got == expected
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: anchored={got} expected={expected}"
          f"{'  note=' + finding['anchor_note'] if not got else ''}")

# partition keeps everything: nothing may be silently discarded
a, q = partition([dict(c[1]) for c in cases], DOC)
part_ok = len(a) + len(q) == len(cases)
fails += not part_ok
print(f"  [{'PASS' if part_ok else 'FAIL'}] partition loses nothing "
      f"({len(a)} anchored + {len(q)} quarantined = {len(cases)})")

print()
# The block is config-driven, so the test injects its own blocklist rather than
# depending on any particular deployment's paths.
probe = "/tmp/Secret Programme/report.docx"
r = subprocess.run([sys.executable, "-c",
                    f"import sys; sys.path.insert(0,{str(HERE.parent)!r});"
                    f"import guard; guard.BLOCKED = ['Secret Programme'];"
                    f"guard.check_path({probe!r})"],
                   capture_output=True, text=True)
blocked_ok = r.returncode != 0 and "REFUSED" in r.stdout + r.stderr
fails += not blocked_ok
print(f"  [{'PASS' if blocked_ok else 'FAIL'}] configured path refused (exit={r.returncode})")

_saved, guard.BLOCKED = guard.BLOCKED, ["Secret Programme"]
allowed_ok = True
try:
    guard.check_path(str(HERE / "planted_defects.md"))
except SystemExit:
    allowed_ok = False
guard.BLOCKED = _saved
fails += not allowed_ok
print(f"  [{'PASS' if allowed_ok else 'FAIL'}] unlisted path allowed")

scan_cases = [
    ("generic confidential marker", "CONFIDENTIAL - do not distribute.", True),
    ("pre-publication marker", "These results are unpublished.", True),
    ("site-specific pattern from config", "Results from ACME-12345 were pooled.", True),
    ("clean text", "The model was fitted with first-order elimination.", False),
]
# Site patterns come from config; inject one so the test is deployment-independent.
guard.HINTS = guard.HINTS + [(__import__("re").compile(r"\bACME-\d{4,}\b", 2),
                              "internal project code")]
for name, text, expect_hit in scan_cases:
    hits = guard.scan_text(text)
    ok = bool(hits) == expect_hit
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] content scan flags {name}: {bool(hits)}")

total = len(cases) + 1 + 2 + len(scan_cases)
print()
print(f"{total - fails}/{total} passed")
sys.exit(1 if fails else 0)
