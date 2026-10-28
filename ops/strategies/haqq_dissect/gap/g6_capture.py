#!/usr/bin/env python3
"""GAP step 6 (read-only): what OUR current trade style would have made on HIS events, per ledger bucket (first capture estimate).
His events = (mint, dump slot, dump idx) of his lots that follow a single-sell drop >= 5 % within 2 slots (DIP, ADD-on-dump, and the
same dumps in e/f/a/c buckets). Joined to the DV8 candidate universe (dv8/uni.npz: every outside sell >= 0.5 SOL with drop >= 5 %,
curve > 30.5, age <= 30 min, mayhem excluded, usable hours) whose replay is VALIDATED (exact curve, contention-aware landing,
+5 % guard, 0.40 SOL, timer exit 5/8/12 slots): per event the mean over the 4 rank-landing draws of fill x exact P&L.
Calibrated (live ~= 0.61 x model - 1.17 mSOL/fire, c2), minus costs per fire: NOW 1.75+1.77 mSOL per fill, 0.53 per failed fire;
CHEAP (haqq's recipe) 0.33+0.33 / 0.04. One buy per event (we never add). Everything here is INFERRED (replay), his net is MEASURED.
Also: our engine hours per day (union of trading runs) and our MEASURED P&L per engine hour -> run-gap capture at our own rate.
Out: gap/g6_capture.txt, gap/g6.json"""
import pickle, collections, json, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from g1_walkforward import calib_boot, COST
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/gap")
from g3_ledger import grp
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"


def main():
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]; eps = Z["eps"]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]; FILL = U["FILL"]; PN = U["PN"]; names = list(U["names"]); HS = list(U["HS"])
    may = np.load(f"{L.D}/mayhem.npy")
    rk = [i for i, n in enumerate(names) if n.startswith("rank")]; ideal = names.index("ideal")
    ids, idm = L.ids_map()
    key = {(int(m), int(s), int(i)): k for k, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    (A, B), _ = calib_boot()
    # expected per-attempt values per candidate and exit
    EV = {}
    for hi, H in enumerate(HS[:3]):
        v = np.where(FILL[:, rk], PN[:, rk, hi, 0], 0.0); v = np.where(np.isfinite(v), v, 0.0)
        EV[H] = v.mean(1)
    FR = FILL[:, rk].mean(1)
    IDV = {H: np.where(FILL[:, ideal] & np.isfinite(PN[:, ideal, hi, 0]), PN[:, ideal, hi, 0], 0.0) for hi, H in enumerate(HS[:3])}
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    # events per bucket
    def bucket_of(r):
        if r["bucket"] == "c": return "c. " + grp(r["reason"])
        if r["bucket"] == "b": return "b. " + r["reason"]
        return {"a": "a. run gaps", "e": "e. guard failures", "f": "f. both filled", "NOCOV": "NOCOV"}[r["bucket"]]
    ev = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        b = r["b"]
        if b.get("d_slot") is None or b["d_slots"] > 2 or b["d_drop"] < 0.05 or r["type"] == "PROBE": continue
        ev[(r["day"], bucket_of(r))][(idm.get(b["mint"]), b["d_slot"], b["d_i"])].append(r)
    J = {}
    P("# Our current style (+5 % guard, 0.40 SOL, timer exit, one buy) replayed on HIS dump events, per bucket and day (INFERRED replay)")
    P("# his net = his lots on those events (MEASURED). matched = events found in the DV8 candidate universe (mayhem/unusable excluded).")
    P("| day | bucket | events | matched | his lots | his net (matched) | fill % (ours) | ideal 5-slot | ours 5 / 8 / 12 slots raw | ours calibrated NOW (best exit) | ours calibrated CHEAP |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for (d, bk) in sorted(ev):
        E = ev[(d, bk)]; ks = [key.get(k) for k in E]
        m = [(k, v) for k, v in zip(ks, E.values()) if k is not None and not may[k]]
        if not m: continue
        ix = np.array([k for k, _ in m]); hn = sum(r["net"] for _, v in m for r in v); nl = sum(len(v) for _, v in m)
        fr = FR[ix].mean()
        raw = {H: EV[H][ix].sum() for H in (5, 8, 12)}
        bestH = max(raw, key=raw.get)
        n = len(ix); nf = FR[ix].sum()
        def cal(H, cost):
            cb, cs, cf = COST[cost]
            return A * raw[H] + B * n - nf * (cb + cs) - (n - nf) * cf
        J[f"{d}|{bk}"] = dict(events=len(E), matched=n, his=hn, lots=nl, fill=fr, raw=raw, calNOW={H: cal(H, "NOW") for H in raw}, calCHEAP={H: cal(H, "CHEAP") for H in raw},
                              ideal5=float(IDV[5][ix].sum()))
        P(f"| {d} | {bk} | {len(E)} | {n} | {nl} | {hn:+.2f} | {100 * fr:.0f} | {IDV[5][ix].sum():+.2f} | {raw[5]:+.2f} / {raw[8]:+.2f} / {raw[12]:+.2f} | "
          f"{cal(bestH, 'NOW'):+.2f} ({bestH}) | {cal(bestH, 'CHEAP'):+.2f} |")
    # engine hours per day and our measured P&L per engine hour
    RUNS = pickle.load(open(f"{OUT}/g2_engine.pkl", "rb"))
    iv = sorted((X["start"], X["end"]) for X in RUNS.values() if X["start"] and not X["probe_run"])
    P("\n# Engine hours per day (union of trading runs, either server; MEASURED) and our P&L per engine hour (MEASURED wallet)")
    P("| day | engine hours (any) | FRA h | AMS h | our P&L | per engine hour | gap hours | our rate x gap hours (INFERRED) |"); P("|---|---|---|---|---|---|---|---|")
    ours = collections.defaultdict(float)
    for E in eps: ours[E["day"]] += E["pnl"]
    for d in range(2, 7):
        a0 = L.DAY0 + d * 86400; a1 = a0 + 86400
        if d == 6: a1 = 1793132227
        def hours(srv=None):
            sel = sorted((X["start"], X["end"]) for X in RUNS.values() if X["start"] and not X["probe_run"] and (srv is None or X["srv"] == srv))
            tot = 0.0; cur = None
            for s, e in sel:
                s, e = max(s, a0), min(e, a1)
                if e <= s: continue
                if cur and s <= cur[1]: cur[1] = max(cur[1], e)
                else:
                    if cur: tot += cur[1] - cur[0]
                    cur = [s, e]
            if cur: tot += cur[1] - cur[0]
            return tot / 3600
        h = hours(); span = (a1 - a0) / 3600
        rate = ours[d] / h if h else float("nan")
        J[f"hours|{d}"] = dict(h=h, fra=hours("FRA"), ams=hours("AMS"), ours=ours[d], rate=rate, gap=span - h)
        P(f"| {L.day_name(d)} | {h:.1f} | {hours('FRA'):.1f} | {hours('AMS'):.1f} | {ours[d]:+.3f} | {rate:+.3f} | {span - h:.1f} | {rate * (span - h):+.2f} |")
    open(f"{OUT}/g6_capture.txt", "w").write("\n".join(out) + "\n")
    json.dump(J, open(f"{OUT}/g6.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
