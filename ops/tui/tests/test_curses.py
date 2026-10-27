#!/usr/bin/env python3
"""Curses smoke test: dipmon's real UI in a pseudo-terminal at 50x30, 80x24 and 160x50 on finished runs (one session and four
sessions): every tab, the trade details, help, filters, scope, unit swap, pause, rate keys and a resize; with TERM unset, with
--ascii under LANG=C, and with --no-color. Passes when the UI exits 0 with no traceback / UI error, and its own numbers at exit
(--exit-json) equal the finished files' totals."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import dipmon  # noqa: E402
from ptyrun import Pty  # noqa: E402

DATA = os.environ.get("DIPMON_DATA", "/home/moiz/sniper-data/runs")
RUNS = [os.path.join(DATA, "ams/runs/dip_ams_r26.jsonl"), os.path.join(DATA, "ams/runs/dip_ams_r24.jsonl")]
SIZES = [(30, 50), (24, 80), (50, 160)]
VARIANTS = [("TERM unset", {"TERM": None}, []), ("--ascii LANG=C", {"LANG": "C", "LC_ALL": "C", "TERM": "xterm"}, ["--ascii"]),
            ("--no-color vt100", {"TERM": "vt100"}, ["--no-color"])]


def expected(path):
    src = dipmon.Source(path)
    src.load_all()
    return dipmon.run_totals(src.model)


def drive(p):
    p.pump(2.0)                                  # the initial load
    for k in "1234567":
        p.send(k, 0.25)
        p.send("pgdn", 0.1)
        p.send("end", 0.1)
        p.send("home", 0.1)
    p.send("4")
    for _ in range(3):
        p.send("down", 0.05)
    p.send("enter", 0.3)
    p.send("pgdn", 0.1)
    p.send("u", 0.2)
    p.send("esc", 0.2)
    for _ in range(6):
        p.send("f", 0.1)
    p.send("6")
    p.send("f")
    p.send("w")
    p.send("pgup")
    p.send("end")
    p.send("s")
    p.send("s")
    p.send("s")
    p.send("1")
    p.send("p")
    p.send("tab")
    p.send("btab")
    p.send("p")
    p.send("?", 0.3)
    p.send("x")
    p.send("+")
    p.send("-")
    p.send("r")
    p.resize(max(10, p.rows - 4), max(40, p.cols - 10), 0.4)
    p.send("2", 0.3)
    p.resize(p.rows + 4, p.cols + 10, 0.4)
    p.send("q")


def main():
    fails = []
    tmp = tempfile.mkdtemp(prefix="dipmon-c-")
    for path in RUNS:
        if not os.path.exists(path):
            print(f"missing {path}: skipped")
            continue
        exp = expected(path)
        name = os.path.basename(path)[:-6]
        cases = [(r, c, "TERM=xterm-256color", {"TERM": "xterm-256color"}, []) for r, c in SIZES] + \
                [(24, 80, vn, env, extra) for vn, env, extra in VARIANTS]
        for rows, cols, vname, env, extra in cases:
            ej = os.path.join(tmp, f"exit-{name}-{cols}x{rows}.json")
            p = Pty(["--file", path, "--usd", "100", "--strict", "--exit-json", ej] + extra, rows, cols, env=env)
            drive(p)
            st = p.wait(30)
            txt = p.text()
            ok = st == 0 and "Traceback" not in txt and "UI ERROR" not in txt
            same = False
            if os.path.exists(ej):
                j = json.load(open(ej))
                same = j["total_lamports"] == exp["total"] and j["presend"]["fills"] == exp["ps_fills"] and j["regular"]["fills"] == exp["reg_fills"]
            if vname.startswith("--ascii"):
                ok = ok and all(ord(c) < 128 or c in "�" for c in txt)
            line = f"{name:<12} {cols:>3}x{rows:<3} {vname:<20} exit {st}  bytes {p.total:>7}  totals {'equal' if same else 'DIFFER'}"
            print(("  ok   " if ok and same else "  FAIL ") + line)
            if not (ok and same):
                fails.append(line)
                tb = txt[txt.find("Traceback"):][:1500] if "Traceback" in txt else ""
                if tb:
                    print(tb)
    shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
