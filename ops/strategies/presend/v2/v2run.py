#!/usr/bin/env python3
# PRE-SEND V2 options study driver (read-only). TRAIN = R1 + R2 (10-22 03:07 -> 10-23 18:19 PKT, 36.6 h): every choice is made
# there. TEST = R3 + R4 (10-23 19:26 -> 10-25 09:56 PKT, 38.2 h; R4 holds the live probe hour and the FRA shadow morning).
# Leader filters: R1 (epoch 1064) has no local schedule -> they are chosen on R2 only.
# Sections:
#  1 one-option-at-a-time tables around the BASE (= the probe's config at the calibrated landing, but 0.55 SOL):
#    T2 (htype 3, holding >= 5%, no create-slot trigger), W 10, y 0.12, L4 (4 attempts per slot, calibrated), 0.55 SOL,
#    exit c2_tp10_sl20, all leaders, 1 server (one position), real costs;
#  2 selection on TRAIN per family (T2 / CD / T1t) and attempt rate; the chosen configs on TEST;
#  3 robustness of the finalists: per day, per PKT hour band, worst hour, hour-block bootstrap, without the top 1% of fills.
# usage: nice python3 v2run.py [procs] -> presend_v2/v2run.json + v2run.txt
import sys, os, json, itertools, time
import numpy as np
from multiprocessing import get_context
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
import v2eng as E
OUT = f"{V.OUT}/v2run"
TRAIN = ("R1", "R2"); TEST = ("R3", "R4")
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
G = {}
CLS = {k: i for i, k in enumerate(V.CLS)}
LEAD = {"all": None, "bam": {CLS["bam"]}, "no_jito": {CLS["bam"], CLS["harmonic"], CLS["fd"], CLS["agave"], CLS["rakurai"]},
        "no_harm": {CLS["bam"], CLS["jito"], CLS["fd"], CLS["agave"], CLS["rakurai"]},
        "no_jito_harm": {CLS["bam"], CLS["fd"], CLS["agave"], CLS["rakurai"]}, "bam_fd": {CLS["bam"], CLS["fd"]}}

def fmask(D, spec):
    f = lambda k: E.wf(D, k); fam = spec["fam"]
    if fam == "T2":
        m = (D["w_fam"] == 0) & (f("htype") == spec.get("htype", 3)) & (f("hpct") >= spec.get("hmin", 5.0))
        if not spec.get("cslot", False): m &= f("cslot") == 0
        if spec.get("tool", False): m &= (f("tool_n") == 0) & (f("trig_rebuy") == 0)
        if spec.get("age_max"): m &= f("age_s") <= spec["age_max"]
        if spec.get("hmax"): m &= f("hpct") < spec["hmax"]
    elif fam == "CD":
        m = (D["w_fam"] == 1) & (f("cre_nprev") >= spec["nprev"])
        if spec.get("early"): m &= f("cre_early") >= spec["early"]
        if spec.get("big"): m &= f("cre_big") >= spec["big"]
        if spec.get("tool", False): m &= f("tool_n") == 0
    elif fam == "T1t":
        m = (D["w_fam"] == 2) & (f("drop") >= 4.65) & (f("sell_sol") >= spec.get("sell_min", 1.08))
        if spec.get("tool", False): m &= f("tool_n") == 0
    return m

def ev(cfg, days, detail=False):
    """cfg: spec, W, y, row, size, ex, end_cre, lead, servers, cost -> per day dict"""
    out = {}
    for d in days:
        D = G["DD"][d]
        o = E.run(D, fmask(D, cfg["spec"]), cfg.get("W", 10), cfg.get("y", 0.12), cfg.get("row", "L4"), cfg.get("size", 0.55), cfg.get("ex", "c2_tp10_sl20"),
                  end_cre=cfg.get("end_cre", False), servers=cfg.get("servers", 1), allowed=LEAD[cfg.get("lead", "all")], cost=cfg.get("cost", "real"),
                  detail=detail)
        o["per24"] = o["pnl"] / G["DD"][d]["hours"] * 24
        if detail: o["hourly"] = E.hourly(o, d)
        out[d] = o
    return out

def agg(r, days):
    h = sum(G["DD"][d]["hours"] for d in days); pnl = sum(r[d]["pnl"] for d in days); nf = sum(r[d]["fill"] for d in days)
    na = sum(r[d]["armed"] for d in days); att = sum(r[d]["att"] for d in days); gross = sum(r[d]["gross"] for d in days)
    return dict(per24=pnl / h * 24, fills24=nf / h * 24, per_fill=pnl / nf if nf else 0.0, gross_fill=gross / nf if nf else 0.0, fill_rate=nf / max(na, 1),
                att_fill=att / nf if nf else float("inf"), pnl=pnl, fills=nf, min_day=min(r[d]["per24"] for d in days))

def line(cfg, tag):
    r = ev(cfg, V.DAYS)
    tr = agg(r, TRAIN); te = agg(r, TEST)
    say(f"  {tag:34s} TRAIN {tr['per24']:+6.2f}/d ({tr['fills24']:5.0f} fills/d, {tr['per_fill']:+.4f}/fill) | TEST {te['per24']:+6.2f}/d ({te['fills24']:5.0f} f/d, "
        f"{te['per_fill']:+.4f}/fill, fill rate {100 * te['fill_rate']:4.1f}%, att/fill {te['att_fill']:5.0f}) | per day " + " ".join(f"{d} {r[d]['per24']:+6.2f}" for d in V.DAYS))
    return dict(cfg=cfg, train=tr, test=te, days={d: r[d]["per24"] for d in V.DAYS}, fills={d: r[d]["fill"] for d in V.DAYS})

BASE = dict(spec=dict(fam="T2"), W=10, y=0.12, row="L4", size=0.55, ex="c2_tp10_sl20", lead="all", servers=1, cost="real")
def mod(**kw):
    c = json.loads(json.dumps(BASE)); c.update(kw); return c

def work_sel(cfg):
    r = ev(cfg, V.DAYS)
    return cfg, {d: (r[d]["pnl"], r[d]["fill"], r[d]["armed"], r[d]["att"], r[d]["gross"]) for d in V.DAYS}

if __name__ == "__main__":
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    T0 = time.time()
    G["DD"] = {d: E.load(d) for d in V.DAYS}
    say(f"PRE-SEND V2 options | TRAIN {TRAIN} ({sum(G['DD'][d]['hours'] for d in TRAIN):.1f} h) | TEST {TEST} ({sum(G['DD'][d]['hours'] for d in TEST):.1f} h) | "
        f"windows {', '.join(f'{d} {V.WIN[d][0]}-{V.WIN[d][1]}' for d in V.DAYS)} PKT | SOL per 24 h, net of ALL costs (real = probe-measured)")
    RES = {"sec1": {}, "sec2": {}}
    # ---------------------------------------------------------------- section 1
    say("\n(1) ONE OPTION AT A TIME around the BASE (T2 no create-slot, W 10, y 12%, L4 = 4/slot calibrated, 0.55 SOL, c2_tp10_sl20, all leaders, 1 server, real costs)")
    S1 = RES["sec1"]
    S1["base"] = line(BASE, "BASE")
    say(" (b) size");
    for sz in (0.2, 0.35, 0.55, 1.0): S1[f"size{sz}"] = line(mod(size=sz), f"size {sz}")
    say(" (e) attempt rate (calibrated landing; P = the probe's 3.79/slot) and the study's rows")
    for row in ("P", "L2", "L4", "L8", "L12", "L20", "c", "r4"): S1[f"row{row}"] = line(mod(row=row), f"row {row} (k {E.KROW[row]:g})")
    say(" (f) deadline +2 (attempts live up to 2 slots)")
    for row in ("L4d2", "L8d2"): S1[f"row{row}"] = line(mod(row=row), f"row {row}")
    say(" (f) limit drop y")
    for y in (0.08, 0.12, 0.16): S1[f"y{y}"] = line(mod(y=y), f"y {y}")
    say(" (f) exits")
    for ex in ("c1_tpnone_slnone", "c2_tpnone_slnone", "c2_tp10_sl20", "c2_tp5_sl10", "c2_tp15_sl20", "c3_tp10_sl20", "c4_tp10_sl20", "c4_tpnone_sl20", "c3_tp5_slnone"):
        S1[f"ex{ex}"] = line(mod(ex=ex), f"exit {ex}")
    say(" (a) seller-tool tokens skipped (no tool rebuy seen on the token before the trigger, the trigger is not a rebuy)")
    S1["tool"] = line(mod(spec=dict(fam="T2", tool=True)), "skip seller-tool tokens")
    say(" (c) leader filters (R1 has no schedule: its column is 0 when filtered; read R2 / R3 / R4)")
    for ld in LEAD: S1[f"lead{ld}"] = line(mod(lead=ld), f"leaders {ld}")
    say(" (d) triggers")
    S1["t2cslot"] = line(mod(spec=dict(fam="T2", cslot=True)), "T2 incl. create-slot triggers")
    S1["t2h8"] = line(mod(spec=dict(fam="T2", hmin=8.0)), "T2 holding >= 8%")
    S1["t2w5"] = line(mod(W=5), "T2 window 5 slots")
    S1["t2w20"] = line(mod(W=20), "T2 window 20 slots")
    for npv, early, big, W, ec in ((3, 0.8, 0, 25, False), (5, 0.9, 0, 25, False), (5, 0.9, 0, 50, True), (10, 0.9, 0, 25, False), (5, 0, 0.8, 25, False),
                                   (3, 0, 0.5, 25, True), (10, 0, 0.8, 50, True)):
        S1[f"cd{npv}_{early}_{big}_{W}_{ec}"] = line(mod(spec=dict(fam="CD", nprev=npv, early=early, big=big), W=W, end_cre=ec),
                                                    f"CD prev>={npv} early>={early} big>={big} W{W}{' endcre' if ec else ''}")
    S1["t1t"] = line(mod(spec=dict(fam="T1t"), W=5), "T1t (study: >=4.65% dump, serial, W5)")
    say(" (g) servers")
    S1["srv2"] = line(mod(servers=2), "2 servers (one position each)")
    say(" costs")
    S1["cheapsell"] = line(mod(cost="cheapsell"), "cheap sell (one 0.0002 tip, low priority)")
    S1["study"] = line(mod(cost="study"), "the study's cheap costs")
    json.dump(RES, open(OUT + ".json", "w"), default=float)
    open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
    # ---------------------------------------------------------------- section 2: selection on TRAIN
    say(f"\n(2) SELECTION on TRAIN only ({time.time() - T0:.0f} s)")
    EXS = E.EXN
    cfgs = []
    for row in ("L2", "L4", "L8", "L12", "L20", "L4d2", "L8d2"):
        for cs, tool, hmin in itertools.product((False, True), (False, True), (5.0, 8.0)):
            for y, size, ex in itertools.product((0.08, 0.12, 0.16), (0.35, 0.55, 1.0), EXS):
                cfgs.append(dict(spec=dict(fam="T2", cslot=cs, tool=tool, hmin=hmin), W=10, y=y, row=row, size=size, ex=ex, lead="all", servers=1, cost="real"))
        for npv, q, W, ec in itertools.product((3, 5, 10), (("early", 0.8), ("early", 0.9), ("big", 0.5), ("big", 0.8)), (25, 50), (False, True)):
            for y, size, ex in itertools.product((0.08, 0.12, 0.16), (0.35, 0.55, 1.0), ("c1_tpnone_slnone", "c2_tpnone_slnone", "c2_tp10_sl20", "c2_tp10_sl10", "c3_tp10_sl20", "c4_tp10_sl20")):
                sp = dict(fam="CD", nprev=npv); sp[q[0]] = q[1]
                cfgs.append(dict(spec=sp, W=W, end_cre=ec, y=y, row=row, size=size, ex=ex, lead="all", servers=1, cost="real"))
        for sm, W in itertools.product((0.0, 1.08), (5, 10, 25)):
            for y, size, ex in itertools.product((0.08, 0.12, 0.16), (0.35, 0.55, 1.0), ("c2_tpnone_slnone", "c2_tp10_sl20", "c2_tp10_sl10", "c3_tp10_sl20", "c6_tp10_sl20" if False else "c4_tp10_sl20")):
                cfgs.append(dict(spec=dict(fam="T1t", sell_min=sm), W=W, y=y, row=row, size=size, ex=ex, lead="all", servers=1, cost="real"))
    say(f"  {len(cfgs)} configs x 4 days")
    R = []
    with get_context("fork").Pool(procs) as p:
        for k, r in enumerate(p.imap_unordered(work_sel, cfgs, chunksize=64)):
            R.append(r)
            if (k + 1) % 20000 == 0: say(f"    {k + 1}/{len(cfgs)} {time.time() - T0:.0f} s")
    hr = {d: G["DD"][d]["hours"] for d in V.DAYS}
    def tr_score(v):
        p = [v[d][0] for d in TRAIN]; h = sum(hr[d] for d in TRAIN); nf = sum(v[d][1] for d in TRAIN)
        return sum(p) / h * 24, nf / h * 24, min(v[d][0] / hr[d] * 24 for d in TRAIN)
    best = {}
    for cfg, v in R:
        fam = cfg["spec"]["fam"]; key = f"{fam}|{cfg['row']}"
        s, fpd, mn = tr_score(v)
        if fpd < 20 or mn <= 0: continue
        if key not in best or s > best[key][0]: best[key] = (s, cfg, v)
    S2 = RES["sec2"]
    for key in sorted(best):
        s, cfg, v = best[key]
        te_p = sum(v[d][0] for d in TEST); te_h = sum(hr[d] for d in TEST); te_f = sum(v[d][1] for d in TEST)
        S2[key] = dict(cfg=cfg, train24=s, test24=te_p / te_h * 24, test_fills24=te_f / te_h * 24, test_per_fill=te_p / te_f if te_f else 0.0,
                       days={d: v[d][0] / hr[d] * 24 for d in V.DAYS})
        say(f"  {key:10s} TRAIN {s:+6.2f}/d -> TEST {S2[key]['test24']:+6.2f}/d ({S2[key]['test_fills24']:5.0f} fills/d, {S2[key]['test_per_fill']:+.4f}/fill) | "
            + " ".join(f"{d} {S2[key]['days'][d]:+6.2f}" for d in V.DAYS) + f" | {json.dumps(cfg['spec'])} W {cfg.get('W')} endcre {cfg.get('end_cre', False)} y {cfg['y']} size {cfg['size']} {cfg['ex']}")
    # keep every config's per-day numbers compactly for later sections
    np.save(OUT + "_all.npy", np.array([[v[d][i] for d in V.DAYS for i in range(5)] for _, v in R], np.float64))
    json.dump([c for c, _ in R], open(OUT + "_cfgs.json", "w"))
    json.dump(RES, open(OUT + ".json", "w"), default=float)
    open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
    say(f"done {time.time() - T0:.0f} s")
