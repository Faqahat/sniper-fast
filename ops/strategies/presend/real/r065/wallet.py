#!/usr/bin/env python3
"""REPLAY_065: wallet-level reconciliation per engine segment (MEASURED: start balances from the logs, the end balance read on chain
10-27 ~06:40 PKT = 4.633077414 SOL, last wallet tx 06:09:15 PKT), and the same items at another size (INFERRED: only the trades'
P&L changes; failed-try fees, rent back and close fees are as live).
  pre-send : realized (engine records) + token-account rent back (ata_close delta) - failed-try fees (chain: every landed failed try,
             including the ones the engine logged as unseen but the recording shows on chain)
  regular  : realized (log REALIZED lines) - failed-buy fees (chain: the landed failed variant's fee)"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core

END_BAL = 4.633077414


def items(D, PS, RG, RF):
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    me = next(iter(core.OURS))
    ours_fail = {x[2]: x for T in D.tape.values() for x in T["fails"] if x[4] == me}
    for run, X in D.live.items():
        lands = X["land"]
        for sig, a in X["att"].items():
            L = lands.get(sig) or {}
            seg = a["seg"]
            if L.get("res") in ("ok",): continue
            if L.get("res") not in (None, "unseen"):
                out[(run, seg)]["ps_fail_fee"] += (L.get("fee") if L.get("fee") is not None else 5120) / 1e9
                out[(run, seg)]["ps_fail_n"] += 1
            elif sig in ours_fail:
                out[(run, seg)]["ps_fail_fee"] += (ours_fail[sig][7] or 0) / 1e9
                out[(run, seg)]["ps_fail_n"] += 1; out[(run, seg)]["ps_unseen_landed"] += 1
        for r in X.get("ata_close", []):
            out[(run, r["seg"])]["ps_rent_back"] += (r.get("delta") or 0) / 1e9
            out[(run, r["seg"])]["ps_closes"] += 1
        for (seg, w), W in X["ps"].items():
            if W["realized"]: out[(run, seg)]["ps_realized"] += W["realized"]["pnl"] / 1e9
    for p in RG:
        out[(p.run, p.seg)]["reg_realized"] += p.realized / 1e9
    for p in RF:
        for x in p.fails:
            out[(p.run, p.seg)]["reg_fail_fee"] += (x[7] or 0) / 1e9
        out[(p.run, p.seg)]["reg_fail_n"] += 1
    return out


def balances(D):
    seq = []
    for run in ("r24", "r25"):
        for seg, b in D.live[run]["start_bal"]: seq.append(((run, seg), b))
    bal = {}
    for k, (key, b) in enumerate(seq):
        nxt = seq[k + 1][1] if k + 1 < len(seq) else END_BAL
        bal[key] = (b, nxt)
    return bal


if __name__ == "__main__":
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    it = items(D, PS, RG, RF); bal = balances(D)
    rows = {}
    for key in sorted(bal):
        a, b = bal[key]; x = it[key]
        comp = x["ps_realized"] + x["ps_rent_back"] - x["ps_fail_fee"] + x["reg_realized"] - x["reg_fail_fee"]
        rows["%s:%d" % key] = dict(start=a, end=b, change=b - a, comp=comp, resid=(b - a) - comp, **{k: v for k, v in x.items()})
        print(key, "wallet %+.6f | components %+.6f | residual %+.6f |" % (b - a, comp, (b - a) - comp), {k: round(v, 6) for k, v in x.items()})
    json.dump(rows, open(f"{core.BASE}/wallet.json", "w"), indent=1)
