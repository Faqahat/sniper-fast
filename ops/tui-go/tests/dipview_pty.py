#!/usr/bin/env python3
"""dipview in a real pty: the list appears, Enter opens the selected run in dipmon, q in dipmon comes back to the list,
q quits (exit 0). Also: no mouse capture by default (no ?1000h / ?1002h / ?1003h), the Trades tab writes OSC 8 links
to GMGN, c writes the mint as OSC 52, M turns mouse capture on.
    python3 tests/dipview_pty.py [--bin dipmon-go] [--dir RUNS_DIR]"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ptygo import Pty  # noqa: E402


def until(p, pred, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        p.pump(0.1)
        if pred(p.text()):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default=os.environ.get("DIPMON_BIN", "/home/moiz/sniper-data/tui/dipmon-go"))
    ap.add_argument("--dir", default=os.environ.get("DIPVIEW_DATA", "/home/moiz/sniper-data/runs/ams/runs"))
    a = ap.parse_args()
    fails = []

    def check(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    p = Pty(a.bin, ["--view", "--dir", a.dir, "--usd", "187.42", "--load-duty", "0"], rows=40, cols=160,
            env={"TERM": "xterm-256color"})
    check(until(p, lambda s: "RUNS" in s and "start" in s), "dipview shows the run list")
    check(until(p, lambda s: "result " in s and "pre-send" in s), "the selected run's overview (result, pre-send)")
    raw = bytes(p.raw_tail)
    check(not any(x in raw for x in (b"\x1b[?1000h", b"\x1b[?1002h", b"\x1b[?1003h")), "no mouse capture by default")
    p.send("enter", 0.5)
    check(until(p, lambda s: "1 Overview" in s and "RUN P&L" in s, 30), "enter opens the run in dipmon")
    p.raw_tail.clear()
    p.send("4", 0.8)
    check(b"\x1b]8;" in bytes(p.raw_tail) and b"https://gmgn.ai/sol/token/" in bytes(p.raw_tail), "Trades: OSC 8 links to GMGN")
    p.raw_tail.clear()
    p.send("c", 0.5)
    check(b"\x1b]52;c;" in bytes(p.raw_tail), "c: OSC 52 clipboard write")
    p.raw_tail.clear()
    p.send("M", 0.5)
    check(any(x in bytes(p.raw_tail) for x in (b"\x1b[?1002h", b"\x1b[?1003h", b"\x1b[?1000h")), "M: mouse capture on")
    p.send("q", 0.5)
    check(until(p, lambda s: "RUNS" in s and "start" in s, 10), "q in dipmon returns to dipview")
    check(p.poll() is None, "dipview still running")
    p.send("q", 0.3)
    st = p.wait(10)
    check(st == 0, "q quits dipview (exit %s)" % st)
    print("ALL PASS" if not fails else "FAILED: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
