#!/usr/bin/env python3
"""Q1 FRESH-WALLET seed (engine dip42 --q1-log on, --q1-fresh-state FILE) [MEASURED, read-only on the tape].

Q1 (the w2num3 study's lead, /home/it/sniper-studies/sniper-w2num3 ex9.py + build.py) needs "the buyer had traded <= 2 tokens before": build.py's
`trig_freq = wfreq(u, s)` = the DISTINCT mints the wallet first traded in a slot BEFORE the trigger's slot, counted on the study's tape =
trades of launched, non-mayhem tokens at age <= 400 slots (build.py: `(cs > 0) & (d.s - cs <= 400) & (d.s >= cs)`). The engine keeps that
book from its own feed (psq1.rs: the same rule, the wallet's first Q1_K = 8 mints with their first slots, idle wallets forgotten after
--q1-fresh-hours); without history every wallet looks fresh ("warm": true on its records). This script builds the book from the collector
tape (/home/it/sniper-studies/sniper-reviewer/tape.py tape.load; data /data/tapes/collect/run_*; the launches of the same runs) over the
last --hours (default 48) so a run starts with history.

State FORMAT (what the engine loads and saves; psq1.rs header):
  {"v": 1, "kind": "q1_fresh", "t": <ns: the newest trade's clock>, "slot": <its slot>, "from": <ns: the history's start>,
   "k": 8, "age_max": 400,
   "w": {"<wallet base58>": [last, m, s, m, s, ...]}}             (last = the wallet's newest counted trade, unix s; m = the mint's first
                                                                    4 bytes as a little-endian u32, s = the slot of the wallet's first
                                                                    trade of it; up to 8 pairs, the EARLIEST first; a wallet with 8
                                                                    pairs is "seen 8+ tokens")
  "built" (this script's counts) is ignored by the engine.
The engine uses a state whose "t" is <= 24 h before its feed's first trade (older: ignored, a warning, the records "warm": true).

usage: PYTHONPATH=/home/it/sniper-studies/sniper-reviewer/lib python3 ops/prod/q1_fresh_seed.py [--out /home/it/sniper-data/q1/q1_fresh_seed.json]
       [--hours 48] [--end UNIX_S] [--fresh-max 2] [--show WALLET]"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, "/home/it/sniper-studies/sniper-reviewer")
sys.path.insert(0, "/home/it/sniper-studies/sniper-reviewer/lib")
import numpy as np  # noqa: E402
import tape  # noqa: E402

K = 8
AGE_MAX = 400
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b


def mint_id(m):
    """the engine's id of a mint: its first 4 bytes, little-endian u32"""
    b = b58dec(m)
    b = b"\0" * (32 - len(b)) + b
    return int.from_bytes(b[:4], "little")


def launches(t0):
    """mint -> (create slot, mayhem) of every collector run whose data can reach the window (build.py's LA: first seen wins, failed creates out)"""
    la = {}
    for f in sorted(glob.glob("/data/tapes/collect/run_*/launches.jsonl")):
        if os.path.getmtime(f) < t0 - 3600:
            continue
        for line in open(f):
            try:
                d = json.loads(line)
            except Exception:
                continue
            m = d.get("mint")
            if not m or m in la or d.get("err") is not None:
                continue
            la[m] = (int(d["slot"]), "InitializeMayhemState" in (d.get("ixn") or []))
    return la


def build(tp, la):
    """tape (sorted by s, i) + launches -> (per wallet: [(mint id, first slot)] earliest first (all of them), its newest trade (unix s), stats)"""
    cs = tp.mint.map(lambda m: la[m][0] if m in la and not la[m][1] else -1)
    young = (cs > 0) & (tp.s - cs <= AGE_MAX) & (tp.s >= cs)
    d = tp[young]
    fm = d.groupby(["user", "mint"], sort=False).s.min().reset_index()
    fm = fm.sort_values(["user", "s"], kind="stable")
    last = d.groupby("user").bt.max()
    ids = {m: mint_id(m) for m in fm.mint.unique()}
    out = {}
    for u, m, s in zip(fm.user.values, fm.mint.values, fm.s.values):
        out.setdefault(u, []).append((ids[m], int(s)))
    st = {"tape_rows": int(len(tp)), "young_rows": int(len(d)), "young_mints": int(d.mint.nunique()), "launches": len(la),
          "mayhem_launches": sum(1 for v in la.values() if v[1])}
    return out, last, st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="/home/it/sniper-data/q1/q1_fresh_seed.json")
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--end", type=float, default=None, help="the window's end (unix s; default now)")
    ap.add_argument("--fresh-max", type=int, default=2, help="Q1's fresh bound (counts only): prior tokens <= this = fresh")
    ap.add_argument("--show", default=None)
    a = ap.parse_args()
    t1 = a.end or time.time()
    t0 = t1 - a.hours * 3600
    tl = time.time()
    tp = tape.load(t0, t1)
    if not len(tp):
        sys.exit("no tape in the window")
    tp = tp[(tp.bt >= t0) & (tp.bt <= t1)]
    if not len(tp):
        sys.exit("no tape in the window")
    la = launches(t0)
    hist, last, st = build(tp, la)
    t_state = int(tp.bt.max()) * 10**9
    slot_state = int(tp.s.max())
    t_from = int(tp.bt.min()) * 10**9
    w = {}
    for u, v in hist.items():
        row = [int(last[u])]
        for m, s in v[:K]:
            row += [m, s]
        w[u] = row
    n = np.array([len(v) for v in hist.values()]) if hist else np.zeros(0, dtype=int)
    built = {"from": float(t0), "to": float(t1), "hours": a.hours, "made": time.time(), **st, "wallets": len(w),
             "fresh_le": a.fresh_max, "not_fresh": int((n > a.fresh_max).sum()), "capped": int((n >= K).sum())}
    j = {"v": 1, "kind": "q1_fresh", "t": t_state, "slot": slot_state, "from": t_from, "k": K, "age_max": AGE_MAX, "w": w, "built": built}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".new"
    with open(tmp, "w") as f:
        json.dump(j, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t + 5 * 3600))  # noqa: E731
    print(f"window {pkt(t0)} .. {pkt(t1)} PKT ({a.hours:g} h); tape {pkt(t_from / 1e9)} .. {pkt(t_state / 1e9)} PKT, {st['tape_rows']:,} trades, "
          f"loaded in {time.time() - tl:.0f} s")
    print(f"launches known {st['launches']:,} (mayhem {st['mayhem_launches']:,}); trades on launched non-mayhem tokens at age <= {AGE_MAX} slots: "
          f"{st['young_rows']:,} on {st['young_mints']:,} tokens")
    print(f"wallets {len(w):,}: 1 token {int((n == 1).sum()):,}, 2 tokens {int((n == 2).sum()):,}, 3..{K - 1} tokens {int(((n >= 3) & (n < K)).sum()):,}, "
          f">= {K} tokens (capped) {int((n >= K).sum()):,}; NOT fresh now (> {a.fresh_max} tokens) {int((n > a.fresh_max).sum()):,}")
    print(f"wrote {a.out} ({os.path.getsize(a.out):,} bytes; t {t_state}, slot {slot_state}, from {t_from})")
    if a.show:
        print(a.show, json.dumps(w.get(a.show)))


if __name__ == "__main__":
    main()
