#!/usr/bin/env python3
"""HAQQ_SEL step 4 (read-only, offline): regular dip buys (M2 gate) on the 24 h window, at 0.50 SOL, on ALL tokens and on haqq's
tokens only. Rows = h2_m2build.py's dd1_HQ_s0.5.npz (the study's own dump rows, P&L per landing row 35 / 50 / 75 ms, +5% buy guard).
Picks = M2 >= the live threshold inside the study envelope (dd20_shadow_eval's Stage A, the bundle the engine loads), exit
c4_tpnone_slnone (hold ~5 slots, no stop: SL -50% practically never fires inside 5 slots), the engine's limits via dd_lib.sim
(AMS near-leader slots, one position, 5 slots between picks on a token, FIX 0.0051 per fill, FAIL 0.0005 per guard-blocked buy).
haqq's trades are used ONLY for the token list (tokens.json). Out: DATA/m2_rows.pkl"""
import sys, os, json, pickle
import numpy as np
DIPD = "/home/moiz/sniper/ops/strategies/dipdetect"; sys.path.insert(0, DIPD)
import dd_lib as L
import dd20_shadow_eval as D20
DATA = "/home/moiz/sniper-data/haqq_sel"; WORK = f"{DATA}/m2/work"
W0 = 1793038500; W1 = 1793124900
E4 = L.EXI["c4_tpnone_slnone"]
BUNDLE = f"{L.OUT}/m2_v3_reg4_top25.json"

if __name__ == "__main__":
    d = D20.load_dd1(f"{WORK}/dd1_HQ_s0.5.npz", W0, W1)
    meta = json.load(open(f"{WORK}/day_HQ_meta.json"))["meta"]
    mint = np.array([meta[t]["m"] for t in d["tok"]])
    B0 = json.load(open(BUNDLE)); cols = [L.FNI[f] for f in B0["fn"]]
    P, B = D20.bundle_scores(BUNDLE, d["Xall"][:, cols]); MIN = float(B["thr_default"])
    HQ = {x["mint"]: x for x in json.load(open(f"{DATA}/tokens.json"))["tokens"]}
    hq = np.array([m in HQ for m in mint])
    inspan = np.array([(m in HQ) and (HQ[m]["first_bt"] - 60 <= t <= HQ[m]["last_bt"] + 60) for m, t in zip(mint, d["t"])])
    sel = d["env"] & (P >= MIN)
    known = np.array([(m in HQ) and HQ[m]["first_slot"] < s_ for m, s_ in zip(mint, d["s"])])      # haqq traded the token before the dump's slot
    print(f"rows {len(mint)}, envelope {int(d['env'].sum())}, M2 picks {int(sel.sum())} (on haqq tokens {int((sel & hq).sum())}, in his span {int((sel & inspan).sum())}); "
          f"near AMS {int((sel & d['near_a']).sum())}, near FRA {int((sel & d['near_f']).sum())}, leader unknown {int((d['lead'] < 0).sum())}")
    out = dict(MIN=MIN, n=len(mint))
    for nm, m_ in (("ALL", sel), ("HQ", sel & hq), ("NONHQ", sel & ~hq), ("HQSPAN", sel & inspan), ("HQKNOWN", sel & known), ("NOTKNOWN", sel & ~known)):
        for srv in (("a",), ("f", "a")):
            for li, lat in enumerate((35, 50, 75)):
                o = L.sim(d, m_, li, E4, servers=srv, detail=True)
                rows = [(int(r), sv, float(p), int(f)) for r, sv, p, f in o["rows"]]
                out[(nm, "+".join(srv), lat)] = dict(att=o["att"], fill=o["fill"], fail=o["fail"], pnl=o["pnl"], win=o["win"], rows=rows)
                print(f"{nm:7s} {'+'.join(srv):4s} {lat} ms: picks tried {o['att']:4d} fills {o['fill']:4d} guard-fails {o['fail']:4d} P&L {o['pnl']:+7.3f} "
                      f"per fill {o['per_fill']:+.4f} win {100 * o['winr']:.0f}%")
    out["mint"] = mint; out["t"] = d["t"]; out["hq"] = hq; out["s"] = d["s"]; out["known"] = known
    pickle.dump(out, open(f"{DATA}/m2_rows.pkl", "wb"))
