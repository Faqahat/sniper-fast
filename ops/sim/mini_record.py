# READ-ONLY (host; public RPCs): a light recording (record_window.py format, the fields sim_land.py needs) of the FIRED
# launches in engine logs: blocks S..S+K, every trade of the mint with its exact block position. No cache of full blocks.
# usage: python3 mini_record.py <out dir> <engine log> [<engine log> ...]      env: K=3 RPC_URLS=a,b THREADS=3
import sys, os, re, json, time, base64, itertools, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
K = int(os.environ.get("K", "3"))
EPS = os.environ.get("RPC_URLS", "https://solana-rpc.publicnode.com,https://api.mainnet-beta.solana.com").split(",")
_rr = itertools.cycle(range(len(EPS))); _lock = threading.Lock()
VOTE = "Vote111111111111111111111111111111111111111"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def rpc(meth, params, tries=10):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    for i in range(tries):
        with _lock: ep = EPS[next(_rr)]
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(ep, data=data, headers={"content-type": "application/json"}), timeout=90))
            if "error" in r:
                if r["error"].get("code") in (-32007, -32009): return None
                time.sleep(1 + i); continue
            return r.get("result")
        except Exception:
            time.sleep(1 + i)
    return "ERR"


def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n:
        n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + "".join(reversed(out))


def trades(logs, mint):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try: raw = base64.b64decode(l[14:] + "===")
        except Exception: continue
        if raw[:8] != TRADE_DISC or len(raw) < 129: continue
        o = 8; m = b58enc(raw[o:o + 32]); o += 32
        if m != mint: continue
        sol = int.from_bytes(raw[o:o + 8], "little"); o += 8
        tok = int.from_bytes(raw[o:o + 8], "little"); o += 8
        buy = raw[o]; o += 1
        user = b58enc(raw[o:o + 32]); o += 32 + 8
        vsol = int.from_bytes(raw[o:o + 8], "little"); o += 8
        vtok = int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=m, sol=sol, tok=tok, buy=buy, user=user, vsol=vsol, vtok=vtok, fbps=None, cbps=None))
    return out


# SKIPLATE=1: instead of the fired launches, take the ones that passed the race gate but were skipped as created late in
# their slot (GATE-CREATE-MS verdict=skip_late), with their create_ms (to test a later --max-create-ms on paper)
SKIPLATE = os.environ.get("SKIPLATE") == "1"
fires = {}; cms = {}; passed = set()
for fn in sys.argv[2:]:
    for line in open(fn, errors="replace"):
        m = re.search(r"GATE-CREATE-MS slot=(\d+) mint=(\w+) create_ms=([\d.]+) .*verdict=(\w+)", line)
        if m: cms[(int(m.group(1)), m.group(2))] = (float(m.group(3)), m.group(4))
        m = re.search(r"RACE decide slot=(\d+) mint=(\w+) .*bundle_sol=([\d.]+) .*pass=true", line)
        if m: passed.add((int(m.group(1)), m.group(2)))
        m = re.search(r"RACE obs slot=(\d+) mint=(\w+) .* bundle_sol=([\d.]+) fired=(true|false)", line)
        if m and (m.group(4) == "true") != SKIPLATE: fires[(int(m.group(1)), m.group(2))] = (float(m.group(3)), os.path.basename(fn))
if SKIPLATE:
    fires = {k: v for k, v in fires.items() if k in passed and cms.get(k, (0, ""))[1] == "skip_late"}


def one(item):
    (S, mint), (bsol, src) = item
    path = os.path.join(OUT, f"{mint}.json")
    if os.path.exists(path): return "cached"
    tr = []
    for s in range(S, S + K + 1):
        b = rpc("getBlock", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False}])
        if b == "ERR": return f"ERR block {s}"
        if not b: continue
        txs = [t for t in b["transactions"] if VOTE not in t["transaction"]["message"]["accountKeys"]]
        for i, t in enumerate(txs):
            meta = t.get("meta") or {}
            if meta.get("err") is not None: continue
            for e in trades(meta.get("logMessages"), mint):
                e.update(slot=s, idx=i, payer=t["transaction"]["message"]["accountKeys"][0]); tr.append(e)
        del b, txs
    sS = [t for t in tr if t["slot"] == S]
    if not sS: return "no trades in S"
    ci = sS[0]["idx"]; ge = ci
    for t in sS[1:]:
        if t["idx"] == ge + 1 and t["buy"]: ge = t["idx"]
        else: break
    r = dict(mint=mint, S=S, slot_ms=217.4, fired=not SKIPLATE, engine=("skip_late" if SKIPLATE else "fired") + f" ({src})", create_ms=cms.get((S, mint), (None,))[0], leader_rtt=None, rule2_largest=True, any_moon=True,
             cidx=ci, glued_end=ge + 1, gsol=bsol, glued=ge - ci, dev=None, bundle_members=[], creator=sS[0]["user"], trades=tr, window_slots=K)
    json.dump(r, open(path, "w"))
    return f"ok {len(tr)} trades"


items = sorted(fires.items())
print(f"fired launches in the logs: {len(items)}", flush=True)
with ThreadPoolExecutor(int(os.environ.get("THREADS", "3"))) as ex:
    for (k, _), res in zip(items, ex.map(one, items)):
        print(f"  {k[1][:8]} S={k[0]}: {res}", flush=True)
