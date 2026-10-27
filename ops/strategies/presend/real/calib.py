#!/usr/bin/env python3
"""REAL replay calibration on the two live probes (pre-registered marks: REAL_REPLAY.md section 0.1).
Each live armed window is re-run from the chain tape with MODELED tries (never the real ones), N draws; the landing donor is
never the window itself nor its token. Live = the engine's records + the chain (MEASURED).
usage: calib.py [--draws 400] [--procs 16] [--mode interp|corr] [--follower slack|naive] [--tag NAME]"""
import sys, os, pickle, json, argparse, collections, time
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib, sim

OUT = "/home/moiz/sniper-data/presend_real"
MISSES = ("2uYDtKbW", "7Y436FBv", "GvtdnDT8", "2yrbEtsu")
G = {}

def cfg_for(name, follower):
    c = G["D"][name]["cfg"]
    rate = c["path_max_per_sec"]
    return sim.Cfg(extra_lag_ms=G.get("lag", 0.0), slot_ms=(214.1 if name == "P1" else 211.7), size=c["spend"], k=c["k"], drop=c["drop"], deadline_slots=c["deadline_slots"], window_slots=c["window_slots"],
                   live_ms=c["live_ms"], whale_sell_ms=c["whale_sell_ms"], paths=[(rate, rate)], global_rate=c["max_per_sec"],
                   exit_slots=c["exit_slots"], tp=c["tp"], sl=c["sl"], whale_pct=c["whale_pct"], follower=follower)

def windows(name):
    tp = G["tp"]; idm = tp.id_map(); out = []
    for W in G["D"][name]["wins"]:
        tr = W["trig"]; mid = idm[tr["mint"]]; whale = idm[tr["wallet"]]
        a, e = tp.span[mid]
        ws = None
        for k in range(a, e):
            if (tp.s[k], tp.i[k], tp.j[k]) <= (tr["slot"], tr["idx"], tr["j"]): continue
            if tp.user[k] == whale and not tp.buy[k]: ws = (int(tp.s[k]), int(tp.i[k])); break
        out.append(dict(mint=tr["mint"], slot=tr["slot"], idx=tr["idx"], j=tr["j"], age_slots=tr["age_slots"], whale=whale, whale_sell=ws,
                        force_arm=True, probe=name, w=W["w"]))
    return out

def init(mode, follower):
    """in the parent, before the workers fork: the tape is read once; the workers share the small store / clock"""
    tp = rlib.Tape(); G["tp"] = tp
    G["D"] = pickle.load(open(f"{OUT}/donors.pkl", "rb"))
    G["land"] = sim.Landing(G["D"], mode=mode); G["model"] = sim.Model(G["D"], tp); G["ck"] = tp.clock(); G["view"] = sim.View()
    G["wins"] = {n: windows(n) for n in ("P1", "P2")}; G["follower"] = follower
    spans = {}
    for n in G["wins"]:
        for x in G["wins"][n]:
            lo, hi = spans.get(x["mint"], (1 << 62, 0))
            spans[x["mint"]] = (min(lo, x["slot"] - 400), max(hi, x["slot"] + 120))
    G["store"] = sim.build_store(tp, spans)
    del G["tp"]

def one(args):
    name, seed = args
    rng = np.random.default_rng(seed)
    res = sim.run(G["ck"], G["store"], G["wins"][name], cfg_for(name, G["follower"]), G["land"], G["model"], G["view"], rng, exclude_self=True)
    return name, [(r["trig"]["w"], r.get("filled", False), r.get("net", 0), r.get("pnl", 0), r.get("fees", 0), r.get("sent", 0), r.get("landed", 0),
                   sum((r.get("rate") or {}).values()), r.get("deadline", 0), r.get("why"), r.get("exit"), r.get("fill_d"), r.get("xgap")) for r in res]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--draws", type=int, default=400); ap.add_argument("--procs", type=int, default=16)
    ap.add_argument("--mode", default="interp"); ap.add_argument("--follower", default="slack"); ap.add_argument("--tag", default="main"); ap.add_argument("--lag", type=float, default=0.0)
    A = ap.parse_args()
    t0 = time.time()
    G["lag"] = A.lag
    init(A.mode, A.follower)
    D = G["D"]
    jobs = [(n, 1000 * (1 + (n == "P2")) + s) for n in ("P1", "P2") for s in range(A.draws)]
    R = collections.defaultdict(list)
    import gc; gc.collect()
    with Pool(A.procs) as p:
        for name, rows in p.imap_unordered(one, jobs, chunksize=4): R[name].append(rows)
    out = {}
    lines = [f"REAL replay calibration ({A.tag}: landing {A.mode}, followers {A.follower}, {A.draws} draws per probe) {time.strftime('%m-%d %H:%M', time.gmtime(time.time() + 18000))} PKT"]
    for name in ("P1", "P2"):
        live = {W["w"]: W for W in D[name]["wins"]}
        live_fill = {w: W["fill"] is not None for w, W in live.items()}
        live_net = sum(W["realized"]["pnl"] for W in live.values() if W["fill"]) - sum((t["fee"] or 5120) for W in live.values() for t in W["tries"] if t["res"] in ("6042", "deadline", "ata_exists", "other"))
        draws = R[name]
        ws = sorted(live)
        pf = {w: np.mean([dict((r[0], r[1]) for r in d)[w] for d in draws]) for w in ws}
        agree = np.mean([pf[w] if live_fill[w] else 1 - pf[w] for w in ws])
        major = np.mean([(pf[w] >= 0.5) == live_fill[w] for w in ws])
        nets = np.array([sum(r[2] for r in d) for d in draws]) / 1e9
        pnls = np.array([sum(r[3] for r in d) for d in draws]) / 1e9
        fees = np.array([sum(r[4] for r in d) for d in draws]) / 1e9
        fills = np.array([sum(r[1] for r in d) for d in draws])
        sent = np.mean([sum(r[5] for r in d) for d in draws]); landed = np.mean([sum(r[6] for r in d) for d in draws]); refused = np.mean([sum(r[7] for r in d) for d in draws])
        live_sent = sum(len(W["tries"]) for W in live.values()); live_landed = sum(1 for W in live.values() for t in W["tries"] if t["res"] not in ("drop", "unknown"))
        dl = np.mean([sum(r[8] for r in d) for d in draws]); live_dl = sum(1 for W in live.values() for t in W["tries"] if t["res"] == "deadline")
        xg = [r[12] for d in draws for r in d if r[1] and r[12] is not None]
        ck = G["ck"]; live_xg = []
        for W in live.values():
            L = W["fill"]
            if not L: continue
            tr = next((t for t in W["tries"] if t["sig"] == L["sig"]), None)
            tk = G["store"][W["mint"]]
            if tr is None: continue
            ks = tk.before(tr["pos"][0], tr["pos"][1] + 0.5); kb = tk.before(L["slot"], L["idx"])
            xk = next((j for j in range(ks + 1, kb + 1) if tk.vsol[j] / tk.vtok[j] <= tr["lim"]), kb)
            live_xg.append(ck.cc(L["slot"], L["idx"]) - tk.cc[xk])
        lines.append(f"  deadline failures {dl:.0f} (live {live_dl}); fills landed after their crossing trade (chain clock ms): replay p25/p50/p75 "
                     f"{np.percentile(xg, 25):.0f}/{np.percentile(xg, 50):.0f}/{np.percentile(xg, 75):.0f} | live {np.percentile(live_xg, 25):.0f}/{np.percentile(live_xg, 50):.0f}/{np.percentile(live_xg, 75):.0f}")
        miss = {}
        for w in ws:
            m = live[w]["mint"][:8]
            if m in MISSES: miss[m] = round(float(pf[w]), 3)
        lines.append(f"\n== {name}: {len(ws)} windows, live fills {sum(live_fill.values())}, live net {live_net / 1e9:+.4f} SOL")
        lines.append(f"  Mark 1 agreement (expected) {agree * 100:.1f}%  | majority rule {major * 100:.1f}%")
        lines.append(f"  replay fills mean {fills.mean():.1f} (p5 {np.percentile(fills, 5):.0f}, p95 {np.percentile(fills, 95):.0f})")
        lines.append(f"  Mark 2 replay net mean {nets.mean():+.4f} SOL (p5 {np.percentile(nets, 5):+.4f}, p95 {np.percentile(nets, 95):+.4f}) vs live {live_net / 1e9:+.4f} -> diff {nets.mean() - live_net / 1e9:+.4f}")
        lines.append(f"     fills P&L {pnls.mean():+.4f}, failed-try fees {fees.mean():.4f} (live: realized {sum(W['realized']['pnl'] for W in live.values() if W['fill']) / 1e9:+.4f}, fees {(sum(W['realized']['pnl'] for W in live.values() if W['fill']) - live_net) / 1e9:.4f})")
        lines.append(f"  tries sent {sent:.0f} (live {live_sent}), landed {landed:.0f} (live {live_landed}), refused by caps {refused:.0f}")
        if miss: lines.append(f"  Mark 3 the 4 misses, p(fill): {miss}")
        # per window table (live fills + windows with p > 0.05)
        lines.append("  per window (live fill or p >= 0.05): w mint live p | replay mean net mSOL | live net mSOL")
        for w in ws:
            if live_fill[w] or pf[w] >= 0.05:
                W = live[w]
                ln = (W["realized"]["pnl"] if W["fill"] else 0) - 5120 * sum(1 for t in W["tries"] if t["res"] in ("6042", "deadline", "ata_exists", "other"))
                mn = np.mean([dict((r[0], r[2]) for r in d)[w] for d in draws])
                lines.append(f"    w{w:3d} {W['mint'][:8]} live {'FILL' if live_fill[w] else '  - '} p {pf[w]:.2f} | replay {mn / 1e6:+7.2f} | live {ln / 1e6:+7.2f}")
        pct_live = float((nets <= live_net / 1e9).mean())
        lines.append(f"  live net sits at the replay's {pct_live * 100:.0f}th percentile (P(replay <= live)); replay net sd {nets.std():.4f}")
        out[name] = dict(agree=agree, major=major, net_mean=float(nets.mean()), live_net=live_net / 1e9, miss=miss, pf={int(k): float(v) for k, v in pf.items()},
                         fills_mean=float(fills.mean()), live_fills=int(sum(live_fill.values())), nets=nets.tolist(), fills=fills.tolist(), pct_live=pct_live,
                         p5=float(np.percentile(nets, 5)), p95=float(np.percentile(nets, 95)), fills_p5=float(np.percentile(fills, 5)), fills_p95=float(np.percentile(fills, 95)),
                         sent=float(sent), live_sent=live_sent, landed=float(landed), live_landed=live_landed, refused=float(refused), fees=float(fees.mean()), pnl=float(pnls.mean()),
                         live_realized=sum(W['realized']['pnl'] for W in live.values() if W['fill']) / 1e9, deadline=float(dl), live_deadline=live_dl,
                         xgap=[float(np.percentile(xg, q)) for q in (25, 50, 75)], live_xgap=[float(np.percentile(live_xg, q)) for q in (25, 50, 75)])
    if "P1" in out and "P2" in out:
        comb = np.array(out["P1"]["nets"]) + np.array(out["P2"]["nets"])
        lc = out["P1"]["live_net"] + out["P2"]["live_net"]
        lines.append(f"\n== both probes: replay net {comb.mean():+.4f} SOL [p5 {np.percentile(comb, 5):+.4f}, p95 {np.percentile(comb, 95):+.4f}] vs live {lc:+.4f} -> diff {comb.mean() - lc:+.4f}; "
                     f"fills {out['P1']['fills_mean'] + out['P2']['fills_mean']:.1f} vs {out['P1']['live_fills'] + out['P2']['live_fills']}")
    lines.append(f"\n{time.time() - t0:.0f} s")
    txt = "\n".join(lines)
    print(txt)
    open(f"{OUT}/calib_{A.tag}.txt", "w").write(txt + "\n")
    json.dump(out, open(f"{OUT}/calib_{A.tag}.json", "w"), indent=1)
