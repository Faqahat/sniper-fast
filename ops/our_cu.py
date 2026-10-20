import json, urllib.request, os, time, re, base64, concurrent.futures as cf
TOK = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
CB = "ComputeBudget111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def rpc(m, p):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    for i in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=20)).get("result")
        except Exception:
            time.sleep(0.3 * (i + 1))
    return None


def decode_cu(sig):
    tx = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}])
    if not tx:
        return None
    ixs = tx["transaction"]["message"]["instructions"]
    cu_limit = None
    cu_price = None
    for ix in ixs:
        if ix.get("programId") == CB and "data" in ix:
            try:
                raw = b58dec(ix["data"])
            except Exception:
                continue
            if not raw:
                continue
            if raw[0] == 0x02 and len(raw) >= 5:  # SetComputeUnitLimit
                cu_limit = int.from_bytes(raw[1:5], "little")
            elif raw[0] == 0x03 and len(raw) >= 9:  # SetComputeUnitPrice
                cu_price = int.from_bytes(raw[1:9], "little")
    err = tx.get("meta", {}).get("err")
    fee = tx.get("meta", {}).get("fee", 0)
    return (cu_limit, cu_price, fee, err)


# collect our BUY sigs from the recent live logs
sigs = []
for lg in ["live_bl_exit.log", "live_bl_noz.log", "live_bl_rt.log"]:
    try:
        for ln in open(f"/root/sniper-fast/{lg}"):
            m = re.search(r"BUY  sig=(\w+)", ln)
            if m:
                sigs.append((lg.replace("live_bl_", "").replace(".log", ""), m.group(1)))
    except FileNotFoundError:
        pass
print(f"our buy txs found: {len(sigs)}")
print(f"{'run':6} {'cu_limit':>9} {'cu_price':>10} {'prio_fee_SOL':>12} {'err'}")
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    res = list(ex.map(lambda x: (x[0], decode_cu(x[1])), sigs))
from collections import Counter
cl = Counter()
cp = Counter()
for run, r in res:
    if not r:
        continue
    cu_limit, cu_price, fee, err = r
    prio = (cu_price or 0) * (cu_limit or 0) / 1e6 / 1e9
    print(f"{run:6} {str(cu_limit):>9} {str(cu_price):>10} {prio:>12.6f} {'ERR' if err else 'ok'}")
    cl[cu_limit] += 1
    cp[cu_price] += 1
print("\ncu_limit values used:", dict(cl))
print("cu_price values used:", dict(cp))
