#!/usr/bin/env python3
"""D2-D5 tabs lost their user b58 list (ids.json -> archived dv8). Map the competitor + our wallets: their rows in the haqqml fresh
tape (10-21..10-28) -> tx signature hashes -> the same tx rows in each tab -> tab user id (majority). Writes ids.json (tab mint
names from omen3 + these users) into /home/it/sniper-data/comp_rearm/tabs/tab_D*/ with symlinks to the data."""
import sys, os, json, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comps import COMP
OUR = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
HQ = "/home/it/sniper-data/haqqml/fresh/tape"; H = np.load(HQ + "/trades.npy", mmap_mode="r"); HU = json.load(open(HQ + "/users.json"))
hu = {v: k for k, v in enumerate(HU)}
want = list(COMP.values()) + list(OUR)
hus = np.asarray(H["user"]); hsg = np.asarray(H["sigh"])
sig_of = {w: set(hsg[hus == hu[w]].tolist()) for w in want if w in hu}
for d in (2, 3, 4, 5):
    src = f"/home/it/sniper-data/omen3/tabs/tab_D{d}"; dst = f"/home/it/sniper-data/comp_rearm/tabs/tab_D{d}"; os.makedirs(dst, exist_ok=True)
    for f in ("trades.npy", "slots.npy", "creates.json"):
        if not os.path.exists(f"{dst}/{f}"): os.symlink(os.path.realpath(f"{src}/{f}"), f"{dst}/{f}")
    ids = json.load(open(f"{src}/ids.json"))
    T = np.load(f"{src}/trades.npy", mmap_mode="r"); sg = np.asarray(T["sigh"]); us = np.asarray(T["user"])
    rep = []
    for w, ss in sig_of.items():
        m = np.isin(sg, np.fromiter(ss, dtype=sg.dtype))
        c = collections.Counter(us[m].tolist()).most_common(2)
        if c and (len(c) == 1 or c[0][1] > 5 * c[1][1]):
            u = c[0][0]
            if ids[u] and ids[u] != w: rep.append(f"CLASH {w[:8]}")
            ids[u] = w; rep.append(f"{w[:6]}={u}({c[0][1]})")
        else: rep.append(f"{w[:6]}:none{c}")
    json.dump(ids, open(f"{dst}/ids.json", "w")); print(d, " ".join(rep), flush=True)
