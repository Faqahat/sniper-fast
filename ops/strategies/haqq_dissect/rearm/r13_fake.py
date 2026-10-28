#!/usr/bin/env python3
"""REARM step 13 (read-only; G2): FAKE-DUMP fills. For every pre-send fill, the sell that pushed the curve to our limit (the last trade
before our fill whose pre-trade price was above our limit and post-trade price at/below it: the 'crossing sell'), and its seller:
  round_trip  = the seller bought >= 50 % of the sold tokens of this mint within the last 2 slots (incl. the same slot) before it
               (the FRA r27 H6oKev case: buy 2.963 SOL + sell 2.963 SOL in one slot);
  whale       = not a round trip, and held >= 6 % of supply before the sell (a real holder);
  small       = anyone else (held < 6 %, not a round trip);
  armed_whale = (live T2 windows) the crossing seller is the wallet the window armed on.
Balances are counted from the token's first trade on the tape cut (tab_D4/D5/D6; tokens are young).
Fills: (1) LIVE (MEASURED): every presend_live_fill of AMS r24-r33 and FRA r26 on the dv8 tape (FRA r27 is past the tape's end,
10-28 02:33 PKT, so its fills cannot be classified here); P&L = the window's live fill P&L + rent back (val_<run>.pkl);
(2) REPLAY (INFERRED): the re-arm fills of decisions.jsonl (any:20:30:8:2, test days D1-D6), P&L model NOW.
Out: r13.txt"""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import rlib
from r1_tapes import RUNS
from r3_events import our_sighs
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
WHALE = 60_000_000_000_000
Lo = []
def P(s=""): print(s, flush=True); Lo.append(s)


def boot(v, n=2000):
    v = np.asarray(v, float)
    if len(v) < 2: return (np.nan, np.nan)
    r = np.random.default_rng(1); m = [v[r.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return np.percentile(m, 5), np.percentile(m, 95)


TABS = {}
def tab(d, ours):
    k = (d, ours)
    if k not in TABS:
        tp = rlib.Tape(tab=f"{OUT}/tab_D{d}", with_ours=False)
        keep = np.ones(len(tp.s), bool) if ours else ~np.isin(tp.sigh, np.fromiter(our_sighs(), dtype=np.uint64))
        TABS[k] = (tp, keep, tp.id_map())
    return TABS[k]


def classify(tp, keep, idm, mint, S, I, lim, armed=None):
    mid = idm.get(mint)
    if mid is None or mid not in tp.span: return None
    a, e = tp.span[mid]
    rows = [k for k in range(a, e) if keep[k]]
    pos = [(int(tp.s[k]), float(tp.i[k])) for k in rows]
    # rows strictly before our fill
    n = 0
    while n < len(rows) and pos[n] < (S, I): n += 1
    bal = collections.defaultdict(int); first = {}; hist = collections.defaultdict(list)
    cross = None
    for q in range(n):
        k = rows[q]; u = int(tp.user[k])
        if q > 0:
            kp = rows[q - 1]; p_pre = tp.vsol[kp] / tp.vtok[kp]; p_post = tp.vsol[k] / tp.vtok[k]
            if (not tp.buy[k]) and p_pre > lim >= p_post and int(tp.s[k]) >= S - 3:
                cross = (q, k, bal[u], first.get(u), [h for h in hist[u] if h[0] >= int(tp.s[k]) - 2])
        if tp.buy[k]:
            bal[u] += int(tp.tok[k]); first.setdefault(u, int(tp.s[k])); hist[u].append((int(tp.s[k]), int(tp.tok[k])))
        else: bal[u] -= int(tp.tok[k])
    if cross is None: return dict(cls="no_crossing")
    q, k, b0, f0, rec = cross
    u = int(tp.user[k]); tok = int(tp.tok[k])
    rt = sum(t for s_, t in rec) >= 0.5 * tok
    rt_same = sum(t for s_, t in rec if s_ == int(tp.s[k])) >= 0.5 * tok
    is_armed = armed is not None and tp.ids[u] == armed
    cls = "armed_whale" if is_armed else ("round_trip" if rt else ("whale" if b0 >= WHALE else "small"))
    return dict(cls=cls, seller=tp.ids[u], pct=tok / 1e13, bal_pct=b0 / 1e13, held_slots=(int(tp.s[k]) - f0) if f0 is not None else None,
                armed=is_armed, rt=rt, rt_same=rt_same, sell_slot=int(tp.s[k]))


def tab_for(S):
    for d, (lo, hi) in ((4, (461338294, 461764868)), (5, (461745105, 462171110)), (6, (462151392, 462200814))):
        if lo <= S <= hi - 20: return d
    return None


def table(title, R):
    P(f"\n## {title}")
    P("| Crossing seller | Fills | Share | P&L mSOL/fill [90%] | Win | Sum SOL | bought it back within 2 slots (same slot) |")
    P("|---|---|---|---|---|---|---|")
    n = len(R)
    for c in ("armed_whale", "whale", "small", "round_trip", "no_crossing"):
        v = [x for x in R if x["cls"] == c]
        if not v: continue
        p = np.array([x["pnl"] for x in v]); lo, hi = boot(p)
        P(f"| {c} | {len(v)} | {100 * len(v) / n:.0f}% | {p.mean():+.2f} [{lo:+.2f}, {hi:+.2f}] | {100 * (p > 0).mean():.0f}% | {p.sum() / 1e3:+.3f} | {sum(1 for x in v if x.get('rt'))} ({sum(1 for x in v if x.get('rt_same'))}) |")


# ---- live
L = []; NCONS = {}
for run in ["a24", "a25", "a26", "a27", "a28", "a29", "a30", "a31", "a32", "a33", "f26"]:
    Z = pickle.load(open(f"{OUT}/val_{run}.pkl", "rb")); lv = {x["w"]: x["live"] for x in Z["meta"]["live"]}
    arm = {}; fills = []
    for l in open(RUNS[run], errors="ignore"):
        if '"presend_live_arm"' in l:
            r = json.loads(l); arm[(r["w"], r["trig"]["mint"])] = r["trig"]["wallet"]
        elif '"presend_live_fill"' in l:
            r = json.loads(l)
            if r.get("after_exit"): continue
            fills.append(r)
    seen = set(); NCONS[run] = [len(fills), 0]
    # the live window of a fill: matched by mint and arm time (the run file's window ids restart in a24)
    bym = collections.defaultdict(list)
    for x in Z["meta"]["live"]: bym[x["mint"]].append((x["t_ns"], x["w"]))
    for r in fills:
        cand = [(t, w_) for t, w_ in bym.get(r["mint"], []) if t <= r["t"] and lv[w_]["filled"]]
        if not cand: continue
        w = max(cand)[1]
        if w in seen: continue
        seen.add(w)
        d = tab_for(r["slot"])
        if d is None: continue
        tp, keep, idm = tab(d, True)
        c = classify(tp, keep, idm, r["mint"], r["slot"], r["idx"], r["lim"], arm.get((r["w"], r["mint"])))
        if c is None: continue
        c.update(run=run, w=w, mint=r["mint"], slot=r["slot"], pnl=(lv[w]["pnl"] + lv[w].get("rb", 0)) / 1e6); NCONS[run][1] += 1
        L.append(c)
P("# Fake-dump fills: who pushed the price to our limit (crossing sell), and what those fills earned")
table(f"LIVE pre-send fills (MEASURED), AMS r24-r33 + FRA r26, {len(L)} fills classified", L)
by = collections.defaultdict(lambda: collections.Counter())
for x in L: by[x["run"]][x["cls"]] += 1
P("Per run (armed_whale / whale / small / round_trip / no_crossing): " + "; ".join(f"{r} {c['armed_whale']}/{c['whale']}/{c['small']}/{c['round_trip']}/{c['no_crossing']}" for r, c in by.items()))
P("Considered per run: " + str(NCONS))
ex = [x for x in L if x["cls"] == "round_trip" and x["rt_same"]][:6]
P("Round-trip examples (live): " + "; ".join(f"{x['run']} w{x['w']} {x['mint']} slot {x['slot']} seller {x['seller'][:8]} {x['pct']:.1f}% P&L {x['pnl']:+.1f} mSOL" for x in ex))
# ---- replay re-arm fills
R = []
fills = {}; sells = {}
for l in open(f"{OUT}/decisions.jsonl"):
    if '"kind":"fill"' in l: r = json.loads(l); fills[r["win"]] = r
    elif '"kind":"sell"' in l: r = json.loads(l); sells[r["win"]] = r
for wid, r in fills.items():
    tp, keep, idm = tab(r["day"], False)
    c = classify(tp, keep, idm, r["mint"], r["slot"], r["idx"], r["lim_px"])
    if c is None: continue
    c.update(pnl=sells[wid]["pnl_model_sol"] * 1e3, on_next=r["on_next_dump"])
    R.append(c)
table(f"REPLAY re-arm fills (INFERRED), any:20:30:8:2, D1-D6, {len(R)} fills", R)
pickle.dump(dict(live=L, replay=R), open(f"{OUT}/r13.pkl", "wb"))
open(f"{OUT}/r13.txt", "w").write("\n".join(Lo) + "\n")
