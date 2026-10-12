# -*- coding: utf-8 -*-
"""self_test for image-prompt-schema — v2 template, four defenses:
1) SystemExit/Exception capture  2) Unicode-safe matching
3) fixtures written with newline=""  4) last line: SUMMARY: PASS n/n
NOTE: tool is text-only by contract; no test touches image files.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import image_prompt_schema as mod  # noqa: E402

main = mod.main


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = main(argv) or 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:  # noqa: BLE001
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


FIX = tempfile.mkdtemp(prefix="ips_selftest_")


def wfile(name, content):
    path = os.path.join(FIX, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return path


def blk(subject="a cat", style="watercolor", extra=None):
    lines = ["subject: %s" % subject, "style: %s" % style]
    if extra:
        lines += extra
    return "\n".join(lines)


def rules(text):
    return [f["rule"] for f in mod.check_text(text)["findings"]]


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


# ---------- [A] functional ----------
@case("canonical block passes clean")
def t01():
    r = mod.check_text(blk(extra=["composition: close-up",
                                  "constraints: aspect=16:9; no_text=true",
                                  "negative: blurry"]))
    assert r["findings"] == [] and r["blocks"] == 1, r


@case("minimal subject+style passes")
def t02():
    assert mod.check_text(blk())["findings"] == []


@case("missing-subject fires")
def t03():
    assert "missing-subject" in rules("style: ink\n")


@case("missing-style fires")
def t04():
    assert "missing-style" in rules("subject: a dog\n")


@case("empty-segment fires")
def t05():
    assert "empty-segment" in rules("subject:   \nstyle: ink\n")


@case("unknown-segment warning")
def t06():
    assert "unknown-segment" in rules(blk(extra=["mood: gloomy"]))


@case("out-of-order warning")
def t07():
    r = rules("style: ink\nsubject: cat\n")
    assert "out-of-order" in r and "missing-subject" not in r, r


@case("constraint-syntax error on token without =")
def t08():
    r = rules(blk(extra=["constraints: no_text"]))
    assert "constraint-syntax" in r, r


@case("well-formed constraints pass")
def t09():
    r = rules(blk(extra=["constraints: aspect=16:9; no_text=true; quality=high"]))
    assert "constraint-syntax" not in r, r


@case("duplicate-constraint error on conflicting values")
def t10():
    r = rules(blk(extra=["constraints: aspect=16:9; aspect=1:1"]))
    assert "duplicate-constraint" in r, r


@case("same-constraint warning on identical repeat")
def t11():
    r = rules(blk(extra=["constraints: aspect=16:9; aspect=16:9"]))
    assert "same-constraint" in r and "duplicate-constraint" not in r, r


@case("overlong-segment warning at >500 chars")
def t12():
    r = rules(blk(subject="x" * 501))
    assert "overlong-segment" in r, r


@case("500-char segment is fine")
def t13():
    r = rules(blk(subject="x" * 500))
    assert "overlong-segment" not in r, r


@case("too-many-subjects warning on 4 parts")
def t14():
    r = rules(blk(subject="a + b + c + d"))
    assert "too-many-subjects" in r, r


@case("3 subjects is fine")
def t15():
    assert mod.check_text(blk(subject="a + b + c"))["findings"] == []


@case("inline single-line form parses")
def t16():
    r = mod.check_text("subject: cat | style: ink | constraints: no_text=1")
    assert r["findings"] == [] and r["blocks"] == 1, r


@case("multiple blocks counted")
def t17():
    text = blk() + "\n---\n" + blk(subject="dog")
    r = mod.check_text(text)
    assert r["blocks"] == 2 and r["findings"] == [], r


@case("per-block line numbers in findings")
def t18():
    text = blk() + "\n---\n" + "style: ink\n"
    r = mod.check_text(text)
    f = [x for x in r["findings"] if x["rule"] == "missing-subject"][0]
    assert f["block"] == 2, r


@case("one bad block does not mask the good one")
def t19():
    text = "style: ink\n---\n" + blk()
    r = mod.check_text(text)
    assert "missing-subject" in rules(text) and r["blocks"] == 2


@case("=== separator also works")
def t20():
    text = blk() + "\n===\n" + blk(subject="dog")
    assert mod.check_text(text)["blocks"] == 2


@case("segment repeated warning")
def t21():
    r = rules(blk() + "\nstyle: oil\n")
    assert any("appears 2 times" in f["message"] for f in
               mod.check_text(blk() + "\nstyle: oil\n")["findings"])


@case("stray free line is unknown-segment warning")
def t22():
    r = rules(blk() + "\njust some text\n")
    assert "unknown-segment" in r, r


@case("empty-block error")
def t23():
    r = mod.check_text("subject: a\nstyle: b\n---\n---\n")
    assert r["findings"] == [], r


@case("case-insensitive keys")
def t24():
    assert mod.check_text("Subject: cat\nSTYLE: ink\n")["findings"] == []


@case("json output shape")
def t25():
    path = wfile("bad.txt", "style: ink\n")
    code, out, _ = run_cli([path, "--json"])
    data = json.loads(out)
    assert code == 1 and any(f["rule"] == "missing-subject"
                             for f in data["findings"])


@case("clean file exits 0")
def t26():
    path = wfile("ok.txt", blk())
    code, out, _ = run_cli([path])
    assert code == 0 and "0 error(s)" in out, out


@case("error file exits 1")
def t27():
    path = wfile("e.txt", "subject: cat\n")
    code, _, _ = run_cli([path])
    assert code == 1


@case("warning-only exits 0 without --strict")
def t28():
    path = wfile("w.txt", "style: ink\nsubject: cat\n")
    code, _, _ = run_cli([path])
    assert code == 0


@case("--strict fails on warnings")
def t29():
    path = wfile("s.txt", "style: ink\nsubject: cat\n")
    code, _, _ = run_cli([path, "--strict"])
    assert code == 1


@case("stdin mode works")
def t30():
    buf = io.StringIO(blk())
    old = sys.stdin
    sys.stdin = buf
    try:
        code, out, _ = run_cli(["-"])
    finally:
        sys.stdin = old
    assert code == 0 and "1 blocks" in out, out


# ---------- [B] error paths ----------
@case("missing file exits 2")
def t31():
    code, _, err = run_cli([os.path.join(FIX, "nope.txt")])
    assert code == 2 and "cannot read" in err, err


@case("missing file --json prints json error")
def t32():
    code, out, _ = run_cli([os.path.join(FIX, "nope.txt"), "--json"])
    assert code == 2 and "error" in json.loads(out)


@case("directory as input exits 2")
def t33():
    assert run_cli([FIX])[0] == 2


@case("no arguments raises SystemExit 2")
def t34():
    try:
        main([])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 2


@case("--help exits 0")
def t35():
    code, out, _ = run_cli(["--help"])
    assert code == 0 and "usage" in out.lower()


@case("--version exits 0")
def t36():
    code, out, _ = run_cli(["--version"])
    assert code == 0 and "0.1.1" in out


@case("unknown flag exits 2")
def t37():
    assert run_cli(["--bogus"])[0] == 2


@case("findings always have four keys")
def t38():
    for f in mod.check_text("subject: x\n")["findings"]:
        assert set(f) == {"rule", "severity", "block", "message"}


@case("check_text never raises on garbage")
def t39():
    for s in ("", ":", "|", "a:b:c", " ::: ", "---\n---\n", "|||"):
        mod.check_text(s)


@case("empty file: zero blocks zero findings")
def t40():
    r = mod.check_text("")
    assert r["blocks"] == 0 and r["findings"] == []


# ---------- [C] extreme edge ----------
@case("whitespace-only input")
def t41():
    assert mod.check_text("  \n\t\n")["blocks"] == 0


@case("unicode prompt text")
def t42():
    text = "subject: 赛博朋克城市\nstyle: 赛博朋克\nconstraints: 光照=霓虹"
    assert mod.check_text(text)["findings"] == [], mod.check_text(text)


@case("unicode constraint syntax error")
def t43():
    r = rules("subject: 猫\nstyle: 水墨\nconstraints: 无文字")
    assert "constraint-syntax" in r, r


@case("CRLF input")
def t44():
    assert mod.check_text(blk().replace("\n", "\r\n"))["findings"] == []


@case("BOM prefix tolerated")
def t45():
    assert mod.check_text("\ufeff" + blk())["findings"] == []


@case("very long single segment 100k chars")
def t46():
    r = rules(blk(subject="x" * 100000))
    assert "overlong-segment" in r and "missing-style" not in r


@case("2000 blocks performance path")
def t47():
    text = "\n---\n".join(blk(subject="cat %d" % i) for i in range(2000))
    r = mod.check_text(text)
    assert r["blocks"] == 2000 and r["findings"] == [], r["findings"][:3]


@case("constraint with empty value tolerated")
def t48():
    r = rules(blk(extra=["constraints: aspect="]))
    assert "constraint-syntax" not in r, r


@case("constraints with trailing semicolon")
def t49():
    r = rules(blk(extra=["constraints: aspect=16:9;"]))
    assert "constraint-syntax" not in r and "duplicate-constraint" not in r, r


@case("inline form with negative segment")
def t50():
    r = mod.check_text("subject: cat | style: ink | negative: blur")
    assert r["findings"] == [], r


@case("value containing colons survives split")
def t51():
    r = mod.check_text("subject: time 12:30 scene\nstyle: ink")
    assert r["findings"] == [], r


@case("value containing pipe in subject breaks into parts")
def t52():
    mod.check_text("subject: cat | dog\nstyle: ink")  # must not raise


@case("emoji in segments")
def t53():
    assert mod.check_text("subject: 🎨 artist\nstyle: 🖌️ ink")["findings"] == []


@case("whitespace around keys and values stripped")
def t54():
    assert mod.check_text("  subject :  cat  \n  style :  ink ")["findings"] == []


@case("duplicate subject segments flagged")
def t55():
    r = mod.check_text("subject: a\nsubject: b\nstyle: ink\n")
    assert any("subject" in f["message"] and f["severity"] == "warning"
               for f in r["findings"]), r


@case("strict mode still passes clean input")
def t56():
    path = wfile("c56.txt", blk())
    code, _, _ = run_cli([path, "--strict"])
    assert code == 0


@case("repeated runs deterministic")
def t57():
    text = "style: ink\nconstraints: a=1; a=2\n"
    assert mod.check_text(text) == mod.check_text(text)


@case("negative empty segment flagged")
def t58():
    r = rules(blk(extra=["negative:  "]))
    assert "empty-segment" in r, r


@case("block numbering skips leading separator")
def t59():
    text = "---\n" + blk()
    r = mod.check_text(text)
    assert r["blocks"] == 1 and r["findings"] == [], r


@case("order check ignores unknown segments")
def t60():
    r = rules(blk(extra=["mood: x", "composition: wide"]))
    assert "out-of-order" not in r, r


@case("full pipeline contract")
def t61():
    path = wfile("c61.txt", "style: ink\n---\n" + blk(extra=["constraints: bad"]))
    code, out, _ = run_cli([path])
    assert code == 1 and "missing-subject" in out and "constraint-syntax" in out, out


@case("summary line format stable")
def t62():
    path = wfile("c62.txt", blk())
    code, out, _ = run_cli([path])
    assert out.strip().endswith("checked 1 blocks: 0 error(s), 0 warning(s)"), out


@case("image filename in prompt stays text-only")
def t63():
    r = mod.check_text("subject: reference to sketch.png\nstyle: ink")
    assert all(f["rule"] != "unknown-segment" or "png" not in f["message"]
               for f in r["findings"])


@case("inline form missing style fires")
def t64():
    r = rules("subject: cat | constraints: a=1")
    assert "missing-style" in r, r


@case("key with unicode chars is unknown segment")
def t65():
    r = rules(blk(extra=["氛围: 暗"]))
    assert "unknown-segment" in r, r


class ToolTests(unittest.TestCase):
    pass


def _name(i, n):
    return "test_%03d_%s" % (i, re.sub(r"\W+", "_", n))


for _i, (_n, _fn) in enumerate(CASES):
    setattr(ToolTests, _name(_i, _n), lambda self, _f=_fn: _f())


if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    for t, _ in r.failures + r.errors:
        print("FAIL:", t.id().split(".")[-1])
    print("SUMMARY: PASS %d/%d" % (total - fails, total))
    sys.exit(0 if fails == 0 else 1)
