#!/usr/bin/env python3
"""verify_dip / sel_diag: data-quality checks on the claim's L=35 CV-selected trades.
 - collector gaps: synthetic (gap-repair) trades between the sell and our exit; slots in [sell slot, exit slot] with no line at
   all in the raw chunks (skipped by the leader or lost by the collector); trades of the launch in failed txs (excluded)
 - launches whose events fall in two CV blocks (train/test overlap at block boundaries)
usage: python3 -I -B sel_diag.py"""
import sys, os, json, gzip, zlib, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
R.init("mine")
SM = set()
for tag in ("R1", "R2"):
    SM |= {int(k) for k in json.load(gzip.open(os.path.join(R.WORK, tag, "smax.json.gz"), "rt"))}
S35 = json.load(open(os.path.join(HERE, "out", "cv_claim_b05.json")))["35"]["sel"]
ev = {}
for l in gzip.open(os.path.join(HERE, "out", "vx_events_mine.jsonl.gz"), "rt"):
    r = json.loads(l); ev[(r["m"], r["age"])] = r
by = collections.defaultdict(list)
for s in S35: by[(s["run"], zlib.crc32(s["m"].encode()) % 256)].append(s)
n_syn = 0; syn_pnl = 0.0; n_miss = 0; miss_pnl = 0.0; n_ok = 0; rows = []
for (tag, b), ss in sorted(by.items()):
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt"))
    for s in ss:
        r = ev.get((s["m"], s["age"]))
        if r is None or "35" not in r["info"]: continue
        inf = r["info"]["35"]; tr, _ = R.tape(data[s["m"]]["t"])
        k = next(j for j, t in enumerate(tr) if t["sig"] == r["sig"] and not t["buy"])
        win = [t for t in tr[k:] if t["s"] <= inf["E"]]
        has_syn = any(t["syn"] for t in win)
        missing = [x for x in range(r["s"], inf["E"] + 1) if x not in SM]
        pnl = r["pnl"]["35"]["c"] - 0.0016
        if has_syn: n_syn += 1; syn_pnl += pnl
        if missing: n_miss += 1; miss_pnl += pnl
        n_ok += 1
print(f"L35 selected trades checked: {n_ok}")
print(f"  with a gap-repair (synthetic) trade between the sell and our exit: {n_syn} (their PnL {syn_pnl:+.2f})")
print(f"  with a slot in [sell slot, exit slot] that has no raw line at all: {n_miss} (their PnL {miss_pnl:+.2f})")
# launches spanning two CV blocks
blk_of = collections.defaultdict(set)
cvb = json.load(open(os.path.join(HERE, "out", "cv_claim_b05.json")))["35"]["blocks"]
edges = [(b["b"], b["t0u"], b["t1u"]) for b in cvb]
allev = [json.loads(l) for l in gzip.open(os.path.join(HERE, "snap", "ev4_b05.jsonl.gz"), "rt")]
for r in allev:
    t = r["bt"] + r["age"]
    for b, t0, t1 in edges:
        if t0 <= t <= t1: blk_of[r["m"]].add(b)
span = {m for m, v in blk_of.items() if len(v) > 1}
sel_span = [s for s in S35 if s["m"] in span]
print(f"launches with events in two CV blocks: {len(span)}; selected L35 trades on them: {len(sel_span)} (PnL {sum(s['pnl'] for s in sel_span):+.2f})")
