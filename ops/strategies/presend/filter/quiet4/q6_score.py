#!/usr/bin/env python3
"""QUIET4 step 6: score the QUIET family against the CURRENT setting (all 4 signals, fol 4.0, no follower-bot list, hist 24 h, stop 5:2,
min age 2) on the 24 earlier runs (PICK, real outcomes; frozen) and on r37 (TEST, fresh): gain = sum over triggers of
value(rule) - value(current), SOL at 0.696. Tightening on r37 = exact live P&L; loosening on r37 = the calibrated phantom model.
Grid: fol 2.24 / 3 / 4 / 5 / 6 x k-of-4 (4 / 3 / 2) x follower bots (none / frozen list) x hist 24 / 12 / 6 h x stop (3..8):2, (4..8):3
x min age 1 / 2 / 3 x v2 (off / 5th condition). Pre-registered pick: best PICK SOL/day with PICK w/o top 5 > 0 and >= 15 changed fills.
Out: /home/it/sniper-data/presend_quiet4/score.json, score_out.md"""
import sys, json, itertools, collections, random
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filter/quiet4")
import q6data as Q6

D4 = Q6.D4
rows, HOURS = Q6.build(); rows = Q6.values(rows)
n = len(rows)
src = np.array([r["src"] for r in rows]); kind = np.array([r["kind"] for r in rows])
PICK = src == "e"; TEST = src == "r37"
key = np.array([r["key"] for r in rows]); night = np.array([r["night"] for r in rows])
since1 = np.array([r["since"] >= 1 for r in rows]); coh0 = np.array([r["coh"] == 0 for r in rows]); fb2 = np.array([r["fb"] < 2 for r in rows])
WF = {24: np.array([r["wf24"] for r in rows]), 12: np.array([r["wf12"] for r in rows]), 6: np.array([r["wf6"] for r in rows])}
age = np.array([r["age"] if r["age"] is not None else 99 for r in rows]); v2s = np.array([r["v2skip"] for r in rows])
isfill = np.array([r["isfill"] for r in rows]); win = np.array([r["win"] for r in rows])
VAL = {S: np.array([r["val"][S] for r in rows]) for S in Q6.STOPS}
VALC = {S: np.array([(np.nan if r["valc"][S] is None else r["valc"][S]) for r in rows]) for S in Q6.STOPS}
CENS = {S: np.array([r["cens"][S] for r in rows]) for S in Q6.STOPS}
# model fills of r37 virtual rows (expected), live fills elsewhere
FILLS = {S: np.array([(r["vals"][(S, 0.0)][1] if r["src"] == "r37" else (1.0 if r["isfill"] else 0.0)) for r in rows]) for S in Q6.STOPS}
block = np.array([f"{r['key']}|{int(r['t'] // 3_600_000_000_000)}" for r in rows])
# blocked r37 rows: arm only when their blocker is skipped (the first blocked trigger of a blocker only)
idx_of = {r["wkey"]: i for i, r in enumerate(rows) if r["src"] == "r37" and r["kind"] == "armed"}
blk = np.array([idx_of.get(r.get("blocker"), -1) if r["kind"] == "blocked" else -1 for r in rows])
first_blk = np.zeros(n, bool); seen = set()
for i in sorted(np.nonzero(kind == "blocked")[0].tolist(), key=lambda i: rows[i]["t"]):
    if blk[i] >= 0 and blk[i] not in seen: first_blk[i] = True; seen.add(blk[i])
HP = sum(h for k, h in HOURS.items() if k != "r37AMS"); HT = HOURS["r37AMS"]
# r37 blocked_armed triggers (a window was armed on the mint) arm only when their blocker is skipped: modelled, and the PICK runs have
# no such rows, so they stay blocked unless --blocked (then reported as a side result)
USE_BLOCKED = "--blocked" in sys.argv
CUTKEYS = {"r34AMS", "r35AMS", "r36AMS", "r26FRA", "r27FRA", "r28FRA"}
HC = sum(HOURS[k] for k in CUTKEYS)


def armed(R):
    fl = [since1, coh0, (fb2 if R["fb"] else np.ones(n, bool)), WF[R["H"]] < R["F"]]
    q = (fl[0].astype(int) + fl[1] + fl[2] + fl[3]) >= R["k"]
    if R["v2"] == "and": q = q & v2s
    a = (age >= R["A"]) & ~q
    if USE_BLOCKED: a = np.where(kind == "blocked", a & first_blk & (blk >= 0) & ~np.where(blk >= 0, a[np.maximum(blk, 0)], True), a)
    else: a = np.where(kind == "blocked", False, a)
    return a


CURA = armed(Q6.CUR); CURU = np.where(CURA, VAL[Q6.CUR["S"]], 0.0); CURUC = np.where(CURA, VALC[Q6.CUR["S"]], 0.0)


def diff(R):
    a = armed(R)
    u = np.where(a, VAL[R["S"]], 0.0); uc = np.where(a, VALC[R["S"]], 0.0)
    return a, u - CURU, uc - CURUC


def name(R):
    s = f"{'all-4' if R['k'] == 4 else str(R['k']) + '-of-4'} fol<{R['F']:g} fb{'=frozen' if R['fb'] else '=none'} h{R['H']} stop {R['S'][0]}:{R['S'][1]} age>={R['A']}"
    return s + (" +v2" if R["v2"] else "")


def stats(R, mask, hrs, boot=False, d=None):
    a, dv, dc = diff(R) if d is None else d
    m = mask
    g = dv[m]; G = float(g.sum())
    ch = ((a != CURA) | (np.abs(dv) > 1e-9)) & m
    nf = float(np.sum(np.where(ch, np.maximum(FILLS[R["S"]], FILLS[Q6.CUR["S"]]), 0)))
    top = np.sort(g)[::-1]; wo5 = G - float(np.sum(top[:5][top[:5] > 0]))
    per = collections.defaultdict(float)
    for k_, v in zip(key[m], g): per[k_] += v
    help_ = sum(1 for v in per.values() if v > 0.0005); hurt = sum(1 for v in per.values() if v < -0.0005)
    ng = float(g[night[m]].sum())
    cm = m & np.isin(key, list(CUTKEYS | {"r37AMS"}))
    gc = dc[cm]; GC = float(np.nansum(gc)); hc = (HC if hrs != HT else 0) + (HT if np.any(cm & TEST) else 0)
    cens_armed = int(np.sum(a & (kind == "cens") & m)) + int(np.sum(a & m & (src == "e") & CENS[R["S"]] & (kind != "cens")))
    out = dict(G=G, day=G / hrs * 24, wo5=wo5, help=help_, hurt=hurt, night=ng, dayg=G - ng, nf=nf, cut=GC, cutday=(GC / hc * 24) if hc else 0.0, cens=cens_armed,
               skipped_more=int(np.sum(~a & CURA & m)), armed_more=int(np.sum(a & ~CURA & m)))
    if boot:
        bl = block[m]; ub, inv = np.unique(bl, return_inverse=True); bs = np.bincount(inv, weights=g, minlength=len(ub))
        rng = np.random.default_rng(1); B = np.array([bs[rng.integers(0, len(ub), len(ub))].sum() for _ in range(2000)])
        out["ci"] = (float(np.percentile(B, 5)) / hrs * 24, float(np.percentile(B, 95)) / hrs * 24)
    return out


def fmt(nm, s):
    ci = s.get("ci", (np.nan, np.nan))
    return (f"| {nm} | {s['skipped_more']}/{s['armed_more']} | {s['nf']:.0f} | {s['G']:+.3f} | {s['day']:+.2f} | [{ci[0]:+.2f},{ci[1]:+.2f}] | {s['wo5']:+.3f} | "
            f"{s['cutday']:+.2f} | {s['help']}/{s['hurt']} | {s['dayg']:+.3f}/{s['night']:+.3f} | {s['cens']} |")


HDR = ("| rule | arms skipped more / armed more | fills changed | net SOL | SOL/day @0.696 | CI90 /day | w/o top 5 | -20% fol. /day* | runs help/hurt | day/night SOL | censored arms |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")
out = []


def pr(s=""): out.append(s); print(s, flush=True)


def main():
    pr(f"rows: pick {int(PICK.sum())} (armed {int(np.sum(PICK & (kind == 'armed')))}, censored {int(np.sum(kind == 'cens'))}; {HP:.1f} h, 24 runs) | "
       f"test r37 {int(TEST.sum())} ({dict(collections.Counter(kind[TEST]))}; {HT:.1f} h)")
    pr(f"current rule: pick value {CURU[PICK].sum():+.3f} SOL ({CURU[PICK].sum() / HP * 24:+.2f}/day) | r37 value {CURU[TEST].sum():+.3f} ({CURU[TEST].sum() / HT * 24:+.2f}/day; live armed {sum(r['v'] for r in rows if r['src'] == 'r37' and r['kind'] == 'armed'):+.3f})")
    pr("(* -20% followers: replay runs only = AMS r34-r36, FRA r26-r28 for PICK; r37 for TEST)")
    pr(f"r37 blocked_armed triggers {'ARM when their blocker is skipped (modelled)' if USE_BLOCKED else 'stay blocked (not modelled in PICK either; see --blocked run)'}")
    # ---- one factor at a time
    pr("\n## A. One change at a time (vs current; PICK = 24 earlier runs, TEST = r37)\n" + HDR.replace("| rule |", "| change | set |").replace("|---|", "|---|---|", 1))
    C = dict(Q6.CUR)
    single = [("fol", "F", v) for v in (2.24, 3.0, 5.0, 6.0)] + [("k-of-4", "k", v) for v in (3, 2)] + [("follower bots frozen", "fb", True)] + \
             [("hist-h", "H", v) for v in (12, 6)] + [("min age", "A", v) for v in (1, 3)] + [("v2 as 5th condition", "v2", "and")]
    res_single = []
    for lab, f, v in single:
        R = dict(C); R[f] = v
        sp = stats(R, PICK, HP, boot=True); st = stats(R, TEST, HT, boot=True)
        nm = f"{lab} {v if not isinstance(v, tuple) else str(v[0]) + ':' + str(v[1])}"
        pr(fmt(nm + " | PICK", sp)); pr(fmt(nm + " | r37", st))
        res_single.append((nm, R, sp, st))
    pr("\n## A2. What the current parts are worth (current vs the part switched OFF; + = the part helps)\n| part | PICK: arms it skips that traded live / their value (real) | PICK help/hurt runs | r37 skipped arms / value (model) | r37 value at -20% (model) |\n|---|---|---|---|---|")
    for lab, R in (("QUIET arm rule (all 4, fol 4.0, no bot list)", dict(Q6.CUR, k=5)), ("age-1 skip (min age 2), after QUIET", dict(Q6.CUR, A=1))):
        a, dv, dc = diff(R)
        mP = PICK & (kind == "armed") & a & ~CURA; mT = TEST & a & ~CURA
        per = collections.defaultdict(float)
        for k_, v in zip(key[mP], dv[mP]): per[k_] += v
        pr(f"| {lab} | {int(mP.sum())} / {-dv[mP].sum():+.3f} ({-dv[mP].sum() / HP * 24:+.2f}/day) | {sum(1 for v in per.values() if v < -0.0005)}/{sum(1 for v in per.values() if v > 0.0005)} | "
           f"{int(mT.sum())} / {-dv[mT].sum():+.3f} ({-dv[mT].sum() / HT * 24:+.2f}/day) | {-np.nansum(dc[mT]):+.3f} |")
    pr("\nr37 split of the A rows: EXACT part (armed windows the rule skips: live P&L) | MODEL part (skipped windows the rule arms: phantom model)")
    for nm, R, sp, st in res_single:
        a, dv, dc = diff(R)
        ex = dv[TEST & CURA & ~a].sum(); mo = dv[TEST & ~CURA & a].sum()
        pr(f"  {nm}: exact {ex:+.3f} ({int(np.sum(TEST & CURA & ~a))} arms, {int(np.sum(TEST & CURA & ~a & isfill))} live fills) | model {mo:+.3f} ({int(np.sum(TEST & ~CURA & a))} arms)")
    # ---- the stop rule: PICK split by method (paired replay on the 6 runs with pickles; quiet3 stopgain shortcut on the other 18)
    REPL = np.array([r.get("stop_src") == "replay" for r in rows])
    HR = sum(HOURS[k] for k in CUTKEYS); HA = HP - HR
    pr("\n## S. Stop rule N:M (vs 5:2; same arm rule). PICK-replay = AMS r34-r36 + FRA r26-r28 (30.7 h, paired try-level replay at each run's own config); "
       "PICK-shortcut = the other 18 earlier runs (quiet3 stopgain on the per-slot counts; it disagrees with the replay on r37); r37 = replay\n"
       "| stop | PICK-replay net / day | w/o top 5 | -20% /day | runs +/- | PICK-shortcut net / day | r37 net / day | r37 CI90 /day | r37 w/o top 5 | r37 -20% /day | r37 day/night |\n|---|---|---|---|---|---|---|---|---|---|---|")
    res_stop = []
    for S in Q6.STOPS:
        if S == (5, 2): continue
        R = dict(Q6.CUR, S=S); d = diff(R)
        a_ = stats(R, PICK & REPL, HR, d=d); b_ = stats(R, PICK & ~REPL, HA, d=d); t_ = stats(R, TEST, HT, boot=True, d=d)
        pr(f"| {S[0]}:{S[1]} | {a_['G']:+.3f} / {a_['day']:+.2f} | {a_['wo5']:+.3f} | {a_['cutday']:+.2f} | {a_['help']}/{a_['hurt']} | {b_['G']:+.3f} / {b_['day']:+.2f} | "
           f"{t_['G']:+.3f} / {t_['day']:+.2f} | [{t_['ci'][0]:+.2f},{t_['ci'][1]:+.2f}] | {t_['wo5']:+.3f} | {t_['cutday']:+.2f} | {t_['dayg']:+.3f}/{t_['night']:+.3f} |")
        res_stop.append((S, a_, b_, t_))
    # ---- the arm-rule grid at stop 5:2
    grid = []
    for F, k, fb, H, A, v2 in itertools.product((2.24, 3.0, 4.0, 5.0, 6.0), (4, 3, 2), (False, True), (24, 12, 6), (1, 2, 3), (None, "and")):
        R = dict(F=F, k=k, fb=fb, H=H, S=(5, 2), A=A, v2=v2)
        d = diff(R)
        sp = stats(R, PICK, HP, d=d); st = stats(R, TEST, HT, d=d); sa = stats(R, np.ones(n, bool), HP + HT, d=d)
        grid.append((R, sp, st, sa))
    pr(f"\ngrid (arm rule x min age x v2, stop 5:2): {len(grid)} rules")
    elig = [g for g in grid if g[1]["wo5"] > 0 and g[1]["nf"] >= 15 and g[1]["G"] > 0]
    elig.sort(key=lambda g: -g[1]["day"])
    pr(f"{len(elig)} rules beat current on PICK with w/o top 5 > 0 and >= 15 changed fills")
    pr("\n## B. PICK top 15 by SOL/day (24 earlier runs; frozen) and their r37 test (every rule, eligible or not, marked)\n" + HDR.replace("| rule |", "| rule (set) |"))
    gp = sorted(grid, key=lambda g: -g[1]["day"])
    for R, sp, st, sa in gp[:15]:
        tag = " [eligible]" if (sp["wo5"] > 0 and sp["nf"] >= 15 and sp["G"] > 0) else ""
        pr(fmt(name(R) + tag + " (PICK)", stats(R, PICK, HP, boot=True))); pr(fmt(name(R) + " (r37)", stats(R, TEST, HT, boot=True)))
    pick = elig[0][0] if elig else None
    pr(f"\nPRE-REGISTERED PICK (best PICK SOL/day, PICK w/o top 5 > 0, >= 15 changed fills): {name(pick) if pick else 'none -> current stays'}")
    if pick:
        pr(fmt(name(pick) + " (r37 TEST)", stats(pick, TEST, HT, boot=True)))
    # ---- best on all 25 runs
    grid.sort(key=lambda g: -g[3]["day"])
    pr("\n## C. Best on ALL 25 runs (r37 included; SOL/day over all hours), top 12\n" + HDR.replace("| rule |", "| rule (set) |"))
    for R, sp, st, sa in grid[:12]:
        pr(fmt(name(R) + " (all 25)", stats(R, np.ones(n, bool), HP + HT, boot=True)))
        pr(fmt(name(R) + " (PICK)", stats(R, PICK, HP, boot=True))); pr(fmt(name(R) + " (r37)", stats(R, TEST, HT, boot=True)))
    # ---- candidates passing every bar
    pr("\n## D. Rules positive on PICK and on r37, w/o top 5 > 0 on both, -20% followers > 0 on both (PICK: replay runs; r37)")
    ok = [g for g in grid if g[1]["G"] > 0 and g[2]["G"] > 0 and g[1]["wo5"] > 0 and g[2]["wo5"] > 0 and g[1]["cut"] > 0 and g[2]["cut"] > 0 and g[1]["nf"] >= 5]
    ok.sort(key=lambda g: -g[3]["day"])
    pr(f"{len(ok)} of {len(grid)} pass\n" + HDR.replace("| rule |", "| rule (set) |"))
    for R, sp, st, sa in ok[:20]:
        pr(fmt(name(R) + " (PICK)", stats(R, PICK, HP, boot=True))); pr(fmt(name(R) + " (r37)", stats(R, TEST, HT, boot=True)))
    json.dump({"pick": pick, "ok": [g[0] for g in ok[:50]], "grid_top_all": [g[0] for g in grid[:50]], "elig_top": [g[0] for g in elig[:50]]},
              open(f"{D4}/score.json", "w"), default=str)
    open(f"{D4}/score_out.md", "w").write("\n".join(out))


if __name__ == "__main__":
    main()
