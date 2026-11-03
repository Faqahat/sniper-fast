#!/usr/bin/env python3
"""MULTIARM / min-age: anatomy of the LIVE re-arm fills by the dump's token age (MEASURED: live records + recorder tape).
Per live re-arm fill: the dump that armed it (age in slots since the create, seller, % of supply, SOL), our buy and sell (chain
positions from the records), realized P&L, and every OTHER trade on the token between our buy and our sell landing:
  sellers by role (first match): creator (the create's creator / signer / payer), dumper (the trigger dump's seller again),
  holder (a >= 6% holder at the window's check), create_slot (bought in the create's own slot: insider / bundle), early (first buy
  within create + 3 slots), other; their SOL out and % of supply; buys in the hold (followers) and their SOL.
  'buyback' = the dumper bought again in the same slot as its dump (a same-block buyback).
Aggregates per age bucket (<= 5, 6-10, 11-20, 21-40, > 40): fills, realized SOL, win share, mean SOL sold into our hold by role,
the share of fills where a creator / insider / holder / the dumper sold into our hold, and the role of the biggest seller on losers.
usage: ma11_young.py OUT.json RUN:X.pkl:TAB [RUN:X.pkl:TAB ...]"""
import sys, json, pickle, collections, datetime
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import ma_lib as M

BUCKETS = ((0, 5, "<=5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, 40, "21-40"), (41, 10 ** 9, ">40"))


def bucket(a):
    for lo, hi, n in BUCKETS:
        if lo <= a <= hi: return n
    return "?"


def pkt(t_ns): return (datetime.datetime.fromtimestamp(t_ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M:%S")


def one_run(run, xp, tab):
    X = pickle.load(open(xp, "rb")); tape = M.Tape(tab)
    rows = []
    for W in X["wins"]:
        if W["kind"] != "rearm" or not W["fills"] or not W["close"]: continue
        m = W["mint"]; d = W["trig"]
        c = tape.creates.get(m) or {}
        s0 = c.get("slot")
        t = tape.trades(m)
        if t is None or s0 is None: continue
        ids = tape.ids
        age = int(d["slot"] - s0)
        f = W["fills"][0]; cl = W["close"]
        buy_pos = (f["slot"], f["idx"])
        sl = cl.get("sell_land") or []
        if len(sl) < 2: continue
        sell_pos = (sl[0], sl[1])
        creator = {c.get("creator"), c.get("user"), c.get("payer")} - {None}
        dumper = d["wallet"]
        holders = {h["w"] for h in (W["rearm"].get("holders") or [])}
        # wallets by first buy slot
        first_buy = {}; cs_buy = set()
        for x in t:
            u = ids[int(x["user"])]
            if x["buy"] and u not in first_buy: first_buy[u] = int(x["slot"])
            if x["buy"] and int(x["slot"]) == s0 and u not in creator: cs_buy.add(u)
        buyback = any(ids[int(x["user"])] == dumper and x["buy"] and int(x["slot"]) == d["slot"] for x in t)
        def role(u):
            if u in creator: return "creator"
            if u == dumper: return "dumper"
            if u in holders: return "holder"
            if u in cs_buy: return "create_slot"
            if first_buy.get(u, 10 ** 12) <= s0 + 3: return "early"
            return "other"
        sells = collections.defaultdict(float); sells_pct = collections.defaultdict(float); n_sell = collections.Counter()
        buys_sol = 0.0; n_buy = 0; big = None
        for x in t:
            p = (int(x["slot"]), int(x["idx"]))
            if p <= buy_pos or p >= sell_pos: continue
            u = ids[int(x["user"])]
            if u in M.OURS: continue
            if x["buy"]: buys_sol += x["sol"] / 1e9; n_buy += 1; continue
            r = role(u)
            sells[r] += x["sol"] / 1e9; sells_pct[r] += x["tok"] / 1e13; n_sell[r] += 1
            if big is None or x["sol"] > big[1]: big = (r, int(x["sol"]), u)
        real = sum((x["pnl"] or 0) for x in W["real"]) / 1e9
        rows.append({"run": run, "mint": m, "t": pkt(d["t"]), "age": age, "bucket": bucket(age), "dump_pct": d.get("pct"), "dump_sol": d["sol"] / 1e9, "dumper": dumper[:8],
                     "dumper_role": "creator" if dumper in creator else ("create_slot" if dumper in cs_buy else ("early" if first_buy.get(dumper, 10 ** 12) <= s0 + 3 else "other")),
                     "buyback": buyback, "holders": len(holders), "exit": cl.get("exit_why"), "held_s": cl.get("held_s"), "realized": real,
                     "sells_sol": dict(sells), "sells_pct": dict(sells_pct), "n_sell": dict(n_sell), "buys_sol": buys_sol, "n_buy": n_buy,
                     "biggest_seller": None if big is None else {"role": big[0], "sol": big[1] / 1e9, "w": big[2][:8]}})
    return rows


def agg(rows):
    out = {}
    for lo, hi, n in BUCKETS + ((0, 10, "<=10 all"), (11, 10 ** 9, ">10 all")):
        R = [r for r in rows if lo <= r["age"] <= hi]
        if not R: continue
        roles = ("creator", "dumper", "holder", "create_slot", "early", "other")
        los = [r for r in R if r["realized"] < 0]
        out[n] = {"fills": len(R), "realized": round(sum(r["realized"] for r in R), 4), "mean_mSOL": round(1e3 * np.mean([r["realized"] for r in R]), 2),
                  "win_share": round(float(np.mean([r["realized"] > 0 for r in R])), 3),
                  "worst_mSOL": round(1e3 * min(r["realized"] for r in R), 1), "best_mSOL": round(1e3 * max(r["realized"] for r in R), 1),
                  "sold_into_hold_SOL_mean": {k: round(float(np.mean([r["sells_sol"].get(k, 0.0) for r in R])), 3) for k in roles},
                  "share_with_seller": {k: round(float(np.mean([r["sells_sol"].get(k, 0.0) > 0 for r in R])), 3) for k in roles},
                  "follower_buys_SOL_mean": round(float(np.mean([r["buys_sol"] for r in R])), 3),
                  "dumper_role": dict(collections.Counter(r["dumper_role"] for r in R)), "buyback_share": round(float(np.mean([r["buyback"] for r in R])), 3),
                  "losers_biggest_seller_role": dict(collections.Counter((r["biggest_seller"] or {}).get("role", "none") for r in los)),
                  "losers_realized": round(sum(r["realized"] for r in los), 4), "exit": dict(collections.Counter(r["exit"] for r in R))}
    return out


if __name__ == "__main__":
    outp = sys.argv[1]
    rows = []
    for spec in sys.argv[2:]:
        run, xp, tab = spec.split(":")
        rows += one_run(run, xp, tab)
    res = {"rows": rows, "all": agg(rows), "by_run": {r: agg([x for x in rows if x["run"] == r]) for r in sorted({x["run"] for x in rows})}}
    json.dump(res, open(outp, "w"), indent=1)
    for k, v in res["all"].items():
        print(k, {kk: vv for kk, vv in v.items() if kk in ("fills", "realized", "mean_mSOL", "win_share", "worst_mSOL", "share_with_seller", "sold_into_hold_SOL_mean", "dumper_role",
                                                           "buyback_share", "losers_biggest_seller_role", "follower_buys_SOL_mean")})
