#!/usr/bin/env python3
"""VERIFY step 6 [MEASURED from my tape; causal cutoffs]: per live window
  T2: cutoff = the trigger trade (all rows with (slot, idx) <= trigger's); re-arm: every row with slot < arm slot.
  nbuyers50  = distinct buyer wallets (not ours) in slots [s-49, s] up to the cutoff (whale included)   [STATE's definition]
  nbuy50     = number of buy trades in that range; oth50 = distinct buyers other than the whale; nbuyers20 / 100 variants
  cre_pct    = creator's (create record) balance % at the cutoff; oth6_arm = a non-whale non-ours wallet >= 6% at the cutoff
per live fill: oth6_sign = such a wallet at the filled try's signing position (attempt 'pos'), depth = 1 - p_pre / p_sign.
Out: /home/it/sniper-data/prevent/verify/feats.pkl {(run, w): {...}}"""
import pickle, collections, bisect
import numpy as np
OUT = "/home/it/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb")); TP = pickle.load(open(f"{OUT}/tape.pkl", "rb")); L = pickle.load(open(f"{OUT}/live.pkl", "rb"))
M, USERS, CR = TP["mints"], TP["users"], TP["creates"]
uid = {u: k for k, u in enumerate(USERS)}
OURS = {uid[u] for u in ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE") if u in uid}
SUP = 1e15

def cut(R, slot, idx=None):
    s = R["slot"]
    if idx is None: return int(np.searchsorted(s, slot, side="left"))
    a = int(np.searchsorted(s, slot, side="left")); b = int(np.searchsorted(s, slot, side="right"))
    return a + int(np.searchsorted(R["idx"][a:b], idx, side="right"))

def balances(R, n):
    bal = collections.defaultdict(float)
    for u, b, tk in zip(R["user"][:n].tolist(), R["buy"][:n].tolist(), R["tok"][:n].tolist()):
        bal[u] += tk if b else -tk
    return bal

att_pos = {}
for run, D in L.items():
    for w, lst in D["att"].items():
        for x in lst:
            if x[0] == "A": att_pos[(run, x[7])] = (x[5], x[4], x[3])
fills_by_w = collections.defaultdict(list)
for run, D in L.items():
    for f in D["fills"]: fills_by_w[(run, f["w"])].append(f)
out = {}; miss = collections.Counter()
for w in T["wins"]:
    R = M.get(w["mint"]); f = {"ok": False}
    key = (w["run"], w["w"])
    if R is None: miss["nomint"] += 1; out[key] = f; continue
    who = uid.get(w["who"], -1)
    if w["kind"] == "t2":
        n = cut(R, w["slot"], w["idx"]); s0 = w["slot"]
        trig_ok = n > 0 and int(R["slot"][n - 1]) == w["slot"] and int(R["idx"][n - 1]) == w["idx"]
        # the whale's trigger row present (any j of the trigger tx)
        a = int(np.searchsorted(R["slot"], w["slot"], side="left")); b = int(np.searchsorted(R["slot"], w["slot"], side="right"))
        trig_row = any(int(R["idx"][k]) == w["idx"] and int(R["user"][k]) == who and bool(R["buy"][k]) for k in range(a, b))
    else:
        s0 = (w["arm_slot"] or (w["slot"] + 3)) - 1; n = cut(R, s0 + 1); trig_ok = trig_row = None
    if n <= 0: miss["nohist"] += 1; out[key] = f; continue
    S = R["slot"][:n]; B = R["buy"][:n]; Us = R["user"][:n]
    notours = ~np.isin(Us, list(OURS))
    f = dict(ok=True, trig_ok=trig_ok, trig_row=trig_row, n_rows=n, first_slot=int(S[0]))
    for W_ in (20, 50, 100):
        m = (S > s0 - W_) & B & notours
        f[f"nbuyers{W_}"] = len(set(Us[m].tolist())); f[f"nbuy{W_}"] = int(m.sum())
        f[f"oth{W_}"] = len(set(Us[m].tolist()) - {who})
    # strictly before the trigger tx (excludes every row of the trigger tx)
    if w["kind"] == "t2":
        nb = cut(R, w["slot"], w["idx"] - 1)
        m = (R["slot"][:nb] > s0 - 50) & R["buy"][:nb] & ~np.isin(R["user"][:nb], list(OURS))
        f["nbuyers50_pre"] = len(set(R["user"][:nb][m].tolist()))
    bal = balances(R, n)
    c = CR.get(w["mint"]); cre = uid.get(c[0], -2) if c else -2
    f["creator"] = c[0] if c else None; f["cre_pct"] = max(bal.get(cre, 0.0), 0.0) / SUP * 100
    f["oth6_arm"] = any(v >= 0.06 * SUP for u, v in bal.items() if u != who and u not in OURS)
    f["whale_pct_arm"] = bal.get(who, 0.0) / SUP * 100
    # fills: holders at the filled try's signing position
    fl = fills_by_w.get(key)
    if fl:
        f0 = fl[0]; ap = att_pos.get((w["run"], (f0.get("sig") or "")[:16]))
        if ap and ap[0]:
            ps, pi, pj = ap[0][0], ap[0][1], ap[0][2]
            ns = cut(R, ps, pi)
            bs = balances(R, ns)
            f["oth6_sign"] = any(v >= 0.06 * SUP for u, v in bs.items() if u != who and u not in OURS)
            f["oth6_sign_n"] = sum(1 for u, v in bs.items() if u != who and u not in OURS and v >= 0.06 * SUP)
            f["sign_pos"] = (ps, pi)
        else: miss["nosignpos"] += 1
        if f0.get("p_sign") and f0.get("p_entry_pre"): f["depth"] = 1 - f0["p_entry_pre"] / f0["p_sign"]
    out[key] = f
pickle.dump(out, open(f"{OUT}/feats.pkl", "wb"))
t2 = [(w, out[(w["run"], w["w"])]) for w in T["wins"] if w["kind"] == "t2"]
ok = [x for x in t2 if x[1].get("ok")]
print("windows", len(T["wins"]), "t2", len(t2), "with tape", len(ok), "trigger row found", sum(1 for w, f in ok if f["trig_row"]), dict(miss))
per = collections.defaultdict(lambda: [0, 0, 0])
for w, f in t2:
    p = per[w["run"]]; p[0] += 1; p[1] += bool(f.get("ok") and f.get("trig_row")); p[2] += bool(f.get("ok") and f.get("nbuyers50", 9) <= 1)
print("per run t2 windows / trigger found / nbuyers50<=1:", {r: tuple(v) for r, v in sorted(per.items())})
