"""REGIME step 5: per-run tables (20 live + 9 PAPER) for the key rules, r38 from 03:24, and the after-drop base rate (INFERRED r38
continuation). usage: rg5_tables.py"""
import sys, pickle, json, collections, datetime as dt
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/regime")
import rg_lib as G
import rg2_core as C
import importlib.util
OUT = "/home/moiz/sniper-data/prevent/regime"
D = pickle.load(open(f"{OUT}/runs.pkl", "rb"))
live, paper = D["live"], D["paper"]
spec = importlib.util.spec_from_file_location("L4", "/home/moiz/sniper/ops/strategies/presend/prevent/regime/rg4_locks_signals.py")
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    L4 = importlib.util.module_from_spec(spec); spec.loader.exec_module(L4)   # computes signals on live/paper copies it loads itself
live4, paper4 = L4.live, L4.paper
rules = {r.name: r for r in C.mk_rules()}
KEY = ["C2 SL exit -> pause 5m", "C1 big loss -> pause 10m", "C3 2 big in 15m -> pause 15m", "C4 5 losses in a row -> pause 10m",
       "C5 15m P&L < -0.25 -> pause 15m", "C6 10m P&L < -0.35 -> pause 15m"]
S5cut = {t: L4.cuts["S5"][t] for t in (0.1, 0.2)}
def s5skip(tail):
    thr = S5cut[tail]
    return lambda run, w: (w["sig"]["S5"] is not None and w["sig"]["S5"] < thr)
T0R38 = dt.datetime(2026, 10, 30, 3, 24, tzinfo=G.PKT).timestamp()
lines = []
def P(s=""):
    print(s); lines.append(s)

P("== per-run saving (scaled to 0.696 SOL, + = rule kept more than no rule). LIVE runs then PAPER (shadow row c, age>=2)")
cols = []
for k in KEY:
    cols.append((k.split(" -> ")[0][:2] + " " + k.split(" ", 1)[1][:22], lambda runs, n, k=k: C.score({n: runs[n]}, rules[k])[n]["save"], "rule"))
cols.append(("S5 low 10%", lambda runs, n: C.score({n: runs[n]}, None, s5skip(0.1))[n]["save"], "sig"))
cols.append(("S5 low 20%", lambda runs, n: C.score({n: runs[n]}, None, s5skip(0.2))[n]["save"], "sig"))
lk = {nm: kw for nm, kw in L4.LOCKS}
for nm in ("L1 stop, give-back 0.65 (live)", "L2 0.65 -> pause 30m, resume", "L3 15m drop > 0.50 -> pause 30m"):
    cols.append((nm[:18], lambda runs, n, nm=nm: L4.lock_replay(runs[n], **lk[nm])[0] - L4.lock_replay(runs[n], "none")[0], "lock"))
hdr = f"{'run':9s} {'trades':>6s} {'net':>7s} | " + " | ".join(f"{c[0][:14]:>14s}" for c in cols)
P(hdr)
tot = collections.defaultdict(float)
for group, runs, names in (("LIVE", live4, G.LIVE_ORDER), ("PAPER", paper4, list(paper4))):
    for n in names:
        r = runs[n]
        net = sum(-w["fee"] + (w["tr"]["v"] if w["tr"] else 0) for w in r["wins"])
        vals = [f(runs, n) for _, f, _ in cols]
        for (c, _, _), v in zip(cols, vals):
            tot[(group, c)] += v
        P(f"{('P ' if group == 'PAPER' else '') + G.short(n):9s} {len(r['trades']):6d} {net:+7.3f} | " + " | ".join(f"{v:+14.3f}" for v in vals))
    P(f"{group + ' sum':9s} {'':6s} {'':7s} | " + " | ".join(f"{tot[(group, c)]:+14.3f}" for c, _, _ in cols))
    hh = []
    for c, f, _ in cols:
        vs = [f(runs, n) for n in names]
        hh.append(f"{sum(1 for v in vs if v > 1e-9)}/{sum(1 for v in vs if v < -1e-9)}")
    P(f"{group + ' h/h':9s} {'':6s} {'':7s} | " + " | ".join(f"{h:>14s}" for h in hh))
P()
P("== r38: what each rule would have done FROM 03:24 PKT (peak) to the 03:38 stop (scaled; real in brackets) and in r37")
r38 = live4["dip_ams_r38"]
for k in KEY + ["S5 low 10%", "S5 low 20%"]:
    if k.startswith("S5"):
        kept, sk = C.replay(r38, None, s5skip(0.1 if "10" in k else 0.2))
        kept2, sk2 = C.replay(r38, None, s5skip(0.1 if "10" in k else 0.2), real=True)
        r37s = C.score({"dip_ams_r37": live4["dip_ams_r37"]}, None, s5skip(0.1 if "10" in k else 0.2))["dip_ams_r37"]["save"]
    else:
        kept, sk = C.replay(r38, rules[k]); kept2, sk2 = C.replay(r38, rules[k], real=True)
        r37s = C.score({"dip_ams_r37": live4["dip_ams_r37"]}, rules[k])["dip_ams_r37"]["save"]
    late = [(v, tr, w) for v, tr, w in sk if w["t"] >= T0R38]
    late2 = [(v, tr, w) for v, tr, w in sk2 if w["t"] >= T0R38]
    early = [(v, tr, w) for v, tr, w in sk if w["t"] < T0R38]
    lt = [f"{G.pkt(tr['t'], '%H:%M')} {tr['kind'][:2]} {tr['vr']:+.3f}" for v, tr, w in late2 if tr is not None and abs(tr["vr"]) > 0.02]
    P(f"  {k:34s} r38 from 03:24: skipped {sum(1 for v,tr,w in late if tr)} trades, saved {-sum(v for v,tr,w in late):+.3f} [{-sum(v for v,tr,w in late2):+.3f} real]; before 03:24 saved {-sum(v for v,tr,w in early):+.3f} | r37 {r37s:+.3f}")
    if lt: P(f"      big skipped after 03:24: {', '.join(lt)}")
P()
P("== INFERRED r38 continuation: what came AFTER comparable drops in the 20 live runs (scaled SOL, the next 30/60/120 min)")
for X, W in ((0.4, 15), (0.5, 15), (0.65, 15)):
    ev = []
    for n in G.LIVE_ORDER:
        if n == "dip_ams_r38": continue
        r = live4[n]
        tr = sorted(r["trades"], key=lambda x: x["known"])
        cum = 0.0; hist = []; last = -1e18
        for x in tr:
            cum += x["v"]; hist.append((x["known"], cum))
            mx = max(c for t, c in hist if t >= x["known"] - W * 60)
            if cum < mx - X and x["known"] - last > 3600:
                last = x["known"]
                nxt = {}
                for H in (30, 60, 120):
                    if r["t1"] - x["known"] < H * 60:
                        nxt[H] = None; continue
                    nxt[H] = sum(-w["fee"] + (w["tr"]["v"] if w["tr"] else 0) for w in r["wins"] if x["known"] <= w["t"] < x["known"] + H * 60)
                ev.append((n, G.pkt(x["known"], "%m-%d %H:%M"), round(cum - mx, 3), nxt))
    P(f"  drop > {X} within {W} min: {len(ev)} events")
    for e in ev:
        P(f"     {G.short(e[0])} {e[1]} drop {e[2]:+.3f} -> next 30m {e[3][30] if e[3][30] is None else round(e[3][30],3)} | 60m {e[3][60] if e[3][60] is None else round(e[3][60],3)} | 120m {e[3][120] if e[3][120] is None else round(e[3][120],3)}")
    for H in (30, 60, 120):
        v = [e[3][H] for e in ev if e[3][H] is not None]
        if v: P(f"     mean next {H}m: {sum(v)/len(v):+.3f} (n {len(v)}, positive {sum(1 for z in v if z > 0)})")
# whole-run hourly base rate
hrs = []
for n in G.LIVE_ORDER:
    if n == "dip_ams_r38": continue
    r = live4[n]
    t = r["t0"]
    while t + 3600 <= r["t1"]:
        hrs.append(sum(-w["fee"] + (w["tr"]["v"] if w["tr"] else 0) for w in r["wins"] if t <= w["t"] < t + 3600)); t += 3600
P(f"  base rate, any full hour of the 19 other live runs: mean {sum(hrs)/len(hrs):+.3f} SOL/h (n {len(hrs)}, positive {sum(1 for h in hrs if h > 0)}), 03-05h PKT hours only: " +
  str([round(h, 3) for h in []]))
open(f"{OUT}/tables.txt", "w").write("\n".join(lines) + "\n")
