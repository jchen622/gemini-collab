#!/usr/bin/env python3
"""Collaborate with Gemini: consult it, have it review a document, or have it attack an
argument. One entry point, one send gate, one set of guarantees.

    python3 collab.py check
    python3 collab.py ask "question"  [--context-file F] [--confirm]
    python3 collab.py review   <file>              [--confirm]
    python3 collab.py critique <file | --text "..."> [--confirm]

Constant across every mode: nothing is sent without --confirm, the content and its
destination are printed first, and Gemini's output is returned attributed to Gemini.
It is never laundered into the caller's own voice and never treated as confirmation of
anything against a source.

For the document-grounded modes (review, critique), every finding is additionally
anchored to verbatim document text and unanchored ones are quarantined. Free-form `ask`
has no document to anchor against, so its output carries no such guarantee and must be
verified independently before it is acted on.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gemini          # noqa: E402
import guard           # noqa: E402
from anchor import partition          # noqa: E402
from extract import extract_to_file   # noqa: E402

MAX_TOKENS_PER_CALL = 200_000
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quoted_text": {"type": "string"},
                    "second_quoted_text": {"type": "string"},
                    "locator": {"type": "string"},
                    "category": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "defect": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["quoted_text", "locator", "category", "severity", "defect"],
            },
        }
    },
    "required": ["findings"],
}

MODE_META = {
    "review": {
        "prompt": "full_review.md",
        "title": "Independent QC read",
        "noun": "findings",
        "what": ("An independent read of the document against itself: arithmetic, units, "
                 "denominators, inconsistent repeats, internal contradictions, and claims "
                 "the text does not support."),
    },
    "critique": {
        "prompt": "critique.md",
        "title": "Adversarial critique",
        "noun": "objections",
        "what": ("An adversarial read of the reasoning: conclusions the evidence does not "
                 "reach, unstated assumptions, confounds, and claims beyond the scope of "
                 "what is shown."),
    },
}

NOT_CONFIRMATION = (
    "**What this is not.** Nothing here is confirmed against any source. Gemini had only "
    "this document, with no access to the literature, the data, or the cited references. "
    "Each item below is a claim to be checked, not a verdict, and the absence of an item "
    "is not evidence that anything is correct."
)


def _send_gate(what, text, args, source=None):
    """Print the banner. Return True only if the caller may send."""
    ntok = gemini.count_tokens(text, model=args.model)
    hints = guard.scan_text(text)
    print(guard.banner(what, len(text), ntok, gemini.PROJECT, gemini.LOCATION,
                       args.model, hints, source))
    if not args.confirm:
        print("  Not sent. Re-run with --confirm to send.")
        if source:
            print(f"  Read {source} first to see exactly what would leave the machine.")
        return False, ntok
    return True, ntok


def _chunks(text, ntok):
    if ntok <= MAX_TOKENS_PER_CALL:
        return [text]
    approx = int(len(text) * (MAX_TOKENS_PER_CALL / ntok) * 0.9)
    paras, out, cur = text.split("\n\n"), [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 2 > approx:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def _write_report(mode, src_label, model, anchored, quarantined, usage, outdir):
    meta = MODE_META[mode]
    today = dt.date.today().isoformat()
    stem = Path(src_label).stem if Path(src_label).suffix else "inline"
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / f"{mode}_{stem}_{today}.md"
    total = len(anchored) + len(quarantined)

    L = [f"# {meta['title']}: {Path(src_label).name}", "",
         f"- Reviewed by `{model}` via Vertex AI "
         f"(project `{gemini.PROJECT}`, location `{gemini.LOCATION}`)",
         f"- Date: {today}", f"- Source: `{src_label}`", "",
         f"**What this is.** {meta['what']}", "", NOT_CONFIRMATION, "",
         "## Counts", "", "| | n |", "|---|---|",
         f"| {meta['noun'].capitalize()} returned by Gemini | {total} |",
         f"| Anchored to verbatim text (reported below) | {len(anchored)} |",
         f"| Quarantined as unverifiable (appendix) | {len(quarantined)} |", ""]
    if usage:
        L += [f"Tokens: {usage.get('promptTokenCount', 0)} in, "
              f"{usage.get('candidatesTokenCount', 0)} out.", ""]

    L += [f"## {meta['noun'].capitalize()}", ""]
    if not anchored:
        L.append(f"No anchored {meta['noun']}. Given the counts above, read that as "
                 f"\"this pass surfaced nothing it could point at\", not as \"the "
                 f"document is sound\".")
    for i, f in enumerate(anchored, 1):
        L += [f"### {i}. [{f.get('severity','?').upper()}] {f.get('category','')} "
              f"- {f.get('locator','')}", "", f.get("defect", ""), "",
              f"> {f.get('quoted_text','').strip()}"]
        if (f.get("second_quoted_text") or "").strip():
            L += [">", f"> {f['second_quoted_text'].strip()}"]
        L.append("")
        if f.get("why"):
            L += [f["why"], ""]

    if quarantined:
        L += ["## Appendix: quarantined (likely model error)", "",
              "Each of these cites text that does not occur in the document, which is the "
              "signature of a fabricated item. Listed for completeness; do not action one "
              "without checking the document yourself.", ""]
        for i, f in enumerate(quarantined, 1):
            L += [f"{i}. **{f.get('severity','?')}** {f.get('defect','')} "
                  f"({f.get('anchor_note','')})",
                  f"   - claimed quote: `{(f.get('quoted_text') or '')[:200]}`"]
        L.append("")

    dest.write_text("\n".join(L), encoding="utf-8")
    return dest


def run_document_mode(mode, args):
    """review and critique: anchored, document-grounded."""
    if getattr(args, "text", None):
        text, extract_path, label = args.text, None, "inline text"
    else:
        src = Path(args.file).resolve()
        guard.check_path(src)
        text, extract_path = extract_to_file(src, HERE / "extracted")
        label = str(src)

    ok, ntok = _send_gate(label, text, args, extract_path)
    if not ok:
        return 0

    template = (HERE / "prompts" / MODE_META[mode]["prompt"]).read_text(encoding="utf-8")
    raw, usage = [], {"promptTokenCount": 0, "candidatesTokenCount": 0}
    parts = _chunks(text, ntok)
    for i, c in enumerate(parts, 1):
        if len(parts) > 1:
            print(f"  chunk {i}/{len(parts)} ({len(c):,} chars) ...")
        data, u = gemini.generate(template.replace("<<<DOCUMENT>>>", c),
                                  schema=FINDINGS_SCHEMA, model=args.model)
        raw.extend(data.get("findings", []))
        for k in usage:
            usage[k] += u.get(k, 0)

    anchored, quarantined = partition(raw, text)
    anchored.sort(key=lambda f: SEV_ORDER.get(f.get("severity", "low"), 3))

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{mode}_{Path(label).stem or 'inline'}.json").write_text(
        json.dumps({"source": label, "mode": mode, "model": args.model,
                    "anchored": anchored, "quarantined": quarantined}, indent=2),
        encoding="utf-8")
    report = _write_report(mode, label, args.model, anchored, quarantined, usage, outdir)

    print(f"\n  returned {len(raw)}  anchored {len(anchored)}  "
          f"quarantined {len(quarantined)}")
    print(f"  report: {report}")
    return 0


# Candidates probed by `models`. countTokens is free, so discovery costs nothing.
# Having to find these by hand is a gap the prior art (zen-mcp-server's listmodels)
# gets right and this tool originally did not.
CANDIDATE_MODELS = [
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
    "gemini-2.0-flash", "gemini-2.0-flash-lite",
    "gemini-3-pro-preview", "gemini-3-flash-preview",
    "gemini-flash-latest", "gemini-pro-latest",
]


def run_models(args):
    """Probe which publisher models this project actually serves.

    Serial and slow on purpose: a tight loop against this endpoint returns HTML 404s
    that are indistinguishable from "model does not exist", which is exactly the false
    conclusion this command exists to prevent.
    """
    print(f"project={gemini.PROJECT} location={gemini.LOCATION}\n")
    available = []
    for m in CANDIDATE_MODELS:
        try:
            n = gemini.count_tokens("probe", model=m)
            available.append(m)
            print(f"  AVAILABLE    {m}  (countTokens -> {n})")
        except gemini.GeminiError as e:
            msg = str(e)
            if "was not found" in msg or "404" in msg:
                print(f"  not present  {m}")
            else:
                print(f"  ERROR        {m}: {msg[:90]}")
    print(f"\n  {len(available)}/{len(CANDIDATE_MODELS)} available. Default is "
          f"{gemini.MODEL}.")
    if not available:
        print("  Nothing resolved. Check the project id and that Vertex AI is enabled.")
    return 0


def run_statement_mode(mode, args):
    """challenge and stances: operate on a claim, not a document. Prose out.

    No anchoring is possible here (there is no document to match against), so the
    output is labelled unverified and must be checked before it is acted on.
    """
    statement = args.statement
    if mode == "challenge":
        template = (HERE / "prompts" / "challenge.md").read_text(encoding="utf-8")
        rounds = [("reassessment", template.replace("<<<STATEMENT>>>", statement))]
    else:
        base = (HERE / "prompts" / "stances.md").read_text(encoding="utf-8")
        rounds = [
            ("supporting case",
             base.replace("<<<STANCE>>>", "argue that it is CORRECT")
                 .replace("<<<STATEMENT>>>", statement)),
            ("opposing case",
             base.replace("<<<STANCE>>>", "argue that it is WRONG")
                 .replace("<<<STATEMENT>>>", statement)),
        ]

    combined = "\n".join(p for _, p in rounds)
    ok, _ = _send_gate(f"{mode}: statement of {len(statement)} chars", combined, args)
    if not ok:
        return 0

    print("=" * 72)
    print(f"GEMINI ({args.model}) - unverified, attribute it, check before acting")
    if mode == "stances":
        print("NOTE: both sides are the SAME model arguing opposite positions. Where "
              "they\nagree that is weak evidence, not independent corroboration.")
    print("=" * 72)
    for label, prompt in rounds:
        answer, _ = gemini.generate(prompt, model=args.model, temperature=0.3)
        if len(rounds) > 1:
            print(f"\n--- {label.upper()} ---")
        print(answer.strip())
    print("=" * 72)
    return 0


def run_ask(args):
    question = args.question
    context = ""
    if args.context_file:
        src = Path(args.context_file).resolve()
        guard.check_path(src)
        context, _ = extract_to_file(src, HERE / "extracted")
        question = f"{question}\n\n## Context document\n\n{context}"

    template = (HERE / "prompts" / "ask.md").read_text(encoding="utf-8")
    prompt = template.replace("<<<QUESTION>>>", question)

    ok, _ = _send_gate("free-form question" +
                       (f" + {Path(args.context_file).name}" if args.context_file else ""),
                       prompt, args)
    if not ok:
        return 0

    answer, usage = gemini.generate(prompt, model=args.model, temperature=0.3)
    print("=" * 72)
    print(f"GEMINI ({args.model}) SAYS - unverified, attribute it, check before acting")
    print("=" * 72)
    print(answer.strip())
    print("=" * 72)
    print(f"[{usage.get('promptTokenCount',0)} in / "
          f"{usage.get('candidatesTokenCount',0)} out]")
    return 0


def main():
    # Shared flags live on a parent parser so they work either before or after the
    # subcommand. `collab.py review f.docx --confirm` is how anyone would actually type
    # it, and argparse rejects that unless the subparser knows the flag too.
    # SUPPRESS matters: without it the subparser's own default overwrites a value the
    # parent already parsed, so `collab.py --confirm review f.md` would silently drop
    # the flag. Defaults are applied after parsing instead.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=argparse.SUPPRESS)
    common.add_argument("--out", default=argparse.SUPPRESS)
    common.add_argument("--confirm", action="store_true", default=argparse.SUPPRESS,
                        help="required to actually send anything")

    ap = argparse.ArgumentParser(description="Collaborate with Gemini via Vertex AI",
                                 parents=[common])
    sub = ap.add_subparsers(dest="mode", required=True)

    sub.add_parser("check", parents=[common],
                   help="free reachability probe, sends no content")
    sub.add_parser("models", parents=[common],
                   help="probe which Gemini models this project serves (free)")

    p_cha = sub.add_parser("challenge", parents=[common],
                           help="force critical reassessment of a claim")
    p_cha.add_argument("statement")

    p_sta = sub.add_parser("stances", parents=[common],
                           help="argue a claim both for and against, then compare")
    p_sta.add_argument("statement")

    p_ask = sub.add_parser("ask", parents=[common],
                           help="consult Gemini with a free-form question")
    p_ask.add_argument("question")
    p_ask.add_argument("--context-file", default=None)

    p_rev = sub.add_parser("review", parents=[common],
                           help="anchored QC read of a document")
    p_rev.add_argument("file")

    p_cri = sub.add_parser("critique", parents=[common],
                           help="adversarial critique of an argument")
    p_cri.add_argument("file", nargs="?")
    p_cri.add_argument("--text", default=None, help="critique inline text instead")

    args = ap.parse_args()
    args.model = getattr(args, "model", gemini.MODEL)
    args.out = getattr(args, "out", str(HERE / "reports"))
    args.confirm = getattr(args, "confirm", False)

    if args.mode == "check":
        print(f"project={gemini.PROJECT} location={gemini.LOCATION} model={args.model}")
        print("countTokens:", gemini.count_tokens("reachability probe", model=args.model))
        return 0
    if args.mode == "models":
        return run_models(args)
    if args.mode in ("challenge", "stances"):
        return run_statement_mode(args.mode, args)
    if args.mode == "ask":
        return run_ask(args)
    if args.mode == "critique" and not args.file and not args.text:
        ap.error("critique needs a file or --text")
    return run_document_mode(args.mode, args)


if __name__ == "__main__":
    sys.exit(main())
