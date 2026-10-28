#!/usr/bin/env python3
"""BOTS step 8 (read-only): EMPIRICAL PROXY, no landing model. On every dump that bot 247 / 248 bought (dv8 universe, usable, non-mayhem),
take every OTHER real wallet (not haqq, not ours) whose first trade on the token after the dump is a BUY landing k outside trades after the
dump (k counted like our rank model: rows not ours, haqq included), within slots dump..dump+2, holding nothing before, and whose next trade
on the token sells >= 95 % of those tokens 1-8 s later (the ~4 s round trip). Realized return per SOL = sell SOL x (1 - fee) /
(buy SOL x (1 + fee)) - 1 (pump fees from the rows, tx costs excluded = curve P&L). MEASURED.
Compared with: the exact replay at our rank-model landing with MS4000 / HIS exits (b4) per SOL, and our measured k on shared dumps.
Out: bots/b8.txt"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import xlib as X
from plib import boot_mean, Out
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
KB = [(0, 0), (1, 1), (2, 3), (4, 7), (8, 12)]


def main():
    P = Out(f"{OUT}/b8.txt")
    Z = pickle.load(open(f"{OUT}/b4_res.pkl", "rb")); meta, res, PL = Z["meta"], Z["res"], [str(p) for p in Z["PL"]]
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]; ours = (MI["who"]["FRA"], MI["who"]["AMS"])
    import dv8lib as L
    ids, idm = L.ids_map()
    ev = {}
    for i, m in meta.items():
        if m["kind"] == "lot" and res.get(i): ev.setdefault((m["mint"], m["dslot"], m["didx"]), []).append(i)
    out = collections.defaultdict(list)       # (code, kbucket) -> list of (ret, day)
    for (mint, ds, di), lots in ev.items():
        mi = idm.get(mint)
        if mi not in span: continue
        a, b = span[mi]; Xr = R[a:b]; cc = CC[a:b]
        sl = Xr["slot"].astype(np.int64); ix = Xr["idx"].astype(np.int64); us = Xr["user"].astype(np.int64); bu = Xr["buy"].astype(bool)
        jd = np.flatnonzero((sl == ds) & (ix == di) & ~bu)
        if not len(jd): continue
        jd = int(jd[0]); nonour = ~np.isin(us, ours)
        codes = set(meta[i]["code"] for i in lots); day = meta[lots[0]]["day"]
        rows_after = np.flatnonzero(nonour & (np.arange(len(sl)) > jd) & (sl <= ds + 2))
        seen = set(us[:jd + 1][nonour[:jd + 1]].tolist())          # wallets that traded before the dump (holding nothing is required)
        fee = (Xr["fee_bps"].astype(np.float64) + Xr["cfee_bps"]) / 1e4; fee = np.where(fee > 0, fee, X.FEE)
        for k, j in enumerate(rows_after.tolist()):
            if k > 12: break
            w = int(us[j])
            if w == H or w in seen: seen.add(w); continue
            seen.add(w)
            if not bu[j]: continue
            nx = np.flatnonzero((us == w) & (np.arange(len(sl)) > j))
            if not len(nx): continue
            n = int(nx[0])
            if bu[n]: continue
            dt = (cc[n] - cc[j]) / 1000
            if not (1.0 <= dt <= 8.0) or Xr["tok"][n] < 0.95 * Xr["tok"][j]: continue
            sold_frac = min(1.0, Xr["tok"][j] / Xr["tok"][n])
            ret = (Xr["sol"][n] / 1e9 * (1 - fee[n]) * sold_frac) / (Xr["sol"][j] / 1e9 * (1 + fee[j])) - 1
            for c in codes:
                for kb in KB:
                    if kb[0] <= k <= kb[1]: out[(c, kb)].append((ret, day, dt))
    P("# Empirical proxy: real wallets' ~4 s round trips (1-8 s) entering k outside trades after the dumps 247 / 248 bought (MEASURED)")
    P("| bot | k ahead | trips | return per SOL mean [90%] | median | win | mean hold s | days with mean > 0 |"); P("|---|---|---|---|---|---|---|---|")
    W = {}
    for c in (247, 248):
        for kb in KB:
            v = out.get((c, kb), [])
            if len(v) < 20: continue
            r = np.array([x[0] for x in v]); d = np.array([x[1] for x in v]); lo, hi = boot_mean(r)
            pdm = [r[d == k].mean() for k in range(7) if (d == k).sum() >= 10]
            W[(c, kb)] = r.mean()
            P(f"| {c} | {kb[0]}-{kb[1]} | {len(r):,} | {100 * r.mean():+.2f}% [{100 * lo:+.2f}..{100 * hi:+.2f}] | {100 * np.median(r):+.2f}% | {100 * np.mean(r > 0):.0f}% | {np.mean([x[2] for x in v]):.1f} | {sum(x > 0 for x in pdm)}/{len(pdm)} |")
    # model comparison: our rank-model landing on the same lots, MS4000 / HIS per SOL; and his own lots per SOL
    P("\n## Same dumps, the exact replay (b4, bot replaced) per SOL, mean over lots: our rank landing with MS4000 / HIS exits; his realized")
    ims = PL.index("('MS', 4000)"); ihis = PL.index("('HIS',)")
    for c in (247, 248):
        ids_ = [i for i, m in meta.items() if m["kind"] == "lot" and m["code"] == c and res.get(i)]
        ms = np.array([np.nanmean([e["pn"][0, ims] for e in res[i][1:]]) / meta[i]["size"] for i in ids_])
        hh = np.array([np.nanmean([e["pn"][0, ihis] for e in res[i][1:]]) / meta[i]["size"] for i in ids_])
        kk = np.array([np.mean([e["k"] for e in res[i][1:]]) for i in ids_])
        his = np.array([meta[i]["gross"] / meta[i]["size"] for i in ids_])
        P(f"- {c}: rank landing MS4000 {100 * np.nanmean(ms):+.2f}%/SOL, HIS exit {100 * np.nanmean(hh):+.2f}%/SOL (mean rank k {kk.mean():.1f}); his own lots {100 * his.mean():+.2f}%/SOL (before his tx costs)")
    P.save()


if __name__ == "__main__":
    main()
