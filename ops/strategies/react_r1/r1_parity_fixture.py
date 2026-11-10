#!/usr/bin/env python3
"""dip40 REACT R1 parity fixture: random pump tapes (several mints, ~30 wallets, a bot list, the anchor, our wallet) scored with the
haqq7 study's OWN feature code (/home/it/sniper-studies/sniper-haqq7/sim.py run_mint, the feature part copied verbatim but for numpy -> lists) and
mask (test.py, policy R1_hqadd of /home/it/sniper-data/haqq7/frozen_rules.json). The engine's unit test (dip40_r1_tests.rs,
r1_parity_with_study) replays the same trades through react_r1::Book in tape order and must give the same features and verdict on
every study candidate. Plain python3, no pandas.
usage: r1_parity_fixture.py OUT.json"""
import sys, json, bisect, random
OURS_ID, HAQQ_ID = 99, 98
BOTS = set(range(1, 16))                       # listed wallets 1..15 (first_seen <= bt for all: the study's registry filter)
R1 = {"pct": (3, 6), "age": 30, "prior": (1, 1e9), "dipb": 2, "bots": 5, "hq": True}   # frozen_rules.json R1_hqadd
MINPCT, MINSOL = 1.0, 0.2

def tape(rng, lslot, n):
    """a sorted tape (s, i) of one mint: buys / sells by wallets 1..30, the anchor and us, sizes that cross the 1% / 3% / 6% bands"""
    S, I, B, SOL, TOK, U = [], [], [], [], [], []
    held = {}
    s = lslot
    for _ in range(n):
        s += rng.choice([0, 0, 0, 0, 1, 1, 1, 2, 3]) if rng.random() < 0.98 else rng.choice([40, 100, 101, 150, 199, 200, 201])
        u = rng.choice(list(range(1, 31)) + [HAQQ_ID] * 4 + [OURS_ID] * 2)
        buy = rng.random() < (0.8 if u == HAQQ_ID else 0.55) or held.get(u, 0) <= 0
        pct = rng.choice([0.2, 0.5, 0.99, 1.0, 1.5, 2.99, 3.0, 3.5, 4.2, 5.99, 6.0, 7.0])
        tok = int(pct * 1e13) if buy else min(int(pct * 1e13), held.get(u, 0)) or int(pct * 1e13)
        if not buy and rng.random() < 0.2: tok = held.get(u, tok)   # a full exit
        sol = rng.choice([0.05, 0.19, 0.2, 0.29, 0.3, 0.31, 0.8, 1.5, 3.0])
        held[u] = held.get(u, 0) + (tok if buy else -tok)
        S.append(s); I.append(len(S)); B.append(buy); SOL.append(int(sol * 1e9)); TOK.append(tok); U.append(u)
    return S, I, B, SOL, TOK, U

def features(S, I, B, SOL, TOK, U, lslot):
    """sim.py run_mint, the feature part (verbatim logic)"""
    n = len(S); ours = [u == OURS_ID for u in U]
    posb = [0.0] * n; pos = {}; lastbig = -10**9; dipflag = [False] * n
    big1 = [0] * (n + 1)
    for t in range(n):
        u = U[t]; p = pos.get(u, 0.0); posb[t] = p
        if B[t]:
            pos[u] = p + TOK[t]; dipflag[t] = (S[t] - lastbig <= 2) and not ours[t]
        else:
            pos[u] = p - TOK[t]
            if SOL[t] >= 3e8: lastbig = S[t]
        big1[t + 1] = big1[t] + int((not B[t]) and TOK[t] >= 1e13 and not ours[t])
    out = []
    for j in range(n):
        if B[j] or ours[j] or TOK[j] < MINPCT * 1e13 or SOL[j] < MINSOL * 1e9: continue
        s = S[j]
        w200 = bisect.bisect_left(S, s - 200); w100 = bisect.bisect_left(S, s - 100)
        bots100 = len(set(U[t] for t in range(w100, j) if U[t] in BOTS and not ours[t]))
        dipb = len(set(U[t] for t in range(w200, j) if dipflag[t]))
        hq_hold = False
        for t in range(j - 1, w200 - 1, -1):
            if U[t] == HAQQ_ID: hq_hold = (posb[t] + (TOK[t] if B[t] else -TOK[t])) > 1e10; break
        f = dict(j=j, dpct=TOK[j] / 1e13, age=s - lslot, prior1=int(big1[j] - big1[w200]), dipb=dipb, bots100=bots100, hq_hold=hq_hold)
        r = (f["dpct"] >= R1["pct"][0]) and (f["dpct"] < R1["pct"][1]) and f["age"] <= R1["age"] and R1["prior"][0] <= f["prior1"] <= R1["prior"][1] \
            and f["dipb"] >= R1["dipb"] and f["bots100"] >= R1["bots"] and f["hq_hold"]
        f["pass"] = bool(r)
        out.append(f)
    return out

def main():
    rng = random.Random(40)
    mints = []
    for k in range(120):
        lslot = 1_000_000 + 1000 * k
        n = rng.choice([30, 60, 120, 250])
        S, I, B, SOL, TOK, U = tape(rng, lslot, n)
        mints.append({"lslot": lslot, "trades": [[S[t], I[t], int(B[t]), SOL[t], TOK[t], U[t]] for t in range(len(S))],
                      "expect": features(S, I, B, SOL, TOK, U, lslot)})
    json.dump({"ours": OURS_ID, "anchor": HAQQ_ID, "bots": sorted(BOTS), "mints": mints}, open(sys.argv[1], "w"))
    c = sum(len(m["expect"]) for m in mints); p = sum(f["pass"] for m in mints for f in m["expect"])
    print(f"{len(mints)} mints, {sum(len(m['trades']) for m in mints)} trades, {c} study candidates, {p} R1 passes")

if __name__ == "__main__":
    main()
