# Backup strategy check: the live shadow scorer's FINAL-2 picks (token-quality model + anti-dump veto, decided at the
# bundle close) traded with the S4 mechanics: 1% price guard, block-order placement, sell at the end of the next slot.
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
picks = {}
for f in ("scores_v1.jsonl", "scores_v2.jsonl", "scores_v3.jsonl"):
    for l in open(f"/home/moiz/sniper-data/collect/shadow/{f}"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") != "decide" or r.get("quote") != "sol": continue
        m = r["mint"]
        sc = r.get("final_score", r.get("score")); veto = r.get("veto_score")
        picks[m] = dict(final=bool(r.get("final_pick")), score=sc, veto=veto, name=r.get("final"))
print("scored launches:", len(picks), "| FINAL-2 picks:", sum(1 for v in picks.values() if v["final"]))
scores = sorted(v["score"] for v in picks.values() if v["score"] is not None)
thr = {q: scores[int((1 - q) * (len(scores) - 1))] for q in (0.01, 0.02, 0.05, 0.10, 0.20)}
todo = [m for m in picks if m in L and m in O and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            r[Lm] = (o["eos1"]["pnl"] if o else None, ok)
        out[m] = (c["bt"], r)
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    def show(name, sel):
        ms = [m for m in res if sel(m)]
        if not ms: return
        t0 = min(res[m][0] for m in ms); t1 = max(res[m][0] for m in ms); mid = t0 + (t1 - t0) / 2
        cells = []
        for Lm in (45, 75):
            ng = [res[m][1][Lm][0] for m in ms if Lm in res[m][1] and res[m][1][Lm][0] is not None]
            g = [(res[m][0], res[m][1][Lm][0] if res[m][1][Lm][1] else -0.005) for m in ms if Lm in res[m][1] and res[m][1][Lm][0] is not None]
            tot = sum(x for _, x in g); a = sum(x for t, x in g if t < mid)
            cells.append(f"L{Lm}: no guard {sum(ng):+6.2f} | guard {tot:+6.2f} ({a:+.1f}/{tot - a:+.1f}) fills {sum(1 for _, x in g if x != -0.005)}/{len(g)}")
        print(f"{name:34} " + " || ".join(cells))
    show("FINAL-2 live picks", lambda m: picks[m]["final"])
    for q, t in thr.items(): show(f"model score top {q:.0%}", lambda m, t=t: picks[m]["score"] is not None and picks[m]["score"] >= t)
    show("model top 5% and veto < 0.5", lambda m: picks[m]["score"] is not None and picks[m]["score"] >= thr[0.05] and (picks[m]["veto"] or 0) < 0.5)
