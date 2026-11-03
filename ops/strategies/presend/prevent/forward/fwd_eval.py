#!/usr/bin/env python3
"""dip27 FORWARD TEST of the 10-30 loss-study rules on a live run's records (read-only; times PKT).
  lone_whale  LIVE skip (--presend-live-lone-whale-slots): skips counted; what they saved = the shadow's paper P&L of the skipped windows
              (filter_savings.py, row c scaled: approximate)
  ctx85       LOG-ONLY (fill "ann"): T2 fills with another wallet >= 6% at signing and a drop < 15% (GUARDS' deeper-limit lead) -> their
              realized P&L (would-save = minus it; a deeper refill is possible, not counted)
  gcr         LOG-ONLY (arm "ann"): the creator holds >= 3% at arm and our past fills where it held >= 3% number >= 2 with sum <= -0.05 SOL
              (WHO's bad-creator lead; past = the seed of 26 earlier runs + this run's realized fills so far, record order)
  due         LOG-ONLY, APPROXIMATE (fill "ann" holder clocks): a holder >= 6% at our landing with >= 5 past holds and h3 >= 0.3 (the
              engine's hazard over 3 slots; TIMING's own hz3 also counts open positions, so this is not its exact rule)
usage: fwd_eval.py RUN.jsonl [--seed gcr_seed.json] [--since-pkt HH:MM]"""
import sys, json, collections, subprocess, datetime as dt, os
path = sys.argv[1]
seed_p = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "/home/moiz/sniper-data/prevent/forward/gcr_seed.json"
led = collections.defaultdict(lambda: [0, 0.0])
for c, d in (json.load(open(seed_p)).items() if os.path.exists(seed_p) else []): led[c] = [d["n"], d["sum"]]
arm_ann, fill_ann, kind_of, real, gcr_w = {}, {}, {}, {}, {}
skips = collections.Counter()
order = []
for line in open(path, errors="replace"):
    if '"ev":"presend_live_' not in line: continue
    d = json.loads(line); e = d["ev"]
    if e == "presend_live_skip": skips[d.get("why")] += 1; continue
    w = d.get("w")
    if e == "presend_live_arm":
        mint = d.get("mint") or (d.get("trig") or {}).get("mint")
        kind_of[(w, mint)] = d.get("kind", "t2")
        a = d.get("ann")
        if a is not None:
            arm_ann[(w, mint)] = a
            c = a.get("creator")
            n, s = led[c] if c else (0, 0.0)
            gcr_w[(w, mint)] = bool(c and a.get("cr_pct", 0) >= 3 and n >= 2 and s <= -0.05)
    elif e == "presend_live_fill" and d.get("ann") is not None:
        fill_ann[(w, d["mint"])] = d["ann"]
    elif e == "presend_live_realized":
        k = (w, d["mint"]); real[k] = d["pnl"] / 1e9; order.append(k)
        a = arm_ann.get(k)
        if a and a.get("creator") and a.get("cr_pct", 0) >= 3:
            led[a["creator"]][0] += 1; led[a["creator"]][1] += real[k]
def tally(keys):
    v = [real[k] for k in keys if k in real]
    return len(v), sum(v), sum(1 for x in v if x < -0.05)
ctx = [k for k, a in fill_ann.items() if a.get("ctx85")]
gcr = [k for k in real if gcr_w.get(k)]
due = [k for k, a in fill_ann.items() if any(h.get("pct", 0) >= 6 and h.get("n", 0) >= 5 and (h.get("h3") or 0) >= 0.3 for h in a.get("holders", []))]
fills = len(real); tot = sum(real.values())
print(f"FORWARD (dip27) {os.path.basename(path)}: {fills} realized positions, {tot:+.3f} SOL realized | annotated fills {len(fill_ann)}, arms {len(arm_ann)}")
print(f"  lone_whale (LIVE skip): {skips.get('lone_whale', 0)} triggers skipped")
fs = "/home/moiz/sniper/ops/obs/filter_savings.py"
if skips.get("lone_whale") and os.path.exists(fs):
    out = subprocess.run(["python3", fs, path], capture_output=True, text=True).stdout
    for l in out.splitlines():
        if "lone_whale" in l: print("   " + l.strip() + "  (shadow paper, approximate)")
for name, keys, what in (("ctx85", ctx, "deeper limit when another >= 6% holder"), ("gcr", gcr, "bad-creator list"), ("due (approx)", due, "a >= 6% holder due to sell")):
    n, s, big = tally(keys)
    print(f"  {name:12s} (log-only, {what}): would skip {n} fills, their P&L {s:+.3f} -> would save {-s:+.3f} SOL (big losses among them {big})")
