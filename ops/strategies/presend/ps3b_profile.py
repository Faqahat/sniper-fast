#!/usr/bin/env python3
# Step 1d: profile the pre-placers' FILLS (tapes) + their ATTEMPT streams (raw, failed txs included).
# Per fill: the dump just before it (same slot?), queue position, dump size, the dumper (type, holding, when it bought),
# token state (age, curve, earlier dumps, creator / insider holding, biggest holder), exit (hold, sells), round-trip P&L.
# Per mint (raw): first attempt vs the dump, attempts per slot, attempts per fill, failed-attempt fees.
# usage: python3 ps3b_profile.py <wallets.json>   -> presend/ps3b_fills.jsonl, ps3b_streams.jsonl, stdout summary
import sys, json, gzip, glob, zlib, collections
import numpy as np
import ps_common as C
SUP = 1e15            # pump supply in raw token units (1e9 tokens x 1e6)

def tape_fills(day, wallets):
    d = C.load(day); U = {C.crc(w): w for w in wallets}
    uid = d["uid"]; hit = np.isin(uid, list(U))
    toks = np.unique(d["tok"][hit]); out = []
    for t in toks.tolist():
        o = int(d["off"][t]); n = int(d["cnt"][t]); sl = slice(o, o + n)
        S = d["s"][sl]; A = d["arr"][sl]; B = d["buy"][sl].astype(bool); SOL = d["sol"][sl]; TK = d["tokn"][sl]; V = d["vsol"][sl]; T = d["vtok"][sl]
        FR = d["fr"][sl]; UID = uid[sl]; MV = d["move"][sl]; WT = d["wt"][sl]; TT = d["t"][sl]
        meta = d["meta"][t]; S0 = meta["S0"]; cre = C.crc(meta["creator"]) if meta.get("creator") else None
        bal = collections.defaultdict(float); first_buy = {}; last_buy = {}
        dumps = []          # (j, arr) of >= 2% sells so far
        pos = {}            # wallet -> list of open buys [j, tokens, sol_cost]
        rt = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])   # wallet -> buy cost, sell proceeds, tok bought, tok sold
        for j in range(n):
            u = int(UID[j])
            if u in U and B[j]:
                # previous dump (any slot) and same-slot dump
                jd = dumps[-1][0] if dumps else None
                same = jd is not None and S[jd] == S[j]
                big = max(bal.items(), key=lambda x: x[1]) if bal else (None, 0.0)
                rec = dict(day=day, w=U[u], m=meta["m"], tok=t, j=o + j, s=int(S[j]), t=int(TT[j]), sol=SOL[j] / 1e9, age_s=(S[j] - S0) * 0.4,
                           curve=V[j] / 1e9, p=V[j] / T[j], same=bool(same), ndumps_before=len(dumps) - (1 if same else 0))
                if jd is not None:
                    du = int(UID[jd]); pre_bal = bal[du] + TK[jd]
                    nb_between = int(B[jd + 1:j].sum()); ns_between = int((~B[jd + 1:j]).sum())
                    rec.update(dump_move=float(MV[jd]), dump_sol=SOL[jd] / 1e9, dump_dt_ms=float(A[j] - A[jd]), dump_dslots=int(S[j] - S[jd]),
                               trades_between=int(j - jd - 1), buys_between=nb_between, sells_between=ns_between,
                               dumper_wt=int(WT[jd]), dumper_is_creator=bool(du == cre), dumper_pct_supply=pre_bal / SUP * 100,
                               dumper_sold_frac=float(TK[jd] / pre_bal) if pre_bal > 0 else 1.0,
                               dumper_first_buy_slots=(int(S[jd] - S[first_buy[du]]) if du in first_buy else None),
                               dumper_last_buy_slots=(int(S[jd] - S[last_buy[du]]) if du in last_buy else None),
                               prev_dump_slots=(int(S[jd] - S[dumps[-2][0]]) if len(dumps) >= 2 else None),
                               first_dump_slots=int(S[j] - S[dumps[0][0]]))
                rec.update(big_pct=big[1] / SUP * 100, cre_pct=(bal.get(cre, 0.0) / SUP * 100 if cre else 0.0),
                           ins_pct=sum(v for k, v in bal.items() if k in G_INS.get(t, ())) / SUP * 100)
                pos.setdefault(u, []).append(rec)
            # update state
            if B[j]:
                bal[u] += TK[j]; first_buy.setdefault(u, j); last_buy[u] = j
                if u in U: r = rt[u]; r[0] += SOL[j] * (1 + FR[j]); r[2] += TK[j]
            else:
                bal[u] -= TK[j]
                if MV[j] <= -2.0: dumps.append((j, A[j]))
                if u in U:
                    r = rt[u]; r[1] += SOL[j] * (1 - FR[j]); r[3] += TK[j]
                    # attach exit info to the earliest open fill of this wallet on this token without an exit yet
                    for rec in pos.get(u, []):
                        if "exit_slots" not in rec:
                            rec["exit_slots"] = int(S[j] - rec["s"]); rec["exit_ms"] = float(A[j] - A[rec["j"] - o]); break
        last_p = V[-1] / T[-1]
        for u, recs in pos.items():
            r = rt[u]; left = max(r[2] - r[3], 0.0)
            pnl = (r[1] + left * last_p * 0.0 - r[0]) / 1e9          # open remainder valued at 0 (conservative); flagged below
            for k, rec in enumerate(recs):
                rec["tok_pnl"] = pnl if k == 0 else 0.0; rec["tok_left_frac"] = left / r[2] if r[2] > 0 else 0.0
                rec["n_sells_tok"] = None
                out.append(rec)
    return out

G_INS = {}
def insiders(day):
    d = C.load(day, cols=("tok", "s", "buy", "uid", "wt")); out = collections.defaultdict(set)
    m = d["wt"] == 2
    for t, u in zip(d["tok"][m].tolist(), d["uid"][m].tolist()): out[t].add(u)
    return out

def streams(day, wallets):
    """attempt streams from the raw rows: per (wallet, mint): buy attempts (failed + ok), sell attempts, slots"""
    S = collections.defaultdict(list)
    for f in sorted(glob.glob(f"{C.OUT}/raw/{day}_*.jsonl.gz") + glob.glob(f"{C.OUT}/raw2/{day}_*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r["w"] not in wallets or not r["mints"]: continue
            ix = " ".join(r["ixn"]); side = "B" if "Buy" in ix else ("S" if "Sell" in ix else "O")
            if side == "O" and r["tr"]: side = "B" if r["tr"][0][3] else "S"
            S[(r["w"], r["mints"][0])].append((r["s"], r["i"], side, r["err"], r["fee"] or 0, r["tips"], r["cup"], r["cul"]))
    return S

if __name__ == "__main__":
    wallets = json.load(open(sys.argv[1]))
    allf = []; allst = []
    for day in ("R1", "R2", "R3", "R4"):
        G_INS.clear(); G_INS.update(insiders(day))
        F = tape_fills(day, wallets); allf += F
        ST = streams(day, set(wallets))
        fills_by = collections.defaultdict(list)
        for r in F: fills_by[(r["w"], r["m"])].append(r)
        for (w, m), L in ST.items():
            L.sort(); b = [x for x in L if x[2] == "B"]; s_ = [x for x in L if x[2] == "S"]
            okb = [x for x in b if x[3] is None]; fb = [x for x in b if x[3] is not None]
            fl = sorted(fills_by.get((w, m), []), key=lambda r: r["j"])
            rec = dict(day=day, w=w, m=m, n_buy_att=len(b), n_buy_ok=len(okb), n_buy_fail=len(fb), n_sell_att=len(s_),
                       n_sell_ok=sum(1 for x in s_ if x[3] is None), fail_fee=sum(x[4] for x in fb), first_s=b[0][0] if b else None,
                       last_s=b[-1][0] if b else None, slots_active=len({x[0] for x in b}), errs=collections.Counter(x[3] for x in fb).most_common(3),
                       fills=[(r["s"], r.get("dump_move"), r.get("same")) for r in fl])
            if okb:
                s_f = okb[0][0]; rec["att_before_first_fill"] = sum(1 for x in b if (x[0], x[1]) < (okb[0][0], okb[0][1]))
                rec["slots_first_att_to_fill"] = s_f - b[0][0]
                pre = [x for x in b if x[0] < s_f]; rec["att_in_fill_slot_before"] = sum(1 for x in b if x[0] == s_f and x[1] < okb[0][1])
                rec["att_slots_before_fill"] = len({x[0] for x in pre})
            allst.append(rec)
        print(f"{day}: fills {len(F)}, streams {len(ST)}", flush=True)
    with open(f"{C.OUT}/ps3b_fills.jsonl", "w") as f:
        for r in allf: f.write(json.dumps(r, default=float) + "\n")
    with open(f"{C.OUT}/ps3b_streams.jsonl", "w") as f:
        for r in allst: f.write(json.dumps(r, default=float) + "\n")
