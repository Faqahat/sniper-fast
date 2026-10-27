#!/usr/bin/env python3
# Compare with TODAY'S REACTIVE BOT on the same hours: dd_lib.sim (dipdetect, read-only import) with IMIT1 top4 inside the
# envelope, 35 / 50 / 75 ms, exits c4_tpnone_slnone and c6_tpnone_sl10. Then: do the pre-sent fills hit DIFFERENT dumps (same
# crossing trade = same dump; same token within 20 slots), and a COMBINED replay sharing the 2 servers (reactive picks need their
# near server; pre-sent fills take any free server; no two positions on one token; on a shared dump the pre-sent order lands
# first (dump + D ms vs dump + 35/50/75 ms) and the reactive buy is skipped). Pre-sent attempt costs are the standalone ones.
# usage: python3 ps8_compare.py KEY [KEY ...]   (keys from ps6_select.json, e.g. T3|c)  -> presend/ps8_compare.json + stdout
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_lib as L
import ps5_lib as E, ps7_test as T
DAYS = ("R2", "R3", "R4", "R1")
def combined(d, sel, lat, ex, o, spacing=5, smart=None):
    """smart = (D, size index): a pre-sent fill on a dump that also passes the reactive gate holds with the reactive exit"""
    e = L.EXI[ex]; ev = []
    if smart is not None:
        Dp, si = smart; ep = E.EXI[ex]; selk = set(d["k"][sel].tolist())
        o = dict(o); o["cand_net"] = o["cand_net"].copy(); o["cand_xt"] = o["cand_xt"].copy()
        for i, x in enumerate(o["cand_x"].tolist()):
            if x in selk:
                pid = o["cand_pid"][i]; o["cand_net"][i] = float(Dp["p_pnl"][pid, si, ep]) - o["cand_cost"]
                o["cand_xt"][i] = (o["cand_sin"][i] + int(Dp["p_off"][pid, si, ep])) * E.SMS + 75.0
    for sv in ("f", "a"):
        near = d["near_f"] if sv == "f" else d["near_a"]
        for r in np.flatnonzero(sel & near).tolist(): ev.append((float(d["arr"][r]) + (35.0, 50.0, 75.0)[lat], 0, r, sv))   # reactive lands at dump + latency
    for i in range(len(o["cand_ft"])): ev.append((float(o["cand_ft"][i]), 1, i, None))
    ev.sort(key=lambda x: (x[0], x[1]))
    busy = {"f": -1e18, "a": -1e18}; hold = {}; last = {}; pn_r = 0.0; pn_p = 0.0; nr = nf_r = npre = 0
    for t0, kind, r, sv in ev:
        if kind == 0:
            if float(d["arr"][r]) < busy[sv]: continue
            st = d["st"][r, lat]
            if st == 2: continue
            tk = int(d["tok"][r]); s = int(d["s"][r])
            if tk in last and s < last[tk] + spacing: continue
            if hold.get(tk, -1e18) > t0: continue
            last[tk] = s; nr += 1
            if st == 1: pn_r -= L.FAIL; busy[sv] = float(d["arr"][r]) + 800.0; continue
            p = float(d["pnl"][r, lat, e]) - L.FIX; pn_r += p; nf_r += 1
            busy[sv] = (d["sin"][r, lat] + d["off"][r, lat, e]) * L.SMS + 75.0 + 300.0; hold[tk] = busy[sv]
        else:
            tk = int(o["cand_tok"][r])
            if hold.get(tk, -1e18) > t0: continue
            fs = [s_ for s_ in ("f", "a") if busy[s_] <= t0]
            if not fs: continue
            s_ = min(fs, key=lambda q: busy[q]); busy[s_] = float(o["cand_xt"][r]) + 300.0; hold[tk] = busy[s_]
            pn_p += float(o["cand_net"][r]); npre += 1
    return dict(react=pn_r, react_fills=nf_r, react_att=nr, pre=pn_p - o["cost_att"], pre_fills=npre, total=pn_r + pn_p - o["cost_att"])

if __name__ == "__main__":
    best = json.load(open(f"{E.C.OUT}/ps6_select.json"))["best"]; keys = sys.argv[1:]
    out = {}
    for day in DAYS:
        d = L.load(day); h = L.hours(d); D = E.load(day); hp = D["hours"]
        sel = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"]) & d["env"]
        print(f"\n=== {day} ({h:.1f} h reactive window / {hp:.1f} h pre-sent window)", flush=True)
        base = {}
        for exn in ("c4_tpnone_slnone", "c6_tpnone_sl10"):
            for lat in (0, 1, 2):
                o = L.sim(d, sel, lat, L.EXI[exn], detail=True); base[(exn, lat)] = o
                print(f"  REACTIVE IMIT1 top4 env {exn:17s} {(35, 50, 75)[lat]} ms: {L.fmt(o, h)}")
                out[f"base|{exn}|{lat}|{day}"] = dict(pnl=o["pnl"], fill=o["fill"], att=o["att"], per_fill=o["per_fill"], per24=o["pnl"] / h * 24)
        for key in keys:
            b = best[key]; o = T.one(D, b)
            xs = set(o["acc_x"].tolist())
            for exn in ("c4_tpnone_slnone", "c6_tpnone_sl10"):
                for lat in (0, 1, 2):
                    rb = base[(exn, lat)]["rows"]
                    rk = {int(d["k"][r]) for r, sv, p, fl in rb if fl}
                    same = len(xs & rk)
                    # same token within 20 slots
                    rt = collections.defaultdict(list)
                    for r, sv, p, fl in rb:
                        if fl: rt[int(d["tok"][r])].append(int(d["s"][r]))
                    D_s = D["s_tape"]
                    near = sum(1 for tk, x in zip(o["acc_tok"].tolist(), o["acc_x"].tolist()) if any(abs(int(D_s[x]) - s) <= 20 for s in rt.get(tk, [])))
                    cb = combined(d, sel, lat, exn, o)
                    cs = combined(d, sel, lat, exn, o, smart=(D, E.SIZES.index(b["size"])))
                    rec = dict(pre_fills=o["fill"], pre_pnl=o["pnl"], react_fills=base[(exn, lat)]["fill"], same_dump=same, same_tok20=near,
                               combined=cb, combined_smart=cs, react_alone=base[(exn, lat)]["pnl"])
                    out[f"{key}|{exn}|{lat}|{day}"] = rec
                    print(f"  {key:8s} vs reactive {exn:17s} {(35, 50, 75)[lat]} ms: pre-sent fills {o['fill']}, on the SAME dump as a reactive fill {same} "
                          f"({100 * same / max(o['fill'], 1):.0f}%), same token +-20 slots {near}; COMBINED {cb['total']:+.2f} (reactive {cb['react']:+.2f} "
                          f"[{cb['react_fills']} fills], pre-sent {cb['pre']:+.2f} [{cb['pre_fills']}]) vs reactive alone {base[(exn, lat)]['pnl']:+.2f} "
                          f"+ pre-sent alone {o['pnl']:+.2f} | SMART-EXIT COMBINED {cs['total']:+.2f} ({cs['react']:+.2f} + {cs['pre']:+.2f})", flush=True)
        del d, D
    json.dump(out, open(f"{E.C.OUT}/ps8_compare.json", "w"), indent=1, default=float)
