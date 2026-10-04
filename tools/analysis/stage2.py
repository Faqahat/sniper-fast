#!/usr/bin/env python3
"""Long run, stage 2: every arbitrage bot's profile across all segments (joined.jsonl.gz from stage 1).
A signer is a BOT when its successful transactions are clean round trips (no token left over, SOL/WSOL change only):
at least 3 clean wins and >= 80% of its results clean; or it sprays (>= 50 transactions, >= 50% on a durable nonce).
Per bot: volume, wins, profit, fee rule (priority vs profit on wins), senders (tips), nonce, reaction time on the PoH
clock after its trigger, spray (copies per trigger), errors, programs, tables, venues, slots (for the leader stage).
Operators: bots grouped by top-level program. Writes bots.json, operators.json, wins.jsonl.gz (every clean win).
usage: stage2.py <segment dir> [...]"""
import json, sys, gzip, collections, math

q = lambda v, p: (sorted(v)[min(len(v) - 1, int(len(v) * p))] if v else None)
S = collections.defaultdict(lambda: {"n": 0, "res": 0, "ok": 0, "clean": 0, "wins": 0, "profit": 0, "nonce": 0, "tipless": 0, "v": collections.Counter(),
    "tips": collections.Counter(), "tip_amt": collections.defaultdict(list), "prog": collections.Counter(), "alts": collections.Counter(),
    "venues": collections.Counter(), "err": collections.Counter(), "win_ms": [], "fail_ms": [], "win_prio": [], "win_profit": [], "fail_prio": [],
    "win_cu_price": [], "fail_cu_price": [], "cu_limit": [], "per_trig": collections.Counter(), "win_slots": [], "fail_slots": [], "feed": collections.Counter(),
    "n_sig": collections.Counter(), "disc": collections.Counter(), "same_slot_wins": 0, "win_tip_share": [], "first_t": None, "last_t": None, "pools": collections.Counter()})
# a transaction whose top-level programs are one venue (plus token housekeeping) is a plain swap or a fee claim, not
# an arbitrage (e.g. token creators collecting PumpSwap / Pump.fun creator fees: SOL in, no token out)
VENUE = {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
         "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
         "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
         "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe",
         "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
NEUTRAL = {"ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
           "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
def not_arb(progs):
    p = {x for x in progs if x not in NEUTRAL}
    # PumpSwap + Pump.fun at top level together is the creator-fee claim (a token trades on one or the other, never both)
    # and a venue plus Jupiter at top level is a position exit swapped to SOL (DLMM remove liquidity + Jupiter): Jupiter is
    # not a second venue
    return bool(p) and (p <= {"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}
                        or (p <= VENUE and len(p - {"JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}) < 2))
wins_out = gzip.open("wins.jsonl.gz", "wt")
total = 0
for seg in sys.argv[1:]:
    for l in gzip.open(f"{seg.rstrip('/')}/joined.jsonl.gz", "rt"):
        j = json.loads(l); total += 1
        if not_arb(j.get("progs") or []): continue
        s = S[j["signer"]]
        s["n"] += 1
        s["first_t"] = min(s["first_t"] or j["t"], j["t"]); s["last_t"] = max(s["last_t"] or 0, j["t"])
        prio = j["v1_fee"] if j["v1_fee"] is not None else ((j["cu_price"] or 0) * (j["cu_limit"] or 200_000) // 1_000_000)
        tips = sum(a for _, a in j["tips"] if not str(_).startswith("?"))
        if j["nonce"]: s["nonce"] += 1
        if not any(not str(n).startswith("?") for n, _ in j["tips"]): s["tipless"] += 1
        for n, a in j["tips"]:
            if not str(n).startswith("?"): s["tips"][n] += 1; s["tip_amt"][n].append(a)
        s["v"][j["v"]] += 1; s["n_sig"][j["n_sig"]] += 1; s["feed"][j["feed"]] += 1
        main = next((x for x in (j.get("progs") or []) if x not in NEUTRAL), None)
        if main: s["prog"][main] += 1
        for a in j["alts"][:3]: s["alts"][a] += 1
        for v in j["venues"]: s["venues"][v] += 1
        for p in j["pools"]: s["pools"][p] += 1
        s["disc"][j["disc"][:16]] += 1
        if j["cu_limit"]: s["cu_limit"].append(j["cu_limit"])
        if j["trig"]: s["per_trig"][j["trig"]["sig"]] += 1
        if j["ok"] is not None:
            s["res"] += 1
            if j["ok"]:
                s["ok"] += 1
                clean = j["profit"] is not None and not j["tok_other"]
                if clean: s["clean"] += 1
                if clean and j["profit"] > 0:
                    s["wins"] += 1; s["profit"] += j["profit"]
                    s["win_prio"].append(prio); s["win_profit"].append(j["profit"] + prio + tips)   # gross: before priority and tips
                    s["win_cu_price"].append(j["cu_price"] or 0); s["win_slots"].append(j["slot"])
                    if tips: s["win_tip_share"].append(tips / max(1, j["profit"] + prio + tips))
                    if j["trig"]:
                        s["win_ms"].append(j["trig"]["ms"])
                        if j["poh"] and j["trig"]["ms"] < 400: s["same_slot_wins"] += 1
                    wins_out.write(json.dumps({k: j[k] for k in ("sig", "slot", "signer", "prog", "profit", "cu_price", "cu_limit", "v1_fee", "tips", "nonce",
                        "trig", "poh", "idx", "feed", "venues", "pools", "arr", "v")} | {"prio": prio}) + "\n")
            else:
                s["err"][(j["err"] or "?") + " " + (j["why_err"] or "")[:70]] += 1
                s["fail_prio"].append(prio); s["fail_cu_price"].append(j["cu_price"] or 0); s["fail_slots"].append(j["slot"])
                if j["trig"]: s["fail_ms"].append(j["trig"]["ms"])
wins_out.close()

def slope(xs, ys):
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pts) < 5: return None
    mx = sum(p[0] for p in pts) / len(pts); my = sum(p[1] for p in pts) / len(pts)
    vx = sum((p[0] - mx) ** 2 for p in pts)
    return round(sum((p[0] - mx) * (p[1] - my) for p in pts) / vx, 2) if vx else None

bots = {}
for k, s in S.items():
    # clean round trips make up most of its successes (some bots leave token dust on a few: still bots)
    is_winner = s["wins"] >= 3 and s["ok"] and (s["clean"] / s["ok"] >= 0.8 or s["wins"] / s["ok"] >= 0.3)
    is_sprayer = s["n"] >= 50 and s["nonce"] / s["n"] >= 0.5
    if not (is_winner or is_sprayer): continue
    # arbitrage bots run their own program; a wallet whose main program is a venue itself is a trader or LP
    main = next(iter(s["prog"].most_common(1)), (None,))[0]
    if main in VENUE: continue
    trig_counts = list(s["per_trig"].values())
    share = [p / g for p, g in zip(s["win_prio"], s["win_profit"]) if g > 0]
    bots[k] = {
        "signer": k, "kind": "winner" if is_winner else "sprayer", "n": s["n"], "with_result": s["res"], "ok": s["ok"], "clean": s["clean"], "wins": s["wins"],
        "profit_sol": round(s["profit"] / 1e9, 4), "win_rate": round(s["wins"] / s["res"], 3) if s["res"] else None,
        "nonce_pct": round(100 * s["nonce"] / s["n"]), "tipless_pct": round(100 * s["tipless"] / s["n"]),
        "senders": dict(s["tips"].most_common(6)), "tip_median": {n: q(v, .5) for n, v in s["tip_amt"].items()},
        "versions": dict(s["v"]), "n_sig": dict(s["n_sig"]), "programs": dict(s["prog"].most_common(3)), "alts": dict(s["alts"].most_common(3)),
        "venues": dict(s["venues"].most_common(6)), "pools_n": len(s["pools"]), "top_pools": dict(s["pools"].most_common(5)),
        "disc": dict(s["disc"].most_common(3)), "cu_limit_p50": q(s["cu_limit"], .5),
        "win_ms_p10_p50_p90": [q(s["win_ms"], .1), q(s["win_ms"], .5), q(s["win_ms"], .9)], "win_ms_n": len(s["win_ms"]),
        "fail_ms_p50": q(s["fail_ms"], .5), "same_slot_wins": s["same_slot_wins"],
        "win_cu_price_p50": q(s["win_cu_price"], .5), "fail_cu_price_p50": q(s["fail_cu_price"], .5),
        "win_prio_p50": q(s["win_prio"], .5), "fail_prio_p50": q(s["fail_prio"], .5),
        "prio_share_of_gross_p10_p50_p90": [round(x, 3) if x is not None else None for x in (q(share, .1), q(share, .5), q(share, .9))],
        "prio_vs_gross_slope": slope(s["win_profit"], [max(1, p) for p in s["win_prio"]]),
        "tip_share_p50": q(s["win_tip_share"], .5),
        "copies_per_trigger_p50_p90": [q(trig_counts, .5), q(trig_counts, .9)], "triggers": len(trig_counts),
        "errors": dict(s["err"].most_common(5)), "first_feed": dict(s["feed"].most_common(3)),
        "active_min": round((s["last_t"] - s["first_t"]) / 6e10, 1),
        "win_slots": s["win_slots"], "fail_slots": s["fail_slots"][:5000],
    }
ops = collections.defaultdict(lambda: {"signers": [], "wins": 0, "n": 0, "profit_sol": 0.0})
for b in bots.values():
    p = next(iter(b["programs"]), None)
    o = ops[p]; o["signers"].append(b["signer"]); o["wins"] += b["wins"]; o["n"] += b["n"]; o["profit_sol"] += b["profit_sol"]
json.dump(bots, open("bots.json", "w"))
json.dump({k: v for k, v in sorted(ops.items(), key=lambda x: -x[1]["profit_sol"])}, open("operators.json", "w"), indent=1)
W = sorted(bots.values(), key=lambda b: -b["profit_sol"])
print(f"{total} arbitrage-like transactions; {len(bots)} bots ({sum(1 for b in W if b['kind']=='winner')} winners); {len(ops)} programs")
print("TOP BOTS: signer | wins/res | profit SOL | win ms p10/p50/p90 | prio share p50 | cu_price win/fail | nonce% | tipless% | senders | copies/trig")
for b in W[:25]:
    print(f"  {b['signer'][:8]} | {b['wins']}/{b['with_result']} | {b['profit_sol']} | {b['win_ms_p10_p50_p90']} | {b['prio_share_of_gross_p10_p50_p90'][1]} | {b['win_cu_price_p50']}/{b['fail_cu_price_p50']} | {b['nonce_pct']} | {b['tipless_pct']} | {b['senders']} | {b['copies_per_trigger_p50_p90']}")
