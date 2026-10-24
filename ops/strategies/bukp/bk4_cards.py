#!/usr/bin/env python3
# Haiku pass for BUkpShoE (train day R2 only): compact cards of TAKEN trips (trigger trade, token state, its buy, the path,
# what preceded its sell, P&L) and of SKIPPED similar moments (high selection-model score, same token or same hour, not
# taken). Haiku infers the exact entry filter and the early-exit rule as DSL JSON. Batch API, spend kind "bukp_*" (cap $20).
#   python3 bk4_cards.py prep r1 | submit r1 | status r1 | fetch r1
import sys, os, json, zlib, random, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import s4_llm as S
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/bukp"; WK = f"{OUT}/llm"
W = "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP"; UID = zlib.crc32(W.encode())
CAP = 20.0; MAXTOK = 16000
WTN = {0: "other", 1: "creator", 2: "insider", 3: "new", 4: "bot", **{10 + k: f"F{k}" for k in range(1, 11)}}
KNOWN = """MEASURED FACTS ABOUT THIS WALLET (do not re-derive; use them):
 - ~3,500-3,850 round trips per day, one buy then one sell per trip (no scale-ins, no ladders), never in the create slot.
 - Buy size = ~2.0% of the token's curve SOL at entry (0.60 SOL at curve 30, 1.0 at 50, 1.6 at 80): a fixed ~4% price impact.
 - 73% of entries come right after ANOTHER wallet's BUY in the same slot (median 0.33 SOL, +1.5%); 27% right after a SELL
   (median 0.85 SOL, -3.9%). It lands a median ~100 transactions after the trigger in the same slot.
 - It holds 5-7 positions at once (max ~20). 24% of trips end at a fixed ~1,417-slot (~300 s) timeout; the rest exit earlier.
 - 57% of the early exits come right after another wallet's SELL in the same slot. Exit price / entry: p10 0.79, p50 1.02, p90 1.41.
 - ~40% of its transactions fail (it fires on more moments than it fills); fees ~0.0002 SOL priority + 0.00021 SOL tip.
 - A gradient-boosted model separates its taken moments from skipped ones with AUC ~0.91 using public features; the strongest
   signals: a 0.25-1.2 SOL buy or a >=1.2 SOL sell in the current slot, a large 1-slot price move either way, curve 32-64 SOL,
   younger tokens, and MORE active bots / profitable-family bots currently holding the token (nbot_hold, fam_hold)."""
SYSTEM = """You are reverse-engineering ONE trading bot's exact rules on pump.fun bonding curves (Solana meme coins; constant-product
curve from 30 to ~115 virtual SOL; 1 slot = 0.212 s; pump fee 1.25% per side). You get cards of its TAKEN trades (with the
trigger trade right before its buy, the token state, its buy, the price path while it held, what happened right before its
sell, and the result) and cards of SKIPPED moments that looked similar but it did not trade.
""" + "{KNOWN}" + """
TASK: infer the remaining unknowns precisely:
 1. ENTRY FILTER: which conditions separate taken from skipped moments (thresholds on the features named in the cards).
 2. EARLY-EXIT RULE: what makes it sell before the 300 s timeout (e.g. a sell by another wallet of >= X SOL, price falling
    below entry, a take-profit level, a drop from the peak, a quiet period, a number of slots) - be specific with numbers.
 3. Anything else systematic (time of day, token type, which wallets' trades it reacts to).
Express entry rules in this DSL (features as named in the cards):
 {"name": str, "event": "buy"|"sell"|"any", "when": [[feature, op, value], ...], "exit": {"tp": mult|null, "sl": mult|null,
  "max_slots": int, "on": [exit events]}, "why": str}
 ops: ">=", "<=", ">", "<", "==", "!=", "in", "not_in"; exit events: "big_sell" (another wallet sells >= 0.5 SOL), "big_buy",
 "dev_sell", "fam_sell". Features: sol, move, wt (creator/insider/new/bot/other/F1..F10), age, curve, ath_r, from_bun, ret1,
 ret3, ret10, ret30, ret100, quiet, nb1, ns1, bsol1, ssol1, maxb1, maxs1, nb3/ns3/bsol3/ssol3/net3/nw3/bigb3/bigs3/maxb3/
 maxs3/dd3 (same for 10 and 30), fam_b10, fam_s10, bot_b10, fresh_b10, dev_s30, ins_s30, dev_sold, ins_sold, ntr, nwal, peak,
 hour, nbot_hold, fam_hold.
Reply with ONLY one JSON object: {"entry_rules": [up to 3 rules, best first], "exit_hypotheses": [up to 3 exit objects with
 a one-line "why"], "other_findings": [short strings]}"""

def fmt_trade(d, j, base_slot, me=False):
    F = d["F"]; FI = d["FI"]
    who = "THIS BOT" if me else WTN.get(int(d["wt"][j]), "other") + (f"/B{int(d['bid'][j])}" if d["bid"][j] else "")
    return f"@{int(d['s'][j] - base_slot):+d} {'BUY ' if d['buy'][j] else 'SELL'} {d['sol'][j] / 1e9:.2f} {who} move {F[j, FI['move']]:+.1f}% curve {d['vsol'][j] / 1e9:.1f}"

def state_line(d, j):
    F = d["F"]; FI = d["FI"]
    keys = ("age", "curve", "ath_r", "ret1", "ret10", "ret100", "dd3", "nb3", "ns3", "maxb1", "maxs1", "net10", "nw30", "nwal", "peak", "dev_sold", "ins_sold", "nbot_hold", "fam_hold", "hour")
    return " ".join(f"{k}={F[j, FI[k]]:.3g}" for k in keys)

def taken_card(d, t):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; s0 = int(d["s"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] == UID: j -= 1
    L = [f"TAKEN trip: token {t['mint'][:6]} | trigger = the trade right before its buy:"]
    if j >= a: L.append("  trigger: " + fmt_trade(d, j, s0) + f" | state after trigger: {state_line(d, j)}")
    L.append("  tape before entry: " + " ; ".join(fmt_trade(d, q, s0) for q in range(max(a, j - 4), j)))
    L.append(f"  its buy: {t['buys'][0]['sol']:.3f} SOL ({t['buys'][0]['sol'] / (d['vsol'][j] / 1e9) * 100 if j >= a else 0:.2f}% of curve), lands {int(t['idx'] - d['i'][j]) if j >= a and d['s'][j] == s0 else 'n/a'} tx after the trigger")
    if t["sells"]:
        ks = t["sells"][-1]["k"]
        L.append(f"  held {t['hold']} slots; peak while held {t['peak_mult']:.2f}x; exit price {t['exit_mult']:.2f}x; result {t['pnl_curve']:+.4f} SOL")
        L.append("  right before its sell: " + " ; ".join(fmt_trade(d, q, s0) for q in range(max(k0 + 1, ks - 4), ks)) + " ; " + fmt_trade(d, ks, s0, me=True))
    return "\n".join(L)

def skipped_card(d, j):
    a = j - int(d["F"][j, d["FI"]["ntr"]]) + 1; s0 = int(d["s"][j])
    # what happened next (30 slots): price change, to judge whether skipping was right
    e = int(d["tend"][j]); q = j
    while q + 1 < e and d["s"][q + 1] <= s0 + 30: q += 1
    p0 = d["vsol"][j] / d["vtok"][j]; p1 = d["vsol"][q] / d["vtok"][q]
    return ("SKIPPED moment: token " + E.DAYS["R2"]["M"]["meta"][int(d["tok"][j])]["m"][:6] + "\n  trigger: " + fmt_trade(d, j, s0) + f" | state: {state_line(d, j)}\n"
            f"  tape before: " + " ; ".join(fmt_trade(d, x, s0) for x in range(max(a, j - 4), j)) + f"\n  price 30 slots later: {(p1 / p0 - 1) * 100:+.1f}%")

def model_scores(d, idx):
    M = json.load(open(f"{OUT}/select_model.json")); FI = d["FI"]
    X = d["F"][idx][:, [FI[f] for f in M["feats"]]].astype(float)
    B = np.zeros(X.shape, np.int16)
    for c, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), X[:, c], side="right") + 1; b[np.isnan(X[:, c])] = 0; B[:, c] = b
    s = np.zeros(len(idx))
    for t in M["trees"]: s += M["lr"] * G.pred(t, B)
    return s

def prep(rnd, n_req=16, n_taken=24, n_skip=14, extra=""):
    os.makedirs(WK, exist_ok=True)
    E.load(["R2"]); d = E.DAYS["R2"]; rng = random.Random(7 + len(rnd))
    T = [t for t in json.load(open(f"{OUT}/trips_R2.json")) if t["closed"]]
    rng.shuffle(T)
    # skipped candidates: other-wallet trades with high model score, in tokens / hours where it was active, not taken
    taken_trig = set()
    for t in T:
        j = t["k0"] - 1
        while j >= 0 and d["uid"][j] == UID: j -= 1
        taken_trig.add(j)
    toks = sorted({t["tok"] for t in T})
    tokmask = np.isin(d["tok"], toks) & (d["uid"] != UID) & (d["F"][:, d["FI"]["curve"]] >= 30) & (d["F"][:, d["FI"]["age"]] >= 5)
    cand = np.flatnonzero(tokmask); cand = np.array([c for c in cand if c not in taken_trig][:400000])
    sc = model_scores(d, cand); top = cand[np.argsort(-sc)[:20000]]
    skip = list(top); rng.shuffle(skip)
    reqs = []
    sysmsg = SYSTEM.replace("{KNOWN}", KNOWN)
    for r in range(n_req):
        cards = [taken_card(d, t) for t in T[r * n_taken:(r + 1) * n_taken]] + [skipped_card(d, int(j)) for j in skip[r * n_skip:(r + 1) * n_skip]]
        rng.shuffle(cards)
        user = (extra + "\n\n" if extra else "") + "CARDS (train day):\n\n" + "\n\n".join(cards)
        reqs.append({"custom_id": f"{rnd}_{r:03d}", "params": {"model": S.MODEL, "max_tokens": MAXTOK, "system": sysmsg, "messages": [{"role": "user", "content": user}]}})
    with open(f"{WK}/req_{rnd}.jsonl", "w") as f:
        for q in reqs: f.write(json.dumps(q) + "\n")
    chars = sum(len(q["params"]["system"]) + len(q["params"]["messages"][0]["content"]) for q in reqs)
    print(f"{rnd}: {len(reqs)} requests, ~{chars / 2.6 / 1e6:.2f}M input tokens; task spend so far ${task_spend():.3f}")

def task_spend(): return sum(e["usd"] for e in S.ledger()["entries"] if e["kind"].startswith("bukp_"))

def submit(rnd):
    reqs = [json.loads(l) for l in open(f"{WK}/req_{rnd}.jsonl")]
    chars = sum(len(q["params"]["system"]) + len(q["params"]["messages"][0]["content"]) for q in reqs)
    worst = (chars / 2.0 * S.PRICE_IN + len(reqs) * MAXTOK * S.PRICE_OUT) / 2e6
    if task_spend() + worst > CAP: raise SystemExit("cap")
    b = S.call("POST", "/messages/batches", {"requests": reqs})
    json.dump({"id": b["id"], "t": time.time()}, open(f"{WK}/batch_{rnd}.json", "w")); print("submitted", b["id"], len(reqs))

def status(rnd):
    st = json.load(open(f"{WK}/batch_{rnd}.json")); b = S.call("GET", f"/messages/batches/{st['id']}")
    print(rnd, b.get("processing_status"), b.get("request_counts"))

def collect_out(rnd, items, tin, tout, batch):
    with open(f"{WK}/answers_{rnd}.jsonl", "w") as f:
        for cid, o in items: f.write(json.dumps({"id": cid, **o}) + "\n")
    usd = S.add_spend(f"bukp_{rnd}" + ("" if batch else "_sync"), tin, tout, batch=batch)
    print(f"{rnd}: {len(items)} answers; ${usd:.3f}; task spend ${task_spend():.3f}")

def fetch(rnd):
    st = json.load(open(f"{WK}/batch_{rnd}.json")); b = S.call("GET", f"/messages/batches/{st['id']}")
    if b.get("processing_status") != "ended": print("not ended", b.get("request_counts")); return
    items = []; tin = tout = 0
    for l in S.call("GET", b["results_url"], raw=True).decode().splitlines():
        r = json.loads(l); res = r.get("result", {})
        if res.get("type") != "succeeded": continue
        m = res["message"]; u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
        o = S.parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"))
        if isinstance(o, dict): items.append((r["custom_id"], o))
    collect_out(rnd, items, tin, tout, True)

def sync(rnd, threads=4):
    from concurrent.futures import ThreadPoolExecutor
    reqs = [json.loads(l) for l in open(f"{WK}/req_{rnd}.jsonl")]
    chars = sum(len(q["params"]["system"]) + len(q["params"]["messages"][0]["content"]) for q in reqs)
    if task_spend() + (chars / 2.0 * S.PRICE_IN + len(reqs) * MAXTOK * S.PRICE_OUT) / 1e6 > CAP: raise SystemExit("cap")
    def one(q):
        m = S.call("POST", "/messages", q["params"]); u = m.get("usage", {})
        return q["custom_id"], S.parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")), u.get("input_tokens", 0), u.get("output_tokens", 0)
    items = []; tin = tout = 0
    with ThreadPoolExecutor(threads) as ex:
        for cid, o, a, b in ex.map(one, reqs):
            tin += a; tout += b
            if isinstance(o, dict): items.append((cid, o))
    collect_out(rnd, items, tin, tout, False)

if __name__ == "__main__":
    a = sys.argv[1:]
    {"prep": prep, "submit": submit, "status": status, "fetch": fetch, "sync": sync}[a[0]](a[1])
