#!/usr/bin/env python3
"""FLAT study, step 3 (read-only): the per-window table of each run, joined with the chain (MEASURED).
Per window: the score (realized + rent back - failed-try fees), every try (send slot, pos, fee charged, fill flag), the trigger's
row on the chain; per fill: our buy and sell rows, the other wallets' trades strictly between them on chain (FLAT = none), the
engine's view at its time exit (other trades it had received since our buy before the exit decision; presend_live_tape).
Failed-try fee: the landing record's fee when its result is an error (5,120 if no fee logged); a try logged 'unseen' is priced
from our own failed tx on chain (0 if it never landed). Writes /home/moiz/sniper-data/presend_flat/base_<run>.pkl
usage: f3_base.py r24 r25 r26 r27"""
import sys, json, pickle, collections
import numpy as np
import flatlib as FL


def ourfails(phases):
    F = {}
    for ph in phases:
        F.update(json.load(open(f"{FL.D}/ourfail_p{ph}.json")))
    return F


def build(run, C, OF):
    L = pickle.load(open(f"{FL.D}/live_{run}.pkl", "rb"))
    c = C.c; S, I, J, U, BUY = c["s"], c["i"], c["j"], c["user"], c["buy"]
    own_s = FL.RUNS[run]["wallet"]; own = C.wid.get(own_s, -3); other_region = C.fra if own == C.ams else C.ams
    out = []; issues = collections.Counter()
    for (seg, w), X in L["W"].items():
        tr = X["arm"]["trig"]; mint = tr["mint"]
        rows = C.mint_rows(mint)
        key = C.key[rows]
        kt = np.searchsorted(key, FL.poskey(tr["slot"], tr["idx"], tr.get("j", 0)))
        trig_ok = kt < len(rows) and key[kt] == FL.poskey(tr["slot"], tr["idx"], tr.get("j", 0))
        if not trig_ok: issues["trigger_not_on_chain"] += 1
        tries = []; fee = 0
        fsig = X["fills"][0]["sig"] if X["fills"] else None
        for a in X["tries"]:
            Ld = a.get("land") or {}; res = Ld.get("res"); f = 0
            if res not in ("ok", None, "unseen"):
                f = Ld.get("fee") if Ld.get("fee") is not None else 5120
            elif a["sig"] in OF:
                f = OF[a["sig"]][2]; issues["unseen_priced_on_chain"] += 1
            fee += f
            tries.append(dict(slot=a["slot"], pos=tuple(a.get("pos") or (0, 0, 0)), fee=f, fill=(a["sig"] == fsig), t=a["t"], res=res))
        r = dict(run=run, seg=seg, w=w, mint=mint, spend=X["spend"], k=X["k"], trig=tr, t=tr["t"], en_slot=X["arm"]["en_slot"], quiet=X["arm"].get("quiet"),
                 disarm=X["disarm"], tries=tries, fail_fee=fee, filled=bool(X["fills"]), rows_n=len(rows), k_trig=int(kt) if trig_ok else None)
        if X["fills"]:
            f = X["fills"][0]; ex = X["exits"][0] if X["exits"] else {}; sl = X["sells"]
            r.update(fill=dict(slot=f["slot"], idx=f["idx"], t=f["t"], tokens=f["tokens"], sol_in=f["sol_in"], sig=f["sig"], fee=f["fee"], tip=f["tip"],
                               slots_after_trigger=f.get("slots_after_trigger")),
                     exit=dict(why=ex.get("why"), slot=ex.get("slot"), t=ex.get("t"), value=ex.get("value")),
                     sells=[dict(slot=s["slot"], idx=s["idx"], t=s["t"], sol=s["sol"], fee=s["fee"], sig=s["sig"]) for s in sl],
                     close=X["close"], pnl=X["pnl"], rb=X["rb"], net=X["pnl"] + X["rb"])
            # chain rows of our buy and our last sell
            bk = FL.poskey(f["slot"], f["idx"], 0)
            kb = [q for q in range(np.searchsorted(key, bk), len(rows)) if S[rows[q]] == f["slot"] and I[rows[q]] == f["idx"]]
            kb = [q for q in kb if U[rows[q]] == own and BUY[rows[q]] == 1]
            ks = []
            for s in sl:
                cand = [q for q in range(np.searchsorted(key, FL.poskey(s["slot"], s["idx"], 0)), len(rows)) if S[rows[q]] == s["slot"] and I[rows[q]] == s["idx"]]
                ks += [q for q in cand if U[rows[q]] == own and BUY[rows[q]] == 0]
            if not kb: issues["buy_not_on_chain"] += 1
            if sl and not ks: issues["sell_not_on_chain"] += 1
            r["k_buy"] = kb[0] if kb else None; r["k_sell"] = max(ks) if ks else None
            if kb and ks:
                a, b = kb[0], max(ks)
                between = rows[a + 1:b]
                oth = between[U[between] != own]
                r["n_between"] = int(len(oth)); r["flat"] = len(oth) == 0
                r["n_between_other_region"] = int((U[between] == other_region).sum())
                # MEASURED check: our buy's tokens and our sell's SOL on chain = the records
                if int(c["tok"][rows[a]]) != f["tokens"]: issues["buy_tokens_mismatch"] += 1
                if sum(s["sol"] for s in sl) != int(sum(c["sol"][rows[q]] for q in ks)): issues["sell_sol_mismatch"] += 1
            else:
                r["n_between"] = None; r["flat"] = None
            # the engine's view at its exit decision: other wallets' trades it had received, chain position after our buy
            tx = ex.get("t")
            seen = [z for z in X["tape"] if z["user"] != own_s and tx is not None and z["t"] <= tx and (z["slot"], z["idx"], z["j"]) > (f["slot"], f["idx"], 0)]
            r["eng_seen"] = len(seen); r["eng_flat"] = (ex.get("why") == "time-limit" and len(seen) == 0)
            r["tape"] = X["tape"]
        out.append(r)
    return dict(run=run, W=out, segs=L["segs"], fires=L["fires"], skips=L["skips"], issues=dict(issues))


def main():
    runs = sys.argv[1:]
    phases = sorted(set(p for r in runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); OF = ourfails(phases)
    print(f"chain rows {C.n:,}, phases {phases}", flush=True)
    for run in runs:
        B = build(run, C, OF)
        pickle.dump(B, open(f"{FL.D}/base_{run}.pkl", "wb"))
        W = B["W"]; F = [x for x in W if x["filled"]]
        print(f"{run}: windows {len(W)}, fills {len(F)}, flat known {sum(1 for x in F if x.get('flat') is not None)}, issues {B['issues']}", flush=True)


if __name__ == "__main__":
    main()
