#!/usr/bin/env python3
"""FLAT study, IDEA A evaluation (read-only, offline): the hold variants of prereg.py on one or more runs.
Per run: the baseline's kept windows (prereg 'primary': dev with QUIET replayed; or 'asrun'); the positions whose time exit was
decided while the engine had seen no other wallet's trade (eng_flat) get the variant's exit (a_core.walk); every other position
is unchanged. Side cost of a longer hold (one_position): the live tries of other kept windows sent inside the extra hold are not
sent (fees saved; a fill among them is lost with its live net); a kept window on the same token armed inside the extra hold
(+300 ms margin) is blocked (its whole score lost); reactive fires inside it are counted (blocked).
Per position gain = (variant score - live score) + its side cost. Results: /home/moiz/sniper-data/presend_flat/a_<tag>.json
usage: a_eval.py --runs r24 r25 r26 [--mode primary|asrun] [--variants all|frozen] [--lims FILE] [--tag dev]"""
import sys, json, argparse, collections, pickle
import numpy as np
import flatlib as FL, evalcore as EC, a_core as AC, prereg as PR

MARGIN_NS = 300_000_000


def side_effects(P, r, kept_tries, kept_windows, fires, run):
    """the live events inside the extra hold of this position (wall clock): (dropped tries [(window, try k)], blocked windows, fires)"""
    d_ms = r["a_sell"] - P["cc_sell"]
    if d_ms <= 0 or P["t_sell"] is None: return [], [], []
    t0 = P["t_sell"]; t1 = t0 + d_ms * 1e6
    me = (P["w"]["seg"], P["w"]["w"])
    dt = [(key, k) for (key, k, t) in kept_tries if key != me and t0 < t <= t1]
    bw = [key for key, w in kept_windows.items() if key != me and w["mint"] == P["w"]["mint"] and t0 < w["t"] <= t1 + MARGIN_NS]
    fz = [f for f in fires if f["t"] is not None and t0 < f["t"] <= t1]
    return dt, bw, fz


def eval_run(C, O, run, mode, variants, d_react, lims=None):
    B = FL.load_base(run)
    W = B["W"]
    bskip, bstops = EC.base_cfg(run, mode)
    base = {}; kept_windows = {}; kept_tries = []
    for w in W:
        b = EC.run_rules(w, O, skip=bskip(w), stops=bstops)
        key = (w["seg"], w["w"]); base[key] = b
        if b["skipped"]: continue
        kept_windows[key] = w
        for k, t in enumerate(w["tries"]):
            if b["stop_k"] is None or k < b["stop_k"]: kept_tries.append((key, k, t["t"]))
    pos = []
    for w in W:
        key = (w["seg"], w["w"])
        if not w["filled"] or not base[key]["fill_kept"] or not w.get("eng_flat"): continue
        P = AC.prep(C, w)
        if P is None: continue
        pos.append(P)
    res = {}
    for name, rule in variants:
        rows = []; sumd = collections.Counter()
        dropped_all = set(); blocked_all = set(); fires_all = set()
        for P in pos:
            r = AC.walk(P, rule, d_react, lims=lims)
            live = P["pnl"] + P["rb"]
            dt, bw, fz = side_effects(P, r, kept_tries, kept_windows, B["fires"], run)
            side = 0; lost_fill = []; fees_saved = 0
            for (key, k) in dt:
                if (key, k) in dropped_all: continue
                dropped_all.add((key, k))
                ww = kept_windows[key]; t = ww["tries"][k]
                if t["fill"]:
                    side -= ww["net"]; lost_fill.append((key, ww["net"]))
                else:
                    side += t["fee"]; fees_saved += t["fee"]
            for key in bw:
                if key in blocked_all: continue
                blocked_all.add(key)
                side -= base[key]["score"]
            for f in fz: fires_all.add((f["t"], f["mint"]))
            g = (r["score"] - live) + side
            rows.append(dict(mint=P["w"]["mint"], t=P["w"]["t"], flat=P["w"]["flat"], live=live, cf=r["score"], why=r["why"], hold_ms=r["a_sell"] - P["cc_sell"],
                             side=side, lost_fills=lost_fill, fees_saved=fees_saved, blocked=len(bw), fires=len(fz), gain=g, dropped_followers=r["dropped"],
                             our_blocked=len(r["blocked"]), first_other=(r["first_other"]["s"] - P["land"]) if r["first_other"] else None))
        res[name] = rows
    return dict(run=run, n_pos=len(pos), res=res, n_fills_kept=sum(1 for w in W if w["filled"] and base[(w["seg"], w["w"])]["fill_kept"]),
                n_flat_kept=sum(1 for w in W if w["filled"] and base[(w["seg"], w["w"])]["fill_kept"] and w.get("flat")))


def vname(kind, p):
    return f"{kind}(" + ",".join(f"{k}={v}" for k, v in p.items()) + ")"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True); ap.add_argument("--mode", default="primary"); ap.add_argument("--variants", default="all")
    ap.add_argument("--lims"); ap.add_argument("--tag", default="dev")
    A = ap.parse_args()
    dl = json.load(open(f"{FL.D}/a_delays.json")); d_react = dl["d_react_median"]
    if A.variants == "all":
        variants = [(vname(k, p), dict(p)) for k, p in PR.GRID_A]
    else:
        F = json.load(open("/home/moiz/sniper/ops/strategies/presend/flat/FROZEN.json"))
        variants = [(F["A"]["name"], F["A"]["rule"])]
    for _, rule in variants:
        rule.setdefault("K", None); rule.setdefault("X", None)
    lims = None
    if A.lims:
        lims = {}
        for l in open(A.lims):
            x = json.loads(l); lims[x["sig"]] = tuple(x["lim"]) if x.get("lim") else None
        lims = {k: v for k, v in lims.items() if v}
    phases = sorted(set(p for r in A.runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); O = EC.Others(C)
    out = {}
    for run in A.runs:
        out[run] = eval_run(C, O, run, A.mode, variants, d_react, lims)
        print(f"{run}: kept fills {out[run]['n_fills_kept']}, kept flats {out[run]['n_flat_kept']}, affected positions (engine-flat at the exit) {out[run]['n_pos']}", flush=True)
    json.dump(dict(mode=A.mode, d_react=d_react, runs=A.runs, out=out), open(f"{FL.D}/a_{A.tag}_{A.mode}.json", "w"))
    # table
    print(f"\n{'variant':24s} " + " ".join(f"{r:>22s}" for r in A.runs) + f" {'TOTAL':>9s}  winners(cf>0) worse  side(SOL) lost-fills blocked fires")
    for name, _ in variants:
        cells = []; tot = 0; nw = 0; nworse = 0; side = 0; lf = 0; bl = 0; fz = 0
        for run in A.runs:
            rows = out[run]["res"][name]
            g = sum(x["gain"] for x in rows) / 1e9; tot += g
            cells.append(f"{g:+.4f} ({sum(x['live'] for x in rows)/1e9:+.3f}->{sum(x['cf'] for x in rows)/1e9 + sum(x['side'] for x in rows)/1e9:+.3f})")
            nw += sum(1 for x in rows if x["cf"] > 0); nworse += sum(1 for x in rows if x["cf"] < x["live"])
            side += sum(x["side"] for x in rows) / 1e9; lf += sum(len(x["lost_fills"]) for x in rows); bl += sum(x["blocked"] for x in rows); fz += sum(x["fires"] for x in rows)
        print(f"{name:24s} " + " ".join(f"{c:>22s}" for c in cells) + f" {tot:+9.4f}  {nw:5d} {nworse:5d}  {side:+.4f} {lf:3d} {bl:3d} {fz:3d}")


if __name__ == "__main__":
    main()
