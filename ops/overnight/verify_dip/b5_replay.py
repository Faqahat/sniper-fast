#!/usr/bin/env python3
"""verify_dip / b5_replay: spacing-5 check. Re-prices CV picks (cv_repro output) with my own replay (my extraction: work/R1,
work/b5_R2; own code from vx_replay.py), exit 2 slots after our buy slot (own arrival slot), our sell 75 ms into it, real
decoded follower limits where available (b5_snap/slip_args.jsonl), imputed slack otherwise (the claim's rule).
Specs:
  c   : the claim's spec (as dipbuy4.py with DIP_REAL_SLIP=1, bug fixes 1+2)
  x   : + the 70 fast dip-backrunners follow their measured tolerance (out/tau_backrunners.json, 95th pct) instead of
        their decoded/imputed limit
Modes:
  ind : every pick priced alone on the real tape (the claim's way)
  seq : picks on the same launch priced in time order on ONE modified tape: our earlier buy + sell (and the followers they
        priced out) stay in the curve for the later picks
Block sizes: 'claim' = core/slotsize2.json with the 400 default (what dipbuy4 uses), 'mine' = max index in the raw chunks.
usage: python3 -I -B b5_replay.py <cv json> <LAT> <out json> [grid=1]"""
import sys, os, json, gzip, zlib, hashlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.path.join(HERE, "work")
SMS = 212.0; B = 0.5; H = 2; SL = 75.0; VT_DONE = 1_073_000_000_000_000 - 793_100_000_000_000
DIRS = {"R1": os.path.join(WORK, "R1"), "R2": os.path.join(WORK, "b5_R2")}
G = {}
def init():
    SS = {}
    for d in DIRS.values():
        for k, v in json.load(gzip.open(os.path.join(d, "smax.json.gz"), "rt")).items():
            if v + 1 > SS.get(int(k), 0): SS[int(k)] = v + 1
    G["SS_mine"] = SS
    G["SS_claim"] = {int(k): v for k, v in json.load(open(os.path.join(HERE, "snap", "slotsize2.json"))).items()}
    G["SLACK"] = sorted(r[1] for r in json.load(open(os.path.join(HERE, "snap", "a8_slack.json")))["rows"])
    REAL = {}
    for l in open(os.path.join(HERE, "b5_snap", "slip_args.jsonl")):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("kind") in ("sol", "tok"): REAL[r["sig"]] = (r["kind"], r["a1"], r["a2"])
    G["REAL"] = REAL
    G["TAU"] = json.load(open(os.path.join(HERE, "out", "tau_backrunners.json")))
    L = {}
    for tag, run in (("R1", "run_20261021_2207"), ("R2", "run_20261022_1543")):
        for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            if c["mint"] not in L: c["run"] = tag; L[c["mint"]] = c
    G["L"] = L
def slack(sig):
    S = G["SLACK"]; h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return S[min(len(S) - 1, int(h * len(S)))]
def fbps(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
def tape(rows):
    out = []; seen = set()
    for r in rows:
        if r[4] or (r[3], r[2]) in seen: continue
        seen.add((r[3], r[2]))
        out.append(dict(s=r[0], i=r[1], k=r[2], sig=r[3], payer=r[5], user=r[6], sol=r[7], tok=r[8], buy=r[9] == 1, vsol=r[10], vtok=r[11],
                        fbps=r[14], cbps=r[16], syn=False))
    out.sort(key=lambda t: (t["s"], t["i"], t["k"]))
    rep = []; prev = None
    for t in out:
        pre = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
        if prev is not None and pre != prev and t["vtok"] and prev[1]:
            dv = pre[0] - prev[0]; dt = pre[1] - prev[1]
            if dt != 0 and abs(dv) > 1000 and abs((pre[0] * pre[1]) / (prev[0] * prev[1]) - 1) < 0.002:
                rep.append(dict(t, k=-1, sig="gap:" + t["sig"], payer="?", user="?", buy=dv > 0, sol=abs(dv), tok=abs(dt), vsol=pre[0], vtok=pre[1], syn=True))
        rep.append(t); prev = (t["vsol"], t["vtok"])
    return rep
class Sim:
    def __init__(self, tr, ss):
        self.tr = tr; self.SS = ss
    def pos(self, t): return t["i"] / max(self.SS.get(t["s"], 400), t["i"] + 1) * SMS
    def arr(self, t): return t["s"] * SMS + self.pos(t)
    def apply(self, t, V, T, fr, spec, p_dip):
        """one outside trade on the (possibly modified) curve -> (V, T); a buy that its own limit rejects is dropped"""
        if t["buy"]:
            if spec == "x" and p_dip is not None and t["payer"] in G["TAU"]:
                if (V / T) / p_dip > G["TAU"][t["payer"]]: return V, T, False
                d = T * t["sol"] // (V + t["sol"]); return V + t["sol"], T - d, True
            lim = G["REAL"].get(t["sig"]) if not t["syn"] else None
            if lim is not None:
                kind, a1, a2 = lim
                if kind == "sol":
                    d = T * t["sol"] // (V + t["sol"])
                    if d < a2: return V, T, False
                    return V + t["sol"], T - d, True
                if a1 >= T: return V, T, False
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: return V, T, False
                return V + cst, T - a1, True
            d = T * t["sol"] // (V + t["sol"])
            if not t["syn"] and d < t["tok"] / (1 + slack(t["sig"])): return V, T, False
            return V + t["sol"], T - d, True
        so = V * t["tok"] // (T + t["tok"]); return V - so, T + t["tok"], True
    def run(self, picks, Lm, spec, seq):
        """picks: sorted list of (k, age). Returns {age: (pnl_gross, info)}"""
        tr = self.tr; out = {}; V = T = None; j = 0
        for k, age in picks:
            t0 = tr[k]
            if not seq or V is None or k < j:
                V, T = t0["vsol"], t0["vtok"]
            else:
                for t in tr[j:k]:
                    V, T, _ = self.apply(t, V, T, fbps(t), spec, None)
                so = V * t0["tok"] // (T + t0["tok"]); V, T = V - so, T + t0["tok"]          # the dip sell, same tokens
            fr = fbps(t0); p_dip = V / T; a0 = self.arr(t0)
            ke = k + 1
            while ke < len(tr) and self.arr(tr[ke]) < a0 + Lm: ke += 1
            for t in tr[k + 1:ke]:                                                        # trades ahead of us
                V, T, _ = self.apply(t, V, T, fbps(t), spec, None)
            s_land = int((a0 + Lm) // SMS); s_in = max(tr[ke - 1]["s"], s_land); E = s_in + H
            X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; frs = fr; nd = 0; jj = ke
            for jj in range(ke, len(tr) + 1):
                if jj == len(tr): break
                t = tr[jj]
                if t["s"] > E or (t["s"] == E and self.pos(t) >= SL): break
                V, T, ok = self.apply(t, V, T, fr, spec, p_dip)
                if not ok: nd += 1; continue
                frs = fbps(t)
                if V >= 110e9 or T <= VT_DONE: jj += 1; break
            so = V * q // (T + q); V -= so; T += q
            out[age] = (so * (1 - frs) / 1e9 - B, nd, ke - k - 1)
            j = jj
        return out
def work(arg):
    (tag, b), items, Ls = arg
    data = json.load(gzip.open(os.path.join(DIRS[tag], f"b{b:03d}.json.gz"), "rt")); res = {}
    by = collections.defaultdict(list)
    for m, age in items: by[m].append(age)
    for m, ages in by.items():
        c = G["L"][m]; tr = tape(data[m]["t"]); S = c["slot"]; want = set(ages); picks = []
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < 1e9: continue
            a = round((t["s"] - S) * SMS / 1000, 2)
            if a in want: want.discard(a); picks.append((k, a))
        picks.sort()
        r = {}
        for bs in ("claim", "mine"):
            sim = Sim(tr, G["SS_" + bs])
            for Lm in Ls:
                for spec in ("c", "x"):
                    if bs == "claim" and (spec == "x" or Lm not in Ls[:1]): continue
                    for seq in (False, True):
                        o = sim.run(picks, Lm, spec, seq)
                        for a, v in o.items(): r.setdefault(a, {})[f"{bs}|{spec}|{'seq' if seq else 'ind'}|{Lm}"] = v
        for a, v in r.items(): res[f"{m}|{a}"] = v
    return res
if __name__ == "__main__":
    cvf, LAT, outp = sys.argv[1], sys.argv[2], sys.argv[3]; grid = len(sys.argv) > 4 and sys.argv[4] == "1"
    sel = json.load(open(cvf))[LAT]["sel"]
    Ls = [int(LAT)] + ([x for x in range(0, 155, 5) if x != int(LAT)] if grid else [])
    init()
    by = collections.defaultdict(list)
    for s in sel: by[(G["L"][s["m"]]["run"], zlib.crc32(s["m"].encode()) % 256)].append((s["m"], s["age"]))
    res = {}
    with Pool(8, initializer=init) as p:
        for o in p.imap_unordered(work, [(k, v, Ls) for k, v in sorted(by.items())]): res.update(o)
    json.dump(dict(sel=sel, res=res, Ls=Ls), open(outp, "w"))
    tx = 0.0016
    claim = {f"{s['m']}|{s['age']}": s["pnl"] for s in sel}
    def tot(key): return sum((v[key][0] - tx) for v in res.values() if key in v)
    n_ok = sum(1 for k in claim if k in res and f"claim|c|ind|{LAT}" in res[k])
    diff = [res[k][f"claim|c|ind|{LAT}"][0] - tx - claim[k] for k in claim if k in res and f"claim|c|ind|{LAT}" in res[k]]
    print(f"{os.path.basename(cvf)} L{LAT}: picks {len(sel)} priced {n_ok}; claim total {sum(claim.values()):+.2f}")
    print(f"  claim spec, claim block sizes, independent: {tot(f'claim|c|ind|{LAT}'):+.2f} | exact match (<0.0001) {sum(1 for d in diff if abs(d) < 1e-4) / max(1, len(diff)):.1%}")
    print(f"  claim spec, claim block sizes, sequential:  {tot(f'claim|c|seq|{LAT}'):+.2f}")
    print(f"  claim spec, my block sizes: independent {tot(f'mine|c|ind|{LAT}'):+.2f} | sequential {tot(f'mine|c|seq|{LAT}'):+.2f}")
    print(f"  + measured backrunner tolerance: independent {tot(f'mine|x|ind|{LAT}'):+.2f} | sequential {tot(f'mine|x|seq|{LAT}'):+.2f}")
