#!/usr/bin/env python3
"""VERIFY step 3: profit-lock replays on each live run's own P&L sequence (MEASURED trades; SCALED = INFERRED linear size scaling).
Event series: trade value at its sell landing + 2 s (lock polls every 2 s, 2-poll confirmation -> +4 s), failed-try fees at window arm.
Lock (engine dipmode.rs): floor = max(-0.5, peak - max(G, 0.3 x peak)); stop when the P&L is below the floor; peak = running max.
Variants: G in 0.65 / 0.8 / 1.0 / 1.5; series: real SOL, scaled 0.696 with the CORRECT fixed costs (mine) and with REGIME's formula."""
import pickle, collections, datetime as dt, json, sys
OUT = "/home/it/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb"))
PKT = dt.timezone(dt.timedelta(hours=5))
def pk(t): return dt.datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M")
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
EXTRA = ["A28", "A29", "A30", "A31", "A32", "A33"]
tr = collections.defaultdict(list); wn = collections.defaultdict(list)
for x in T["trades"]: tr[x["run"]].append(x)
for w in T["wins"]: wn[w["run"]].append(w)

def regime_scale(x):   # REGIME's formula: (pnl + 0.002) * 0.696 / spend - 0.002, rent refund unscaled
    return (x["pnl"] + 0.002) * 0.696 / x["spend"] - 0.002 + x["refund"]

def series(run, mode):
    ev = []
    for w in wn[run]:
        if w["wfee"]: ev.append((w["t"], -w["wfee"], None))
    for x in tr[run]:
        if mode == "real": v = x["unit"]
        elif mode == "scaled": v = x["s"] if x["kind"] == "t2" else x["unit"]     # re-arm (r38 only) stays at its real 0.65
        else: v = regime_scale(x) if x["kind"] == "t2" else x["unit"]
        ev.append((x["t_sell"] + 4.0, v, x))
    ev.sort(key=lambda e: e[0])
    return ev

def lock(ev, G, F=0.3, kill=-0.5):
    cum = 0.0; peak = 0.0; maxdd = 0.0
    for t, v, x in ev:
        cum += v; peak = max(peak, cum); maxdd = max(maxdd, peak - cum)
        floor = max(kill, peak - max(G, F * peak))
        if G is not None and cum < floor:
            return dict(t=t, at=cum, peak=peak, final=sum(e[1] for e in ev), kill=cum < kill + 1e-12 and kill >= peak - max(G, F * peak))
    return None

def maxdd(ev):
    cum = 0.0; peak = 0.0; md = 0.0; when = None; pk_ = 0.0
    for t, v, x in ev:
        cum += v
        if cum > peak: peak = cum
        if peak - cum > md: md = peak - cum; when = t; pk_ = peak
    return md, when, pk_

res = {}
lines = []
P = lines.append
for mode in ("real", "scaled", "regime"):
    P(f"== lock replay, series = {mode} ({'real SOL' if mode == 'real' else 'trade P&L scaled to 0.696; ' + ('fixed 3.524/2.010 mSOL, rent refund unscaled (verifier)' if mode == 'scaled' else 'REGIME formula FIX 2.0 mSOL')})")
    P(f"{'run':4s} {'final':>7s} {'maxDD':>6s} {'(peak)':>7s} | " + " | ".join(f"G {G:<4} trip @ P&L -> cost" for G in (0.65, 0.8, 1.0, 1.5)))
    tot = collections.Counter(); trips = collections.Counter()
    for run in ORDER + EXTRA:
        if run not in tr: continue
        ev = series(run, mode); fin = sum(e[1] for e in ev); md, mdt, mdp = maxdd(ev)
        row = f"{run:4s} {fin:+7.3f} {md:6.3f} ({mdp:+5.2f}) |"
        for G in (0.65, 0.8, 1.0, 1.5):
            L = lock(ev, G)
            if L is None: row += f" {'-':>27s} |"
            else:
                cost = L["at"] - fin
                row += f" {pk(L['t'])[6:]} {L['at']:+.2f} -> {cost:+.2f}{' K' if L['kill'] else '  '}   |"
                if run in ORDER and run not in ("A37", "A38"): tot[G] += cost; trips[G] += 1
            res.setdefault(mode, {}).setdefault(run, {})[str(G)] = None if L is None else dict(t=pk(L["t"]), at=round(L["at"], 4), cost=round(L["at"] - fin, 4), peak=round(L["peak"], 4))
        res[mode][run]["final"] = round(fin, 4); res[mode][run]["maxdd"] = round(md, 4); res[mode][run]["maxdd_peak"] = round(mdp, 4)
        P(row)
    P("  PICK (18 runs before r37) lock effect: " + ", ".join(f"G {G}: {tot[G]:+.3f} ({trips[G]} trips)" for G in (0.65, 0.8, 1.0, 1.5)))
    P("")

# after-drop: drops > X within 15 min (from the max of the last 15 min), events >= 1 h apart; next 30/60/120 min P&L (scaled)
P("== after a drop > X SOL within 15 min (scaled series, events >= 1 h apart), what the run made in the next 30/60/120 min")
drops = {}
for X in (0.4, 0.5):
    evs = []
    for run in ORDER:
        if run == "A38": continue
        ev = series(run, "scaled"); cum = 0.0; hist = []; last = -1e18
        tend = max(e[0] for e in ev)
        for i, (t, v, x) in enumerate(ev):
            cum += v; hist.append((t, cum))
            if x is None: continue
            mx = max(c for tt, c in hist if tt >= t - 900)
            if cum < mx - X and t - last > 3600:
                last = t; nx = {}
                for H in (30, 60, 120):
                    nx[H] = None if tend - t < H * 60 else round(sum(e[1] for e in ev if t < e[0] <= t + H * 60), 3)
                evs.append((run, pk(t), round(cum - mx, 3), nx))
    drops[X] = evs
    P(f"  X = {X}: {len(evs)} events")
    for e in evs: P(f"     {e[0]} {e[1]} drop {e[2]:+.3f} -> next 30m {e[3][30]} | 60m {e[3][60]} | 120m {e[3][120]}")
    for H in (30, 60, 120):
        v = [e[3][H] for e in evs if e[3][H] is not None]
        if v: P(f"     mean next {H}m {sum(v)/len(v):+.3f} (n {len(v)}, positive {sum(1 for z in v if z > 0)})")
# base rate: every full clock hour of the 19 other runs (scaled)
hrs = []
for run in ORDER:
    if run == "A38": continue
    ev = series(run, "scaled"); t0 = min(w["t"] for w in wn[run]); t1 = max(e[0] for e in ev); t = t0
    while t + 3600 <= t1:
        hrs.append(sum(e[1] for e in ev if t <= e[0] < t + 3600)); t += 3600
P(f"  base rate any full hour (19 runs, scaled): mean {sum(hrs)/len(hrs):+.3f} (n {len(hrs)}, positive {sum(1 for h in hrs if h > 0)})")
res["drops"] = {str(k): v for k, v in drops.items()}; res["hour_base"] = dict(mean=sum(hrs) / len(hrs), n=len(hrs), pos=sum(1 for h in hrs if h > 0))
# r38 detail (real): the trades from the peak, lock floor per G
P("")
P("== r38 real sequence from 03:15 PKT (cum = run P&L by my series)")
ev = series("A38", "real"); cum = 0.0; peak = 0.0
for t, v, x in ev:
    cum += v; peak = max(peak, cum)
    if x is not None and t >= ev[0][0] and pk(t)[6:] >= "03:15":
        P(f"   {pk(t)[6:]}  {x['kind']:5s} {x['mint'][:8]} {v:+.4f}  cum {cum:+.3f}  peak {peak:+.3f}  floor0.65 {max(-0.5, peak - max(0.65, 0.3*peak)):+.3f} floor1.0 {max(-0.5, peak - max(1.0, 0.3*peak)):+.3f}")
json.dump(res, open(f"{OUT}/locks.json", "w"), indent=1)
open(f"{OUT}/locks.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
