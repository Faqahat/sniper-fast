#!/usr/bin/env python3
"""EXPLORATION (DEV ONLY): DURING rules - a try is sent only once the token shows enough activity by OTHER wallets (not the whale,
not us), counted on the trades the engine had seen when it signed the try. Also ARM rules on the token's history. Prints dev only."""
import sys
import numpy as np
import sim

DEV = ("ams:r24", "ams:r25")
W = sim.load(DEV)
OURS = sim._cache["ours"]
NCONF = 0


def oth_since(w, k, buys_only=False, distinct=False, last=None):
    rows = sim.known_rows(w, k)
    if rows is None: return 0
    kt = w["X"]["k_trig"]; wh = w["X"]["whale"]
    if last is None:
        r = rows[kt + 1:]
    else:
        pos = w["X"]["tries"][k][7]
        r = rows[rows[:, 0] >= pos[0] - last]
    m = (r[:, 3] != wh) & ~np.isin(r[:, 3], list(OURS))
    if buys_only: m &= r[:, 4] == 1
    if distinct: return len(set(r[m, 3].tolist()))
    return int(m.sum())


def show(name, **kw):
    global NCONF
    NCONF += 1
    res = sim.evaluate(W, **kw)
    print(f"--- [{NCONF}] {name}\n" + sim.fmt(res, list(DEV)))


show("BASE (live config)")
for N in (1, 2, 3, 4, 6):
    show(f"send only after >= {N} other trades since the trigger", send=lambda w, k, N=N: oth_since(w, k) >= N)
for N in (1, 2, 3):
    show(f"send only after >= {N} other BUYS since the trigger", send=lambda w, k, N=N: oth_since(w, k, buys_only=True) >= N)
for L, N in ((10, 2), (10, 4), (20, 4), (20, 6), (50, 8)):
    show(f"send only if >= {N} other trades in the last {L} slots (incl. before the trigger)", send=lambda w, k, L=L, N=N: oth_since(w, k, last=L) >= N)
print("configs tried:", NCONF)


# ---- added: STOP rules (tries start as live; the window stops at trigger + N slots if it stayed quiet)
def oth_list(w, k):
    rows = sim.known_rows(w, k)
    if rows is None: return rows
    kt = w["X"]["k_trig"]; wh = w["X"]["whale"]
    r = rows[kt + 1:]
    return r[(r[:, 3] != wh) & ~np.isin(r[:, 3], list(OURS))]


for N in (1, 2, 3, 4, 6):
    for M in (1, 2):
        show(f"STOP at send slot >= trigger + {N} if < {M} other trades since the trigger",
             send=lambda w, k, N=N, M=M: not (w["X"]["tries"][k][0] >= w["trig_slot"] + N and oth_since(w, k) < M))
print("configs tried:", NCONF)
