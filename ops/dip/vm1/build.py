#!/usr/bin/env python3
"""VM1 independent check, step 2: merge the decoded files into one chain-ordered trade table (read-only on raw data).
Writes OUT/trades.npy (sorted by slot, idx, j; deduped), OUT/mints.json, OUT/users.json, OUT/slots.npy (block size
estimate per slot), OUT/holes.json (recording holes: >= HOLE consecutive slots with no record), OUT/ours.jsonl,
OUT/files.json (per file: slot range, truncated?).
Usage: build.py DECDIR OUT
"""
import sys, os, glob, json
import numpy as np

HOLE = 12          # >= 12 consecutive slots without any pump record = a recording hole (a skipped leader turn is 4)

def main(dec, out):
    files = sorted(glob.glob(os.path.join(dec, "*.npz")))
    mint_id, user_id, mints, users = {}, {}, [], []
    parts, slot_parts, ours, finfo = [], [], [], []
    for fn in files:
        z = np.load(fn, allow_pickle=True)
        tr = z["trades"].copy(); fm = z["mints"]; fu = z["users"]
        mm = np.empty(len(fm), np.uint32); uu = np.empty(len(fu), np.uint32)
        for k, m in enumerate(fm):
            if m not in mint_id: mint_id[m] = len(mints); mints.append(m)
            mm[k] = mint_id[m]
        for k, u in enumerate(fu):
            if u not in user_id: user_id[u] = len(users); users.append(u)
            uu[k] = user_id[u]
        if len(tr):
            tr["mint"] = mm[tr["mint"]]; tr["user"] = uu[tr["user"]]
        parts.append(tr)
        sl = z["slots"]; slot_parts.append(sl)
        ours += list(z["ours"])
        meta = json.loads(z["meta"][0])
        finfo.append({"npz": os.path.basename(fn), "lines": meta["lines"], "truncated": meta["truncated"],
                      "slot_lo": int(sl["slot"].min()) if len(sl) else None, "slot_hi": int(sl["slot"].max()) if len(sl) else None})
    T = np.concatenate(parts)
    order = np.lexsort((T["j"], T["idx"], T["slot"]))
    T = T[order]
    key = T["slot"].astype(np.uint64) * np.uint64(1 << 24) + T["idx"].astype(np.uint64) * np.uint64(256) + T["j"].astype(np.uint64)
    keep = np.ones(len(T), bool); keep[1:] = key[1:] != key[:-1]
    T = T[keep]
    np.save(os.path.join(out, "trades.npy"), T)
    S = np.concatenate(slot_parts)
    o = np.lexsort((-S["maxi"].astype(np.int64), S["slot"])); S = S[o]
    k2 = np.ones(len(S), bool); k2[1:] = S["slot"][1:] != S["slot"][:-1]; S = S[k2]
    np.save(os.path.join(out, "slots.npy"), S)
    # holes: gaps between recorded slots of >= HOLE slots
    s = S["slot"].astype(np.int64); d = np.diff(s)
    holes = [(int(s[k]) + 1, int(s[k + 1]) - 1) for k in np.where(d > HOLE)[0]]
    json.dump(holes, open(os.path.join(out, "holes.json"), "w"))
    json.dump(mints, open(os.path.join(out, "mints.json"), "w")); json.dump(users, open(os.path.join(out, "users.json"), "w"))
    seen = set()
    with open(os.path.join(out, "ours.jsonl"), "w") as f:
        for line in ours:
            r = json.loads(line)
            if r["sig"] in seen: continue
            seen.add(r["sig"]); f.write(line if line.endswith("\n") else line + "\n")
    json.dump(finfo, open(os.path.join(out, "files.json"), "w"))
    print(f"trades {len(T):,} (dups dropped {int((~keep).sum()):,}) | mints {len(mints):,} users {len(users):,} | slots {len(S):,} "
          f"{int(s[0])}->{int(s[-1])} | holes {len(holes)} ({sum(b - a + 1 for a, b in holes):,} slots) | ours {len(seen)}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
