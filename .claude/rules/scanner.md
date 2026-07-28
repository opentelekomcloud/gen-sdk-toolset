---
description: Rules for the scanner, providers and RST parsers
paths:
  - "src/tools/scanner/**"
---

The scanner turns upstream documentation into an intermediate representation.
Upstream is not under our control, so every assumption about it must degrade
into a recorded diagnostic rather than into missing data.

- **Style classification happens before the parser runs.** The parser may assume
  a Style-A document. An unrecognized style is `UNSUPPORTED_DOC_STYLE`, which
  rolls up to `OverallStatus.UNSUPPORTED` - a distinct outcome from a parse
  failure, and it must stay distinct.
- **`ParseFailure` gates a document; `Issue` degrades a section.** Raise
  `ParseFailure` only when the document cannot be interpreted at all (no URI
  line, for instance). Everything smaller is an `Issue` attached to the section,
  with the section status moved off `ok`.
- **Every row is accounted for.** A parameter row that cannot be read counts
  into `fields_failed` or `fields_unknown_type`. It never disappears from
  `fields_total`. The validator will catch you, but write it correctly first.
- **Fallbacks emit their issue.** An unlabeled example, an unparseable type, a
  reference that could not be resolved - each has a code
  (`EXAMPLE_UNLABELED`, `UNKNOWN_TYPE_FORMAT`, `NESTED_*`). Use it even when the
  fallback is obviously right, so consumers can measure how much was guessed.
- **Never trust a listing to be complete.** GitHub caps large trees with HTTP
  200 and `truncated: true`. That is what `FileListing.truncated` and
  `incomplete_reason` exist for. Any new pagination or listing code needs a test
  with a fake provider that answers unconditionally.
- **Providers normalize their own failures** into `ProviderError` with a
  `ProviderErrorKind`. `requests` must not leak past the provider package.
- **Skipping is a decision, so it is recorded.** Paths filtered by
  `excluded_segments` go into `excluded_documents`.

Ports live in `interfaces/` and describe what the scanner needs, not what GitHub
offers. Keep provider vocabulary out of them.
