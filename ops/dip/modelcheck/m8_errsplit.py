#!/usr/bin/env python3
# MODEL CHECK step 8: bias split on the REAL bot trades (trades_<day>.jsonl.gz), per trade, in mSOL:
#  entry    = model entry value - real (identity: same spot / SOL) -> tokens model/real - 1, and the identity P&L error
#  exit     = our sell at 75 ms into the real sell slot (model) - the real sell row            (I_75 - I_real)
#  follower = what the model credits an EXTRA buyer placed right in front of this bot (X_c4 - I_c4) times the gap between the
#             model's keep probability for the bot's buy (1 - X_botdrop; random a8 slack) and the measured one
#             (S_w(p (1+push) | bot ahead) / S_w(p | real); m6 curves) -> expected optimism of the follower rule
#  + the bot's real P&L, real tx costs; by latency band, leader client, wallet.
import sys, os, json, zlib, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m2_analyze as A2, mc_corr as MC
OUT = "/home/moiz/sniper-data/modelcheck"

def main():
    R = A2.load(tx=True); cl = A2.clients(); CV = MC.Curves(f"{OUT}/curves_all.json")
    C = [r for r in R if r["closed"] and r["I_real"] is not None]
    for r in C:
        r["band"] = next(b for (lo, hi), b in zip(A2.BANDS, A2.BN) if lo <= r["L"] < hi); r["cli"] = cl(r["s"]); r["w8"] = r["w"][:8]
        Vb = (r["curve"] + r["sol_ahead"]) * 1e9; X = r["sol"] * 1e9
        push = ((Vb + X) / Vb) ** 2 - 1
        p = r["ratio"]; w = r["w"]
        kr = min(1.0, CV.S(w, p * (1 + push), 1) / max(CV.S(w, p, 1 if r["tg_ahead"] else 0), 1e-6))
        kt = min(1.0, CV.S(w, p * (1 + push)) / max(CV.S(w, p), 1e-6))
        km = 0.0 if r["X_botdrop"] else 1.0
        cred = r["X_c4"] - r["I_c4"]
        r["push"] = push; r["k_real"] = kr; r["k_tol"] = kt; r["k_mod"] = km
        r["e_fol"] = (km - kr) * cred; r["e_fol_tol"] = (km - kt) * cred
        r["e_exit"] = r["I_75"] - r["I_real"]; r["e_ent"] = r["I_real"] - r["real"]
        r["net"] = r["real"] - ((r.get("txb") or 0) + (r.get("txs") or 0))
    def tab(key, groups, rows, title):
        print(f"\n== {title}  (mSOL per trade; follower = expected optimism of the model's follower rule for an extra buyer in front of the bot)")
        print(f"  {'group':14s} {'n':>6s} {'SOL':>6s} | {'real':>7s} {'net':>7s} | {'entry':>7s} {'exit':>7s} {'follow':>7s} {'(tol)':>7s} | {'credit':>7s} {'keep mod':>8s} {'keep real':>9s} {'push':>6s}")
        for g in groups:
            v = [r for r in rows if r[key] == g]
            if len(v) < 30: continue
            m = lambda k: 1000 * np.mean([r[k] for r in v])
            print(f"  {g:14s} {len(v):6d} {np.mean([r['sol'] for r in v]):6.2f} | {m('real'):+7.2f} {m('net'):+7.2f} | {m('e_ent'):+7.3f} {m('e_exit'):+7.2f} {m('e_fol'):+7.2f} {m('e_fol_tol'):+7.2f} | "
                  f"{1000 * np.mean([r['X_c4'] - r['I_c4'] for r in v]):+7.2f} {np.mean([r['k_mod'] for r in v]):8.1%} {np.mean([r['k_real'] for r in v]):9.1%} {np.mean([r['push'] for r in v]):6.1%}")
        tot = rows
        m = lambda k: 1000 * np.mean([r[k] for r in tot])
        print(f"  {'ALL':14s} {len(tot):6d} {np.mean([r['sol'] for r in tot]):6.2f} | {m('real'):+7.2f} {m('net'):+7.2f} | {m('e_ent'):+7.3f} {m('e_exit'):+7.2f} {m('e_fol'):+7.2f} {m('e_fol_tol'):+7.2f} | "
              f"{1000 * np.mean([r['X_c4'] - r['I_c4'] for r in tot]):+7.2f} {np.mean([r['k_mod'] for r in tot]):8.1%} {np.mean([r['k_real'] for r in tot]):9.1%} {np.mean([r['push'] for r in tot]):6.1%}")
        med = lambda k: 1000 * np.median([r[k] for r in tot])
        print(f"  {'ALL medians':14s} {'':6s} {'':6s} | {med('real'):+7.2f} {med('net'):+7.2f} | {med('e_ent'):+7.3f} {med('e_exit'):+7.2f} {med('e_fol'):+7.2f} {med('e_fol_tol'):+7.2f} |")
    tab("band", A2.BN, C, "ALL BOT DIP BUYS by latency band")
    env = [r for r in C if r["pf"] and (r["pf"]["top4"] or r["pf"]["m2"])]
    tab("band", A2.BN, env, "ON OUR PICK DUMPS (IMIT1 top4 or M2) by latency band")
    tab("cli", [c for c, _ in collections.Counter(r["cli"] for r in C).most_common()], C, "by leader client")
    tab("w8", A2.FOCUS + [w for w, _ in collections.Counter(r["w8"] for r in C).most_common(25) if w not in A2.FOCUS], C, "by wallet")
    # per-SOL comparison with the paper at the same latency: model extra buyer (X) vs replacement (I) vs real, our pick dumps, 35-50 band
    print("\n== pick dumps, 10-75 ms bands: per SOL of buy (c4 exit unless real)")
    for b in ("10-35", "35-50", "50-75"):
        v = [r for r in env if r["band"] == b]; sol = sum(r["cost"] for r in v)
        f = lambda k: 100 * sum(r[k] for r in v) / sol
        print(f"  {b:6s} n {len(v):5d}: real (own exit) {f('real'):+5.2f}% | replace c4 {f('I_c4'):+5.2f}% | extra-buyer c4 (paper) {f('X_c4'):+5.2f}% | "
              f"extra-buyer corrected {100 * sum(r['I_c4'] + r['k_real'] * (r['X_c4'] - r['I_c4']) for r in v) / sol:+5.2f}%")
    json.dump({"note": "see printout"}, open(f"{OUT}/m8_done.json", "w"))

if __name__ == "__main__":
    main()
