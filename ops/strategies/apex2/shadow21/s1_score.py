#!/usr/bin/env python3
"""SHADOW21 s1: score APEX-3 shadow run 21 buys on the real tape with the APEX-REALISM replay (r3_sim.py, imported
verbatim: live-calibrated landing clock draws, guard 'first' = no other >=0.05 SOL non-bundle buy ahead, curve/fees from
tape fee_bps, WAVE exit w0.4_6.0, phi=0.2 follower drop) and r5_score.py's M1 costs (CT 2.62 mSOL landed trip, CR 0.16 mSOL
revert, exec gap 1.15% of size).  Tape = sniper-data/apex2/shadow21/tab/run_20261103_1245 (b1_build of collect chunks).
Out: sniper-data/apex2/shadow21/scored.json"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/apex2/realism")
import r3_sim as R
OUT = "/home/moiz/sniper-data/apex2/shadow21"; TAB = f"{OUT}/tab/run_20261103_1245"
SHADOW = "/home/moiz/sniper-data/apex2/probes/apex_r21.jsonl"
CT, CR, XG = 0.00262, 0.00016, 0.0115
SIZES = (0.4, 1.0)

def load():
    T = np.load(f"{TAB}/trades.npy"); S = np.load(f"{TAB}/slots.npy"); C = json.load(open(f"{TAB}/creates.json"))
    ids = json.load(open(f"{TAB}/ids.json"))
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, gs = np.unique(T["mint"], return_index=True); ge = np.append(gs[1:], len(T))
    GS = np.zeros(len(ids), np.int64); GE = np.zeros(len(ids), np.int64); GS[um] = gs; GE[um] = ge
    R.G.update(T=T, gs=GS, ge=GE, mid={ids[i]: i for i in um.tolist()}, ids=ids, pid=(ids.index(R.PAYER) if R.PAYER in ids else -1),
               sidx={int(s): k for k, s in enumerate(S["slot"].tolist())}, bsz=(S["maxi"].astype(np.float64) + 1))
    return C, S

if __name__ == "__main__":
    C, S = load()
    slots = set(S["slot"].tolist())
    recs = [json.loads(l) for l in open(SHADOW)]
    buys = [r for r in recs if r["ev"] == "buy_shadow"]; land = {r["id"]: r for r in recs if r["ev"] == "shadow_landscape"}
    jobs, meta, out = [], [], []
    for b in buys:
        c = C.get(b["mint"]); why = None
        if c is None: why = "create not in tape"
        elif not c.get("std"): why = "non-standard curve (excluded by b1)"
        elif not all(s in slots for s in range(int(c["slot"]), int(c["slot"]) + 40)): why = "slot gap in first 40 slots"
        m = dict(id=b["id"], mint=b["mint"], creator=b["ev_creator"], signer=b["signer"], score=b["entry"]["score"],
                 pass_=bool(b["entry"]["pass"]), t=b["t"] / 1e9, slot=b["slot"], route=b["route"]["client"], why=why,
                 holder=b.get("holder_reward"), dev_buy=b.get("dev_buy", 0) / 1e9)
        L = land.get(b["id"])
        if L: m.update(ls_found=L.get("create_found"), ls_same=L.get("buy_txs_same_slot_after_create"))
        if why is None:
            m["create_slot_tape"] = int(c["slot"]); m["slot_match"] = int(c["slot"]) == int(b["slot"])
            R.G["C"] = [(c, SIZES, True, None)]
            q, r = R.run_one(0)
            if r[0] == "ERR": m["why"] = "replay error: " + r[1][-200:]
            else:
                _, feat, Aref, EV, PL, _, _ = r
                m["feat"] = dict(nb=feat["nb"], rc=feat["rc"], first=feat["first"])
                for zi, z in enumerate(SIZES):
                    for hi, ph in enumerate(R.PHIS):
                        for xi, e in enumerate(R.EXITS):
                            pl = float(PL[1, 0, zi]); ev = float(EV[1, 0, zi, hi, xi])   # scale 1.0, guard first
                            m[f"pl_{z}"] = pl
                            m[f"net_{z}_{e}_{ph}"] = ev - pl * CT - (1 - pl) * CR
                            m[f"netx_{z}_{e}_{ph}"] = ev - pl * (CT + XG * z) - (1 - pl) * CR
                            m[f"cond_{z}_{e}_{ph}"] = (ev / pl - CT) if pl > 0 else None
                            a = float(Aref[zi, hi, xi]); m[f"A_{z}_{e}_{ph}"] = (a - CT) if np.isfinite(a) else -CR
        out.append(m)
    json.dump(out, open(f"{OUT}/scored.json", "w"), indent=0)
    print("buys", len(buys), "scored", sum(1 for m in out if m["why"] is None), {w: sum(1 for m in out if m["why"] == w) for w in set(m["why"] for m in out)})
