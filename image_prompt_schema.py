#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""image-prompt-schema — structural validator for segmented image prompts.

It validates the *structure* of text prompts (subject/style/constraints
segments). It never generates, renders, or inspects image files — input and
output are text only.

Prompt format: blocks separated by `---` lines; each block is `key: value`
lines. Inline single-line form is also accepted:
`subject: ... | style: ... | constraints: k=v; k=v`

Known segments (canonical order): subject, style, composition, constraints,
negative.

Rules:
  missing-subject      (error)   block has no subject segment
  missing-style        (error)   block has no style segment
  empty-segment        (error)   segment present but value empty
  constraint-syntax    (error)   constraints token without 'k=v' form
  duplicate-constraint (error)   same constraint key with different values
  unknown-segment      (warning) key outside the known set
  out-of-order         (warning) segments not in canonical order
  same-constraint      (warning) constraint repeated with identical value
  overlong-segment     (warning) value longer than 500 chars
  too-many-subjects    (warning) subject has more than 3 '+'-separated parts
  empty-block          (error)   a `---`-separated block with no content

Exit codes: 0 clean-or-warnings, 1 errors, 2 I/O failure.
Pure stdlib. Python 3.8+.
"""
import argparse
import json
import sys

__version__ = "0.1.1"

CANONICAL = ("subject", "style", "composition", "constraints", "negative")
KNOWN = set(CANONICAL)
MAX_SEGMENT_LEN = 500
MAX_SUBJECTS = 3


def split_blocks(text):
    """Split into non-empty blocks on '---' lines; keep block numbers."""
    blocks = []
    cur = []
    for line in text.splitlines():
        if line.strip() in ("---", "==="):
            blocks.append(cur)
            cur = []
        else:
            cur.append(line)
    blocks.append(cur)
    out = []
    for i, b in enumerate(blocks, 1):
        if any(l.strip() for l in b):
            out.append((i, b))
    return out  # (block_no, lines); blank blocks dropped from numbering


def parse_block(lines):
    """Parse `key: value` lines; return (segments dict in order, anomalies).

    Inline `a: x | b: y` single-line form is split on ' | '.
    """
    segments = []  # (key, value)
    anomalies = []
    for line in lines:
        if not line.strip():
            continue
        if "|" in line and ":" in line:
            for part in line.split("|"):
                part = part.strip()
                if ":" in part:
                    k, v = part.split(":", 1)
                    segments.append((k.strip().lower(), v.strip()))
                elif part:
                    anomalies.append(("orphan-inline-part", part))
        elif ":" in line:
            k, v = line.split(":", 1)
            segments.append((k.strip().lower(), v.strip()))
        else:
            anomalies.append(("free-line", line.strip()))
    return segments, anomalies


def _check_constraints(value, blk, findings):
    def add(rule, severity, msg):
        findings.append({"rule": rule, "severity": severity,
                         "block": blk, "message": msg})

    seen = {}
    for token in value.split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            add("constraint-syntax", "error",
                "constraint %r is not 'k=v' form" % token)
            continue
        k, v = token.split("=", 1)
        k = k.strip().lower()
        if k in seen and seen[k] != v.strip():
            add("duplicate-constraint", "error",
                "constraint %r has conflicting values %r vs %r"
                % (k, seen[k], v.strip()))
        elif k in seen:
            add("same-constraint", "warning",
                "constraint %r repeated with identical value" % k)
        else:
            seen[k] = v.strip()


def check_text(text):
    """Validate text; return {"blocks": int, "findings": [dict]}."""
    findings = []

    def add(rule, severity, blk, msg):
        findings.append({"rule": rule, "severity": severity,
                         "block": blk, "message": msg})

    if text.startswith("\ufeff"):
        text = text[1:]
    blocks = split_blocks(text)
    for blk, lines in blocks:
        raw_nonempty = [l for l in lines if l.strip()]
        segments, anomalies = parse_block(lines)
        if not segments and anomalies:
            add("empty-block", "error", blk,
                "block has no key:value segments (%d stray line(s))"
                % len(anomalies))
            continue
        keys = [k for k, _ in segments]
        seg_map = {}
        for k, v in segments:
            seg_map.setdefault(k, []).append(v)
        for kind, val in anomalies:
            add("unknown-segment" if kind == "free-line" else
                "constraint-syntax", "warning" if kind == "free-line" else
                "error", blk, "stray content: %r" % val[:60])
        order_idx = []
        for pos, k in enumerate(keys):
            if k not in KNOWN:
                add("unknown-segment", "warning", blk,
                    "segment %r is not in %s" % (k, list(CANONICAL)))
                continue
            order_idx.append((CANONICAL.index(k), pos, k))
            vals = seg_map[k]
            v = vals[0]
            if len(vals) > 1:
                add("duplicate-constraint" if k == "constraints" else
                    "unknown-segment", "error" if k == "constraints" else
                    "warning", blk,
                    "segment %r appears %d times" % (k, len(vals)))
            if not v.strip():
                add("empty-segment", "error", blk,
                    "segment %r is empty" % k)
                continue
            if len(v) > MAX_SEGMENT_LEN:
                add("overlong-segment", "warning", blk,
                    "segment %r is %d chars (max %d)"
                    % (k, len(v), MAX_SEGMENT_LEN))
            if k == "constraints":
                _check_constraints(v, blk, findings)
            if k == "subject":
                parts = [p for p in v.split("+") if p.strip()]
                if len(parts) > MAX_SUBJECTS:
                    add("too-many-subjects", "warning", blk,
                        "%d '+'-separated subjects (max %d)"
                        % (len(parts), MAX_SUBJECTS))
        canonical_positions = [c for c, _, _ in order_idx]
        if canonical_positions != sorted(canonical_positions):
            add("out-of-order", "warning", blk,
                "segments out of canonical order %s" % (list(CANONICAL),))
        if "subject" not in seg_map:
            add("missing-subject", "error", blk, "no subject segment")
        if "style" not in seg_map:
            add("missing-style", "error", blk, "no style segment")
    findings.sort(key=lambda f: (f["block"], f["rule"]))
    return {"blocks": len(blocks), "findings": findings}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="image-prompt-schema",
        description="Structural validator for segmented image prompts "
                    "(text-only; never touches image files).")
    p.add_argument("file", help="prompt file ('-' for stdin)")
    p.add_argument("--strict", action="store_true",
                   help="treat warnings as failures")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="version",
                   version="%(prog)s " + __version__)
    args = p.parse_args(argv)
    try:
        if args.file == "-":
            text = sys.stdin.read()
        else:
            with open(args.file, "r", encoding="utf-8-sig") as f:
                text = f.read()
    except OSError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print("error: cannot read %s: %s" % (args.file, e), file=sys.stderr)
        return 2
    result = check_text(text)
    errors = [f for f in result["findings"] if f["severity"] == "error"]
    warns = len(result["findings"]) - len(errors)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for f in result["findings"]:
            print("%-20s %-7s block %s: %s"
                  % (f["rule"], f["severity"], f["block"], f["message"]))
        print("checked %d blocks: %d error(s), %d warning(s)"
              % (result["blocks"], len(errors), warns))
    if errors:
        return 1
    return 1 if (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
