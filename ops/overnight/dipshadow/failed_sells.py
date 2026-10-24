#!/usr/bin/env python3
# READ-ONLY RPC: how many FAILED direct pump sells would look like a dip trigger to a shred engine (>=1 SOL on a launch aged
# 1-120 s), and would the planned checks catch them? Sample failed direct sell txs on young launches from the raw chunks,
# fetch them (instruction data: tokens to sell, min SOL out), price the sell on the curve from our trade history, and check:
#   (a) seller's holdings in our history >= tokens to sell;  (b) min SOL out <= expected SOL out (curve, minus fees).
# usage: python3 -I failed_sells.py N
import sys, os, json, gzip, glob, random, time, collections, urllib.request, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WL = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
      "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
      "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", PUMP}
SELLS = {"33e685a4017f83ad": (2, 6), "1c92de7726c469d5": (1, 8), "5df6823ce7e940b2": (1, 13)}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
U = lambda b, o: int.from_bytes(b[o:o + 8], "little")
def rpc(m, p, tries=5):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                                                                        headers={"content-type": "application/json"}), timeout=30))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
N = int(sys.argv[1]); rnd = random.Random(9)
files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz"))
cands = []
for f in rnd.sample(files, 24):
    for line in gzip.open(f, "rt"):
        if '"Sell' not in line or '"err":null' in line: continue
        r = json.loads(line)
        if PUMP not in (r.get("progs") or []) or (set(r.get("progs") or []) - WL): continue
        if not any(n.startswith("Sell") for n in (r.get("ixn") or [])): continue
        m = [x for x in (r.get("mints") or []) if x in D.L]
        if not m: continue
        age = (r["s"] - D.L[m[0]]["slot"]) * D.SMS / 1000
        if 1 <= age <= 120: cands.append((r["sig"], m[0], r["s"], r["i"], json.dumps(r["err"])[:40]))
rnd.shuffle(cands); cands = cands[:N]
print("failed direct sells on young launches sampled:", len(cands), flush=True)
def one(c):
    sig, m, s, i, err = c
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    out = []
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != PUMP: continue
        d = b58dec(ix["data"]); lay = SELLS.get(d[:8].hex())
        if not lay: continue
        accs = [keys[a] for a in ix["accounts"]]
        if len(accs) <= lay[1] or accs[lay[0]] != m: continue
        out.append(dict(sig=sig, m=m, s=s, i=i, err=err, seller=accs[lay[1]], tok=U(d, 8), minsol=U(d, 16)))
    return out
R = []
with cf.ThreadPoolExecutor(16) as ex:
    for o in ex.map(one, cands):
        if o: R += o
byb = collections.defaultdict(set)
for r in R: byb[(D.L[r["m"]]["run"], D.rp.bucket(r["m"]))].add(r["m"])
H = {}
for key in byb:
    for m, tr in D.rp.read_bucket(key[0], key[1], byb[key]).items(): H[m] = tr
res = collections.Counter(); big = collections.Counter()
for r in R:
    tr = H.get(r["m"], [])
    prev = [x for x in tr if (x["s"], x["i"]) < (r["s"], r["i"])]
    if not prev: res["no history"] += 1; continue
    V, T = prev[-1]["vsol"], prev[-1]["vtok"]
    so = V - V * T // (T + r["tok"]); fr = 0.0125; exp = so * (1 - fr)
    held = sum(x["tok"] for x in prev if x["user"] == r["seller"] and x["buy"]) - sum(x["tok"] for x in prev if x["user"] == r["seller"] and not x["buy"])
    is_big = so >= 1e9
    k = ("would look like a >=1 SOL dump" if is_big else "< 1 SOL")
    res[k] += 1
    if is_big:
        a = held >= r["tok"]; b = r["minsol"] <= exp * 1.0
        big[("holdings ok" if a else "holdings FAIL") + " / " + ("min-out ok" if b else "min-out FAIL") + " | " + r["err"][:30]] += 1
print("decoded failed direct sells:", len(R), dict(res))
print("those that would look like a >=1 SOL dump, by check result and error:")
for k, v in big.most_common(12): print(f"   {v:4d}  {k}")
