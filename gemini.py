#!/usr/bin/env python3
"""Minimal Vertex AI Gemini client. Python stdlib only.

Why these specific choices (all verified on this machine 2026-11-16):

  * REGIONAL ENDPOINTS DO NOT WORK. us-central1-aiplatform.googleapis.com returns an
    HTML 404 page for these publisher models. Only the global host with
    locations/global returns JSON.
  * SERIAL CALLS ONLY. A tight loop of four requests came back as HTML 404s; the
    identical single call returned clean JSON three times in a row. Same
    serial-not-parallel behaviour CLAUDE.md records for the Drive API. There is
    deliberately no threading here, and an HTML body is treated as a retryable
    throttle signal rather than a real 404.
  * FLASH ONLY. gemini-2.5-pro, gemini-3-pro-preview and gemini-3-flash-preview all
    may not exist in a given project; run `collab.py models` to discover.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import config

PROJECT = config.PROJECT
LOCATION = config.LOCATION
MODEL = config.MODEL

HOST = "https://aiplatform.googleapis.com"
TIMEOUT = 600


class GeminiError(RuntimeError):
    pass


def _endpoint(method, model=None):
    return (
        f"{HOST}/v1/projects/{PROJECT}/locations/{LOCATION}"
        f"/publishers/google/models/{model or MODEL}:{method}"
    )


_token_cache = {"value": None}


def access_token(refresh=False):
    """gcloud's own token. No key material is read or written by this module."""
    if refresh or not _token_cache["value"]:
        try:
            out = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True, text=True, timeout=60, check=True,
            )
        except subprocess.CalledProcessError as e:
            raise GeminiError(f"gcloud auth failed: {e.stderr.strip()[:300]}")
        except FileNotFoundError:
            raise GeminiError("gcloud not found on PATH")
        _token_cache["value"] = out.stdout.strip()
    return _token_cache["value"]


def _post(method, payload, model=None, max_attempts=5):
    """One serial POST with backoff. Retries 5xx, 429, and non-JSON (throttle) bodies."""
    url = _endpoint(method, model)
    last = None
    for attempt in range(1, max_attempts + 1):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {access_token(refresh=(attempt > 1 and last == 401))}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            last = e.code
            raw = e.read().decode("utf-8", "replace")
            retryable = e.code in (429, 500, 502, 503, 504) or not raw.lstrip().startswith("{")
            if e.code == 401 and attempt < max_attempts:
                retryable = True
            if not retryable or attempt == max_attempts:
                try:
                    msg = json.loads(raw)["error"]["message"]
                except Exception:
                    msg = raw[:300].replace("\n", " ")
                raise GeminiError(f"HTTP {e.code} from {method}: {msg}")
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            last = None
            if attempt == max_attempts:
                raise GeminiError(f"{method} failed after {attempt} attempts: {e}")
        time.sleep(min(2 ** attempt, 30))
    raise GeminiError(f"{method} exhausted retries")


def count_tokens(text, model=None):
    """Free, generates nothing. Also the cheapest reachability probe."""
    d = _post("countTokens",
              {"contents": [{"role": "user", "parts": [{"text": text}]}]},
              model=model)
    return d.get("totalTokens", 0)


def generate(prompt, schema=None, model=None, temperature=0.0, max_output_tokens=32768):
    cfg = {"temperature": temperature, "maxOutputTokens": max_output_tokens}
    if schema is not None:
        cfg["responseMimeType"] = "application/json"
        cfg["responseSchema"] = schema
    d = _post("generateContent",
              {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
               "generationConfig": cfg},
              model=model)

    cands = d.get("candidates") or []
    if not cands:
        fb = d.get("promptFeedback", {})
        raise GeminiError(f"no candidates returned (promptFeedback={fb})")
    cand = cands[0]
    parts = cand.get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    finish = cand.get("finishReason", "")

    if not text.strip():
        raise GeminiError(f"empty response (finishReason={finish})")
    # MAX_TOKENS mid-JSON yields a truncated object that json.loads would reject with a
    # confusing error. Surface the real cause instead.
    if schema is not None and finish == "MAX_TOKENS":
        raise GeminiError(
            "response hit maxOutputTokens and the JSON is truncated; "
            "re-run with a smaller chunk"
        )
    return (json.loads(text) if schema is not None else text), d.get("usageMetadata", {})


if __name__ == "__main__":
    import sys
    probe = sys.argv[1] if len(sys.argv) > 1 else "hi"
    print(f"project={PROJECT} location={LOCATION} model={MODEL}")
    print("countTokens:", count_tokens(probe))
