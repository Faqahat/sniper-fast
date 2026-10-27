#!/usr/bin/env python3
# Anatomy of the accepted fills of one config (default T2|c): who sold into our order (the big holder itself = quick flip?),
# time from the holder's buy to the dump, holder buy size, token age, dump size, curve, trades ahead of us, which known wallets
# were ahead (pre-placers / fast bots), exit outcome. MEASURED from the replay + tapes.
import sys, json, collections
import numpy as np
import ps_common as C, ps5_lib as E, ps7_test as T
key = sys.argv[1] if len(sys.argv) > 1 else "T2|c"
best = json.load(open(f"{C.OUT}/ps6_select.json"))["best"]; b = best[key]
PP = {C.crc(w): w[:8] for w in json.load(open(f"{C.OUT}/pp_wallets.json"))}
FAST = {C.crc(w): w[:8] for w in ["9K5QgBKarMUHqdkQprh94GVZkxdSPTmsevHedYhSEzaq", "CZ77onJzkSCwZC51Gg7H8oEUUJhqcx8LLKqnsNXWZSBx",
        "FNuoWSQcPMmnbHGQU4sRjZ1iK3nPL4kyxqtsX9Yr4VMb", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"]}
rows = []
for day in ("R2", "R3", "R4", "R1"):
    D = E.load(day); d = C.load(day)
    o = T.one(D, b)
    for w, fr, pn in zip(o["acc_rows"].tolist(), o["acc_fr"].tolist(), o["acc_pnl"].tolist()):
        j = int(D["w_j"][w]); x = int(D["f_x"][fr]); m = int(D["f_m"][fr]); hu = int(d["uid"][j])
        t = int(d["tok"][j]); S0 = d["meta"][t]["S0"]
        ahead = [int(d["uid"][q]) for q in range(x + 1, m + 1)]
        rows.append(dict(day=day, pnl=pn, seller_is_holder=int(d["uid"][x]) == hu, holder_sol=float(d["sol"][j] / 1e9),
                         holder_pct=float(D["w_f"][w, E.FI["hpct"]]), dt_slots=int(d["s"][x] - d["s"][j]), age_s=float((d["s"][x] - S0) * 0.4),
                         drop=float(-d["move"][x]), dump_sol=float(d["sol"][x] / 1e9), curve=float(d["vsol"][x] / 1e9), n_ahead=len(ahead),
                         pp_ahead=any(u in PP for u in ahead), fast_ahead=any(u in FAST for u in ahead), seller_wt=int(d["wt"][x])))
    del D, d
q = lambda v, p: float(np.percentile(v, p))
R = rows; n = len(R)
print(f"{key}: {n} accepted fills over R1..R4 (config {b['filt']}, W {b['W']}, y {b['y']}, {b['dm']}, {b['ex']})")
for nm, sel in (("all", lambda r: True), ("seller = the big holder (quick flip)", lambda r: r["seller_is_holder"]), ("seller = someone else", lambda r: not r["seller_is_holder"])):
    rr = [r for r in R if sel(r)]
    if not rr: continue
    pn = np.array([r["pnl"] for r in rr])
    print(f"  {nm:38s} n {len(rr):5d} ({100 * len(rr) / n:3.0f}%)  net/fill {pn.mean():+.4f}  win {100 * (pn > 0).mean():3.0f}%  "
          f"holder buy {q([r['holder_sol'] for r in rr], 50):.2f} SOL ({q([r['holder_pct'] for r in rr], 50):.1f}% supply)  dump after {q([r['dt_slots'] for r in rr], 50):.0f} slots  "
          f"drop {q([r['drop'] for r in rr], 50):.1f}%  dump {q([r['dump_sol'] for r in rr], 50):.2f} SOL  age {q([r['age_s'] for r in rr], 25):.0f}/{q([r['age_s'] for r in rr], 50):.0f}/{q([r['age_s'] for r in rr], 75):.0f} s  "
          f"curve {q([r['curve'] for r in rr], 50):.0f}  ahead of us {q([r['n_ahead'] for r in rr], 50):.0f} trades, pre-placer ahead {100 * np.mean([r['pp_ahead'] for r in rr]):.0f}%, fast bot ahead {100 * np.mean([r['fast_ahead'] for r in rr]):.0f}%")
for day in ("R2", "R3", "R4", "R1"):
    rr = [r for r in R if r["day"] == day]; pn = np.array([r["pnl"] for r in rr])
    print(f"  {day}: n {len(rr)}, flips {100 * np.mean([r['seller_is_holder'] for r in rr]):.0f}%, net/fill {pn.mean():+.4f}")
json.dump(rows, open(f"{C.OUT}/ps7c_anatomy_{key.replace('|', '_')}.json", "w"))
