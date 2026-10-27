#!/usr/bin/env python3
# POST-MIGRATION STUDY, pass 2: merge pass-1 chunk files of one run into per-run tables.
#  <RUN>_amm.npz   every PumpSwap Buy/SellEvent (global string ids), sorted by (s, i, k); sigx = index into sigs (first
#                  SIGWIN slots after the pool's migration only, else -1)
#  <RUN>_bc.npz    bonding-curve trades of graduated mints only
#  <RUN>_fail.npz  failed PumpSwap txs on graduated mints within FAILWIN slots after migration
#  <RUN>_migs.json one record per graduated mint (first successful migration tx) + attempts
#  <RUN>_slots.npz slot, block-size estimate (max index seen + 1), block time
#  <RUN>_strs.pkl  string table (wallets, pools, mints, relays) and kept signatures
import sys, os, glob, json, pickle, time
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from pm1_extract import load_chunk, OUT as TMP
OUT = "/home/moiz/sniper-data/strategies/postmig"
SIGWIN = 3000; FAILWIN = 3000
WSOL = "So11111111111111111111111111111111111111112"

def main(run):
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(TMP, run, "*.pkl")))
    # phase A: migrations + slot table
    migs = {}; attempts = {}; slots = {}
    for f in files:
        d = load_chunk(f)
        for s, (mi, bt) in d["slots"].items():
            o = slots.get(s)
            if o is None or mi > o[0]: slots[s] = (mi, bt)
        for m in d["migs"]:
            c = m["cpe"]; g = m["mig"]
            mint = (c or {}).get("base_mint") or (g or {}).get("mint")
            if not mint: continue
            attempts[mint] = attempts.get(mint, 0) + 1
            if c is None: continue
            # canonical pump.fun migrations only: the pump program's Migrate/MigrateV2 in the tx, WSOL quote
            if not any(x in ("Migrate", "MigrateV2") for x in (m.get("ixn") or [])) or c.get("quote_mint") != WSOL: continue
            key = (m["s"], m["i"])
            if mint not in migs or key < (migs[mint]["s"], migs[mint]["i"]): migs[mint] = m
    print(run, "phase A", len(files), "chunks", len(migs), "migrations", f"{time.time()-t0:.0f}s", flush=True)
    pool2mint = {m["cpe"]["pool"]: k for k, m in migs.items()}
    migslot = {k: m["s"] for k, m in migs.items()}
    # phase B: tables
    G = {}; GL = []
    def gid(x):
        v = G.get(x)
        if v is None: v = G[x] = len(GL); GL.append(x)
        return v
    sigs = []
    A = []; BC = []; F = []
    pool_gid_mint = {}
    for f in files:
        d = load_chunk(f); strl = d["strl"]
        lm = np.full(len(strl) + 1, -1, np.int64)
        def remap(col):
            u = np.unique(col[col >= 0])
            for j in u.tolist(): lm[j] = gid(strl[j])
            return np.where(col >= 0, lm[np.maximum(col, 0)], -1).astype(np.int32)
        a = d["amm"]
        if len(a["s"]):
            a = dict(a)
            pool_l = a["pool"]
            # keep only events on pools of graduated mints of this run
            keep = np.array([strl[j] in pool2mint for j in pool_l.tolist()], bool) if len(pool_l) else np.zeros(0, bool)
            a = {c: v[keep] for c, v in a.items()}
            if len(a["s"]):
                mint_g = np.array([gid(pool2mint[strl[j]]) for j in a["pool"].tolist()], np.int32)
                ms = np.array([migslot[pool2mint[strl[j]]] for j in a["pool"].tolist()], np.int64)
                sigx = np.full(len(a["s"]), -1, np.int32)
                win = (a["s"].astype(np.int64) - ms) <= SIGWIN
                for r in np.nonzero(win)[0].tolist():
                    sigx[r] = len(sigs); sigs.append(strl[int(a["sig"][r])])
                for c in ("pool", "user", "signer", "cc", "relay"): a[c] = remap(a[c])
                a["mint"] = mint_g; a["sigx"] = sigx; del a["sig"]
                A.append(a)
        b = d["bc"]
        if len(b["s"]):
            b = dict(b)
            keep = np.array([strl[j] in migs for j in b["mint"].tolist()], bool)
            b = {c: v[keep] for c, v in b.items()}
            if len(b["s"]):
                for c in ("mint", "user", "signer", "relay"): b[c] = remap(b[c])
                del b["sig"]; BC.append(b)
        fl = d["fail"]
        if len(fl["s"]):
            fl = dict(fl)
            mk = fl["mint"]
            keep = np.array([(j >= 0 and strl[j] in migs and 0 <= s - migslot[strl[j]] <= FAILWIN) for j, s in zip(mk.tolist(), fl["s"].tolist())], bool)
            fl = {c: v[keep] for c, v in fl.items()}
            if len(fl["s"]):
                for c in ("mint", "signer", "relay"): fl[c] = remap(fl[c])
                F.append(fl)
    def cat(L):
        if not L: return {}
        out = {c: np.concatenate([x[c] for x in L]) for c in L[0]}
        o = np.lexsort((out["k"], out["i"], out["s"])) if "k" in out else np.lexsort((out["i"], out["s"]))
        return {c: v[o] for c, v in out.items()}
    A = cat(A); BC = cat(BC); F = cat(F)
    np.savez(os.path.join(OUT, f"{run}_amm.npz"), **A)
    np.savez(os.path.join(OUT, f"{run}_bc.npz"), **BC)
    np.savez(os.path.join(OUT, f"{run}_fail.npz"), **F)
    ss = np.array(sorted(slots), np.int64)
    np.savez(os.path.join(OUT, f"{run}_slots.npz"), s=ss, bs=np.array([slots[s][0] + 1 for s in ss.tolist()], np.int32),
             bt=np.array([slots[s][1] for s in ss.tolist()], np.int64))
    for k, m in migs.items(): m["attempts"] = attempts.get(k, 1)
    json.dump(migs, open(os.path.join(OUT, f"{run}_migs.json"), "w"))
    pickle.dump(dict(strs=GL, sigs=sigs), open(os.path.join(OUT, f"{run}_strs.pkl"), "wb"), protocol=5)
    print(run, "done", "amm", len(A.get("s", [])), "bc", len(BC.get("s", [])), "fail", len(F.get("s", [])), "strings", len(GL),
          "sigs", len(sigs), f"{time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)
