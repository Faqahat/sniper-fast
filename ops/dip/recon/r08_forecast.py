#!/usr/bin/env python3
# r08: the PAPER FORECAST for exactly what ran live, run by run (covered hours = each run's own start..end, all covered).
# Candidates = the engine's own picks (dump records with pass=True: IMIT1 wider, or M2 gate on FRA run 15), the server's
# near-leader list (epoch schedules; reproduces every far_leader skip of the engine), 5-slot spacing per token, one position
# per server (busy until our sell + 0.3 s after a fill, 0.8 s after a failed buy = dd_lib.sim), the run's size (normal / dev)
# and exit, +5% guard, our own trades removed from the tape. Rows: fixed latencies and MEASURED (= our exact landing
# position for every dump we really fired on; the measured distribution for the few the replay takes that live did not).
# Also the "paper as before" (dd20 / dd_lib.sim style: 0.55 SOL, both near lists, IMIT1 c6 SL10, our trades left in the tape).
import sys, os, json, collections, bisect
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S

FIX = 0.0051; FAIL = 0.0005
LATS = (0, 10, 20, 35, 50, 75, 100, 150)


def paper_exit(cfg):
    h = cfg["hold_slots"]
    return {19: (19, 0.20), 6: (6, 0.10), 5: (4, None)}.get(h, (h, cfg["sl"]))


def load_dumps():
    out = collections.defaultdict(list)
    for srv, rn, base in R.RUN_FILES:
        for l in open(f"{R.LIVE}/{base}.jsonl"):
            if '"dump"' not in l[:400]: continue
            o = json.loads(l)
            if o.get("ev") != "dump" or not o.get("pass"): continue
            out[(srv, rn)].append(o)
    return out


def engine(rows, key, fix=FIX, fail=FAIL, margin=300.0, fail_busy=800.0, spacing=5):
    """one position at a time (dd_lib.sim rules); rows sorted by dump arrival; key(row) -> outcome dict or None (skip)"""
    busy = -1e18; last = {}; att = fil = 0; pnl = 0.0; used = []
    for r in rows:
        if r["arr"] < busy: continue
        oc = key(r)
        if oc is None or oc["st"] == 2: continue
        if r["mint"] in last and r["slot"] < last[r["mint"]] + spacing: continue
        last[r["mint"]] = r["slot"]; att += 1
        if oc["st"] == 1:
            pnl -= fail; busy = r["arr"] + fail_busy; used.append((r, oc, -fail)); continue
        p = oc["gross"] - fix; fil += 1; pnl += p
        busy = oc["sell_arr"] + margin; used.append((r, oc, p))
    return dict(att=att, fill=fil, pnl=pnl, used=used)


if __name__ == "__main__":
    F = json.load(open(f"{R.WORK}/fires.json")); cfgs = {(r["srv"], r["run"]): r for r in F["runs"]}
    fired = {(r["srv"], r["dump_sig"]): r for r in F["rows"]}
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    D = load_dumps()
    # measured landing distribution (block-position ms after the dump), all fires
    Lm = np.array([r["L_meas"] for r in F["rows"] if r.get("L_meas") is not None])
    Lq = np.percentile(Lm, np.arange(5, 100, 10))           # 10 equal-weight points of our measured distribution
    print(f"measured landing distribution (10 deciles, ms): {np.round(Lq, 0).tolist()}")
    res_all = {}; detail = {}
    for (srv, rn), ru in sorted(cfgs.items()):
        if (srv, rn) not in D: continue
        cfg = ru["cfg"]; cap, sl = paper_exit(cfg); NL = R.near_list(R.near_name(srv, rn))
        t0 = ru["start"]; t1 = ru["end"] or max(o["t"] for o in D[(srv, rn)]) / 1e9
        rows = []
        for o in D[(srv, rn)]:
            ld = R.leader(o["slot"])
            if ld not in NL: continue
            hit = None
            for tag in ("NEW", "OLD"):
                t, j0 = TPS[tag].find(o["mint"], o["slot"], o["idx"], o.get("sell"))
                if j0 is not None: hit = (tag, t, j0); break
            if hit is None: continue
            tag, t, j0 = hit; tp = TPS[tag].token(t)
            size = (cfg["dev_spend"] if o.get("dev") else cfg["spend"]) / 1e9
            r = dict(sig=o["sig"], mint=o["mint"], slot=o["slot"], idx=o["idx"], arr=float(tp["arr"][j0]), dev=o.get("dev"), size=size, oc={})
            def outcome(res):
                if res["st"] != 0: return dict(st=res["st"])
                v, so, why = S.exits(res, cap, sl=sl)
                return dict(st=0, gross=v - size, sell_arr=(res["s_in"] + so) * S.SMS + 75.0, why=why)
            for L in LATS: r["oc"][L] = outcome(S.run_path(tp, j0, size, L=L))
            f = fired.get((srv, o["sig"]))
            if f is not None and f.get("land_slot") is not None:
                r["oc"]["meas"] = outcome(S.run_path(tp, j0, size, at=(f["land_slot"], f["land_idx"]))); r["fired"] = True
            else:
                # expected value over our measured distribution (10 deciles); fill if most deciles fill
                ocs = [outcome(S.run_path(tp, j0, size, L=float(L))) for L in Lq]
                nf = [x for x in ocs if x["st"] == 0]
                if not nf: r["oc"]["meas"] = dict(st=1 if any(x["st"] == 1 for x in ocs) else 2)
                else:
                    # mixture: P&L = mean over deciles (fails cost FAIL), busy = median sell time of the filled ones
                    g = np.mean([x["gross"] - (0 if x["st"] == 0 else 0) if x["st"] == 0 else (-FAIL + FIX) for x in ocs])
                    r["oc"]["meas"] = dict(st=0, gross=float(g), sell_arr=float(np.median([x["sell_arr"] for x in nf])), why="mix",
                                           pfill=len(nf) / len(ocs))
                r["fired"] = False
            rows.append(r)
        rows.sort(key=lambda x: x["arr"])
        out = {}
        for L in list(LATS) + ["meas"]:
            e = engine(rows, lambda x, L=L: x["oc"].get(L))
            out[L] = e
        res_all[(srv, rn)] = dict(h=(t1 - t0) / 3600, n_cand=len(rows), out=out, cfg=cfg)
        detail[(srv, rn)] = rows
        live = [x for x in F["rows"] if x["srv"] == srv and x["run"] == rn]
        livepnl = sum(((x.get("land_delta") or 0) + sum((s.get("delta") or 0) for s in x["sells"] if not s.get("missing"))) / 1e9 for x in live)
        res_all[(srv, rn)]["live"] = dict(att=len(live), fill=sum(1 for x in live if x["live_result"] == "sold"), pnl=livepnl)
        mf = out["meas"]; used_fired = sum(1 for r_, oc, p in mf["used"] if r_["fired"])
        print(f"{srv} r{rn:<2d} {R.pkt(t0)}..{R.pkt(t1)} ({(t1 - t0) / 3600:4.1f} h) size {cfg['spend'] / 1e9:.2f}/dev {cfg['dev_spend'] / 1e9:.2f} "
              f"exit c{cap} sl{sl} | cand {len(rows):3d} | live {livepnl:+.3f} ({res_all[(srv, rn)]['live']['fill']}/{len(live)}) | " +
              " ".join(f"{L}:{out[L]['pnl']:+.2f}({out[L]['fill']}/{out[L]['att']})" for L in (0, 20, 35, 50, 75)) +
              f" | meas {mf['pnl']:+.3f} ({mf['fill']}/{mf['att']}, {used_fired} of them fired live)")
    # totals
    print("\nTOTAL over all runs (SOL, fills/attempts):")
    for L in list(LATS) + ["meas"]:
        p = sum(v["out"][L]["pnl"] for v in res_all.values()); f = sum(v["out"][L]["fill"] for v in res_all.values()); a = sum(v["out"][L]["att"] for v in res_all.values())
        print(f"   {str(L):>5s} ms: {p:+.3f} ({f}/{a})")
    lp = sum(v["live"]["pnl"] for v in res_all.values()); la = sum(v["live"]["att"] for v in res_all.values()); lf = sum(v["live"]["fill"] for v in res_all.values())
    hh = sum(v["h"] for v in res_all.values())
    print(f"    LIVE: {lp:+.3f} ({lf}/{la}) over {hh:.1f} server-hours")
    json.dump({f"{k[0]}_{k[1]}": dict(h=v["h"], n_cand=v["n_cand"], live=v["live"],
                                     out={str(L): dict(pnl=e["pnl"], fill=e["fill"], att=e["att"]) for L, e in v["out"].items()})
               for k, v in res_all.items()}, open(f"{R.WORK}/forecast.json", "w"), indent=1)
    import pickle
    pickle.dump(detail, open(f"{R.WORK}/forecast_rows.pkl", "wb"))
