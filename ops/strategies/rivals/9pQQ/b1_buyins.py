#!/usr/bin/env python3
"""9pQQ buy-ins and tx anatomy: reaction delay after the trade it reacted to (slots, block index gap, chain-clock ms with
block size = max landed pump-tx index seen in that slot + 1), position among same-slot buyers, price paid vs before the trigger,
fees / CU price / tips by path, failed txs and error codes, CloseAccount (rent refund) flows.  Read-only.  usage: b1_buyins.py"""
import pickle, collections, json, glob
import numpy as np
import tlib9 as L

SMS = 212.0
def slot_sizes(run):
    mx = collections.defaultdict(int)
    for fn in glob.glob(f"{L.TAPE}/{run}/*.npz"):
        a = np.load(fn)["a"]
        if not len(a): continue
        s = a[:, 0]; i = a[:, 1]
        o = np.lexsort((i, s)); s = s[o]; i = i[o]
        last = np.r_[s[1:] != s[:-1], True]
        for ss, ii in zip(s[last].tolist(), i[last].tolist()): mx[ss] = max(mx[ss], ii)
    return mx

if __name__ == "__main__":
    out = {}
    TIPN = {"astra4": "astralane", "Cw8CFy": "jito", "96gYZG": "jito", "DfXygS": "jito", "DttWaM": "jito", "3AVi9T": "jito",
            "HFqU5x": "jito", "ADaUMi": "jito", "ADuUkR": "jito"}
    for r in L.RUNS:
        own = L.own(r); T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok")]
        mx = slot_sizes(r)
        cc = lambda s, i: s * SMS + i / max(mx.get(s, 400) + 1, i + 1) * SMS
        d_ms = []; d_dip = []; first_after = 0; n_dip = 0; pos = []
        for x in T:
            if x.get("last_gap") is None: continue
            # chain-clock delay from the trade it reacted to
            ts = x["bs"] - x["last_gap"]
            # last trade's index: recover from last_ix when same slot, else unknown index -> use tape
            pass
        t = L.load_tape(r); wid = t.user_ix[L.W]
        for x in T:
            mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
            S = t.s[a0:a1]; I = t.i[a0:a1]; U = t.u[a0:a1]; TK = t.tok[a0:a1]; SL = t.sol[a0:a1]
            jb = int(np.searchsorted(S * 10000 + I, x["bs"] * 10000 + x["bi"]))
            j = jb - 1
            while j >= 0 and U[j] == wid: j -= 1
            if j < 0: continue
            d = cc(x["bs"], x["bi"]) - cc(S[j], I[j])
            d_ms.append(d)
            if (x.get("dump_sol") or 0) >= 0.5:
                n_dip += 1
                # the dump row: biggest other sell within 3 slots before
                k0 = int(np.searchsorted(S, x["bs"] - 3))
                cand = [k for k in range(k0, jb) if U[k] != wid and TK[k] < 0]
                if cand:
                    q = max(cand, key=lambda k: SL[k])
                    d_dip.append(cc(x["bs"], x["bi"]) - cc(S[q], I[q]))
                    # outside buys between the dump and its buy
                    nb = sum(1 for k in range(q + 1, jb) if U[k] != wid and TK[k] > 0)
                    pos.append(nb); first_after += nb == 0
        d_ms = np.array(d_ms); d_dip = np.array(d_dip)
        # fees and tips
        buys = [x for x in own if x["kind"] == "buy"]; sells = [x for x in own if x["kind"] == "sell"]; fails = [x for x in own if x["kind"] == "fail"]
        def tipsum(v):
            c = collections.Counter(); amt = collections.defaultdict(list)
            for x in v:
                for a, l in x["tips"]:
                    nm = TIPN.get(a[:6], a[:6]); c[nm] += 1; amt[nm].append(l)
            return {k: (c[k], int(np.median(amt[k]))) for k in c}
        errs = collections.Counter()
        for x in fails:
            e = json.loads(x["err"]) if x["err"] else None
            try: code = e["InstructionError"][1]; code = code.get("Custom", code) if isinstance(code, dict) else code
            except Exception: code = str(e)[:40]
            errs[(x["ixn"][-1] if x["ixn"] else "?", code)] += 1
        res = dict(
            delay_ms_p=np.percentile(d_ms, [10, 25, 50, 75, 90]).round(1).tolist(),
            same_slot=float(np.mean([x.get("last_gap") == 0 for x in T])),
            dip_delay_ms_p=np.percentile(d_dip, [10, 25, 50, 75, 90]).round(1).tolist() if len(d_dip) else None,
            dip_first_outside_buyer=first_after / max(1, len(pos)), dip_outside_buys_before_p=np.percentile(pos, [25, 50, 75, 90]).tolist() if pos else None,
            buy_fee_p50=int(np.median([x["fee"] for x in buys])), sell_fee_p50=int(np.median([x["fee"] for x in sells])),
            cup=collections.Counter(x["cup"] for x in buys + sells).most_common(3), cul_buy=collections.Counter(x["cul"] for x in buys).most_common(3),
            cul_sell=collections.Counter(x["cul"] for x in sells).most_common(3), tips_buy=tipsum(buys), tips_sell=tipsum(sells),
            n_buy=len(buys), n_sell=len(sells), n_fail=len(fails), fail_cost_sol=round(-sum(x["sol"] for x in fails) / 1e9, 4),
            errors=[(str(k), v) for k, v in errs.most_common(8)],
            closes=sum(1 for x in own if x["kind"] == "close"), close_accounts=sum(len(x["ixn"]) for x in own if x["kind"] == "close"),
            close_sol=round(sum(x["sol"] for x in own if x["kind"] == "close") / 1e9, 3),
            created_accounts=sum(1 for x in buys if "InitializeAccount3" in x["ixn"]),
            buy_ix=collections.Counter(tuple(x["ixn"]) for x in buys).most_common(3), sell_ix=collections.Counter(tuple(x["ixn"]) for x in sells).most_common(3),
            nsig=collections.Counter(x["nsig"] for x in buys).most_common(2),
            per_tx_cost_buy_lamports=int(np.median([x["fee"] + sum(l for _, l in x["tips"]) for x in buys])),
            per_tx_cost_sell_lamports=int(np.median([x["fee"] + sum(l for _, l in x["tips"]) for x in sells])),
        )
        out[L.DAY[r]] = res
        print(L.DAY[r], json.dumps(res, default=str))
    json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/buyins.json", "w"), indent=1, default=str)
