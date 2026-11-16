#!/usr/bin/env python3
"""Verify that a Gemini finding points at text the document actually contains.

This is the component the whole design leans on. A second model fabricates findings in
the same confident register as its real ones, so a finding is only reportable if the
span it quotes is really there.

The matcher tolerates invisible drift (whitespace, case, curly quotes, hyphen variants,
non-breaking spaces) because quarantining a genuine finding over a U+2010 costs a real
catch. It never alters digits, letters or symbols, so no amount of folding can turn a
fabricated quote into a matching one.
"""
import re
import unicodedata

MIN_QUOTE = 15

_FOLD = (
    ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
    ("–", "-"), ("—", "-"), ("−", "-"),
    ("‐", "-"), ("‑", "-"), (" ", " "),
)


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in _FOLD:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def anchor(finding, haystack_norm):
    """True only if every quoted span in the finding occurs in the document."""
    q = (finding.get("quoted_text") or "").strip()
    if len(q) < MIN_QUOTE:
        finding["anchor_note"] = f"quote too short to verify ({len(q)} chars)"
        return False
    if norm(q) not in haystack_norm:
        finding["anchor_note"] = "quoted_text does not appear in the document"
        return False
    second = (finding.get("second_quoted_text") or "").strip()
    if second and norm(second) not in haystack_norm:
        finding["anchor_note"] = "second_quoted_text does not appear in the document"
        return False
    return True


def partition(findings, document_text):
    """Split into (anchored, quarantined). Nothing is discarded."""
    hay = norm(document_text)
    good, bad = [], []
    for f in findings:
        (good if anchor(f, hay) else bad).append(f)
    return good, bad
