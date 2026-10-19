# Late-entry extension (READ-ONLY): for launches still active near 10 min, sigs to 30 min, checkpoints 300..1200 s, paths.
import sys, json, os, bisect, threading, time, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/strat")
from srpc import rpc, stats
from pev import events
W0 = 2780; W = 8330
CK = [1386, 1940, 2771, 4157, 5543]   # 300, 420, 600, 900, 1200 s
HOLD = 2771                           # 600 s
OUT = "/root/strat/ext.jsonl"
SCR_V = 36e9
anc = []
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l); anc.append((x["slot"], x["signature"]))
for l in open("/root/det/truth_run.jsonl"):
    x = json.loads(l)
    if x.get("sig") and x.get("slot"): anc.append((x["slot"], x["sig"]))
for l in open("/root/strat/anchors.jsonl"):
    x = json.loads(l); anc.append((x[0], x[1]))
anc.sort(); aslots = [a[0] for a in anc]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
tg = []
for l in open("/root/strat/pipe.jsonl"):
    x = json.loads(l)
    if x["mint"] in done or x.get("nonsol") or x.get("stage", 0) < 3: continue
    a1 = sum(k for d, k in x["act"] if 1246 <= d <= 1386)
    a2 = sum(k for d, k in x["act"] if 1800 <= d <= 1940)
    late = sum(k for d, k in x["act"] if d >= 2300)
    if a1 >= 3 or a2 >= 3 or late >= 3:
        tg.append(x)
print("todo", len(tg), flush=True)
out = open(OUT, "a"); lk = threading.Lock(); cnt = collections.Counter()
def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
def work(x):
    try: work2(x)
    except Exception as ex:
        with lk: cnt["exc"] += 1; print("EXC", x["mint"], ex, flush=True)
def work2(x):
    mint, S = x["mint"], x["slot"]
    i = bisect.bisect_left(aslots, S + W + 2)
    if i >= len(anc):
        with lk: cnt["noanchor"] += 1
        return
    before = anc[i][1]; sigs = []; pages = 0; err = None
    while True:
        r = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "before": before}])
        pages += 1
        if not isinstance(r, list): err = str(r)[:100]; break
        sigs += r
        if len(r) < 1000 or r[-1]["slot"] <= S + 1300 or pages >= 30: break
        before = r[-1]["signature"]
    sg = [[s["slot"] - S, 1 if s.get("err") is not None else 0, s["signature"]] for s in reversed(sigs) if S + 1300 < s["slot"] <= S + W]
    ok = [s for s in sg if not s[1]]
    okd = [s[0] for s in ok]
    rec = {"mint": mint, "slot": S, "bt": x["bt"], "src": x["src"], "pages": pages, "trunc": pages >= 30, "mayhem": x.get("mayhem")}
    if err: rec["sig_err"] = err
    rec["act2"] = sorted(collections.Counter(okd).items())
    # all ok tx slot offsets over [0, W]
    old_ok = [(d, None) for d, n in x["act"] for _ in range(n)]
    fetched = {}
    def fetch_last_le(d):
        j = bisect.bisect_right(okd, d) - 1
        if j < 0: return None
        s = ok[j]
        if s[2] not in fetched:
            t = gtx(s[2])
            if isinstance(t, dict) and "meta" in t:
                tr, _ = events((t.get("meta") or {}).get("logMessages"))
                ev = [[e["buy"], e["sol"], e["tok"], e["user"][:10], e["vsol"], e["vtok"], e["fbps"], e["cbps"]] for e in tr if e["mint"] == mint]
                fetched[s[2]] = [s[0], ev, t.get("blockTime")]
            else:
                fetched[s[2]] = [s[0], None, None]
        return fetched[s[2]]
    # state at 10 min boundary from old rows (if any) else fetch from new list later
    last_old = [r for r in (x.get("rows") or []) if r[1]]
    cks = []; passed = []
    for d in CK:
        r = fetch_last_le(d)
        v = r[1][-1][4] if r and r[1] else None
        if r is None and last_old:
            v = None
        cks.append([d, v])
        if v and v >= SCR_V: passed.append(d)
    rec["cks"] = cks; rec["passed"] = passed
    if passed:
        lo = passed[0]; hi = min(W, passed[-1] + HOLD)
        bnd = set()
        for p in passed: bnd.add(p + 1); bnd.add(p + 2)
        d = lo + 2
        while d < hi:
            d += 23; bnd.add(d)
        bnd.add(hi)
        prev = lo
        for b in sorted(bb for bb in bnd if lo < bb <= hi):
            j = bisect.bisect_right(okd, b) - 1
            if j >= 0 and ok[j][0] > prev: fetch_last_le(b)
            prev = b
    rec["rows"] = sorted(fetched.values(), key=lambda r: r[0])
    with lk:
        out.write(json.dumps(rec) + "\n"); out.flush(); cnt["done"] += 1; cnt["tx"] += len(fetched); cnt["passed"] += 1 if passed else 0
with ThreadPoolExecutor(4) as ex:
    futs = [ex.submit(work, t) for t in tg]
    for k, f in enumerate(futs):
        f.result()
        if k % 50 == 0: print(time.strftime("%H:%M:%S"), k, dict(cnt), stats, flush=True)
print("FINISHED", dict(cnt), stats, flush=True)
