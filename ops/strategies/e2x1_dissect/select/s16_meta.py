#!/usr/bin/env python3
"""SELECT s16: create-time token metadata features per mint (all from the CreateEvent, known before any of his buys):
uri host take-rate (target-encoded on TRAIN tokens only = created before the newest 6 h, smoothed), name/symbol length, symbol upper,
non-ascii name, word count, 'pump' vanity suffix. Out: meta.npz (arrays indexed by tape mint id)."""
import sys, json, re, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names(); mid = {m: i for i, m in enumerate(MN)}
CA = json.load(open(f"{OUT}/creates_all.json"))
n = len(MN); TCUT = int(D["bt"].max()) - 6 * 3600
his = np.zeros(n, bool); his[np.unique(D["mint"][D["user"] == w])] = True
host = np.array(["?"] * n, dtype=object)
F = {k: np.full(n, np.nan, np.float32) for k in ("name_len", "sym_len", "sym_upper", "name_nonascii", "name_words", "vanity_pump", "host_rate")}
crbt = np.zeros(n, np.int64)
for k, v in CA.items():
    i = mid.get(k)
    if i is None: continue
    m = re.match(r"https?://([^/]+)", v.get("uri") or ""); host[i] = m.group(1) if m else "none"
    nm = v.get("name") or ""; sy = v.get("symbol") or ""
    F["name_len"][i] = len(nm); F["sym_len"][i] = len(sy); F["sym_upper"][i] = float(sy.isupper()); F["name_nonascii"][i] = float(any(ord(c) > 127 for c in nm))
    F["name_words"][i] = len(nm.split()); F["vanity_pump"][i] = float(k.endswith("pump")); crbt[i] = int(v.get("bt") or 0)
tr = (crbt > 0) & (crbt < TCUT)
cnt = collections.Counter(host[tr].tolist()); hit = collections.Counter(host[tr & his].tolist())
prior = hit_total = his[tr].sum() / max(tr.sum(), 1)
for i in np.flatnonzero(crbt > 0):
    h = host[i]; F["host_rate"][i] = (hit.get(h, 0) + 20 * prior) / (cnt.get(h, 0) + 20)
np.savez(f"{OUT}/meta.npz", **F)
print("meta for", int((crbt > 0).sum()), "mints; train prior", round(float(prior), 4))
