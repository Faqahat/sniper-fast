#!/usr/bin/env python3
"""VERIFY step 13 [INFERRED, simplified, independent of custom37]: what a removed shallow T2 fill (other >= 6% holder at signing, depth < 15%)
would have become under the holder-conditional 0.85 limit.
Counterfactual curve = the tape after our fill without our own rows (token deltas on V*T = k). The window keeps sending: tries signed in the
fill slot keep the live p_sign; tries signed in a later slot s use the price at the end of slot s-1; each try can land in its slot or the
next (deadline +1) and fills at the FIRST row after which the price <= (1 - D) x p_sign, D = 0.15 with another >= 6% holder at that
signing else 0.12 (optimistic catch: upper bound on refills). Exit: our tokens sold after the other rows of fill slot + 2 (200 ms timer +
landing); fee 1.25% of volume, fixed 2.01 mSOL + ATA net 0. Extra failed tries: 8 per remaining slot x 0.9 landed x 5,120 lamports.
Calibration: the same exit model on the LIVE fills vs their realized P&L. Size 0.696."""
import pickle, collections, json
import numpy as np
OUT = "/home/it/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb")); F = pickle.load(open(f"{OUT}/feats.pkl", "rb")); TP = pickle.load(open(f"{OUT}/tape.pkl", "rb"))
M, USERS = TP["mints"], TP["users"]; uid = {u: k for k, u in enumerate(USERS)}
OURS = {uid[u] for u in ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE") if u in uid}
R20 = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
SUP = 1e15; FEE = 0.0125; FIX = 0.00201; SIZE = 0.696
tw = {(x["run"], x["w"]): x for x in T["trades"]}

def sim_exit(V, Tk, rows, k0, exit_slot):
    """buy SIZE at (V, Tk), apply other rows (token deltas) with slot <= exit_slot, sell"""
    x = SIZE / (1 + FEE); tok = Tk * x / (V + x); k = V * Tk
    Tn = Tk - tok
    for (s, i, b, tk, u) in rows:
        if s > exit_slot: break
        Tn = Tn - tk if b else Tn + tk
    Vn = k / Tn
    out = Vn * tok / (Tn + tok) * (1 - FEE)
    return out - SIZE - FIX

res = collections.defaultdict(lambda: collections.Counter()); calib = collections.defaultdict(lambda: [0.0, 0.0, 0])
for w in T["wins"]:
    if w["run"] not in R20 or w["kind"] != "t2": continue
    x = tw.get((w["run"], w["w"]))
    if not x: continue
    f = F.get((w["run"], w["w"]), {}); R = M.get(w["mint"])
    if R is None or x["fslot"] is None: continue
    S, I, B, TK, U, VS, VT = R["slot"], R["idx"], R["buy"], R["tok"], R["user"], R["vsol"], R["vtok"]
    # our fill row and the state before it
    a = int(np.searchsorted(S, x["fslot"], side="left")); b = int(np.searchsorted(S, x["fslot"], side="right"))
    pos = None
    for kk in range(a, b):
        if int(I[kk]) == x["fidx"] and int(U[kk]) in OURS: pos = kk; break
    if pos is None: res[w["run"]]["nofillrow"] += 1; continue
    prev = pos - 1
    while prev >= 0 and int(U[prev]) in OURS: prev -= 1
    if prev < 0: continue
    V0, T0 = float(VS[prev]), float(VT[prev]); k = V0 * T0
    after = [(int(S[j]), int(I[j]), bool(B[j]), float(TK[j]), int(U[j])) for j in range(pos + 1, len(S)) if int(U[j]) not in OURS and int(S[j]) <= (w["en_slot"] or x["fslot"] + 12) + 4]
    # calibration on the live fill (entry at the live state)
    mod = sim_exit(V0, T0, after, k, x["fslot"] + 2)
    c = calib[w["run"]]; c[0] += mod; c[1] += x["unit"] - x["refund"] + (x["refund"]) if False else x["s"]; c[2] += 1
    removed = bool(f.get("oth6_sign") and f.get("depth") is not None and f["depth"] < 0.15)
    if not removed: continue
    r = res[w["run"]]; r["removed"] += 1; r["live_s"] += x["s"]
    # holders before our fill (for D at later signings), whale id
    who = uid.get(w["who"], -1)
    bal = collections.defaultdict(float)
    for j in range(0, pos):
        if int(U[j]) in OURS: continue
        bal[int(U[j])] += float(TK[j]) if B[j] else -float(TK[j])
    en = w["en_slot"] or (x["fslot"] + 10)
    # walk the counterfactual path slot by slot
    Tc = T0; price = lambda Tv: (k / Tv) / Tv
    psign_live = x["p_sign"]
    tries = [(x["fslot"], psign_live, 0.15 if f.get("oth6_sign") else 0.12)]   # remaining tries of the fill slot (live p_sign)
    j = 0; refill = None; cur_slot = x["fslot"]
    rows = after
    # index rows by slot
    by_slot = collections.defaultdict(list)
    for row in rows: by_slot[row[0]].append(row)
    state_T = T0
    for s in range(x["fslot"], en + 2):
        if s > x["fslot"] and s <= en:
            p_s = price(state_T)
            oth = any(v >= 0.06 * SUP for u, v in bal.items() if u != who)
            tries.append((s, p_s, 0.15 if oth else 0.12))
        active = [t_ for t_ in tries if t_[0] <= s <= t_[0] + 1]
        for row in by_slot.get(s, []):
            _, _, bb, tk, u = row
            state_T = state_T - tk if bb else state_T + tk
            bal[u] += tk if bb else -tk
            p = price(state_T)
            for (ts, ps, D) in active:
                if p <= ps * (1 - D):
                    refill = (s, row, ps, D); break
            if refill: break
        if refill: break
    extra_slots = max(0, (refill[0] if refill else en) - x["fslot"])
    r["extra_fee"] += extra_slots * 8 * 0.9 * 5120 / 1e9
    if refill:
        s_r = refill[0]
        Vr, Tr = k / state_T, state_T
        rest = [row for row in rows if (row[0], row[1]) > (refill[1][0], refill[1][1])]
        pnl = sim_exit(Vr, Tr, rest, k, s_r + 2)
        r["refills"] += 1; r["refill_pnl"] += pnl
out = {}
tot = collections.Counter(); P = []
P(f"{'run':4s} removed live_s | refills refill_pnl extra_fee | direct gain  refill-adjusted gain | calib: model vs live (all T2 fills)") if False else None
print(f"{'run':4s} {'rm':>3s} {'live':>7s} | {'refil':>5s} {'r_pnl':>7s} {'xfee':>6s} | {'direct':>7s} {'adjusted':>8s} | calib model/live (n)")
for run in R20:
    r = res[run]; c = calib[run]
    direct = -r["live_s"]; adj = -r["live_s"] + r["refill_pnl"] - r["extra_fee"]
    out[run] = dict(removed=r["removed"], live=r["live_s"], refills=r["refills"], refill_pnl=r["refill_pnl"], extra_fee=r["extra_fee"], direct=direct, adjusted=adj, calib_model=c[0], calib_live=c[1], n=c[2])
    for kk in ("removed", "refills"): tot[kk] += r[kk]
    for kk, v in (("live", r["live_s"]), ("rp", r["refill_pnl"]), ("xf", r["extra_fee"]), ("direct", direct), ("adj", adj), ("cm", c[0]), ("cl", c[1])):
        tot[(kk, "PICK" if run not in ("A37", "A38") else run)] += v
    print(f"{run:4s} {r['removed']:3d} {r['live_s']:+7.3f} | {r['refills']:5d} {r['refill_pnl']:+7.3f} {r['extra_fee']:6.3f} | {direct:+7.3f} {adj:+8.3f} | {c[0]:+.3f} / {c[1]:+.3f} ({c[2]})")
for g in ("PICK", "A37", "A38"):
    print(f"{g}: direct {tot[('direct', g)]:+.3f} refill-adjusted {tot[('adj', g)]:+.3f} (refill pnl {tot[('rp', g)]:+.3f}, extra fees {tot[('xf', g)]:.3f}) | calib model {tot[('cm', g)]:+.3f} vs live {tot[('cl', g)]:+.3f}")
print("refills", tot["refills"], "of removed", tot["removed"])
json.dump(out, open(f"{OUT}/refill_model.json", "w"), indent=1)
