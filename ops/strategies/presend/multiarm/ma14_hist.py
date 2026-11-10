#!/usr/bin/env python3
"""FILTERS step 1 [MEASURED, read-only]: the timer-hazard history for the ST filter (TIMING's a2 rule), built for EVERY wallet that
holds >= 6% of any token at some point in the replayed runs' tapes (r37 paper_audit/tab, r38 tab38f, r39 tab39), not only TIMING's
5,675 live-fill wallets (the replay fills windows live never filled).
History = every pump.fun curve trade of those wallets, 10-24 19:25 PKT -> the r39 tape end, from the decoded tapes on disjoint slot ranges:
  presend_quiet3 chain [460883340, 462709231) | presend_young/ext [462709231, 462710488) | paper_audit/tab [462710488, 463011691)
  multiarm/tabgapA [463011691, 463021093) | tab38f [463021093, 463053837) | tabgapB [463053837, 463081489) | tab39 [463081489, ...)
Positions (TIMING t3_pos): per (wallet, mint) the first buy slot b0 and the first sell slot after it s1 (-1: none yet).
Out: /home/it/sniper-data/multiarm/hz_pos.npz (u, m, b0, s1 sorted by u, b0) + hz_ids.json (users, mints)"""
import json, gc
import numpy as np
D = "/home/it/sniper-data"
OURS = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
RUN_TABS = [f"{D}/paper_audit/tab", f"{D}/multiarm/tab38f", f"{D}/multiarm/tab39f"]
SRC = [("chain", f"{D}/presend_quiet3", 460883340, 462709231), ("chain", f"{D}/presend_young/ext", 462709231, 462710488),
       ("tab", f"{D}/paper_audit/tab", 462710488, 463011691), ("tab", f"{D}/multiarm/tabgapA", 463011691, 463021093),
       ("tab", f"{D}/multiarm/tab38f", 463021093, 463053837), ("tab", f"{D}/multiarm/tabgapB", 463053837, 463081489),
       ("tab", f"{D}/multiarm/tab39f", 463081489, 10 ** 12)]


def big_wallets(tab):
    T = np.load(f"{tab}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{tab}/ids.json"))
    m = np.asarray(T["mint"]).astype(np.int64); u = np.asarray(T["user"]).astype(np.int64)
    tok = np.asarray(T["tok"]).astype(np.int64); buy = np.asarray(T["buy"]).astype(bool)
    d = np.where(buy, tok, -tok); key = m * (1 << 32) + u
    o = np.argsort(key, kind="stable"); ks = key[o]; cs = np.cumsum(d[o])
    brk = np.nonzero(ks[1:] != ks[:-1])[0] + 1; st = np.concatenate([[0], brk])
    base = np.repeat(np.concatenate([[0], cs[brk - 1]]), np.diff(np.concatenate([st, [len(ks)]])))
    mx = np.maximum.reduceat(cs - base, st)
    users = ks[st] & ((1 << 32) - 1)
    return {ids[int(x)] for x in users[mx >= 6e13].tolist()} - set(OURS)


def main():
    V = set()
    for tab in RUN_TABS: V |= big_wallets(tab)
    Vn = sorted(V); Vi = {u: k for k, u in enumerate(Vn)}
    print("wallets", len(Vn), flush=True)
    MINTS = []; Mi = {}
    cols = {k: [] for k in ("slot", "idx", "j", "mint", "user", "buy")}
    for kind, path, lo, hi in SRC:
        if kind == "chain":
            I = json.load(open(f"{path}/ids.json")); ml = I["mint"]; ul = I["user"]
            z = np.load(f"{path}/chain.npz")
            wid = np.array([k for k, u in enumerate(ul) if u in Vi], dtype=np.int64)
            u = z["user"]; s = z["s"]
            m = np.isin(u, wid) & (s >= lo) & (s < hi); sel = np.nonzero(m)[0]; del m
            uu = u[sel]; del u
            cols["slot"].append(s[sel].astype(np.int64)); del s
            cols["idx"].append(z["i"][sel].astype(np.int32)); cols["j"].append(z["j"][sel].astype(np.int16)); cols["buy"].append(z["buy"][sel].astype(np.int8))
            mm = z["mint"][sel]
            names_m = [ml[int(x)] for x in mm]; names_u = [ul[int(x)] for x in uu]
        else:
            T = np.load(f"{path}/trades.npy", mmap_mode="r"); ids = json.load(open(f"{path}/ids.json"))
            wid = np.array([k for k, u in enumerate(ids) if u in Vi], dtype=np.int64)
            u = np.asarray(T["user"]); s = np.asarray(T["slot"])
            m = np.isin(u, wid) & (s >= lo) & (s < hi); sel = np.nonzero(m)[0]; del m
            t = np.asarray(T[sel])
            cols["slot"].append(t["slot"].astype(np.int64)); cols["idx"].append(t["idx"].astype(np.int32)); cols["j"].append(t["j"].astype(np.int16))
            cols["buy"].append(t["buy"].astype(np.int8))
            names_m = [ids[int(x)] for x in t["mint"]]; names_u = [ids[int(x)] for x in t["user"]]
            del u, s, T
        mk = np.empty(len(names_m), np.int32)
        for n, x in enumerate(names_m):
            g = Mi.get(x)
            if g is None: g = Mi[x] = len(MINTS); MINTS.append(x)
            mk[n] = g
        cols["mint"].append(mk); cols["user"].append(np.array([Vi[x] for x in names_u], np.int32))
        print(path.split("sniper-data/")[1], lo, hi, len(sel), flush=True)
        gc.collect()
    A = {k: np.concatenate(v) for k, v in cols.items()}
    o = np.lexsort((A["j"], A["idx"], A["slot"], A["mint"], A["user"]))
    A = {k: v[o] for k, v in A.items()}
    u = A["user"]; m = A["mint"]; n = len(u)
    brk = np.nonzero((u[1:] != u[:-1]) | (m[1:] != m[:-1]))[0] + 1
    st = np.concatenate([[0], brk]); en = np.concatenate([brk, [n]])
    S = A["slot"]; B = A["buy"].astype(bool)
    pu, pm, pb0, ps1 = [], [], [], []
    for a, e in zip(st.tolist(), en.tolist()):
        bb = np.nonzero(B[a:e])[0]
        if len(bb) == 0: continue
        b0 = a + int(bb[0])
        ss = np.nonzero(~B[b0 + 1:e])[0]
        s1 = int(S[b0 + 1 + ss[0]]) if len(ss) else -1
        pu.append(int(u[a])); pm.append(int(m[a])); pb0.append(int(S[b0])); ps1.append(s1)
    P = np.zeros(len(pu), dtype=[("u", "i4"), ("m", "i4"), ("b0", "i8"), ("s1", "i8")])
    P["u"] = pu; P["m"] = pm; P["b0"] = pb0; P["s1"] = ps1
    P = P[np.lexsort((P["b0"], P["u"]))]
    np.savez(f"{D}/multiarm/hz_pos.npz", P=P)
    json.dump({"user": Vn, "mint": MINTS}, open(f"{D}/multiarm/hz_ids.json", "w"))
    sold = P["s1"] >= 0
    print("trades", n, "positions", len(P), "sold", int(sold.sum()), "median hold slots", float(np.median(P["s1"][sold] - P["b0"][sold])))


if __name__ == "__main__":
    main()
