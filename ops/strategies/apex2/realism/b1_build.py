#!/usr/bin/env python3
"""APEX2 step 2: merge one run's chunk .npz files (x1_extract.py) into a chain-ordered table.
Keeps only standard pump.fun SOL curves created in this run (CreateEvent quote = SOL, vsol*vtok == 30e9*1.073e15 exactly,
not mayhem by event flag or InitializeMayhemState ix), and only their trades within MAXS slots after the create.
Missing-event gaps (reserve chain breaks, e.g. >6 sells in one tx whose events were not all recorded) are filled with a
synthetic trade (flag syn=1) carrying the exact token/SOL delta, so the replayed curve always matches recorded reserves.
Out: OUT/RUN/{trades.npy, fails.npy, slots.npy, ids.json, creates.json, info.json}
usage: b1_build.py RUN [MAXS=3000]"""
import sys, os, glob, json
import numpy as np

X = "/home/it/sniper-data/apex2/realism/x"; OUT = "/home/it/sniper-data/apex2/realism/tab"
K0 = 30_000_000_000 * 1_073_000_000_000_000
SOLQ = "11111111111111111111111111111111"
TD = np.dtype([("slot", "u8"), ("idx", "u4"), ("j", "u1"), ("mint", "u4"), ("user", "u4"), ("signer", "u4"), ("buy", "u1"),
               ("sol", "u8"), ("tok", "u8"), ("vsol", "u8"), ("vtok", "u8"), ("fee_bps", "u2"), ("cfee_bps", "u2"),
               ("txfee", "u4"), ("tips", "u8"), ("cu", "u4"), ("ixk", "u1"), ("sd", "i8"), ("bt", "u4"), ("syn", "u1")])

def main(run, maxs):
    files = sorted(glob.glob(f"{X}/{run}__*.npz"))
    gid, names = {}, []
    def g(k):
        v = gid.get(k)
        if v is None: v = gid[k] = len(names); names.append(k)
        return v
    creates = {}; info = dict(chunks=len(files), truncated=0)
    for fn in files:
        z = np.load(fn, allow_pickle=True)
        for c in z["creates"]:
            c = json.loads(c); k = c.get("mint")
            if k and (k not in creates or (c["slot"], c["idx"]) < (creates[k]["slot"], creates[k]["idx"])): creates[k] = c
    std = {}
    for m, c in creates.items():
        ok = (c.get("quote", SOLQ) == SOLQ and int(c.get("vsol", 0)) * int(c.get("vtok", 0)) == K0 and not c.get("mayhem")
              and not c.get("mayhem_ix") and "err" not in c)
        c["std"] = bool(ok)
        if ok: std[m] = int(c["slot"])
    parts, fparts, sparts = [], [], []
    for fn in files:
        z = np.load(fn, allow_pickle=True); ids = z["ids"]
        if json.loads(z["meta"][0])["truncated"]: info["truncated"] += 1
        sparts.append(z["slots"])
        t = z["trades"]
        if len(t):
            ms = ids[t["mint"]]
            cs = np.array([std.get(m, -1) for m in ms], np.int64)
            keep = (cs >= 0) & (t["slot"].astype(np.int64) >= cs) & (t["slot"].astype(np.int64) <= cs + maxs)
            t = t[keep]; ms = ms[keep]
            o = np.zeros(len(t), TD)
            for c in TD.names:
                if c in ("syn",): continue
                if c in ("mint", "user", "signer"): continue
                o[c] = t[c]
            o["mint"] = [g(m) for m in ms]; o["user"] = [g(u) for u in ids[t["user"]]]; o["signer"] = [g(u) for u in ids[t["signer"]]]
            parts.append(o)
        f = z["fails"]
        if len(f):
            ms = ids[f["mint"]]; keep = np.array([m in std for m in ms], bool)
            f = f[keep].copy(); ms = ms[keep]
            if len(f):
                f["mint"] = [g(m) for m in ms]; f["signer"] = [g(u) for u in ids[f["signer"]]]
                fparts.append(f)
    T = np.concatenate(parts)
    o = np.lexsort((T["j"], T["idx"], T["slot"])); T = T[o]
    key = (T["slot"].astype(np.uint64) << np.uint64(24)) + (T["idx"].astype(np.uint64) << np.uint64(8)) + T["j"].astype(np.uint64)
    keep = np.ones(len(T), bool); keep[1:] = key[1:] != key[:-1]; T = T[keep]; info["dups"] = int((~keep).sum())
    # chain check per mint + synthetic gap fills
    o = np.lexsort((T["j"], T["idx"], T["slot"], T["mint"])); Tm = T[o]
    syn = []; nchk = 0; nbad = 0
    mm = Tm["mint"]; vs = Tm["vsol"].astype(object); vt = Tm["vtok"].astype(object)
    sol = Tm["sol"].astype(object); tok = Tm["tok"].astype(object); bu = Tm["buy"]
    for k in range(1, len(Tm)):
        if mm[k] != mm[k - 1]: continue
        nchk += 1
        V, Tt = vs[k - 1], vt[k - 1]
        pV, pT = (V + sol[k], Tt - tok[k]) if bu[k] else (V - sol[k], Tt + tok[k])
        if pV == vs[k] and pT == vt[k]: continue
        nbad += 1
        # state just before trade k (from its own recorded post state)
        bV, bT = (vs[k] - sol[k], vt[k] + tok[k]) if bu[k] else (vs[k] + sol[k], vt[k] - tok[k])
        dT = int(bT) - int(Tt); dV = int(bV) - int(V)
        r = Tm[k - 1].copy()          # same slot/idx/j as k-1, syn=1 sorts right after it (missing tail events of tx k-1)
        r["buy"] = 1 if dT < 0 else 0; r["tok"] = abs(dT); r["sol"] = abs(dV); r["vsol"] = int(bV); r["vtok"] = int(bT)
        r["syn"] = 1; r["txfee"] = 0; r["tips"] = 0; r["sd"] = 0
        syn.append(r)
    info.update(chain_checked=nchk, chain_breaks=nbad)
    if syn:
        T = np.concatenate([T, np.array(syn, TD)]); o = np.lexsort((T["syn"], T["j"], T["idx"], T["slot"])); T = T[o]
    S = np.concatenate(sparts); o = np.lexsort((-S["maxi"].astype(np.int64), S["slot"])); S = S[o]
    k2 = np.ones(len(S), bool); k2[1:] = S["slot"][1:] != S["slot"][:-1]; S = S[k2]
    F = np.concatenate(fparts) if fparts else np.zeros(0, fparts[0].dtype if fparts else np.dtype([("slot", "u8")]))
    od = f"{OUT}/{run}"; os.makedirs(od, exist_ok=True)
    np.save(f"{od}/trades.npy", T); np.save(f"{od}/slots.npy", S); np.save(f"{od}/fails.npy", F)
    json.dump(names, open(f"{od}/ids.json", "w")); json.dump(creates, open(f"{od}/creates.json", "w"))
    info.update(trades=len(T), syn=len(syn), fails=len(F), creates=len(creates), std=len(std), slot_lo=int(S["slot"][0]),
                slot_hi=int(S["slot"][-1]), bt_lo=int(S["bt"][0]), bt_hi=int(S["bt"][-1]))
    json.dump(info, open(f"{od}/info.json", "w")); print(run, info, flush=True)

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3000)
