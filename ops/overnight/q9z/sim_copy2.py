#!/usr/bin/env python3
# READ-ONLY, offline paper replay: the SNIPE-copy ideas (a) oracle picks and (b) walk-forward creator list, re-scored the
# owner's way (2026-10-23): the profit must not come from selling into pro bots' buys. Same mechanics as sim_copy.py
# (45 / 75 ms, block-order placement, 1% guard, 0.5 SOL, sell at the end of the next slot, rp default costs) plus:
#   fs      buys after our entry by the 380 fast sniper wallets removed (fast_snipers.json; 9qz7cW is one of them)
#   t10     buys after our entry by the 10 wallets that most often buy right after us (counted over these trades) removed
#   fs_t10  both
#   slip    follower buys that their own decoded slippage limit rejects after our insert are dropped (core/slip_args.jsonl
#           + 9qz7cW's own limits slip_q9z.jsonl); fs_slip = fs + slip
# -> sim_copy2.json + sim_copy2.txt
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
FS = frozenset(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_q9z.json"))
SC = json.load(open(os.path.join(HERE, "sim_copy.json")))
L = rp.load_launches(); O = rp.load_obs()
SLIP = {}
for f in ("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl", os.path.join(HERE, "slip_q9z.jsonl")):
    if os.path.exists(f):
        for l in open(f):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("kind") in ("sol", "tok"): SLIP[r["sig"]] = (r["kind"], r["a1"], r["a2"])
cand_a = {m for m, v in A.items() if v["9qz7cW"][1] <= 1 and m in L and L[m]["run"] == "R2" and m in O and "InitializeMayhemState" not in (L[m].get("ixn") or [])}
K1 = set(SC["keepK"]["1"]); K2 = set(SC["keepK"]["2"])
todo = cand_a | K1
jobs = collections.defaultdict(set)
for m in todo: jobs[rp.bucket(m)].add(m)
EOS = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
def work(b, top10=frozenset()):
    tra = rp.read_bucket("R2", b, jobs[b]); fa = rp.read_failed("R2", b, jobs[b]); out = {}
    for m, tr in tra.items():
        c = L[m]
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(bt=c["bt"], creator=c.get("creator") or c.get("user"))
        for Lm in (45, 75):
            ib, n_ahead = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            d = dict(fill=ok, ahead=n_ahead, its_ahead=any(t["user"] == W and t["buy"] for t in tr[st["g_end"]:ib]))
            if ok:
                def s_(drop=None, slip=None):
                    o = rp.sim(tr, c, st, ib, 0.5, EOS, fill_pen=0.015, drop_after=drop, slip=slip)
                    return o["eos1"]["pnl"] if o else None
                if top10: d.update(t10=s_(top10), fs_t10=s_(FS | top10))
                else:
                    d.update(base=s_(), fs=s_(FS), its=s_(frozenset([W])), slip=s_(slip=SLIP), fs_slip=s_(FS, SLIP))
                    end = tr[ib - 1]["s"] + 2
                    d["after"] = sorted({t["user"] for t in tr[ib:] if t["buy"] and t["s"] <= end})
                    d["its_after"] = any(t["user"] == W and t["buy"] for t in tr[ib:] if t["s"] <= end)
            r[str(Lm)] = d
        out[m] = r
    return out
def run_all(top10=frozenset()):
    res = {}
    with Pool(12) as pool:
        for o in pool.starmap(work, [(b, top10) for b in sorted(jobs)]): res.update(o)
    return res
if __name__ == "__main__":
    res = run_all()
    cnt = collections.Counter()
    for v in res.values():
        for Lm in ("45", "75"):
            d = v.get(Lm)
            if d and d.get("after"): cnt.update(d["after"])
    top10 = frozenset(w for w, _ in cnt.most_common(10))
    res2 = run_all(top10)
    for m, v in res2.items():
        for Lm in ("45", "75"):
            if Lm in v and m in res and Lm in res[m]: res[m][Lm].update({k: v[Lm].get(k) for k in ("t10", "fs_t10")})
    json.dump(dict(top10=sorted(top10), res=res), open(os.path.join(HERE, "sim_copy2.json"), "w"))
    lines = []
    def P(x): print(x, flush=True); lines.append(x)
    P(f"top-10 after-us buyers: {[(w[:6], cnt[w], w in FS) for w, _ in cnt.most_common(10)]} | slip limits known {len(SLIP)}")
    def table(name, ms):
        for Lm in ("45", "75"):
            rows = sorted((res[m]["bt"], res[m][Lm]) for m in ms if m in res and Lm in res[m])
            if not rows: continue
            mid = rows[0][0] + (rows[-1][0] - rows[0][0]) / 2
            cells = []
            for var in ("base", "its", "fs", "t10", "fs_t10", "slip", "fs_slip"):
                v = [(bt, (d.get(var) if d["fill"] else -0.005)) for bt, d in rows if (not d["fill"]) or d.get(var) is not None]
                tot = sum(x for _, x in v); a = sum(x for t, x in v if t < mid)
                cells.append(f"{var} {tot:+.2f} ({a:+.1f}/{tot - a:+.1f})")
            nf = sum(1 for _, d in rows if d["fill"]); ia = sum(1 for _, d in rows if d["fill"] and d.get("its_after"))
            P(f"{name:34} L{Lm}: fills {nf}/{len(rows)} (9qz7cW buys right after us in {ia}) | " + " | ".join(cells))
    table("(a) its snipe attempts (oracle)", cand_a)
    table("(b) walk-forward creator list K=1", K1)
    table("(b) walk-forward creator list K=2", K2)
    open(os.path.join(HERE, "sim_copy2.txt"), "w").write("\n".join(lines) + "\n")
