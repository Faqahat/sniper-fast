#!/usr/bin/env python3
"""EXPLORATION (DEV ONLY): competing PRE-SENDERS on the same trigger. A competitor = a wallet with failed txs in >= 100 of the dev
windows (trigger -> window end) and >= 5 failed txs per window it appears in (dense pre-sending), not us. Their failed attempts on the
token become visible on chain from the slot after the trigger. Knowledge at our try: their failed txs that landed in slots
<= send slot - LAG (LAG 1 or 2: our send slot is the current-slot estimate, the feed lags it).
NOTE: the engine does not see other wallets' failed txs today; this needs a failed-tx subscription for these wallets."""
import json, collections, sys
import numpy as np
from chainlib import B
import sim
F = np.load(f"{B}/fails.npz"); I = json.load(open(f"{B}/ids.json"))
mid = {s: k for k, s in enumerate(I["m"])}; WAL = I["w"]
OURS = {WAL.index("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"), WAL.index("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")}
fm = F["mint"]; o = np.argsort(fm, kind="stable"); st = np.searchsorted(fm[o], np.arange(len(I["m"]) + 1))
DEV = ("ams:r24", "ams:r25")
W = sim.load()
def fails_of(w):
    k = mid.get(w["mint"])
    if k is None: return np.zeros(0, np.int64), np.zeros(0, np.int64)
    r = o[st[k]:st[k + 1]]
    return F["s"][r].astype(np.int64), F["signer"][r].astype(np.int64)
# competitor list from DEV windows only
cnt = collections.Counter(); nwin = collections.Counter()
for w in W:
    if w["run"] not in DEV: continue
    S, sg = fails_of(w)
    m = (S > w["trig_slot"]) & (S <= w["en_slot"])
    for s in sg[m].tolist(): cnt[s] += 1
    for s in set(sg[m].tolist()): nwin[s] += 1
COMP = {s for s, n in nwin.items() if n >= 100 and cnt[s] / n >= 5 and s not in OURS}
json.dump(sorted(WAL[s] for s in COMP), open(f"{B}/competitors_dev.json", "w"))
print("competitor pre-senders (from dev windows):", len(COMP), [WAL[s][:8] for s in COMP])
for w in W:
    S, sg = fails_of(w)
    m = (S >= w["trig_slot"]) & np.isin(sg, list(COMP))
    w["comp_slots"] = np.sort(S[m])
    w["comp_n_win"] = int(((S > w["trig_slot"]) & (S <= w["en_slot"]) & np.isin(sg, list(COMP))).sum())
Wd = [w for w in W if w["run"] in DEV]
F_ = [w for w in Wd if w["filled"]]
y = np.array([w["net"] for w in F_]) / 1e9; nt = np.array([w.get("y_nb") == 0 for w in F_])
for LAG in (1, 2):
    pres = np.array([bool(len(w["comp_slots"]) and w["comp_slots"][0] <= w["fill_send_slot"] - LAG) for w in F_])
    print(f"LAG {LAG}: fills with a competitor attempt seen before our filling try: n={pres.sum()} wins={(y[pres] > 0).sum()} net={y[pres].sum():+.3f} notrade={nt[pres].sum()} | "
          f"without: n={(~pres).sum()} wins={(y[~pres] > 0).sum()} net={y[~pres].sum():+.3f} notrade={nt[~pres].sum()}")
anyc = np.array([w["comp_n_win"] > 0 for w in F_])
print(f"(label-side) competitor tried anywhere in the window: n={anyc.sum()} net={y[anyc].sum():+.3f} notrade={nt[anyc].sum()} | none: n={(~anyc).sum()} net={y[~anyc].sum():+.3f} notrade={nt[~anyc].sum()}")
for LAG in (1, 2):
    def send(w, k, LAG=LAG):
        cs = w["comp_slots"]; ss = w["X"]["tries"][k][0]
        return bool(len(cs) and cs[0] <= ss - LAG)
    print(f"RULE send a try only once a competitor attempt is seen (LAG {LAG}):\n" + sim.fmt(sim.evaluate(Wd, send=send), list(DEV)))
