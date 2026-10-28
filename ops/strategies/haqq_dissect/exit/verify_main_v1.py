#!/usr/bin/env python3
"""MAIN-SESSION independent check of analyst C's exit claim (own code; shares only the tape).
Each of our filled buys (tape signer = our wallet), the value of exactly those tokens sold at the curve state at time T:
  actual = state just before our real sell; alt exits = decision at fill + D, landing +L ms later (chain clock).
Value = vsol*tok/(vtok+tok) * (1 - (fee_bps+cfee_bps)/1e4). P&L = value - buy SOL (from the buy's trade event + its fees).
Pre-send vs regular by the buy tx's CU limit (pre-send 120000, regular 100000) from tab/ours.jsonl."""
import json, numpy as np, collections, time
TAB = "/home/moiz/sniper-data/dv8/tab"; SMS = 212.3
T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
OURS = (313621, 372603)
cul = {}
for l in open(f"{TAB}/ours.jsonl"):
    d = json.loads(l)
    if d["err"] is None: cul[(d["s"], d["i"])] = d.get("cul")
sel = np.isin(T["signer"], OURS); O = np.array(T[sel])
mints = np.unique(O["mint"])
M = np.array(T[np.isin(T["mint"], mints)]); M = M[np.lexsort((M["j"], M["idx"], M["slot"], M["mint"]))]
S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min()); bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.float64); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.float64) + 1
def cc(s, i):
    k = s - s0; n = bsz[k] if 0 <= k < len(bsz) and bsz[k] > 0 else 400.0
    return s * SMS + min(i / n, 0.999) * SMS
um, st = np.unique(M["mint"], return_index=True); en = np.append(st[1:], len(M)); rng = dict(zip(um.tolist(), zip(st.tolist(), en.tolist())))
def val(tok, r):
    fee = (int(r["fee_bps"]) + int(r["cfee_bps"])) / 1e4
    return float(r["vsol"]) * tok / (float(r["vtok"]) + tok) * (1 - fee) / 1e9
LAND = 59.0
res = collections.defaultdict(lambda: collections.defaultdict(float)); cnt = collections.Counter()
for k in range(len(O)):
    b = O[k]
    if not b["buy"]: continue
    kind = {120000: "presend", 100000: "regular"}.get(cul.get((int(b["slot"]), int(b["idx"]))), None)
    if kind is None: continue
    a, e = rng[int(b["mint"])]; seq = M[a:e]
    pos = np.flatnonzero((seq["slot"] == b["slot"]) & (seq["idx"] == b["idx"]) & (seq["signer"] == b["signer"]))
    if not len(pos): continue
    p = int(pos[0]); tok = float(b["tok"])
    later = np.flatnonzero((np.arange(len(seq)) > p) & (seq["signer"] == b["signer"]) & (seq["buy"] == 0))
    if not len(later): continue
    q = int(later[0])
    cost = float(b["sol"]) * (1 + (int(b["fee_bps"]) + int(b["cfee_bps"])) / 1e4) / 1e9
    t0 = cc(int(b["slot"]), int(b["idx"]))
    tt = np.array([cc(int(x["slot"]), int(x["idx"])) for x in seq[p:q + 1]])
    def state_at(t):                       # last trade (incl. ours) at or before chain time t, but never past our real sell
        j = int(np.searchsorted(tt, t, side="right")) - 1
        j = max(0, min(j, q - p - 1)); return seq[p + j]
    day = time.strftime("%m-%d", time.gmtime(int(b["bt"]) + 18000 + 2700))   # day window ending 23:15 PKT
    out = {"actual": val(tok, seq[q - 1]) - cost}
    for D in (100, 200, 300, 400):
        out[f"t{D}"] = val(tok, state_at(t0 + D + LAND)) - cost
    # wave rule: from fill+150, sell at the first 150 ms gap with no OUTSIDE buy; cap 1 s
    ob = [tt[j] for j in range(1, q - p + 1) if seq[p + j]["buy"] and seq[p + j]["signer"] not in OURS]
    tdec = t0 + 150; cap = t0 + 1000
    while tdec < cap:
        if not any(tdec - 150 < x <= tdec for x in ob): break
        tdec += 10
    out["wave"] = val(tok, state_at(min(tdec, cap) + LAND)) - cost
    for kk, v in out.items(): res[(kind, day)][kk] += v; res[(kind, "ALL")][kk] += v
    cnt[(kind, day)] += 1; cnt[(kind, "ALL")] += 1
keys = ["actual", "t100", "t200", "t300", "t400", "wave"]
print("curve P&L SOL (tx costs excluded); alt exits land +59 ms after the decision; capped at our real sell position")
print(f"{'kind':8s} {'day':6s} {'fills':>5s} " + " ".join(f"{k:>8s}" for k in keys))
for (kind, day) in sorted(res):
    r = res[(kind, day)]; print(f"{kind:8s} {day:6s} {cnt[(kind, day)]:5d} " + " ".join(f"{r[k]:+8.3f}" for k in keys))
