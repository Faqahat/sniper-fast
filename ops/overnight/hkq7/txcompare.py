#!/usr/bin/env python3
# FULL TX ANATOMY, OURS vs RIVALS (read-only). For each guard revert (2g FRA last 3.5 h, AMS last 4 h): our tx vs the buy that crossed our min_out.
# For each of our fills in the same windows: our tx vs the first rival buy that landed between the dump and us (or the first one right behind us).
# Per tx: version, ALT, size bytes, #signatures, #accounts, top-level programs, #instructions, ATA create, nonce, CU limit / CU price / CU used,
# base fee, priority lamports, tip (service, lamports, where in the tx), buy kind (pump buy / buy_exact_sol_in / router CPI), slippage room, landing ms after the dump.
import os, sys, json, time, base64, urllib.request, collections, statistics, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"; TOK = {"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "spl", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "tok22"}
MEMO = {"MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
NAMES = {SYS: "system", CB: "computebudget", PUMP: "pump", ATA: "ata", **{k: v for k, v in TOK.items()}}
DISC = {"66063d1201daebea": "buy", "38fc74089edfcd5f": "buy_exact_sol_in", "33e685a4017f83ad": "sell"}
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
BLK = {}
def block(slot):
    if slot not in BLK:
        b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); BLK[slot] = b["signatures"] if b else []
    return BLK[slot]
es = rpc("getEpochSchedule", []); SCH = {}
def leader(slot):
    ep = (slot - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
    if ep not in SCH: s = rpc("getLeaderSchedule", [slot]) or {}; SCH[ep] = {first + i: k for k, v in s.items() for i in v}
    return SCH[ep].get(slot)
NODES = {n["pubkey"]: n for n in rpc("getClusterNodes", [])}
def client(i):
    c = (NODES.get(i or "") or {}).get("clientId") or ""
    return "BAM" if "Bam" in c or "BAM" in c else ("Harmonic" if "Harmonic" in c else ("Jito" if c in ("JitoLabs", "Rakurai") else ("Firedancer" if "dancer" in c.lower() else c or "?")))
L = rp.load_launches()
def anatomy(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    raw = rpc("getTransaction", [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    cup = 0; cul = None; tips = []; tip_pos = []; progs = []; buy = None; mint = None; spend = mn = None; ata = False; nonce = False; memo = False; ixs = msg["instructions"]
    pump_k = None
    for k, ix in enumerate(ixs):
        p = keys[ix["programIdIndex"]]; d = dec(ix["data"]); progs.append(NAMES.get(p, p[:6]))
        if p == CB and d:
            if d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif d[0] == 2: cul = int.from_bytes(d[1:5], "little")
        elif p == SYS and len(d) >= 4 and int.from_bytes(d[:4], "little") == 4: nonce = nonce or k == 0
        elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP:
            tips.append((TIP[keys[ix["accounts"][1]]], int.from_bytes(d[4:12], "little"))); tip_pos.append(k)
        elif p == ATA: ata = True
        elif p in MEMO: memo = True
        elif p == PUMP and len(d) >= 24:
            buy = DISC.get(d[:8].hex(), d[:8].hex()); pump_k = k
            cands = [keys[a] for a in ix["accounts"][:4]]; mint = next((c for c in cands if c in L), None)
            spend, mn = int.from_bytes(d[8:16], "little"), int.from_bytes(d[16:24], "little")
    inner_tip = []
    for g in meta.get("innerInstructions") or []:
        for ix in g["instructions"]:
            p = keys[ix["programIdIndex"]]; d = dec(ix["data"])
            if p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP: inner_tip.append((TIP[keys[ix["accounts"][1]]], int.from_bytes(d[4:12], "little")))
            if buy is None and p == PUMP and len(d) >= 8 and d[:8].hex() in DISC: buy = "router→" + DISC[d[:8].hex()]
    if buy is None: buy = "?"
    # a tip transferred inside a router CPI is invisible at the top level; count it too
    alltips = tips + inner_tip
    s = block(t["slot"]); idx = s.index(sig) if sig in s else None
    rb = base64.b64decode(raw["transaction"][0]) if raw else b""
    ver = t.get("version"); nsig = len(t["transaction"]["signatures"])
    cul_eff = cul if cul is not None else 200000 * sum(1 for x in ixs if keys[x["programIdIndex"]] != CB)
    return dict(sig=sig, signer=keys[0], slot=t["slot"], idx=idx, size_blk=len(s), version=str(ver), alt=len(msg.get("addressTableLookups") or []), bytes=len(rb), nsig=nsig,
                nkeys=len(keys), nix=len(ixs), progs=progs, ata=ata, nonce=nonce, memo=memo, cu_limit=cul_eff, cu_price=cup, cu_used=meta.get("computeUnitsConsumed"),
                fee=meta["fee"], prio_lam=cup * cul_eff // 10**6, tip_svc="+".join(sorted({a for a, _ in alltips})) or "none", tip_lam=sum(b for _, b in alltips),
                tip_where=("inner" if inner_tip and not tips else ("before buy" if tips and pump_k is not None and max(tip_pos) < pump_k else ("after buy" if tips else "-"))),
                buy=buy, mint=mint, spend=spend, min_out=mn, err=json.dumps(meta["err"]), leader_client=client(leader(t["slot"])))
def ms(a, b): return (b[0] - a[0]) * 212.0 + (b[1] / max(b[2], 1) - a[1] / max(a[2], 1)) * 212.0
def fr(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
WALLETS = {"2g FRA": ("rev_2g.json", time.time() - 3.5 * 3600), "AMS": ("rev_ams.json", time.time() - 4 * 3600)}
pairs = []
for wname, (f, t0) in WALLETS.items():
    R = [r for r in json.load(open(f)) if r["signer"] and r["bt"] >= t0]
    with cf.ThreadPoolExecutor(8) as ex: A = list(ex.map(lambda r: anatomy(r["sig"]), R))
    byb = collections.defaultdict(set)
    for a in A:
        if a and a["mint"] in L: byb[(L[a["mint"]]["run"], rp.bucket(a["mint"]))].add(a["mint"])
    tapes = {}
    for k, m in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], m))
    for r, a in zip(R, A):
        if not a or a["idx"] is None or a["buy"] in ("sell", "?") or not a["mint"]: continue
        rev = "6042" in a["err"]
        if not rev and a["err"] != "null": continue
        tr = tapes.get(a["mint"], []); me = (a["slot"], a["idx"])
        dk = max((k for k, t in enumerate(tr) if (t["s"], t["i"]) < me and not t["buy"] and t["sol"] >= 1e9), default=None)
        if dk is None: continue
        d = tr[dk]; dpos = (d["s"], d["i"], len(block(d["s"])))
        btw = [t for t in tr[dk + 1:] if (t["s"], t["i"]) < me and t["buy"] and t["user"] != a["signer"]]
        if rev: riv = next((t for t in btw if (lambda X: t["vtok"] * X // (t["vsol"] + X))(int(a["spend"] / (1 + fr(t)))) < a["min_out"]), None); role = "crossed our guard"
        elif btw: riv = btw[0]; role = "landed ahead of our fill"
        else: riv = next((t for t in tr[dk + 1:] if (t["s"], t["i"]) > me and t["buy"] and t["user"] != a["signer"]), None); role = "first behind our fill"
        if not riv: continue
        b = anatomy(riv["sig"])
        if not b: continue
        a["ms"] = ms(dpos, (a["slot"], a["idx"], a["size_blk"])); b["ms"] = ms(dpos, (b["slot"], b["idx"], b["size_blk"]))
        a["dump_client"] = client(leader(d["s"]))
        pairs.append(dict(wallet=wname, outcome="REVERT" if rev else "FILL", role=role, ours=a, rival=b, dump_sol=d["sol"] / 1e9, n_ahead=len(btw)))
json.dump(pairs, open("txcompare.json", "w"), default=str)
print(f"pairs: {len(pairs)}")
