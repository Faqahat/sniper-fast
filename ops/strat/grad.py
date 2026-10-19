# Graduation study (READ-ONLY): pump.fun migrations -> PumpSwap pool price at fixed delays after migration.
import sys, json, os, bisect, threading, time, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/strat")
from srpc import rpc, stats
from pev import events
MIG = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
MA = "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"
WSOL = "So11111111111111111111111111111111111111112"
LOW = int(sys.argv[1]) if len(sys.argv) > 1 else 458250000
DEL = [2, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]
OUT = "/root/strat/grad.jsonl"
def page_all(addr, low):
    out = []; before = None
    while True:
        prm = {"limit": 1000}
        if before: prm["before"] = before
        r = rpc("getSignaturesForAddress", [addr, prm])
        if not isinstance(r, list) or not r: break
        out += r; before = r[-1]["signature"]
        if r[-1]["slot"] < low or len(r) < 1000: break
    return out
if not os.path.exists("/root/strat/grad_anchors.json"):
    a = page_all(MA, LOW - 20000)
    json.dump([[x["slot"], x["signature"]] for x in reversed(a)], open("/root/strat/grad_anchors.json", "w"))
anc = json.load(open("/root/strat/grad_anchors.json")); aslots = [x[0] for x in anc]
migs = page_all(MIG, LOW)
migs = [m for m in reversed(migs) if m.get("err") is None and m["slot"] >= LOW]
print("anchors", len(anc), "ok migration txs", len(migs), flush=True)
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["sig"])
        except Exception: pass
out = open(OUT, "a"); lk = threading.Lock(); cnt = collections.Counter(); seen_mint = set()
def gtx(sig): return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
def pool_state(t, pool):
    sol = tok = None; mint = None
    for b in (t.get("meta") or {}).get("postTokenBalances") or []:
        if b.get("owner") != pool: continue
        if b.get("mint") == WSOL: sol = int(b["uiTokenAmount"]["amount"])
        else: tok = int(b["uiTokenAmount"]["amount"]); mint = b.get("mint")
    return sol, tok, mint
def work(m):
    try: work2(m)
    except Exception as ex:
        with lk: cnt["exc"] += 1; print("EXC", ex, flush=True)
def work2(m):
    t = gtx(m["signature"])
    if not isinstance(t, dict) or "meta" not in t: cnt["txerr"] += 1; return
    logs = t["meta"].get("logMessages") or []
    if not any("Migrate" in l for l in logs): cnt["notmig"] += 1; return
    # pool = owner holding both WSOL and a non-WSOL token with ~206.9M tokens
    own = collections.defaultdict(dict)
    for b in t["meta"].get("postTokenBalances") or []:
        own[b.get("owner")][b.get("mint")] = int(b["uiTokenAmount"]["amount"])
    pool = None
    for o, d in own.items():
        if WSOL in d and len(d) == 2: pool = o
    if not pool: cnt["nopool"] += 1; return
    sol0, tok0, mint = pool_state(t, pool)
    with lk:
        if mint in seen_mint: cnt["dup"] += 1; return
        seen_mint.add(mint)
    rec = {"sig": m["signature"], "slot": m["slot"], "bt": m.get("blockTime"), "mint": mint, "pool": pool, "sol0": sol0, "tok0": tok0, "nlogs": len(logs)}
    tr, _ = events(logs)
    rec["tr_in_mig"] = len(tr)
    # pre-migration activity on the mint
    r = rpc("getSignaturesForAddress", [mint, {"limit": 1000, "before": m["signature"]}])
    if isinstance(r, list):
        rec["pre_n"] = len(r); rec["pre_span_s"] = (m.get("blockTime") or 0) - (r[-1].get("blockTime") or 0) if r else None
        rec["pre_n60"] = sum(1 for x in r if (m.get("blockTime") or 0) - (x.get("blockTime") or 0) <= 60)
        rec["pre_n300"] = sum(1 for x in r if (m.get("blockTime") or 0) - (x.get("blockTime") or 0) <= 300)
    pts = []
    if sol0 and sol0 >= 40e9:
        for dsec in DEL:
            target = m["slot"] + int(dsec / 0.2165)
            i = bisect.bisect_left(aslots, target)
            if i >= len(anc): pts.append([dsec, None]); continue
            s = rpc("getSignaturesForAddress", [pool, {"limit": 1, "before": anc[i][1]}])
            if not isinstance(s, list) or not s: pts.append([dsec, None]); continue
            s = s[0]
            if s["slot"] < m["slot"]: pts.append([dsec, None]); continue
            if pts and pts[-1][1] and pts[-1][1][0] == s["signature"]:
                pts.append([dsec, pts[-1][1]]); continue
            x = gtx(s["signature"])
            if not isinstance(x, dict) or "meta" not in x: pts.append([dsec, None]); continue
            so, to, _ = pool_state(x, pool)
            pts.append([dsec, [s["signature"], s["slot"] - m["slot"], so, to]])
    rec["pts"] = pts
    with lk:
        out.write(json.dumps(rec) + "\n"); out.flush(); cnt["done"] += 1
todo = [m for m in migs if m["signature"] not in done]
with ThreadPoolExecutor(4) as ex:
    futs = [ex.submit(work, m) for m in todo]
    for k, f in enumerate(futs):
        f.result()
        if k % 100 == 0: print(time.strftime("%H:%M:%S"), k, len(todo), dict(cnt), stats, flush=True)
print("FINISHED", dict(cnt), stats, flush=True)
