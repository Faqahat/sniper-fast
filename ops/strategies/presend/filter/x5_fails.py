#!/usr/bin/env python3
"""EXPLORATION (DEV ONLY): other wallets' FAILED pump txs on the token (competing pre-senders / bots) before the trigger and during the
window up to our filling try's send slot. NOTE: the engine's feed does not carry other wallets' failed txs today (own_fail_watch only)."""
import json, collections
import numpy as np
from chainlib import B
F = np.load(f"{B}/fails.npz")
I = json.load(open(f"{B}/ids.json"))
mid = {s: k for k, s in enumerate(I["m"])}; wid = {s: k for k, s in enumerate(I["w"])}
ours = {wid.get("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"), wid.get("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")}
fs = json.load(open(f"{B}/failsigners.json"))
heavy = {wid[w] for w, n in fs.items() if n >= 2000 and w in wid}
print("heavy failers (>= 2000 failed pump txs in the span):", len(heavy))
fm = F["mint"]; o = np.argsort(fm, kind="stable"); st = np.searchsorted(fm[o], np.arange(len(I["m"]) + 1))
W = [w for w in json.load(open(f"{B}/windows.json")) if w["run"] in ("ams:r24", "ams:r25") and w["chain_ok"]]
for w in W:
    k = mid[w["mint"]]; r = o[st[k]:st[k + 1]]
    S = F["s"][r].astype(np.int64); sg = F["signer"][r]
    oth = ~np.isin(sg, list(ours))
    s0 = w["trig_slot"]
    w["f_pre5"] = int((oth & (S >= s0 - 5) & (S <= s0)).sum())
    w["f_pre5_heavy"] = int((oth & (S >= s0 - 5) & (S <= s0) & np.isin(sg, list(heavy))).sum())
    w["f_pre50_signers"] = len(set(sg[oth & (S >= s0 - 50) & (S <= s0)].tolist()))
    if w["filled"]:
        se = w["fill_send_slot"]
        w["f_during"] = int((oth & (S > s0) & (S < se)).sum())
        w["f_during_signers"] = len(set(sg[oth & (S > s0) & (S < se)].tolist()))
Fl = [w for w in W if w["filled"]]
y = np.array([w["net"] for w in Fl]) / 1e9; nt = np.array([w.get("y_nb") == 0 for w in Fl])
for k, bins in (("f_pre5", [(0, 1), (1, 5), (5, 20), (20, 1e9)]), ("f_pre5_heavy", [(0, 1), (1, 5), (5, 1e9)]), ("f_pre50_signers", [(0, 1), (1, 3), (3, 6), (6, 1e9)]),
                ("f_during", [(0, 1), (1, 5), (5, 20), (20, 1e9)]), ("f_during_signers", [(0, 1), (1, 2), (2, 4), (4, 1e9)])):
    x = np.array([w.get(k, 0) for w in Fl])
    print(k)
    for lo, hi in bins:
        m = (x >= lo) & (x < hi)
        print(f"   [{lo},{hi}) n={m.sum():3d} wins={(y[m] > 0).sum():3d} net={y[m].sum():+.3f} notrade={nt[m].sum()}")
