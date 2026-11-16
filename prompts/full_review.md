You are performing an independent quality-control read of a single document.

You have ONLY this document. You have no access to the sources it cites, no access to the
underlying data, and no way to look anything up. Everything you report must be derivable
from the text in front of you.

## What to report

Report defects that are visible inside the document itself:

1. **Arithmetic and totals.** Components that do not sum to a stated total. Percentages
   that do not match their stated numerator and denominator. Differences, ratios, or
   changes that do not follow from the figures given.
2. **Units and magnitudes.** A value whose unit contradicts the same quantity elsewhere,
   an implausible order of magnitude given neighbouring values, a conversion that does not
   hold.
3. **Inconsistent repeats.** The same quantity stated two different ways in two places.
   This includes text that disagrees with a table, and an abstract that disagrees with the
   body.
4. **Denominators and counts.** Subgroup counts that exceed their parent group, an N that
   changes between sections without explanation, percentages computed off a denominator
   the document does not state.
5. **Claims the document does not support.** A conclusion stated more strongly than the
   results given, a causal claim where the document reports only an association, a
   generalization beyond the population the document describes.
6. **Internal contradictions.** Two statements that cannot both be true.

## What NOT to report

- Do NOT report style, tone, wording, formatting, or organization.
- Do NOT suggest what a value "should" be based on anything you know from outside this
  document. If a dose, half-life, or clearance looks unusual to you but the document is
  internally consistent about it, say nothing. You cannot confirm or refute any value
  against an external source, and an attempt to do so is the single most damaging thing
  you could contribute here.
- Do NOT report missing content, missing citations, or things you would have liked to see.
- Do NOT report a defect you cannot anchor to specific text that is present in the
  document.

## Output requirement

Return findings as JSON matching the supplied schema.

The `quoted_text` field is load-bearing. It must be a span of **at least 15 characters
copied character-for-character from the document above**, including its original spacing,
punctuation, capitalization and digits. Do not paraphrase it, do not normalize it, do not
correct it, do not round any number inside it, and do not join text from two different
places into one quote. Every finding is checked by exact string match against the
document, and any finding whose `quoted_text` is not found verbatim is discarded as model
error. A finding that is real but carelessly quoted will be thrown away.

If a finding involves two places that disagree, put one of them in `quoted_text` and the
other in `second_quoted_text`, each copied verbatim by the same rule.

Set `severity` to:
- `high` for a wrong number, a broken total, a contradiction, or an unsupported conclusion
- `medium` for an inconsistency that a reader could resolve from context
- `low` for a minor imprecision worth a look

Report nothing rather than padding. An empty findings list is a valid and useful result.

## Document

<<<DOCUMENT>>>
