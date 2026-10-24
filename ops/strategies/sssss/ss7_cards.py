#!/usr/bin/env python3
# Haiku pass for sssssDdM (train day R2 only; adapted from bukp/bk4_cards.py, not modified). Two request types:
#  ENTRY: compact cards of TAKEN trips (tape before its buy with ms timing, token state, its buy, outcome), FAILED attempts
#         (its buy tx failed on slippage: what it TRIED to buy) and SKIPPED similar moments (high selection-model score or
#         same token +-300 slots, not attempted) -> Haiku infers the entry trigger + filters as DSL JSON.
#  EXIT:  trips with the price path while it held (every non-own trade, price multiple vs its fill, drawdown from peak)
#         and the trades right before its sell -> Haiku infers the exit logic as exit-DSL JSON.
# Batch API via sssss/llm.py (own ledger sssss/spend.json, HARD CAP $20).
#   python3 ss7_cards.py prep <tag> [n_entry n_exit] | submit <tag> | status <tag> | fetch <tag>
import sys, os, json, zlib, random
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import gbdt_np as G
import llm as L
OUT = "/home/moiz/sniper-data/strategies/sssss"; WK = f"{OUT}/llm"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
MAXTOK = 16000
WTN = {0: "other", 1: "creator", 2: "insider", 3: "new", 4: "bot", **{10 + k: f"F{k}" for k in range(1, 11)}}
KNOWN = """MEASURED FACTS ABOUT THIS BOT (wallet sssssDdM; do not re-derive, use them):
 - ~4,200-4,800 round trips per day on ~1,100-1,400 tokens; exactly ONE buy then ONE full sell per trip; never in the create
   slot; never buys a token it already holds; re-enters the same token later (median 2-5 trips per token).
 - BUY SIZE = 1.88% of the curve's SOL at entry (a fixed ~3.8% price impact): 0.72 SOL at curve 38, 0.93 at 49, 1.34 at 71.
 - It fires ~10,000-11,000 buy txs per day; ~57% FAIL on slippage (other buys landed first in the same slot and moved the
   price past its limit). Failed attempts are shown as TRIED cards - they are decisions too.
 - The operator runs a sibling wallet (ssssswdk, shown as SIBLING) with the same logic and smaller size; the sibling already
   holds the token at 55% of this bot's entries and often sells the same token in the same slot right before this bot sells.
 - Entry context: in 71% of entries the last trade before its buy is in the SAME slot (83% of those are buys, median 0.3 SOL,
   +1.2% price move; its tx lands a median ~30 transactions / ~15 ms later); 25% the last trade was 1 slot earlier.
   Base-rate lifts: >=0.5 SOL buy in the same slot x2.1, dip >=10% from the 3-slot high x2.2, price <=70% of ATH x1.9,
   price -10% over the last 10 slots x1.9, net flow >=+1 SOL (3 slots) x1.7 AND <=-1 SOL x1.8 (busy, volatile moments);
   never quiet tokens (quiet>=20 slots: 0%), never <=10 trades so far, token age median 760 slots (p10 55, p90 11,700),
   curve 38-73 SOL (median 49), price vs ATH median 0.70.
 - Holds: median 100 slots (p10 10, p90 900); 4-11 positions open at once. Exit price / entry: p10 0.80, p50 1.01, p90 1.38.
   Only trips held >=300 slots make money; short holds lose. Exits right after another wallet's SELL: 85% (73% same slot);
   no single stop-loss / trailing / take-profit / big-sell threshold reproduces its exit slot (best ~20% hits).
 - Fees: 0.0001-0.00012 SOL per tx (1 lamport/CU priority), Helius tip 0.00006 on ~25% of txs."""
SYS_ENTRY = """You are reverse-engineering ONE trading bot's exact ENTRY rules on pump.fun bonding curves (Solana meme coins;
constant-product curve from 30 to ~115 virtual SOL; 1 slot = 0.212 s; pump fee ~1.25% per side). You get cards of its TAKEN
trades (tape right before its buy with slot offsets and ms timing, the token state, its buy, outcome), TRIED moments (its buy
tx failed on slippage) and SKIPPED moments that looked similar but it did not trade.
""" + "{KNOWN}" + """
TASK: infer the ENTRY TRIGGER and FILTERS precisely: which trade event (buy / sell, size, price move, wallet type) and which
token-state conditions separate taken/tried moments from skipped ones. Be specific with numbers. Use only these features
(computed at the trigger trade = the last trade before its buy): sol, move (% price move of that trade), wt (creator/insider/
new/bot/other/F1..F10), age (slots since create), curve (virtual SOL), ath_r (price / all-time-high), from_bun, ret1, ret3,
ret10, ret30, ret100 (% price change over N slots), quiet (slots since the previous trade), nb1/ns1 (buys/sells this slot),
bsol1/ssol1, maxb1/maxs1, and for N in 3,10,30: nbN, nsN, bsolN, ssolN, netN (buy SOL - sell SOL), nwN (distinct wallets),
bigbN/bigsN (count of >=0.5 SOL buys/sells), maxbN/maxsN, ddN (% drop from the N-slot high), fam_b10, fam_s10, bot_b10,
fresh_b10, dev_s30, ins_s30, dev_sold, ins_sold (0-1), ntr (trades so far), nwal (wallets so far), peak (max curve SOL so
far), hour (PKT), nbot_hold, fam_hold (known bots / profitable-family bots holding now).
DSL: {"name": str, "event": "buy"|"sell"|"any", "when": [[feature, op, value], ...], "why": str}
 ops: ">=", "<=", ">", "<", "==", "!=", "in", "not_in".
Reply with ONLY one JSON object: {"entry_rules": [up to 4 rules, best first; together they should cover most taken moments],
 "trigger_latency": "<how fast it reacts and to what>", "other_findings": [short strings]}"""
SYS_EXIT = """You are reverse-engineering ONE trading bot's exact EXIT rule on pump.fun bonding curves (Solana meme coins;
constant-product curve 30 to ~115 virtual SOL; 1 slot = 0.212 s; pump fee ~1.25% per side). Each card is one round trip:
its buy, then EVERY other trade while it held (slot offset since its buy, side, SOL, wallet type, % price move of that
trade, price multiple vs its entry fill AFTER that trade, peak multiple so far, drawdown from peak), then its sell.
""" + "{KNOWN}" + """
TASK: infer WHEN it sells. Find the exact condition(s) on the trade right before its sell and on the position state, that
make it sell there and NOT at the earlier trades. Consider: size / price move of a sell (or buy) by another wallet, the
position multiple, drawdown from peak, time held, flow since entry (sold vs bought SOL), counts of sells in recent slots,
"momentum fading" signals, sibling selling. Be specific with numbers.
EXIT DSL: {"name": str, "any_of": [[[feature, op, value], ...], ...], "max_slots": int|null, "why": str}
 - "any_of" is a list of condition lists; it sells at the FIRST other-wallet trade where ALL conditions of ANY list hold.
 - features: ev ("buy"/"sell"), sol, move, wt, mult (price / its fill after the trade), peak (max mult so far), dd (drawdown
   from peak, 0-1), held (slots since its buy), sold_since / bought_since (other wallets' SOL since its buy), net_since,
   n_sells_3 / n_buys_3 / sell_sol_3 / buy_sol_3 / net_3 (other wallets, last 3 slots incl. this one), same for _10,
   ret3, ret10 (% price change over 3 / 10 slots), sib_sold (1 if the SIBLING sold this token within the last 2 slots).
Reply with ONLY one JSON object: {"exit_rules": [up to 3 exit rules, best first], "other_findings": [short strings]}"""

def P(d, j): return float(d["vsol"][j] / d["vtok"][j])
def who(d, j):
    u = int(d["uid"][j])
    if u == UID: return "THIS BOT"
    if u in set(int(x) for x in FLEET[1:]): return "SIBLING"
    return WTN.get(int(d["wt"][j]), "other")
def fmt(d, j, s_ref, a_ref, extra=""):
    F = d["F"]; FI = d["FI"]
    return (f"{int(d['s'][j] - s_ref):+d}sl {d['arr'][j] - a_ref:+.0f}ms {'BUY ' if d['buy'][j] else 'SELL'} {d['sol'][j] / 1e9:.2f} {who(d, j)} "
            f"{F[j, FI['move']]:+.1f}% c{d['vsol'][j] / 1e9:.1f}{extra}")
def state_line(d, j):
    F = d["F"]; FI = d["FI"]
    keys = ("age", "curve", "ath_r", "ret1", "ret3", "ret10", "ret30", "dd3", "dd10", "nb3", "ns3", "net3", "net10", "maxb1", "maxs1", "nw10", "ntr", "nwal", "dev_sold", "nbot_hold", "fam_hold", "hour")
    return " ".join(f"{k}={F[j, FI[k]]:.3g}" for k in keys)
def first_idx(d, j): return j - int(d["F"][j, d["FI"]["ntr"]]) + 1

def entry_taken(d, t):
    k0 = t["k0"]; a = first_idx(d, k0); s0 = int(d["s"][k0]); a0 = float(d["arr"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] in FLEET: j -= 1
    L_ = [f"TAKEN: token {t['mint'][:6]} | state at the last trade before its buy: {state_line(d, j) if j >= a else 'n/a'}"]
    L_.append("  tape (slot / ms vs its buy): " + " ; ".join(fmt(d, q, s0, a0) for q in range(max(a, k0 - 8), k0)))
    sib = "sibling holds it" if t["sibpos"] else "sibling not in"
    L_.append(f"  ITS BUY {t['buys'][0]['sol']:.3f} SOL at idx {t['idx']} ({sib}); held {t['hold']} slots; peak {t['peak_mult']:.2f}x; exit {t['exit_mult']:.2f}x; result {t['pnl_curve']:+.3f} SOL")
    return "\n".join(L_)
def entry_tried(d, at):
    q = at["q"]; a = first_idx(d, q); s0 = at["s"]; a0 = s0 * 212.0 + 106
    e = int(d["tend"][q]); z = q
    while z + 1 < e and d["s"][z + 1] <= s0 + 30: z += 1
    return (f"TRIED (failed on slippage): token {d['M']['meta'][int(d['tok'][q])]['m'][:6]} | state at the last trade before: {state_line(d, at['j'])}\n"
            f"  tape (slot / ms vs its attempt): " + " ; ".join(fmt(d, x, s0, a0) for x in range(max(a, q - 7), q + 1)) +
            f"\n  price 30 slots later vs then: {(P(d, z) / P(d, q) - 1) * 100:+.1f}%")
def entry_skipped(d, j):
    a = first_idx(d, j); s0 = int(d["s"][j]); a0 = float(d["arr"][j]); e = int(d["tend"][j]); z = j
    while z + 1 < e and d["s"][z + 1] <= s0 + 30: z += 1
    return (f"SKIPPED: token {d['M']['meta'][int(d['tok'][j])]['m'][:6]} | state at this trade: {state_line(d, j)}\n"
            f"  tape (slot / ms vs the last trade): " + " ; ".join(fmt(d, x, s0, a0) for x in range(max(a, j - 7), j + 1)) +
            f"\n  price 30 slots later vs then: {(P(d, z) / P(d, j) - 1) * 100:+.1f}%")
def exit_card(d, t, max_rows=45):
    k0 = t["k0"]; ks = t["sells"][-1]["k"]; s0 = int(d["s"][k0]); p_in = t["p_in"]
    rows = []; pk = 1.0
    for q in range(k0 + 1, ks):
        if d["uid"][q] == UID: continue
        m = P(d, q) / p_in; pk = max(pk, m)
        rows.append(f"{int(d['s'][q] - s0):+d} {'B' if d['buy'][q] else 'S'} {d['sol'][q] / 1e9:.2f} {who(d, q)} {d['F'][q, d['FI']['move']]:+.1f}% m{m:.3f} pk{pk:.3f} dd{1 - m / pk:.3f}")
    if len(rows) > max_rows: rows = rows[:12] + [f"... {len(rows) - max_rows + 12} trades omitted ..."] + rows[-(max_rows - 12):]
    return (f"TRIP token {t['mint'][:6]}: its buy {t['buys'][0]['sol']:.3f} SOL at curve {t['buys'][0]['vsol'] / 1e9:.1f}; trades while held "
            f"(slot since buy, side, SOL, wallet, move, mult, peak, dd):\n  " + "\n  ".join(rows) +
            f"\n  ITS SELL at +{t['hold']} slots: exit {t['exit_mult']:.3f}x, result {t['pnl_curve']:+.3f} SOL")

def model_scores(d, idx):
    M = json.load(open(f"{OUT}/select_model.json")); FI = d["FI"]
    X = d["F"][idx][:, [FI[f] for f in M["feats"]]].astype(float)
    B = np.zeros(X.shape, np.int16)
    for c, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), X[:, c], side="right") + 1; b[np.isnan(X[:, c])] = 0; B[:, c] = b
    s = np.zeros(len(idx))
    for t in M["trees"]: s += M["lr"] * G.pred(t, B)
    return s

def prep(tag, n_entry=16, n_exit=14, extra=""):
    os.makedirs(WK, exist_ok=True)
    E.load(["R2"]); d = E.DAYS["R2"]; rng = random.Random(11 + len(tag))
    T = [t for t in json.load(open(f"{OUT}/trips_R2.json")) if t["closed"]]
    att = json.load(open(f"{OUT}/att_R2.json"))
    tried = [a for a in att if not a["ok"] and a["dslot"] <= 2]
    att_j = {a["j"] for a in att}
    rng.shuffle(T); rng.shuffle(tried)
    # skipped: (1) top selection-model scores among non-attempted trades in its tokens; (2) same token +-300 slots
    toks = sorted({t["tok"] for t in T}); isfleet = np.isin(d["uid"], FLEET)
    F = d["F"]; FI = d["FI"]
    cand = np.flatnonzero(np.isin(d["tok"], toks) & ~isfleet & (F[:, FI["curve"]] >= 30) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5))
    cand = np.array([c for c in cand if c not in att_j])
    skip_model = []
    if os.path.exists(f"{OUT}/select_model.json"):
        sc = model_scores(d, cand); skip_model = list(cand[np.argsort(-sc)[:20000]]); rng.shuffle(skip_model)
    near = []
    for t in T[:3000]:
        lo = first_idx(d, t["k0"]); hi = int(d["tend"][t["k0"]])
        ss = np.flatnonzero((d["s"][lo:hi] >= t["slot"] - 300) & (d["s"][lo:hi] <= t["slot"] + 300)) + lo
        ss = [int(x) for x in ss if not isfleet[x] and x not in att_j]
        if ss: near.append(rng.choice(ss))
    rng.shuffle(near)
    sys_e = SYS_ENTRY.replace("{KNOWN}", KNOWN); sys_x = SYS_EXIT.replace("{KNOWN}", KNOWN)
    reqs = []; ti = 0; tri = 0; sm = 0; sn = 0
    for r in range(n_entry):
        cards = [entry_taken(d, t) for t in T[ti:ti + 22]]; ti += 22
        cards += [entry_tried(d, a) for a in tried[tri:tri + 8]]; tri += 8
        cards += [entry_skipped(d, int(j)) for j in skip_model[sm:sm + 10]]; sm += 10
        cards += [entry_skipped(d, int(j)) for j in near[sn:sn + 10]]; sn += 10
        rng.shuffle(cards)
        user = (extra + "\n\n" if extra else "") + "CARDS (train day; 'ms' = modelled arrival time difference):\n\n" + "\n\n".join(cards)
        reqs.append({"custom_id": f"{tag}_entry_{r:03d}", "params": {"model": L.MODEL, "max_tokens": MAXTOK, "system": sys_e, "messages": [{"role": "user", "content": user}]}})
    TX = sorted(T, key=lambda t: t["slot"]); rng.shuffle(TX)
    # exit cards: balanced mix of short / medium / long holds
    short = [t for t in TX if t["hold"] < 30]; med = [t for t in TX if 30 <= t["hold"] < 300]; lng = [t for t in TX if t["hold"] >= 300]
    for r in range(n_exit):
        ts = short[r * 4:(r + 1) * 4] + med[r * 6:(r + 1) * 6] + lng[r * 4:(r + 1) * 4]
        cards = [exit_card(d, t) for t in ts]; rng.shuffle(cards)
        user = (extra + "\n\n" if extra else "") + "TRIPS (train day):\n\n" + "\n\n".join(cards)
        reqs.append({"custom_id": f"{tag}_exit_{r:03d}", "params": {"model": L.MODEL, "max_tokens": MAXTOK, "system": sys_x, "messages": [{"role": "user", "content": user}]}})
    with open(f"{WK}/req_{tag}.jsonl", "w") as f:
        for q in reqs: f.write(json.dumps(q) + "\n")
    chars = sum(len(q["params"]["system"]) + len(q["params"]["messages"][0]["content"]) for q in reqs)
    print(f"{tag}: {len(reqs)} requests, ~{chars / 3.0 / 1e6:.2f}M input tokens; worst case ${L.worst_case(reqs):.3f}; spend so far ${L.ledger()['usd']:.3f}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prep": prep(a[1], *(int(x) for x in a[2:4]))
    elif a[0] == "submit": L.submit(a[1], [json.loads(l) for l in open(f"{WK}/req_{a[1]}.jsonl")])
    elif a[0] == "status": print(L.status(a[1]))
    elif a[0] == "fetch": L.fetch(a[1])
