#!/usr/bin/env python3
# SPEED TRUTH step 5 (read-only): the same comparison on the EXECUTED-FEED clock of our own server (no block-position model):
# rival buys from the engine's tape records (logged from our fire until the position closes) vs our own landed tx, both as
# (executed-feed arrival - the dump's executed-feed arrival). Rival buys that arrived before our fire (< ~3 ms) are not in the tape.
import json, sys, os, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
R = json.load(open(f"{tl.OUT}/timeline.json"))
tape = collections.defaultdict(list)
for srv, run, base in tl.RUNS:
    for l in open(f"{tl.LIVE}/{base}.jsonl"):
        if '"tape"' not in l: continue
        r = json.loads(l)
        if r.get("ev") == "tape": tape[(base, r["mint"])].append(r)
rows = []
for r in R:
    t0 = r["t_dump_rx"]
    ours = (r["land"]["t"] if r["land"] else r["fail"]["t"]) if (r["land"] or r["fail"]) else None
    tp = [x for x in tape[(r["base"], r["mint"])] if x["t"] >= t0 and x["slot"] <= r["C"]["dump_slot"] + 2 and x["user"] not in tl.OURS and x["buy"]]
    tp.sort(key=lambda x: x["t"])
    first = (tp[0]["t"] - t0) / 1e6 if tp else None
    named = {}
    for x in tp:
        lb = tl.NAMED.get(x["user"]) or ("cohort" if x["user"] in tl.COHORT else None)
        if lb and lb not in named: named[lb] = (x["t"] - t0) / 1e6
    rows.append(dict(ours=(ours - t0) / 1e6 if ours else None, first=first, filled=r["filled"], cls=r["L"]["dump_class"], named=named,
                     before=sum(1 for x in tp if ours and x["t"] < ours)))
P = lambda v: tl.pct(v, (10, 25, 50, 75, 90))
print("EXECUTED-FEED CLOCK (ms after the dump arrived on the executed feed, our server):")
print(f"  us, all attempts          {P([x['ours'] for x in rows])}")
print(f"  us, fills                 {P([x['ours'] for x in rows if x['filled']])}")
print(f"  us, failed                {P([x['ours'] for x in rows if not x['filled']])}")
print(f"  first rival buy in tape   {P([x['first'] for x in rows])}  (n={sum(1 for x in rows if x['first'] is not None)})")
for c in ("bam", "harmonic", "jito"):
    v = [x for x in rows if x["cls"] == c]
    print(f"    {c:9s} us {tl.pct([x['ours'] for x in v])} | first rival {tl.pct([x['first'] for x in v])}")
for lb in ("HkQ7hMjy", "haqqiUUX", "8PgC4ngp", "6n2cCJrr", "G9G3dCBG", "A9KKBdLy", "cohort"):
    v = [x["named"][lb] for x in rows if lb in x["named"]]
    print(f"  {lb:10s} n={len(v):3d} {tl.pct(v)}")
print(f"  rival buys seen before our tx: fills {tl.pct([x['before'] for x in rows if x['filled']], (10, 50, 90), '{:.0f}')} | fails {tl.pct([x['before'] for x in rows if not x['filled']], (10, 50, 90), '{:.0f}')}")

# ---- the guard curve on the executed-feed clock: does our buy pass if it ARRIVES (lands) d ms after the dump on our feed?
# state after each tape trade (vsol / vtok after it, from the trade event), our own trades left out (no own impact)
def out_tokens(vsol, vtok, spend, fr):
    xin = int(spend / (1.0 + fr)); return vtok * xin // (vsol + xin)
curve = collections.defaultdict(lambda: [0, 0]); fcross = []
for r in R:
    t0 = r["t_dump_rx"]; fr = 0.0125  # pump 0.95 % protocol + 0.30 % creator fee (the engine's default when the event has none)
    ev = sorted([x for x in tape[(r["base"], r["mint"])] if x["t"] >= t0 and x["user"] not in tl.OURS and x["slot"] <= r["C"]["dump_slot"] + 2], key=lambda x: x["t"])
    # remove our own buy's impact from later states
    dv = dt_ = 0; own = [x for x in tape[(r["base"], r["mint"])] if x["user"] in tl.OURS and x["buy"]]
    st = []
    for x in sorted([x for x in tape[(r["base"], r["mint"])] if x["t"] >= t0 and x["slot"] <= r["C"]["dump_slot"] + 2], key=lambda x: (x["slot"], x["idx"], x["j"])):
        if x["user"] in tl.OURS and x["buy"]:
            dv += x["sol"]; dt_ += x["tok"]; continue     # approx: our SOL in and tokens out move the reserves
        st.append(((x["t"] - t0) / 1e6, out_tokens(x["vsol"] - dv, x["vtok"] + dt_, r["spend"], fr) >= r["min_out"]))
    st.sort()
    fc = next((t for t, ok in st if not ok), None); fcross.append((fc, r["filled"]))
    for d in (5, 10, 15, 20, 25, 30, 35, 40, 50, 75, 100):
        ok = True
        for t, p in st:
            if t < d: ok = p
            else: break
        curve[d][0] += ok; curve[d][1] += 1
print("\n  guard on the EXECUTED-FEED clock: share of all attempts that pass if our buy lands d ms after the dump (feed arrival)")
for d in sorted(curve): print(f"     {d:4d} ms: {curve[d][0]}/{curve[d][1]} ({curve[d][0] / curve[d][1]:.0%})")
print(f"  failed buys: first guard crossing on the feed clock {tl.pct([f for f, ok in fcross if not ok], (10, 25, 50, 75, 90))} ms after the dump")

# ---- rescues on the feed clock: failed buys that would pass had our tx landed dt ms earlier on the same feed clock
def g_feed(r, d):
    t0 = r["t_dump_rx"]; fr = 0.0125; dv = dt_ = 0; st = []
    for x in sorted([x for x in tape[(r["base"], r["mint"])] if x["t"] >= t0 and x["slot"] <= r["C"]["dump_slot"] + 2], key=lambda x: (x["slot"], x["idx"], x["j"])):
        if x["user"] in tl.OURS and x["buy"]: dv += x["sol"]; dt_ += x["tok"]; continue
        st.append(((x["t"] - t0) / 1e6, out_tokens(x["vsol"] - dv, x["vtok"] + dt_, r["spend"], fr) >= r["min_out"]))
    st.sort(); ok = True
    for t, p in st:
        if t < d: ok = p
        else: break
    return ok
F = [r for r in R if not r["filled"]]
def ours_feed(r): return ((r["land"]["t"] if r["land"] else r["fail"]["t"]) - r["t_dump_rx"]) / 1e6
print("\n  FEED-CLOCK rescues of the", len(F), "failed buys (our landing moved earlier by dt on the executed-feed clock):")
for lab, fn in (("exec-feed wait removed (fire on shreds)", lambda r: r["W"]["exec_wait"]),
                ("decision -> 0.2 ms", lambda r: max(0.0, r["W"]["decision"] - 0.2)),
                ("both (first write 0.2 ms after first sighting)", lambda r: max(0.0, r["W"]["first_write"] - 0.2)),
                ("5 ms earlier", lambda r: 5.0), ("10 ms earlier", lambda r: 10.0), ("15 ms earlier", lambda r: 15.0), ("20 ms earlier", lambda r: 20.0), ("30 ms earlier", lambda r: 30.0)):
    n = sum(1 for r in F if g_feed(r, ours_feed(r) - fn(r)))
    print(f"     {lab:48s} {n:3d}")
# check: the feed-clock state at OUR feed arrival predicts our result?
agree = sum(1 for r in R if g_feed(r, ours_feed(r)) == r["filled"])
print(f"  check: the feed-clock state just before our tx's feed arrival predicts fill/fail for {agree}/{len(R)}")

# ---- per client on the feed clock: us, first rival, HkQ7, haqq (medians) + our same-slot / spill split
print("\n  PER CLIENT on the executed-feed clock (median ms after the dump): us | first rival | HkQ7 | haqq | us same-slot | us spilled")
for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai"):
    v = [(x, r) for x, r in zip(rows, R) if x["cls"] == c]
    if not v: continue
    med = lambda L: f"{np.median(L):5.1f}" if L else "   - "
    print(f"     {c:9s} n={len(v):3d} | {med([x['ours'] for x, r in v if x['ours'] is not None])} | {med([x['first'] for x, r in v if x['first'] is not None])} | "
          f"{med([x['named']['HkQ7hMjy'] for x, r in v if 'HkQ7hMjy' in x['named']])} | {med([x['named']['haqqiUUX'] for x, r in v if 'haqqiUUX' in x['named']])} | "
          f"{med([x['ours'] for x, r in v if r['C']['slot_delta'] == 0])} | {med([x['ours'] for x, r in v if r['C']['slot_delta'] > 0])}")
for s in ("FRA", "AMS"):
    v = [x["ours"] for x, r in zip(rows, R) if r["srv"] == s]
    print(f"  {s}: us {tl.pct(v)}")

# ---- failed buys on the feed clock: when the guard was first crossed vs when our tx arrived
late = []
for r in F:
    t0 = r["t_dump_rx"]; fr = 0.0125; dv = dt_ = 0; st = []
    for x in sorted([x for x in tape[(r["base"], r["mint"])] if x["t"] >= t0 and x["slot"] <= r["C"]["dump_slot"] + 2], key=lambda x: (x["slot"], x["idx"], x["j"])):
        if x["user"] in tl.OURS and x["buy"]: dv += x["sol"]; dt_ += x["tok"]; continue
        st.append(((x["t"] - t0) / 1e6, out_tokens(x["vsol"] - dv, x["vtok"] + dt_, r["spend"], fr) >= r["min_out"]))
    st.sort()
    fc = next((t for t, ok in st if not ok), None)
    if fc is not None: late.append(ours_feed(r) - fc)
print(f"\n  failed buys, feed clock: our tx arrived {tl.pct(late, (10, 25, 50, 75, 90))} ms after the first guard crossing (n={len(late)}); "
      f"<= 2 ms: {sum(1 for x in late if x <= 2)}, <= 5: {sum(1 for x in late if x <= 5)}, <= 10: {sum(1 for x in late if x <= 10)}, <= 20: {sum(1 for x in late if x <= 20)}")
