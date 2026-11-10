#!/usr/bin/env python3
"""HOLDER LEDGER seed + replay (engine dip37 --presend-live-holder-loss PCT:SOL:WIN, --presend-live-holder-state FILE) [MEASURED, read-only].

The rule (ideas_a HOLD X2 n1 s0.1 wp0.05 age1, /home/it/sniper-studies/sniper-ideas-a/ideas.py + sim.py + load.py, frozen): a position's KEYS are its holders
>= PCT% known at the decision (the re-arm arm record's "holders" + the fill's ann.holders at landing), the T2 whale / re-arm dumper excluded
(ours are never in those lists). Every realized position adds [1, its P&L] to each key and keeps each key's best single position (the win
protection). A decision is BLOCKED when one of its keys (landing holders only with age >= 1 slot) has >= 1 position, a summed P&L <= -SOL
and no position >= +WIN. Positions in chronological order (load.py's clock: the newest t of the presend_live_* records so far; a position is
decided at its arm's clock and learned at its realized record's clock); one file per region x run number (the first in sorted order).
  --out FILE           the engine's state: {"v": 1, "h": {wallet: [n, lamports, best lamports]}, "built": {...}} (every real position)
  --replay PCT:SOL:WIN the standalone replay in "seed" mode (before each run: every real position of the earlier runs; inside the run only
                       the positions it keeps) = replay2.txt's "HOLDER LEDGER seed alone" (default 2:0.10:0.05)
usage: holder_seed.py --out FILE RUN.jsonl ... [--replay 2:0.10:0.05]"""
import argparse
import collections
import json
import os
import re
import sys


def runs_of(paths):
    seen, out = set(), []
    for p in sorted(paths):
        m = re.search(r"_r(\d+)\.jsonl$", p)
        if not m:
            continue
        key = ("FRA" if "/fra/" in p else "AMS", int(m.group(1)))
        if key in seen:
            continue
        seen.add(key)
        out.append((key[0], key[1], p))
    return out


def positions(files):
    """load.py's positions (the fields the holder rule reads)"""
    pos = []
    for reg, n, p in files:
        run = f"{reg}{n}"
        arm, fill, real, clock = {}, {}, [], 0
        with open(p, errors="replace") as fh:
            for line in fh:
                if '"ev":"presend_live_' not in line:
                    continue
                d = json.loads(line)
                e = d["ev"][13:]
                tt = d.get("t") or (d.get("trig") or {}).get("t") or (d.get("dump") or {}).get("t")
                if tt and tt > clock:
                    clock = tt
                mint = d.get("mint") or (d.get("trig") or {}).get("mint")
                k = (d.get("w"), mint)
                if e == "arm":
                    arm[k] = (d, clock)
                elif e == "fill":
                    fill.setdefault(k, d)
                elif e == "realized":
                    real.append((k, d, clock))
        for k, d, creal in real:
            a, carm = arm.get(k, (None, None))
            if a is None:
                continue
            kind = a.get("kind") or "t2"
            whale = (a.get("trig") or {}).get("wallet") if kind != "rearm" else (a.get("dump") or {}).get("seller")
            f = fill.get(k, {})
            lh = [(h["w"], h["pct"], h.get("age")) for h in ((f.get("ann") or {}).get("holders") or [])]
            ah = [(h["w"], h["pct"]) for h in (a.get("holders") or [])]
            pos.append(dict(run=run, kind=kind, mint=k[1], w=k[0], pnl=int(d["pnl"]), t_arm=carm, t_real=max(creal or 0, carm), whale=whale, ah=ah, lh=lh))
    pos.sort(key=lambda x: x["t_arm"])
    for i, p in enumerate(pos):
        p["i"] = i
    first = {}
    for x in pos:
        first.setdefault(x["run"], x["t_arm"])
    return pos, sorted(first, key=first.get)


def holders(p, minpct, minage=0):
    s = {}
    for w, pct in p["ah"]:
        if pct >= minpct:
            s[w] = max(pct, s.get(w, 0))
    for w, pct, age in p["lh"]:
        if pct >= minpct and (age is None or age >= minage):
            s[w] = max(pct, s.get(w, 0))
    return s


def lkeys(p, pct): return [w for w in holders(p, pct) if w != p["whale"]]
def ckeys(p, pct): return [w for w in holders(p, pct, 1) if w != p["whale"]]


def blocks(h, loss, win):
    return h[0] >= 1 and h[1] <= -loss and h[2] < win


def replay(pos, runs, pct, loss, win):
    """seed mode per run R (sim.run_sim(..., ("seed", R))): events in time order (arm = decide, realized = learn; a learn sorts before a
    decide at the same clock); other runs' positions always learned, run R's only when kept"""
    ev = sorted([(p["t_arm"], 1, p["i"]) for p in pos] + [(p["t_real"], 0, p["i"]) for p in pos])
    per = {}
    for R in runs:
        led = collections.defaultdict(lambda: [0, 0, -10**18])
        out = {}
        blk = []
        for _, typ, i in ev:
            p = pos[i]
            if typ == 1:
                if p["run"] == R:
                    b = any(blocks(led[w], loss, win) for w in ckeys(p, pct) if w in led)
                    out[i] = b
                    if b:
                        blk.append(-p["pnl"])
            elif p["run"] != R or out.get(i) is False:
                for w in lkeys(p, pct):
                    h = led[w]
                    h[0] += 1
                    h[1] += p["pnl"]
                    h[2] = max(h[2], p["pnl"])
        if blk:
            per[R] = blk
    return per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", default="2:0.10:0.05")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    pct, sol, win = (float(x) for x in a.replay.split(":"))
    loss, winl = round(sol * 1e9), round(win * 1e9)
    pos, runs = positions(runs_of(a.runs))
    led = collections.defaultdict(lambda: [0, 0, -10**18])
    for p in sorted(pos, key=lambda x: x["t_real"]):
        for w in lkeys(p, pct):
            h = led[w]
            h[0] += 1
            h[1] += p["pnl"]
            h[2] = max(h[2], p["pnl"])
    state = {"v": 1, "h": {w: v for w, v in sorted(led.items())},
             "built": {"by": "holder_seed.py", "pct": pct, "runs": runs, "positions": len(pos), "with_keys": sum(1 for p in pos if lkeys(p, pct))}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(a.out + ".tmp", a.out)
    print(f"runs ({len(runs)}): {' '.join(runs)}")
    print(f"positions {len(pos)}, with holder keys >= {pct}% {state['built']['with_keys']}")
    print(f"seed -> {a.out}: {len(led)} holder wallets, blocking now under {a.replay}: {sum(1 for h in led.values() if blocks(h, loss, winl))}")
    per = replay(pos, runs, pct, loss, winl)
    allb = [x for v in per.values() for x in v]
    tot = sum(allb) / 1e9
    t5 = sum(sorted(allb, reverse=True)[:5]) / 1e9
    print(f"replay seed alone {a.replay}: blocked {len(allb)} saved {tot:+.3f} SOL, w/o top5 {tot - t5:+.3f} | runs with blocks {len(per)}, "
          f">= 0 {sum(1 for v in per.values() if sum(v) >= 0)}")
    print("   per run: " + " ".join(f"{r}:{sum(per[r]) / 1e9:+.2f}({len(per[r])})" for r in runs if r in per))


if __name__ == "__main__":
    main()
