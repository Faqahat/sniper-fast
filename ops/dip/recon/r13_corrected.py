#!/usr/bin/env python3
# r13: the CORRECTED replay and what speed is worth.
#  Corrections (all MEASURED on the live fills, r07 / r12):
#   - exit timing: time-limit sell lands in slot s_in + hold - 1 at index ~148 (the paper sold one slot later for hold 6/19);
#     stop-loss sells land ~42 block-ms after the trigger trade (the paper sold the NEXT slot at 75 ms),
#   - costs: each run's real tx fees + tips per fill (0.0027-0.0047 vs FIX 0.0051) and per failed buy (0.000505 at 5M
#     priority, 0.001505 at 15M) instead of FIX 0.0051 / FAIL 0.0005,
#   - engine busy after a failed buy: ~0.2 s (live median 45 ms) instead of 0.8 s.
#  A) per trade at our EXACT landing: corrected model vs live chain P&L (residuals, bootstrap CI)
#  B) the live-config forecast per run with the corrected model at fixed latencies and at our measured landing
#  C) SOL/day vs landing latency (0..150 ms, measured distributions) for one fixed config over the whole covered window
import sys, os, json, collections, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r08_forecast import load_dumps

LATS = (0, 10, 20, 35, 50, 75, 100, 150)
W0, W1 = R.pk("10-24 16:59"), R.pk("10-25 07:50")
THR4 = 0.21088520504965255


def engine(rows, key, margin=300.0, fail_busy=200.0, spacing=5):
    busy = -1e18; last = {}; att = fil = 0; pnl = 0.0; used = []
    for r in rows:
        if r["arr"] < busy: continue
        oc = key(r)
        if oc is None or oc["st"] == 2: continue
        if r["mint"] in last and r["slot"] < last[r["mint"]] + spacing: continue
        last[r["mint"]] = r["slot"]; att += 1
        if oc["st"] == 1:
            pnl += oc["pnl"]; busy = r["arr"] + fail_busy; used.append((r, oc)); continue
        fil += 1; pnl += oc["pnl"]; busy = oc["sell_arr"] + margin; used.append((r, oc))
    return dict(att=att, fill=fil, pnl=pnl, used=used)


def outcome(res, hold, sl, cost, fcost):
    if res["st"] == 2: return dict(st=2, pnl=0.0)
    if res["st"] == 1: return dict(st=1, pnl=-fcost)
    v, k, why = S.exits_live(res, hold, sl)
    return dict(st=0, pnl=v - res["size"] - cost, sell_arr=S.key2arr(k), why=why)


def mix(ocs, fcost):
    """expected outcome over equally likely landing points (our measured distribution)"""
    nf = [x for x in ocs if x["st"] == 0]
    if all(x["st"] == 2 for x in ocs): return dict(st=2, pnl=0.0)
    p = float(np.mean([x["pnl"] for x in ocs if x["st"] != 2]))
    if not nf: return dict(st=1, pnl=p)
    return dict(st=0, pnl=p, sell_arr=float(np.median([x["sell_arr"] for x in nf])), pfill=len(nf) / len(ocs))


if __name__ == "__main__":
    F = json.load(open(f"{R.WORK}/fires.json")); runs = {(r["srv"], r["run"]): r for r in F["runs"]}
    P = json.load(open(f"{R.WORK}/pertrade.json"))
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    # ---- measured costs per run
    cost = {}; fcost = {}
    for k in runs:
        fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
        fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
        cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
        fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
    print("measured cost per fill / per failed buy by run: " + ", ".join(f"{k[0]} r{k[1]} {cost[k]:.4f}/{fcost[k]:.6f}" for k in sorted(runs) if k in {(o['srv'], o['run']) for o in P}))
    # ================= A) per trade at our exact landing
    res_rows = []
    for o in P:
        k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]
        TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
        res = S.run_path(tp, j0, o["size"], at=(o["land_slot"], o["land_idx"]))
        sl = cfg["sl"] if cfg["sl"] < 0.5 else None
        oc = outcome(res, cfg["hold_slots"], sl, cost[k], fcost[k])
        old = (o["x_paper"]["pnl"] if o["x_st"] == 0 else (-0.0005 if o["x_st"] == 1 else 0.0))
        res_rows.append(dict(k=k, live=o["chain_pnl"], corr=oc["pnl"], old=old, fill=o["live_fill"], mst=oc["st"], why=oc.get("why"),
                             why_live=o.get("exit_why_live"), L=o["L_meas"]))
    lv = np.array([r["live"] for r in res_rows]); co = np.array([r["corr"] for r in res_rows]); ol = np.array([r["old"] for r in res_rows])
    print(f"\nA) per trade at our exact landing, {len(res_rows)} fires: LIVE {lv.sum():+.3f} | corrected model {co.sum():+.3f} | old model {ol.sum():+.3f}")
    d = lv - co; rng = np.random.default_rng(7)
    bs = np.array([d[rng.integers(0, len(d), len(d))].sum() for _ in range(5000)])
    print(f"   live - corrected: total {d.sum():+.3f} SOL, per fire mean {d.mean():+.5f} (sd {d.std():.4f}), 90% bootstrap CI of the total [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]")
    fl = np.array([r["fill"] for r in res_rows])
    print(f"   fills: live {lv[fl].sum():+.3f} corrected {co[fl].sum():+.3f} old {ol[fl].sum():+.3f} | fails: live {lv[~fl].sum():+.3f} corrected {co[~fl].sum():+.3f} old {ol[~fl].sum():+.3f}")
    print(f"   corr(live, corrected) on fills {np.corrcoef(lv[fl], co[fl])[0, 1]:.3f}; exit kind agreement on fills: "
          f"{dict(collections.Counter((r['why_live'], r['why']) for r in res_rows if r['fill']))}")
    byk = collections.defaultdict(lambda: np.zeros(4))
    for r in res_rows: byk[r["k"]] += [1, r["live"], r["corr"], r["old"]]
    for k in sorted(byk): print(f"   {k[0]} r{k[1]:<3d} n {int(byk[k][0]):3d}  live {byk[k][1]:+.3f}  corrected {byk[k][2]:+.3f}  old {byk[k][3]:+.3f}")
    json.dump(res_rows, open(f"{R.WORK}/corrected_pertrade.json", "w"), default=str)
    # ================= B) live-config forecast per run, corrected model
    fired = {(r["srv"], r["dump_sig"]): r for r in F["rows"]}
    Lall = np.array([r["L_meas"] for r in F["rows"]])
    Lq_all = np.percentile(Lall, np.arange(5, 100, 10))
    D = load_dumps(); totB = collections.defaultdict(float); fB = collections.defaultdict(int); aB = collections.defaultdict(int)
    hours = 0.0; liveT = 0.0
    print("\nB) live-config forecast per run, CORRECTED model (SOL, fills/attempts)")
    for k in sorted(runs):
        if k not in D: continue
        srv, rn = k; ru = runs[k]; cfg = ru["cfg"]; NL = R.near_list(R.near_name(srv, rn)); sl = cfg["sl"] if cfg["sl"] < 0.5 else None
        t1 = ru["end"] or max(o["t"] for o in D[k]) / 1e9; hours += (t1 - ru["start"]) / 3600
        rows = []
        for o in D[k]:
            if R.leader(o["slot"]) not in NL: continue
            hit = None
            for tag in ("NEW", "OLD"):
                t, j0 = TPS[tag].find(o["mint"], o["slot"], o["idx"], o.get("sell"))
                if j0 is not None: hit = (tag, t, j0); break
            if hit is None: continue
            tag, t, j0 = hit; tp = TPS[tag].token(t); size = (cfg["dev_spend"] if o.get("dev") else cfg["spend"]) / 1e9
            r = dict(mint=o["mint"], slot=o["slot"], arr=float(tp["arr"][j0]), oc={})
            for L in LATS: r["oc"][L] = outcome(S.run_path(tp, j0, size, L=L), cfg["hold_slots"], sl, cost[k], fcost[k])
            f = fired.get((srv, o["sig"]))
            if f is not None: r["oc"]["meas"] = outcome(S.run_path(tp, j0, size, at=(f["land_slot"], f["land_idx"])), cfg["hold_slots"], sl, cost[k], fcost[k])
            else: r["oc"]["meas"] = mix([outcome(S.run_path(tp, j0, size, L=float(L)), cfg["hold_slots"], sl, cost[k], fcost[k]) for L in Lq_all], fcost[k])
            rows.append(r)
        rows.sort(key=lambda x: x["arr"])
        live = [x for x in P if (x["srv"], x["run"]) == k]; lp = sum(x["chain_pnl"] for x in live); liveT += lp
        line = []
        for L in list(LATS) + ["meas"]:
            e = engine(rows, lambda x, L=L: x["oc"].get(L)); totB[L] += e["pnl"]; fB[L] += e["fill"]; aB[L] += e["att"]
            line.append((L, e))
        print(f"   {srv} r{rn:<2d} live {lp:+.3f} | " + " ".join(f"{L}:{e['pnl']:+.2f}" for L, e in line))
    print("   TOTAL: " + " | ".join(f"{L} {totB[L]:+.2f} ({fB[L]}/{aB[L]})" for L in list(LATS) + ["meas"]) + f" | LIVE {liveT:+.3f} | {hours:.1f} server-h")
    json.dump(dict(tot={str(k): v for k, v in totB.items()}, fills={str(k): v for k, v in fB.items()}, att={str(k): v for k, v in aB.items()},
                   live=liveT, server_hours=hours), open(f"{R.WORK}/corrected_forecast.json", "w"))
