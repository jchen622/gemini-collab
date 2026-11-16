# gemini-collab

Collaborate with Google Gemini as an independent second model: consult it, have it QC a
document, have it attack an argument, or have it reassess a claim. Built so the second
model's output is treated as a claim to be verified rather than a verdict to be trusted.

Python stdlib only, plus `python-pptx` for decks and `pdftotext` for PDFs. Runs on the
existing `gcloud` login through Vertex AI. No API key.

## Why it is built this way

A second model is worth having only if it is independent, and it is dangerous precisely
because its fabricated findings arrive in the same confident register as its real ones.

- Every document finding must carry `quoted_text` copied verbatim from the source.
- That quote is string-matched locally before the finding is reported.
- Failures are **quarantined and counted**, never silently dropped.
- Reports lead with the denominator: returned / anchored / quarantined.

The matcher tolerates invisible drift (whitespace, case, curly quotes, hyphen variants)
because quarantining a real finding over a U+2010 costs a genuine catch. It never alters
digits, letters or symbols, so folding cannot turn a fabricated quote into a real one.

## Modes

```bash
python3 collab.py check                                    # free probe
python3 collab.py models                                   # which models this project serves (free)
python3 collab.py ask "question" [--context-file F] --confirm
python3 collab.py review    <file> --confirm               # anchored QC read
python3 collab.py critique  <file|--text "..."> --confirm   # adversarial read
python3 collab.py challenge "claim" --confirm              # critical reassessment
python3 collab.py stances   "claim" --confirm              # argue both sides
python3 tests/test_anchor.py                               # 14 offline tests, no network
```

`review` and `critique` are document-grounded and anchored. `ask`, `challenge` and
`stances` operate on a claim, have nothing to anchor against, and are labelled unverified
in their own output.

**Nothing sends without `--confirm`.** Without it the tool extracts, sizes, prints the
destination banner and stops, having sent nothing.

## Files

| File | What it does |
|---|---|
| `gemini.py` | Vertex AI client. Serial, stdlib `urllib`, token from `gcloud`. |
| `extract.py` | `.docx` / `.pptx` / `.pdf` / `.md` / `.txt` to text, written to `extracted/` so the sent content is auditable. |
| `guard.py` | Hard path block on confidential trees, plus a best-effort content scan and the send banner. |
| `anchor.py` | The verifier. Decides whether a finding reaches the reader. |
| `collab.py` | CLI and report writing. |
| `prompts/` | One per mode. |
| `tests/` | 14 offline tests and the planted-defect fixture. |

## Prior art

The multi-model second-opinion idea is not new. [zen-mcp-server /
PAL MCP](https://github.com/BeehiveInnovations/zen-mcp-server) (Apache-2.0) is the mature
implementation and is worth using if you want breadth across providers.

Two of its ideas were adopted here as modes, reimplemented rather than copied:
`challenge` (force critical reassessment instead of reflexive agreement) and `listmodels`
(here as `models`). The `stances` mode is a narrowed version of its stance-based
`consensus`, honest about the fact that one model arguing both sides is not corroboration.

What this tool does that the prior art does not: **mechanically verify the reviewing
model's output against the source.** zen instructs its models not to fabricate, in the
prompt. It has no code that checks whether a returned finding actually corresponds to
text in the reviewed material. That check is the reason this exists.

## Verified behaviour (2026-11-16)

- Planted-defect test: all three planted defects found (total 118+118 vs 240 stated,
  clearance L/day vs L/h, PFS 7.4 vs 7.9 months). The 21-day IgG1 half-life trap was
  correctly not flagged.
- `critique` on the same file produced a finding `review` did not: the dose
  recommendation is unsupported without an exposure-response analysis.
- Anchor verifier: 14/14 offline, including fabricated quotes, a real sentence with one
  digit altered, a fabricated second quote beside a real first one, the path block, and
  the content scan.
- Extraction: `.docx` preserves superscript citation markers; `.docx` and `.pdf` sharing
  a stem no longer overwrite each other's extract. PUA stripping verified on synthetic
  input (U+F0B3, U+F03D).

## Environment constraints

- **Run `collab.py models` rather than assuming.** Hand-probing this endpoint in a loop
  produced HTML 404s that read as "model absent" and led to a wrong conclusion about
  which models existed. That is why discovery is a command.
- Global host only (`aiplatform.googleapis.com`, `locations/global`); regional hosts
  return HTML 404s for these models.
- Serial calls only; concurrency returns HTML 404s.
- Configure with `collab.config.json` (copy `config.example.json`), or the environment
  variables `GEMINI_COLLAB_PROJECT`, `GEMINI_COLLAB_LOCATION`, `GEMINI_COLLAB_MODEL`,
  which take precedence. There is no default project id: an unconfigured run fails with
  an explicit message rather than reporting every model as missing.

## Refusals

`guard.BLOCKED` lists trees whose content must never reach an external service. Files
under them are refused outright. The free-form content scan is a hint only and misses
things; it is not a clearance.
