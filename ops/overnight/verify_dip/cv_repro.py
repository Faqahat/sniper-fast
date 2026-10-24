#!/usr/bin/env python3
"""verify_dip / cv_repro: reproduce the claim's block CV (dip/dipcv.py logic, same seeds) on a frozen snapshot of its
event file, and dump which events each block's model selected (top 5%), with scores. Uses gb.py = a byte copy of
dip/gbdt_np.py so the trees and RNG draws are identical. Does not import anything from dip/ or core/.
usage: python3 -I -B cv_repro.py <events.jsonl.gz> <LATS e.g. 20,35> <EXIT> <out.json> [K]
env: NOSNP=1 drops the snp_seller feature (leakage test); WALK=1 = walk-forward (train only on earlier blocks)."""
import sys, os, json, gzip, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gb as G
EVF, LATS, EXIT, OUT = sys.argv[1], sys.argv[2].split(","), sys.argv[3], sys.argv[4]
K = int(sys.argv[5]) if len(sys.argv) > 5 else 6
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
W = json.load(open(os.path.join(HERE, "snap", "gf_wallets.json")))
SN8 = {u[:8] for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
XF = ["s_frac", "s_pnl", "s_nb", "s_entry", "s_in_bundle", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3",
      "sellers20", "uniq_buyers", "ins_sold", "net_flow"]
FK = ["age", "sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "pro_seller",
      "snp_seller", "sell_share", "bs_ratio"] + XF
if os.environ.get("NOSNP") == "1": FK = [k for k in FK if k != "snp_seller"]
def fv(r):
    d = dict(r); d["first_big"] = float(r["first_big"]); d["ins"] = float(r["ins"]); d["pro_seller"] = float(r["seller"].startswith(PRO6))
    d["snp_seller"] = float(r["seller"] in SN8)
    d["sell_share"] = r["sell"] / max(r["vsol"] - 30, 0.1); d["bs_ratio"] = r["b20"] / (r["s20"] + 0.1); d.update(r.get("xf", {}))
    return [float(d[k]) for k in FK]
def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
if __name__ == "__main__":
    R = [json.loads(l) for l in gzip.open(EVF, "rt")]
    R.sort(key=lambda r: r["bt"] + r["age"])
    out = {}
    for LAT in LATS:
        rows = [r for r in R if LAT in r["pnl"] and EXIT in r["pnl"][LAT]]
        X = np.array([fv(r) for r in rows]); P = np.array([r["pnl"][LAT][EXIT] for r in rows]); y = (P > 0).astype(float)
        n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(int(os.environ.get('SEED', '1')))
        print(f"\nLAT {LAT} exit {EXIT}: {n} events, {K} blocks", flush=True)
        tot = 0.0; sel = []; blocks = []
        for b in range(K):
            if os.environ.get("WALK") == "1":
                trall = blk < b
                if b == 0: rng.random(n); continue
            else:
                trall = blk != b
            va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
            Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3, seed=int(os.environ.get('SEED2', '0')))
            thr = np.quantile(f[va], float(os.environ.get("QT", "0.95"))); st = te & (f >= thr)
            i0, i1 = np.where(te)[0][0], np.where(te)[0][-1]
            tot += P[st].sum()
            blocks.append(dict(b=b, t0=pkt(rows[i0]["bt"] + rows[i0]["age"]), t1=pkt(rows[i1]["bt"] + rows[i1]["age"]),
                               t0u=rows[i0]["bt"] + rows[i0]["age"], t1u=rows[i1]["bt"] + rows[i1]["age"],
                               n=int(st.sum()), total=float(P[st].sum()), auc=G.auc(y[te], f[te]), thr=float(thr), ntrees=len(trees)))
            print(f"  block {b} ({blocks[-1]['t0']} -> {blocks[-1]['t1']} PKT): AUC {blocks[-1]['auc']:.3f} | top5% n {st.sum():4d} "
                  f"mean {P[st].mean() if st.sum() else 0:+.4f} total {P[st].sum():+6.2f} win {(P[st] > 0).mean() if st.sum() else 0:.0%}", flush=True)
            for q in np.where(st)[0]:
                r = rows[q]
                sel.append(dict(m=r["m"], age=r["age"], run=r["run"], bt=r["bt"], b=b, f=float(f[q]), thr=float(thr), pnl=float(P[q]),
                                sell=r["sell"], vsol=r["vsol"], seller=r["seller"]))
        print(f"  all blocks total {tot:+.2f}  trades {len(sel)}", flush=True)
        out[LAT] = dict(blocks=blocks, sel=sel, total=tot, n_events=n)
    json.dump(out, open(OUT, "w"))
