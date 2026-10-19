#!/usr/bin/env python3
# Public HTTP GET of each launch's metadata URI (short timeout, cached). Stores the raw JSON (values truncated).
# usage: meta.py <blk jsonl files...>   -> meta.jsonl
import sys, json, os, threading, time, collections, urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT = "/root/nob/meta.jsonl"
GW = ["https://ipfs.filebase.io/ipfs/", "https://4everland.io/ipfs/", "https://gw.ipfs-lens.dev/ipfs/", "https://gateway.pinata.cloud/ipfs/"]
recs = {}
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l)
        if r.get("missing"):
            continue
        recs[r["mint"]] = r["uri"]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            x = json.loads(l)
            if x.get("status") == "ok":
                done.add(x["mint"])
        except Exception:
            pass
todo = [(m, u) for m, u in recs.items() if m not in done]
print("todo", len(todo), flush=True)
out = open(OUT, "a")
lk = threading.Lock()
cnt = collections.Counter()


def trunc(v, d=0):
    if isinstance(v, str):
        return v[:400]
    if isinstance(v, dict) and d < 2:
        return {str(k)[:40]: trunc(x, d + 1) for k, x in list(v.items())[:30]}
    if isinstance(v, list) and d < 2:
        return [trunc(x, d + 1) for x in v[:10]]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return str(v)[:200]


def fetch(u, to):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=to) as r:
        raw = r.read(200000)
    return json.loads(raw)


def work(item):
    m, uri = item
    rec = {"mint": m, "uri": uri}
    urls = [uri]
    tail = None
    if "/ipfs/" in uri:
        tail = uri.split("/ipfs/", 1)[1]
        urls = []  # public ipfs.io-style gateways rate-limit us (403); use these first
    elif uri.startswith("ipfs://"):
        tail = uri[7:]
        urls = []
    if tail:
        urls += [g + tail for g in GW]
    j, err = None, None
    for rnd in range(3):
        for u in urls[:4]:
            if not u.startswith("http"):
                continue
            try:
                j = fetch(u, 8)
                rec["via"] = u.split("/")[2]
                break
            except Exception as ex:
                err = repr(ex)[:120]
                if "429" in err:
                    time.sleep(1.5 + rnd * 2)
        if j is not None or not tail or "429" not in (err or ""):
            break
    if j is None:
        rec["status"] = "fail"
        rec["err"] = err
    elif not isinstance(j, dict):
        rec["status"] = "notdict"
    else:
        rec["status"] = "ok"
        rec["j"] = trunc(j)
    with lk:
        out.write(json.dumps(rec) + "\n")
        out.flush()
        cnt[rec["status"]] += 1
        if sum(cnt.values()) % 200 == 0:
            print(time.strftime("%H:%M:%S"), dict(cnt), "/", len(todo), flush=True)


with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(work, todo))
print("FINISHED", dict(cnt), flush=True)
