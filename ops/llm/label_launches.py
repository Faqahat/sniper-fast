#!/usr/bin/env python3
# Label every recorded pump.fun launch with an LLM (owner 10-24 19:30 PKT: use the expiring Anthropic credit). The model sees only
# what a launch shows at create time: name, symbol, and (for ~43% of launches) the metadata JSON (description, X link, website,
# telegram). It returns short labels per token; a later study tests whether they predict anything (dip-bot attention, bounces,
# the top sniper's picks). No trading, no server touched. The API key is read from ~/.config/sniper/anthropic_key, never printed.
#
#   python3 label_launches.py prep   RUN_DIR [RUN_DIR ...]   -> WORK/requests.jsonl (+ items.jsonl), token/cost estimate
#   python3 label_launches.py sample [N_REQUESTS]           -> N requests sent one by one (normal API), labels + real usage
#   python3 label_launches.py submit [--max-usd X]          -> Message Batches API (half price), batch ids saved
#   python3 label_launches.py status | fetch                -> poll; download results -> WORK/labels.jsonl + usage totals
import json, os, re, sys, time, urllib.request, urllib.error
WORK = os.environ.get("LLM_WORK", "/home/moiz/sniper-data/llm/launch_labels")
MODEL = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
PER = int(os.environ.get("LLM_PER", "25"))                     # launches per request
PRICE = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}  # $/MTok in, out (normal API; batch = half)
API = "https://api.anthropic.com/v1"
SYSTEM = """You label new pump.fun meme-coin launches. For each launch you get its id (i), name (n), symbol (s) and, when available,
description (d), X/Twitter link (x), website (w) and telegram (tg). Judge only from this text. Reply with ONLY a JSON array, one
object per launch, same order, with exactly these keys:
 "i": the id you were given
 "th": theme, one of: animal, character_meme, person_celebrity, politics, ai_tech, crypto_finance, news_event, sports, food,
       brand_product, nsfw_vulgar, gibberish_random, other
 "rw": 1 if it rides a specific real-world person, brand, event or viral post happening now, else 0
 "who": that person/brand/event in at most 4 words, or ""
 "eff": listing effort 0-3 (0 = random letters/test, 1 = bare name, 2 = coherent name + some text/link, 3 = full story + links)
 "cpy": 1 if it copies or rides another known coin/ticker or a trending meme (e.g. "PEPE2", "Trump 2.0"), else 0
 "fun": meme appeal 0-3 (how likely degens find it funny / shareable)
 "x": X link type: "post" (links one tweet), "profile", "community", "none"
 "lang": main language code (en, zh, es, ...), "" if none
 "red": 1 if obvious red flags (impersonating an official project, "guaranteed" gains, drain/claim bait), else 0
No prose, no markdown, no code fences."""

def key():
    return open(os.path.expanduser("~/.config/sniper/anthropic_key")).read().strip()

def call(method, path, body=None, raw=False):
    h = {"x-api-key": key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    for k in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + path if path.startswith("/") else path, data=data, headers=h, method=method), timeout=120)
            b = r.read()
            return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 529) and k < 5: time.sleep(3 * (k + 1)); continue
            raise SystemExit(f"API error {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError) as e:
            if k < 5: time.sleep(3 * (k + 1)); continue
            raise

def short_link(u, keep=60):
    if not u or not isinstance(u, str): return ""
    u = re.sub(r"^https?://(www\.)?", "", u.strip()); u = re.sub(r"[?#].*$", "", u)
    return u[:keep]

def items_from(run_dir):
    meta = {}
    p = os.path.join(run_dir, "enrich.jsonl")
    if os.path.exists(p):
        for l in open(p):
            try: e = json.loads(l)
            except ValueError: continue
            j = (e.get("meta") or {}).get("json")
            if isinstance(j, dict): meta[e["mint"]] = j
    for l in open(os.path.join(run_dir, "launches.jsonl")):
        try: L = json.loads(l)
        except ValueError: continue
        if L.get("err"): continue
        j = meta.get(L["mint"], {})
        it = {"n": (L.get("name") or "")[:60], "s": (L.get("symbol") or "")[:20]}
        d = (j.get("description") or "").strip().replace("\n", " ")
        if d: it["d"] = d[:240]
        for k, kk in (("twitter", "x"), ("website", "w")):
            v = short_link(j.get(k))
            if v: it[kk] = v
        if j.get("telegram"): it["tg"] = 1
        yield L["mint"], L.get("bt"), it

def prep(dirs):
    os.makedirs(WORK, exist_ok=True)
    seen = set(); items = []
    for d in dirs:
        for m, bt, it in items_from(d):
            if m in seen: continue
            seen.add(m); items.append((m, bt, it))
    with open(f"{WORK}/items.jsonl", "w") as f:
        for i, (m, bt, it) in enumerate(items): f.write(json.dumps({"i": i, "mint": m, "bt": bt, **it}) + "\n")
    nreq = 0; chars = 0
    with open(f"{WORK}/requests.jsonl", "w") as f:
        for k in range(0, len(items), PER):
            chunk = [{"i": i, **it} for i, (_, _, it) in enumerate(items[k:k + PER], start=k)]
            user = "\n".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in chunk)
            req = {"custom_id": f"r{k // PER:06d}", "params": {"model": MODEL, "max_tokens": 8000,
                   "system": SYSTEM, "messages": [{"role": "user", "content": user}]}}
            f.write(json.dumps(req, ensure_ascii=False) + "\n"); nreq += 1; chars += len(SYSTEM) + len(user)
    tin = chars / 3.5; tout = len(items) * 160; pi, po = PRICE.get(MODEL, (0, 0))
    with_meta = sum(1 for _, _, it in items if len(it) > 2)
    print(f"{len(items)} launches ({with_meta} with metadata) -> {nreq} requests of {PER}; est. {tin / 1e6:.1f}M input + {tout / 1e6:.1f}M output tokens"
          f" = ${(tin * pi + tout * po) / 1e6:.2f} normal, ${(tin * pi + tout * po) / 2e6:.2f} batch ({MODEL})")

def parse(text):
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < a: return []
    try: v = json.loads(text[a:b + 1])
    except ValueError: return []
    return [o for o in v if isinstance(o, dict) and "i" in o]

def sample(n):
    reqs = [json.loads(l) for _, l in zip(range(n), open(f"{WORK}/requests.jsonl"))]
    tin = tout = 0; got = 0; want = 0; out = []
    for r in reqs:
        t0 = time.time(); m = call("POST", "/messages", r["params"]); dt = time.time() - t0
        u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
        labs = parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"))
        want += r["params"]["messages"][0]["content"].count("\n") + 1; got += len(labs); out += labs
        print(f"  {r['custom_id']}: {len(labs)} labels, {u.get('input_tokens')} in / {u.get('output_tokens')} out tokens, {dt:.1f} s, stop={m.get('stop_reason')}")
    pi, po = PRICE.get(MODEL, (0, 0)); total = sum(1 for _ in open(f"{WORK}/requests.jsonl"))
    print(f"sample: {got}/{want} labels parsed; {tin} in + {tout} out tokens = ${(tin * pi + tout * po) / 1e6:.4f}"
          f" -> all {total} requests ≈ ${(tin * pi + tout * po) / 1e6 * total / max(1, len(reqs)):.2f} normal, half in batch")
    items = {json.loads(l)["i"]: json.loads(l) for _, l in zip(range(PER * n), open(f"{WORK}/items.jsonl"))}
    for o in out[:12]:
        it = items.get(o["i"], {}); print("   ", json.dumps({k: it.get(k) for k in ("n", "s", "d", "x") if it.get(k)}, ensure_ascii=False)[:110], "->", json.dumps({k: v for k, v in o.items() if k != "i"}, ensure_ascii=False))
    json.dump(out, open(f"{WORK}/sample_labels.json", "w"), ensure_ascii=False)

def submit(max_usd):
    reqs = [json.loads(l) for l in open(f"{WORK}/requests.jsonl")]
    pi, po = PRICE.get(MODEL, (0, 0)); chars = sum(len(r["params"]["system"]) + len(r["params"]["messages"][0]["content"]) for r in reqs)
    est = (chars / 3.5 * pi + PER * len(reqs) * 160 * po) / 2e6
    if est > max_usd: raise SystemExit(f"estimated ${est:.2f} > --max-usd {max_usd}; not submitted")
    ids = []
    for k in range(0, len(reqs), 20000):                                   # stay well under the 256 MB / 100k request limits
        b = call("POST", "/messages/batches", {"requests": reqs[k:k + 20000]}); ids.append(b["id"])
        print(f"  batch {b['id']}: {len(reqs[k:k + 20000])} requests, status {b.get('processing_status')}")
    json.dump({"ids": ids, "model": MODEL, "t": time.time(), "est_usd": est}, open(f"{WORK}/batches.json", "w"))
    print(f"submitted {len(reqs)} requests in {len(ids)} batch(es); estimate ${est:.2f} (batch price)")

def status():
    st = json.load(open(f"{WORK}/batches.json")); done = True
    for i in st["ids"]:
        b = call("GET", f"/messages/batches/{i}"); c = b.get("request_counts", {})
        print(f"  {i}: {b.get('processing_status')} {c}"); done &= b.get("processing_status") == "ended"
    return done

def fetch():
    st = json.load(open(f"{WORK}/batches.json")); items = {}
    for l in open(f"{WORK}/items.jsonl"):
        o = json.loads(l); items[o["i"]] = o["mint"]
    tin = tout = 0; n = bad = 0
    with open(f"{WORK}/labels.jsonl", "w") as f:
        for i in st["ids"]:
            b = call("GET", f"/messages/batches/{i}")
            if b.get("processing_status") != "ended": print(f"  {i} not ended yet"); continue
            for l in call("GET", b["results_url"], raw=True).decode().splitlines():
                r = json.loads(l); res = r.get("result", {})
                if res.get("type") != "succeeded": bad += 1; continue
                m = res["message"]; u = m.get("usage", {}); tin += u.get("input_tokens", 0); tout += u.get("output_tokens", 0)
                for o in parse("".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")):
                    if o.get("i") in items: f.write(json.dumps({"mint": items[o["i"]], **o}, ensure_ascii=False) + "\n"); n += 1
    pi, po = PRICE.get(st["model"], (0, 0))
    print(f"labels {n} / {len(items)} launches; failed requests {bad}; usage {tin} in + {tout} out = ${(tin * pi + tout * po) / 2e6:.2f} at batch price")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__ or "usage: prep|sample|submit|status|fetch")
    if a[0] == "prep": prep(a[1:])
    elif a[0] == "sample": sample(int(a[1]) if len(a) > 1 else 4)
    elif a[0] == "submit": submit(float(a[a.index("--max-usd") + 1]) if "--max-usd" in a else 10.0)
    elif a[0] == "status": status()
    elif a[0] == "fetch": fetch()
