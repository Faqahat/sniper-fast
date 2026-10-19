# Phase 2: bucketed curve-state path over [S, S+W] for active launches + create tx + dev txs. READ-ONLY.
import sys, json, os, bisect, threading, time, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/strat")
from srpc import rpc, stats
from pev import events
INP = sys.argv[1] if len(sys.argv) > 1 else "/root/strat/sigs.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/root/strat/paths.jsonl"
MIN_OK = int(os.environ.get("MIN_OK", "8"))
W = 2780
def bucket(d):
    if d <= 10: return d
    if d <= 140: return 10 + (d - 11) // 2 * 2 + 2   # bucket end
    if d <= 560: return 140 + (d - 141) // 5 * 5 + 5
    return 560 + (d - 561) // 14 * 14 + 14
anc = []
for l in open("/root/nob/csigs.jsonl"):
    x = json.loads(l); anc.append((x["slot"], x["signature"]))
for l in open("/root/det/truth_run.jsonl"):
    x = json.loads(l)
    if x.get("sig") and x.get("slot"): anc.append((x["slot"], x["sig"]))
if os.path.exists("/root/strat/anchors.jsonl"):
    for l in open("/root/strat/anchors.jsonl"):
        x = json.loads(l); anc.append((x[0], x[1]))
anc.sort(); aslots = [a[0] for a in anc]
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["mint"])
        except Exception: pass
tg = []
for l in open(INP):
    x = json.loads(l)
    if x["mint"] in done or x.get("sig_err"): continue
    ok = [s for s in x["sigs"] if not s[1]]
    if len(ok) >= MIN_OK:
        tg.append(x)
print("todo", len(tg), flush=True)
out = open(OUT, "a"); lk = threading.Lock(); cnt = collections.Counter()
def gtx(sig):
    return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
def work(x):
    mint, S = x["mint"], x["slot"]
    ok = [s for s in x["sigs"] if not s[1]]
    rec = {k: x[k] for k in ("mint", "slot", "bt", "src") if k in x}
    for k in ("dev_sol", "creator", "mayhem"):
        if k in x: rec[k] = x[k]
    act = collections.Counter(s[0] for s in ok)
    rec["act"] = sorted(act.items())
    rec["err_act"] = sorted(collections.Counter(s[0] for s in x["sigs"] if s[1]).items())
    # create tx = earliest ok sig in slot 0
    c = ok[0]
    tx = gtx(c[2])
    if not isinstance(tx, dict) or "meta" not in tx:
        rec["create_err"] = 1
    else:
        tr, cr = events((tx.get("meta") or {}).get("logMessages"))
        ev = [e for e in tr if e["mint"] == mint]
        rec["create"] = cr[0] if cr else None
        rec["cev"] = [[e["buy"], e["sol"], e["tok"], e["user"][:10], e["vsol"], e["vtok"], e["fbps"], e["cbps"]] for e in ev]
        rec["c_d"] = c[0]
        if ev and ev[-1]["vsol"] < 25e9:
            rec["nonsol"] = 1
    if rec.get("nonsol"):
        with lk:
            out.write(json.dumps(rec) + "\n"); out.flush(); cnt["nonsol"] += 1
        return
    last = {}
    for s in ok[1:]:
        last[bucket(s[0])] = s
    rows = []
    for b in sorted(last):
        s = last[b]
        tx = gtx(s[2])
        if not isinstance(tx, dict) or "meta" not in tx:
            rows.append([s[0], None]); continue
        tr, _ = events((tx.get("meta") or {}).get("logMessages"))
        ev = [[e["buy"], e["sol"], e["tok"], e["user"][:10], e["vsol"], e["vtok"], e["fbps"], e["cbps"]] for e in tr if e["mint"] == mint]
        rows.append([s[0], ev, tx.get("blockTime")])
    rec["rows"] = rows
    # dev txs on this mint
    cre = (rec.get("create") or {}).get("user") or x.get("creator")
    if cre:
        i = bisect.bisect_left(aslots, S + W + 2)
        prm = {"limit": 1000}
        if i < len(anc): prm["before"] = anc[i][1]
        r = rpc("getSignaturesForAddress", [cre, prm])
        if isinstance(r, list):
            mys = {s[2]: s[0] for s in x["sigs"]}
            rec["dev_txs"] = sorted(mys[y["signature"]] for y in r if y["signature"] in mys)
            rec["dev_nsig"] = len(r)
            rec["dev_oldest_d"] = (r[-1]["slot"] - S) if r else None
    with lk:
        out.write(json.dumps(rec) + "\n"); out.flush()
        cnt["done"] += 1; cnt["tx"] += len(rows)
        if cnt["done"] % 50 == 0:
            print(time.strftime("%H:%M:%S"), dict(cnt), "/", len(tg), stats, flush=True)
with ThreadPoolExecutor(4) as ex:
    list(ex.map(work, tg))
print("FINISHED", dict(cnt), stats, flush=True)
