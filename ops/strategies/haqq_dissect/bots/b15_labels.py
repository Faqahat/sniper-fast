#!/usr/bin/env python3
"""BOTS step 15 (read-only): export the imitation labels for a hand audit. One JSON line per sell in the trigger envelope:
 - broad envelope (b2b/b11): outside sells on non-mayhem tokens <= 300 s old that are a >= 5 % single sell, a dev sell, a creation-slot /
   early holder (>= 1 % of supply) sell or any >= 2 % holder sell - all sizes, all hours (usable flag given);
 - plus every dv8-universe dump (>= 5 % drop, >= 0.5 SOL, curve > 30.5, age <= 30 min, non-mayhem) not already in it.
Fields: mint, slot, idx, seller, seller_type, drop / dd10 %, sell SOL, seller balance before (% supply), chunk count (10 slots), curve SOL after,
age, bought247 / bought248 (MEASURED: that bot bought within 0..2 slots after the sell), broad-model scores (b11, walk-forward OOS, D1-D6),
dv8-universe TAPE-model scores (b3, walk-forward OOS) where the sell is a dv8 candidate. Out: bots/labels.jsonl.gz"""
import sys, json, gzip
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
ST = ("dev", "creation_slot_buyer", "early_buyer", "other")


def main():
    ids, idm = L.ids_map()
    ld = lambda p, keys=None: (lambda z: {k: z[k] for k in (keys or z.files)})(np.load(p))     # materialise npz arrays once (lazy NpzFile re-reads per access)
    Z = ld(f"{OUT}/b2b.npz"); B = ld(f"{OUT}/b11.npz"); S3 = ld(f"{OUT}/b3_scores.npz"); Y = ld(f"{OUT}/b2.npz", ["Y247", "Y248"])
    U = ld(f"{L.D}/uni.npz", ["M", "X"]); M = U["M"]
    may = np.load(f"{L.D}/mayhem.npy")
    st = Z["stype"]; d = Z["drop"]; h = Z["hold"]
    envall = (d >= 0.05) | (st == 0) | (np.isin(st, (1, 2)) & (h >= 1)) | (h >= 2)
    ukey = {(int(m), int(s), int(i)): k for k, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    sg = lambda x: None if not np.isfinite(x) else round(float(1 / (1 + np.exp(-x))), 5)
    seen = set(); n = 0
    with gzip.open(f"{OUT}/labels.jsonl.gz", "wt") as f:
        for r in np.flatnonzero(envall).tolist():
            m, s, i = int(Z["mint"][r]), int(Z["slot"][r]), int(Z["idx"][r])
            u = ukey.get((m, s, i)); seen.add(u)
            rec = dict(mint=ids[m], slot=s, idx=i, seller=ids[int(Z["user"][r])], seller_type=ST[int(st[r])], drop_pct=round(100 * float(d[r]), 2),
                       dd10_pct=round(100 * float(Z["dd10"][r]), 2), sell_sol=round(float(Z["sol"][r]), 4), seller_hold_pct=round(float(h[r]), 3),
                       chunks10=int(Z["ch10"][r]), curve_sol_after=round(float(Z["vpost"][r]), 3), age_s=round(float(Z["age"][r]), 1), time_pkt=L.pkt(int(Z["bt"][r])),
                       usable_hour=bool(Z["usable"][r]), bought247=bool(Z["Y247"][r]), bought248=bool(Z["Y248"][r]),
                       score247_broad=sg(B["S247"][r]) if np.isfinite(B["S247"][r]) else None, score248_broad=sg(B["S248"][r]) if np.isfinite(B["S248"][r]) else None,
                       in_dv8_universe=u is not None,
                       score247_dv8=(sg(S3["247_TAPE"][u]) if u is not None and np.isfinite(S3["247_TAPE"][u]) else None),
                       score248_dv8=(sg(S3["248_TAPE"][u]) if u is not None and np.isfinite(S3["248_TAPE"][u]) else None))
            f.write(json.dumps(rec) + "\n"); n += 1
        # dv8-universe candidates not in the broad envelope (older tokens / other)
        hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
        for u in range(len(M)):
            if u in seen or may[u]: continue
            hs = (int(M["bt"][u]) + 18000) // 3600 * 3600 - 18000
            rec = dict(mint=ids[int(M["mint"][u])], slot=int(M["slot"][u]), idx=int(M["idx"][u]), seller=None, seller_type=None,
                       drop_pct=round(100 * float(U["X"][u, 0]), 2), sell_sol=round(float(U["X"][u, 1]), 4), curve_sol_after=round(float(U["X"][u, 3]), 3),
                       age_s=round(float(U["X"][u, 4]), 1), time_pkt=L.pkt(int(M["bt"][u])), usable_hour=hs in good, bought247=bool(Y["Y247"][u]), bought248=bool(Y["Y248"][u]),
                       in_dv8_universe=True, score247_dv8=sg(S3["247_TAPE"][u]), score248_dv8=sg(S3["248_TAPE"][u]))
            f.write(json.dumps(rec) + "\n"); n += 1
    print(n, "label rows")


if __name__ == "__main__":
    main()
