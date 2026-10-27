#!/usr/bin/env python3
# INSTANT-BOTS study, step 7 (read-only): per candidate wallet, from ALL its recorded txs (i6) and its fast follows (i5):
#  - activity: landed buys / sells, FAILED txs (error codes), successful txs WITHOUT a trade (no-op attempts), failed per fill;
#  - how it sends: tip services, CU price / limit, custom programs, signers;
#  - H1 per fast follow: its own attempts (failed or no-op) on the SAME mint in the 3 slots before + the same slot before the dump,
#    and right after (copies that failed once the price moved); per-slot attempt rate while it streams;
#  - P&L (rough): the fee payer's SOL delta summed over all its recorded txs (fees + tips + trades; tokens still held not counted).
# usage: python3 -I i7_profiles.py WTX.jsonl.gz FOLLOWERS.json OUT.json
import sys, json, gzip, collections, statistics
wtx, folp, outp = sys.argv[1], sys.argv[2], sys.argv[3]
FOL = json.load(open(folp))
EVW = collections.defaultdict(list)
for e in FOL["ev"]: EVW[e["u"]].append(e)
# index the wallets' rows: per wallet -> per mint -> list of (s, i, kind, err, sig)
R = collections.defaultdict(lambda: collections.defaultdict(list))
ST = collections.defaultdict(lambda: collections.Counter()); ERR = collections.defaultdict(collections.Counter); NOOP = collections.defaultdict(collections.Counter)
TSV = collections.defaultdict(collections.Counter); CUP = collections.defaultdict(list); CUL = collections.defaultdict(list); PR = collections.defaultdict(collections.Counter)
PNL = collections.Counter(); FEES = collections.Counter(); TIPS = collections.Counter(); SIGN = collections.defaultdict(collections.Counter)
for l in gzip.open(wtx, "rt"):
    s, i, sig, sg, err, fee, cup, cul, cu, pr, ixn, mints, tr, tips, sd0 = json.loads(l)
    payer = sg[0]
    for w in set(sg):
        if err:
            kind = "fail"; ERR[w][err] += 1
        elif tr:
            mine = [t for t in tr if t[4] == w] or tr
            kind = "buy" if any(t[1] for t in mine) else "sell"
        else:
            kind = "noop"; NOOP[w][(ixn[:40] or "-") + " / " + (pr[:20] or "-")] += 1
        ST[w][kind] += 1
        if kind in ("buy", "fail", "noop"):
            TSV[w]["|".join(sorted({t[0] for t in tips})) or "none"] += 1 if kind == "buy" else 0
            if kind == "buy": CUP[w].append(cup or 0); CUL[w].append(cul or 0)
        PR[w][pr[:24] or "-"] += 1
        SIGN[w][len(sg)] += 1
        for m in mints: R[w][m].append((s, i, kind, err, sig))
    PNL[payer] += sd0; FEES[payer] += fee or 0; TIPS[payer] += sum(v for _, v in tips)
def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else None
out = {}
for w in sorted(ST, key=lambda w: -len(EVW.get(w, []))):
    st = ST[w]; ev = EVW.get(w, [])
    fills = st["buy"]
    h1 = []
    for e in ev:
        rows = R[w].get(e["mint"], [])
        bef3 = [r for r in rows if e["s"] - 3 <= r[0] and (r[0], r[1]) < (e["s"], e["di"]) and r[2] in ("fail", "noop")]
        same_before = [r for r in bef3 if r[0] == e["s"]]
        aft = [r for r in rows if r[0] in (e["s"], e["s"] + 1) and (r[0], r[1]) > (e["s"], e["di"] + e["gap"]) and r[2] in ("fail", "noop")]
        prev = [r for r in rows if r[0] < e["s"] - 3 and r[0] >= e["s"] - 40 and r[2] in ("fail", "noop")]
        h1.append(dict(s=e["s"], gap=e["gap"], client=e["client"], att_3slots=len(bef3), att_same_slot=len(same_before), att_after=len(aft), att_prev40=len(prev),
                       per_slot=len(bef3) / 3.0 if bef3 else 0.0, errs=collections.Counter(r[3] or r[2] for r in bef3).most_common(3)))
    out[w] = dict(w=w, fast=len(ev), g1=sum(1 for e in ev if e["gap"] == 1), g2_5=sum(1 for e in ev if 2 <= e["gap"] <= 5), g6_40=sum(1 for e in ev if e["gap"] >= 6),
                  buys=fills, sells=st["sell"], failed=st["fail"], noop=st["noop"], failed_per_fill=st["fail"] / max(fills, 1), noop_per_fill=st["noop"] / max(fills, 1),
                  errs=ERR[w].most_common(6), noops=NOOP[w].most_common(4), tips=TSV[w].most_common(5), cup_med=pct(CUP[w], 0.5), cul_med=pct(CUL[w], 0.5),
                  progs=PR[w].most_common(4), nsigners=dict(SIGN[w]), pnl_sol=PNL[w] / 1e9, fees_sol=FEES[w] / 1e9, tips_sol=TIPS[w] / 1e9,
                  h1_any=sum(1 for x in h1 if x["att_3slots"] > 0), h1_same=sum(1 for x in h1 if x["att_same_slot"] > 0), h1_med_per_slot=pct([x["per_slot"] for x in h1], 0.5),
                  h1_rows=h1)
json.dump(out, open(outp, "w"))
print("wallet    fast g1 g2-5 g6+ | buys sells failed noop  fail/fill noop/fill | H1: att before (3 slots) / same slot, med att/slot | tips | cup cul | pnl fees tips | errs | noops")
for w, o in out.items():
    if o["fast"] < 1 and o["buys"] < 1: continue
    print(f"{w[:8]} {o['fast']:5d} {o['g1']:2d} {o['g2_5']:4d} {o['g6_40']:4d} | {o['buys']:5d} {o['sells']:5d} {o['failed']:6d} {o['noop']:5d} {o['failed_per_fill']:8.1f} {o['noop_per_fill']:8.1f} | "
          f"{o['h1_any']:4d} / {o['h1_same']:4d}, {o['h1_med_per_slot'] or 0:.1f} | {o['tips'][:3]} | {o['cup_med']} {o['cul_med']} | {o['pnl_sol']:+.2f} {o['fees_sol']:.3f} {o['tips_sol']:.3f} | {o['errs'][:3]} | {o['noops'][:2]}")
