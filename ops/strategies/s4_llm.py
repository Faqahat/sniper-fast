#!/usr/bin/env python3
# LLM pass (owner 10-24): Claude Haiku 5.5 reads each winner's evidence card and describes its strategy. Message Batches
# API (half price). The API key is read from ~/.config/sniper/anthropic_key and never printed or written anywhere.
# Every response's real token usage goes into a spend ledger; HARD CAP $15 for this task (checked before each submit).
#   python3 s4_llm.py prep [cards|families]      -> WORK/requests_<kind>.jsonl + cost estimate
#   python3 s4_llm.py submit <kind>              -> batch (refused if ledger + estimate > cap)
#   python3 s4_llm.py status <kind> | fetch <kind>
import json, os, sys, time, urllib.request, urllib.error, glob
OUT = "/home/moiz/sniper-data/strategies"; WORK = f"{OUT}/llm"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50          # $/MTok normal; batch = half
CAP = 15.0
API = "https://api.anthropic.com/v1"
LEDGER = f"{WORK}/spend.json"
SYSTEM_CARD = """You are a quantitative analyst studying trading bots on pump.fun bonding curves (Solana meme-coin launches).
Background: each new token trades on a constant-product bonding curve (virtual reserves start at 30 SOL; the curve completes
and the token "graduates" at ~115 SOL virtual). Every buy raises the price, every sell lowers it. A slot is 0.212 s; many
bots race to land in the same block (slot) as a trigger transaction. Pump fees are ~1.25% per side; landing services
take tips. "Insider" trades (creator, bundle in the create slot) were already removed from the data you see.
You get an EVIDENCE CARD for one wallet that was consistently profitable over ~46 hours (realized P&L only). The card shows
its round trips, P&L, sizes, holding times, the context right before its entries compared with BASE RATES over all
traders (lift = how much more often than average), its exit context, speed (block position after a trigger), fees/tips,
active hours (PKT = UTC+5) and example trips with the trade tape around entry and exit.
Infer the wallet's strategy from the evidence. Be concrete and quantitative; quote the numbers that support you. If the
evidence is weak or mixed, say so and lower your confidence. Reply with ONLY one JSON object (no prose, no code fences):
{"family": "<2-5 word strategy family name>",
 "entry_rule": "<one sentence, concrete thresholds: trigger, size, token age, curve level>",
 "exit_rule": "<one sentence: timer / take-profit / sell-into-buys / stop, with numbers>",
 "speed": "<one of: same-block, 1-3 slots, seconds, minutes, not speed-based>",
 "latency_ms": <rough max latency after the trigger that still works, integer ms, or null>,
 "info_source": "<one of: public on-chain, insider/coordination, off-chain/social, unclear>",
 "how_it_makes_money": "<1-2 sentences>",
 "testable_rule": "<a concrete rule another bot could replay on recorded data: trigger + filters + size + exit>",
 "dip_backrun": <true if this is 'buy right after a big sell in the same block, sell within seconds', else false>,
 "crowding_hint": "<what in the card suggests many bots chase the same trigger, or 'none'>",
 "risks": "<1 sentence>",
 "confidence": <0.0-1.0>}"""

def key(): return open(os.path.expanduser("~/.config/sniper/anthropic_key")).read().strip()

def call(method, path, body=None, raw=False):
    h = {"x-api-key": key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    for k in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + path if path.startswith("/") else path, data=data, headers=h, method=method), timeout=180)
            b = r.read()
            return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 529) and k < 5: time.sleep(3 * (k + 1)); continue
            raise SystemExit(f"API error {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError):
            if k < 5: time.sleep(3 * (k + 1)); continue
            raise

def ledger():
    try: return json.load(open(LEDGER))
    except Exception: return {"entries": [], "usd": 0.0}

def add_spend(kind, tin, tout, batch=True):
    L = ledger(); usd = (tin * PRICE_IN + tout * PRICE_OUT) / 1e6 * (0.5 if batch else 1.0)
    L["entries"].append({"kind": kind, "in": tin, "out": tout, "usd": round(usd, 4), "t": time.time()}); L["usd"] = round(L["usd"] + usd, 4)
    json.dump(L, open(LEDGER, "w"), indent=1); return usd

def prep(kind):
    os.makedirs(WORK, exist_ok=True)
    reqs = []
    if kind == "cards":
        cards = json.load(open(f"{OUT}/cards.json"))
        for u in cards:
            txt = open(f"{OUT}/cards/{u}.txt").read()
            reqs.append({"custom_id": u[:60], "params": {"model": MODEL, "max_tokens": 12000, "system": SYSTEM_CARD,
                         "messages": [{"role": "user", "content": txt}]}})
    elif kind.startswith("fam"):
        for f in sorted(glob.glob(f"{WORK}/fam_prompts/*.txt")):
            fid = os.path.basename(f)[:-4]
            reqs.append({"custom_id": fid[:60], "params": {"model": MODEL, "max_tokens": 12000, "system": open(f"{WORK}/fam_system.txt").read(),
                         "messages": [{"role": "user", "content": open(f).read()}]}})
    with open(f"{WORK}/requests_{kind}.jsonl", "w") as f:
        for r in reqs: f.write(json.dumps(r) + "\n")
    chars = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"]) for r in reqs)
    tin = chars / 3.3; tout = len(reqs) * 4000
    est = (tin * PRICE_IN + tout * PRICE_OUT) / 2e6
    print(f"{kind}: {len(reqs)} requests, ~{tin / 1e6:.2f}M input tokens, ~{tout / 1e6:.2f}M output (incl. thinking) -> est ${est:.2f} at batch price; ledger so far ${ledger()['usd']:.2f}")
    return est

def submit(kind):
    est = prep(kind); L = ledger()
    # worst case: every request uses its full max_tokens of output
    reqs = [json.loads(l) for l in open(f"{WORK}/requests_{kind}.jsonl")]
    worst = est + len(reqs) * 12000 * PRICE_OUT / 2e6
    if L["usd"] + worst > CAP: raise SystemExit(f"refused: ledger ${L['usd']:.2f} + worst case ${worst:.2f} > cap ${CAP}")
    b = call("POST", "/messages/batches", {"requests": reqs})
    st = {"id": b["id"], "n": len(reqs), "t": time.time(), "est": est, "worst": worst}
    json.dump(st, open(f"{WORK}/batch_{kind}.json", "w"))
    print(f"submitted {kind}: batch {b['id']} with {len(reqs)} requests; status {b.get('processing_status')}; est ${est:.2f}, worst ${worst:.2f}")

def status(kind):
    st = json.load(open(f"{WORK}/batch_{kind}.json"))
    b = call("GET", f"/messages/batches/{st['id']}")
    print(f"{kind} {st['id']}: {b.get('processing_status')} {b.get('request_counts')}")
    return b.get("processing_status") == "ended"

def parse(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: return None
    try: return json.loads(text[a:b + 1])
    except ValueError: return None

def fetch(kind):
    st = json.load(open(f"{WORK}/batch_{kind}.json"))
    if st.get("fetched"): print("already fetched (usage already in ledger)"); return
    b = call("GET", f"/messages/batches/{st['id']}")
    if b.get("processing_status") != "ended": print("not ended:", b.get("request_counts")); return
    tin = tout = 0; n = bad = 0
    with open(f"{WORK}/labels_{kind}.jsonl", "w") as f:
        for l in call("GET", b["results_url"], raw=True).decode().splitlines():
            r = json.loads(l); res = r.get("result", {})
            if res.get("type") != "succeeded": bad += 1; continue
            m = res["message"]; u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
            o = parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"))
            if o is None: bad += 1; continue
            f.write(json.dumps({"id": r["custom_id"], **o}, ensure_ascii=False) + "\n"); n += 1
    usd = add_spend(kind, tin, tout, batch=True)
    st["fetched"] = True; st["usage"] = [tin, tout, usd]; json.dump(st, open(f"{WORK}/batch_{kind}.json", "w"))
    print(f"{kind}: {n} parsed, {bad} failed/unparsed; usage {tin} in + {tout} out = ${usd:.3f}; ledger total ${ledger()['usd']:.3f}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: raise SystemExit("usage: prep|submit|status|fetch <kind>")
    {"prep": prep, "submit": submit, "status": status, "fetch": fetch}[a[0]](a[1] if len(a) > 1 else "cards")
