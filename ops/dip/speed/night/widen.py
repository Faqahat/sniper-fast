#!/usr/bin/env python3
# READ-ONLY: what if the dip engine took MORE of the dumps it scored? (live runs FRA r14 / AMS r13, their own near leaders, in-envelope,
# launch ok). Each dump replayed on the real chain tape: entry = curve just before (dump slot, dump idx + OFF) [our measured median
# landing], +5% guard vs the post-dump price (else a revert, -0.0005), exit = curve at the run's hold slots later, 0.35 SOL,
# 1.25% fee per side, 0.002 SOL tx+tips per filled round trip, 20% cut of gains (our buy prices out some followers).
import json, collections, bisect, statistics, sys
import os; rows = json.load(open(os.environ.get("ROWS", "rows_recent.json"))); L = json.load(open("leaders_by_slot.json"))
OFF = int(sys.argv[1]) if len(sys.argv) > 1 else 80
tape = collections.defaultdict(list)
for r in rows:
    if r[4]:
        for t in r[11]: tape[t[0]].append((r[0], r[1], t[5], t[6]))
for m in tape: tape[m].sort()
def before(m, s, i):
    v = tape.get(m, []); k = bisect.bisect_left(v, (s, i, -1, -1)) - 1
    return v[k] if k >= 0 else None
S = 0.35e9; FEE = 0.0125
def replay(m, s, i, hold):
    post = before(m, s, i + 1); ent = before(m, s, i + 1 + OFF)
    if not post or not ent: return None
    if (ent[2] / ent[3]) / (post[2] / post[3]) > 1.05: return -0.0005
    x = S * (1 - FEE); q = ent[3] * x / (ent[2] + x)
    ex = before(m, s + hold + 1, 0) or ent
    out = (ex[2] + x) * q / ex[3] * (1 - FEE)
    p = (out - S) / 1e9 - 0.002
    return p * 0.8 if p > 0 else p
for fn, nf in [tuple(x.split(":")) for x in os.environ.get("RUNS", "dip_r14.jsonl:near_fra.txt,dip_ams_r13.jsonl:near_ams.txt").split(",")]:
    near = {l.strip() for l in open(nf) if l.strip()}
    D, hold, real = [], 6, {}
    for l in open(fn):
        r = json.loads(l)
        if r["ev"] == "run_start": hold = r.get("hold_slots", 6)
        elif r["ev"] == "dump" and r.get("launch_ok") and L.get(str(r["slot"])) in near: D.append(r)
        elif r["ev"] == "close" and r.get("curve_pnl") is not None: real[r["dump_sig"]] = r["curve_pnl"] / 1e9
    hold = int(os.environ.get("HOLDX", hold))
    for d in D: d["val"] = replay(d["mint"], d["slot"], d["idx"], hold)
    D = [d for d in D if d["val"] is not None]
    if os.environ.get("SKIPLATE"):
        MX = json.load(open(os.environ.get("ROWS", "rows_recent.json") + ".mx"))
        D = [d for d in D if d["idx"] / max(MX.get(str(d["slot"]), 1), 1) <= float(os.environ["SKIPLATE"])]
    cal = [(d["val"], real[d["sig"]]) for d in D if d["sig"] in real]
    npick = sum(1 for d in D if d["pass"]); nm2 = sum(1 for d in D if d.get("m2_pick"))
    print(f"\n=== {fn}: near-leader in-envelope dumps replayed {len(D)} | today's picks {npick} | new-model picks {nm2} | hold {hold} slots")
    if cal: print(f"   replay vs real curve P&L on the {len(cal)} fired picks: replay {sum(a for a,_ in cal):+.3f} vs real {sum(b for _,b in cal):+.3f} SOL")
    for key, base in (("score", npick), ("m2", nm2)):
        v = sorted([d for d in D if d.get(key) is not None], key=lambda d: -d[key])
        if not v or base == 0: continue
        for mult in (1.0, 1.5, 2.0, 3.0):
            top = v[:max(1, int(base * mult))]
            if os.environ.get("ONEPOS"):       # one open position at a time: skip a pick within 12 slots of the last taken one
                taken, last = [], -10**9
                for d in sorted(top, key=lambda d: (d["slot"], d["idx"])):
                    if d["slot"] >= last + 12: taken.append(d); last = d["slot"]
                top = taken
            vals = [d["val"] for d in top]
            print(f"   {('today' if key=='score' else 'new M2'):6s} top {len(top):4d} (x{mult}) | total {sum(vals):+.3f} SOL | per buy {sum(vals)/len(vals):+.4f} | winners {sum(1 for x in vals if x > 0)} | reverts {sum(1 for x in vals if x == -0.0005)}")
