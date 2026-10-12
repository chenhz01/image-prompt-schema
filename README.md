# image-prompt-schema

image-prompt-schema is a structural validator for segmented image prompts: it enforces a `subject / style / composition / constraints / negative` schema, checks constraint `k=v` grammar, and catches duplicates and conflicts before a prompt batch hits your generation pipeline. Text in, findings out — it never renders or inspects image files. Confidence: High (≥80%) for all eleven rules, per the 65-case suite.

## Problem

Image prompts degenerate into prose soup: the subject is buried in line 4, two `aspect` constraints contradict each other, the "negative" section leaks into the style, and nobody notices until a 500-prompt batch renders wrong. Batch pipelines make it worse — one malformed prompt fails silently or, worse, renders expensively. A schema gate at prompt-authoring time costs seconds and prevents the whole class.

## How it works

1. **Blocks** — a prompt file is split into blocks by `---` (or `===`) lines; each block is one prompt. An inline single-line form also parses: `subject: cat | style: ink | constraints: no_text=true`.
2. **Schema** — known segments in canonical order: `subject`, `style`, `composition`, `constraints`, `negative`. Keys are case-insensitive; values keep their colons and spacing.
3. **Rules** —
   - **missing-subject / missing-style** (error): the two mandatory segments.
   - **empty-segment** (error): key present, value blank.
   - **constraint-syntax** (error): constraints must be `k=v` pairs split by `;` — bare flags are rejected so the grammar stays machine-parseable.
   - **duplicate-constraint** (error): same constraint key, different values (`aspect=16:9; aspect=1:1`); identical repeats are a `same-constraint` warning.
   - **unknown-segment** (warning), **out-of-order** (warning), **overlong-segment** (warning, >500 chars), **too-many-subjects** (warning, >3 `+`-parts).
4. **Exit contract** — 0 clean or warnings, 1 errors (or warnings under `--strict`), 2 I/O failure. `--json` for CI.

## Quickstart (~2 min)

```bash
# step 1: validate a prompt file (~0.07 s for 5000 blocks)
python image_prompt_schema.py prompts.txt
# step 2: strict mode — warnings also fail
python image_prompt_schema.py prompts.txt --strict
# step 3: CI mode
python image_prompt_schema.py prompts.txt --json
# full suite (~1 s)
python self_test.py   # SUMMARY: PASS 65/65 [Measured]
```

Library use: `check_text(text)` → `{"blocks": int, "findings": [dict]}`.

## Why not X? (as of 2026-10-13)

**No direct equivalent found as of 2026-10-13** — no standalone stdlib-only structural validator for segmented text-to-image prompts was located in the searched space. Nearest adjacent options:

- **ComfyUI / Automatic1111 prompt syntax** — render-time conventions (weights, wildcards), not a validation layer; they interpret whatever text arrives, including contradictory constraints, and require the whole generation stack.
- **JSON-schema validators (jsonschema)** — would work if prompts *were* JSON, but prompt files are authored as human-readable text; forcing JSON kills the authoring workflow this tool is built for.
- **General linters (vale, markdownlint)** — prose quality, no segment schema, no constraint grammar, no block-level exit contract.
- **Prompt-management SaaS** — version and store prompts but validate little structure, and they take your prompt library out of the repo.

## Performance

All numbers [Measured] on this machine (Windows, Python 3.x, single run):

| Input | Time | Command |
|---|---|---|
| 573 KB, 5,000 blocks (5,000 findings) | 0.068 s | see repro below |
| 65-case self-test suite | 0.10 s | `python self_test.py` |

Repro:

```bash
python -c "import time,image_prompt_schema as m; t='\n---\n'.join('subject: item %d\nstyle: watercolor\nconstraints: aspect=16:9; no_text=true'%(i,) for i in range(5000)); t0=time.perf_counter(); r=m.check_text(t); print('%.3f s'%(time.perf_counter()-t0), r['blocks'],'blocks')"
```

## Minimal Fallback (PLAN B)

No Python: `grep -L "^subject:" prompt.txt` (per file) finds missing subjects; `grep -n "aspect=" prompt.txt | sort | uniq -c -f1 | awk '$1>1'` surfaces conflicting aspect values. You lose block batching, constraint grammar checking, order/severity semantics, and the exit-code contract.

## Design Trade-offs

Priority order: **machine-parseable-constraints > catch-real-conflicts > zero-dependency > expressiveness**. Bare constraint flags (`no_text` without a value) are deliberately rejected — a grammar that sometimes has values and sometimes doesn't cannot be diffed, aggregated, or enforced downstream, and "it usually renders fine" is exactly the ambiguity this tool exists to remove. Near-miss issues (order, length, subject count) are warnings so authoring style stays free. No semantic quality judgment is attempted: "a cat" vs "feline mammal" is not the tool's business. Image generation itself is explicitly out of scope — the tool is a *text* gate and never reads image files.

## Limits & Second-order Effects

- Structure-only: a schema-perfect prompt can still be a bad prompt (wrong subject, ugly style words).
- The five-segment schema is opinionated; teams with more segment types must edit `CANONICAL` (one line) — unknown segments are warnings, not errors, so extension is graceful.
- The inline `|` form and the multi-line form cannot be mixed in one block; a value containing a literal `|` will be misread as segment splits.
- Second-order: strict gates push authors toward template-clone prompts, reducing stylistic diversity — keep `--strict` for batch pipelines only, not for human-authored single prompts.
- Constraint vocabularies are free-form: `aspect` vs `aspect_ratio` are not unified; teams should publish a constraint dictionary alongside this tool.

## FAQ

**Q: Does it generate images or call any model API?**
No. It is a pure text validator — it never reads, writes, or renders image files.

**Q: Why must constraints be `k=v`?**
So they can be parsed, diffed, and enforced by scripts; bare prose constraints are the failure mode this tool prevents.

**Q: Can I add my own segments?**
Yes — edit `CANONICAL` in `image_prompt_schema.py`; unknown segments are warnings meanwhile.

**Q: When NOT to use this tool?**
For free-form artistic prompts where structure is unwanted, for chat-style one-off generations, or if your pipeline already stores prompts as structured JSON — then a plain JSON-schema validator is the better layer.

**Q: What about weights like `(subject:1.2)`?**
They survive as subject value text; the tool validates structure, not renderer-specific weight syntax.

## [Core Assumptions]

1. Prompt batches benefit from a fixed segment schema with two mandatory segments (subject, style).
2. Constraints are machine-consumed, so their grammar must be strict `k=v` pairs — free text does not belong in that segment.
3. Block files (`---` separated) are the common batch format; inline single-line prompts are a compatible shortcut form.
4. Validation happens at authoring/commit time, before any generation spend.

Confidence: High (≥80%) for the eleven rules (65-case suite); Medium (60–79%) for the five-segment schema's universality across teams — it is a designed convention, not an observed standard. Data as of 2026-10-13.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [rfc2119-keyword-lint](https://github.com/chenhz01/rfc2119-keyword-lint) · [onboarding-checklist-check](https://github.com/chenhz01/onboarding-checklist-check) · [storyboard-consistency-check](https://github.com/chenhz01/storyboard-consistency-check)
