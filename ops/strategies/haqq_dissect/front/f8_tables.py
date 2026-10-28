#!/usr/bin/env python3
"""FRONT step 8 (read-only): the tables for the report.
Value of a paying dump = vpos1 = a 0.40 SOL buy inserted just before front buyer #1 (wave exit, exact curve, gross, fol 1.0; INFERRED
upper bound, MEASURED tape). Days: D2..D5 full (10-23 23:15 -> 10-27 23:15 PKT), D6 partial (to 10-28 01:12).
Out: sniper-data/haqq_dissect/front/f8_tables.txt, f8_rows.pkl"""
import pickle, collections, sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/front")
import dv8lib as L
from f4_join import region_of
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
rng = np.random.default_rng(11)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
FULL = (2, 3, 4, 5)


def boot(v, f=np.sum, n=1000):
    v = np.asarray(v, float)
    if len(v) == 0: return (0.0, 0.0)
    b = [f(v[rng.integers(0, len(v), len(v))]) for _ in range(n)]
    return np.percentile(b, 5), np.percentile(b, 95)


def main():
    R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); SE = pickle.load(open(f"{OUT}/f2_sets.pkl", "rb"))
    F4 = {x["i"]: x for x in pickle.load(open(f"{OUT}/f4.pkl", "rb")) if x["set"] == "S"}
    F6 = {x["i"]: x for x in pickle.load(open(f"{OUT}/f6.pkl", "rb")) if x["set"] == "S"}
    W = pickle.load(open(f"{OUT}/f7.pkl", "rb"))
    ids, _ = L.ids_map()
    OT = {(x["s"], x["i"]): x for x in pickle.load(open("/home/moiz/sniper-data/haqq_dissect/exec/txs.pkl", "rb")) if x["w"] in ("FRA", "AMS")}
    rows = []
    for i in SE["S"]:
        r = R[i]; x = F4[i]; f6 = F6.get(i); w = W.get(i)
        v = r["front"][0]["vpos"]
        f1 = r["front"][0]
        sh1 = f6["front"][0]["shape"] if f6 and f6["front"] and f6["front"][0]["shape"] else None
        pres = None
        if w:
            b = [a for a in w["after"] if a["buy"] and a["ok"] and not a["ours"]]
            if b: pres = b[0]["pre_fail"] > 0
        # our status
        up = x["up"]["AMS"] or x["up"]["FRA"]
        tr = [t for t in x["tries"] if t.get("slot") is not None]
        tr_after = [t for t in tr if t["rel"] in ("same", "next", "later")]
        tr_before = [t for t in tr if t["rel"] == "before"]
        ft = x["ft"]
        regv = list(x["reg"].values())
        ourbest = None
        cands = [(t["slot"], t["idx"], "ps", t.get("ahead"), t.get("ms"), t.get("res"), t["srv"]) for t in tr_after]
        if ft and ft.get("us"): cands.append((ft["us"][0], ft["us"][1], "reg", ft.get("ahead"), ft.get("ms"), ft["out"], ft["srv"]))
        if cands: ourbest = min(cands)
        captured = bool(ourbest and ourbest[3] == 0 and ourbest[5] in ("ok", "fill"))
        if not up: st = "1 engine down"
        elif x["armed"] or tr:
            if captured: st = "8 captured (we were first buyer)"
            elif not tr_after and tr_before: st = "6a pre-send: tries landed only BEFORE the dump"
            elif not tr_after: st = "6b pre-send armed: no landed try around the dump"
            elif ourbest and ourbest[3] == 0: st = "6d pre-send: try landed FIRST after the dump but failed our limit"
            else: st = "6c pre-send: try landed after the dump, behind"
        elif ft is not None:
            st = "8 captured (we were first buyer)" if captured else ("7b regular: landed first but failed the +5% guard" if (ourbest and ourbest[3] == 0) else "7 regular fired, behind")
        else:
            if not regv: st = "2 not a dump for the engine (its thresholds)"
            else:
                vv = regv[0]
                if vv["skip"] == "far_leader": st = "4 regular: far-leader skip"
                elif vv["skip"]: st = "5 regular: other skip (" + str(vv["skip"]) + ")"
                elif not vv["gate"]: st = "3 regular: gate refused"
                else: st = "5 regular: other skip (gate pass, no fire)"
        ps_why = (x["pskip"][-1][2] if x["pskip"] else "no whale trigger") if not x["armed"] else "armed"
        lost_to = None
        if st.startswith(("6c", "7 ")):
            if x["region"] != "EU": lost_to = "far leader (non-EU)"
            elif pres: lost_to = "pre-sender ahead"
            elif sh1 and sh1["jito"] and f1["slot"] == r["ds"] and f1["idx"] - r["di"] <= 2: lost_to = "Jito-tip tx right after dump"
            else: lost_to = "reactive buyer faster (EU leader)"
        our_path = None
        if ourbest:
            o = OT.get((ourbest[0], ourbest[1]))
            our_path = ("pre-send:" if ourbest[2] == "ps" else "regular:") + (o["path"] if o else "?")
        rows.append(dict(i=i, mint=ids[r["mint"]], ds=r["ds"], di=r["di"], day=x["day"], v=v, vf=r["vf"], client=x["client"], region=x["region"], st=st,
                         ps_why=ps_why, lost_to=lost_to, pres=pres, sh1=sh1, f1=f1, ourbest=ourbest, our_path=our_path, ft=ft, tries=tr,
                         armed=bool(x["armed"]), nearF=x["nearF"], nearA=x["nearA"], up=x["up"], dump_sh=f6["dump"] if f6 else None))
    # S+ : paying dumps where OUR buy was first after the dump (excluded from S by construction; value = vf, the front value)
    for i, r in enumerate(R):
        if not (r["front"] and r["front"][0]["ours"] and r["front"][0]["dsl"] == 0 and r["vf"] >= 0.030): continue
        f1 = r["front"][0]; o = OT.get((f1["slot"], f1["idx"]))
        ld = L.leader_of(r["ds"]); _, CL, _ = L._sched()
        x4 = dict(region=region_of(ld))
        rows.append(dict(i=i, mint=ids[r["mint"]], ds=r["ds"], di=r["di"], day=L.day_of(r["bt"]), v=r["vf"], vf=r["vf"], client=L.client_class(CL.get(ld, "")) if ld else "?",
                         region=x4["region"], st="8 captured (we were first buyer)", ps_why="", lost_to=None, pres=None, sh1=None, f1=f1,
                         ourbest=(f1["slot"], f1["idx"], "ps" if (o and o["fee"] < 10000) else "reg", 0, f1["ms"], "ok", "?"),
                         our_path=(("pre-send:" if (o and o["fee"] < 10000) else "regular:") + (o["path"] if o else "?")), ft=None, tries=[], armed=None,
                         nearF=None, nearA=None, up=dict(AMS=True, FRA=True), dump_sh=None, splus=True))
    pickle.dump(rows, open(f"{OUT}/f8_rows.pkl", "wb"))
    D = collections.Counter(r["day"] for r in rows)
    nd = len(FULL)
    # ---------------- T1
    P("# FRONT tables (MEASURED tape/raw/run records; values INFERRED = 0.40 SOL wave value at front buyer #1's position, gross, fol 1.0)")
    P(f"Paying set S: front buyer #1 lands in the dump's own slot and a 0.40 SOL buy just before it is worth >= +30 mSOL. n = {len(rows):,}")
    P("\n## T1. Paying dumps per day")
    P("| day | dumps | front value SOL (sum) | front #1 ms after dump p25/p50/p75 | idx gap <= 2 | front #1 pre-sender | front #1 Jito tip |")
    P("|---|---|---|---|---|---|---|")
    for d in sorted(D):
        g = [r for r in rows if r["day"] == d]
        ms = np.array([r["f1"]["ms"] for r in g]); gap = np.array([r["f1"]["idx"] - r["di"] for r in g])
        pr = [r["pres"] for r in g if r["pres"] is not None]; jt = [r["sh1"]["jito"] for r in g if r["sh1"]]
        P(f"| {L.day_name(d)} | {len(g):,} | {sum(r['v'] for r in g):+.1f} | {np.percentile(ms,25):.1f} / {np.median(ms):.1f} / {np.percentile(ms,75):.1f} | "
          f"{100*np.mean(gap<=2):.0f}% | {100*np.mean(pr):.0f}% (n {len(pr):,}) | {100*np.mean(jt):.1f}% |")
    # ---------------- T2 who
    P("\n## T2. Who lands first (front buyer #1) on paying dumps — top wallets")
    c = collections.Counter(ids[r["f1"]["signer"]] for r in rows)
    P("| wallet | front #1 count | share | pre-sender share | ms p50 | idx gap<=2 | main service | CU price p50 | router | days present |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for wl, n in c.most_common(15):
        g = [r for r in rows if ids[r["f1"]["signer"]] == wl]
        pr = [r["pres"] for r in g if r["pres"] is not None]
        sv = collections.Counter(p for r in g if r["sh1"] for p in r["sh1"]["paths"]).most_common(2)
        cup = [r["sh1"]["cup"] for r in g if r["sh1"] and r["sh1"]["cup"]]
        rt = collections.Counter(r["sh1"]["router"] for r in g if r["sh1"]).most_common(1)
        P(f"| {wl} | {n} | {100*n/len(rows):.1f}% | {100*np.mean(pr) if pr else float('nan'):.0f}% | {np.median([r['f1']['ms'] for r in g]):.1f} | "
          f"{100*np.mean([(r['f1']['idx']-r['di'])<=2 for r in g]):.0f}% | {', '.join(f'{p} {100*k/len(g):.0f}%' for p,k in sv)} | "
          f"{np.median(cup) if cup else float('nan'):,.0f} | {rt[0][0] if rt else '?'} | {len(set(r['day'] for r in g))} |")
    hq = [r for r in rows if ids[r["f1"]["signer"]] == L.HAQQ]
    hc = collections.Counter((r["sh1"]["cup"] % 1000) if r["sh1"] and r["sh1"]["cup"] else None for r in hq)
    P(f"- haqq as front #1: {len(hq)} ({100*len(hq)/len(rows):.1f}%); bot codes {dict(hc.most_common(6))}; ms p50 {np.median([r['f1']['ms'] for r in hq]):.1f}")
    top50 = sum(n for _, n in c.most_common(50)) / len(rows)
    P(f"- distinct front #1 wallets {len(c):,}; top 10 = {100*sum(n for _, n in c.most_common(10))/len(rows):.0f}%, top 50 = {100*top50:.0f}%")
    # ---------------- T3 our status
    P("\n## T3. Our side on the paying dumps (status is exclusive; value = front value of those dumps, SOL/day mean of D2..D5 [90% bootstrap])")
    P("| status | dumps | share | front value SOL/day | per day D2/D3/D4/D5 |")
    P("|---|---|---|---|---|")
    tot = sum(r["v"] for r in rows if r["day"] in FULL) / nd
    for st in sorted(set(r["st"] for r in rows)):
        g = [r for r in rows if r["st"] == st]
        gv = [r["v"] for r in g if r["day"] in FULL]
        lo, hi = boot(gv)
        P(f"| {st} | {len(g):,} | {100*len(g)/len(rows):.1f}% | {sum(gv)/nd:+.2f} [{lo/nd:+.2f}..{hi/nd:+.2f}] | " +
          " / ".join(f"{sum(r['v'] for r in g if r['day']==d):+.1f}" for d in FULL) + " |")
    P(f"| total | {len(rows):,} | 100% | {tot:+.2f} | |")
    nf = [r for r in rows if r["up"]["AMS"] or r["up"]["FRA"]]
    nar = [r for r in nf if not r["armed"] and not r["tries"]]
    P("- pre-send not armed (engine up): why the token was not armed at the dump (latest pre-send skip on the mint, else no whale trigger): " +
      ", ".join(f"{k} {v}" for k, v in collections.Counter(r["ps_why"] for r in nar).most_common(8)))
    # ---------------- T4 region x client
    P("\n## T4. By the dump slot's leader: region (IP geo) and client")
    for key in ("region", "client"):
        P(f"\n| {key} | dumps | value share | front #1 ms p50 | front #1 pre-sender | we attempted | our first landed try/fire ms p50 | our buys ahead p50 | we were first | front value SOL/day |")
        P("|---|---|---|---|---|---|---|---|---|---|")
        tv = sum(r["v"] for r in rows)
        for k in sorted(set(r[key] for r in rows), key=lambda k: -sum(r["v"] for r in rows if r[key] == k)):
            g = [r for r in rows if r[key] == k]
            if len(g) < 20: continue
            at = [r for r in g if r["ourbest"]]
            pr = [r["pres"] for r in g if r["pres"] is not None]
            P(f"| {k} | {len(g):,} | {100*sum(r['v'] for r in g)/tv:.1f}% | {np.median([r['f1']['ms'] for r in g]):.1f} | {100*np.mean(pr) if pr else float('nan'):.0f}% | "
              f"{len(at):,} | {np.median([r['ourbest'][4] for r in at]) if at else float('nan'):.1f} | {np.median([r['ourbest'][3] for r in at]) if at else float('nan'):.0f} | "
              f"{sum(r['st'].startswith('8') for r in g)} | {sum(r['v'] for r in g if r['day'] in FULL)/nd:+.2f} |")
    # ---------------- T5 paths x client (window data: every landed buy in the dump slot after the dump)
    P("\n## T5. Same-slot rank of each landing service after a paying dump, per leader client (window data: every landed buy in the dump's slot after it; rank 0 = first)")
    P("lift = share of front #1 buys using the service / share of all same-slot buys using it (>1 = over-represented at the front)")
    for cl in ("bam", "harmonic", "jito", "fd"):
        allb = collections.defaultdict(list); first = collections.Counter(); nfirst = 0; nall = 0
        for r in rows:
            if r["client"] != cl or r["i"] not in W: continue
            b = [a for a in W[r["i"]]["after"] if a["buy"] and a["ok"] and a["s"] == r["ds"]]
            for k, a in enumerate(b):
                if a["ours"]:
                    o = OT.get((a["s"], a["i"]))
                    keys = ["OURS:" + ("pre-send" if (o and o["fee"] < 10000) else "regular") + ":" + (o["path"] if o else "?")]
                else:
                    keys = a["sh"]["paths"] + (["pre-sender"] if a["pre_fail"] > 0 else [])
                for p in keys: allb[p].append(k)
                nall += 1
                if k == 0:
                    nfirst += 1
                    for p in keys: first[p] += 1
        P(f"\n### {cl}: dumps with window data, {nall:,} same-slot buys, {nfirst:,} front #1")
        P("| service | buys | rank p50 | rank p25 | front #1 share of its buys | share of front #1 | lift |")
        P("|---|---|---|---|---|---|---|")
        for p, v in sorted(allb.items(), key=lambda z: -len(z[1])):
            if len(v) < 25 and not p.startswith("OURS"): continue
            v = np.array(v)
            sf = first[p] / max(nfirst, 1); sa = len(v) / max(nall, 1)
            P(f"| {p} | {len(v):,} | {np.median(v):.0f} | {np.percentile(v,25):.0f} | {100*np.mean(v==0):.1f}% | {100*sf:.1f}% | {sf/sa:.2f} |")
    # ---------------- T6 decomposition
    P("\n## T6. Where the paying-dump value goes (exclusive causes; SOL/day of front value, D2..D5 mean)")
    cause = collections.defaultdict(float); cn = collections.Counter()
    for r in rows:
        if r["day"] not in FULL: continue
        st = r["st"]
        if st.startswith("1"): k = "A not running (no engine up)"
        elif st.startswith(("2", "3", "5")): k = "B not armed / not fired: engine threshold, gate or other skip"
        elif st.startswith("4"): k = "C not fired: far-leader skip"
        elif st.startswith("6a"): k = "D armed, but every try landed BEFORE the dump (timing miss)"
        elif st.startswith("6b"): k = "D2 armed, no try landed near the dump"
        elif st.startswith(("6d", "7b")): k = "E0 landed first but our price limit failed (dump smaller than our trigger/guard)"
        elif st.startswith(("6c", "7")): k = "E attempted, landed behind: " + r["lost_to"]
        else: k = "F captured (we were first)"
        cause[k] += r["v"] / nd; cn[k] += 1
    tt = sum(cause.values())
    P("| cause | dumps (D2..D5) | SOL/day | share |")
    P("|---|---|---|---|")
    for k in sorted(cause): P(f"| {k} | {cn[k]:,} | {cause[k]:+.2f} | {100*cause[k]/tt:.1f}% |")
    open(f"{OUT}/f8_tables.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
