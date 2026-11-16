#!/usr/bin/env python3
"""Site configuration, kept out of the code so the tool is portable.

Resolution order, first hit wins:
  1. environment variables (GEMINI_COLLAB_PROJECT / _LOCATION / _MODEL)
  2. collab.config.json next to this file
  3. built-in fallback for location and model only

There is deliberately NO fallback project id. A wrong project silently produces
"Publisher model was not found" for every model, which reads as "Gemini is unavailable"
rather than "you did not configure this". Failing loudly is cheaper.

collab.config.json is gitignored. Copy config.example.json and fill it in.
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
_CONFIG_PATH = HERE / "collab.config.json"

_DEFAULTS = {"location": "global", "model": "gemini-2.5-flash", "blocked_paths": []}


def _load_file():
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{_CONFIG_PATH.name} is not valid JSON: {e}")
    return {}


_FILE = _load_file()


def get(key, env_var=None, required=False):
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    if key in _FILE:
        return _FILE[key]
    if key in _DEFAULTS:
        return _DEFAULTS[key]
    if required:
        raise SystemExit(
            f"\nNot configured: '{key}'.\n"
            f"  Set {env_var or key.upper()} in the environment, or copy\n"
            f"  config.example.json to collab.config.json and fill it in.\n"
        )
    return None


PROJECT = get("project", "GEMINI_COLLAB_PROJECT", required=True)
LOCATION = get("location", "GEMINI_COLLAB_LOCATION")
MODEL = get("model", "GEMINI_COLLAB_MODEL")

# Paths whose content must never reach an external service. Site-specific by nature:
# what is confidential depends entirely on where the tool is deployed.
BLOCKED_PATHS = _FILE.get("blocked_paths", _DEFAULTS["blocked_paths"])

# Extra [regex, label] pairs for the free-form content scan, on top of the generic ones
# in guard.py. Site-specific: internal id formats, programme codenames, document types.
CONTENT_HINTS = _FILE.get("content_hints", [])
