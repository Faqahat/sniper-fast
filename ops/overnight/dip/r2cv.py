#!/usr/bin/env python3
# Block cross-validation of the dip model: events sorted by time, K contiguous blocks; for each block, train on the others
# (early stop + top-5% threshold from a held-out 15% of the training events, chosen at random), test on the block.
# Labels: follower slippage imputed (events_timed3_slip). Features: base + richer (XF).
import sys, os, json, gzip, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbdt_np as G
os.environ.setdefault("XF", "1")
EVF = os.environ.get("EVF", "/home/moiz/sniper/ops/overnight/dip/events_timed3_slip.jsonl.gz"); K = int(os.environ.get("K", "6")); EXIT = os.environ.get("EXIT", "8")
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
W = json.load(open("/home/moiz/sniper/ops/overnight/core/gf_wallets.json"))
SN8 = {u[:8] for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
XF = ["s_frac", "s_pnl", "s_nb", "s_entry", "s_in_bundle", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow"]
FK = ["age", "sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "pro_seller", "snp_seller", "sell_share", "bs_ratio"] + XF
def fv(r):
    d = dict(r); d["first_big"] = float(r["first_big"]); d["ins"] = float(r["ins"]); d["pro_seller"] = float(r["seller"].startswith(PRO6)); d["snp_seller"] = float(r["seller"] in SN8)
    d["sell_share"] = r["sell"] / max(r["vsol"] - 30, 0.1); d["bs_ratio"] = r["b20"] / (r["s20"] + 0.1); d.update(r.get("xf", {}))
    return [float(d[k]) for k in FK]
if __name__ == "__main__":
    R = [json.loads(l) for l in gzip.open(EVF, "rt")]
    R = [r for r in R if r["run"] in os.environ.get("RUNS", "R1,R2").split(",")]
    R.sort(key=lambda r: r["bt"] + r["age"])
    for LAT in os.environ.get("LATS", "20,35,50").split(","):
        rows = [r for r in R if LAT in r["pnl"] and EXIT in r["pnl"][LAT]]
        X = np.array([fv(r) for r in rows]); P = np.array([r["pnl"][LAT][EXIT] for r in rows]); y = (P > 0).astype(float)
        n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(1)
        print(f"\nLAT {LAT} ms exit {EXIT}: {n} events, {K} time blocks")
        tot = 0.0; gt = {}; tot2 = 0.0
        P2 = None
        if os.environ.get("EVF2"):
            E2 = {}
            for l2 in gzip.open(os.environ["EVF2"], "rt"):
                r2 = json.loads(l2); E2[(r2["m"], r2["age"])] = r2["pnl"].get(LAT, {}).get(EXIT)
            P2 = np.array([E2.get((r["m"], r["age"])) if E2.get((r["m"], r["age"])) is not None else np.nan for r in rows])
        for b in range(K):
            trall = blk != b; va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
            Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3)
            thr = np.quantile(f[va], 1 - float(os.environ.get("Q", "0.05"))); st = te & (f >= thr)
            t0 = time.strftime("%m-%d %H:%M", time.gmtime(rows[np.where(te)[0][0]]["bt"] + rows[np.where(te)[0][0]]["age"] + 18000))
            t1 = time.strftime("%m-%d %H:%M", time.gmtime(rows[np.where(te)[0][-1]]["bt"] + rows[np.where(te)[0][-1]]["age"] + 18000))
            tot += P[st].sum()
            if P2 is not None:
                v2 = P2[st]; v2 = v2[~np.isnan(v2)]; tot2 += v2.sum()
                print(f"      same trades, variant file: n {len(v2)} total {v2.sum():+6.2f} mean {v2.mean() if len(v2) else 0:+.4f}")
            print(f"  block {b} ({t0} -> {t1} PKT): AUC {G.auc(y[te], f[te]):.3f} | top5% n {st.sum():4d} mean {P[st].mean() if st.sum() else 0:+.4f} total {P[st].sum():+6.2f} win {(P[st] > 0).mean() if st.sum() else 0:.0%}")
            for gd in ([float(x) for x in os.environ["GUARDS"].split(",")] if os.environ.get("GUARDS") else []):
                px = np.array([rows[q].get("px", {}).get(LAT, 1.0) for q in range(n)])
                ok = st & (px <= gd); fail = st & (px > gd)
                gt[gd] = gt.get(gd, 0.0) + P[ok].sum() - 0.0002 * fail.sum()
                print(f"      guard <= {gd}: buys {ok.sum():4d} (failed guarded {fail.sum():4d}) total {P[ok].sum() - 0.0002 * fail.sum():+6.2f} mean/buy {P[ok].mean() if ok.sum() else 0:+.4f}")
        print(f"  all blocks total {tot:+.2f}" + "".join(f" | guard {gd}: {v:+.2f}" for gd, v in gt.items()) + (f" | variant file total {tot2:+.2f}" if P2 is not None else ""))
