#!/usr/bin/env python3
"""REAL replay, step 2: merge the decoded chunks (decode.py) into one chain-ordered table (read-only on the raw data).
Writes OUT/trades.npy (slot, idx, j sorted; duplicates dropped; global ids), OUT/ids.json (id -> base58 string),
OUT/creates.json (one per mint, the first create), OUT/slots.npy (per slot: max tx index seen, records, block time),
OUT/ours.jsonl (our wallets' txs, deduplicated), OUT/files.json.
Usage: build.py DECDIR OUT"""
import sys, os, glob, json
import numpy as np

def main(dec, out):
    os.makedirs(out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(dec, "*.npz")))
    gid, names = {}, []
    def g(k):
        v = gid.get(k)
        if v is None: v = gid[k] = len(names); names.append(k)
        return v
    parts, sparts, ours, creates, finfo = [], [], [], {}, []
    for fn in files:
        z = np.load(fn, allow_pickle=True)
        ids = z["ids"]
        m = np.array([g(k) for k in ids], dtype=np.uint32) if len(ids) else np.zeros(0, np.uint32)
        tr = z["trades"].copy()
        if len(tr):
            for c in ("mint", "user", "signer"): tr[c] = m[tr[c]]
        parts.append(tr); sparts.append(z["slots"])
        ours += list(z["ours"])
        for c in z["creates"]:
            c = json.loads(c)
            k = c.get("mint")
            if k and (k not in creates or (c["slot"], c["idx"]) < (creates[k]["slot"], creates[k]["idx"])): creates[k] = c
        meta = json.loads(z["meta"][0]); sl = z["slots"]
        finfo.append({"npz": os.path.basename(fn), "lines": meta["lines"], "truncated": meta["truncated"],
                      "slot_lo": int(sl["slot"].min()) if len(sl) else None, "slot_hi": int(sl["slot"].max()) if len(sl) else None})
    T = np.concatenate(parts)
    o = np.lexsort((T["j"], T["idx"], T["slot"])); T = T[o]
    key = T["slot"].astype(np.uint64) * np.uint64(1 << 24) + T["idx"].astype(np.uint64) * np.uint64(256) + T["j"].astype(np.uint64)
    keep = np.ones(len(T), bool); keep[1:] = key[1:] != key[:-1]; T = T[keep]
    np.save(os.path.join(out, "trades.npy"), T)
    S = np.concatenate(sparts)
    o = np.lexsort((-S["maxi"].astype(np.int64), S["slot"])); S = S[o]
    k2 = np.ones(len(S), bool); k2[1:] = S["slot"][1:] != S["slot"][:-1]; S = S[k2]
    np.save(os.path.join(out, "slots.npy"), S)
    json.dump(names, open(os.path.join(out, "ids.json"), "w"))
    json.dump(creates, open(os.path.join(out, "creates.json"), "w"))
    seen = set()
    with open(os.path.join(out, "ours.jsonl"), "w") as f:
        for line in ours:
            r = json.loads(line)
            if r["sig"] in seen: continue
            seen.add(r["sig"]); f.write(line if line.endswith("\n") else line + "\n")
    json.dump(finfo, open(os.path.join(out, "files.json"), "w"))
    print(f"trades {len(T):,} (dups {int((~keep).sum()):,}) | ids {len(names):,} | creates {len(creates):,} | slots {len(S):,} "
          f"{int(S['slot'][0])}->{int(S['slot'][-1])} | ours {len(seen)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
