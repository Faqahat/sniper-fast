"""Decode real PumpSwap Buy/SellEvents (emit_cpi self-CPI data) from recent mainnet swaps on a pool, and check the
SDK pricing formulas (incl. the buyback fee) against the program's own numbers: the event carries the pre-swap pool
reserves and the virtual quote reserve, so every fee and output can be recomputed exactly."""
import hashlib, sys
from solrpc import *

PUMP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
EVT_TAG = bytes.fromhex("e445a52e51cb9a1d")
D_BUY = hashlib.sha256(b"event:BuyEvent").digest()[:8]
D_SELL = hashlib.sha256(b"event:SellEvent").digest()[:8]

class R:
    def __init__(s, b): s.b, s.o = b, 0
    def u(s, n, signed=False): v = int.from_bytes(s.b[s.o:s.o + n], "little", signed=signed); s.o += n; return v
    def pk(s): v = b58e(s.b[s.o:s.o + 32]); s.o += 32; return v
    def st(s): n = s.u(4); v = s.b[s.o:s.o + n].decode(); s.o += n; return v

def buy(b):
    r = R(b); e = {}
    for f in ["timestamp", "base_amount_out", "max_quote_amount_in", "user_base_token_reserves", "user_quote_token_reserves",
              "pool_base_token_reserves", "pool_quote_token_reserves", "quote_amount_in", "lp_fee_basis_points", "lp_fee",
              "protocol_fee_basis_points", "protocol_fee", "quote_amount_in_with_lp_fee", "user_quote_amount_in"]:
        e[f] = r.u(8)
    for f in ["pool", "user", "uba", "uqa", "pfr", "pfra", "coin_creator"]: e[f] = r.pk()
    e["coin_creator_fee_basis_points"] = r.u(8); e["coin_creator_fee"] = r.u(8); e["track_volume"] = r.u(1)
    for f in ["total_unclaimed_tokens", "total_claimed_tokens", "current_sol_volume", "last_update_timestamp", "min_base_amount_out"]: e[f] = r.u(8)
    e["ix_name"] = r.st()
    for f in ["cashback_fee_basis_points", "cashback", "buyback_fee_basis_points", "buyback_fee"]: e[f] = r.u(8)
    e["virtual_quote_reserves"] = r.u(16, True); e["can_boost"] = r.u(1); e["base_supply"] = r.u(8)
    return e

def sell(b):
    r = R(b); e = {}
    for f in ["timestamp", "base_amount_in", "min_quote_amount_out", "user_base_token_reserves", "user_quote_token_reserves",
              "pool_base_token_reserves", "pool_quote_token_reserves", "quote_amount_out", "lp_fee_basis_points", "lp_fee",
              "protocol_fee_basis_points", "protocol_fee", "quote_amount_out_without_lp_fee", "user_quote_amount_out"]:
        e[f] = r.u(8)
    for f in ["pool", "user", "uba", "uqa", "pfr", "pfra", "coin_creator"]: e[f] = r.pk()
    e["coin_creator_fee_basis_points"] = r.u(8); e["coin_creator_fee"] = r.u(8)
    for f in ["cashback_fee_basis_points", "cashback", "buyback_fee_basis_points", "buyback_fee"]: e[f] = r.u(8)
    e["virtual_quote_reserves"] = r.u(16, True); e["can_boost"] = r.u(1); e["base_supply"] = r.u(8)
    return e

cdiv = lambda a, b: -(-a // b)
fee = lambda a, bps: cdiv(a * bps, 10_000)

def check_sell(e):
    B, Q, V, b = e["pool_base_token_reserves"], e["pool_quote_token_reserves"], e["virtual_quote_reserves"], e["base_amount_in"]
    q = (Q + V) * b // (B + b)
    lp, pr, cr = fee(q, e["lp_fee_basis_points"]), fee(q, e["protocol_fee_basis_points"]), fee(q, e["coin_creator_fee_basis_points"])
    bb, cb = fee(q, e["buyback_fee_basis_points"]), fee(q, e["cashback_fee_basis_points"])
    user = q - lp - pr - cr - bb - cb
    return [("quote_amount_out", q, e["quote_amount_out"]), ("lp_fee", lp, e["lp_fee"]), ("protocol_fee", pr, e["protocol_fee"]),
            ("coin_creator_fee", cr, e["coin_creator_fee"]), ("buyback_fee(ceil q*bps)", bb, e["buyback_fee"]),
            ("user_quote_amount_out = q-lp-pr-cr-bb-cb", user, e["user_quote_amount_out"])]

def check_buy(e):
    B, Q, V, base = e["pool_base_token_reserves"], e["pool_quote_token_reserves"], e["virtual_quote_reserves"], e["base_amount_out"]
    qin = cdiv((Q + V) * base, B - base)
    lp, pr, cr = fee(qin, e["lp_fee_basis_points"]), fee(qin, e["protocol_fee_basis_points"]), fee(qin, e["coin_creator_fee_basis_points"])
    bb, cb = fee(qin, e["buyback_fee_basis_points"]), fee(qin, e["cashback_fee_basis_points"])
    out = [("quote_amount_in = ceil((Q+V)*base/(B-base))", qin, e["quote_amount_in"]), ("lp_fee", lp, e["lp_fee"]), ("protocol_fee", pr, e["protocol_fee"]),
           ("coin_creator_fee", cr, e["coin_creator_fee"]), ("buyback_fee(ceil q*bps)", bb, e["buyback_fee"]),
           ("user_quote_amount_in = qin+lp+pr+cr+bb+cb", qin + lp + pr + cr + bb + cb, e["user_quote_amount_in"])]
    if e["ix_name"] == "buy_exact_quote_in":
        # SDK buyQuoteInput, with the buyback fee added to the fee total (spendable = max_quote_amount_in)
        x = e["max_quote_amount_in"]
        tot = e["lp_fee_basis_points"] + e["protocol_fee_basis_points"] + e["coin_creator_fee_basis_points"] + e["buyback_fee_basis_points"] + e["cashback_fee_basis_points"]
        eff = x * 10_000 // (10_000 + tot)
        tw = eff + sum(fee(eff, e[k]) for k in ["lp_fee_basis_points", "protocol_fee_basis_points", "coin_creator_fee_basis_points", "buyback_fee_basis_points", "cashback_fee_basis_points"])
        if tw > x: eff -= tw - x
        sdk_base = B * (eff - 1) // (Q + V + eff - 1)
        out.append(("buy_exact_quote_in base = B*(eff-1)/(Q+V+eff-1), eff incl. buyback bps", sdk_base, base))
        tot2 = tot - e["buyback_fee_basis_points"]
        eff2 = x * 10_000 // (10_000 + tot2)
        tw2 = eff2 + sum(fee(eff2, e[k]) for k in ["lp_fee_basis_points", "protocol_fee_basis_points", "coin_creator_fee_basis_points", "cashback_fee_basis_points"])
        if tw2 > x: eff2 -= tw2 - x
        out.append(("   (same, buyback NOT in the fee total)", B * (eff2 - 1) // (Q + V + eff2 - 1), base))
    return out

pool = sys.argv[1] if len(sys.argv) > 1 else "GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV"
sigs = rpc("getSignaturesForAddress", [pool, {"limit": int(sys.argv[2]) if len(sys.argv) > 2 else 25}])
n = {"buy": 0, "sell": 0, "mismatch": 0}
for s in sigs:
    if s["err"] is not None: continue
    tx = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if tx is None: continue
    msg = tx["transaction"]["message"]; la = tx["meta"].get("loadedAddresses") or {"writable": [], "readonly": []}; keys = msg["accountKeys"] + la["writable"] + la["readonly"]
    for inner in tx["meta"]["innerInstructions"] or []:
        for ix in inner["instructions"]:
            if keys[ix["programIdIndex"]] != PUMP: continue
            d = b58d(ix["data"])
            if d[:8] != EVT_TAG: continue
            if d[8:16] == D_BUY: e = buy(d[16:]); rows = check_buy(e); kind = "buy"
            elif d[8:16] == D_SELL: e = sell(d[16:]); rows = check_sell(e); kind = "sell"
            else: continue
            if e["pool"] != pool: continue
            n[kind] += 1
            bad = [r for r in rows if r[1] != r[2] and not r[0].startswith("   ")]
            if bad: n["mismatch"] += 1
            print(f"{kind:4} {e.get('ix_name', 'sell'):18} slot {tx['slot']} bps lp/pr/cr/bb/cb = {e['lp_fee_basis_points']}/{e['protocol_fee_basis_points']}/{e['coin_creator_fee_basis_points']}/{e['buyback_fee_basis_points']}/{e['cashback_fee_basis_points']} V={e['virtual_quote_reserves']}")
            for name, mine, theirs in rows:
                print(f"     {'ok ' if mine == theirs else 'DIFF'} {name}: formula {mine} event {theirs}")
print(n)
