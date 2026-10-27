#!/usr/bin/env python3
"""SIZE_48H step 2 (read-only): replay probe 3's own hours with probe-3 settings and compare to live (MEASURED, AMS run 19).
  A. window by window (as calib.py): each live armed window re-run from the chain tape with MODELED tries, N draws; the
     landing donor is never the window itself nor its token. Landing pools:
       "P3"   = the calibrated model (probe 3's own windows; leave-one-out, so in-sample for landing);
       "P12"  = the old model (probes 1-2 only; out-of-sample for probe 3).
  B. the variant pipeline on the same hours (detected triggers, the engine's own skip rules, no forced arming; only tokens
     created after the engine started), N draws, calibrated landing.
usage: p3check.py [--draws 400] [--hdraws 100] [--procs 14] [--size SOL]"""
import sys, os, json, pickle, argparse, collections, time
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib
s48lib.use_tab48()
import rlib, sim, variants

G = {}
_fin = sim.finish
def _finish(w, cfg):
    """sim.finish + the landed tries' slot after the engine's send slot (0 / 1 / 2+), for the per-try landing comparison"""
    r = _fin(w, cfg)
    if w.armed: r["sas"] = collections.Counter(min(t["S"] - t["E"], 2) for t in w.tries if t["res"] != "drop" and "S" in t)
    return r
sim.finish = _finish

def cfg_p3(slot_ms, size=None, D=None):
    c = (D or G["D"])["P3"]["cfg"]; rate = c["path_max_per_sec"]
    return sim.Cfg(slot_ms=slot_ms, size=(size or c["spend"]), k=c["k"], drop=c["drop"], deadline_slots=c["deadline_slots"], window_slots=c["window_slots"],
                   live_ms=c["live_ms"], whale_sell_ms=c["whale_sell_ms"], paths=[(rate, rate)], global_rate=c["max_per_sec"], exit_slots=c["exit_slots"],
                   tp=c["tp"], sl=c["sl"], whale_pct=c["whale_pct"])

def pace_slot(D):
    """the engine's pace slot (ms) in probe 3: k x the modal gap between a window's consecutive tries (MEASURED)"""
    k = D["P3"]["cfg"]["k"]; gaps = []
    for W in D["P3"]["wins"]:
        d = sorted(t["d"] for t in W["tries"])
        gaps += list(np.diff(d))
    g = np.array(gaps); g = g[(g > 10) & (g < 40)]
    h, e = np.histogram(g, bins=np.arange(20, 34, 0.1))
    mode = e[np.argmax(h)] + 0.05
    sel = g[np.abs(g - mode) < 0.6]
    return float(np.median(sel) * k), len(sel)

def windows_p3():
    tp = G["tp"]; idm = tp.id_map(); out = []
    for W in G["D"]["P3"]["wins"]:
        tr = W["trig"]; mid = idm[tr["mint"]]; whale = idm[tr["wallet"]]
        a, e = tp.span[mid]; ws = None
        for k in range(a, e):
            if (tp.s[k], tp.i[k], tp.j[k]) <= (tr["slot"], tr["idx"], tr["j"]): continue
            if tp.user[k] == whale and not tp.buy[k]: ws = (int(tp.s[k]), int(tp.i[k])); break
        out.append(dict(mint=tr["mint"], slot=tr["slot"], idx=tr["idx"], j=tr["j"], age_slots=tr["age_slots"], whale=whale, whale_sell=ws,
                        force_arm=True, probe="P3", w=W["w"]))
    return out

def one(args):
    pool, seed = args
    rng = np.random.default_rng(seed)
    res = sim.run(G["ck"], G["store"], G["wins"], G["cfg"], G["land"][pool], G["model"][pool], G["view"], rng, exclude_self=True)
    return pool, [(r["trig"]["w"], r.get("filled", False), r.get("net", 0), r.get("pnl", 0), r.get("fees", 0), r.get("sent", 0), r.get("landed", 0),
                   sum((r.get("rate") or {}).values()), r.get("deadline", 0), r.get("exit"), r.get("xgap"), r.get("sas")) for r in res]

def hours_one(seed):
    rng = np.random.default_rng(seed)
    res = sim.run(G["ck"], G["hstore"], G["hws"], G["cfg"], G["land"]["P3"], G["model"]["P3"], G["view"], rng)
    a = [r for r in res if r["armed"]]
    return (len(a), sum(r.get("filled", False) for r in a), sum(1 for r in a if r.get("filled") and r["pnl"] > 0), sum(r.get("pnl", 0) for r in a) / 1e9,
            sum(r.get("fees", 0) for r in a) / 1e9, sum(r.get("net", 0) for r in a) / 1e9)

def pct(a, q): return float(np.percentile(a, q))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--draws", type=int, default=400); ap.add_argument("--hdraws", type=int, default=100)
    ap.add_argument("--procs", type=int, default=14); A = ap.parse_args()
    t0 = time.time()
    tp = s48lib.Tape48(); G["tp"] = tp
    D = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb")); G["D"] = D
    slot_ms, ngap = pace_slot(D)
    G["cfg"] = cfg_p3(slot_ms)
    G["land"] = {"P3": sim.Landing(D, probes=("P3",)), "P12": sim.Landing(D, probes=("P1", "P2"))}
    G["model"] = {"P3": s48lib.ModelN(D, tp, ("P1", "P2", "P3")), "P12": s48lib.ModelN(D, tp, ("P1", "P2"))}
    G["view"] = sim.View(); G["ck"] = tp.clock()
    G["wins"] = windows_p3()
    spans = {}
    for x in G["wins"]:
        lo, hi = spans.get(x["mint"], (1 << 62, 0)); spans[x["mint"]] = (min(lo, x["slot"] - 400), max(hi, x["slot"] + 120))
    G["store"] = sim.build_store(tp, spans)
    # B: the detected triggers in probe 3's hours (tokens created after the engine started)
    P3 = D["P3"]; t_start = P3["start"]["t"] / 1e9
    t_end = (P3["stop"] or {}).get("t", 0) / 1e9 or max(W["trig"]["t"] for W in P3["wins"]) / 1e9
    t_lo = max(W["trig"]["t"] for W in P3["wins"][:1]) / 1e9 - 1.0
    trig = pickle.load(open(f"{s48lib.S48}/trig_6.pkl", "rb"))
    hws = []
    for d in trig:
        if not (t_lo <= d["bt"] < t_end): continue
        if tp.creates[d["mint"]]["bt"] < t_start: continue
        sw = None
        if d["sells"]: k = d["sells"][0]; sw = (int(tp.s[k]), int(tp.i[k]))
        hws.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=d["v2"], cashback=d["cashback"], whale=d["whale"],
                        whale_sell=sw, pred=None, quick=0, bt=d["bt"], half=1))
    G["hws"] = hws; G["hstore"] = sim.build_store(tp, variants.spans_for(hws))
    del G["tp"]
    print(f"prep {time.time() - t0:.0f} s; pace slot {slot_ms:.1f} ms ({ngap} gaps); live windows {len(G['wins'])}; detected triggers in {rlib.pkt(t_lo)}-{rlib.pkt(t_end)} PKT: {len(hws)}", flush=True)
    live = s48lib.live_summary(P3["wins"])
    jobs = [(pool, 7000 + s) for pool in ("P3", "P12") for s in range(A.draws)]
    R = collections.defaultdict(list)
    import gc; gc.collect()
    with Pool(A.procs) as p:
        for pool, rows in p.imap_unordered(one, jobs, chunksize=4): R[pool].append(rows)
        HB = list(p.imap_unordered(hours_one, range(9000, 9000 + A.hdraws), chunksize=2))
    out = dict(live=live, slot_ms=slot_ms, hours=(t_lo, t_end), n_hws=len(hws))
    lines = [f"PROBE-3 CHECK (written {time.strftime('%m-%d %H:%M', time.gmtime(time.time() + 18000))} PKT, before any 48 h result)",
             f"live (MEASURED, AMS run 19, {rlib.pkt(P3['start']['t'] / 1e9)}-{rlib.pkt(t_end)} PKT): windows {live['windows']}, fills {live['fills']}, wins {live['wins']}, "
             f"realized {live['realized']:+.4f}, failed-try fees {live['fees']:.4f}, net {live['net']:+.4f} SOL, net/fill {live['per_fill']:+.4f} "
             f"(fills without a realized record: {live['unrealized']})"]
    livefill = {W["w"]: W["fill"] is not None for W in P3["wins"]}
    for pool in ("P3", "P12"):
        dr = R[pool]
        fills = np.array([sum(r[1] for r in d) for d in dr]); wins = np.array([sum(1 for r in d if r[1] and r[3] > 0) for d in dr])
        pnl = np.array([sum(r[3] for r in d) for d in dr]) / 1e9; fees = np.array([sum(r[4] for r in d) for d in dr]) / 1e9
        net = np.array([sum(r[2] for r in d) for d in dr]) / 1e9; npf = net / np.maximum(fills, 1)
        pf = {w: np.mean([dict((r[0], r[1]) for r in d)[w] for d in dr]) for w in livefill}
        agree = np.mean([pf[w] if livefill[w] else 1 - pf[w] for w in livefill])
        o = dict(fills=(fills.mean(), pct(fills, 5), pct(fills, 95)), wins=(wins.mean(), pct(wins, 5), pct(wins, 95)), pnl=(pnl.mean(), pct(pnl, 5), pct(pnl, 95)),
                 fees=(fees.mean(), pct(fees, 5), pct(fees, 95)), net=(net.mean(), pct(net, 5), pct(net, 95)), npf=(npf.mean(), pct(npf, 5), pct(npf, 95)),
                 live_pct_net=float((net <= live["net"]).mean()), live_pct_fills=float((fills <= live["fills"]).mean()), live_pct_npf=float((npf <= live["per_fill"]).mean()),
                 live_pct_pnl=float((pnl <= live["realized"]).mean()), live_pct_fees=float((fees <= live["fees"]).mean()), agree=float(agree),
                 sent=float(np.mean([sum(r[5] for r in d) for d in dr])), landed=float(np.mean([sum(r[6] for r in d) for d in dr])),
                 refused=float(np.mean([sum(r[7] for r in d) for d in dr])), deadline=float(np.mean([sum(r[8] for r in d) for d in dr])),
                 sas={k: v / max(1, sum(sum((r[11] or {}).values()) for d in dr for r in d)) for k, v in
                      sum((collections.Counter(r[11] or {}) for d in dr for r in d), collections.Counter()).items()},
                 xgap=[pct([r[10] for d in dr for r in d if r[1] and r[10] is not None], q) for q in (25, 50, 75)])
        out[pool] = o
        f3 = lambda t, f="%+.4f": (f % t[0]) + " [" + (f % t[1]) + ", " + (f % t[2]) + "]"
        lines.append(f"\nA. window by window, landing pool {pool} ({A.draws} draws; mean [p5, p95]); fill/no-fill agreement {agree * 100:.1f}%")
        lines.append(f"   fills {f3(o['fills'], '%.1f')} (live {live['fills']}, at the replay's {o['live_pct_fills'] * 100:.0f}th pct)")
        lines.append(f"   wins {f3(o['wins'], '%.1f')} (live {live['wins']})")
        lines.append(f"   realized {f3(o['pnl'])} (live {live['realized']:+.4f}, {o['live_pct_pnl'] * 100:.0f}th pct)")
        lines.append(f"   failed-try fees {f3(o['fees'])} (live {live['fees']:.4f}, {o['live_pct_fees'] * 100:.0f}th pct)")
        lines.append(f"   net {f3(o['net'])} (live {live['net']:+.4f}, {o['live_pct_net'] * 100:.0f}th pct)")
        lines.append(f"   net/fill {f3(o['npf'])} (live {live['per_fill']:+.4f}, {o['live_pct_npf'] * 100:.0f}th pct)")
        lines.append(f"   landed tries by slot after the engine's send slot: " + ", ".join(f"+{k}: {o['sas'].get(k, 0) * 100:.0f}%" for k in (0, 1, 2)))
        lines.append(f"   tries sent {o['sent']:.0f} landed {o['landed']:.0f} refused {o['refused']:.0f} deadline {o['deadline']:.0f}; fill after crossing ms p25/50/75 {o['xgap'][0]:.0f}/{o['xgap'][1]:.0f}/{o['xgap'][2]:.0f}")
    HB = np.array(HB)
    live_n = live["net"]
    lines.append(f"\nB. detected triggers in the same hours ({len(hws)} triggers, {A.hdraws} draws, landing P3): armed {HB[:, 0].mean():.0f} (live {live['windows']}), "
                 f"fills {HB[:, 1].mean():.1f} [{pct(HB[:, 1], 5):.0f}, {pct(HB[:, 1], 95):.0f}] (live {live['fills']}), wins {HB[:, 2].mean():.1f} (live {live['wins']}), "
                 f"realized {HB[:, 3].mean():+.4f}, fees {HB[:, 4].mean():.4f}, net {HB[:, 5].mean():+.4f} [{pct(HB[:, 5], 5):+.4f}, {pct(HB[:, 5], 95):+.4f}] "
                 f"(live {live_n:+.4f}, at the {float((HB[:, 5] <= live_n).mean()) * 100:.0f}th pct); net/fill {HB[:, 5].sum() / max(HB[:, 1].sum(), 1):+.4f}")
    out["B"] = dict(armed=float(HB[:, 0].mean()), fills=(float(HB[:, 1].mean()), pct(HB[:, 1], 5), pct(HB[:, 1], 95)), wins=float(HB[:, 2].mean()),
                    pnl=float(HB[:, 3].mean()), fees=float(HB[:, 4].mean()), net=(float(HB[:, 5].mean()), pct(HB[:, 5], 5), pct(HB[:, 5], 95)),
                    live_pct=float((HB[:, 5] <= live_n).mean()))
    lines.append(f"\n{time.time() - t0:.0f} s")
    txt = "\n".join(lines); print(txt)
    open(f"{s48lib.S48}/p3check.txt", "w").write(txt + "\n")
    json.dump(out, open(f"{s48lib.S48}/p3check.json", "w"), indent=1, default=float)
