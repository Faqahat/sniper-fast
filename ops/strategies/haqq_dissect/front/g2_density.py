#!/usr/bin/env python3
"""FRONT addendum step 2 (read-only, MEASURED): k4 vs k8 pre-send in the live runs.
(c) try spacing and landing (slot after send, block position, send->rx ms), per client;
(d) rate-cap refusals (run_end not_sent; rate_path = CLI path bucket, rate_path_config = the path's [[send]] max_per_sec);
(a) per dump in an armed window (dv8 dump universe, tape to 10-28 01:12 PKT): our first landed try after the dump - ms (chain clock),
    same-slot share, block position, outside buys ahead, filled;
(b) the same on paying dumps (front value vf >= +30 mSOL), plus fill rate and realized P&L per hour by group.
FRA27 (after the tape) is added by g3_r27.py. Out: sniper-data/haqq_dissect/front/g2.txt, g2_rows.pkl"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
GROUP = {"AMS17": "k8 cap30", "AMS19": "k8 cap30", "AMS32": "k8 cap30", "AMS33": "k8 cli40/cfg30", "FRA26": "k8 cli40/cfg20", "FRA27": "k8 cli40/cfg20"}
def grp(run): return GROUP.get(run, "k4 cap20")
GORD = ["k4 cap20", "k8 cap30", "k8 cli40/cfg30", "k8 cli40/cfg20"]
s0, bsz = L.slot_sizes(); SMAX = s0 + len(bsz) - 1
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
pc = lambda v, q: float(np.percentile(v, q)) if len(v) else float("nan")


def main():
    RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb"))
    P("# Pre-send k4 vs k8, live runs (MEASURED)")
    P("Groups: k4 cap20 = AMS16,20,24-31, FRA21-24 | k8 cap30 = AMS17,19,32 | k8 cli40/cfg30 = AMS33 | k8 cli40/cfg20 = FRA26, FRA27 (CLI 40/s but helius-ps [[send]] max_per_sec 20 on FRA, 30 on AMS)")
    # ---------- (d) + (c) per run
    P("\n## (c)+(d) Per run: tries, refusals, spacing, landing")
    P("| run | group | hours | armed windows | tries sent | refused: rate_path / rate_path_config / rate_global | refused share | try gap ms p10/p50/p90 | gaps > 1.5x nominal | tries per armed slot | landed in send slot / next / later | block pos p25/p50/p75 (send-slot landings) | send->rx ms p50 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    G = collections.defaultdict(lambda: collections.defaultdict(list))
    for run in sorted(RU, key=lambda r: (r[:3], int(r[3:]))):
        x = RU[run]; k = x["cfg"]["k"]; nom = 212.0 / k; g = grp(run)
        T = x["tries"]
        byw = collections.defaultdict(list)
        for t in T: byw[(t["w"], t["mint"])].append(t)
        gaps = []; tps = []
        for v in byw.values():
            ts = sorted(t["t_send"] for t in v if t.get("t_send"))
            if len(ts) >= 2:
                d = np.diff(ts) * 1000; gaps += [z for z in d if z < 1000]
                ss = [t["send_slot"] for t in v]; span = max(ss) - min(ss) + 1; tps.append(len(v) / span)
        gaps = np.array(gaps)
        land = [t for t in T if t.get("slot") is not None and t.get("idx") is not None]
        sa = np.array([t["slot"] - t["send_slot"] for t in land])
        bp = np.array([t["idx"] / bsz[t["slot"] - s0] for t in land if t["slot"] == t["send_slot"] and s0 <= t["slot"] <= SMAX])
        ms = np.array([t["ms_rx"] for t in land if t.get("ms_rx") is not None])
        ns = (x["rend"] or {}).get("not_sent") or {}
        rp, rc, rg = ns.get("rate_path", 0), ns.get("rate_path_config", 0), ns.get("rate_global", 0)
        P(f"| {run} | {g} | {(x['t1']-x['t0'])/3600:.1f} | {len(x['arms'])} | {len(T):,} | {rp} / {rc} / {rg}{'' if x['rend'] else ' (no run_end)'} | "
          f"{100*(rp+rc+rg)/max(len(T)+rp+rc+rg,1):.0f}% | {pc(gaps,10):.0f}/{pc(gaps,50):.0f}/{pc(gaps,90):.0f} | {100*np.mean(gaps>1.5*nom) if len(gaps) else float('nan'):.0f}% | "
          f"{np.median(tps) if tps else float('nan'):.2f} | {100*np.mean(sa==0):.0f}% / {100*np.mean(sa==1):.0f}% / {100*np.mean(sa>=2):.0f}% | "
          f"{pc(bp,25):.2f}/{pc(bp,50):.2f}/{pc(bp,75):.2f} | {pc(ms,50):.0f} |")
        G[g]["gaps"] += list(gaps); G[g]["tps"] += tps; G[g]["sa"] += list(sa); G[g]["bp"] += list(bp); G[g]["ms"] += list(ms)
        G[g]["ref"].append(rp + rc + rg); G[g]["sent"].append(len(T)); G[g]["h"].append((x["t1"] - x["t0"]) / 3600)
        for t in land:
            G[g]["cl:" + str(t["client"])].append((t["slot"] - t["send_slot"], t.get("ms_rx")))
    P("\n| group | hours | refused share | try gap ms p25/p50/p75 | gaps > 1.5x nominal | tries per armed slot p50 | landed send slot / next / later | block pos p50 | send->rx ms p50 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for g in GORD:
        d = G[g]
        if not d["sent"]: continue
        gp = np.array(d["gaps"]); sa = np.array(d["sa"]); nom = 212.0 / (4 if g.startswith("k4") else 8)
        P(f"| {g} | {sum(d['h']):.1f} | {100*sum(d['ref'])/(sum(d['sent'])+sum(d['ref'])):.0f}% | {pc(gp,25):.0f}/{pc(gp,50):.0f}/{pc(gp,75):.0f} (nominal {nom:.0f}) | "
          f"{100*np.mean(gp>1.5*nom):.0f}% | {np.median(d['tps']):.2f} | {100*np.mean(sa==0):.0f}% / {100*np.mean(sa==1):.0f}% / {100*np.mean(sa>=2):.0f}% | {pc(d['bp'],50):.2f} | {pc(d['ms'],50):.0f} |")
    P("\n### Landing by leader client (all groups pooled; landed slot - send slot, send->rx ms)")
    P("| client | k4: tries | k4: same slot | k4: rx ms p50 | k8: tries | k8: same slot | k8: rx ms p50 |")
    P("|---|---|---|---|---|---|---|")
    cls = sorted({k[3:] for g in G for k in G[g] if k.startswith("cl:")}, key=lambda c: -len(G["k4 cap20"].get("cl:" + c, [])))
    for c in cls:
        a = G["k4 cap20"].get("cl:" + c, []); b = [z for g in GORD[1:] for z in G[g].get("cl:" + c, [])]
        if len(a) + len(b) < 200: continue
        f = lambda v: (len(v), 100 * np.mean([z[0] == 0 for z in v]) if v else float("nan"), pc([z[1] for z in v if z[1] is not None], 50))
        A = f(a); B = f(b)
        P(f"| {c} | {A[0]:,} | {A[1]:.0f}% | {A[2]:.0f} | {B[0]:,} | {B[1]:.0f}% | {B[2]:.0f} |")
    # ---------- (a)+(b) dumps in armed windows (tape)
    R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); ids, idm = L.ids_map()
    bym = collections.defaultdict(list)
    for r in R: bym[ids[r["mint"]]].append(r)
    rows = []
    for run, x in RU.items():
        g = grp(run)
        trw = collections.defaultdict(list)
        for t in x["tries"]:
            if t.get("slot") is not None and t.get("idx") is not None: trw[(t["w"], t["mint"])].append(t)
        for a in x["arms"]:
            if a["arm_slot"] is None: continue
            v = trw.get((a["w"], a["mint"]), [])
            end = a["end_slot"] if a["end_slot"] is not None else (max([t["send_slot"] for t in v]) if v else a["arm_slot"] + 10)
            if end > SMAX: continue
            for r in bym.get(a["mint"], []):
                if not (a["arm_slot"] <= r["ds"] <= end): continue
                aft = [t for t in v if (t["slot"], t["idx"]) > (r["ds"], r["di"]) and t["slot"] <= r["ds"] + 2]
                bef = [t for t in v if (t["slot"], t["idx"]) < (r["ds"], r["di"]) and t["slot"] >= r["ds"] - 1]
                rec = dict(run=run, g=g, mint=a["mint"], ds=r["ds"], di=r["di"], drop=r["drop"], vf=r["vf"], day=L.day_of(r["bt"]), nbef=len(bef),
                           f1ms=next((f["ms"] for f in r["front"] if not f["ours"]), None), real=x["real"].get((a["w"], a["mint"])))
                if aft:
                    t = min(aft, key=lambda t: (t["slot"], t["idx"]))
                    ms = float(L.cc(t["slot"], t["idx"]) - r["cc"])
                    ahead = sum(1 for f in r["front"] if not f["ours"] and (f["slot"], f["idx"]) < (t["slot"], t["idx"]))
                    rec.update(ms=ms, same=t["slot"] == r["ds"], bp=t["idx"] / bsz[t["slot"] - s0], ahead=ahead, ok=t.get("res") == "ok",
                               anyok=any(z.get("res") == "ok" for z in aft), client=t["client"])
                rows.append(rec)
    pickle.dump(rows, open(f"{OUT}/g2_rows.pkl", "wb"))
    def tab(title, sel):
        P(f"\n## {title}")
        P("| group | dumps | a try landed <= 2 slots after | first try ms p25/p50/p75 | same slot | block pos p50 | buys ahead p50 | first (0 ahead) | first try filled | any try filled | front #1 ms p50 |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        for g in GORD:
            v = [r for r in rows if r["g"] == g and sel(r)]
            if not v: continue
            a = [r for r in v if "ms" in r]
            ms = [r["ms"] for r in a]
            P(f"| {g} | {len(v):,} | {100*len(a)/len(v):.0f}% | {pc(ms,25):.0f}/{pc(ms,50):.0f}/{pc(ms,75):.0f} | {100*np.mean([r['same'] for r in a]) if a else float('nan'):.0f}% | "
              f"{pc([r['bp'] for r in a],50):.2f} | {pc([r['ahead'] for r in a],50):.0f} | {100*np.mean([r['ahead']==0 for r in a]) if a else float('nan'):.0f}% | "
              f"{100*np.mean([r['ok'] for r in a]) if a else float('nan'):.0f}% | {100*np.mean([r['anyok'] for r in a]) if a else float('nan'):.0f}% | "
              f"{pc([r['f1ms'] for r in v if r['f1ms'] is not None],50):.1f} |")
    tab("(a) all dumps >= 12% in armed windows (crossing size)", lambda r: r["drop"] >= 0.12)
    tab("(a) all dumps >= 5% in armed windows", lambda r: True)
    tab("(b) PAYING dumps (front value vf >= +30 mSOL) in armed windows", lambda r: r["vf"] >= 0.030)
    tab("(b) non-paying dumps >= 12% in armed windows", lambda r: not (r["vf"] >= 0.030) and r["drop"] >= 0.12)
    # P&L per hour by group (realized windows + failed-try fees)
    P("\n## (b) Realized P&L by group (wallet-realized per window, MEASURED; failed tries x 5,120 lamports)")
    P("| group | hours | windows | fills | realized SOL | failed-try fees SOL | net SOL/h | fills/h |")
    P("|---|---|---|---|---|---|---|---|")
    for g in GORD:
        rs = [r for r in RU if grp(r) == g]
        if not rs: continue
        h = sum((RU[r]["t1"] - RU[r]["t0"]) / 3600 for r in rs)
        re = sum(sum(RU[r]["real"].values()) for r in rs) / 1e9
        nf = sum(len(RU[r]["fills"]) for r in rs)
        ff = sum(sum(1 for t in RU[r]["tries"] if t.get("res") not in ("ok", None, "unseen")) for r in rs) * 5120 / 1e9
        P(f"| {g} | {h:.1f} | {sum(len(RU[r]['arms']) for r in rs):,} | {nf} | {re:+.3f} | {ff:.3f} | {(re-ff)/h:+.3f} | {nf/h:.1f} |")
    open(f"{OUT}/g2.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
