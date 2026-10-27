#!/usr/bin/env python3
# Quote-token curves (R2 train / R3 test): census of wallets, and replays of launch snipe / dip-backrun / momentum at our speed.
# Prices in SOL-equivalent: V = u / vtok (u calibrated per token from buyers who paid SOL). 1 SOL per trade, constant product with our impact,
# fees: pump 1.25% each side + 0.5% swap SOL<->quote each side + 0.0015 SOL/tx x2. Variants: followers kept / dropped for 2 slots.
import gzip, pickle, json, collections, statistics, os, sys
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
Q = pickle.load(gzip.open("qtapes.pkl.gz", "rb")); L = rp.load_launches()
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(s, i): return s * 212.0 + i / max(SS.get(s, 0), i + 1, 380) * 212.0
FEE = 0.0125 + 0.005; TX = 0.0015; B = 1.0; HOLDS = (1, 3, 10, 30, 60)
def replay(rows, u, k_after, t_fill, drop2):
    """our buy fills on the state after row k_after (or the initial state if -1)"""
    vt = rows[k_after]["vtok"] if k_after >= 0 else 1.073e15
    V = u / vt; X = B / (1 + FEE); V2 = V + X; vt2 = u / V2; q = vt - vt2; vt = vt2; fs = rows[k_after]["s"] if k_after >= 0 else None
    val = lambda vt: (u / vt - u / (vt + q)) * (1 - FEE)
    path = [(t_fill, val(vt))]
    for k in range(k_after + 1, len(rows)):
        t = rows[k]; mt = ms(t["s"], t["i"])
        if mt - t_fill > 65_000: break
        vb = rows[k - 1]["vtok"] if k else 1.073e15
        if t["buy"]:
            if drop2 and fs is not None and t["s"] - fs <= 2: continue
            dV = u / t["vtok"] - u / vb; vt = u / (u / vt + dV)
        else: vt = vt + t["tok"]
        path.append((mt, val(vt)))
    return {h: [p for m_, p in path if m_ - t_fill <= h * 1000][-1] - B - 2 * TX for h in HOLDS}
R = collections.defaultdict(list); W = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0, 0]))
comp = collections.defaultdict(list)
for m, d in Q.items():
    rows = d["rows"]; u = d["u"]; c = L.get(m)
    if not c: continue
    run = rows[0]["run"]; tc = ms(c["slot"], c.get("idx") or 0)
    # census
    pos = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
    for k, t in enumerate(rows):
        vb = rows[k - 1]["vtok"] if k else 1.073e15
        amt = abs(u / t["vtok"] - u / vb)
        p = pos[t["user"]]
        if t["buy"]: p[0] += amt; p[2] += t["tok"]
        else: p[1] += amt; p[3] += t["tok"]
    for usr, p in pos.items():
        if p[2] and p[3] >= 0.98 * p[2]:
            pnl = p[1] * (1 - FEE) - p[0] * (1 + FEE) - 2 * TX; w = W[usr][run]; w[0] += 1; w[1] += pnl; w[2] += pnl > 0
    # launch snipe at +75 ms
    for T in (75, 200):
        k = -1
        while k + 1 < len(rows) and ms(rows[k + 1]["s"], rows[k + 1]["i"]) - tc <= T: k += 1
        for d2 in (False, True): R[("snipe", T, d2, run)].append(replay(rows, u, k, tc + T, d2))
    # dips and momentum
    last_mom = -1e18
    for k, t in enumerate(rows):
        vb = rows[k - 1]["vtok"] if k else 1.073e15; amt = abs(u / t["vtok"] - u / vb); t0 = ms(t["s"], t["i"])
        if not t["buy"] and amt >= 1.0:
            for T in (35, 75):
                kk = k
                while kk + 1 < len(rows) and ms(rows[kk + 1]["s"], rows[kk + 1]["i"]) - t0 <= T: kk += 1
                for d2 in (False, True): R[("dip1", T, d2, run)].append(replay(rows, u, kk, t0 + T, d2))
            comp[run].append(len({x["user"] for x in rows[k + 1:] if x["buy"] and ms(x["s"], x["i"]) - t0 <= 1000}))
        if t["buy"] and t0 - last_mom > 60_000:
            net = 0.0; j = k
            while j >= 0 and t0 - ms(rows[j]["s"], rows[j]["i"]) <= 10_000:
                vbj = rows[j - 1]["vtok"] if j else 1.073e15; a = abs(u / rows[j]["vtok"] - u / vbj); net += a if rows[j]["buy"] else -a; j -= 1
            if net >= 5:
                last_mom = t0; kk = k
                while kk + 1 < len(rows) and ms(rows[kk + 1]["s"], rows[kk + 1]["i"]) - t0 <= 75: kk += 1
                for d2 in (False, True): R[("mom5", 75, d2, run)].append(replay(rows, u, kk, t0 + 75, d2))
pickle.dump(dict(R=dict(R), W={k: dict(v) for k, v in W.items()}), open("qstudy.pkl", "wb"))
print(f"calibrated quote-curve tokens: {len(Q)} (R2 {sum(1 for d in Q.values() if d['rows'][0]['run'] == 'R2')}, R3 {sum(1 for d in Q.values() if d['rows'][0]['run'] == 'R3')})")
print("buyers within 1 s after a >= 1 SOL-eq sell (competition), median:", {r: statistics.median(v) for r, v in comp.items() if v})
print("\n=== replays, 1 SOL (total SOL-eq; share up). kept = followers kept, drop2 = followers in 2 slots after us dropped")
for key in sorted({(k[0], k[1], k[2]) for k in R}):
    for run in ("R2", "R3"):
        v = R.get((key[0], key[1], key[2], run), [])
        if v: print(f"  {key[0]:5s} T={key[1]:3d} {'drop2' if key[2] else 'kept ':5s} {run} n={len(v):6d} | " + " | ".join(f"{h}s {sum(x[h] for x in v):+7.1f} ({sum(1 for x in v if x[h] > 0)/len(v):.0%})" for h in HOLDS))
print("\n=== consistent quote-curve winners (>= 15 closed positions per day, both days > 0, SOL-eq)")
rows = [(d["R2"][1] + d["R3"][1], u, d) for u, d in W.items() if "R2" in d and "R3" in d and d["R2"][0] >= 15 and d["R3"][0] >= 15 and d["R2"][1] > 0 and d["R3"][1] > 0]
print(f"  wallets: {len(rows)}")
for tot, usr, d in sorted(rows, reverse=True)[:25]:
    print(f"  {usr}  R2 {d['R2'][1]:+7.1f} ({d['R2'][0]} pos, win {d['R2'][2]/d['R2'][0]:.0%}) | R3 {d['R3'][1]:+7.1f} ({d['R3'][0]} pos, win {d['R3'][2]/d['R3'][0]:.0%})")
