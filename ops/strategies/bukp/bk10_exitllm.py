#!/usr/bin/env python3
# Refinement round (exits): cards of R2 trips (its entries re-timed to 35 ms, 0.6 SOL) where ITS exit beat our best causal
# exit rule by a lot, and where it did worse; the path while held in 10-slot buckets (price vs entry, other-wallet buy/sell
# SOL, # of ID'd bots selling) and the moment it sold. Haiku proposes causal exit rules in an extended DSL that bk10 then
# replays on R2 / R3 / R1. Sync calls (small); spend kind "bukp_exit".
import sys, json, zlib, random
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import p4_eval as E
import bk8_replica as B8
import bk4_cards as B4
OUT = "/home/moiz/sniper-data/strategies/bukp"; WK = f"{OUT}/llm"
SYS = """You reverse-engineer one pump.fun bot's EXIT rule. Each card is one of its trades: the token state at entry, then the
price path while it held (10-slot buckets; 1 slot = 0.212 s): price vs its entry, other wallets' buy and sell SOL, how many
known bots sold, then the bucket where it sold and the price it got, compared with what a simple 'timer/take-profit' exit
got. MEASURED: it never sells within ~15 slots; 24% of trades end at a fixed ~1,417-slot timeout; its early exits are fast
(same slot as another wallet's trade, often 3-60 transactions later); after its exit the price does NOT fall more than its
own ~3.5% sell impact (it is not front-running sell waves); a learned model and simple rules (TP/SL, sell on any sell >= 0.5,
sell into a buy burst, minimum hold) all fail to match its exits' profit.
Find what its exit reacts to. Use only information available at that moment (no future). Reply with ONLY JSON:
{"exit_rules": [up to 3 objects {"name": str, "min_hold": slots, "max_hold": slots, "tp": mult|null, "sl": mult|null,
  "trail": [arm_mult, drop_frac]|null, "when_any": [[[feature, op, value], ...], ...] (sell when ALL conditions of ANY group
  hold at a trade; features: mult (price/entry), peak (max mult so far), dd_peak (1 - mult/peak), held (slots), sell_since,
  buy_since (other wallets' SOL since entry), bsol3, ssol3, nb3, ns3, maxs3, maxb3, net3, net10, ret1, ret3, ret10, curve,
  nbot_hold, fam_hold, bot_s10 (# ID'd-bot sells in last 10 slots), side (1 buy / 0 sell of the trade), sol, wt), "why": str}],
 "notes": [short strings]}"""
def card(d, t, e, path_rows, own_exit_idx, own_pnl, rule_pnl):
    k0 = t["k0"]; FI = d["FI"]
    L = [f"TRADE {t['mint'][:6]}: entry state curve={d['F'][k0, FI['curve']]:.1f} age={d['F'][k0, FI['age']]:.0f} ath_r={d['F'][k0, FI['ath_r']]:.2f} nbot_hold={d['F'][k0, FI['nbot_hold']]:.0f} fam_hold={d['F'][k0, FI['fam_hold']]:.0f} ret10={d['F'][k0, FI['ret10']]:.1f}"]
    rows = path_rows; s0 = e["s_land"]
    b = {}
    for n, r in enumerate(rows):
        m = r[0]; bk = (int(d["s"][m]) - s0) // 10
        x = b.setdefault(bk, dict(mult=r[1], buy=0.0, sell=0.0, botsell=0, sold=False))
        x["mult"] = r[1]
        if d["buy"][m]: x["buy"] += d["sol"][m] / 1e9
        else:
            x["sell"] += d["sol"][m] / 1e9
            if d["bid"][m]: x["botsell"] += 1
        if n == own_exit_idx: x["sold"] = True
        if n >= own_exit_idx + 3: break
    for bk in sorted(b)[:40]:
        x = b[bk]
        L.append(f"  {bk * 10:>5}-{bk * 10 + 9}: price {x['mult']:.3f}x buys {x['buy']:.2f} sells {x['sell']:.2f} botsells {x['botsell']}" + ("   <== IT SOLD HERE" if x["sold"] else ""))
    L.append(f"  its result {own_pnl:+.4f} SOL; simple timer/TP rule result {rule_pnl:+.4f} SOL")
    return "\n".join(L)
if __name__ == "__main__":
    E.load(["R2"]); d = E.DAYS["R2"]
    T = [t for t in json.load(open(f"{OUT}/trips_R2.json")) if t["closed"] and t["sells"] and t["buys"][0]["sol"] < 1.0]
    rng = random.Random(3); rng.shuffle(T)
    cards = []
    for t in T[:1500]:
        e = B8.entry(d, t, 35, "0.6")
        if not e or e["fail"] or not e["path"]: continue
        ks = t["sells"][-1]["k"]; own = None
        for n, m in enumerate(e["path"]):
            if m < ks: own = n
            else: break
        if own is None: continue
        got = e["Vs"][own] * e["qt"] / (e["Ts"][own] + e["qt"]) * (1 - e["fr"]) / 1e9; own_pnl = got - e["B"] - B8.FIX
        # simple rule: tp1.1 / sl0.93 / 283 slots
        nn = len(e["path"]) - 1
        for n, r in enumerate(e["rows"]):
            if r[1] >= 1.1 or r[1] <= 0.93 or r[3] > 283: nn = n; break
        got2 = e["Vs"][nn] * e["qt"] / (e["Ts"][nn] + e["qt"]) * (1 - e["fr"]) / 1e9; rule_pnl = got2 - e["B"] - B8.FIX
        cards.append((own_pnl - rule_pnl, card(d, t, e, e["rows"], own, own_pnl, rule_pnl)))
    cards.sort(key=lambda x: -x[0])
    pick = [c for _, c in cards[:90]] + [c for _, c in cards[-30:]]
    rng.shuffle(pick)
    reqs = []
    for r in range(6):
        user = "CARDS (its exit beat the simple rule on most of these; a few where it did worse):\n\n" + "\n\n".join(pick[r * 20:(r + 1) * 20])
        reqs.append({"custom_id": f"ex_{r}", "params": {"model": B4.S.MODEL, "max_tokens": 16000, "system": SYS, "messages": [{"role": "user", "content": user}]}})
    with open(f"{WK}/req_exit.jsonl", "w") as f:
        for q in reqs: f.write(json.dumps(q) + "\n")
    B4.sync("exit")
