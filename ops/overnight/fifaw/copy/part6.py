# READ-ONLY, offline (rp.py replay): can WE copy FiFawH?  Our mechanics: land at 45 or 75 ms after the create (our engine's
# arrival clock), 1% price guard vs the price right after the dev's glued bundle (fail = -0.005 SOL), block-order placement
# with failed-tx anchors (rp.place_bo2), sell everything at the end of the next slot (rp "eos1"), 0.5 SOL per buy
# (same conventions as guard_final2.py / ana_lists_guard.py).  Sets:
#   (a) ORACLE: every launch FiFawH attempted (not tradable: we only know after it lands)
#   (b) WALK-FORWARD deployer list from its attempts: deployer has >= 2 earlier FiFawH attempts and attempts / launches >= 10%,
#       using only launches BEFORE the one being decided (both collector runs feed the history; trading only on the R2 window)
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
def wf_list(rate=0.10, k=2):
    ev = []
    for m, c in L.items():
        if not c.get("bt"): continue
        ev.append((c["bt"], c["user"], 0))
        if "FiFawH" in A.get(m, {}): ev.append((c["bt"], c["user"], 1))
    ev.sort(); na = collections.Counter(); nl = collections.Counter(); j = 0; keep = {}
    for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt")):
        while j < len(ev) and ev[j][0] < bt:
            _, d, a = ev[j]; (na if a else nl)[d] += 1; j += 1
        d = L[m]["user"]
        keep[m] = na[d] >= k and (nl[d] == 0 or na[d] / nl[d] >= rate)
    return keep
SEL = {"(a) ORACLE: its attempts": {m: "FiFawH" in A.get(m, {}) for m in L},
       "(a') ORACLE: its FILLED buys": {m: A.get(m, {}).get("FiFawH", [0])[0] == 1 for m in L},
       "(b) walk-forward deployer list (>=2, >=10%)": wf_list(),
       "(b') walk-forward list (>=2, >=30%)": wf_list(rate=0.30),
       "(b'') walk-forward list (>=3, >=20%)": wf_list(rate=0.20, k=3)}
ALL = {m for s in SEL.values() for m, v in s.items() if v}
fw = [m for m in ALL if m in O and L[m]["run"] == "R2" and "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in fw: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
B = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue      # SOL-quoted curves only
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            ib, nah = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015)
            if o is None: continue
            r[Lm] = dict(pnl=o["eos1"]["pnl"], ok=ok, ahead=nah)
        out[m] = (c["bt"], r)
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    t0 = min(v[0] for v in res.values()); t1 = max(v[0] for v in res.values()); mid = t0 + (t1 - t0) / 2
    print(f"forward window (R2 launches with our engine's timeline): {(t1 - t0) / 3600:.1f} h, {len(res)} simulated SOL-quoted launches in the union; buy {B} SOL, eos1 exit")
    summ = {}
    for name, s in SEL.items():
        ms = [m for m in res if s.get(m)]
        cells = []; summ[name] = {}
        for Lm in (45, 75):
            v = [(res[m][0], res[m][1][Lm]) for m in ms if Lm in res[m][1]]
            g = [(t, x["pnl"] if x["ok"] else -0.005) for t, x in v]
            ng = sum(x["pnl"] for _, x in v)
            tot = sum(z for _, z in g); a = sum(z for t, z in g if t < mid); nf = sum(1 for _, x in v if x["ok"])
            fills = [x["pnl"] for _, x in v if x["ok"]]
            summ[name][Lm] = dict(n=len(v), fills=nf, guard_total=round(tot, 3), half1=round(a, 3), half2=round(tot - a, 3), no_guard_total=round(ng, 3),
                                  fill_mean=round(statistics.mean(fills), 4) if fills else None, fill_win=round(sum(1 for z in fills if z > 0) / len(fills), 2) if fills else None)
            cells.append(f"L{Lm}: guard {tot:+6.2f} ({a:+.2f}/{tot - a:+.2f}) fills {nf}/{len(v)}" + (f" mean/fill {statistics.mean(fills):+.3f} win {sum(1 for z in fills if z > 0) / len(fills):.0%}" if fills else "") + f" | no guard {ng:+.2f}")
        print(f"{name:46} " + " || ".join(cells))
    json.dump(dict(B=B, window_h=(t1 - t0) / 3600, summary=summ, per_launch={m: v for m, v in res.items()}, sets={k: sorted(m for m, v in s.items() if v and m in res) for k, s in SEL.items()}),
              open(f"part6_B{B}.json", "w"))
