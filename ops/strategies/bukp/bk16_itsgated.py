#!/usr/bin/env python3
# ITS strategy + GRADUATION GATE (read-only): BUkpShoE's entries re-timed to 35 ms (0.6 SOL, its trades removed: we take its
# place), kept only when the graduation-model score at its trigger (bk12, N = 5 or 10 min; cached by bk15) is above the
# R2 top-q cut; exits: its own exit, hold to graduation / 300 s, timer 120 s, trailing 20% + 300 s, ladder. R3 and R1 are
# out-of-sample for the model (R2 is in-sample and only shown for reference). -> bukp/its_gated.json
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import bk8_replica as B8
import bk13_exits as B13
import bk12_grad as B12
OUT = "/home/moiz/sniper-data/strategies/bukp"
EXN = ["to_grad_300s", "timer_120s", "ts_sell20_300s_mh15", "ts_sell10_120s_mh15", "ladder_1.2_1.5_300s"]
FAM = {F["name"]: F for F in B13.FAMS}
if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    thr = json.load(open(f"{OUT}/grad_gate_thr.json"))
    out = {}
    for run in days:
        d = E.DAYS[run]; d["run"] = run
        T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
        sc = {}
        for N in (5, 10):
            z = np.load(f"{OUT}/grad_scores_{run}_N{N}.npz"); sc[N] = dict(zip(z["idx"].tolist(), z["s"].tolist()))
        rows = []
        for t in T:
            j = t["k0"] - 1
            while j >= 0 and d["uid"][j] == B8.UID: j -= 1
            e = B8.entry(d, t, 35, "0.6")
            if e is None: continue
            rec = dict(grad=t["grad"], s5=sc[5].get(j), s10=sc[10].get(j))
            if e["fail"]: rec.update({k: e["pnl"] for k in ["own"] + EXN}); rows.append(rec); continue
            if not e["path"]: continue
            ks = t["sells"][-1]["k"]; nn = 0
            for n, m in enumerate(e["path"]):
                if m < ks: nn = n
                else: break
            rec["own"] = B13.proceeds(e, nn) - e["B"] - B8.FIX
            for x in EXN: rec[x] = B13.run_family(d, e, FAM[x])[0]
            rows.append(rec)
        for N in (5, 10):
            for q in (None, 0.01, 0.003, 0.001):
                cut = thr[f"N{N}_q{q}"] if q else -1e9
                sel = [r for r in rows if r[f"s{N}"] is not None and r[f"s{N}"] >= cut]
                key = f"{run}|N{N}|q{q}"
                out[key] = dict(n=len(sel), grad_share=round(float(np.mean([r["grad"] for r in sel])), 3) if sel else None,
                                **{x: round(sum(r[x] for r in sel), 2) for x in ["own"] + EXN})
    json.dump(out, open(f"{OUT}/its_gated.json", "w"), indent=1)
    for N in (5, 10):
        for q in (None, 0.01, 0.003, 0.001):
            print(f"N{N} gate top {q if q else 'none (all its entries)'}:")
            for run in days:
                o = out[f"{run}|N{N}|q{q}"]
                print(f"   {run}{' (in-sample)' if run == 'R2' else ''}: n {o['n']} graduating {o['grad_share']} | own exit {o['own']:+.2f} | " + " | ".join(f"{x} {o[x]:+.2f}" for x in EXN))
