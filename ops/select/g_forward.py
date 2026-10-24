#!/usr/bin/env python3
# FORWARD PAPER TEST (read-only, offline): apply the FROZEN strategies (g_freeze.py models + fixed filters) to launches
# created after FORWARD_START (the new collection run), unseen by any training. Reports every entry position so the
# speed requirement is visible. Costs: pump fee per side (in the replay) + FIX SOL per round trip.
# usage: python3 g_forward.py <combined table.jsonl.gz> <forward start unix> <out dir> <frozen.json> [<frozen2.json> ...]
import sys, os, json, gzip, collections
import numpy as np
T, START, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3]; FROZ = sys.argv[4:]; SIZE = 0.5
os.makedirs(OUT, exist_ok=True)
R = [json.loads(l) for l in gzip.open(T, "rt")]
R = [r for r in R if r.get("bt") and r["bt"] >= START and r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200]
LAST = max((r["bt"] for r in R), default=START); R = [r for r in R if r["bt"] <= LAST - 900]   # skip the last 15 min: outcomes not complete yet
R.sort(key=lambda r: (r["bt"], r["S"])); N = len(R)
g = lambda k: np.array([r.get(k) if isinstance(r.get(k), (int, float)) else np.nan for r in R], float)
hour = ((g("bt") - START) // 3600).astype(int) if N else np.array([])
def feat(name):
    if "==" in name:
        k, v = name.split("==", 1); return np.array([float((r.get(k) or "") == v) for r in R])
    return g(name)
def pred(t, Bm):
    out = np.zeros(len(Bm)); stack = [(t, np.arange(len(Bm)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = Bm[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out
def stats(v):
    v = v[~np.isnan(v)]
    if len(v) == 0: return None
    pnl = v * SIZE; pos, neg = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum(); cum = np.concatenate([[0], np.cumsum(pnl)])
    return dict(n=int(len(v)), win=round(float((v > 0).mean()), 3), mean=round(float(v.mean()), 4), median=round(float(np.median(v)), 4),
                pf=round(float(pos / neg), 2) if neg else None, total_sol=round(float(pnl.sum()), 3), maxdd_sol=round(float(np.max(np.maximum.accumulate(cum) - cum)), 3))
SEL = {
 "F4 dev>=2 & bundle>=2 wallets & idle>=300s & not mayhem": (g("dev_buy") >= 2) & (g("glued_wallets") >= 2) & (g("cr_last_tx_s") >= 300) & (g("mayhem") == 0),
 "F3 dev>=2 & bundle>=3 SOL & idle>=300s & no dev create <15 min": (g("dev_buy") >= 2) & (g("glued_sol") >= 3) & (g("cr_last_tx_s") >= 300) & ~(g("cr_min_since_prev_create") < 15),
 "F5 dev>=1 & idle>=350s": (g("dev_buy") >= 1) & (g("cr_last_tx_s") >= 350),
}
fix = 0.015
for fz in FROZ:
    M = json.load(open(fz)); fix = M["fix"]
    X = np.column_stack([feat(k) for k in M["features"]]) if N else np.zeros((0, len(M["features"])))
    Bm = np.zeros(X.shape, np.int16)
    for j, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    sc = np.full(N, M["F0"])
    for t in M["trees"]: sc += M["lr"] * pred(t, Bm)
    tag = {"liveh": "LIVE", "liveh2": "LIVE2"}.get(M.get("featset"), M["entry"])
    for q, thr in M["thresholds"].items(): SEL[f"MODEL {tag}/{M['exit']} top {q}"] = sc >= thr
EXITS = ["fsell_30s_eos", "fsell_30s", "sk1_10s_eos", "sk2_10s_eos", "h3s", "h5s", "h10s", "sk1_10s", "sk2_10s", "sk3_10s", "sv1_10s", "trail20_10_s15_2m", "tp20_sl10_30s"]
rep = dict(forward_start=START, launches=N, hours=float((g("bt").max() - START) / 3600) if N else 0, fix=fix, results={})
lines = [f"FORWARD PAPER TEST: {N} SOL launches since start ({rep['hours']:.1f} h); fixed cost {fix} SOL/trade, 0.5 SOL size"]
for nm, m in SEL.items():
    lines.append(f"\n{nm}: {int(m.sum())} picks ({m.sum() / max(rep['hours'], 1e-9):.1f}/h)")
    res = {}
    for en in ("E_bundle", "E_k1", "E_k2", "E_slot"):
        for ex in EXITS:
            col = f"{en}_h{ex[1:]}" if ex.startswith("h") and ex[1].isdigit() else f"{en}_{ex}"
            s = stats(g(col)[m] - fix / SIZE)
            if s: res[f"{en}|{ex}"] = s
    rep["results"][nm] = res
    for en in ("E_bundle", "E_k1", "E_k2", "E_slot"):
        row = [f"{ex}:{res[f'{en}|{ex}']['mean']:+.3f}" for ex in ("h5s", "sk1_10s", "sk2_10s", "trail20_10_s15_2m") if f"{en}|{ex}" in res]
        if row: lines.append(f"   {en:8} n={res[f'{en}|h5s']['n'] if f'{en}|h5s' in res else '?'}  " + "  ".join(row))
    if f"E_bundle|h5s" in res:
        hh = {int(h): stats((g("E_bundle_h5s") - fix / SIZE)[m & (hour == h)]) for h in np.unique(hour[m])}
        lines.append("   E_bundle h5s by hour: " + " ".join(f"h{h}:{s['mean']:+.2f}({s['n']})" for h, s in hh.items() if s))
STRATS = [("S1 model(fsell_eos) top 1%, sell at first sell, end of slot", "MODEL E_bundle/fsell_30s_eos top 1%", "fsell_30s_eos"),
          ("S2 model(fsell) top 1%, sell at first sell, instant", "MODEL E_bundle/fsell_30s top 1%", "fsell_30s"),
          ("S3 model(h5s) top 1%, sell after 5 s", "MODEL E_bundle/h5s top 1%", "h5s"),
          ("S4 model(fsell_eos) top 2%, sell at first sell, end of slot", "MODEL E_bundle/fsell_30s_eos top 2%", "fsell_30s_eos"),
          ("S5 model(sk2_eos) top 1%, sell after 2nd outside buy, end of slot", "MODEL E_bundle/sk2_10s_eos top 1%", "sk2_10s_eos"),
          ("S6 model(h3s) top 0.5%, sell after 3 s", "MODEL E_bundle/h3s top 0%", "h3s"),
          ("S8 model(sk1_eos) top 1%, sell after 1st outside buy, end of slot", "MODEL E_bundle/sk1_10s_eos top 1%", "sk1_10s_eos"),
          ("S9 LIVE model (no RPC) top 1%, sell at first sell, instant", "MODEL LIVE/fsell_30s top 1%", "fsell_30s"),
          ("S10 LIVE model (no RPC) top 2%, sell at first sell, instant", "MODEL LIVE/fsell_30s top 2%", "fsell_30s"),
          ("S11 LIVE2 model (shadow-exact features) top 1%, sell at first sell, instant", "MODEL LIVE2/fsell_30s top 1%", "fsell_30s"),
          ("S12 LIVE2 model (shadow-exact features) top 2%, sell at first sell, instant", "MODEL LIVE2/fsell_30s top 2%", "fsell_30s")]
head = [f"=== OWNER'S 4 PAPER STRATEGIES (0.5 SOL/trade, fixed cost {fix} SOL, pump fees in the replay) ==="]
for lab, sel, ex in STRATS:
    if sel not in SEL: head.append(f"{lab}: model missing"); continue
    m = SEL[sel]; head.append(f"{lab}: {int(m.sum())} picks ({m.sum() / max(rep['hours'], 1e-9):.1f}/h)")
    for en in ("E_bundle", "E_k1", "E_k2", "E_slot"):
        col = f"{en}_h{ex[1:]}" if ex.startswith("h") and ex[1].isdigit() else f"{en}_{ex}"
        s_ = stats(g(col)[m] - fix / SIZE)
        if s_: head.append(f"   {en:8} n={s_['n']:4} mean={s_['mean']:+.3f} median={s_['median']:+.3f} win={s_['win']:.0%} pf={s_['pf']} total={s_['total_sol']:+.3f} SOL maxDD={s_['maxdd_sol']} SOL")
    col = f"E_bundle_h{ex[1:]}" if ex.startswith("h") and ex[1].isdigit() else f"E_bundle_{ex}"
    hh = {int(h): stats((g(col) - fix / SIZE)[m & (hour == h)]) for h in np.unique(hour[m])} if m.sum() else {}
    if hh: head.append("   E_bundle by hour: " + " ".join(f"h{h}:{s_['mean']:+.2f}({s_['n']})" for h, s_ in hh.items() if s_))
    rep.setdefault("owner_strategies", {})[lab] = {"picks": int(m.sum()), "mints": [R[i]["mint"] for i in np.where(m)[0]]}
# S7: size by score on the fsell_eos model (1.5 SOL top 0.5%, 1.0 next 0.5%, 0.5 next 1%), returns per SOL deployed
if "MODEL E_bundle/fsell_30s_eos top 2%" in SEL:
    a, b_, c_ = (SEL[f"MODEL E_bundle/fsell_30s_eos top {q}"] for q in ("0%", "1%", "2%"))
    size = np.where(a, 1.5, np.where(b_, 1.0, np.where(c_, 0.5, 0.0)))
    for en in ("E_bundle", "E_k1", "E_slot"):
        rr = g(f"{en}_fsell_30s_eos") - fix / SIZE; m = (size > 0) & ~np.isnan(rr)
        if m.sum(): head.append(f"S7 sized by score, {en}: trades {int(m.sum())}, deployed {size[m].sum():.1f} SOL, PnL {(rr[m] * size[m]).sum():+.3f} SOL (flat 0.5: {(rr[m] * 0.5).sum():+.3f})")
lines = head + [""] + lines
json.dump(rep, open(os.path.join(OUT, "forward.json"), "w"), indent=1)
open(os.path.join(OUT, "forward.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
