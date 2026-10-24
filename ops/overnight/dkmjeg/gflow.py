#!/usr/bin/env python3
# READ-ONLY, offline: GENERIC demand on dKMjeG's picks vs other launches. Generic traders = not the creator / glued bundle,
# not one of the 374 FAST snipers (fast_snipers.json), not dKMjeG. Per launch: generic buy SOL, sell SOL and net flow in
# windows after the create (0-1 s, 1-5 s, 5-15 s, 15-60 s; slots x 0.212 s), and generic buy SOL per slot (time profile).
import sys, json, collections, statistics as S
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"; HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"
L = rp.load_launches(); FAST = set(json.load(open(f"{HERE}/fast_snipers.json")))
C = json.load(open(f"{HERE}/coll.json")); R = {r["m"]: r for r in json.load(open(f"{HERE}/sel_rows.json"))}
byb = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or []): byb[(c["run"], rp.bucket(m))].add(m)
WIN = [("0-1s", 0, 5), ("1-5s", 6, 24), ("5-15s", 25, 71), ("15-60s", 72, 283)]
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); out = {}
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); S0 = c["slot"]; d = {}
        prof = [0.0] * 60
        for nm, a, z in WIN:
            gb = sum(t["sol"] for t in tr[st["g_end"]:] if a <= t["s"] - S0 <= z and t["buy"] and t["user"] not in st["insiders"] and t["user"] not in FAST and t["user"] != W) / 1e9
            # sells: SOL out estimated from the curve move (sell events carry sol out)
            gs = sum(t["sol"] for t in tr[st["g_end"]:] if a <= t["s"] - S0 <= z and not t["buy"] and t["user"] not in st["insiders"] and t["user"] not in FAST and t["user"] != W) / 1e9
            fb = sum(t["sol"] for t in tr[st["g_end"]:] if a <= t["s"] - S0 <= z and t["buy"] and t["user"] in FAST and t["user"] != W) / 1e9
            d[nm] = (round(gb, 3), round(gs, 3), round(fb, 3))
        for t in tr[st["g_end"]:]:
            k = t["s"] - S0
            if 0 <= k < 60 and t["buy"] and t["user"] not in st["insiders"] and t["user"] not in FAST and t["user"] != W: prof[k] += t["sol"] / 1e9
        out[m] = dict(w=d, prof=[round(x, 3) for x in prof])
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(f"{HERE}/gflow.json", "w"))
    att = {m for m, v in C.items() if "dk" in v}
    def show(lab, sel):
        ms = [m for m in res if sel(m)]
        cells = []
        for nm, _, _ in WIN:
            gb = [res[m]["w"][nm][0] for m in ms]; gs = [res[m]["w"][nm][1] for m in ms]; fb = [res[m]["w"][nm][2] for m in ms]
            cells.append(f"{nm}: generic buy {S.mean(gb):.2f} / sell {S.mean(gs):.2f} / net {S.mean(gb) - S.mean(gs):+.2f} (fast-sniper buy {S.mean(fb):.2f})")
        print(f"{lab:46} n={len(ms):5} | " + " | ".join(cells))
    print("mean SOL per launch (generic = not creator/bundle, not the 374 fast snipers, not dKMjeG):")
    show("its attempted launches", lambda m: m in att)
    show("not attempted", lambda m: m not in att)
    pref = lambda m: m in R and ((R[m]["dev_buy"] or 0) + (R[m]["glued_sol"] or 0) >= 2) and R[m]["has_web"]
    show("not attempted, dev+bundle >= 2 SOL & website", lambda m: m not in att and pref(m))
    show("its attempted, dev+bundle >= 2 SOL & website", lambda m: m in att and pref(m))
    # time profile of generic buying (mean SOL per slot) on its picks: slots 0..40 (vs its sell times)
    pa = [res[m]["prof"] for m in res if m in att]; pn = [res[m]["prof"] for m in res if m not in att and pref(m)]
    print("generic buy SOL per slot after the create (mean), its picks:", [round(S.mean(p[k] for p in pa), 2) for k in range(0, 41, 2)])
    print("                                    similar non-picks      :", [round(S.mean(p[k] for p in pn), 2) for k in range(0, 41, 2)])
