"""Check the PumpSwap pricing model of DESIGN.md §2.1 against the program's own BuyEvent/SellEvent on recent mainnet
swaps (read-only RPC, cached). Each event carries the PRE-swap pool reserves, the virtual quote reserve and every fee,
so the model is checked field by field. Usage: python3 pump_events_check.py [n_signatures] [before_signature]"""
import sys
exec(open("pump_events.py").read().split("pool = sys.argv[1]")[0])

N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
params = {"limit": min(N, 1000)}
if len(sys.argv) > 2: params["before"] = sys.argv[2]
sigs = rpc("getSignaturesForAddress", [PUMP, params])
stats, edge = {}, []
def rec(k, ok):
    stats.setdefault(k, [0, 0]); stats[k][0 if ok else 1] += 1
for s in sigs:
    if s["err"] is not None: continue
    tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if tx is None: continue
    msg = tx["transaction"]["message"]; la = tx["meta"].get("loadedAddresses") or {"writable": [], "readonly": []}
    keys = msg["accountKeys"] + la["writable"] + la["readonly"]
    for inner in tx["meta"]["innerInstructions"] or []:
        for ix in inner["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP: continue
            d = b58d(ix["data"])
            if d[:8] != EVT_TAG or d[8:16] not in (D_BUY, D_SELL): continue
            sell_ = d[8:16] == D_SELL
            e = sell(d[16:]) if sell_ else buy(d[16:])
            B, Q, V = e["pool_base_token_reserves"], e["pool_quote_token_reserves"], e["virtual_quote_reserves"]
            bps = [e["lp_fee_basis_points"], e["protocol_fee_basis_points"], e["coin_creator_fee_basis_points"]]
            cb = e["cashback_fee_basis_points"]
            tag = f"{'cashback ' if cb else ''}{'virtual ' if V else ''}"
            rec("buyback_fee = floor(protocol_fee * buyback_bps / 1e4) (carve-out, not a user fee)", e["protocol_fee"] * e["buyback_fee_basis_points"] // 10_000 == e["buyback_fee"])
            if sell_:
                b = e["base_amount_in"]; q = (Q + V) * b // (B + b)
                lp, pr, cr = (fee(q, x) for x in bps); cbf = fee(q, cb)
                rec(f"sell {tag}q = floor((Q+V)*b/(B+b))", q == e["quote_amount_out"])
                rec(f"sell {tag}lp,pr,cr = ceil(q*bps/1e4) each", (lp, pr, cr) == (e["lp_fee"], e["protocol_fee"], e["coin_creator_fee"]))
                rec(f"sell {tag}cashback = ceil(q*cb_bps/1e4)", cbf == e["cashback"])
                rec(f"sell {tag}user_out = q - lp - pr - cr - cashback", q - lp - pr - cr - cbf == e["user_quote_amount_out"])
            else:
                base = e["base_amount_out"]
                if e["ix_name"] == "buy":
                    qin = cdiv((Q + V) * base, B - base)
                    lp, pr, cr = (fee(qin, x) for x in bps); cbf = fee(qin, cb)
                    rec(f"buy {tag}quote_in = ceil((Q+V)*base/(B-base))", qin == e["quote_amount_in"])
                    rec(f"buy {tag}lp,pr,cr = ceil(quote_in*bps/1e4)", (lp, pr, cr) == (e["lp_fee"], e["protocol_fee"], e["coin_creator_fee"]))
                    rec(f"buy {tag}user_in = quote_in + lp + pr + cr + cashback", qin + lp + pr + cr + cbf == e["user_quote_amount_in"])
                else:
                    x = e["max_quote_amount_in"]; F = sum(bps) + cb
                    eff0 = x * 10_000 // (10_000 + F)
                    f0 = sum(fee(eff0, y) for y in bps) + fee(eff0, cb)
                    eff = eff0 - max(0, eff0 + f0 - x)
                    feff = sum(fee(eff, y) for y in bps) + fee(eff, cb)
                    rec(f"bxqi {tag}eff (SDK adjust) == event user_quote_amount_in", eff == e["user_quote_amount_in"])
                    rec(f"bxqi {tag}base = floor(B*(eff-1)/(Q+V+eff-1))", B * (eff - 1) // (Q + V + eff - 1) == base)
                    rec(f"bxqi {tag}fees = ceil(eff*bps/1e4)", tuple(fee(eff, y) for y in bps) == (e["lp_fee"], e["protocol_fee"], e["coin_creator_fee"]))
                    rec(f"bxqi {tag}eff + fees(eff) == spendable", eff + feff == x)
                    if eff + feff != x: edge.append((s["signature"], x, eff, feff))
print(f"{len(sigs)} signatures from {sigs[0]['signature'][:12]}.. to {sigs[-1]['signature'][:12]}..")
for k, (a, b) in sorted(stats.items()): print(f"{a:4} ok {b:4} diff  {k}")
print("buy_exact_quote_in with eff+fees(eff) != spendable:", edge[:10])
