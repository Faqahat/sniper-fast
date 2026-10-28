#!/usr/bin/env python3
"""REARM step 3b (read-only; G2 continuation): the WHALE-HOLDER stop for re-arm windows. A next whale dump (one sell >= 6% of
supply) can only come from a wallet that holds >= 6%; the engine's Detector already keeps every wallet's balance of a followed token
(src/presend_live.rs DTok.wal). For every whale dump of ev_D<k>.pkl (r3_events.py), with the same tape cut and the same removal of
our own txs, this finds the first trade AFTER the end of slot dump+2 at which no wallet holds >= 6% of supply any more ('nobig',
(slot, idx)); None = some wallet holds >= 6% until the end of the tape. Balances are counted from the token's create (as r3).
A re window in mode H=2 (r4_days.py) arms only if a >= 6% holder exists at the end of slot dump+2 (nbig2 >= 1) and is stopped 30 ms
after the engine sees the 'nobig' trade (like the whale-sell stop). Out: evh_D<k>.pkl = {(mint, slot, idx): nobig}"""
import sys, os, pickle, time, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import rlib
from r3_events import our_sighs, OUT, WHALE


def main(D):
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/ev_D{D}.pkl", "rb")); EV = Z["EV"]
    tp = rlib.Tape(tab=f"{OUT}/tab_D{D}", with_ours=False)
    keep = ~np.isin(tp.sigh, np.fromiter(our_sighs(), dtype=np.uint64))
    idm = tp.id_map()
    by = collections.defaultdict(list)
    for e in EV: by[e["mint"]].append(e)
    out = {}
    for mint, es in by.items():
        a, e_ = tp.span[idm[mint]]
        rows = [k for k in range(a, e_) if keep[k]]
        bal = collections.defaultdict(int); nbig = 0; snap = np.zeros(len(rows), np.int32)
        for q, k in enumerate(rows):
            u = int(tp.user[k]); b0 = bal[u]
            bal[u] = b0 + (int(tp.tok[k]) if tp.buy[k] else -int(tp.tok[k]))
            nbig += int(bal[u] >= WHALE) - int(b0 >= WHALE)
            snap[q] = nbig
        rs = np.array([tp.s[k] for k in rows], np.int64)
        zero = np.flatnonzero(snap == 0)
        for ev in es:
            r_end = int(np.searchsorted(rs, ev["slot"] + 2, side="right"))
            z = zero[np.searchsorted(zero, r_end)] if np.searchsorted(zero, r_end) < len(zero) else None
            out[(mint, ev["slot"], ev["idx"])] = None if z is None else (int(tp.s[rows[z]]), int(tp.i[rows[z]]))
    tmp = f"{OUT}/evh_D{D}.pkl.new"
    pickle.dump(out, open(tmp, "wb")); os.replace(tmp, f"{OUT}/evh_D{D}.pkl")
    n_h = sum(1 for e in EV if e["ok"] and e["nbig2"] >= 1)
    print(f"D{D}: {len(out):,} dumps; usable with a >= 6% holder at dump+2: {n_h:,}; holder stop found {sum(v is not None for v in out.values()):,} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    for d in sys.argv[1].split(","): main(int(d))
