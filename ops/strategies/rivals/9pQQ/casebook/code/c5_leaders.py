#!/usr/bin/env python3
"""CASEBOOK: slot -> leader map (public RPC getLeaderSchedule, epochs 1070-1076) and a first scale check:
does 9pQQ's buy rate per slot depend on the slot leader? (buys per leader-slot, run 10-28/10-30/10-31; 11-02 untouched)"""
import json, collections, sys, numpy as np, math
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
def load():
    names, arr = {}, {}
    for e in range(1070, 1077):
        r = json.load(open(f"{D}/leaders/ls_{e}.json"))["result"]
        a = np.full(432000, -1, np.int32)
        for v, idx in r.items():
            k = names.setdefault(v, len(names)); a[np.array(idx)] = k
        arr[e] = a
    return names, arr
if __name__ == "__main__":
    names, arr = load(); inv = {v: k for k, v in names.items()}
    np.save(f"{D}/leaders/names.npy", np.array([inv[k] for k in range(len(inv))]))
    np.save(f"{D}/leaders/slot_leader.npy", np.concatenate([arr[e] for e in range(1070, 1077)]))  # index = slot - 1070*432000
    base = 1070 * 432000
    allL = np.concatenate([arr[e] for e in range(1070, 1077)])
    for run in ["run_20261028_1405", "run_20261030_1355", "run_20261031_1350"]:
        rows = [json.loads(l) for l in open(f"{D}/own_{run}.jsonl")]
        land = [r for r in rows if r["kind"] == "buy"]
        s0 = min(r["s"] for r in rows); s1 = max(r["s"] for r in rows)
        Ls = allL[s0 - base:s1 - base + 1]
        nslot = collections.Counter(Ls.tolist())
        cb = collections.Counter(int(allL[r["s"] - base]) for r in land if not r["err"])
        cs = collections.Counter(int(allL[r["s"] - base]) for r in rows if r["kind"] == "sell" and not r["err"])
        tot_b = sum(cb.values()); tot_s = sum(cs.values()); S = s1 - s0 + 1
        rb = tot_b / S; rs = tot_s / S
        big = [k for k, n in nslot.items() if n >= 400]
        ratios = sorted(((cb[k] / nslot[k]) / rb, (cs[k] / nslot[k]) / rs, nslot[k], cb[k], k) for k in big)
        # chi-square overdispersion vs Poisson for buys and sells
        chib = sum((cb[k] - rb * nslot[k]) ** 2 / (rb * nslot[k]) for k in big); chis = sum((cs[k] - rs * nslot[k]) ** 2 / (rs * nslot[k]) for k in big)
        print(run, "slots", S, "leaders(>=400 slots)", len(big), "buys", tot_b, "sells", tot_s, f"chi2/df buys {chib/len(big):.2f} sells {chis/len(big):.2f}")
        print("  lowest buy-ratio leaders:", [(round(a, 2), round(b, 2), n, c, inv[k][:6]) for a, b, n, c, k in ratios[:6]])
        print("  highest:", [(round(a, 2), round(b, 2), n, c, inv[k][:6]) for a, b, n, c, k in ratios[-6:]])
        # slot-in-leader-window position (0..3)
        pos_b = collections.Counter((r["s"] % 4) for r in land if not r["err"]); pos_s = collections.Counter((r["s"] % 4) for r in rows if r["kind"] == "sell" and not r["err"])
        print("  buy slot%4:", dict(sorted(pos_b.items())), " sell slot%4:", dict(sorted(pos_s.items())))
