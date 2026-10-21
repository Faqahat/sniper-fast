# READ-ONLY (host; public RPC): full trade tape of each selected launch for slots S..S+NS (getSignaturesForAddress on the
# mint, paged back to S, then getTransaction for every successful sig with slot <= S+NS) -> <out_dir>/<mint>.tape.json
# rows: slot, sig, events (pump TradeEvents: user, buy, sol, tok, vsol, vtok), fee payer. Order inside a slot is the
# signature list's (reverse) order, which is not exact; the S..S+2 recording (exact block order) is used for those slots.
# usage: python3 -I tapes.py <launches.json> <out_dir> [sel]   sel = r2 | r2nc (default r2nc)   env NS=60 THREADS=3
import sys, os, json, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import txs_multi as X

LJ, OUT = sys.argv[1], sys.argv[2]; SEL = sys.argv[3] if len(sys.argv) > 3 else "r2nc"
NS = int(os.environ.get("NS", "60")); TH = int(os.environ.get("THREADS", "3")); SKIP = int(os.environ.get("SKIP", "2"))
L = [l for l in json.load(open(LJ)) if l.get(SEL)]
L.sort(key=lambda l: -l["S"])
print("launches", len(L), flush=True)


def one(l):
    fn = os.path.join(OUT, l["mint"] + ".tape.json")
    if os.path.exists(fn): return "cached"
    S = l["S"]; sigs = []; before = None
    for _ in range(int(os.environ.get("MAXPAGES", "30"))):
        p = {"limit": 1000}
        if before: p["before"] = before
        res = X.rpc("getSignaturesForAddress", [l["mint"], p])
        if res in (None, "ERR") or not res: break
        sigs += res; before = res[-1]["signature"]
        if res[-1]["slot"] < S or len(res) < 1000: break
    reached = bool(sigs) and sigs[-1]["slot"] <= S
    if not reached:
        json.dump(dict(mint=l["mint"], S=S, ns=NS, nsig_all=len(sigs), nsig_win=0, rows=[], capped=True), open(fn, "w"))
        return "capped"
    win = [s for s in sigs if S + SKIP < s["slot"] <= S + NS and s.get("err") is None]   # S..S+SKIP come from the exact-order recording
    rows = []; nmiss = [0]
    for s in win:
        t = X.rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if t in (None, "ERR"): nmiss[0] += 1; continue
        ev = X.trades((t.get("meta") or {}).get("logMessages"))
        ev = [e for e in ev if e["mint"] == l["mint"]]
        if ev: rows.append(dict(slot=t["slot"], sig=s["signature"], payer=t["transaction"]["message"]["accountKeys"][0], ev=ev, fee=(t.get("meta") or {}).get("fee")))
    json.dump(dict(mint=l["mint"], S=S, ns=NS, nsig_all=len(sigs), nsig_win=len(win), rows=rows, nmiss=nmiss[0]), open(fn, "w"))
    return f"{len(rows)}"


n = [0]; lk = threading.Lock()


def job(l):
    try: r = one(l)
    except Exception as e: r = "EXC " + str(e)[:80]
    with lk:
        n[0] += 1
        if n[0] % 20 == 0: print(n[0], time.strftime("%H:%M:%S"), r, flush=True)
    return r


with ThreadPoolExecutor(TH) as ex:
    res = list(ex.map(job, L))
print("DONE", len(res), "exc", sum(str(r).startswith("EXC") for r in res), flush=True)
