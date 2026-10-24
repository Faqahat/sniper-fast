#!/usr/bin/env python3
# READ-ONLY, offline: owner's rule check for the CWiNFA copy ideas (question 6): does the profit come from GENERIC flow or
# from specific bots buying right after us? For the guarded fills of (a) the oracle (its attempts) and (b) the walk-forward
# list + gate, at 45 / 75 ms, our pattern (0.5 SOL, sell at the end of the next slot) and its pattern (1 SOL, sell at 1 s):
#   base | minus CWiNFA's buys after our entry | minus CWiNFA + all fast sniper wallets | minus those + top-10 after-us
#   buyers | slip (followers our buy prices out fail: rp.load_slip() + CWiNFA's own min-outs) | slip + all removals.
# A removed wallet loses its trades after our entry only if it had not bought before us (its later sell goes too).
# Also: share of fills with NO outside buy between our buy and our sell, and the top-10 after-us buyers (pass 1).
import os, sys, json, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
SH = "/home/moiz/sniper-data/collect/shadow"
L = rp.load_launches(); O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
R = json.load(open(os.path.join(HERE, "replay_all.json"))); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
FAST = set(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
def walk(Lm, k=2, rate=0.10, kmin=3, thr=0.0):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    natt = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; picks = []
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; r = R.get(m)
        if r and r["run"] == "R2" and str(Lm) in r and natt[d] >= k and (nl[d] == 0 or natt[d] / nl[d] >= rate) and not (len(hist[d]) >= kmin and statistics.mean(hist[d]) < thr): picks.append(m)
        if r and str(Lm) in r and r[str(Lm)]["ok"] and r[str(Lm)].get("eos05") is not None: pend.append((bt + 60, d, r[str(Lm)]["eos05"])); pend.sort()
        nl[d] += 1
        if m in ATT: natt[d] += 1
    return picks
SETS = {"a": {L_: [m for m, r in R.items() if r["run"] == "R2" and m in ATT and str(L_) in r] for L_ in (45, 75)},
        "b": {L_: walk(L_) for L_ in (45, 75)}}
TODO = collections.defaultdict(set)
for s in SETS.values():
    for L_, ms in s.items():
        for m in ms:
            if R[m][str(L_)]["ok"]: TODO[m].add(L_)
byb = collections.defaultdict(set)
for m in TODO: byb[rp.bucket(m)].add(m)
EOS = rp.R("eos", [(1.0, ("slot", 1))], 5); T1 = rp.R("t1", [(1.0, ("t", 1))], 2)
SLOTS_1S = int(1000 / rp.SLOT_MS) + 1
TOP = set(json.load(open(os.path.join(HERE, "after_us_top10.json")))) if os.path.exists(os.path.join(HERE, "after_us_top10.json")) else None
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
def window_buyers(tr, ib, st, nslots):
    bs = max(st["S"], tr[ib - 1]["s"]); out = []
    for t in tr[ib:]:
        if t["s"] > bs + nslots: break
        if t["buy"] and t["user"] not in st["insiders"]: out.append(t["user"])
    return out
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); st["S"] = c["slot"]; r = {}
        for Lm in TODO[m]:
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            d = dict(after_eos=window_buyers(tr, ib, st, 1), after_1s=window_buyers(tr, ib, st, SLOTS_1S))
            if TOP is not None:
                for name, rm in (("base", set()), ("noCW", {W}), ("noCW_fast", {W} | FAST), ("noCW_fast_top", {W} | FAST | TOP)):
                    tr2 = filt(tr, ib, rm, st["insiders"])
                    a = rp.sim(tr2, c, st, ib, 0.5, [EOS], fill_pen=0.015)
                    bb = rp.sim(tr2, c, st, ib, 1.0, [T1], fee_buy_pct=0.006, sell_fee_sol=0.0011, fill_pen=0.015)
                    d[name] = (a["eos"]["pnl"] if a else None, bb["t1"]["pnl"] if bb else None)
                    d[name + "_nbuy"] = (len([u for u in window_buyers(tr2, ib, st, 1)]), len(window_buyers(tr2, ib, st, SLOTS_1S)))
                    if name in ("base", "noCW_fast_top"):
                        a = rp.sim(tr2, c, st, ib, 0.5, [EOS], fill_pen=0.015, slip=slipmap())
                        bb = rp.sim(tr2, c, st, ib, 1.0, [T1], fee_buy_pct=0.006, sell_fee_sol=0.0011, fill_pen=0.015, slip=slipmap())
                        d[name + "_slip"] = (a["eos"]["pnl"] if a else None, bb["t1"]["pnl"] if bb else None, (a["eos"]["slipped"] if a else 0), (bb["t1"]["slipped"] if bb else 0))
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    if TOP is None:     # pass 1: the most frequent after-us buyers (non-insiders, not us) over all these fills, both exits
        cnt = collections.Counter(); fills = 0
        for m, r in res.items():
            for Lm, d in r.items():
                fills += 1
                for u in set(d["after_1s"]): cnt[u] += 1
        top = [u for u, _ in cnt.most_common(10)]
        json.dump(top, open(os.path.join(HERE, "after_us_top10.json"), "w"))
        json.dump([(u, n, u in FAST) for u, n in cnt.most_common(30)], open(os.path.join(HERE, "after_us_counts.json"), "w"))
        print(f"pass 1: {fills} guarded fills; top-10 after-us buyers (within ~1 s after our buy):")
        for u, n in cnt.most_common(10): print(f"   {u[:6]}… in {n} fills ({n / fills:.0%}), fast sniper: {u in FAST}")
        sys.exit(0)
    json.dump(res, open(os.path.join(HERE, "rescore.json"), "w"))
    lines = []; SUMM = {}
    for sname, title in (("a", "(a) oracle: its attempts"), ("b", "(b) walk-forward list + gate")):
        for Lm in (45, 75):
            ms = SETS[sname][Lm]
            fails = sum(1 for m in ms if not R[m][str(Lm)]["ok"]); fl = [m for m in ms if R[m][str(Lm)]["ok"] and str(Lm) in res.get(m, {})]
            lines.append(f"{title} @ {Lm} ms: {len(ms)} launches, {len(fl)} guarded fills, {fails} guard fails (-0.005 each)")
            for name in ("base", "noCW", "noCW_fast", "noCW_fast_top", "base_slip", "noCW_fast_top_slip"):
                v0 = [res[m][str(Lm)][name][0] for m in fl if res[m][str(Lm)].get(name) and res[m][str(Lm)][name][0] is not None]
                v1 = [res[m][str(Lm)][name][1] for m in fl if res[m][str(Lm)].get(name) and res[m][str(Lm)][name][1] is not None]
                extra = ""
                if name.endswith("_slip"):
                    extra = f" | followers priced out per fill: eos {statistics.mean(res[m][str(Lm)][name][2] for m in fl):.2f}, 1 s {statistics.mean(res[m][str(Lm)][name][3] for m in fl):.2f}"
                SUMM[f"{sname}|{Lm}|{name}"] = dict(ours=round(sum(v0) - 0.005 * fails, 3), its=round(sum(v1) - 0.005 * fails, 3), fills=len(fl), n=len(ms), win=round(sum(x > 0 for x in v0) / len(v0), 3))
                lines.append(f"   {name:20} ours (0.5 SOL, end of next slot) {sum(v0) - 0.005 * fails:+7.2f} SOL (per fill {statistics.mean(v0):+.4f}, win {sum(x > 0 for x in v0) / len(v0):.0%}) | "
                             f"its pattern (1 SOL, 1 s) {sum(v1) - 0.005 * fails:+7.2f} (per fill {statistics.mean(v1):+.4f}){extra}")
            for name in ("base", "noCW", "noCW_fast", "noCW_fast_top"):
                nb = [res[m][str(Lm)][name + "_nbuy"] for m in fl if res[m][str(Lm)].get(name + "_nbuy")]
                SUMM[f"{sname}|{Lm}|nobuy|{name}"] = [round(sum(1 for x in nb if x[0] == 0) / len(nb), 3), round(sum(1 for x in nb if x[1] == 0) / len(nb), 3)]
                lines.append(f"   fills with NO outside buy between our buy and our sell [{name}]: end of next slot {sum(1 for x in nb if x[0] == 0) / len(nb):.0%}, 1 s {sum(1 for x in nb if x[1] == 0) / len(nb):.0%}")
    open(os.path.join(HERE, "rescore.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
    json.dump(SUMM, open(os.path.join(HERE, "rescore_summary.json"), "w"), indent=1)
