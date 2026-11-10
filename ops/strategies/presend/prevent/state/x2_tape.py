#!/usr/bin/env python3
"""STATE step 2 [MEASURED, read-only]: one decoded pump.fun trade tape for every mint we need (live windows of all runs, shadow arms of the
shadow-only runs, observatory re-arm windows), from
  presend_quiet3/chain.npz   block time < 1793240200 (10-29 07:16:40 PKT; quiet3 recorder decode)
  presend_quiet4/tab37       1793240200 .. 1793305231 (to 10-30 01:20 PKT)
  prevent/state/tab38b       1793305232 .. 1793313901 (r37 tail + run 38, my decode)
Out: /home/it/sniper-data/prevent/state/tape.npz (sorted by mint, slot, idx, j) + tape_ids.json {mints, users}"""
import json, pickle, time
import numpy as np
D = "/home/it/sniper-data/prevent/state"
Q3 = "/home/it/sniper-data/presend_quiet3"; T37 = "/home/it/sniper-data/presend_quiet4/tab37"; T38 = "/home/it/sniper-data/prevent/state/tab38b"   # my decode of run_20261029_1400 chunks 1793304940..1793313650 (r37 tail + all of r38)
CUT_BT = 1793240200
CUT37 = 1793305232            # tab37 last block time 1793305231; tab38b from here
t0 = time.time()


def main():
    R = pickle.load(open(f"{D}/windows.pkl", "rb")); O = pickle.load(open(f"{D}/obs_rearm.pkl", "rb"))
    need = set()
    for r in R.values():
        for x in r["wins"]: need.add(x["mint"])
        if not r["live"]:
            for x in r["shadow"]: need.add(x["mint"])
    for W in O.values():
        for x in W: need.add(x["mint"])
    print("mints needed", len(need), flush=True)
    mints = sorted(need); mid = {m: k for k, m in enumerate(mints)}
    users = []; uid = {}

    def umap(names, arr):
        """map a source user-id array to global ids"""
        u = np.unique(arr); m = np.zeros(int(u.max()) + 1 if len(u) else 1, np.int32)
        for g in u.tolist():
            s = names[g]; k = uid.get(s)
            if k is None: k = uid[s] = len(users); users.append(s)
            m[g] = k
        return m[arr]

    parts = []
    # chain (quiet3)
    I = json.load(open(f"{Q3}/ids.json")); ml = I["mint"]; ul = I["user"]
    C = np.load(f"{Q3}/chain.npz")
    cm = C["mint"]
    want = np.zeros(len(ml), bool)
    for k, m in enumerate(ml):
        if m in need: want[k] = True
    sel = want[cm]
    bt = C["bt"]; sel &= bt < CUT_BT
    ix = np.nonzero(sel)[0]
    print("chain rows", len(cm), "selected", len(ix), f"{time.time()-t0:.0f}s", flush=True)
    P = {"slot": C["s"][ix].astype(np.int64), "idx": C["i"][ix].astype(np.int32), "j": C["j"][ix].astype(np.int16), "buy": C["buy"][ix].astype(np.uint8),
         "sol": C["sol"][ix].astype(np.int64), "tok": C["tok"][ix].astype(np.int64), "vsol": C["vsol"][ix].astype(np.int64), "vtok": C["vtok"][ix].astype(np.int64),
         "bt": bt[ix].astype(np.int64)}
    mm = np.array([mid[ml[g]] for g in cm[ix].tolist()], np.int32) if len(ix) else np.zeros(0, np.int32)
    P["mint"] = mm; P["user"] = umap(ul, C["user"][ix]); P["signer"] = np.full(len(ix), -1, np.int32)
    parts.append(P); del C, cm, bt, sel
    for tab, lo, hi in ((T37, CUT_BT, CUT37), (T38, CUT37, 1 << 40)):
        T = np.load(f"{tab}/trades.npy"); ids = json.load(open(f"{tab}/ids.json"))
        want = np.zeros(len(ids), bool)
        for k, m in enumerate(ids):
            if m in need: want[k] = True
        sel = want[T["mint"]] & (T["bt"] >= lo) & (T["bt"] < hi)
        T = T[sel]
        P = {"slot": T["slot"].astype(np.int64), "idx": T["idx"].astype(np.int32), "j": T["j"].astype(np.int16), "buy": T["buy"].astype(np.uint8),
             "sol": T["sol"].astype(np.int64), "tok": T["tok"].astype(np.int64), "vsol": T["vsol"].astype(np.int64), "vtok": T["vtok"].astype(np.int64),
             "bt": T["bt"].astype(np.int64), "mint": np.array([mid[ids[g]] for g in T["mint"].tolist()], np.int32),
             "user": umap(ids, T["user"]) if len(T) else np.zeros(0, np.int32), "signer": umap(ids, T["signer"]) if len(T) else np.zeros(0, np.int32)}
        parts.append(P)
        print(tab, "selected", len(T), f"{time.time()-t0:.0f}s", flush=True)
    A = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    o = np.lexsort((A["j"], A["idx"], A["slot"], A["mint"]))
    A = {k: v[o] for k, v in A.items()}
    np.savez(f"{D}/tape.npz", **A)
    json.dump({"mints": mints, "users": users}, open(f"{D}/tape_ids.json", "w"))
    print("tape rows", len(A["slot"]), "mints with trades", len(np.unique(A["mint"])), "of", len(mints), f"{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
