# Changelog

## v0.1.1 — 2026-10-13
- Round-2 fixes found by self-audit (4 failing cases → green):
  - BOM-prefixed prompt files no longer break key parsing of the first segment.
  - canonical test examples corrected to the strict `k=v` constraint grammar (bare flags like `no_text` are errors by design — documented in Trade-offs).
  - block-count semantics pinned down: leading separators produce dropped empty blocks, so `blocks` counts content blocks only.
- Self-test re-run: `python self_test.py` → `SUMMARY: PASS 65/65` (was 61/65 at first draft).

## v0.1.0 — 2026-10-13
- Initial implementation: block splitter (`---`/`===`), segment parser (multi-line and inline `|` form), eleven rules (missing-subject / missing-style / empty-segment / constraint-syntax / duplicate-constraint / same-constraint / unknown-segment / out-of-order / overlong-segment / too-many-subjects / empty-block), `--strict` mode, CLI (file/stdin, `--json`, exit 0/1/2 contract). Text-only by design: no image file is ever read.
- Self-test suite (functional / error / extreme-edge tiers), 65 cases at first draft.
