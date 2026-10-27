#!/usr/bin/env python3
"""LIVE28 step 1: the QUIET stop as the replay models it, checked on run 28's live windows (MEASURED vs model).
  * decision time: live QUIET stops happen at d_stop (engine ms after it saw the trigger); the model decides at
    d_dec = chain clock of the start of slot trigger + 6 - the trigger's chain clock + delta. delta is MEASURED here
    (median of d_stop - that chain gap over the live stops).
  * others: the trades by others (not the whale, not us) the engine had counted at its decision (the disarm record's 'others',
    117 decided windows) vs the model's count of tape trades seen by d_dec (view model, each window's own fitted view speed q).
Writes DATA/qcheck.json (delta and the agreement)."""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L
import sim, rlib

SMS = rlib.SMS

if __name__ == "__main__":
    R = L.load_run(); tp = L.Tape28(R)
    D = pickle.load(open(f"{L.DATA}/donors28.pkl", "rb"))
    qv = {W["w"]: W["q_view"] for W in D["R28"]["wins"]}
    view = sim.View(); idm = tp.id_map()
    rows = []
    for w, x in R["W"].items():
        tr = x["arm"]["trig"]; dz = x["disarm"]; q = dz.get("quiet") or {}
        ct = tp.cc(tr["slot"], tr["idx"]); t6 = (tr["slot"] + 6) * SMS - ct
        d_dis = (dz["t"] - tr["t"]) / 1e6
        rows.append(dict(w=w, mint=tr["mint"], slot=tr["slot"], idx=tr["idx"], whale=tr["wallet"], ct=ct, t6=t6, d_dis=d_dis, why=dz["why"],
                         decided=q.get("decided"), others=q.get("others"), stop=dz.get("quiet_stop"), q=qv[w], dslot=dz["slot"] - tr["slot"]))
    st = [r for r in rows if r["stop"]]
    delta = np.array([r["d_dis"] - r["t6"] for r in st])
    print(f"live QUIET stops {len(st)}: disarm slot - trigger slot {collections.Counter(r['dslot'] for r in st)}")
    print("delta = d_stop - chain gap to slot+6 start (ms) pcts 5/25/50/75/95:", np.percentile(delta, [5, 25, 50, 75, 95]).round(1))
    dmed = float(np.median(delta))
    # others: model count at d_dec = t6 + delta_med, with the window's own q
    agree = collections.Counter(); diffs = []; out = []
    for r in rows:
        if not r["decided"]: continue
        tk = sim.Tok(tp, r["mint"], r["slot"] - 3, r["slot"] + 40)
        kt = max(tk.before(r["slot"], r["idx"] + 0.5), 0)
        seen = view.seen_times(tk, kt, r["slot"], r["ct"], r["q"])
        wid = idm.get(r["whale"], -1)
        d_dec = r["t6"] + dmed
        n = int(np.searchsorted(seen, d_dec, side="right"))
        oth = sum(1 for k in range(kt + 1, kt + 1 + n) if tk.user[k] != wid and tk.user[k] != tp.our_id)
        # the chain truth: others on chain before the start of slot +6 (no view model)
        oth_chain = sum(1 for k in range(kt + 1, tk.n) if tk.s[k] < r["slot"] + 6 and tk.user[k] != wid and tk.user[k] != tp.our_id)
        m_stop = oth < 2; l_stop = (r["others"] or 0) < 2
        agree[(l_stop, m_stop)] += 1; diffs.append(oth - (r["others"] or 0))
        out.append(dict(w=r["w"], live_others=r["others"], model_others=oth, chain_others=oth_chain, live_stop=l_stop, model_stop=m_stop))
    n = sum(agree.values())
    print(f"decided windows {n}: (live stop, model stop) {dict(agree)}; agreement {(agree[(True, True)] + agree[(False, False)]) / n * 100:.1f}%")
    diffs = np.array(diffs); print("model - live others: mean %.2f, exact %.0f%%, |diff|<=1 %.0f%%" % (diffs.mean(), (diffs == 0).mean() * 100, (np.abs(diffs) <= 1).mean() * 100))
    ch = np.array([o["chain_others"] - (o["live_others"] or 0) for o in out]); print("chain(before slot+6) - live others: mean %.2f exact %.0f%%" % (ch.mean(), (ch == 0).mean() * 100))
    json.dump(dict(delta_med=dmed, delta_pcts=np.percentile(delta, [5, 25, 50, 75, 95]).tolist(), agree={f"{a}|{b}": v for (a, b), v in agree.items()},
                   n=n, rows=out, stops=[dict(w=r["w"], d=r["d_dis"], t6=r["t6"]) for r in st]), open(f"{L.DATA}/qcheck.json", "w"), indent=1)
