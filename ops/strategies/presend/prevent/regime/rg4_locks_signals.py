"""REGIME step 4: task 4 (profit-lock variants) and task 3 (market-wide regime signals) on the live runs (+ PAPER for signals).
usage: rg4_locks_signals.py"""
import sys, pickle, json, collections, bisect, heapq, random
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/prevent/regime")
import rg_lib as G
import rg2_core as C

OUT = "/home/it/sniper-data/prevent/regime"
D = pickle.load(open(f"{OUT}/runs.pkl", "rb"))
live, paper = D["live"], D["paper"]
PICK, TEST, R38, ALL = G.PICK, G.TEST, ["dip_ams_r38"], G.LIVE_ORDER


# ------------------------------------------------------------- locks
def lock_replay(run, kind, G_=0.65, K=None, X=None, real=False, kill=-0.5, kinds=None):
    """kind: none | stop | pause | roll. Returns (final P&L, stop/pause events, skipped values, peak)."""
    cum = 0.0; peak = 0.0; stopped = False; pause_until = -1.0; events = []; skipped = []
    pend = []; hist = collections.deque()       # (t, cum) for the rolling lock
    for i, w in enumerate(run["wins"]):
        ta = w["t"]
        while pend and pend[0][0] <= ta:
            kn, _, v = heapq.heappop(pend)
            cum += v; peak = max(peak, cum); hist.append((kn, cum))
            if cum < kill and not stopped:
                stopped = True; events.append(("kill", kn, cum))
            if stopped or kn < pause_until:
                continue
            if kind == "stop" and peak > 0 and cum < peak - max(G_, 0.3 * peak):
                stopped = True; events.append(("stop", kn, cum))
            elif kind == "pause" and peak > 0 and cum < peak - max(G_, 0.3 * peak):
                pause_until = kn + K * 60; events.append(("pause", kn, cum)); peak = cum   # resume with the peak reset
            elif kind == "roll":
                while hist and hist[0][0] < kn - 900: hist.popleft()
                mx = max(c for t, c in hist) if hist else cum
                if cum < mx - X:
                    pause_until = kn + K * 60; events.append(("pause", kn, cum)); hist.clear()
        tr = w["tr"]
        if kinds is not None and w["kind"] not in kinds:
            continue
        val = -w["fee"] + ((tr["vr"] if real else tr["v"]) if tr else 0.0)
        if stopped or ta < pause_until:
            skipped.append((val, tr, w)); continue
        cum += -w["fee"]
        if tr:
            heapq.heappush(pend, (tr["known"], i, val + w["fee"]))
    while pend:
        kn, _, v = heapq.heappop(pend); cum += v
    return cum, events, skipped, peak


LOCKS = [("no lock (kill -0.5 only)", dict(kind="none")),
         ("L1 stop, give-back 0.65 (live)", dict(kind="stop", G_=0.65)), ("L1 stop, give-back 1.0", dict(kind="stop", G_=1.0)),
         ("L1 stop, give-back 1.5", dict(kind="stop", G_=1.5)),
         ("L2 0.65 -> pause 30m, resume", dict(kind="pause", G_=0.65, K=30)), ("L2 0.65 -> pause 60m, resume", dict(kind="pause", G_=0.65, K=60)),
         ("L2 1.0 -> pause 30m, resume", dict(kind="pause", G_=1.0, K=30)), ("L2 1.0 -> pause 60m, resume", dict(kind="pause", G_=1.0, K=60)),
         ("L3 15m drop > 0.40 -> pause 30m", dict(kind="roll", X=0.40, K=30)), ("L3 15m drop > 0.40 -> pause 60m", dict(kind="roll", X=0.40, K=60)),
         ("L3 15m drop > 0.50 -> pause 30m", dict(kind="roll", X=0.50, K=30)), ("L3 15m drop > 0.50 -> pause 60m", dict(kind="roll", X=0.50, K=60)),
         ("L3 15m drop > 0.65 -> pause 30m", dict(kind="roll", X=0.65, K=30)), ("L3 15m drop > 0.65 -> pause 60m", dict(kind="roll", X=0.65, K=60))]


def lock_table(real=False):
    base = {n: lock_replay(live[n], "none", real=real)[0] for n in ALL}
    rows = []
    for name, kw in LOCKS:
        per = {}; ev = {}; sk = {}
        for n in ALL:
            fin, events, skipped, peak = lock_replay(live[n], real=real, **kw)
            per[n] = fin - base[n]; ev[n] = events; sk[n] = skipped
        tops = sorted([-v for n in PICK + TEST for v, tr, w in sk[n] if tr is not None and v < 0], reverse=True)
        s_pt = sum(per[n] for n in PICK + TEST)
        rows.append(dict(name=name, per=per, events={n: [(e, G.pkt(t, "%H:%M"), round(c, 3)) for e, t, c in ev[n]] for n in ALL},
                         pick=sum(per[n] for n in PICK), test=per["dip_ams_r37"], r38=per["dip_ams_r38"],
                         help=sum(1 for n in PICK if per[n] > 1e-9), hurt=sum(1 for n in PICK if per[n] < -1e-9),
                         wo1=s_pt - (tops[0] if tops else 0), wo5=s_pt - sum(tops[:5]), n_trips=sum(len(ev[n]) for n in ALL)))
    return base, rows


print("== TASK 4. profit-lock variants vs no lock (scaled to 0.696 SOL; + = the lock kept more)")
base, rows = lock_table(False)
print(f"  {'variant':34s} {'PICK':>7s} {'h/h':>5s} {'r37':>7s} {'r38*':>7s} {'w/o1':>6s} {'w/o5':>6s} trips  where")
for r in rows:
    trips = "; ".join(f"{G.short(n)} {e[0][0]} {e[0][1]}" for n, e in r["events"].items() if e)[:150]
    print(f"  {r['name']:34s} {r['pick']:+7.3f} {r['help']:2d}/{r['hurt']:<2d} {r['test']:+7.3f} {r['r38']:+7.3f} {r['wo1']:+6.2f} {r['wo5']:+6.2f} {r['n_trips']:4d}  {trips}")
print("  * r38 stops at 03:38 in the data (the live lock): its sequence after 03:38 is unknown, so r38 savings only cover 01:59-03:38")
baseR, rowsR = lock_table(True)
print("  REAL SOL (unscaled) for r36/r37/r38, locks that tripped:")
for r in rowsR:
    if any(r["events"][n] for n in ("dip_ams_r36", "dip_ams_r37", "dip_ams_r38")):
        print(f"   {r['name']:34s} " + " | ".join(f"{G.short(n)} {r['per'][n]:+.3f} {r['events'][n][:2]}" for n in ("dip_ams_r36", "dip_ams_r37", "dip_ams_r38")))
# r38: separate re-arm lock (re-arm trades only, give-back X of the re-arm P&L)
r38 = live["dip_ams_r38"]
cum = {"t2": 0.0, "rearm": 0.0}; pk = {"t2": 0.0, "rearm": 0.0}; first = {}
for tr in sorted(r38["trades"], key=lambda x: x["known"]):
    k = tr["kind"]; cum[k] += tr["vr"]; pk[k] = max(pk[k], cum[k])
    for X in (0.2, 0.3, 0.4):
        if (k, X) not in first and cum[k] < pk[k] - X:
            first[(k, X)] = (G.pkt(tr["known"], "%H:%M:%S"), round(cum[k], 3), round(pk[k], 3))
print("  r38 per-kind running P&L (REAL, trades + rent, no try fees): first time each kind fell X below its own peak:")
for (k, X), v in sorted(first.items()):
    print(f"    {k:5s} X {X}: at {v[0]} P&L {v[1]:+.3f} (peak {v[2]:+.3f})")

# ------------------------------------------------------------- regime signals
def run_signals(run):
    o = run["o"]
    dumps = sorted(o["dumps"], key=lambda d: d[0])
    dt_ = [d[0] / 1e9 for d in dumps]
    big_t = [d[0] / 1e9 for d in dumps if (d[3] or 0) >= 12]
    # cascade: for each big dump, the time of a follow-up dump on the same mint within 2 slots
    by_m = collections.defaultdict(list)
    for d in dumps:
        by_m[d[1]].append(d)
    casc = []   # (t_dump, t_followup or None)
    for m, ds in by_m.items():
        for i, d in enumerate(ds):
            if (d[3] or 0) < 12: continue
            fu = None
            for e in ds[i + 1:]:
                if e[2] is None or d[2] is None: break
                if e[2] - d[2] > 2: break
                if e[0] > d[0]: fu = e[0] / 1e9; break
            casc.append((d[0] / 1e9, fu))
    casc.sort()
    ct = [c[0] for c in casc]
    sh_t = sorted(a["t"] / 1e9 for a in o["sh_arms"] if a["t"])
    sx = sorted((x["t"] / 1e9, x["pnl"], x["why"]) for x in o["sh_exits"] if x["row"] == "c" and x.get("t") and x["pnl"] is not None)
    sxt = [x[0] for x in sx]
    def sig(ta):
        s1 = bisect.bisect_left(dt_, ta) - bisect.bisect_left(dt_, ta - 900)
        s2 = bisect.bisect_left(big_t, ta) - bisect.bisect_left(big_t, ta - 900)
        lo, hi = bisect.bisect_left(ct, ta - 1800), bisect.bisect_left(ct, ta - 1.0)
        n = hi - lo; k = sum(1 for c in casc[lo:hi] if c[1] is not None and c[1] <= ta)
        s3 = k / n if n >= 5 else None
        s4 = bisect.bisect_left(sh_t, ta) - bisect.bisect_left(sh_t, ta - 900)
        a, b = bisect.bisect_left(sxt, ta - 1800), bisect.bisect_left(sxt, ta)
        ex = sx[a:b]
        s5 = sum(x[1] for x in ex) if ex else 0.0
        s6 = (sum(1 for x in ex if x[2] == "sl") / len(ex)) if len(ex) >= 5 else None
        return dict(S1=s1, S2=s2, S3=s3, S4=s4, S5=s5, S6=s6)
    for w in run["wins"]:
        w["sig"] = sig(w["t"])


for n in ALL:
    run_signals(live[n])
for n in paper:
    run_signals(paper[n])

print()
print("== TASK 3. market-wide regime signals: P&L of trades by signal quintile (PICK pooled cuts; scaled mSOL/trade, n)")
SIGS = ["S1", "S2", "S3", "S4", "S5", "S6"]
cuts = {}
for s in SIGS:
    vals = sorted(w["sig"][s] for n in PICK for w in live[n]["wins"] if w["sig"][s] is not None)
    cuts[s] = {q: vals[min(len(vals) - 1, int(q * len(vals)))] for q in (0.1, 0.2, 0.33, 0.5, 0.67, 0.8, 0.9)}
    qs = [vals[int(len(vals) * k / 5)] for k in range(1, 5)]
    line = []
    for nm, names in (("PICK", PICK), ("r37", TEST), ("r38", R38)):
        bins = collections.defaultdict(list)
        for n in names:
            for w in live[n]["wins"]:
                v = w["sig"][s]
                if v is None or w["tr"] is None: continue
                bins[bisect.bisect_right(qs, v)].append(w["tr"]["v"] - w["fee"])
        line.append(f"{nm}: " + " ".join(f"q{b+1} {1000*sum(x)/len(x):+5.1f}({len(x)})" for b, x in sorted(bins.items())))
    print(f"  {s} cuts {['%.3g' % q for q in qs]} | " + " | ".join(line))

print()
print("== TASK 3b. signal pause rules (skip windows while the signal is in its bad tail; scaled SOL saved)")
srows = []
for s, dirs in (("S1", ("hi", "lo")), ("S2", ("hi", "lo")), ("S3", ("hi",)), ("S4", ("hi", "lo")), ("S5", ("lo",)), ("S6", ("hi",))):
    for d in dirs:
        for tail in (0.10, 0.20, 0.33):
            thr = cuts[s][round(1 - tail, 2)] if d == "hi" else cuts[s][tail]
            def skip(run, w, s=s, d=d, thr=thr):
                v = w["sig"][s]
                if v is None: return False
                return v > thr if d == "hi" else v < thr
            res = C.score(live, None, skip)
            pk = C.summarize(res, PICK); ts = C.summarize(res, TEST); r8 = C.summarize(res, R38); b = C.summarize(res, PICK + TEST)
            ci = C.boot_ci(res, PICK + TEST)
            pres = C.score(paper, None, skip); pp = C.summarize(pres, list(paper))
            nsk = sum(res[n]["n_skip"] for n in PICK + TEST); nw = sum(len(live[n]["wins"]) for n in PICK + TEST)
            srows.append(dict(rule=f"{s} {d} tail {int(tail*100)}% (thr {thr:.3g})", fam=s, pick=pk, test=ts, r38=r8, both=b, ci=ci,
                              skipshare=nsk / nw, paper=pp, per_run={n: res[n]["save"] for n in ALL}, paper_per_run={n: pres[n]["save"] for n in paper}))
candS = {}
for fam in SIGS:
    ok = [r for r in srows if r["fam"] == fam and r["pick"]["help"] > r["pick"]["hurt"]]
    if ok: candS[fam] = max(ok, key=lambda r: r["pick"]["save"])["rule"]
for r in srows:
    r["cand"] = candS.get(r["fam"]) == r["rule"]
    pk, ts = r["pick"], r["test"]
    passes = ts["save"] > 0 and pk["help"] > pk["hurt"] and r["ci"][0] > 0 and r["both"]["wo1"] > 0 and r["both"]["win_sol"] <= r["both"]["los_sol"]
    lead = ts["save"] > 0 and pk["save"] > 0 and pk["help"] > pk["hurt"]
    r["verdict"] = ("PASS" if passes else "LEAD" if lead else "FAIL") if r["cand"] else ("(pass)" if passes else "-")
print(f"  {'rule':34s} {'PICK':>7s} {'h/h':>6s} {'r37':>7s} {'r38':>7s} {'P+T CI90':>15s} {'w/o1':>6s} {'w/o5':>6s} {'skipW/L':>11s} {'skip%':>6s} {'PAPER':>6s} verdict")
for r in srows:
    pk, ts, r8, b = r["pick"], r["test"], r["r38"], r["both"]
    print(f"  {r['rule']:34s} {pk['save']:+7.3f} {pk['help']:2d}/{pk['hurt']:<2d} {ts['save']:+7.3f} {r8['save']:+7.3f} {r['ci'][0]:+6.2f}..{r['ci'][1]:+6.2f} {b['wo1']:+6.2f} {b['wo5']:+6.2f} {b['win_sol']:5.2f}/{b['los_sol']:<5.2f} {r['skipshare']:6.1%} {r['paper']['save']:+6.2f} {'*' if r['cand'] else ' '}{r['verdict']}")
# r38 signal values around the crash
print()
print("  r38 signals at window arms (15-min means):")
r38w = live["dip_ams_r38"]["wins"]
b = collections.defaultdict(list)
for w in r38w:
    b[int((w["t"] - r38w[0]["t"]) // 900)].append(w)
for k, ws in sorted(b.items()):
    m = lambda s: [w["sig"][s] for w in ws if w["sig"][s] is not None]
    avg = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    tv = sum(w["tr"]["vr"] for w in ws if w["tr"]) - sum(w["fee"] for w in ws)
    print(f"   {G.pkt(ws[0]['t'], '%H:%M')} wins {len(ws):3d} P&L {tv:+.3f} | " + " ".join(f"{s} {avg(m(s)):.3g}" for s in SIGS))
json.dump(dict(locks=rows, locks_real=rowsR, lock_base=base, signals=srows, sig_cuts=cuts, sig_cands=candS), open(f"{OUT}/locks_signals.json", "w"), indent=1, default=str)
