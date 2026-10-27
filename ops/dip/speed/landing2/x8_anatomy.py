#!/usr/bin/env python3
# Tx anatomy of landed reaction buys (read-only getTransaction, <= 4 req/s, cached): version, size, signatures, keys, ALT,
# durable nonce (+ nonce account), compute-budget ixs (limit, price, loaded-data limit), tips (count, where vs the buy),
# Lighthouse/guard programs, cost units. Sample: per wallet up to PER landings per leader client (pro_rows + our fires).
import sys, json, collections, random, statistics as st, base64
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
from rpc_ro import get_tx
PER = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = json.load(open(f"{lib2.D}/pro_rows_1.0_0.04.json"))
H = json.load(open(f"{lib2.D}/h2h.json"))
WAL = json.load(open(f"{lib2.D}/wallets.json"))
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
LH = "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def cu16(n): return 1 if n < 128 else (2 if n < 16384 else 3)
WANT = ["HkQ7hMjy", "haqqiUUX", "DYXDDrZC", "8PgC4ngp", "6n2cCJrr", "9u5f8WMf", "G9G3dCBG", "5w8xtjc6", "DF7eRXHn", "EprLoV21", "HLU8QbLd",
        "GKd5EMzR", "EMKY7r6U", "BUkpShoE", "3MHgGwdL", "E6JasdE8", "EjywYBfN", "CZ77onJz"]
sample = []
random.seed(7)
by = collections.defaultdict(list)
for r in rows:
    nm = WAL[r["w"]]["name"]
    if nm in WANT: by[(nm, r["cl"])].append(r)
for (nm, cl), v in by.items():
    v = [r for r in v if r["s0"] > 460883322]           # R4 part (recent, inside RPC history)
    random.shuffle(v)
    for r in v[:PER]: sample.append(dict(who=nm, cl=cl, sig=r["sig"], ms=r["ms"], svc=r["svc"], ok=r["ok"]))
# ours: landed variant of our fires (recent runs)
for r in H:
    if "our_sig" in r and r["s0"] > 460883322:
        sample.append(dict(who="OURS-" + r["srv"], cl=r["cl"], sig=r["our_sig"], ms=r["our_ms"], svc=r["our_svc"], ok=r["our_ok"]))
print(f"sample {len(sample)} txs", flush=True)
out = []
for k, x in enumerate(sample):
    t = get_tx(x["sig"])
    if not t: continue
    tx = t["transaction"]; m = tx["message"]; meta = t["meta"]
    keys = m["accountKeys"]; la = meta.get("loadedAddresses") or {}
    allk = keys + la.get("writable", []) + la.get("readonly", [])
    ver = t.get("version", "legacy")
    ixs = m["instructions"]
    progs = [allk[i["programIdIndex"]] for i in ixs]
    size = cu16(len(tx["signatures"])) + 64 * len(tx["signatures"]) + (1 if ver != "legacy" else 0) + 3 + cu16(len(keys)) + 32 * len(keys) + 32 + cu16(len(ixs))
    for i in ixs:
        dl = len(dec(i["data"])); size += 1 + cu16(len(i["accounts"])) + len(i["accounts"]) + cu16(dl) + dl
    luts = m.get("addressTableLookups") or []
    if ver != "legacy":
        size += cu16(len(luts)) + sum(32 + cu16(len(l["writableIndexes"])) + len(l["writableIndexes"]) + cu16(len(l["readonlyIndexes"])) + len(l["readonlyIndexes"]) for l in luts)
    nonce = None
    if ixs and progs[0] == SYS:
        d0 = dec(ixs[0]["data"])
        if len(d0) >= 4 and int.from_bytes(d0[:4], "little") == 4: nonce = allk[ixs[0]["accounts"][0]]
    cul = cup = ldl = None
    for i, p in zip(ixs, progs):
        if p != CB: continue
        d = dec(i["data"])
        if not d: continue
        if d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        elif d[0] == 3: cup = int.from_bytes(d[1:9], "little")
        elif d[0] == 4: ldl = int.from_bytes(d[1:5], "little")
    tips = []; buy_ix = None
    for j, (i, p) in enumerate(zip(ixs, progs)):
        if p == PUMP and buy_ix is None: buy_ix = j
        if p == SYS and len(i["accounts"]) >= 2:
            d = dec(i["data"])
            if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2:
                dst = allk[i["accounts"][1]]; lam = int.from_bytes(d[4:12], "little")
                svc = lib2.svc_of(dst) or lib2.UNK.get(dst)
                if svc: tips.append((j, svc, lam))
    own_prog = sorted({p for p in progs if p not in (SYS, CB, PUMP, LH, "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                                                     "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")})
    out.append(dict(x, ver=ver, size=size, nsig=len(tx["signatures"]), nkeys=len(allk), nstatic=len(keys), alt=len(luts), nonce=nonce, cul=cul, cup=cup, ldl=ldl,
                    tips=tips, tip_where=("before buy" if tips and buy_ix is not None and tips[0][0] < buy_ix else ("after buy" if tips else "-")),
                    lighthouse=LH in progs, own=own_prog, nix=len(ixs), cost=meta.get("costUnits"), cu_used=meta.get("computeUnitsConsumed"),
                    fee=meta.get("fee"), err=meta.get("err") is not None, slot=t["slot"]))
    if k % 50 == 0: print(k, flush=True)
json.dump(out, open(f"{lib2.D}/anatomy.json", "w"))
print(f"done {len(out)}")
