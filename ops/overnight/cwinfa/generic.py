#!/usr/bin/env python3
# READ-ONLY, offline: generic-flow test (owner's rule). For every R2 launch with our timeline in the bundled pool
# (dev buy >= 1 SOL + glued bundle) plus CWiNFA's attempts: our guarded entry at 45 / 75 ms (place_bo2, 1% guard), then
# holds of end-of-next-slot / 1 s / 5 s / 10 s / 30 s, 0.5 SOL with our costs, scored three ways:
#   base | minus CWiNFA + all fast sniper wallets' trades after our entry (generic flow only) | the same + slip
# (followers our buy prices out fail; rp.load_slip() + CWiNFA's own min-outs). Output generic.json / generic.txt by subset.
import os, sys, json, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; SH = "/home/moiz/sniper-data/collect/shadow"
L = rp.load_launches(); O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
R = json.load(open(os.path.join(HERE, "replay_all.json"))); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
FAST = set(json.load(open(os.path.join(HERE, "fast_snipers.json")))) | {W}
pool = [m for m, r in R.items() if r["run"] == "R2" and ((r["dev"] >= 1 and r["glued"] >= 1) or m in ATT)]
byb = collections.defaultdict(set)
for m in pool: byb[rp.bucket(m)].add(m)
RULES = [rp.R("eos", [(1.0, ("slot", 1))], 5), rp.R("t1", [(1.0, ("t", 1))], 2), rp.R("t5", [(1.0, ("t", 5))], 6), rp.R("t10", [(1.0, ("t", 10))], 11), rp.R("t30", [(1.0, ("t", 30))], 31)]
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
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if m not in O: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[str(Lm)] = None; continue
            d = {}
            for name, trx, sl in (("base", tr, None), ("generic", filt(tr, ib, FAST, st["insiders"]), None), ("generic_slip", filt(tr, ib, FAST, st["insiders"]), slipmap())):
                o = rp.sim(trx, c, st, ib, 0.5, RULES, fill_pen=0.015, slip=sl)
                d[name] = {k: v["pnl"] for k, v in o.items()} if o else None
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(os.path.join(HERE, "generic.json"), "w"))
    T = {x["mint"]: x for x in json.load(open(os.path.join(HERE, "table_slim.json")))}
    def host(m): return ((T.get(m) or {}).get("uri_host") or "")
    SUB = {"CWiNFA's attempts (oracle)": lambda m: m in ATT,
           "pool: dev >= 1 SOL + glued bundle (all)": lambda m: R[m]["dev"] >= 1 and R[m]["glued"] >= 1,
           "pool, dev >= 2.5 SOL + 3-tx bundle": lambda m: R[m]["dev"] >= 2.5 and R[m]["glued"] == 3,
           "pool, launcher J7Tracker / Uxento": lambda m: R[m]["dev"] >= 1 and R[m]["glued"] >= 1 and ("j7tracker" in host(m) or "uxento" in host(m))}
    lines = []; SUMM = {}
    for sname, f in SUB.items():
        ms = [m for m in res if f(m)]
        for Lm in (45, 75):
            v = [res[m].get(str(Lm), "x") for m in ms]
            n = sum(1 for x in v if x != "x"); fails = sum(1 for x in v if x is None); fills = [x for x in v if x not in ("x", None)]
            if not fills: continue
            cells = []
            for k in ("eos", "t1", "t5", "t10", "t30"):
                b = sum(x["base"][k] for x in fills if x["base"]) - 0.005 * fails; g = sum(x["generic"][k] for x in fills if x["generic"]) - 0.005 * fails
                gs = sum(x["generic_slip"][k] for x in fills if x["generic_slip"]) - 0.005 * fails
                cells.append(f"{k}: {b:+.2f} / {g:+.2f} / {gs:+.2f}")
                SUMM[f"{sname}|{Lm}|{k}"] = dict(base=round(b, 3), generic=round(g, 3), generic_slip=round(gs, 3), fills=len(fills), n=n)
            lines.append(f"{sname} @ {Lm} ms: {n} launches, {len(fills)} guarded fills | base / generic-only / generic+slip (SOL): " + " | ".join(cells))
    open(os.path.join(HERE, "generic.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
    json.dump(SUMM, open(os.path.join(HERE, "generic_summary.json"), "w"), indent=1)
