#!/usr/bin/env python3
"""8yYMhu e1 (read-only): what decides his exit. Per lot (tape): the position value path (sell-all value on the curve incl. his own buy,
after the 1.25 % sell fee, vs his cost) slot by slot from the buy to the sell, outside flow per slot, and the state at his DECISION point
(the outside trades up to ~73 txs before his sell = his median reaction). Hazard tables + simple-rule fits (exit slot within +-1 of his).
Out: DATA/e1.txt, DATA/exitpath.pkl"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); wid = T.uid()[X.W]
FEE = 0.0125
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
EP = []
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
for mint, ls in bym.items():
    tr = T.trades(mint)
    if tr is None: continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
    vs = tr["vsol"].astype(np.float64); kk = vs * tr["vtok"].astype(np.float64)
    me = tr["user"] == wid; buy = tr["buy"] == 1; sol = tr["sol"].astype(np.float64)
    for l in ls:
        kb = l["s"] * 4096 + l["i"]; pb = int(np.searchsorted(key, kb))
        if not (pb < len(tr) and key[pb] == kb): continue
        ks = l["close_s"] * 4096 + l["close_i"]; ps = int(np.searchsorted(key, ks))
        if not (ps < len(tr) and key[ps] == ks): continue
        tok = float(l["tok"]); k_ = kk[pb]
        def val(j):            # sell-all value after trade j (curve incl. his buy), net of sell fee, minus cost -> return
            V = vs[j]; T1 = k_ / V
            return (V - k_ / (T1 + tok)) * (1 - FEE) / 1e9 / l["cost"] - 1
        hold = l["close_s"] - l["s"]
        path = []
        for x in range(0, hold + 1):
            j = int(np.searchsorted(tr["slot"], l["s"] + x, side="right")) - 1
            seg = (tr["slot"] == l["s"] + x) & ~me
            path.append((x, val(max(j, pb)), float(sol[seg & buy].sum()) / 1e9, float(sol[seg & ~buy].sum()) / 1e9, int((seg & buy).sum()), int((seg & ~buy).sum())))
        # decision point ~73 txs before his sell
        jd = int(np.searchsorted(key, l["close_s"] * 4096 + max(l["close_i"] - 73, 0))) - 1
        jd = max(jd, pb)
        between = np.arange(pb + 1, ps)
        ob = between[~me[between]]
        last_buy = ob[buy[ob]][-1] if (buy[ob]).any() else None
        last_sell = ob[~buy[ob]][-1] if (~buy[ob]).any() else None
        prev = ob[-1] if len(ob) else None
        EP.append(dict(lot=l["lot_id"], hold=hold, ret_exit=val(ps - 1), ret_dec=val(jd), ret_max=max(p[1] for p in path), path=path,
                       pnl=l["pnl_cash"], cost=l["cost"], n_out=len(ob), n_out_buys=int(buy[ob].sum()), n_out_sells=int((~buy[ob]).sum()),
                       prev_buy=(bool(buy[prev]) if prev is not None else None), prev_sol=(float(sol[prev]) / 1e9 if prev is not None else None),
                       prev_slotgap=(l["close_s"] - int(tr["slot"][prev]) if prev is not None else None),
                       since_last_buy=(l["close_s"] - int(tr["slot"][last_buy]) if last_buy is not None else None),
                       since_last_sell=(l["close_s"] - int(tr["slot"][last_sell]) if last_sell is not None else None),
                       big_sell_before=bool(((~buy[ob]) & (sol[ob] >= 1e9)).any()), sell_in_close_slot_before=bool(((tr["slot"][ob] == l["close_s"]) & ~buy[ob]).any()),
                       same_slot_out_before=int((tr["slot"][ob] == l["close_s"]).sum())))
pickle.dump(EP, open(f"{X.D}/exitpath.pkl", "wb"))
n = len(EP); h = np.array([e["hold"] for e in EP])
P(f"lots with full tape path {n}")
c = collections.Counter(h.tolist())
P("hold-slot histogram (slots: count): " + "  ".join(f"{k}:{c[k]}" for k in range(0, 75) if c[k]))
re = np.array([e["ret_exit"] for e in EP]); rm = np.array([e["ret_max"] for e in EP]); rd = np.array([e["ret_dec"] for e in EP])
P(f"return at exit (curve, after fees) p10/25/50/75/90 = " + "/".join(f"{100*X.pct(re,q):+.1f}%" for q in (10, 25, 50, 75, 90)) +
  f"; max return during hold p50 {100*X.med(rm):+.1f}%; exit/max gap p50 {100*X.med(rm-re):.1f} pts")
P("hold by return at exit:")
for lo, hi in ((-1, -.1), (-.1, -.03), (-.03, 0), (0, .03), (.03, .1), (.1, .2), (.2, 9)):
    m = (re >= lo) & (re < hi)
    if m.sum(): P(f"   ret [{100*lo:+.0f}%,{100*hi:+.0f}%): n {m.sum():5}  hold p25/50/75 {X.pct(h[m],25):.0f}/{X.med(h[m]):.0f}/{X.pct(h[m],75):.0f}")
P("what precedes his sell:")
pb_ = [e for e in EP if e["prev_buy"] is not None]
P(f"   previous outside trade is a SELL {100*np.mean([not e['prev_buy'] for e in pb_]):.1f}% (a >=0.5 SOL sell {100*np.mean([(not e['prev_buy']) and e['prev_sol']>=0.5 for e in pb_]):.1f}%), in the same slot as his sell {100*np.mean([e['prev_slotgap']==0 for e in pb_]):.1f}%")
slb = np.array([e["since_last_buy"] if e["since_last_buy"] is not None else 99 for e in EP])
P(f"   slots since the last outside BUY at his sell p25/50/75 = {X.pct(slb,25):.0f}/{X.med(slb):.0f}/{X.pct(slb,75):.0f}; no outside buy at all during hold {100*np.mean(slb==99):.1f}%")
P(f"   an outside sell earlier in his sell slot {100*np.mean([e['sell_in_close_slot_before'] for e in EP]):.1f}%")
# hazard: P(sell at slot x | still holding at x, state at end of slot x-1)
P("hazard: P(he sells in slot x | held through x-1), by slots since entry:")
cnt = collections.Counter(); hz = collections.Counter()
for e in EP:
    for x in range(1, e["hold"] + 1):
        cnt[x] += 1
        if x == e["hold"]: hz[x] += 1
P("   " + "  ".join(f"{x}:{100*hz[x]/cnt[x]:.0f}%" for x in range(1, 41) if cnt[x] >= 30))
P("hazard by return at end of previous slot (x>=3):")
B = [(-9, -.15), (-.15, -.08), (-.08, -.03), (-.03, 0), (0, .03), (.03, .08), (.08, .15), (.15, 9)]
for lo, hi in B:
    a = b = 0
    for e in EP:
        for x in range(3, e["hold"] + 1):
            rp = e["path"][x - 1][1]
            if lo <= rp < hi:
                a += 1; b += (x == e["hold"])
    if a: P(f"   ret [{100*lo:+.0f}%,{100*hi:+.0f}%): slot-obs {a:6}  P(sell next) {100*b/a:5.1f}%")
P("hazard by outside BUY activity in the previous slot (x>=3):")
for lab, fn in (("no outside buy in prev slot", lambda p: p[4] == 0), ("1+ outside buys in prev slot", lambda p: p[4] > 0),
                ("outside sells > buys (SOL) in prev slot", lambda p: p[3] > p[2]), ("outside sell >= 1 SOL total in prev slot", lambda p: p[3] >= 1)):
    a = b = 0
    for e in EP:
        for x in range(3, e["hold"] + 1):
            if fn(e["path"][x - 1]): a += 1; b += (x == e["hold"])
    if a: P(f"   {lab:42}: slot-obs {a:6}  P(sell next) {100*b/a:5.1f}%")
# simple rules: exit at first slot x (>= xmin) where condition holds, cap 73
def rule_eval(name, cond, xmin=1, cap=73):
    agree = 0; pnl_rule = 0.0; pnl_his = 0.0; nn = 0
    for e in EP:
        xs = None
        for x in range(xmin, len(e["path"]) + 200):
            if x >= cap: xs = cap; break
            if x < len(e["path"]):
                if cond(e, x): xs = x; break
            else:
                xs = None; break
        if xs is None or xs >= len(e["path"]): continue          # rule exits after his exit: path unknown beyond -> skip
        nn += 1; agree += abs(xs - e["hold"]) <= 1
        pnl_rule += e["path"][xs][1] * e["cost"]; pnl_his += e["ret_exit"] * e["cost"]
    return name, nn, agree, pnl_rule, pnl_his
P("simple exit rules on his own lots (only lots where the rule fires before or at his exit; agree = within +-1 slot):")
rules = []
for tp in (0.03, 0.05, 0.08, 0.12):
    for sl in (-0.05, -0.1, -0.2):
        rules.append((f"TP {tp:+.0%} / SL {sl:+.0%}", (lambda tp, sl: lambda e, x: e["path"][x][1] >= tp or e["path"][x][1] <= sl)(tp, sl)))
for k in (2, 3, 5):
    rules.append((f"no outside buy for {k} slots (x>={k})", (lambda k: lambda e, x: x >= k and all(e['path'][y][4] == 0 for y in range(x - k + 1, x + 1)))(k)))
rules.append(("first slot with outside sell SOL > buy SOL (x>=2)", lambda e, x: x >= 2 and e["path"][x][3] > e["path"][x][2]))
for tmr in (6, 8, 10, 15):
    rules.append((f"timer {tmr} slots", (lambda t: lambda e, x: x >= t)(tmr)))
for name, cond in rules:
    nm_, nn, ag, pr, ph = rule_eval(name, cond)
    P(f"   {nm_:46} lots {nn:5}  agree {100*ag/max(nn,1):5.1f}%  rule P&L {pr:+8.2f}  his P&L same lots {ph:+8.2f}")
open(f"{X.D}/e1.txt", "w").write("\n".join(out) + "\n")
