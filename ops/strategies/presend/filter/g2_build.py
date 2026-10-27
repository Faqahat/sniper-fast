#!/usr/bin/env python3
"""PRESEND FILTER, step 2: consolidate g1 chunks into one chain-ordered table with interned ids (read-only on the recording).
  /home/moiz/sniper-data/presend_filter/chain.npz : trades sorted by (slot, idx, j), duplicates of the overlapping recording runs removed
  /home/moiz/sniper-data/presend_filter/ids.json  : id -> string tables (mint, wallet, prog, ixn)
  (failed txs: g2b_fails.py)
  /home/moiz/sniper-data/presend_filter/creates.json : pump creates (launches.jsonl of each recording run, bt < CAP)
  /home/moiz/sniper-data/presend_filter/failsigners.json : failed pump txs per signer (all mints, whole span)"""
import glob, json, os, time, collections
import numpy as np

B = "/home/moiz/sniper-data/presend_filter"
CAP = 1793064600
t0 = time.time()
ids = {k: {} for k in ("w", "m", "p", "x")}
def intern(tab, arr):
    d = ids[tab]
    out = np.empty(len(arr), np.uint32)
    for k, s in enumerate(arr.tolist()):
        v = d.get(s)
        if v is None: v = d[s] = len(d)
        out[k] = v
    return out
cols = collections.defaultdict(list); fcols = collections.defaultdict(list); fsig = collections.Counter()
files = sorted(glob.glob(f"{B}/g1/*.npz"), key=lambda f: int(os.path.basename(f).split("__txs_")[1][:10]))
for k, f in enumerate(files):
    z = np.load(f)
    if "t_s" in z:
        for c in ("s", "i", "j", "bt", "buy", "sol", "tok", "vsol", "vtok", "fbps", "cbps", "txfee", "cup", "cul", "tip"): cols[c].append(z["t_" + c])
        cols["mint"].append(intern("m", z["t_mint"])); cols["user"].append(intern("w", z["t_user"])); cols["signer"].append(intern("w", z["t_signer"]))
        cols["prog"].append(intern("p", z["t_prog"])); cols["ixn"].append(intern("x", z["t_ixn"]))
    fsig.update(json.load(open(f[:-4] + ".json")))
    if k % 100 == 0: print(k, f"{time.time() - t0:.0f}s", flush=True)
T = {c: np.concatenate(v) for c, v in cols.items()}
o = np.lexsort((T["j"], T["i"], T["s"]))
T = {c: v[o] for c, v in T.items()}
key_dup = np.zeros(len(T["s"]), bool)
key_dup[1:] = (T["s"][1:] == T["s"][:-1]) & (T["i"][1:] == T["i"][:-1]) & (T["j"][1:] == T["j"][:-1])
T = {c: v[~key_dup] for c, v in T.items()}
np.savez(f"{B}/chain.npz", **T)
json.dump({k: list(d.keys()) for k, d in ids.items()}, open(f"{B}/ids.json", "w"))
json.dump(dict(fsig), open(f"{B}/failsigners.json", "w"))
cr = {}
for run in ("run_20261024_1425", "run_20261025_1420", "run_20261026_1415"):
    for line in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: r = json.loads(line)
        except Exception: continue
        if r.get("bt", 0) >= CAP or r.get("err") is not None: continue
        if r["mint"] in cr: continue
        cr[r["mint"]] = dict(slot=r["slot"], idx=r["idx"], bt=r["bt"], creator=r.get("creator"), user=r.get("user"), payer=r.get("payer"), name=r.get("name"), symbol=r.get("symbol"),
                             uri=r.get("uri"), ixn=(r.get("ixn") or [])[:1], fee=r.get("fee"))
json.dump(cr, open(f"{B}/creates.json", "w"))
print(f"trades {len(T['s']):,} (dups removed {int(key_dup.sum()):,}), wallets {len(ids['w']):,}, mints {len(ids['m']):,}, creates {len(cr):,}, slots {int(T['s'][0])}..{int(T['s'][-1])}, bt max {int(T['bt'].max())}, {time.time() - t0:.0f}s")
