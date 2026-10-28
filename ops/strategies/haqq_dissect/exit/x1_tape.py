#!/usr/bin/env python3
"""EXIT step 1 (read-only): cut the dv8 tape (10-22 03:07 -> 10-28 01:12 PKT, 21.9 M pump.fun trades) down to every mint haqq or
one of our two live wallets traded, sorted in chain order (mint, slot, idx, j). Adds per-mint create info (slot, creator, mayhem).
Out: /home/moiz/sniper-data/haqq_dissect/exit/tape.npy, mints.pkl"""
import json, pickle, time
import numpy as np
TAB = "/home/moiz/sniper-data/dv8/tab"; OUT = "/home/moiz/sniper-data/haqq_dissect/exit"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
OURS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")


def main():
    t0 = time.time()
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    who = [idm[HAQQ]] + [idm[w] for w in OURS if w in idm]
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
    u = np.asarray(T["user"]); mt = np.asarray(T["mint"])
    mints = np.unique(mt[np.isin(u, who)])
    sel = np.isin(mt, mints)
    cols = ("slot", "idx", "j", "mint", "user", "buy", "sol", "tok", "vsol", "vtok", "fee_bps", "cfee_bps", "bt")
    R = np.zeros(int(sel.sum()), dtype=[(c, T.dtype[c]) for c in cols])
    for c in cols: R[c] = np.asarray(T[c])[sel]
    R = R[np.lexsort((R["j"], R["idx"], R["slot"], R["mint"]))]
    np.save(f"{OUT}/tape.npy", R)
    print(f"mints {len(mints):,} rows {len(R):,} ({time.time() - t0:.0f}s)", flush=True)
    CR = json.load(open(f"{TAB}/creates.json"))
    info = {}
    for m in mints.tolist():
        c = CR.get(ids[m]) or {}
        info[m] = dict(cs=c.get("slot"), ci=c.get("idx"), creator=idm.get(c.get("creator"), -1), mayhem=bool(c.get("mayhem")), vsol=c.get("vsol"), vtok=c.get("vtok"))
    pickle.dump(dict(info=info, who=dict(haqq=idm[HAQQ], FRA=idm.get(OURS[0]), AMS=idm.get(OURS[1]))), open(f"{OUT}/mints.pkl", "wb"))
    print(f"mayhem mints {sum(v['mayhem'] for v in info.values())}, with create {sum(v['cs'] is not None for v in info.values())} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
