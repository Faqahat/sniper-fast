#!/usr/bin/env python3
"""WHO step 2 [MEASURED, read-only]: one market tape for 10-23 22:00 -> 10-30 03:55 PKT from the decoded tabs other studies built
(haqq_dissect D2-D6, omen3 D6/D7, paper_audit/tab, multiarm/tab38) + my decode of the two holes (tab_gap: 10-30 01:13-01:50 and
03:25-03:55). Each tab is used on a disjoint slot range.
Out (/home/moiz/sniper-data/prevent/who):
  mints.pkl   {mint: list of (slot, idx, j, buy, sol, tok, vsol, vtok, user)}  all trades of every window mint (live + paper)
  dumps.pkl   market-wide big sells (tok >= 3% supply): dict of arrays slot, bt, user(str), mint(str), tok, sol, drop, vsol
  creates.pkl {mint: (creator, slot, bt, mayhem)} every create
  clock.pkl   (slots, bts) arrays for slot -> unix time
  cover.json  per tab: range used, holes > 300 slots"""
import json, pickle, sys, gc
import numpy as np

D = "/home/moiz/sniper-data"
OUT = f"{D}/prevent/who"
SRC = [  # (kind, path, lo, hi_exclusive)
    ("chain", f"{D}/presend_quiet3", 460883340, 462709231),
    ("chain", f"{D}/presend_young/ext", 462709231, 462710488),
    ("tab", f"{D}/paper_audit/tab", 462710488, 463010350),
    ("tab", f"{D}/prevent/who/tab_gap", 463010350, 463021093),
    ("tab", f"{D}/multiarm/tab38", 463021093, 463049836),
    ("tab", f"{D}/prevent/who/tab_gap", 463049836, 463099999),
]
CREATES = [f"{D}/haqq_dissect/rearm/tab_D{k}/creates.json" for k in (2, 3, 4, 5, 6)] + [f"{D}/omen3/d6/tab_D6/creates.json", f"{D}/omen3/tab_D7/creates.json",
           f"{D}/paper_audit/tab/creates.json", f"{D}/prevent/who/tab_gap/creates.json", f"{D}/multiarm/tab38/creates.json"]
SUP = 1e15


def main():
    W = pickle.load(open(f"{OUT}/windows.pkl", "rb"))
    want = {w["mint"] for w in W if w.get("mint")}
    print("window mints", len(want), flush=True)
    mints = {}
    dl = {k: [] for k in ("slot", "bt", "user", "mint", "tok", "sol", "drop", "vsol")}
    creates = {}
    cs, cb = [], []
    cover = []
    for kind, tab, lo, hi in SRC:
        if kind == "chain":
            z = np.load(f"{tab}/chain.npz"); I = json.load(open(f"{tab}/ids.json")); mids, uids = I["mint"], I["user"]
            s = z["s"]; keep = (s >= lo) & (s < hi)
            T = {"slot": s[keep].astype(np.int64)}
            for c, n in (("i", "idx"), ("j", "j"), ("buy", "buy"), ("sol", "sol"), ("tok", "tok"), ("vsol", "vsol"), ("vtok", "vtok"), ("mint", "mint"), ("user", "user"), ("bt", "bt")):
                T[n] = z[c][keep]
            B = z["blocks"]; B = B[(B[:, 0] >= lo) & (B[:, 0] < hi)]
            sl = B[:, 0].astype(np.int64); bts = B[:, 2].astype(np.int64)
            o = np.argsort(sl, kind="stable"); sl, bts = sl[o], bts[o]
            del z
        else:
            X0 = np.load(f"{tab}/trades.npy"); X0 = X0[(X0["slot"] >= lo) & (X0["slot"] < hi)]
            T = {n: X0[n] for n in ("slot", "idx", "j", "buy", "sol", "tok", "vsol", "vtok", "mint", "user", "bt")}
            ids = json.load(open(f"{tab}/ids.json")); mids = uids = ids
            S = np.load(f"{tab}/slots.npy"); S = S[(S["slot"] >= lo) & (S["slot"] < hi)]
            sl = S["slot"].astype(np.int64); bts = S["bt"].astype(np.int64)
            del X0
        n = len(T["slot"])
        gaps = np.nonzero(np.diff(sl) > 300)[0]
        cover.append({"src": tab, "lo": int(sl[0]) if len(sl) else None, "hi": int(sl[-1]) if len(sl) else None, "n": int(n),
                      "holes": [[int(sl[g]), int(sl[g + 1])] for g in gaps]})
        cs.append(sl); cb.append(bts)
        gid = {k: i for i, k in enumerate(mids)}
        g = np.array(sorted(gid[m] for m in want if m in gid), dtype=np.int64)
        sel = np.nonzero(np.isin(T["mint"].astype(np.int64), g))[0]
        cols = [T[c][sel].tolist() for c in ("slot", "idx", "j", "buy", "sol", "tok", "vsol", "vtok", "mint", "user")]
        for r in zip(*cols):
            mints.setdefault(mids[r[8]], []).append((r[0], r[1], r[2], int(r[3]), r[4], r[5], r[6], r[7], uids[r[9]]))
        m = (T["buy"] == 0) & (T["tok"] >= 3e13)
        vs = T["vsol"][m].astype(np.float64); vt = T["vtok"][m].astype(np.float64); so = T["sol"][m].astype(np.float64); tk = T["tok"][m].astype(np.float64)
        pa = vs / np.maximum(vt, 1); pb = (vs + so) / np.maximum(vt - tk, 1)
        drop = 1 - pa / np.maximum(pb, 1e-30)
        dl["slot"].append(T["slot"][m].astype(np.int64)); dl["bt"].append(T["bt"][m].astype(np.int64)); dl["tok"].append(T["tok"][m].astype(np.int64))
        dl["sol"].append(T["sol"][m].astype(np.int64)); dl["drop"].append(drop); dl["vsol"].append(T["vsol"][m].astype(np.int64))
        dl["user"].append(np.array([uids[int(u)] for u in T["user"][m]], dtype=object)); dl["mint"].append(np.array([mids[int(u)] for u in T["mint"][m]], dtype=object))
        print(tab, lo, hi, "trades", n, "mint-trades", len(sel), "bigsells", int(m.sum()), "holes", len(gaps), flush=True)
        del T, mids, uids, gid, sel, cols; gc.collect()
    for cf in CREATES:
        C = json.load(open(cf))
        for mk, c in C.items():
            if mk not in creates:
                creates[mk] = (c.get("creator") or c.get("user"), int(c["slot"]), int(c.get("bt") or 0), bool(c.get("mayhem") or c.get("mayhem_ix")))
        print(cf, len(C), flush=True)
        del C; gc.collect()
    for k in mints: mints[k].sort()
    dumps = {k: np.concatenate(v) for k, v in dl.items()}
    pickle.dump(mints, open(f"{OUT}/mints.pkl", "wb"))
    pickle.dump(dumps, open(f"{OUT}/dumps.pkl", "wb"))
    pickle.dump(creates, open(f"{OUT}/creates.pkl", "wb"))
    pickle.dump((np.concatenate(cs), np.concatenate(cb)), open(f"{OUT}/clock.pkl", "wb"))
    json.dump(cover, open(f"{OUT}/cover.json", "w"), indent=1)
    print("mints with trades", len(mints), "of", len(want), "dumps", len(dumps["slot"]), "creates", len(creates))


if __name__ == "__main__":
    main()
