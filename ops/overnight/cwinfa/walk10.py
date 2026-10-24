#!/usr/bin/env python3
# READ-ONLY, offline: the CWiNFA deployer list (walk-forward, + gate) traded with a ~10 s hold, scored on GENERIC flow only
# (CWiNFA + the 412 fast sniper wallets' trades after our entry removed) and with slip (followers our buy prices out fail).
# Outcomes for every launch (R1 proxy placement, R2 block-order placement with our timelines) of any deployer CWiNFA ever
# attempted; our 1% guard; 0.5 SOL; our costs. The gate uses OUR OWN realistic results (base, with the bots) of the same
# exit on that deployer's earlier launches, known 60 s after each launch.
import os, sys, json, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; SH = "/home/moiz/sniper-data/collect/shadow"
L = rp.load_launches(); O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
DEPS = {L[m]["user"] for m in ATT if m in L}
FAST = set(json.load(open(os.path.join(HERE, "fast_snipers.json")))) | {W}
todo = [m for m, c in L.items() if c.get("bt") and c["user"] in DEPS and "InitializeMayhemState" not in (c.get("ixn") or []) and (c["run"] == "R1" or m in O)]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
RULES = [rp.R("eos", [(1.0, ("slot", 1))], 5), rp.R("t5", [(1.0, ("t", 5))], 6), rp.R("t10", [(1.0, ("t", 10))], 11)]
SL = None
def slipmap():
    global SL
    if SL is None:
        SL = dict(rp.load_slip())
        for r in json.load(open(os.path.join(HERE, "ledger_CWiNFA.json")))["txs"]:
            if not r.get("missing") and (r.get("router") or {}).get("tag") == 2: SL[r["sig"]] = ("sol", 1_000_000_000, r["router"]["min_out"])
    return SL
def filt(tr, ib, rm, ins):
    pre = {t["user"] for t in tr[:ib] if t["buy"]}
    return tr[:ib] + [t for t in tr[ib:] if not (t["user"] in rm and t["user"] not in pre and t["user"] not in ins)]
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(run=run, bt=c["bt"], dep=c["user"])
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[str(Lm)] = None; continue
            d = {}
            for name, trx, sl in (("base", tr, None), ("generic", filt(tr, ib, FAST, st["insiders"]), None), ("generic_slip", filt(tr, ib, FAST, st["insiders"]), slipmap())):
                o = rp.sim(trx, c, st, ib, 0.5, RULES, fill_pen=0.015, slip=sl)
                d[name] = {k: v["pnl"] for k, v in o.items()} if o else None
            bs = max(c["slot"], tr[ib - 1]["s"]); g2 = filt(tr, ib, FAST, st["insiders"])
            win = lambda trx, n: sum(1 for t in trx[ib:] if t["s"] <= bs + n and t["buy"] and t["user"] not in st["insiders"])
            d["nbuy"] = dict(eos=[win(tr, 1), win(g2, 1)], t10=[win(tr, int(10000 / rp.SLOT_MS)), win(g2, int(10000 / rp.SLOT_MS))])
            r[str(Lm)] = d
        out[m] = r
    return out
def walk(RS, Lm, exit_, run, k=2, rate=0.10, kmin=3, thr=0.0, gate=True):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    natt = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; picks = []
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; r = RS.get(m)
        listed = natt[d] >= k and (nl[d] == 0 or natt[d] / nl[d] >= rate)
        gok = not (gate and len(hist[d]) >= kmin and statistics.mean(hist[d]) < thr)
        if r and r["run"] == run and str(Lm) in r and listed and gok: picks.append(m)
        if r and str(Lm) in r and r[str(Lm)] and r[str(Lm)]["base"]: pend.append((bt + 60, d, r[str(Lm)]["base"][exit_])); pend.sort()
        nl[d] += 1
        if m in ATT: natt[d] += 1
    return picks
if __name__ == "__main__":
    if os.environ.get("REUSE") and os.path.exists(os.path.join(HERE, "walk10.json")): RS = json.load(open(os.path.join(HERE, "walk10.json")))
    else:
        RS = {}
        with Pool(8) as p:
            for o in p.imap_unordered(work, sorted(byb)): RS.update(o)
        json.dump(RS, open(os.path.join(HERE, "walk10.json"), "w"))
    lines = []; SUMM = {}
    for run in ("R2", "R1"):
        for Lm in (45, 75):
            for exit_ in ("eos", "t5", "t10"):
                for gname, gk in (("gate", True), ("no gate", False)):
                    P = walk(RS, Lm, exit_, run, gate=gk)
                    v = sorted(((RS[m]["bt"], RS[m][str(Lm)]) for m in P if str(Lm) in RS[m]), key=lambda z: z[0])
                    if not v: continue
                    t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2; cells = []
                    for name in ("base", "generic", "generic_slip"):
                        xs = [(t, (x[name][exit_] if x and x.get(name) else (-0.005 if x is None else 0.0))) for t, x in v]
                        tot = sum(y for _, y in xs); a = sum(y for t, y in xs if t < mid)
                        cells.append(f"{name} {tot:+6.2f} ({a:+.2f}/{tot - a:+.2f})")
                        SUMM.setdefault(f"{run}|{Lm}|{exit_}|{gname}", {})[name] = [round(tot, 3), round(a, 3), round(tot - a, 3)]
                    fills = sum(1 for _, x in v if x)
                    SUMM[f"{run}|{Lm}|{exit_}|{gname}"]["fills"] = [fills, len(v)]
                    if exit_ in ("eos", "t10"):
                        nb = [x["nbuy"][exit_] for _, x in v if x and x.get("nbuy")]
                        if nb: SUMM[f"{run}|{Lm}|{exit_}|{gname}"]["no_outside_buy"] = [round(sum(1 for a, b in nb if a == 0) / len(nb), 3), round(sum(1 for a, b in nb if b == 0) / len(nb), 3)]
                    lines.append(f"{run} @ {Lm} ms, exit {exit_:4}, {gname:7}: fills {fills}/{len(v)} | " + " | ".join(cells))
    open(os.path.join(HERE, "walk10.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
    json.dump(SUMM, open(os.path.join(HERE, "walk10_summary.json"), "w"), indent=1)
