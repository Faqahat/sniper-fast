#!/usr/bin/env python3
# ON-CHAIN TRUTH per wallet from out/chain_<w8>.json (read-only): tx types, routers/programs, same-tx round trips, other venues,
# flash-loan programs, fee payers, tips, priority fees, PnL = native SOL + WSOL change, per token and per PKT hour, deposits and
# withdrawals (non-trade SOL moves) with counterparties, token moves without a trade (transfers between own wallets?).
import os, sys, json, collections, statistics, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
KNOWN = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "PumpSwap", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "RaydiumV4",
         "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "RaydiumCPMM", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "RaydiumCLMM",
         "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "LaunchLab", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "MeteoraDLMM",
         "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "MeteoraDAMM", "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "MeteoraDAMMv2",
         "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "MeteoraDBC", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
         "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "OrcaWhirlpool", "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FzaE6Hj4u": "MarginFi(flash)",
         "KLend2g3cP87fffoy8q1mQqGKjrxjC8boSyAYavgmjD": "Kamino(flash)", "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo": "Solend(flash)",
         "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe": "SolFi", "ZERor4xhbUycZ6gb9ntrhqscUcZmAbQDjEAtCf4hbZY": "ZeroFi",
         "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump.fun", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ": "pump-fee",
         "ComputeBudget111111111111111111111111111111": "ComputeBudget", "11111111111111111111111111111111": "System",
         "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token2022",
         "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ATA", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
         "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo": "MemoV1", "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": "Metaplex",
         "SysvarRent111111111111111111111111111111111": "Rent", "AddressLookupTab1e1111111111111111111111111": "ALT"}
VENUES = {"PumpSwap", "RaydiumV4", "RaydiumCPMM", "RaydiumCLMM", "LaunchLab", "MeteoraDLMM", "MeteoraDAMM", "MeteoraDAMMv2", "MeteoraDBC", "Jupiter", "OrcaWhirlpool", "SolFi", "ZeroFi"}
FLASH = {"MarginFi(flash)", "Kamino(flash)", "Solend(flash)"}
def nm(p): return KNOWN.get(p, p[:8])
L = lib3.load_launches()
T, _ = lib3.load_tapes()
POS = json.load(open(os.path.join(lib3.HERE, "out/pos3.json")))
TAPEPNL = {(p["w"], p["m"]): p for p in POS if not p.get("nobuy")}
out = {}
for w8, W in lib3.W3.items():
    R = json.load(open(os.path.join(lib3.HERE, f"out/chain_{w8}.json")))
    o = dict(n_tx=len(R))
    # USDC -> SOL: market price per PKT hour from the wallet's own USDC trades: buy-implied (USDC paid per SOL into the curve incl.
    # pump fee) is above market (router fee, swap cost), sell-implied below; market ~ geometric mean of the two hourly medians
    bi = collections.defaultdict(list); si = collections.defaultdict(list)
    for r in R:
        if r["ok"] and r["du"] and len(r["wev"]) == 1 and r["wev"][0]["sol"] > 1e6:
            e = r["wev"][0]; h = r["bt"] // 3600
            if e["buy"] and r["du"] < 0: bi[h].append(-r["du"] / 1e6 / (e["sol"] * 1.0125 / 1e9))
            elif not e["buy"] and r["du"] > 0: si[h].append(r["du"] / 1e6 / (e["sol"] * 0.9875 / 1e9))
    allb = [x for v in bi.values() for x in v]; alls = [x for v in si.values() for x in v]
    PX = {}
    if allb and alls:
        gb, gs = statistics.median(allb), statistics.median(alls)
        for h in set(bi) | set(si):
            b = statistics.median(bi[h]) if bi.get(h) else gb; s_ = statistics.median(si[h]) if si.get(h) else gs
            PX[h] = (b * s_) ** 0.5
        o["usdc_price"] = dict(buy_implied_med=gb, sell_implied_med=gs, market_est=(gb * gs) ** 0.5, round_trip_cost_pct=(gb / gs - 1) * 100)
        hs = sorted(PX)
    def price(bt):
        if not PX: return None
        h = bt // 3600
        if h in PX: return PX[h]
        near = min(PX, key=lambda x: abs(x - h)); return PX[near]
    o["usdc_volume"] = sum(abs(r["du"]) for r in R if r["ok"]) / 1e6
    for r in R:
        r["dn_raw"], r["dw_raw"] = r["dn"], r["dw"]
        r["du_sol"] = (r["du"] / 1e6 / price(r["bt"])) if r["du"] and price(r["bt"]) else 0.0
        r["dn"] = r["dn"] + r["dw"] + int(r["du_sol"] * 1e9); r["dw"] = 0
    o["first"] = lib3.pkt(min(r["bt"] for r in R)); o["last"] = lib3.pkt(max(r["bt"] for r in R)); o["span_h"] = (max(r["bt"] for r in R) - min(r["bt"] for r in R)) / 3600
    cat = collections.Counter()
    for r in R:
        role = "payer" if r["payer"] == W else ("signer" if r["w_signer"] else "account-only")
        cat[(role, "ok" if r["ok"] else "failed", "trade" if r["wev"] else ("pump-other" if r["evs"] else "no-pump-event"))] += 1
    o["tx_types"] = {" / ".join(k): v for k, v in cat.most_common()}
    tr = [r for r in R if r["ok"] and r["wev"]]
    o["trade_txs"] = len(tr); o["buys"] = sum(1 for r in tr for e in r["wev"] if e["buy"]); o["sells"] = sum(1 for r in tr for e in r["wev"] if not e["buy"])
    o["same_tx_buy_and_sell"] = sum(1 for r in tr if any(e["buy"] for e in r["wev"]) and any(not e["buy"] for e in r["wev"]))
    o["multi_mint_txs"] = sum(1 for r in tr if len({e["mint"] for e in r["wev"]}) > 1)
    o["txs_with_other_users_pump_events"] = sum(1 for r in tr if any(e["user"] != W for e in r["evs"]))
    o["top_programs_trade"] = collections.Counter(" > ".join(nm(p) for p in r["top"] if nm(p) not in ("ComputeBudget",)) for r in tr).most_common(8)
    inv = collections.Counter(nm(p) for r in tr for p in r["inv"]); o["invoked_programs_trade"] = inv.most_common(20)
    o["venue_txs"] = {v: sum(1 for r in R if r["ok"] and any(nm(p) == v for p in r["inv"])) for v in VENUES}
    o["flash_txs"] = {v: sum(1 for r in R if any(nm(p) == v for p in r["inv"])) for v in FLASH}
    o["payers_trade"] = collections.Counter(r["payer"][:8] + ("(self)" if r["payer"] == W else "") for r in tr).most_common(5)
    o["signers_trade"] = collections.Counter(len(r["signers"]) for r in tr).most_common()
    o["other_signers_trade"] = collections.Counter(s[:8] for r in tr for s in r["signers"] if s != W).most_common(5)
    tipc = collections.Counter(); tipamt = collections.defaultdict(list)
    for r in tr:
        if not r["tips"]: tipc["none"] += 1
        for svc, lam, mine in r["tips"]: tipc[svc] += 1; tipamt[svc].append(lam / 1e9)
    o["tips"] = {k: (v, round(statistics.median(tipamt[k]), 6) if tipamt[k] else 0) for k, v in tipc.most_common()}
    o["prio_sol_median"] = statistics.median(r["prio"] for r in tr) if tr else None
    o["cu_price_median"] = statistics.median(r["cup"] for r in tr) if tr else None
    o["fee_lamports_median"] = statistics.median(r["fee"] for r in tr) if tr else None
    o["tx_cost_per_trade_median"] = statistics.median(r["fee"] / 1e9 + sum(l for _, l, m in r["tips"] if m) / 1e9 for r in tr) if tr else None
    fails = [r for r in R if not r["ok"] and (r["payer"] == W or r["w_signer"])]
    o["failed_own"] = len(fails); o["failed_own_cost"] = sum(r["fee"] for r in fails if r["payer"] == W) / 1e9
    o["failed_own_err"] = collections.Counter((r["err"] or "")[:60] for r in fails).most_common(4)
    # PnL: native + WSOL
    o["net_native_all"] = sum(r["dn_raw"] for r in R) / 1e9; o["net_wsol_all"] = sum(r["dw_raw"] for r in R) / 1e9; o["net_usdc_all_sol"] = sum(r["du_sol"] for r in R); o["net_usdc_all"] = sum(r["du"] for r in R) / 1e6
    o["net_trade_txs"] = sum(r["dn"] + r["dw"] for r in tr) / 1e9
    nt = [r for r in R if r["ok"] and not r["wev"]]
    o["net_nontrade_txs"] = sum(r["dn"] + r["dw"] for r in nt) / 1e9
    # deposits / withdrawals: non-trade txs that move >= 0.05 SOL
    flows = []
    for r in nt:
        d = (r["dn"] + r["dw"]) / 1e9
        if abs(d) >= 0.05:
            cp = [(k, v / 1e9) for k, v in r["cp"].items() if (v < 0) == (d > 0) and abs(v) > 0.01e9]
            flows.append(dict(t=lib3.pkt(r["bt"]), bt=r["bt"], sol=round(d, 4), payer=r["payer"][:8], top=[nm(p) for p in r["top"]], cp=[(k, round(v, 4)) for k, v in cp[:3]], sig=r["sig"]))
    o["flows"] = flows
    o["flow_in"] = sum(f["sol"] for f in flows if f["sol"] > 0); o["flow_out"] = sum(f["sol"] for f in flows if f["sol"] < 0)
    cpc = collections.defaultdict(float)
    for f in flows:
        for k, v in f["cp"]: cpc[k] += -v
    o["flow_counterparties"] = sorted(((k, round(v, 3)) for k, v in cpc.items()), key=lambda kv: -abs(kv[1]))[:10]
    # small incoming (non-trade) credits
    o["small_credits"] = dict(n=sum(1 for r in nt if 0 < r["dn"] + r["dw"] < 0.05e9), sol=sum(r["dn"] + r["dw"] for r in nt if 0 < r["dn"] + r["dw"] < 0.05e9) / 1e9,
                              payers=collections.Counter(r["payer"][:8] for r in nt if 0 < r["dn"] + r["dw"] < 0.05e9).most_common(4),
                              progs=collections.Counter(" > ".join(nm(p) for p in r["top"]) for r in nt if 0 < r["dn"] + r["dw"] < 0.05e9).most_common(4))
    # token moves without a pump trade of that mint (transfer in/out of own wallets?)
    tm = []
    for r in R:
        if not r["ok"]: continue
        trade_m = {e["mint"] for e in r["wev"]}
        for m, v in r["toks"].items():
            if m not in trade_m: tm.append(dict(t=lib3.pkt(r["bt"]), mint=m[:8], amt=v, top=[nm(p) for p in r["top"]][:4], inv=[nm(p) for p in r["inv"]][:6], payer=r["payer"][:8], sig=r["sig"]))
    o["token_moves_without_pump_trade"] = len(tm); o["token_moves_sample"] = tm[:12]
    o["token_moves_kinds"] = collections.Counter((("in" if x["amt"] > 0 else "out"), " > ".join(x["inv"][:4])) for x in tm).most_common(8)
    # per token on-chain PnL vs tape
    pt = collections.defaultdict(lambda: dict(net=0.0, nb=0, ns=0, bt=None, cost=0.0))
    for r in tr:
        ms_ = {e["mint"] for e in r["wev"]}
        m = next(iter(ms_))
        pt[m]["net"] += (r["dn"] + r["dw"]) / 1e9; pt[m]["nb"] += sum(1 for e in r["wev"] if e["buy"]); pt[m]["ns"] += sum(1 for e in r["wev"] if not e["buy"])
        pt[m]["cost"] += (r["fee"] + sum(l for _, l, mi in r["tips"] if mi)) / 1e9
        if pt[m]["bt"] is None: pt[m]["bt"] = r["bt"]
    o["tokens_traded"] = len(pt)
    closed = {m: v for m, v in pt.items() if v["ns"] > 0}
    wins = [v["net"] for v in closed.values() if v["net"] > 0]; loss = [v["net"] for v in closed.values() if v["net"] <= 0]
    o["closed_tokens"] = len(closed); o["win_rate"] = len(wins) / len(closed) if closed else None
    o["avg_win"] = statistics.mean(wins) if wins else None; o["avg_loss"] = statistics.mean(loss) if loss else None
    o["net_closed_tokens"] = sum(v["net"] for v in closed.values()); o["net_open_tokens_cost"] = sum(v["net"] for m, v in pt.items() if v["ns"] == 0)
    o["tokens_launched_in_runs"] = sum(1 for m in pt if m in L)
    # tx classes and plain transfers (funding / withdrawals)
    PLAIN = {"System", "ComputeBudget", "Memo", "MemoV1", "Token", "ATA"}
    def cls(r):
        if not r["ok"]: return "failed"
        if r["wev"]: return "pump-curve trade"
        if any(nm(p) in VENUES for p in r["inv"]): return "other-venue trade (AMM/Jupiter)"
        if r["toks"]: return "token move without trade (NFT/airdrop/transfer)"
        if (r["dn"] != 0) and all(nm(p) in PLAIN for p in r["inv"]): return "plain SOL/USDC transfer"
        return "other"
    cc = collections.defaultdict(lambda: [0, 0.0])
    for r in R:
        c_ = cls(r); cc[c_][0] += 1; cc[c_][1] += r["dn"] / 1e9
    o["classes"] = {k: (v[0], round(v[1], 3)) for k, v in sorted(cc.items(), key=lambda kv: -kv[1][0])}
    xf = collections.defaultdict(lambda: [0, 0.0, None, None])
    for r in R:
        if cls(r) != "plain SOL/USDC transfer": continue
        for a, b, lam, lvl in r["xfers"]:
            other = b if a == W else a; sgn = -1 if a == W else 1
            x = xf[other]; x[0] += 1; x[1] += sgn * lam / 1e9; x[2] = x[2] or lib3.pkt(r["bt"]); x[3] = lib3.pkt(r["bt"])
        if r["du"]:
            x = xf["USDC:" + r["payer"][:8]]; x[0] += 1; x[1] += r["du_sol"]; x[2] = x[2] or lib3.pkt(r["bt"]); x[3] = lib3.pkt(r["bt"])
    o["plain_transfers"] = sorted(([k, v[0], round(v[1], 3), v[2], v[3]] for k, v in xf.items()), key=lambda x: -abs(x[2]))[:15]
    # compare with tape PnL where both exist
    cmp_ = [(v["net"], TAPEPNL[(w8, m)]["pnl"], v["cost"]) for m, v in closed.items() if (w8, m) in TAPEPNL and not TAPEPNL[(w8, m)]["open"]]
    o["chain_vs_tape"] = dict(n=len(cmp_), chain=sum(a for a, b, c in cmp_), tape=sum(b for a, b, c in cmp_), txcost=sum(c for a, b, c in cmp_))
    # per day / per PKT hour (trade txs only, by tx time)
    hrs = collections.defaultdict(float); days = collections.defaultdict(float)
    for r in tr:
        hrs[time.gmtime(r["bt"] + 18000).tm_hour] += (r["dn"] + r["dw"]) / 1e9; days[time.strftime("%m-%d", time.gmtime(r["bt"] + 18000))] += (r["dn"] + r["dw"]) / 1e9
    o["pnl_by_pkt_hour"] = {h: round(v, 2) for h, v in sorted(hrs.items())}; o["pnl_by_pkt_day"] = {d: round(v, 2) for d, v in sorted(days.items())}
    acts = collections.Counter(time.strftime("%m-%d", time.gmtime(r["bt"] + 18000)) for r in tr if any(e["buy"] for e in r["wev"]))
    o["buy_txs_by_day"] = dict(sorted(acts.items()))
    # sizes
    bs = [e["sol"] / 1e9 for r in tr for e in r["wev"] if e["buy"]]
    o["buy_size"] = dict(p10=statistics.quantiles(bs, n=10)[0], med=statistics.median(bs), p90=statistics.quantiles(bs, n=10)[-1], mean=statistics.mean(bs)) if len(bs) > 10 else None
    o["quote"] = collections.Counter("USDC" if r["du"] else ("WSOL" if r["dw_raw"] != 0 else "native") for r in tr).most_common()
    out[w8] = o
    pt_ser = {m: v for m, v in pt.items()}
    json.dump(pt_ser, open(os.path.join(lib3.HERE, f"out/chain_tokens_{w8}.json"), "w"))
json.dump(out, open(os.path.join(lib3.HERE, "out/chain_summary.json"), "w"), indent=1, default=str)
for w8, o in out.items():
    print("\n########", w8)
    for k, v in o.items():
        if k in ("flows", "token_moves_sample"): continue
        print(f"  {k}: {v}")
    print("  flows (first 25):")
    for f in o["flows"][:25]: print("    ", f["t"], f["sol"], f["payer"], f["top"][:4], [(k[:8], v) for k, v in f["cp"]])
    print("  token moves sample:")
    for x in o["token_moves_sample"][:8]: print("    ", x)
