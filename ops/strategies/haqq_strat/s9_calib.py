#!/usr/bin/env python3
"""HAQQ_STRAT step 9 (read-only): calibrate the s7 replay against OUR real regular-dip fills in the window.
For each live regular fire that filled (AMS r24-r31, FRA r25): realized = our wallet's SOL change over all our txs on that mint from
the dump slot to +60 slots (buy, sell, failed copies; chain 'sd'), scaled to 0.40 SOL. Replay = the s7 method with OUR rows removed from
the tape, landing at our MEASURED chain-clock ms after the dump, guard ignored (it filled), exit = timer 5 (our live rule), NOW costs.
Gap = realized - replay per fill = the calibration. MEASURED."""
import json, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
from hs_lib import D, W0, W1
TAB = "/home/moiz/sniper-data/haqq_model/tab"
FEE = 0.0125; SMS = 212.0
OURS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")


def main():
    h2h = pickle.load(open(f"{D}/h2h.pkl", "rb"))
    ev = [e for e in h2h if e["kind"] == "regular" and e["fill"] and W0 <= e["t"] < W1]
    ours = collections.defaultdict(list)
    for l in open(f"{TAB}/ours.jsonl"):
        d = json.loads(l)
        if d["signers"][0] not in OURS or not d["mints"]: continue
        ours[d["mints"][0]].append((d["s"], sum(v for a, v in d["sd"] if a == d["signers"][0]) / 1e9, d["fee"] / 1e9, sum(v for a, v in d.get("tips") or []) / 1e9))
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
    S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min())
    bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.float64); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1; bsz[bsz <= 0] = 400
    mids = np.array(sorted({idm[e["mint"]] for e in ev}), np.uint32)
    TT = T[np.isin(T["mint"], mids)]
    TT = TT[~np.isin(TT["user"], [idm[w] for w in OURS])]
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st_ = np.unique(TT["mint"], return_index=True); en_ = np.append(st_[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    rows = []
    for e in ev:
        a, b_ = span[e["mint"]]
        sl = TT["slot"][a:b_].astype(np.int64); ix = TT["idx"][a:b_].astype(np.int64); vs = TT["vsol"][a:b_] / 1e9; vt = TT["vtok"][a:b_].astype(np.float64)
        cc = sl * SMS + ix / np.maximum(bsz[np.clip(sl - s0, 0, len(bsz) - 1)], ix + 1.0) * SMS
        dcc = e["ds"] * SMS + e["di"] / max(bsz[e["ds"] - s0], e["di"] + 1.0) * SMS
        r = int(np.searchsorted(cc, dcc + e["u_ms"], side="right"))
        if r < 1 or r >= len(sl): continue
        v0 = vs[r - 1]; t0 = vt[r - 1]; K = v0 * t0; size = 0.4; Sn = size / (1 + FEE); v1 = v0 + Sn; tok = t0 - K / v1
        es = int((dcc + e["u_ms"]) // SMS)
        q = int(np.searchsorted(sl, es + 5, side="right")) - 1
        V = v1 + (vs[q] - v0); sim = (V - K / (K / V + tok)) * (1 - FEE) - size
        tx = [x for x in ours[e["mint"]] if e["ds"] <= x[0] <= e["ds"] + 60]
        real = sum(x[1] for x in tx); fees = sum(x[2] + x[3] for x in tx)
        rows.append((sim, real * 0.4 / 0.55, fees, (real + fees) * 0.4 / 0.55))
    A = np.array(rows)
    P = []
    P.append(f"# Replay calibration on our {len(A)} real regular fills in the last 24 h (0.40 SOL scale)")
    P.append(f"- replay gross (timer 5, our landing): mean {1000 * A[:, 0].mean():+.2f} mSOL/fill, total {A[:, 0].sum():+.3f}")
    P.append(f"- realized gross (wallet change + fees/tips): mean {1000 * A[:, 3].mean():+.2f} mSOL/fill, total {A[:, 3].sum():+.3f}")
    P.append(f"- realized net: mean {1000 * A[:, 1].mean():+.2f} mSOL/fill; our tx costs {1000 * A[:, 2].mean():.2f} mSOL/fill (incl. failed copies)")
    g = A[:, 3] - A[:, 0]
    rng = np.random.default_rng(5); bs = [g[rng.integers(0, len(g), len(g))].mean() for _ in range(2000)]
    P.append(f"- gap realized - replay (gross): {1000 * g.mean():+.2f} mSOL/fill [5-95%: {1000 * np.percentile(bs, 5):+.2f} .. {1000 * np.percentile(bs, 95):+.2f}]")
    print("\n".join(P)); open(f"{D}/s9.txt", "w").write("\n".join(P) + "\n")


if __name__ == "__main__":
    main()
