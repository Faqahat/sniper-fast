"""Build tests/data/mainnet-accounts.json: real mainnet accounts (read-only RPC, cached in
program/venue-harness/fixtures/rpc-cache) for the pools DESIGN.md §1.4 checked, with every state account a sizing
leg reads (pool, configs, vaults, mints, DLMM bin arrays). Most come from the cache the design research filled; the
few mints it did not fetch are read once (getMultipleAccounts, cached). Also writes tests/data/pump-events.json:
the PumpSwap Buy/SellEvents of research/pump_events_check.py as plain numbers (pre-swap reserves, fee bps, amounts,
the program's own outputs)."""
import base64, glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "research")
sys.path.insert(0, RES)
os.chdir(RES)
from solrpc import *

CACHE = os.path.join(RES, "..", "..", "venue-harness", "fixtures", "rpc-cache")
acc = {}   # key -> (slot, owner, data)
for f in sorted(glob.glob(os.path.join(CACHE, "getMultipleAccounts-*.json"))):
    j = json.load(open(f))
    slot = j["result"]["context"]["slot"]
    for k, a in zip(j["request"]["params"][0], j["result"]["value"]):
        if a is None: continue
        if k not in acc or acc[k][0] < slot:
            acc[k] = (slot, a["owner"], base64.b64decode(a["data"][0]))

def need(keys):
    miss = [k for k in keys if k not in acc]
    if miss:
        got, slot = accounts(miss)
        for k, a in got.items():
            if a is not None: acc[k] = (slot, a[0], a[2])
    return keys

PUMP = ["GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV", "6ejg4aYJM3Mk1t2zBKjbJ43df3s7rBMpC9mgo526K51G"]
DLMM = ["6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo", "C9xcUNdJrY45uBeJiuAEiNUZzxs1M22mDFCus3dm1QWq", "7hvn8egrNGkpQFGyziHxvGkJFWtmoCyXmYYXp4V7tszd"]
DAMM = ["C8jdide5evNRRVBiisJSnFeHH2k7FKbARP64iyfSrkdf", "2E8c2vnAKQ3WaSHjezHwQ6GozuXRx96JX7GoNoBeqBug", "3Bu5wTUftguy5BxhTgFrukz6wvG6d4xYRKuU43jWA3cg"]
CPMM = ["GfApkU62yAmUXc6FNsZrBLgcUn8vXdhW6WzSbA5ETtDa", "Hmx1eHEdm67YYZYEathc6aki2q3zjhhTmw7wZPq66BnJ"]
AMM4 = ["FVq2chsiAcPqwL9L3zafF8juQHb7mui6LWMuE8g5L4K4"]
GC = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"; FC = "5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx"
DLMM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"; PUMP_FUN = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
need(PUMP + DLMM + DAMM + CPMM + AMM4 + [GC, FC])
pools = {}
for p in PUMP:
    d = acc[p][2]
    base, quote, bv, qv = key(d, 43), key(d, 75), key(d, 139), key(d, 171)
    need([base, quote, bv, qv])
    bump = pda([b"pool-authority", pk(base)], PUMP_FUN)[1]
    pools[p] = {"venue": "pump", "state": [p, GC, base, quote, bv, qv, FC], "bump": bump}
for p in CPMM:
    d = acc[p][2]
    need([key(d, 8), key(d, 72), key(d, 104), key(d, 168), key(d, 200)])
    pools[p] = {"venue": "cpmm", "state0": [p, key(d, 8), key(d, 72), key(d, 104), key(d, 168), key(d, 200)]}
for p in AMM4:
    d = acc[p][2]
    need([key(d, 336), key(d, 368)])
    pools[p] = {"venue": "ammv4", "state": [p, key(d, 336), key(d, 368)]}
for p in DAMM:
    d = acc[p][2]
    need([key(d, 168), key(d, 200)])
    pools[p] = {"venue": "dammv2", "state": [p, key(d, 168), key(d, 200)]}
for p in DLMM:
    d = acc[p][2]
    active = i32(d, 76); c = active // 70
    arrays = {}
    for i in range(c - 3, c + 4):
        k = pda([b"bin_array", pk(p), i.to_bytes(8, "little", signed=True)], DLMM_ID)[0]
        if k in acc: arrays[i] = k
    need([key(d, 88), key(d, 120)])
    pools[p] = {"venue": "dlmm", "state": [p, key(d, 88), key(d, 120)], "arrays": {str(i): k for i, k in sorted(arrays.items())}}

keys = set()
for v in pools.values():
    for k in v.get("state", []) + v.get("state0", []) + list(v.get("arrays", {}).values()): keys.add(k)
clk = acc.get("SysvarC1ock11111111111111111111111111111111")
clock = {"slot": u64(clk[2], 0), "epoch": u64(clk[2], 16), "unix_timestamp": i64(clk[2], 32)}
out = {"note": "mainnet accounts, read-only RPC 2026-10-04 (slots ~453.2M), see gen_fixtures.py", "clock": clock,
       "pools": pools,
       "accounts": {k: {"slot": acc[k][0], "owner": acc[k][1], "hex": pk(k).hex(), "owner_hex": pk(acc[k][1]).hex(),
                        "data": base64.b64encode(acc[k][2]).decode()} for k in sorted(keys)}}
json.dump(out, open(os.path.join(HERE, "mainnet-accounts.json"), "w"), indent=1)
print(f"{len(keys)} accounts, {len(pools)} pools -> mainnet-accounts.json")

# ---- PumpSwap events ----
exec(open("pump_events.py").read().split("pool = sys.argv[1]")[0])
ev = []
for f in sorted(glob.glob(os.path.join(CACHE, "getTransaction-*.json"))):
    tx = json.load(open(f))["result"]
    if tx is None or tx["meta"]["err"] is not None: continue
    msg = tx["transaction"]["message"]; la = tx["meta"].get("loadedAddresses") or {"writable": [], "readonly": []}
    ks = msg["accountKeys"] + la["writable"] + la["readonly"]
    for inner in tx["meta"]["innerInstructions"] or []:
        for ix in inner["instructions"]:
            if ks[ix["programIdIndex"]] != PUMP: continue
            d = b58d(ix["data"])
            if d[:8] != EVT_TAG or d[8:16] not in (D_BUY, D_SELL): continue
            s = d[8:16] == D_SELL
            e = sell(d[16:]) if s else buy(d[16:])
            row = {"kind": "sell" if s else e["ix_name"], "B": e["pool_base_token_reserves"], "Q": e["pool_quote_token_reserves"],
                   "V": e["virtual_quote_reserves"], "lp": e["lp_fee_basis_points"], "pr": e["protocol_fee_basis_points"],
                   "cr": e["coin_creator_fee_basis_points"], "cb": e["cashback_fee_basis_points"]}
            if s:
                row.update({"in": e["base_amount_in"], "q": e["quote_amount_out"], "lp_fee": e["lp_fee"], "pr_fee": e["protocol_fee"],
                            "cr_fee": e["coin_creator_fee"], "cb_fee": e["cashback"], "out": e["user_quote_amount_out"]})
            else:
                row.update({"in": e["max_quote_amount_in"], "out": e["base_amount_out"], "user_in": e["user_quote_amount_in"],
                            "quote_in": e["quote_amount_in"], "lp_fee": e["lp_fee"], "pr_fee": e["protocol_fee"], "cr_fee": e["coin_creator_fee"],
                            "cb_fee": e["cashback"]})
            ev.append({k: str(v) for k, v in row.items()})
json.dump(ev, open(os.path.join(HERE, "pump-events.json"), "w"), indent=0)
from collections import Counter
print(len(ev), "pump events", Counter(r["kind"] for r in ev))
