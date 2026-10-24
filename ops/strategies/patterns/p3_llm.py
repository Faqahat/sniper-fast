#!/usr/bin/env python3
# LLM-in-the-loop pattern search: Haiku 5.5 reads TRAIN-day (R2) tape stories and proposes (a) new trigger->reaction rules in a
# small JSON DSL that p4_eval.py compiles and replays, and (b) recurring behaviors of the ID'd bots (B<id>), which
# p5_bots.py verifies in code. R3 stories are never sent (R3 stays the clean test day). Message Batches API; usage goes to
# the shared ledger (kinds "pat_*"); this task's cap is $40 (checked before every submit with a worst-case bound).
#   python3 p3_llm.py prep r1 | submit r1 | status r1 | fetch r1        (round 2/3 prompts are written by p6_round.py)
import sys, os, json, time, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s4_llm as S
PO = "/home/moiz/sniper-data/strategies/patterns"; WK = f"{PO}/llm"
CAP = 40.0; PER = int(os.environ.get("PER", "20")); MAXTOK = 16000
FEATDOC = """FEATURES (all measured at the trigger trade, using only trades up to and including it; no look-ahead):
 trigger trade: ev_buy (1 buy / 0 sell), sol (SOL size), move (% price change caused by this trade, + for buys),
   wt (wallet type of the trader: "creator", "insider" (bought in the create slot), "new" (first seen < 10 min ago), "bot"
   (active bot, R2 list), "F1".."F10" (profitable families, see KNOWN), "other"), w_first (1 = trader's first trade in this
   token), bid (bot ID number of the trader, 0 if none; B17 -> 17)
 token state after the trade: age (slots since create; 1 slot = 0.212 s), curve (virtual SOL in the curve: 30 at start, ~115 =
   graduation), ath_r (price / all-time high so far, 1 = at ATH), from_bun (price / price right after the create slot),
   ret1 ret3 ret10 ret30 ret100 (% price change over the last 1/3/10/30/100 slots), quiet (slots since the previous trade)
 windows over the last w slots (w = 1, 3, 10, 30; w=1 is the current slot): nb<w>/ns<w> (# buys/sells), bsol<w>/ssol<w> (SOL),
   maxb<w>/maxs<w> (largest buy/sell SOL); for w = 3, 10, 30 also net<w> (buy SOL - sell SOL), nw<w> (distinct wallets),
   bigb<w>/bigs<w> (# buys/sells >= 0.5 SOL), dd<w> (% drop from the window's highest price to now)
 flows: fam_b10/fam_s10 (# buys/sells by F-family wallets, last 10 slots), bot_b10, fresh_b10 (# buys by bots / new wallets,
   last 10 slots), dev_s30 / ins_s30 (SOL sold by the creator / insiders, last 30 slots), dev_sold / ins_sold (fraction of
   their tokens sold so far, 0-1), nbot_hold / fam_hold (# ID'd bots / family bots currently holding this token)
 totals: ntr (# trades so far), nwal (# distinct wallets so far), peak (highest curve SOL so far), hour (PKT 0-23)
 launch label (by Haiku from name/metadata): theme ("animal","character_meme","person_celebrity","politics","ai_tech",
   "crypto_finance","news_event","sports","food","brand_product","nsfw_vulgar","gibberish_random","other"),
   x ("post","profile","community","none"), eff (listing effort 0-3), fun (0-3), rw (1 = rides a real-world event), cpy, red
 bot-specific: "holds:<id>" (1 if bot <id> currently holds this token), "acted:<id>:<k>" (1 if bot <id> traded this token in
   the last k slots)"""
SYSTEM = """You are a quantitative researcher hunting for profitable, REPEATABLE trading patterns on pump.fun bonding curves (Solana
meme-coin launches), and studying the other bots that trade them.

MARKET: each token trades on a constant-product bonding curve (virtual reserves start at 30 SOL; graduation at ~115 SOL).
Every buy raises the price, every sell lowers it. 1 slot = 0.212 s. Pump fee 1.25% per side.

OUR BOT: sees every trade within a few ms. If it reacts to a trade, its buy lands ~35 ms later (about 65 transactions later in
the same slot) on ~56% of slots, otherwise ~50 ms or the next slot. Costs per round trip: 1.25% fee each side + 0.0035 SOL
fixed (+0.0005 per failed buy; a buy fails if the price already rose >5% after the trigger). Size 0.35-0.75 SOL. One open
position at a time. Buy-then-sell only (no shorting). Bots that land 2-13 transactions behind a trigger are out of our reach.

KNOWN (already tested; do NOT re-propose these without a clear new twist):
1. Dip backrun (our live bot): buy right after a >=1 SOL sell that drops price >=4.65% (token <=344 s old), sell after 1.3-4 s.
   Works only at ~35 ms with a trained selection model; generic dip buying without selection loses 1-5% per trade.
2. F7 quiet bait: a 0.9-3 SOL buy on a token quiet >=20 slots, age >=150 slots, curve <=45 SOL makes follower bots buy within
   1 slot ~63% of the time; the first buyer sells ~21 s later: +3.4% per SOL on both days (measured on other people's baits).
3. F4 big-buy backrun scalp (land 2 tx behind a >=0.5 SOL buy, sell 4 slots later): needs bundle placement; loses at our speed.
4. F1 creator-dump backrun: winners land 5-13 tx behind the creator's sell; loses at our speed.
5. F6 momentum entry + ladder exit and generic momentum buys after big buys: lose at our speed (35-50 ms).
6. F3 dip buy + 30 s timer: worse than short exits. 7. Copying winning wallets with 1-2 slots of lag: loses.
8. Early-launch momentum snipes: about break-even at our speed. 9. Create-slot insiders/bundles: not copyable.
Families of profitable wallets in the tags: F1 dev-dump backrun, F2 big-sell dip backrun, F3 dip + 30 s timer, F4 big-buy
backrun scalp, F5 early-launch momentum, F6 momentum + ladder, F7 quiet bait, F8 follow big buys + scale in, F9 0.3 SOL
active-token scalper, F10 mixed swing. B<id> = a stable ID for one specific active wallet (same ID across all tokens).

STORY FORMAT: one block per token: header (launch label, creator buy, create-slot insiders, life summary), then time buckets
by token age in slots: price change %, curve SOL at bucket end, buys n/SOL, sells n/SOL, new wallets, notable trades
"@<age slot> <B|S><SOL> <who><price impact %>" (all trades >= 0.5 SOL and all trades by ID'd bots).

YOUR TASKS
A) Propose up to 4 NEW trigger->reaction rules we could profit from at OUR speed, as JSON in this DSL:
 {"name": "<short>", "event": "buy" | "sell" | "any" | "idle", "idle_slots": <int, only for idle: fires once when the token has
  had no trade for that many slots>, "when": [[<feature>, <op>, <value>], ...]   (op: ">=", "<=", ">", "<", "==", "!=", "in",
  "not_in"; values are numbers, or strings/lists of strings for wt/theme/x),
  "race": true|false (true = must land in the same slot right behind the trigger; false = enters in the next slot),
  "mode": "follow" | "be_trigger" (be_trigger: WE make the trigger buy ourselves, e.g. a bait buy; only with event "buy"; the
  replay then uses real trigger buys made by others as stand-ins for ours, so keep "sol" bounds realistic for us),
  "size": <0.35-0.75>, "exit": {"tp": <price multiple or null>, "sl": <multiple or null>, "max_slots": <int>, "on": [<exit
  events>]}  (exit events: "dev_sell", "big_sell" (another wallet sells >=0.5 SOL), "big_buy" (another wallet buys >=0.5 SOL:
  sell into it), "fam_sell", "bot_buy:<id>", "bot_sell:<id>"),
  "why": "<one line>", "evidence": ["<story ids>"]}
 Rules must use only the FEATURES below. Prefer patterns you saw repeat across several stories.
B) Describe up to 6 recurring behaviors of ID'd bots (B<id>) that you saw in these stories, as JSON:
 {"bot": "B<id>", "trigger": {"event": "buy"|"sell"|"any", "when": [[<feature>, <op>, <value>], ...]} (the OTHER wallet's
  trade that the bot reacts to; may be empty for "acts on its own"), "action": "buy" | "sell", "within_slots": <int>,
  "size": [<min SOL>, <max SOL>], "notes": "<timing, tokens, holding style>", "exploit": "be_trigger" | "front_run" | "avoid" |
  "none", "exploit_idea": "<one line: how we could profit, at our speed>", "evidence": ["<story ids>"]}
Reply with ONLY one JSON object: {"rules": [...], "bots": [...]}  (no prose, no code fences).

""" + FEATDOC

def ledger_task():
    L = S.ledger(); return sum(e["usd"] for e in L["entries"] if e["kind"].startswith("pat_"))

def prep_r1():
    os.makedirs(WK, exist_ok=True)
    st = [json.loads(l) for l in open(f"{PO}/stories_R2.jsonl")]
    st.sort(key=lambda o: (o["focus_bot"] == 0, o["focus_bot"], o["id"]))
    reqs = []
    for k in range(0, len(st), PER):
        ch = st[k:k + PER]
        user = "STORIES (train day):\n\n" + "\n\n".join(o["text"] for o in ch)
        reqs.append({"custom_id": f"r1_{k // PER:04d}", "params": {"model": S.MODEL, "max_tokens": MAXTOK, "system": SYSTEM,
                     "messages": [{"role": "user", "content": user}]}})
    write("r1", reqs)

def write(rnd, reqs):
    with open(f"{WK}/req_{rnd}.jsonl", "w") as f:
        for r in reqs: f.write(json.dumps(r) + "\n")
    chars = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"]) for r in reqs)
    tin = chars / 2.6; tout = len(reqs) * 7000
    est = (tin * S.PRICE_IN + tout * S.PRICE_OUT) / 2e6
    print(f"{rnd}: {len(reqs)} requests, ~{tin / 1e6:.2f}M input tokens, est ${est:.2f} batch; task spend so far ${ledger_task():.3f}")
    return est

def submit(rnd):
    reqs = [json.loads(l) for l in open(f"{WK}/req_{rnd}.jsonl")]
    chars = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"]) for r in reqs)
    worst = (chars / 2.0 * S.PRICE_IN + len(reqs) * MAXTOK * S.PRICE_OUT) / 2e6
    if ledger_task() + worst > CAP: raise SystemExit(f"refused: task spend ${ledger_task():.2f} + worst ${worst:.2f} > ${CAP}")
    b = S.call("POST", "/messages/batches", {"requests": reqs})
    json.dump({"id": b["id"], "n": len(reqs), "t": time.time(), "worst": worst}, open(f"{WK}/batch_{rnd}.json", "w"))
    print(f"submitted {rnd}: {b['id']} ({len(reqs)} requests), worst case ${worst:.2f}")

def status(rnd):
    st = json.load(open(f"{WK}/batch_{rnd}.json")); b = S.call("GET", f"/messages/batches/{st['id']}")
    print(rnd, b.get("processing_status"), b.get("request_counts")); return b.get("processing_status") == "ended"

def fetch(rnd):
    st = json.load(open(f"{WK}/batch_{rnd}.json"))
    if st.get("fetched"): print("already fetched"); return
    b = S.call("GET", f"/messages/batches/{st['id']}")
    if b.get("processing_status") != "ended": print("not ended", b.get("request_counts")); return
    tin = tout = 0; nr = nb = bad = 0
    with open(f"{WK}/rules_{rnd}.jsonl", "w") as fr, open(f"{WK}/bots_{rnd}.jsonl", "w") as fb:
        for l in S.call("GET", b["results_url"], raw=True).decode().splitlines():
            r = json.loads(l); res = r.get("result", {})
            if res.get("type") != "succeeded": bad += 1; continue
            m = res["message"]; u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
            o = S.parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"))
            if not isinstance(o, dict): bad += 1; continue
            for x in o.get("rules") or []:
                if isinstance(x, dict): fr.write(json.dumps({"src": r["custom_id"], **x}) + "\n"); nr += 1
            for x in o.get("bots") or []:
                if isinstance(x, dict): fb.write(json.dumps({"src": r["custom_id"], **x}) + "\n"); nb += 1
    usd = S.add_spend(f"pat_{rnd}", tin, tout, batch=True)
    st["fetched"] = True; st["usage"] = [tin, tout, usd]; json.dump(st, open(f"{WK}/batch_{rnd}.json", "w"))
    print(f"{rnd}: {nr} rules, {nb} bot behaviors, {bad} failed/unparsed; ${usd:.3f}; task spend ${ledger_task():.3f}")

def sync(rnd, threads=4):
    """run a round's requests with the normal Messages API (full price) when batches are queued too long"""
    from concurrent.futures import ThreadPoolExecutor
    reqs = [json.loads(l) for l in open(f"{WK}/req_{rnd}.jsonl")]
    chars = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"]) for r in reqs)
    worst = (chars / 2.0 * S.PRICE_IN + len(reqs) * MAXTOK * S.PRICE_OUT) / 1e6
    if ledger_task() + worst > CAP: raise SystemExit(f"refused: task spend ${ledger_task():.2f} + worst ${worst:.2f} > ${CAP}")
    def one(r):
        try: m = S.call("POST", "/messages", r["params"])
        except SystemExit as ex: return r["custom_id"], None, 0, 0
        u = m.get("usage", {})
        return r["custom_id"], S.parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")), u.get("input_tokens", 0), u.get("output_tokens", 0)
    tin = tout = 0; nr = nb = bad = 0
    with ThreadPoolExecutor(threads) as ex, open(f"{WK}/rules_{rnd}.jsonl", "w") as fr, open(f"{WK}/bots_{rnd}.jsonl", "w") as fb:
        for cid, o, a, b in ex.map(one, reqs):
            tin += a; tout += b
            if not isinstance(o, dict): bad += 1; continue
            for x in o.get("rules") or []:
                if isinstance(x, dict): fr.write(json.dumps({"src": cid, **x}) + "\n"); nr += 1
            for x in o.get("bots") or []:
                if isinstance(x, dict): fb.write(json.dumps({"src": cid, **x}) + "\n"); nb += 1
    usd = S.add_spend(f"pat_{rnd}_sync", tin, tout, batch=False)
    print(f"{rnd} (sync): {nr} rules, {nb} bot behaviors, {bad} failed; ${usd:.3f}; task spend ${ledger_task():.3f}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prep" and a[1] == "r1": prep_r1()
    elif a[0] == "submit": submit(a[1])
    elif a[0] == "status": status(a[1])
    elif a[0] == "fetch": fetch(a[1])
    elif a[0] == "sync": sync(a[1])
