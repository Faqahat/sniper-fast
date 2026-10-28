#!/usr/bin/env python3
"""BOTS step 16 (read-only): on the shared dumps (our live regular fire + the bot's lot on the same dump): OUR REAL landed position
(MEASURED) with the BOT'S OWN exit (his code-matched sell times / fractions) and with our exits, bot replaced (his lot removed); vs his own
position with his exit. Isolates entry from exit. Exact replay (b4 machinery), 0.40 SOL for both. Out: bots/b16.txt"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/bots")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
import b4_replay as B4
from plib import boot_mean, Out
import dv8lib as L


def main():
    P = Out(f"{B4.OUT}/b16.txt")
    Z = pickle.load(open(f"{B4.OUT}/b4_res.pkl", "rb")); meta = Z["meta"]; PL = [str(p) for p in B4.PL]
    F = pickle.load(open("/home/moiz/sniper-data/dv8/fires_tape.pkl", "rb"))
    rows = pickle.load(open(f"{B4.OUT}/b1.pkl", "rb")); byli = {r["li"]: r for r in rows}
    lots = collections.defaultdict(list)
    for i, m in meta.items():
        if m["kind"] == "lot": lots[(m["mint"], m["dslot"], m["didx"])].append(m)
    ids, idm = L.ids_map()
    B4.init()
    out = collections.defaultdict(list)
    n = 0
    for f in F:
        if f["us"] is None: continue
        for m in lots.get((f["mint"], f["ds"], f["di"]), []):
            r = byli[m["li"]]
            e = dict(id=n, kind="lot", ds=f["ds"], di=f["di"], slot=r["slot"], idx=r["idx"], close_cc=r["close_cc"], code=r["code"], size=0.40, kreg=[], our_us=f["us"])
            res = B4.work((idm[f["mint"]], [e]))[0][1]; n += 1
            if not res: continue
            d = {x["m"]: x for x in res}
            out[r["code"]].append((d["ours_real"], d["his"], r["net"] * 0.40 / r["size"], (f["us"][0], f["us"][1]) < (r["slot"], r["idx"])))
    P("# Shared dumps: OUR REAL position vs HIS position, each with HIS exit and with our exits (bot replaced; exact replay; 0.40 SOL; curve mSOL/lot, tx costs excluded)")
    for c in (247, 248):
        v = out[c]
        P(f"\n## bot {c}: {len(v)} shared dumps (we ahead of him on {100 * np.mean([x[3] for x in v]):.0f}%); his realized lot scaled to 0.40 after his costs {1000 * np.mean([x[2] for x in v]):+.2f}")
        P("| exit | our real position, no limit [90%] | our real position, +5 % guard | his position, no limit | his position - ours |"); P("|---|---|---|---|---|")
        for a, pol in enumerate(PL):
            o = np.array([x[0]["pn"][0, a] for x in v]); h = np.array([x[1]["pn"][0, a] for x in v]); g = np.array([x[0]["pn"][0, a] if x[0]["fill5"] else 0.0 for x in v])
            ok = np.isfinite(o) & np.isfinite(h); lo, hi = boot_mean(o[ok])
            P(f"| {pol} | {1000 * o[ok].mean():+.2f} [{1000 * lo:+.2f}..{1000 * hi:+.2f}] | {1000 * np.nan_to_num(g[ok]).mean():+.2f} | {1000 * h[ok].mean():+.2f} | {1000 * (h[ok] - o[ok]).mean():+.2f} |")
    P.save()


if __name__ == "__main__":
    main()
