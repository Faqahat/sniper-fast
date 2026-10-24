#!/usr/bin/env python3
# READ-ONLY: per-trade evidence for the FINAL-2 "become them" report. For each FINAL-2 live pick (R2 overnight), at 45
# and 75 ms: the tx our modelled buy lands right behind (and how many outside buyers are ahead), the price vs the
# post-bundle price (guard), the trade our 8 s sell lands in front of, and the PnL under three variants (follower
# slippage; + pro buys after us removed; + all sniper buys after us removed) at CW-style cost (0.5 SOL: 1.2% overhead,
# 0.003 SOL per failed buy) and today's cost (2%, 0.005). -> report/f2_evidence.json
# usage: RP_PHASEA_R2=phaseA_gf python3 -I prep_f2_evidence.py
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
CORE = "/home/moiz/sniper/ops/overnight/core"
L = rp.load_launches(); O = rp.load_obs()
B = {r["m"]: r for r in json.load(open(f"{CORE}/final2_picks_v3_become_B0.5_tu.json"))}
picks = list(B)
byb = collections.defaultdict(set)
for m in picks:
    if m in L and m in O: byb[rp.bucket(m)].add(m)
out = []
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = B[m]
        row = dict(m=m, name=c.get("name"), sym=c.get("symbol"), bt=c["bt"], deployer=c.get("user"), create_sig=c.get("sig"),
                   dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3), glued=len(st["glued"]),
                   glued_sol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 3), mc_b=round(p_b * 1e6, 2), pros_in=r.get("pro_in"), land={})
        for Lm in ("45", "75"):
            ib, na = rp.place_bo2(tr, c, st, O[m]["outs"], int(Lm), fa.get(m, []))
            if ib < 1: continue
            ratio = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b
            d = dict(after_sig=tr[ib - 1]["sig"], ahead=na, ratio=round(ratio, 4), fill=ratio <= 1.005)
            x = r.get(Lm, {})
            if d["fill"] and x.get("slip") and x["slip"]["fill"]:
                bs = max(c["slot"], tr[ib - 1]["s"]); due = bs + int(8.0 / (rp.SLOT_MS / 1000.0)) + 1
                ks = next((k for k in range(ib, len(tr)) if tr[k]["s"] >= due), len(tr))
                d["sell_before_sig"] = tr[ks]["sig"] if ks < len(tr) else None
                d["mc_sell_last"] = round(tr[ks - 1]["vsol"] / tr[ks - 1]["vtok"] * 1e6, 2)
                d["nb"] = x["slip"]["nb"]
                for var in ("slip", "proafter_slip", "nosnip"):
                    if x.get(var) and x[var]["fill"]:
                        p8 = x[var]["pnl"]["t8"]; d[var] = dict(today=round(p8, 4), cw=round(p8 + 0.004, 4))
            out.append(row) if False else None
            row["land"][Lm] = d
        out.append(row)
out.sort(key=lambda r: r["bt"])
json.dump(out, open("/home/moiz/sniper/ops/overnight/report/f2_evidence.json", "w"))
f75 = [r for r in out if r["land"].get("75", {}).get("fill")]
print(f"{len(out)} picks; fills 75 ms {len(f75)}; with sell links {sum(1 for r in f75 if r['land']['75'].get('sell_before_sig'))}")
