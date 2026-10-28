#!/usr/bin/env python3
"""SELECT step 8 (read-only): example tokens for the report, with GMGN links filtered to haqq. For each named signal: a seeded sample of
envelope sells (test days D2-D6) where the signal holds, with the seller, creator, the create-tx strings, the dump, y1 (247/248 bought),
y2 (our pre-send-style WAVE P&L, NOW costs, INFERRED) and the ALL / MKT OOS probabilities.
Usage: s8_examples.py  -> select/examples.json + s8.txt"""
import sys, json, glob
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
import dv8lib as L
from s5_pnl import money
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
GM = "https://gmgn.ai/sol/token/{}?maker=haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"


def main():
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in Z.files}
    Y = dict(np.load(f"{OUT}/y2.npz")); SC = load_scores()
    ids, idm = L.ids_map()
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int)
    pmk = 1 / (1 + np.exp(-SC["MKT"])); pal = 1 / (1 + np.exp(-SC.get("ALL", SC["MKT"])))
    cr = {}
    need = set()
    sigs = {
        "serial-dev seller (>= 20 creates), dev sell": (A["f_sel_ncreates"] >= 20) & (A["f_sel_dev"] > 0.5),
        "first-time dev (1 create), dev sell": (A["f_sel_ncreates"] == 1) & (A["f_sel_dev"] > 0.5),
        "non-dev seller that created >= 20 other tokens": (A["f_sel_ncreates"] >= 20) & (A["f_sel_dev"] < 0.5),
        "seller followed by 247/248 >= 5 times before (other mints)": A["f_sel_prev_y"] >= 5,
    }
    rng = np.random.default_rng(8)
    picks = {}
    for nm, m in sigs.items():
        cand = np.flatnonzero(m & (day >= 2) & Y["pick"] & np.isfinite(Y["PSF"]) & np.isfinite(pmk))
        pos = cand[y[cand]]; neg = cand[~y[cand]]
        pk = list(rng.choice(pos, min(4, len(pos)), replace=False)) + list(rng.choice(neg, min(2, len(neg)), replace=False))
        picks[nm] = pk
        for u in pk: need.add(ids[int(A["m"][u])])
    for f in glob.glob(f"{OUT}/cr/*.jsonl"):
        for line in open(f):
            r = json.loads(line)
            if r["mint"] in need: cr[r["mint"]] = dict(name=r.get("name"), sym=r.get("sym"), uri=r.get("uri"), progs=r.get("progs"))
    out = {}; lines = []
    for nm, pk in picks.items():
        n_all = int((sigs[nm] & (day >= 2)).sum()); yr = float(y[sigs[nm] & (day >= 2)].mean())
        lines.append(f"\n## {nm}: {n_all:,} sells D2-D6, y1 rate {yr:.3f}")
        rows = []
        for u in pk:
            mint = ids[int(A["m"][u])]
            v = float(money(Y, np.array([u]), "ps")[0]) * 1000
            r = dict(mint=mint, gmgn=GM.format(mint), time_pkt=L.pkt(int(A["bt"][u])), seller=ids[int(A["sel"][u])], creator=ids[int(A["cr"][u])] if A["cr"][u] >= 0 else None,
                     seller_is_dev=bool(A["f_sel_dev"][u] > 0.5), seller_creates_before=int(A["f_sel_ncreates"][u]), seller_prev_followed=int(A["f_sel_prev_y"][u]),
                     creator_prev_launches=int(A["f_cr_prev"][u]), age_s=round(float(A["f_age_s"][u]), 1), sell_sol=round(float(A["f_sell_sol"][u]), 3),
                     drop_pct=round(100 * float(A["f_drop"][u]), 1), dd10_pct=round(100 * float(A["f_dd10"][u]), 1), seller_bal_pct=round(float(A["f_sel_bal"][u]), 2),
                     bought247=bool(A["y247"][u]), bought248=bool(A["y248"][u]), haqq_net_msol=round(1000 * float(A["hq_net"][u]), 1),
                     ps_wave_now_msol=round(v, 1), p_mkt=round(float(pmk[u]), 3), p_all=round(float(pal[u]), 3), create=cr.get(mint))
            rows.append(r)
            lines.append(f"- [{mint[:6]}…]({r['gmgn']}) {r['time_pkt']} | {(cr.get(mint) or {}).get('sym')} | seller {r['seller'][:6]}… dev={r['seller_is_dev']} "
                         f"creates={r['seller_creates_before']} prevfollowed={r['seller_prev_followed']} | age {r['age_s']} s, sell {r['sell_sol']} SOL, drop {r['drop_pct']} % | "
                         f"247 {r['bought247']} 248 {r['bought248']} haqq {r['haqq_net_msol']:+} mSOL | ps WAVE {r['ps_wave_now_msol']:+} mSOL | p_MKT {r['p_mkt']} p_ALL {r['p_all']}")
        out[nm] = rows
    json.dump(out, open(f"{OUT}/examples.json", "w"), indent=1)
    open(f"{OUT}/s8.txt", "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
