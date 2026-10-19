# Combined per-launch pipeline (READ-ONLY): sigs [S,S+W] -> create tx -> checkpoint states -> path if screened.
import sys, json, os, bisect, random, threading, time, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/strat")
from srpc import rpc, stats
from pev import events
W = 2780
CK = [69, 139, 277, 416, 554, 831, 1109]   # 15,30,60,90,120,180,240 s
HOLD = 1389                                 # 300 s
MIN_OK = 10
SCR_V = float(os.environ.get("SCR_V", "36")) * 1e9
OUT = "/root/strat/pipe.jsonl"
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
    if x.get("sig") and x.get("slot"): anc.append((x["slot"], x["sig"]))
    if x.get("err") or not x.get("mint") or not x.get("kind"): continue
    a = x.get("args") or {}
    tg.append({"mint": x["mint"], "slot": x["slot"], "bt": x["bt"], "src": "truth", "creator": a.get("creator"), "mayhem": a.get("mayhem")})
anc.sort(); aslots = [a[0] for a in anc]
cache = {}
if os.path.exists("/root/strat/sigs.jsonl"):
    for l in open("/root/strat/sigs.jsonl"):
        try:
            x = json.loads(l); cache[x["mint"]] = x
        except Exception: pass
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
tg = [t for t in tg if t["mint"] not in done]
random.seed(11); random.shuffle(tg)
# cached first (cheap), then the rest
tg.sort(key=lambda t: 0 if t["mint"] in cache else 1)
print("todo", len(tg), "cached", sum(1 for t in tg if t["mint"] in cache), flush=True)
out = open(OUT, "a"); lk = threading.Lock(); cnt = collections.Counter()
def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
def evs(tx, mint):
    tr, cr = events((tx.get("meta") or {}).get("logMessages"))
    return [[e["buy"], e["sol"], e["tok"], e["user"][:10], e["vsol"], e["vtok"], e["fbps"], e["cbps"]] for e in tr if e["mint"] == mint], cr
def getsigs(t):
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
        if len(r) < 1000 or r[-1]["slot"] < S or pages >= 40: break
        before = r[-1]["signature"]
    sigs = [x for x in reversed(sigs) if S <= x["slot"] <= S + W]
    return [[x["slot"] - S, 1 if x.get("err") is not None else 0, x["signature"], x.get("blockTime")] for x in sigs], pages, err
def work(t):
    try:
        work2(t)
    except Exception as ex:
        with lk: cnt["exc"] += 1; print("EXC", t["mint"], ex, flush=True)
def work2(t):
    mint, S = t["mint"], t["slot"]
    if mint in cache:
        sg = cache[mint]["sigs"]; pages = cache[mint]["pages"]; err = cache[mint].get("sig_err")
    else:
        sg, pages, err = getsigs(t)
    rec = dict(t); rec["pages"] = pages
    if err: rec["sig_err"] = err
    ok = [s for s in sg if not s[1]]
    rec["act"] = sorted(collections.Counter(s[0] for s in ok).items())
    rec["err_act"] = sorted(collections.Counter(s[0] for s in sg if s[1]).items())
    rec["n_ok"] = len(ok)
    okd = [s[0] for s in ok]
    def n_upto(d): return bisect.bisect_right(okd, d)
    if err or not ok or n_upto(CK[-1]) < MIN_OK:
        rec["stage"] = 1
        with lk:
            out.write(json.dumps(rec) + "\n"); out.flush(); cnt["s1"] += 1
        return
    tx = gtx(ok[0][2])
    if not isinstance(tx, dict) or "meta" not in tx:
        rec["create_err"] = 1; rec["stage"] = 2
        with lk: out.write(json.dumps(rec) + "\n"); out.flush(); cnt["cerr"] += 1
        return
    ev, cr = evs(tx, mint)
    rec["create"] = cr[0] if cr else None; rec["cev"] = ev; rec["c_d"] = ok[0][0]
    if not ev or ev[-1][4] < 25e9:
        rec["nonsol"] = 1; rec["stage"] = 2
        with lk: out.write(json.dumps(rec) + "\n"); out.flush(); cnt["nonsol"] += 1
        return
    v0 = ev[-1][4]
    fetched = {}   # sig -> row
    def state_at(d):
        i = bisect.bisect_right(okd, d) - 1
        if i < 0: return None
        s = ok[i]
        if s[2] not in fetched:
            if i == 0:
                fetched[s[2]] = [s[0], ev, tx.get("blockTime")]
            else:
                x = gtx(s[2])
                if isinstance(x, dict) and "meta" in x:
                    e2, _ = evs(x, mint); fetched[s[2]] = [s[0], e2, x.get("blockTime")]
                else:
                    fetched[s[2]] = [s[0], None, None]
        return fetched[s[2]]
    cks = []; passed = []
    for d in CK:
        if n_upto(d) < MIN_OK:
            cks.append([d, None]); continue
        r = state_at(d)
        # carry back to last row with an event
        v = None
        i = bisect.bisect_right(okd, d) - 1
        while i >= 0:
            rr = fetched.get(ok[i][2])
            if rr is None:
                rr = state_at(ok[i][0]) if False else None
            if rr and rr[1]:
                v = rr[1][-1][4]; break
            if rr is None: break
            i -= 1
        cks.append([d, v, r[0] if r else None])
        if v and v >= SCR_V and v >= v0 + 2e9:
            passed.append(d)
    rec["v0"] = v0; rec["cks"] = cks; rec["passed"] = passed
    rec["stage"] = 3
    if passed:
        lo = passed[0]; hi = min(W, passed[-1] + HOLD)
        bnd = set()
        for p in passed:
            bnd.add(p + 1); bnd.add(p + 2)
        d = lo + 2
        while d < min(hi, lo + 132):
            d += 5; bnd.add(d)
        while d < hi:
            d += 14; bnd.add(d)
        bnd.add(hi)
        bnd = sorted(b for b in bnd if lo < b <= hi)
        prev = lo
        for b in bnd:
            i = bisect.bisect_right(okd, b) - 1
            if i >= 0 and ok[i][0] > prev:
                state_at(b)
            prev = b
        rec["path_lo"] = lo; rec["path_hi"] = hi
        cre = (rec.get("create") or {}).get("user") or t.get("creator")
        if cre:
            i = bisect.bisect_left(aslots, S + W + 2)
            prm = {"limit": 1000}
            if i < len(anc): prm["before"] = anc[i][1]
            r = rpc("getSignaturesForAddress", [cre, prm])
            if isinstance(r, list):
                mys = {s[2]: s[0] for s in sg}
                rec["dev_txs"] = sorted(mys[y["signature"]] for y in r if y["signature"] in mys)
                rec["dev_nsig"] = len(r)
                rec["dev_oldest_d"] = (r[-1]["slot"] - S) if r else None
        rec["stage"] = 4
    rec["rows"] = sorted(fetched.values(), key=lambda r: r[0])
    with lk:
        out.write(json.dumps(rec) + "\n"); out.flush()
        cnt["s%d" % rec["stage"]] += 1; cnt["tx"] += len(fetched)
        if sum(cnt.values()) % 100 < 2:
            pass
with ThreadPoolExecutor(4) as ex:
    futs = [ex.submit(work, t) for t in tg]
    k = 0
    for f in futs:
        f.result(); k += 1
        if k % 200 == 0:
            print(time.strftime("%H:%M:%S"), k, dict(cnt), stats, flush=True)
print("FINISHED", dict(cnt), stats, flush=True)
