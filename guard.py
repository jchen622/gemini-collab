#!/usr/bin/env python3
"""What may leave the machine, and saying out loud what is about to.

Two layers, deliberately unequal in strength:

  * A PATH BLOCK, which is absolute. Trees listed in config are refused outright,
    because their content must not reach an external service. Vertex AI is an external
    service. No override flag exists, by design.

  * A CONTENT SCAN, which is only a hint. Free-form text has no path to check, so this
    looks for markers that often accompany confidential material. It will miss things.
    It is printed as a warning beside the send banner, never relied on as a clearance.
"""
import re
import sys
from pathlib import Path

import config

# Paths whose content must never reach an external service. Site-specific: set
# "blocked_paths" in collab.config.json. Empty means nothing is blocked, which is a
# deliberate choice the deployer makes, not a default anyone should rely on.
BLOCKED = config.BLOCKED_PATHS

# Generic markers, useful anywhere. Site-specific patterns (internal id formats, project
# codenames, document types) go in collab.config.json under "content_hints" as
# [pattern, label] pairs, because what looks confidential is entirely local.
_GENERIC_HINTS = [
    (r"\bconfidential\b", "the word 'confidential'"),
    (r"\b(do not distribute|internal use only|not for distribution)\b",
     "distribution restriction"),
    (r"\b(unpublished|embargoed|pre-?decisional)\b", "pre-publication marker"),
]

HINTS = [(re.compile(p, re.I), label) for p, label in _GENERIC_HINTS]
for _pair in getattr(config, "CONTENT_HINTS", []):
    try:
        HINTS.append((re.compile(_pair[0], re.I), _pair[1]))
    except (re.error, IndexError, TypeError) as _e:
        raise SystemExit(f"bad content_hints entry {_pair!r} in config: {_e}")


def check_path(path):
    """Hard refusal. Exits rather than return a value a caller could ignore."""
    resolved = str(Path(path).resolve())
    for b in BLOCKED:
        if b in resolved:
            sys.exit(
                f"\nREFUSED: {Path(path).name}\n"
                f"  Path is under a tree configured as confidential:\n"
                f"    {b}\n"
                f"  Its content must not be sent to any external service.\n"
                f"  Vertex AI is an external service. Not sending.\n"
            )


def scan_text(text):
    """Best-effort hints only. Absence of hits means nothing."""
    found = []
    for pat, label in HINTS:
        m = pat.search(text)
        if m:
            found.append((label, m.group(0)))
    return found


def banner(what, chars, tokens, project, location, model, hints=(), source=None):
    out = ["", "  About to send content to an external service.",
           f"  content   : {what}"]
    if source:
        out.append(f"  extract   : {source}")
    out += [f"  size      : {chars:,} chars / {tokens:,} tokens",
            f"  service   : Vertex AI, project {project}, location {location}",
            f"  model     : {model}"]
    if hints:
        out.append("  WARNING   : content scan flagged possible confidential markers")
        for label, hit in hints:
            out.append(f"              - {label}: {hit!r}")
        out.append("              This scan is a hint, not a clearance. It misses things.")
    out.append("")
    return "\n".join(out)
