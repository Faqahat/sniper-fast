#!/usr/bin/env python3
# Run the R2-chosen configs (ps6_select.json) UNCHANGED on R2 (in-sample), R3, R4, R1 (test), per queue assumption, with cost rows:
#   cheap-k  : attempts at 5,060 lamports (60k CU x 1,000 uL/CU + base), k consistent with the queue model (a/b/c: 20 per slot)
#   cheap-k1 : same but k = 1 attempt per slot (optimistic for a/b/c: one attempt per slot cannot be sure to land right after)
#   now-k    : attempts at 505,000 lamports (100k CU x 5M uL/CU + base) = what we pay now
#   +selltip : cheap-k with a 0.001 SOL tip on the sell too
# Robustness on each day: hour-block bootstrap (90% interval of the day total), without the top 1% of fills, positive hours,
# falling knife (share of fills followed by a further >= 10% price drop within the hold), fills per token.
# -> presend/ps7_test.json + stdout
import sys, json, collections
import numpy as np
import ps5_lib as E
DAYS = ("R2", "R3", "R4", "R1")
def boot(o, D, h, B=2000, seed=7):
    """hour blocks (PKT clock hours inside the eval window): fills' net + attempt costs of windows armed in that hour"""
    hr = lambda t: ((t + 5 * 3600) // 3600).astype(np.int64)
    contrib = collections.defaultdict(float)
    for t, v in zip(hr(o["acc_t"]).tolist(), o["acc_pnl"].tolist()): contrib[t] += v
    fa = o["fee_att"]; k = o["k"]
    # attempts: k x armed slots per window, minus the fill attempt (already in the fill cost)
    for t, sl in zip(hr(o["arm_t"]).tolist(), o["arm_slots"].tolist()): contrib[t] -= k * sl * fa
    for t in hr(o["acc_t"]).tolist(): contrib[t] += fa
    H = sorted(contrib); v = np.array([contrib[x] for x in H])
    if len(v) < 2: return (float("nan"), float("nan")), 0, len(v)
    rng = np.random.default_rng(seed); s = v[rng.integers(0, len(v), (B, len(v)))].sum(1)
    return (float(np.percentile(s, 5)), float(np.percentile(s, 95))), int((v > 0).sum()), len(v)

def one(D, b, fee="cheap", k=None, sell_tip=0.0):
    m = SEL[b["fam"]](D, b["filt"])
    o = E.run(D, m, b["W"], b["y"], b["dm"], b["size"], b["ex"], k=k, fee=fee, sell_tip=sell_tip, end_cre=b["end_cre"], detail=True)
    o["fee_att"] = E.FEE[fee]
    return o

def m_T1(D, fp, fam=0):
    f = lambda k: E.wfeat(D, k)
    m = (D["w_fam"] == fam) & (f("drop") >= fp["drop_min"]) & (f("age_s") <= fp["age_max"]) & (f("sell_sol") >= fp["sell_min"])
    if fp["first"]: m &= f("ndump2") == 0
    if fp["crelist"]: m &= (f("cre_nprev") >= 3) & (f("cre_early") >= 0.8)
    return m
def m_T2(D, fp):
    f = lambda k: E.wfeat(D, k); m = (D["w_fam"] == 2) & (f("hpct") >= fp["hpct_min"])
    if fp["htype"]: m &= f("htype") == fp["htype"]
    if fp["crelist"]: m &= (f("cre_nprev") >= 3) & (f("cre_early") >= 0.8)
    return m
def m_T3(D, fp):
    f = lambda k: E.wfeat(D, k); m = (D["w_fam"] == 3) & (f("cre_nprev") >= fp["nprev_min"]) & (f("dev_pct") >= fp["dev_pct_min"])
    if fp["nprev_min"] > 0: m &= f("cre_early") >= fp["early_min"]
    return m
SEL = {"T1": lambda D, fp: m_T1(D, fp, 0), "T1t": lambda D, fp: m_T1(D, fp, 1), "T2": m_T2, "T3": m_T3}

def capi(ex):
    c = int(ex.split("_")[0][1:]); return 0 if c <= 4 else (1 if c <= 6 else 2)

if __name__ == "__main__":
    best = json.load(open(f"{E.C.OUT}/ps6_select.json"))["best"]
    keys = sys.argv[1:] or list(best)
    out = {}
    for day in DAYS:
        D = E.load(day); h = D["hours"]
        print(f"\n=== {day} ({h:.1f} h){' TRAIN (in-sample)' if day == 'R2' else ' TEST'}", flush=True)
        for key in keys:
            b = best[key]
            rows = {"cheap-k": one(D, b), "now-k": one(D, b, fee="now"), "+selltip": one(D, b, sell_tip=0.001)}
            if b["dm"] in ("a", "b", "c"): rows["cheap-k1"] = one(D, b, k=1)
            o = rows["cheap-k"]
            ci, poshr, nhr = boot(o, D, h)
            pn = np.sort(o["acc_pnl"]); ntop = max(1, int(round(0.01 * len(pn)))) if len(pn) else 0
            no_top = float(o["pnl"] - pn[-ntop:].sum()) if len(pn) else 0.0
            ci_ = capi(b["ex"]); knife = float((o["acc_pmin"][:, ci_] <= 0.90).mean()) if o["fill"] else float("nan")
            tokc = collections.Counter(o["acc_tok"].tolist()); maxtok = max(tokc.values()) if tokc else 0
            rate = o["att"] / (h * 3600)
            rec = {nm: dict(pnl=r["pnl"], per24=r["pnl"] / h * 24, fill=r["fill"], armed=r["armed"], att=r["att"], att_per_fill=r["att_per_fill"],
                            per_fill=r["per_fill"], gross_per_fill=r["gross_per_fill"], winr=r["winr"], cost_att=r["cost_att"], cost_fill=r["cost_fill"],
                            skip=r["skip"]) for nm, r in rows.items()}
            rec["robust"] = dict(boot90=ci, pos_hours=poshr, hours=nhr, no_top1=no_top, knife10=knife, tokens=len(tokc), max_fills_tok=maxtok,
                                 att_per_s=rate)
            out[f"{key}|{day}"] = rec
            print(f"  {key:8s} " + " | ".join(f"{nm} {r['pnl']:+7.2f} ({r['pnl'] / h * 24:+6.2f}/24h)" for nm, r in rows.items()))
            print(f"           fills {o['fill']} of {o['armed']} armed, net {o['per_fill']:+.4f}/fill (gross {o['gross_per_fill']:+.4f}), win {100 * o['winr']:.0f}%, "
                  f"att/fill {o['att_per_fill']:.0f}, {rate:.1f} att/s | boot90 [{ci[0]:+.2f}, {ci[1]:+.2f}], +hours {poshr}/{nhr}, w/o top1% {no_top:+.2f}, "
                  f"knife(-10%) {100 * knife:.0f}%, tokens {len(tokc)} (max {maxtok}/token)", flush=True)
        del D
    json.dump(out, open(f"{E.C.OUT}/ps7_test.json", "w"), indent=1, default=float)
