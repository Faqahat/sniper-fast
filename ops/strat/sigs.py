# Phase 1: per launch, all signatures in [S, S+W] slots. READ-ONLY.
import sys, json, os, bisect, random, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/strat")
from srpc import rpc, stats
W = 2780  # ~600 s
OUT = "/root/strat/sigs.jsonl"
anc = []
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l); anc.append((x["slot"], x["signature"]))
tg = []
for l in open("/root/nob/ds.jsonl"):
    x = json.loads(l)
    if x.get("in_rand") and not x.get("quote") and x["slot"] >= 457780000:
        tg.append({"mint": x["mint"], "slot": x["slot"], "bt": x["bt"], "src": "ds", "dev_sol": x.get("dev_sol")})
for l in open("/root/det/truth_run.jsonl"):
    x = json.loads(l)
    if x.get("sig") and x.get("slot"):
        anc.append((x["slot"], x["sig"]))
    if x.get("err") or not x.get("mint") or not x.get("kind"):
        continue
    a = x.get("args") or {}
    tg.append({"mint": x["mint"], "slot": x["slot"], "bt": x["bt"], "src": "truth", "creator": a.get("creator"), "csig": x["sig"], "mayhem": a.get("mayhem")})
anc.sort(); aslots = [a[0] for a in anc]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
tg = [t for t in tg if t["mint"] not in done]
random.seed(7); random.shuffle(tg)
print("todo", len(tg), flush=True)
out = open(OUT, "a"); lk = threading.Lock(); n = [0]
def work(t):
    S = t["slot"]
    i = bisect.bisect_left(aslots, S + W + 2)
    before = anc[i][1] if i < len(anc) else None
    sigs = []; pages = 0; err = None
    while True:
        prm = {"limit": 1000}
        if before: prm["before"] = before
        r = rpc("getSignaturesForAddress", [t["mint"], prm])
        pages += 1
        if not isinstance(r, list):
            err = str(r)[:100]; break
        sigs += r
        if len(r) < 1000 or r[-1]["slot"] < S or pages >= 40:
            break
        before = r[-1]["signature"]
    sigs = [x for x in reversed(sigs) if S <= x["slot"] <= S + W]
    rec = dict(t)
    rec["pages"] = pages
    if err: rec["sig_err"] = err
    rec["sigs"] = [[x["slot"] - S, 1 if x.get("err") is not None else 0, x["signature"], x.get("blockTime")] for x in sigs]
    with lk:
        out.write(json.dumps(rec) + "\n"); out.flush(); n[0] += 1
        if n[0] % 250 == 0: print(time.strftime("%H:%M:%S"), n[0], stats, flush=True)
with ThreadPoolExecutor(4) as ex:
    list(ex.map(work, tg))
print("FINISHED", n[0], stats, flush=True)
