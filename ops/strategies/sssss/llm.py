#!/usr/bin/env python3
# Minimal Anthropic API helper for the sssssDdM study (Message Batches + sync). The API key is read from
# ~/.config/sniper/anthropic_key and never printed, logged or copied. Model claude-haiku-5-5 only; no temperature;
# max_tokens >= 8000 (thinking counts as output). Every response's real usage goes into sssss/spend.json; HARD CAP $20
# (checked against the worst case before every submit).
import json, os, time, urllib.request, urllib.error
OUT = "/home/moiz/sniper-data/strategies/sssss"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50          # $/MTok normal; batch = half
CAP = 20.0
API = "https://api.anthropic.com/v1"
LEDGER = f"{OUT}/spend.json"

def _key(): return open(os.path.expanduser("~/.config/sniper/anthropic_key")).read().strip()

def call(method, path, body=None, raw=False):
    h = {"x-api-key": _key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    for k in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + path if path.startswith("/") else path, data=data, headers=h, method=method), timeout=300)
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
    except Exception: return {"entries": [], "usd": 0.0, "cap": CAP}

def add_spend(kind, tin, tout, batch=True):
    L = ledger(); usd = (tin * PRICE_IN + tout * PRICE_OUT) / 1e6 * (0.5 if batch else 1.0)
    L["entries"].append({"kind": kind, "in": tin, "out": tout, "usd": round(usd, 4), "batch": batch, "t": time.time()}); L["usd"] = round(L["usd"] + usd, 4)
    json.dump(L, open(LEDGER, "w"), indent=1); return usd

def worst_case(reqs, batch=True):
    chars = sum(len(q["params"]["system"]) + sum(len(m["content"]) for m in q["params"]["messages"]) for q in reqs)
    return (chars / 2.0 * PRICE_IN + sum(q["params"]["max_tokens"] for q in reqs) * PRICE_OUT) / 1e6 * (0.5 if batch else 1.0)

def check_cap(reqs, batch=True):
    w = worst_case(reqs, batch); s = ledger()["usd"]
    if s + w > CAP: raise SystemExit(f"refused: spend ${s:.3f} + worst case ${w:.3f} > cap ${CAP}")
    return w

def parse(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: return None
    try: return json.loads(text[a:b + 1])
    except ValueError: return None

def submit(tag, reqs):
    w = check_cap(reqs, True)
    b = call("POST", "/messages/batches", {"requests": reqs})
    json.dump({"id": b["id"], "t": time.time(), "n": len(reqs), "worst": w}, open(f"{OUT}/llm/batch_{tag}.json", "w"))
    print(f"submitted {tag}: {b['id']} ({len(reqs)} requests; worst case ${w:.3f}; spend so far ${ledger()['usd']:.3f})")

def status(tag):
    st = json.load(open(f"{OUT}/llm/batch_{tag}.json")); b = call("GET", f"/messages/batches/{st['id']}")
    return b.get("processing_status"), b.get("request_counts")

def fetch(tag):
    st = json.load(open(f"{OUT}/llm/batch_{tag}.json"))
    if st.get("fetched"): print("already fetched"); return [json.loads(l) for l in open(f"{OUT}/llm/answers_{tag}.jsonl")]
    b = call("GET", f"/messages/batches/{st['id']}")
    if b.get("processing_status") != "ended": print("not ended", b.get("request_counts")); return None
    items = []; tin = tout = 0
    for l in call("GET", b["results_url"], raw=True).decode().splitlines():
        r = json.loads(l); res = r.get("result", {})
        if res.get("type") != "succeeded": continue
        m = res["message"]; u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
        txt = "".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
        items.append({"id": r["custom_id"], "answer": parse(txt), "raw": txt[:20000], "stop": m.get("stop_reason")})
    with open(f"{OUT}/llm/answers_{tag}.jsonl", "w") as f:
        for it in items: f.write(json.dumps(it) + "\n")
    usd = add_spend(tag, tin, tout, True)
    st["fetched"] = True; json.dump(st, open(f"{OUT}/llm/batch_{tag}.json", "w"))
    print(f"{tag}: {len(items)} answers ({sum(1 for i in items if i['answer'])} parsed); in {tin} out {tout} tokens; ${usd:.3f}; total spend ${ledger()['usd']:.3f}")
    return items

def sync(tag, reqs, threads=4):
    from concurrent.futures import ThreadPoolExecutor
    check_cap(reqs, False)
    def one(q):
        m = call("POST", "/messages", q["params"]); u = m.get("usage", {})
        txt = "".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
        return {"id": q["custom_id"], "answer": parse(txt), "raw": txt[:20000], "stop": m.get("stop_reason")}, u.get("input_tokens", 0), u.get("output_tokens", 0)
    items = []; tin = tout = 0
    with ThreadPoolExecutor(threads) as ex:
        for it, a, b in ex.map(one, reqs): items.append(it); tin += a; tout += b
    with open(f"{OUT}/llm/answers_{tag}.jsonl", "w") as f:
        for it in items: f.write(json.dumps(it) + "\n")
    usd = add_spend(tag + "_sync", tin, tout, False)
    print(f"{tag}: {len(items)} answers (sync); ${usd:.3f}; total spend ${ledger()['usd']:.3f}")
    return items
