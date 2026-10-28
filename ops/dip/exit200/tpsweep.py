#!/usr/bin/env python3
"""What if the take-profit had been higher (15/20/30/50%/off) with the 200 ms exit? Per fill, on the FRA recorder tape.
Model: exit = the earlier of (a) the first trade in slots <= fill+1 whose value >= (1+TP) x cost, sold at the END of that slot
(a TP sell can't land in the slot it was decided in), and (b) the 200 ms timer = our ACTUAL sell when the live exit was time-ms,
else the end of slot fill+1 with our tokens still in the pool. SL 20% kept (end of its slot). Trades after our real sell are
valued with our tokens put back into the pool. Read-only. usage: tpsweep.py fra 28 | ams 34"""
import json, subprocess, sys, os, random
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); import decode as D
region, RUN = sys.argv[1], sys.argv[2]
ssh = ["ssh", "-p", "1996", "-o", "ConnectTimeout=10"]
if region == "fra":
    recs = open(f"/home/moiz/sniper-data/runs/fra/runs/dip_r{RUN}.jsonl").read().splitlines()
else:
    recs = subprocess.run(ssh + ["it@84.32.104.202", f"sudo grep -E '\"ev\":\"presend_live_(fill|sell_land|realized|exit)\"' /root/prod/runs/dip_ams_r{RUN}.jsonl"], capture_output=True, text=True).stdout.splitlines()
fills, sells, real, exits = {}, {}, {}, {}
for l in recs:
    if '"presend_live_' not in l: continue
    d = json.loads(l)
    if d["ev"] == "presend_live_fill" and not d.get("after_exit"): fills.setdefault(d["mint"], []).append(d)
    elif d["ev"] == "presend_live_sell_land": sells.setdefault(d["mint"], []).append(d)
    elif d["ev"] == "presend_live_realized": real.setdefault(d["mint"], []).append(d)
    elif d["ev"] == "presend_live_exit": exits.setdefault(d["mint"], []).append(d)
for dct in (fills, sells, real, exits):
    for v in dct.values(): v.sort(key=lambda d: (d.get("slot", 0), d.get("idx", 0), d.get("t", 0)))
mints = sorted(m for m in fills if m in sells)
tmp = f"/tmp/tpsweep_{region}{RUN}.txt"; open(tmp, "w").write("\n".join(mints) + "\n")
subprocess.run(["scp", "-q", "-P", "1996", tmp, "it@84.32.100.36:" + tmp])
t0 = min(f["t"] for v in fills.values() for f in v) // 10**9 - 400
cmd = (f"for R in $(sudo sh -c 'ls -d /root/sniper-collect/run_*/txs' | tail -3); do for f in $(sudo ls $R); do t=${{f#txs_}}; t=${{t%.jsonl.gz}}; "
       f"[ \"$t\" -ge {t0} ] 2>/dev/null && sudo sh -c \"zcat $R/$f 2>/dev/null\" | grep -F -f {tmp}; done; done")
lines = subprocess.run(ssh + ["it@84.32.100.36", cmd], capture_output=True, text=True).stdout.splitlines()
tape = {}
for line in lines:
    try: d = json.loads(line)
    except Exception: continue
    if d.get("err") is not None: continue
    for b in D.chunks_of(d.get("ev")):
        if b[:8] != D.DISC: continue
        p = D.parse_trade(b)
        if p and p[0] in fills: tape.setdefault(p[0], {})[(d["s"], d["i"], p[1], p[2])] = dict(s=d["s"], i=d["i"], sol=p[1], tok=p[2], buy=p[3], vsol=p[5], vtok=p[6])
TPS = [0.10, 0.15, 0.20, 0.30, 0.50, None]
tot = {tp: 0.0 for tp in TPS}; n = 0; act_tot = 0.0; diffs = {tp: [] for tp in TPS}
for m in mints:
    for k in range(min(len(fills[m]), len(sells[m]))):
        f = fills[m][k]; s = sells[m][k]
        tr = sorted(tape.get(m, {}).values(), key=lambda x: (x["s"], x["i"]))
        mine = [x for x in tr if x["s"] == s["slot"] and x["i"] == s["idx"]]
        if not tr or not mine: continue
        ms = mine[0]; T = f["tokens"]; cost = f["sol_in"]
        pre = [x for x in tr if (x["s"], x["i"]) < (ms["s"], ms["i"])]
        if not pre: continue
        val = lambda vs, vt: vs * T / (vt + T)
        v_act = val(pre[-1]["vsol"], pre[-1]["vtok"]); sold = s["sol"]
        ex_why = (exits.get(m, [{}] * (k + 1))[k] if len(exits.get(m, [])) > k else {}).get("why", "")
        # path of values after the fill, with our tokens back in after our real sell
        path = []
        for x in tr:
            if (x["s"], x["i"]) <= (f["slot"], f["idx"]) or x is ms: continue
            vs, vt = x["vsol"], x["vtok"]
            if (x["s"], x["i"]) > (ms["s"], ms["i"]): vs, vt = vs + ms["sol"], vt - T
            path.append((x["s"], x["i"], val(vs, vt)))
        if not path: continue
        def end_of_slot(slot):
            v = [p for p in path if p[0] <= slot]
            return v[-1][2] if v else v_act
        timer_v = v_act if ex_why == "time-ms" else end_of_slot(f["slot"] + 1)
        for tp in TPS:
            trig = None; why = "timer"
            for (sl, ix, v) in path:
                if sl > f["slot"] + 1: break
                if tp is not None and v >= (1 + tp) * cost: trig = sl; why = "TP"; break
                if v <= 0.80 * cost: trig = sl; why = "SL"; break
            if trig is not None:
                cf = end_of_slot(trig)
                if why == "TP" and trig == f["slot"] + 1 and ex_why == "time-ms": cf = min(cf, timer_v) if False else cf
            else: cf = timer_v
            cf_sold = sold * cf / v_act
            tot[tp] += (cf_sold - cost) / 1e9; diffs[tp].append((cf_sold - sold) / 1e9)
        act_tot += (sold - cost) / 1e9; n += 1
print(f"{region} r{RUN}: {n} fills priced | actual (TP 10%, 200 ms) curve P&L {act_tot:+.3f} SOL")
random.seed(1)
for tp in TPS:
    dd = diffs[tp]; bs = sorted(sum(random.choice(dd) for _ in dd) for _ in range(1000))
    print(f"  TP {'off' if tp is None else f'{int(tp*100)}%':>4}: {tot[tp]:+.3f} SOL  vs actual {tot[tp]-act_tot:+.3f} [90%: {bs[50]:+.3f}, {bs[949]:+.3f}] | better on {sum(1 for d in dd if d > 1e-6)} / worse on {sum(1 for d in dd if d < -1e-6)}")
