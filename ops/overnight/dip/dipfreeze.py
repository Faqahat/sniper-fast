#!/usr/bin/env python3
# Freeze the dip-buy selection model for a FORWARD test. Train on every dip event up to the freeze time (first 85% by time =
# train, last 15% = early stop + thresholds), causal features only, label = PnL > 0 at entry LAT ms after the sell, exit 8 slots.
# Saves bin edges + trees so new events can be scored identically. -> dip/frozen_dip_L<LAT>.json (+ .sha256)
import sys, os, json, gzip, time, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbdt_np as G
LAT = os.environ.get("LAT", "35"); EXIT = "8"
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
W = json.load(open("/home/moiz/sniper/ops/overnight/core/gf_wallets.json"))
SN8 = sorted({u[:8] for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]})
FK = ["age", "sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "pro_seller", "snp_seller", "sell_share", "bs_ratio"]
def fv(r, sn8):
    d = dict(r); d["first_big"] = float(r["first_big"]); d["ins"] = float(r["ins"]); d["pro_seller"] = float(r["seller"].startswith(PRO6)); d["snp_seller"] = float(r["seller"] in sn8)
    d["sell_share"] = r["sell"] / max(r["vsol"] - 30, 0.1); d["bs_ratio"] = r["b20"] / (r["s20"] + 0.1)
    return [float(d[k]) for k in FK]
if __name__ == "__main__":
    R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/dip/events_timed.jsonl.gz", "rt")]
    R = [r for r in R if LAT in r["pnl"]]
    R.sort(key=lambda r: r["bt"] + r["age"])
    freeze = time.time(); last_ev = R[-1]["bt"] + R[-1]["age"]
    sn8 = set(SN8)
    X = np.array([fv(r, sn8) for r in R]); P = np.array([r["pnl"][LAT][EXIT] for r in R]); y = (P > 0).astype(float)
    n = len(R); TR = np.arange(n) < int(n * 0.85); VA = ~TR
    # bin edges from the training part (same as G.binize), kept for scoring new events
    edges = []
    for j in range(X.shape[1]):
        xt = X[TR, j]; xt = xt[~np.isnan(xt)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist())
    Bm = np.zeros(X.shape, np.int16)
    for j in range(X.shape[1]):
        b = np.searchsorted(np.array(edges[j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
    p0 = y[TR].mean(); F0 = float(np.log(p0 / (1 - p0)))
    thr = {q: float(np.quantile(f[VA], 1 - q)) for q in (0.02, 0.05, 0.10)}
    va_stats = {f"{q:.0%}": dict(n=int((VA & (f >= t)).sum()), mean=float(P[VA & (f >= t)].mean())) for q, t in thr.items()}
    out = dict(name=f"FRZ-DIP-L{LAT}", strategy="buy 0.5 SOL right after a >=1 SOL sell on a launch aged 1-120 s if score >= threshold; sell 8 slots later",
               label=f"pnl>0 at entry {LAT} ms after the sell (block-position arrival proxy), exit {EXIT} slots, 0.0008 SOL/tx, no fill penalty",
               features=FK, sn8=SN8, pro6=list(PRO6), edges=edges, trees=trees, F0=F0, lr=0.05, thresholds={f"{q:.0%}": t for q, t in thr.items()},
               val=va_stats, n_train=int(TR.sum()), n_val=int(VA.sum()), last_event_time=last_ev,
               frozen_at=freeze, frozen_at_pkt=time.strftime("%Y-%m-%d %H:%M", time.gmtime(freeze + 18000)) + " PKT")
    fn = f"/home/moiz/sniper/ops/overnight/dip/frozen_dip_L{LAT}.json"
    s = json.dumps(out); open(fn, "w").write(s)
    h = hashlib.sha256(s.encode()).hexdigest(); open(fn + ".sha256", "w").write(h + "\n")
    print(out["name"], "frozen", out["frozen_at_pkt"], "sha256", h[:12], "| trees", len(trees), "| last event", time.strftime("%m-%d %H:%M", time.gmtime(last_ev + 18000)), "PKT | val", va_stats)
