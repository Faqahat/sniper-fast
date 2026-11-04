#!/usr/bin/env python3
"""WHALE / DUMPER LOSS LEDGER seed + replay (engine dip37 --presend-live-wh-loss N:SOL, --presend-live-whale-state FILE) [MEASURED, read-only].

The ledger key of a live pre-send position = its ARM's wallet: the T2 trigger whale (presend_live_arm trig.wallet) or the re-arm dumper
(dump.seller); its value = [positions realized with us, their summed realized P&L in lamports], from presend_live_arm joined with
presend_live_realized on (w, mint) (scratchpad whaleledger2.py's rule). Runs are taken in chronological order (each run's first record's t;
one file per region x run number: the first path in sorted order), positions within a run in record order.
  --out FILE           the engine's state file: {"v": 1, "w": {wallet: [n, lamports]}, "built": {...}}
  --replay N:SOL[:sum|mean] (repeatable; default 2:0.05:sum and 2:0.01:mean): the ledger replayed over the same runs from empty, the
                       positions it would have blocked (n >= N and sum <= -SOL, or sum / n <= -SOL) and their P&L (saved = -their sum)
  --show WALLET        print one wallet's entry
usage: whale_seed.py --out FILE RUN.jsonl ... [--replay 2:0.05] [--show WALLET]"""
import argparse
import collections
import json
import os
import re
import sys


def runs_of(paths):
    """[(region, run, path)] one per region x run number (sorted paths: the first wins)"""
    seen, out = set(), []
    for p in sorted(paths):
        m = re.search(r"_r(\d+)\.jsonl$", p)
        if not m:
            print(f"skip {p}: no _rN.jsonl", file=sys.stderr)
            continue
        key = ("FRA" if "/fra/" in p else "AMS", int(m.group(1)))
        if key in seen:
            continue
        seen.add(key)
        out.append((key[0], key[1], p))
    return out


def positions(files):
    """[(first t of the run, run tag, wallet or None, pnl lamports, seq)] in chronological order; per-run coverage"""
    pos, cov = [], collections.Counter()
    for reg, n, p in files:
        arm, first = {}, None
        with open(p, errors="replace") as fh:
            for line in fh:
                if '"ev":"presend_live_' not in line:
                    continue
                d = json.loads(line)
                if first is None and d.get("t"):
                    first = d["t"]
                if d["ev"] == "presend_live_arm":
                    k = (d.get("w"), d.get("mint") or (d.get("trig") or {}).get("mint"))
                    arm[k] = (d.get("trig") or {}).get("wallet") or (d.get("dump") or {}).get("seller")
                elif d["ev"] == "presend_live_realized":
                    who = arm.get((d.get("w"), d.get("mint")))
                    cov[(reg + str(n), bool(who))] += 1
                    pos.append((first or 0, reg + str(n), who, int(d["pnl"]), len(pos)))
    pos.sort(key=lambda x: (x[0], x[4]))
    return pos, cov


def blocks(n, s, N, loss, mean):
    return n >= max(N, 1 if mean else N) and (s <= -loss * n if mean else s <= -loss)


def replay(pos, N, loss_sol, mean):
    loss = round(loss_sol * 1e9)
    led = collections.defaultdict(lambda: [0, 0])
    per = collections.defaultdict(lambda: [0, 0])
    blk = []
    for _, run, w, pnl, _ in pos:
        if not w:
            continue
        n, s = led[w]
        if blocks(n, s, N, loss, mean):
            per[run][0] += 1
            per[run][1] -= pnl
            blk.append(-pnl)
        led[w][0] += 1
        led[w][1] += pnl
    return blk, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", action="append", default=None)
    ap.add_argument("--show", action="append", default=[])
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    files = runs_of(a.runs)
    pos, cov = positions(files)
    runs = []
    for x in pos:
        if x[1] not in runs:
            runs.append(x[1])
    led = collections.defaultdict(lambda: [0, 0])
    for _, _, w, pnl, _ in pos:
        if w:
            led[w][0] += 1
            led[w][1] += pnl
    state = {"v": 1, "w": {w: v for w, v in sorted(led.items())},
             "built": {"by": "whale_seed.py", "runs": runs, "positions": len(pos), "with_wallet": sum(1 for x in pos if x[2])}}
    tmp = a.out + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, a.out)
    print(f"runs ({len(runs)}, chronological): {' '.join(runs)}")
    nowal = ", ".join(f"{r}:{c}" for (r, ok), c in sorted(cov.items()) if not ok)
    print(f"positions {len(pos)}, with an arm wallet {state['built']['with_wallet']}; without: {nowal or 'none'}")
    print(f"seed -> {a.out}: {len(led)} wallets")
    for w in a.show:
        n, s = led.get(w, [0, 0])
        print(f"  {w}: n {n} sum {s / 1e9:+.4f} SOL")
    for spec in a.replay or ["2:0.05:sum", "2:0.01:mean"]:
        p = spec.split(":")
        N, S, mode = int(p[0]), float(p[1]), (p[2] if len(p) > 2 else "sum")
        blk, per = replay(pos, N, S, mode == "mean")
        tot = sum(blk) / 1e9
        t5 = sum(sorted(blk, reverse=True)[:5]) / 1e9
        print(f"replay {mode} N{N} {'M' if mode == 'mean' else 'S'}{S}: blocked {len(blk)} saved {tot:+.3f} SOL, w/o top5 {tot - t5:+.3f} | runs with blocks {len(per)}, "
              f">= 0 {sum(1 for v in per.values() if v[1] >= 0)}")
        print("   per run: " + " ".join(f"{r}:{per[r][1] / 1e9:+.2f}({per[r][0]})" for r in runs if r in per))


if __name__ == "__main__":
    main()
