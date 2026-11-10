#!/usr/bin/env python3
"""PAPER AUDIT step 4 [MEASURED tape + live records; the port is validated 1815/1815 fills exact]: the shadow vs LIVE on the live-armed
T2 windows. Per window: the live outcome (fill yes/no, landing position, realized, sell position) and the port's rows at landing delays D
(the engine's rows a / b / c = 0 / 5 / 10 ms, plus 2 / 20 / 40) on the tape WITH our trades (as the engine) and WITHOUT them (clean),
P&L at the live size 0.696 SOL under three exits: E2 = the shadow's (75 ms into fill slot + 2, block-position clock), EL = the live sell's
own landing position (live-filled windows), ECC = fill landing + H ms on the real block clock (H = live median fill -> sell landing).
Gross = SOL back after pump's fee - spend (the shadow's pnl definition). Live realized = gross - the measured fixed costs.
usage: pa4_calib.py X.pkl OUT.pkl"""
import sys, json, pickle, collections, statistics
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/obs/paper_audit")
import pa_lib as L

DS = (0.0, 2.0, 5.0, 10.0, 20.0, 40.0)
SIZE = 0.696


def live_info(X, k, tp):
    fills = X["lv_fill"].get(k) or []
    out = {"filled": bool(fills)}
    dis = X["lv_dis"].get(k)
    out["dis_why"] = dis["why"] if dis else None
    out["dis_t"] = dis["t"] if dis else None
    tries = X["tries"].get(k) or []
    out["tries"] = len(tries)
    out["landed_failed"] = sum(1 for a in tries if a["land"] and a["land"].get("res") not in (None, "unseen", "ok"))
    out["fail_fees"] = sum((a["land"].get("fee") or 0) for a in tries if a["land"] and a["land"].get("res") not in (None, "unseen", "ok")) / 1e9
    if not fills: return out
    f = fills[0]
    out["fill_pos"] = (f["slot"], f["idx"])
    out["fill_t"] = f["t"]
    out["p_entry_pre"] = f.get("p_entry_pre")
    out["sol_in"] = f.get("sol_in"); out["tokens"] = f.get("tokens")
    real = X["lv_real"].get(k) or []
    out["realized"] = sum((r.get("pnl") or 0) for r in real) / 1e9
    cl = (X["lv_close"].get(k) or [None])[0]
    sells = X["lv_sell"].get(k) or []
    if sells:
        s = sells[0]; out["sell_pos"] = (s["slot"], s["idx"]); out["sell_sol"] = s["sol"]
    ex = (X["lv_exit"].get(k) or [None])[0]
    out["exit_why"] = ex["why"] if ex else None
    # the filling try's landing record
    ft = next((a for a in tries if a["sig"] == f["sig"]), None)
    if ft and ft["land"]:
        Ld = ft["land"]
        out["ms_after_x_a"] = Ld.get("ms_after_x_a"); out["ms_after_x_first"] = Ld.get("ms_after_x_first"); out["n_between"] = Ld.get("n_between")
        x = Ld.get("x") or {}
        out["live_x_pos"] = (x.get("slot"), x.get("idx"), x.get("j")) if x else None
    return out


def main(xp, outp):
    X = pickle.load(open(xp, "rb"))
    tp = L.Tape()
    ses = max(k[0] for k in X["sh_arm"])
    sh_by_trig = {(a["sig"], a.get("j", 0)): k for k, a in X["sh_arm"].items() if k[0] == ses}
    cfg = X["cfg"][-1]
    tps, sls = cfg["presend"]["tp"], cfg["presend"]["sl"]
    wins = []
    cache = {}
    # pass 1: H = live fill landing -> sell landing on the real block clock
    hs = []
    for k, a in X["lv_arm"].items():
        if k[0] != ses or a.get("kind") == "rearm": continue
        li = live_info(X, k, tp)
        if li.get("fill_pos") and li.get("sell_pos"):
            hs.append(L.cc_of(tp.maxi, *li["sell_pos"]) - L.cc_of(tp.maxi, *li["fill_pos"]))
    H = statistics.median(hs) if hs else 300.0
    print(f"live fill -> sell landing on the real block clock: n {len(hs)} median {H:.1f} ms, p25 {np.percentile(hs, 25):.1f} p75 {np.percentile(hs, 75):.1f}")
    for k, a in sorted(X["lv_arm"].items(), key=lambda kv: kv[1]["trig"]["t"]):
        if k[0] != ses or a.get("kind") == "rearm": continue
        tg = a["trig"]
        W = {"k": k, "mint": tg["mint"], "trig": (tg["slot"], tg["idx"], tg.get("j", 0)), "t": tg["t"], "age": tg.get("age_slots"), "live": live_info(X, k, tp)}
        ks = sh_by_trig.get((tg["sig"], tg.get("j", 0)))
        W["sh_k"] = ks
        if ks:
            d = X["sh_dis"].get(ks)
            W["sh"] = {r: {"armed": (d["rows"][r]["armed"] if d else None), "fill": X["sh_fill"].get((ks[0], ks[1], r)) is not None,
                           "pnl": (X["sh_exit"].get((ks[0], ks[1], r)) or {}).get("pnl")} for r in ("a", "b", "c")}
        mint = tg["mint"]
        if mint not in cache:
            t = tp.trades(mint)
            cache[mint] = None if t is None else (L.build_recs(t, tp.ours, drop_ours=False), L.build_recs(t, tp.ours, drop_ours=True))
        if cache[mint] is None: W["tape"] = "no_mint"; wins.append(W); continue
        res = {}
        for var, recs in zip(("kept", "clean"), cache[mint]):
            jt = L.find_trig(recs, *W["trig"])
            if jt is None: res[var] = None; continue
            whale = recs[jt].u
            rv = {}
            for D in DS:
                f = L.window_fill(recs, jt, whale, D)
                o = {"fill": f["fill"], "hit": f.get("hit"), "en": f["en"]}
                if f["fill"]:
                    x, m = recs[f["x"]], recs[f["m"]]
                    o.update(x_pos=(x.s, x.i, x.j), m_pos=(m.s, m.i, m.j), a_land=f["a_land"], ft=f["ft"], n_ahead=f["m"] - f["x"], m_ours=m.ours,
                             ours_ahead=sum(1 for q in range(f["x"], f["m"] + 1) if recs[q].ours), p_m=m.p, p_x=x.p, refp=x.refp)
                    for sz in (SIZE, 0.55):
                        for slip in (True, False):
                            P, e = L.run_path(recs, f["m"], f["a_land"], sz, slip, tps, sls)
                            if e is None: continue
                            o[f"e2_{'slip' if slip else 'naive'}_{sz}"] = e["val"]; o[f"e2_why_{sz}"] = e["why"]
                            if sz == SIZE and slip: o["s_in"] = P.s_in; o["dropped"] = P.dropped
                    if var == "clean":
                        for slip in (True, False):
                            cc0 = L.cc_of(tp.maxi, m.s, m.i)
                            v = L.value_at(recs, f["m"], SIZE, slip, cc0 + H, tp.maxi, by_cc=True)
                            if v: o[f"ecc_{'slip' if slip else 'naive'}"] = v["gross"]
                            sp = W["live"].get("sell_pos")
                            if sp:
                                v = L.value_at(recs, f["m"], SIZE, slip, sp)
                                if v: o[f"el_{'slip' if slip else 'naive'}"] = v["gross"]
                rv[D] = o
            # the live fill's own position on the clean tape: our buy right before it, sold right before the live sell (consistency check)
            if var == "clean" and W["live"].get("fill_pos") and W["live"].get("sell_pos"):
                fp = W["live"]["fill_pos"]
                mi = L.last_before(recs, (fp[0], fp[1], -1))
                if mi is not None:
                    v = L.value_at(recs, mi, SIZE, False, W["live"]["sell_pos"])
                    rv["live_pos"] = {"m_pos": (recs[mi].s, recs[mi].i, recs[mi].j), "el_naive": v["gross"] if v else None,
                                      "p_m": recs[mi].p, "n_after_trig": mi - jt}
                    # trades between the shadow-style crossing (row a's x) and the live fill
                    if rv.get(0.0, {}).get("fill"):
                        xa = rv[0.0]["x_pos"]
                        rv["live_pos"]["n_between_x"] = sum(1 for r in recs if (xa[0], xa[1], xa[2]) < (r.s, r.i, r.j) < (fp[0], fp[1], -1))
            res[var] = rv
        W["port"] = res
        wins.append(W)
    pickle.dump({"wins": wins, "H": H, "hs": hs, "ses": ses}, open(outp, "wb"))
    print("windows", len(wins), "live filled", sum(1 for W in wins if W["live"]["filled"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
