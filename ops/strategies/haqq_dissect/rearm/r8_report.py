#!/usr/bin/env python3
"""REARM step 8 (read-only; G2 continuation): the final tables from res_D<k>_<tag>.pkl (r4_days.py; several tags merged per day,
the 'base' of each tag is the same replay: same seed, same T2 list -> checked). All numbers INFERRED (replay) unless marked.
Levels (the task's calibration, from val.txt = MEASURED live vs replay on AMS r24-r33 + FRA r26, 740 live fills):
  model = replay as is;
  cal   = 0.81 x the added fill P&L (after per-fill tx costs) when it is > 0, failed-try fees x 1.00 (validated ratio 1.00);
          a NEGATIVE fill P&L is never shrunk (a factor < 1 would make a loss look smaller);
  cons  = the same with 0.46 (5th pct of the run bootstrap of live/replay net);
  addc  = cross-check: every fill - 1.49 mSOL (the pooled per-fill live - replay gap), fees x 1.00.
Costs per fill: NOW 2.015 mSOL (buy fee + 0.2 mSOL helius-ps tip + sell fee 0.605 + sell tips 1.2 + ATA close); S2 0.510 (sells ~0.3,
analyst D). Failed tries 5,120 lamports each. Exits: 'base' = live TP 10 % / SL 20 % / 2-slot; 'wave' = analyst C's wave exit.
ADDED = (base + re-arm) - base over every window, same draw (common random numbers): it includes the knock-on on today's T2 windows
(one position, rate caps, token blocks), so only NEW value counts.
usage: r8_report.py TAGS [--days 0..6] [--out r8.txt]"""
import sys, os, pickle, argparse, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = {"NOW": 5120 + 200_000 + 605_000 + 1_200_000 + 5020, "S2": 5120 + 200_000 + 300_000 + 5020}
FAIL = 5120
FAC = {"cal": 0.81, "cons": 0.46}
CAND = "0.02:50:120:2:0"


def vname(exit_, fol): return ("base" if fol == "" else "cut" + fol) if exit_ == "base" else "wave" + fol


def parts(rows, kind=None, exit_="base", fol="", cost="NOW"):
    """per armed window: (fill P&L lamports or None, fees lamports)"""
    v = vname(exit_, fol); out = []
    for r in rows:
        if kind and r[0][0] != kind: continue
        if not r[1]: continue
        pf = (r[8][2][v][0] - COST[cost]) if r[3] else None
        out.append((pf, r[4] * FAIL))
    return out


def tot(rows, **kw):
    p = parts(rows, **kw)
    f = [x[0] for x in p if x[0] is not None]
    return dict(n=len(p), f=len(f), w=sum(1 for x in f if x > 0), pf=sum(f) / 1e9, fee=sum(x[1] for x in p) / 1e9)


def level(pf, fee, nf, lvl):
    if lvl == "model": return pf - fee
    if lvl == "addc": return pf - nf * 1.49e-3 - fee
    return (FAC[lvl] * pf if pf > 0 else pf) - fee


def added(res, name, lvl="model", **kw):
    b = tot(res["base"], **kw); c = tot(res[name], **kw)
    d = {k: c[k] - b[k] for k in b}
    d["net"] = level(d["pf"], d["fee"], d["f"], lvl)
    return d


def boot_added(res, name, n=2000, seed=1, **kw):
    """90 % range of the ADDED model net: re windows resampled, the knock-on on T2 windows fixed"""
    re_ = parts(res[name], kind="re", **kw)
    if not re_: return (0.0, 0.0)
    k2 = tot(res[name], kind="t2", **kw); b2 = tot(res["base"], kind="t2", **kw)
    knock = (k2["pf"] - k2["fee"]) - (b2["pf"] - b2["fee"])
    v = np.array([(x[0] or 0) - x[1] for x in re_], float) / 1e9
    r = np.random.default_rng(seed)
    s = np.array([v[r.integers(0, len(v), len(v))].sum() for _ in range(n)]) + knock
    return np.percentile(s, 5), np.percentile(s, 95)


def load_day(d, tags):
    res = {}; meta = None
    for t in tags:
        fn = f"{OUT}/res_D{d}_{t}.pkl"
        if not os.path.exists(fn): continue
        Z = pickle.load(open(fn, "rb")); meta = meta or Z["meta"]
        for k, v in Z["out"].items():
            if k == "base" and "base" in res:
                if [r[3] for r in v[0]] != [r[3] for r in res["base"]]: print(f"WARNING D{d} {t}: base differs", flush=True)
                continue
            res[k] = v[0]
    return res if "base" in res else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("tags"); ap.add_argument("--days", default="0,1,2,3,4,5,6"); ap.add_argument("--out", default="r8.txt")
    A = ap.parse_args()
    tags = A.tags.split(","); days = [int(x) for x in A.days.split(",")]
    R = {d: load_day(d, tags) for d in days}; R = {d: r for d, r in R.items() if r}
    days = sorted(R)
    names = sorted({n for r in R.values() for n in r if n != "base"} & set.intersection(*[set(r) for r in R.values()]))
    Lout = []
    def P(s=""): print(s, flush=True); Lout.append(s)
    P(f"# RE-ARM, engine-faithful replay (rsim.run_x), tags {tags}, days {days}. All INFERRED; calibration factors MEASURED (val.txt).")
    P("Config = X (paid: r2 >= X SOL on a 0.40 buy; any = no check) : G (window slots) : A (max token age s at the paid dump) : K (tries per pace slot) : "
      "H (0 none; 1 a >= 6 % holder at dump+2; 2 = 1 + stop when no wallet holds >= 6 %)")
    P(f"Configs in every day: {len(names)}")
    # ---- 0. base
    P("\n## 0. Base = today's live pre-send replayed (k 8, 40/s, 0.40 SOL, QUIET stop 6:2), per day")
    P("| Day | T2 windows armed | Fills (wins) | Model net | Cal 0.81 | Failed-try fees |")
    P("|---|---|---|---|---|---|")
    for d in days:
        b = tot(R[d]["base"])
        P(f"| {L.day_name(d)} | {b['n']:,} | {b['f']} ({b['w']}) | {b['pf'] - b['fee']:+.2f} | {level(b['pf'], b['fee'], b['f'], 'cal'):+.2f} | {b['fee']:.3f} |")
    # ---- 1. A's candidate, fixed
    def day_rows(name, title):
        pick = name if isinstance(name, dict) else {d: name for d in days}
        P(f"\n## {title}")
        P("| Day | Config | Re windows armed | Re fills (wins) | Re P&L/fill model mSOL | Added fills | **Added model [90%]** | Cal 0.81 | Cons 0.46 | Addc -1.49/fill | Failed-try fees added | "
          "-10 % fol (cal) | -20 % fol (cal) | S2 costs (cal) | Wave exit (cal) | Wave + S2 (cal) | T2 knock-on (model) |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        S = collections.defaultdict(float)
        for d in days:
            res = R[d]; name = pick.get(d)
            if name is None or name not in res: continue
            re_ = tot(res[name], kind="re")
            a = {lv: added(res, name, lvl=lv) for lv in ("model", "cal", "cons", "addc")}
            lo, hi = boot_added(res, name)
            f10 = added(res, name, lvl="cal", fol="10")["net"]; f20 = added(res, name, lvl="cal", fol="20")["net"]
            s2 = added(res, name, lvl="cal", cost="S2")["net"]; wv = added(res, name, lvl="cal", exit_="wave")["net"]
            wv2 = added(res, name, lvl="cal", exit_="wave", cost="S2")["net"]
            k2 = tot(res[name], kind="t2"); b2 = tot(res["base"], kind="t2")
            knock = (k2["pf"] - k2["fee"]) - (b2["pf"] - b2["fee"])
            P(f"| {L.day_name(d)} | {name} | {re_['n']:,} | {re_['f']} ({re_['w']}) | {1e3 * re_['pf'] / max(re_['f'], 1):+.2f} | {a['model']['f']:+d} | **{a['model']['net']:+.2f}** [{lo:+.2f}, {hi:+.2f}] | "
              f"{a['cal']['net']:+.2f} | {a['cons']['net']:+.2f} | {a['addc']['net']:+.2f} | {a['model']['fee']:+.3f} | {f10:+.2f} | {f20:+.2f} | {s2:+.2f} | {wv:+.2f} | {wv2:+.2f} | {knock:+.2f} |")
            for k, v in (("model", a["model"]["net"]), ("cal", a["cal"]["net"]), ("cons", a["cons"]["net"]), ("addc", a["addc"]["net"]), ("f10", f10), ("f20", f20),
                         ("s2", s2), ("wv", wv), ("wv2", wv2), ("fills", a["model"]["f"]), ("fee", a["model"]["fee"])):
                S[k] += v
        P(f"\nSum over days: added fills {S['fills']:+.0f}, model {S['model']:+.2f}, cal {S['cal']:+.2f}, cons {S['cons']:+.2f}, addc {S['addc']:+.2f}, fees {S['fee']:+.3f}, "
          f"-10% {S['f10']:+.2f}, -20% {S['f20']:+.2f}, S2 {S['s2']:+.2f}, wave {S['wv']:+.2f}, wave+S2 {S['wv2']:+.2f} SOL")
        return S
    if CAND in names: day_rows(CAND, f"1. Analyst A's candidate {CAND} (paid >= +0.02 SOL, 50 slots, age <= 120 s, k 2), fixed, every day (ADDED vs base, SOL)")
    # ---- 2. walk-forward
    P("\n## 2. Walk-forward: the config is chosen on PAST days only (by ADDED model net, NOW costs, live exit), tested on the next day")
    P("WF-prev = best of the previous day, always on; WF-off = the same but OFF (added 0) when its past value <= 0; WF-exp = best over all past days (expanding), OFF when <= 0.")
    P("| Test day | WF-prev choice | added model | cal | cons | WF-off | WF-exp choice | WF-exp model | cal | cons | -10 % (cal) | -20 % | S2 (cal) | wave (cal) | wave+S2 (cal) | fees added |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    WF = collections.defaultdict(float); chosen = {}
    for d in days[1:]:
        past = [x for x in days if x < d]
        v1 = {n: added(R[past[-1]], n)["net"] for n in names}
        b1 = max(v1, key=v1.get)
        ve = {n: sum(added(R[x], n)["net"] for x in past) for n in names}
        be = max(ve, key=ve.get)
        res = R[d]
        a1 = {lv: added(res, b1, lvl=lv)["net"] for lv in ("model", "cal", "cons")}
        woff = a1["model"] if v1[b1] > 0 else 0.0
        on = ve[be] > 0
        ae = {lv: (added(res, be, lvl=lv)["net"] if on else 0.0) for lv in ("model", "cal", "cons")}
        ex = {k: (added(res, be, lvl="cal", **kw)["net"] if on else 0.0) for k, kw in (("f10", dict(fol="10")), ("f20", dict(fol="20")), ("s2", dict(cost="S2")),
                                                                                       ("wv", dict(exit_="wave")), ("wv2", dict(exit_="wave", cost="S2")))}
        fee = added(res, be)["fee"] if on else 0.0
        chosen[d] = be if on else None
        P(f"| {L.day_name(d)} | {b1} ({v1[b1]:+.2f}) | {a1['model']:+.2f} | {a1['cal']:+.2f} | {a1['cons']:+.2f} | {woff:+.2f} | {be if on else 'OFF'} ({ve[be]:+.2f}) | "
          f"**{ae['model']:+.2f}** | {ae['cal']:+.2f} | {ae['cons']:+.2f} | {ex['f10']:+.2f} | {ex['f20']:+.2f} | {ex['s2']:+.2f} | {ex['wv']:+.2f} | {ex['wv2']:+.2f} | {fee:+.3f} |")
        for k, v in (("p_model", a1["model"]), ("p_cal", a1["cal"]), ("p_cons", a1["cons"]), ("off", woff), ("e_model", ae["model"]), ("e_cal", ae["cal"]), ("e_cons", ae["cons"])): WF[k] += v
        for k, v in ex.items(): WF["e_" + k] += v
    P(f"\nSum of test days: WF-prev model {WF['p_model']:+.2f} / cal {WF['p_cal']:+.2f} / cons {WF['p_cons']:+.2f}; WF-off model {WF['off']:+.2f}; "
      f"WF-exp model {WF['e_model']:+.2f} / cal {WF['e_cal']:+.2f} / cons {WF['e_cons']:+.2f}; WF-exp cal: -10% {WF['e_f10']:+.2f}, -20% {WF['e_f20']:+.2f}, S2 {WF['e_s2']:+.2f}, "
      f"wave {WF['e_wv']:+.2f}, wave+S2 {WF['e_wv2']:+.2f}")
    json.dump({str(k): v for k, v in chosen.items()}, open(f"{OUT}/r8_chosen.json", "w"))
    # ---- 3. every config: sum and days > 0
    P("\n## 3. Every config over all days (ADDED model / cal, NOW, live exit; wave exit cal; in-sample, for the map)")
    P("| Config | Days > 0 (model) | Sum model | Sum cal | Sum cons | Sum wave (cal) | Sum wave+S2 (cal) | Re fills | Re P&L/fill model mSOL | Added fees |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    rowsC = []
    for n in names:
        vs = [added(R[d], n)["net"] for d in days]
        rf = sum(tot(R[d][n], kind="re")["f"] for d in days); rp = sum(tot(R[d][n], kind="re")["pf"] for d in days)
        rowsC.append((sum(vs), n, sum(x > 0 for x in vs), sum(added(R[d], n, lvl="cal")["net"] for d in days), sum(added(R[d], n, lvl="cons")["net"] for d in days),
                      sum(added(R[d], n, lvl="cal", exit_="wave")["net"] for d in days), sum(added(R[d], n, lvl="cal", exit_="wave", cost="S2")["net"] for d in days),
                      rf, 1e3 * rp / max(rf, 1), sum(added(R[d], n)["fee"] for d in days)))
    for s, n, pos, c, cs, wv, wv2, rf, pp, fe in sorted(rowsC, reverse=True):
        P(f"| {n} | {pos} of {len(days)} | {s:+.2f} | {c:+.2f} | {cs:+.2f} | {wv:+.2f} | {wv2:+.2f} | {rf:,} | {pp:+.2f} | {fe:+.3f} |")
    best = max(rowsC)[1]
    day_rows(best, f"4. The best config over all days (in-sample, an upper bound): {best}")
    wf = {d: c for d, c in chosen.items() if c}
    if wf:
        day_rows(wf, "5. Per test day, the WF-exp choice (out-of-sample; ADDED vs base, SOL)")
        # 6. exits: the re-arm's value under each exit, the wave exit alone, both vs today
        P("\n## 6. Exit combination on the test days (WF-exp choice; cal 0.81; NOW costs unless S2): re-arm alone / wave exit alone / both, each vs today's base with the live 2-slot exit")
        P("| Test day | Re-arm (2-slot exit) | Wave exit alone | Re-arm + wave | Re-arm + wave + S2 | Re-arm added under the wave exit | Rate-capped tries base / with re-arm |")
        P("|---|---|---|---|---|---|---|")
        T = collections.defaultdict(float)
        for d, c in sorted(wf.items()):
            res = R[d]
            def net(rows, exit_, cost):
                t = tot(rows, exit_=exit_, cost=cost); return t
            b0 = net(res["base"], "base", "NOW")
            def vs(rows, exit_, cost):
                t = net(rows, exit_, cost); dpf = t["pf"] - b0["pf"]; dfe = t["fee"] - b0["fee"]
                return level(dpf, dfe, t["f"] - b0["f"], "cal")
            a1 = vs(res[c], "base", "NOW"); a2 = vs(res["base"], "wave", "NOW"); a3 = vs(res[c], "wave", "NOW"); a4 = vs(res[c], "wave", "S2")
            a5 = added(res, c, lvl="cal", exit_="wave")["net"]
            rb = sum(r[6] for r in res["base"] if r[1]); sb = sum(r[5] for r in res["base"] if r[1])
            rc = sum(r[6] for r in res[c] if r[1]); sc = sum(r[5] for r in res[c] if r[1])
            P(f"| {L.day_name(d)} | {a1:+.2f} | {a2:+.2f} | {a3:+.2f} | {a4:+.2f} | {a5:+.2f} | {100 * rb / max(rb + sb, 1):.1f}% / {100 * rc / max(rc + sc, 1):.1f}% |")
            for k, v in (("a1", a1), ("a2", a2), ("a3", a3), ("a4", a4), ("a5", a5)): T[k] += v
        P(f"\nSum: re-arm {T['a1']:+.2f}, wave alone {T['a2']:+.2f}, both {T['a3']:+.2f}, both + S2 {T['a4']:+.2f}, re-arm under wave {T['a5']:+.2f} SOL")
    open(f"{OUT}/{A.out}", "w").write("\n".join(Lout) + "\n")
