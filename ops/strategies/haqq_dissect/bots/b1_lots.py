#!/usr/bin/env python3
"""BOTS step 1 (read-only): bots 247 / 248 (and 244, 226 for reference) - every code-matched lot (pos analyst p1.pkl, codes = CU price
mod 1000) with its decision-time context, joined to the dv8 dump universe (uni.npz: outside sell drop >= 5 %, sell >= 0.5 SOL,
curve > 30.52, age <= 30 min) by the dump's (mint, slot, idx).
MEASURED: lot P&L (code-matched, after pump fees + his measured tx costs), hold, his position after the dump (outside trades
between the dump and his buy, our two wallets removed), his price paid vs the post-dump price.
Out: /home/moiz/sniper-data/haqq_dissect/bots/b1.pkl, b1.txt"""
import sys, pickle, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import load, boot_sum, Out
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/bots"
CODES = (247, 248, 244, 226)


def main():
    P = Out(f"{OUT}/b1.txt")
    B, LO, T = load()
    ids, idm = L.ids_map()
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]
    key = {(int(m), int(s), int(i)): k for k, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
    rows = []
    for li, l in enumerate(LO):
        if l["code"] not in CODES: continue
        b = B[l["b"]]; t = T[l["trip_ix"]]
        if t["mayhem"]: continue
        hs = (b["bt"] + 18000) // 3600 * 3600 - 18000
        r = dict(li=li, code=l["code"], mint=b["mint"], mi=idm.get(b["mint"]), slot=b["slot"], idx=b["idx"], bt=b["bt"], cc=b["cc"], day=l["day"],
                 size=float(l["cost"]), net=float(l["cnet"]), gross=float(l["cgross"]), hold=l["chold_s"], usable=hs in good, gap=t["gap"],
                 kbuy=b["kbuy"], ktrip=b["ktrip"], new_trip=bool(b["new_trip"]), age=b["age"], vsol=b["vsol_pre"], n_open=b["n_open_lots"],
                 d_drop=b["d_drop"], d_sol=b["d_sol"], d_slots=b["d_slots"], d_ms=b["d_ms"], d_type=b["d_type"], d_nbuy=b["d_nbuy"],
                 d_slot=b.get("d_slot"), d_idx=b.get("d_idx"), dd10=b["dd10"], ch10=b["ch10"], bo3=b["bo3"], so3=b["so3"], unreal=b["unreal"],
                 nsell=l["nsell"], close_cc=l.get("cclose_cc"), out=float(l["cout"]), tok=float(l["tok"]))
        r["dump"] = (r["d_drop"] or 0) >= 0.05 and r["d_slots"] is not None and r["d_slots"] <= 2
        r["u"] = key.get((r["mi"], r["d_slot"], r["d_idx"])) if r["d_slot"] is not None else None
        rows.append(r)
    pickle.dump(rows, open(f"{OUT}/b1.pkl", "wb"))
    P(f"# Bots: code-matched lots (non-mayhem), 10-22 03:07 -> 10-28 01:12 PKT (MEASURED)")
    P("| code | lots | usable-hour lots | net SOL | mSOL/lot | dump-reactive (>=5 % drop <=2 slots) | of those in dv8 universe | their net | non-dump lots net |")
    P("|---|---|---|---|---|---|---|---|---|")
    for c in CODES:
        v = [r for r in rows if r["code"] == c]; vu = [r for r in v if r["usable"] and not r["gap"]]
        d = [r for r in vu if r["dump"]]; du = [r for r in d if r["u"] is not None]; nd = [r for r in vu if not r["dump"]]
        P(f"| {c} | {len(v):,} | {len(vu):,} | {sum(r['net'] for r in v):+.2f} | {1000 * np.mean([r['net'] for r in v]):+.2f} | {len(d):,} ({100 * len(d) / max(len(vu), 1):.0f}%) "
          f"net {sum(r['net'] for r in d):+.2f} | {len(du):,} ({100 * len(du) / max(len(d), 1):.0f}%) | {sum(r['net'] for r in du):+.2f} | {sum(r['net'] for r in nd):+.2f} ({len(nd):,}) |")
    # why dump lots fall outside the universe
    P("\n## Dump-reactive lots outside the dv8 universe: which universe condition fails (247+248)")
    v = [r for r in rows if r["code"] in (247, 248) and r["usable"] and not r["gap"] and r["dump"] and r["u"] is None]
    c = collections.Counter()
    for r in v:
        why = []
        if (r["d_sol"] or 0) < 0.5: why.append("sell<0.5")
        if r["age"] is not None and r["age"] * 0.212 > 1800: why.append("age>30min")
        if not why: why.append("other(curve<=30.5 / haqq-own / idx)")
        c["+".join(why)] += 1
    for k, n in c.most_common(): P(f"- {k}: {n:,} lots, net {sum(r['net'] for r in v if ('+'.join([x for x in (['sell<0.5'] if (r['d_sol'] or 0) < 0.5 else []) + (['age>30min'] if r['age'] is not None and r['age'] * 0.212 > 1800 else [])]) or 'other(curve<=30.5 / haqq-own / idx)') == k):+.2f}")
    P.save()


if __name__ == "__main__":
    main()
