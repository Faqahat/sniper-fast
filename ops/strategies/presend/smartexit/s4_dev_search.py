#!/usr/bin/env python3
"""SMARTEXIT step 4 (DEV ONLY): every policy in spol.grid() on DEV fills, own lag, fc 0 and fc 0.2 (followers -20%).
Per policy: gain vs exact t125 on the same fills, w/o the 5 biggest per-fill gains, fc20 gain, gain per DEV chunk
(r37, r38, r39, r40, r41, r42-dev first half, r42-dev second half) -> how many chunks positive.
Out: /home/it/sniper-data/smartexit/dev_search.json + printed tables (top per family)."""
import sys, json, collections, multiprocessing as mp
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/smartexit")
import slib as L, spol as P

F, J, _ = L.load_fills(("dev",))
H = J["split_hours"]["dev"]
r42 = sorted(f.t0 for f in F if f.run == 42); mid42 = r42[len(r42) // 2]
def chunk(f): return f"r{f.run}" if f.run != 42 else ("r42a" if f.t0 < mid42 else "r42b")
CH = [chunk(f) for f in F]
EV0 = [L.events(f) for f in F]; EV2 = [L.events(f, 0.2) for f in F]
G = P.grid()
base0 = [P.run_policy(f, e, P.p_timer(125)) for f, e in zip(F, EV0)]
base2 = [P.run_policy(f, e, P.p_timer(125), 0.2) for f, e in zip(F, EV2)]

def ev(gi):
    fam, prm, fn = G[gi]
    p0 = [P.run_policy(f, e, fn) for f, e in zip(F, EV0)]
    p2 = [P.run_policy(f, e, fn, 0.2) for f, e in zip(F, EV2)]
    d0 = [a - b for a, b in zip(p0, base0)]; d2 = [a - b for a, b in zip(p2, base2)]
    byc = collections.defaultdict(float)
    for c, g in zip(CH, d0): byc[c] += g
    s = sorted(d0, reverse=True)
    return dict(fam=fam, prm=prm, gain=sum(d0), wo5=sum(s[5:]), fc20=sum(d2), chunks=dict(byc),
                npos=sum(1 for v in byc.values() if v > 1e-9), nneg=sum(1 for v in byc.values() if v < -1e-9),
                changed=sum(1 for g in d0 if abs(g) > 1e-9))

if __name__ == "__main__":
    print(f"DEV fills {len(F)} hours {H:.1f} base t125 {sum(base0):+.3f} fc20 {sum(base2):+.3f}; policies {len(G)}", flush=True)
    with mp.Pool(14) as pool:
        R = pool.map(ev, range(len(G)), chunksize=8)
    for r in R: r["score"] = min(r["gain"], r["wo5"], r["fc20"])
    json.dump(dict(base=sum(base0), base20=sum(base2), hours=H, rows=R), open(f"{L.D}/dev_search.json", "w"))
    byf = collections.defaultdict(list)
    for r in R: byf[r["fam"]].append(r)
    for fam, rs in byf.items():
        rs.sort(key=lambda r: -r["score"])
        print(f"\n== {fam} ({len(rs)} variants) top by min(gain, w/o5, fc20):")
        for r in rs[:6]:
            ch = " ".join(f"{k}:{v:+.2f}" for k, v in sorted(r["chunks"].items()))
            print(f"  {str(r['prm']):34} gain {r['gain']:+.3f} ({r['gain'] / H * 24:+.2f}/d) wo5 {r['wo5']:+.3f} fc20 {r['fc20']:+.3f} "
                  f"chunks+ {r['npos']}/{r['npos'] + r['nneg']} chg {r['changed']} | {ch}")
