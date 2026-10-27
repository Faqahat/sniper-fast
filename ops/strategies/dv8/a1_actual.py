#!/usr/bin/env python3
"""DV8 step 5 (read-only): what we actually made per day, and haqq's per-day P&L, on the tape days.
Ours (MEASURED): SOL change of each live wallet over all its landed txs that touch a pump.fun mint (buys, sells, failed buys, ATA
closes; fees and tips included), per day window (23:15 PKT), from dv8/tab/ours.jsonl. Split: regular = txs on a regular fire's
mint from the dump slot to +60 slots (l1); pre-send + other = the rest. Open positions at a day boundary are not marked (seconds).
haqq (MEASURED curve flows, INFERRED tx cost): sum over his tape trades of sell SOL x (1 - fee) - buy SOL x (1 + fee) (actual fee
bps); tx cost 0.78 mSOL per buy lot (haqq_strat s3) subtracted as INFERRED.
Out: dv8/a1.txt, dv8/a1.json"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    F = pickle.load(open(f"{L.D}/live_fires.pkl", "rb"))
    reg = collections.defaultdict(list)
    for f in F:
        if f["ds"] is not None: reg[(L.WAL[f["srv"]], f["mint"])].append(f["ds"])
    tot = collections.defaultdict(float); rg = collections.defaultdict(float); ntx = collections.Counter()
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l); w = d["signers"][0]
        if w not in L.WAL.values() or not d["mints"]: continue
        sd = d["sd"]; sd = json.loads(sd.replace("'", '"')) if isinstance(sd, str) else sd
        v = sum(x for a, x in sd if a == w) / 1e9
        k = (L.day_of(d["bt"]), "FRA" if w == L.WAL["FRA"] else "AMS")
        tot[k] += v; ntx[k] += 1
        if any(ds <= d["s"] <= ds + 60 for ds in reg.get((w, d["mints"][0]), [])): rg[k] += v
    # haqq
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    ids, idm = L.ids_map(); h = idm[L.HAQQ]
    H = np.asarray(T[np.asarray(T["user"]) == h])
    fr = (H["fee_bps"].astype(float) + H["cfee_bps"].astype(float)) / 1e4
    flow = np.where(H["buy"] == 1, -(H["sol"] / 1e9) * (1 + fr), (H["sol"] / 1e9) * (1 - fr))
    hd = ((H["bt"].astype(np.int64) - L.DAY0) // 86400).astype(int)
    days = sorted(set(k[0] for k in tot) | set(hd.tolist()))
    J = {}
    P("# What we actually made per day (MEASURED wallet SOL change, fees/tips included) and haqq's per-day P&L")
    P("| day | FRA regular | FRA pre-send+other | AMS regular | AMS pre-send+other | ours total | haqq buys | haqq curve P&L | haqq net (- 0.78 mSOL/lot, INFERRED) |")
    P("|---|---|---|---|---|---|---|---|---|")
    for k in days:
        fr_r = rg[(k, "FRA")]; fr_o = tot[(k, "FRA")] - fr_r; am_r = rg[(k, "AMS")]; am_o = tot[(k, "AMS")] - am_r
        m = hd == k; nb = int((H["buy"][m] == 1).sum()); hc = float(flow[m].sum())
        J[k] = dict(fra_reg=fr_r, fra_other=fr_o, ams_reg=am_r, ams_other=am_o, ours=fr_r + fr_o + am_r + am_o, haqq_buys=nb, haqq_curve=hc, haqq_net=hc - 0.00078 * nb)
        P(f"| {L.day_name(k)} | {fr_r:+.3f} | {fr_o:+.3f} | {am_r:+.3f} | {am_o:+.3f} | {J[k]['ours']:+.3f} | {nb:,} | {hc:+.2f} | {J[k]['haqq_net']:+.2f} |")
    json.dump(J, open(f"{L.D}/a1.json", "w"), indent=1)
    open(f"{L.D}/a1.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
