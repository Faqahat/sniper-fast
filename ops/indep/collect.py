#!/usr/bin/env python3
# READ-ONLY. Stage 1: enumerate recent pump.fun creates (getSignaturesForAddress on the pump mint authority) plus
# extra launches (fill/rows.jsonl launches, our live buys), fetch the create block and the next produced block(s),
# and record every tx touching each new mint in order (+ a neighbour window around the create).
# usage: collect.py <pages_of_1000_creates> <out.jsonl> [workers]
import json, sys, re, glob, collections, threading, time, os
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import *

PAGES, OUT = int(sys.argv[1]), sys.argv[2]
W = int(sys.argv[3]) if len(sys.argv) > 3 else 6
tipmap = load_tipmap()
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}

# ---- 1. creates from the mint authority
creates = {}  # slot -> set(tags)
before = None
tip = rpc("getSlot", [{"commitment": "finalized"}])
for p in range(PAGES):
    prm = {"limit": 1000}
    if before:
        prm["before"] = before
    r = rpc("getSignaturesForAddress", [MINT_AUTH, prm])
    if not isinstance(r, list) or not r:
        break
    for x in r:
        if x.get("err") is None:
            creates.setdefault(x["slot"], set()).add("rand")
    before = r[-1]["signature"]
    print(f"page {p}: {len(r)} sigs slots {r[-1]['slot']}..{r[0]['slot']}", flush=True)
rand_slots = sorted(creates)

# ---- 2. extra: fill launches + our live buys
extra_mints = {}  # mint -> dict(src, slot, ...)
try:
    for l in open("/root/fill/rows.jsonl"):
        r = json.loads(l)
        cs = r["slot"] - r["sd"]
        extra_mints.setdefault(r["mint"], {"src": "fill", "slot": cs})
except Exception as ex:
    print("fill rows:", ex)
ours = []
fires, vias, buysigs = {}, {}, []
for fn in sorted(glob.glob("/root/arbx-fast/live_bl_*.log")):
    for line in open(fn).read().splitlines():
        m = re.search(r"FIRE slot=(\d+) mint=(\w+) dev_buy=(\d+)", line)
        if m:
            fires[m.group(2)] = {"slot": int(m.group(1)), "mint": m.group(2), "dev_log": int(m.group(3)), "log": fn.split("/")[-1]}
        m = re.search(r"ROUND-TRIP \(LIVE\): mint=(\w+) buy spend=(\d+) lamports .* via ([\w\-]+)", line)
        if m:
            vias[m.group(1)] = (m.group(3), int(m.group(2)))
        m = re.search(r"^\s+BUY\s+sig=(\w+) send_slot=(\d+) land_slot=(\d+) delta=(\d+) ok=(\w+)", line)
        if m:
            buysigs.append((m.group(1), int(m.group(2)), int(m.group(3)), m.group(5) == "true", fn.split("/")[-1]))
seen_sig = set()
for sig, send_slot, land_slot, ok, fn in buysigs:
    if sig in seen_sig:
        continue
    seen_sig.add(sig)
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if not isinstance(t, dict) or "meta" not in t:
        continue
    tr, _ = events((t.get("meta") or {}).get("logMessages"))
    mints = [e["mint"] for e in tr if e["buy"]]
    if not mints or mints[0] not in fires:
        continue
    d = dict(fires[mints[0]])
    d.update(sig=sig, send_slot=send_slot, land_slot=t["slot"], ok=t["meta"].get("err") is None, via=vias.get(mints[0], ("?", 0))[0],
             spend=vias.get(mints[0], ("?", 0))[1], log=fn)
    ours.append(d)
json.dump(ours, open("/root/indep/ours.json", "w"))
for d in ours:
    extra_mints[d["mint"]] = {"src": "ours", "slot": d["slot"], "ours": d}
print(f"rand create slots {len(rand_slots)}; extra launches {len(extra_mints)} (ours {len(ours)})", flush=True)
for mnt, d in extra_mints.items():
    creates.setdefault(d["slot"], set()).add(d["src"])

# how many blocks after S to look at: next produced block; ours: through land slot
need_upto = {}
for s in creates:
    need_upto[s] = s + 1
for mnt, d in extra_mints.items():
    if d["src"] == "ours":
        need_upto[d["slot"]] = max(need_upto[d["slot"]], d["ours"]["land_slot"])

# ---- 3. leaders
allslots = sorted(creates)
if os.environ.get('TEST_LIMIT'):
    allslots = sorted(rand_slots)[-int(os.environ['TEST_LIMIT']):]
leaders = {}
def leaders_for(lo, hi):
    s = lo
    while s <= hi:
        n = min(4000, hi - s + 1)
        r = rpc("getSlotLeaders", [s, n])
        if isinstance(r, list):
            for i, l in enumerate(r):
                leaders[s + i] = l
        s += n
# group into contiguous ranges to save calls
rng = []
for s in allslots:
    if rng and s - rng[-1][1] < 3000:
        rng[-1][1] = s + 8
    else:
        rng.append([s, s + 8])
for lo, hi in rng:
    leaders_for(lo, hi)
print(f"leaders fetched for {len(leaders)} slots", flush=True)


def client_of(slot):
    l = leaders.get(slot)
    return l, nodes.get(l, {}).get("clientId", "?") if l else "?"


# ---- 4. block processing
out = open(OUT, "w")
olock = threading.Lock()
stats = collections.Counter()


def touch_mint(t, keys, mint):
    return mint in keys


def summarize_mint_txs(blk, mint, start_idx, tag_slot):
    """all txs in blk at idx >= start_idx that touch mint (with trade events)"""
    rows = []
    nv = -1
    for idx, t in enumerate(blk["transactions"]):
        v = is_vote(t)
        if not v:
            nv += 1
        if idx < start_idx or v:
            continue
        msg = t["transaction"]["message"]
        meta = t.get("meta") or {}
        ks = msg["accountKeys"]
        la = meta.get("loadedAddresses") or {}
        if mint not in ks and mint not in la.get("writable", []) and mint not in la.get("readonly", []):
            continue
        s, keys = tx_summary(t, tipmap)
        tr, cr = events(meta.get("logMessages"))
        s["ev"] = [e for e in tr if e["mint"] == mint]
        s["ev_other"] = sum(1 for e in tr if e["mint"] != mint)
        s["slot"], s["idx"], s["nv"] = tag_slot, idx, nv
        rows.append(s)
    return rows


def nv_index_list(blk):
    nvl, nv = [], -1
    for t in blk["transactions"]:
        if is_vote(t):
            nvl.append(None)
        else:
            nv += 1
            nvl.append(nv)
    return nvl, nv + 1


def process_slot(S, cache):
    def gb(slot):
        if slot in cache:
            return cache[slot]
        b = get_block(slot)
        if len(cache) > 4:
            cache.pop(next(iter(cache)))
        cache[slot] = b
        return b
    blk = gb(S)
    if not isinstance(blk, dict) or "__err" in blk or "transactions" not in blk:
        stats["s_block_missing"] += 1
        return
    nvl, nnv = nv_index_list(blk)
    # find creates
    found = []
    for idx, t in enumerate(blk["transactions"]):
        msg = t["transaction"]["message"]
        meta = t.get("meta") or {}
        if PUMP not in msg["accountKeys"] and PUMP not in (meta.get("loadedAddresses") or {}).get("readonly", []):
            continue
        if meta.get("err") is not None:
            continue
        logs = meta.get("logMessages") or []
        if not any(l.startswith("Program log: Instruction: Create") for l in logs):
            continue
        tr, cr = events(logs)
        for c in cr:
            found.append((idx, t, c, tr))
    wanted_extra = {m: d for m, d in extra_mints.items() if d["slot"] == S}
    # next produced blocks
    nexts = []
    s2 = S + 1
    upto = need_upto.get(S, S + 1)
    while s2 <= S + 6 and (s2 <= upto or not nexts):
        b2 = gb(s2)
        if isinstance(b2, dict) and "transactions" in b2:
            nexts.append((s2, b2))
        s2 += 1
    for idx, t, c, tr in found:
        mint = c["mint"]
        cs, keys = tx_summary(t, tipmap)
        cs["ev"] = [e for e in tr if e["mint"] == mint]
        cs["slot"], cs["idx"], cs["nv"] = S, idx, nvl[idx]
        # neighbour window (non-vote) -3..+25
        nb = []
        for j in range(max(0, idx - 8), min(len(blk["transactions"]), idx + 60)):
            if nvl[j] is None or j == idx:
                continue
            if not (-3 <= nvl[j] - nvl[idx] <= 25):
                continue
            tt = blk["transactions"][j]
            s, k2 = tx_summary(tt, tipmap)
            tr2, cr2 = events((tt.get("meta") or {}).get("logMessages"))
            nb.append({"d": nvl[j] - nvl[idx], "payer": s["payer"], "signers": s["signers"], "tips": s["tips"], "keytip": s["keytip"],
                       "mint_ev": sum(1 for e in tr2 if e["mint"] == mint), "touch": mint in k2, "other_ev": sum(1 for e in tr2 if e["mint"] != mint),
                       "create": bool(cr2), "err": s["err"], "cu_price": s["cu_price"], "progs": s["progs"][:6]})
        rows = summarize_mint_txs(blk, mint, idx + 1, S)
        nrows = []
        for s2_, b2 in nexts:
            nrows += summarize_mint_txs(b2, mint, 0, s2_)
        l0, c0 = client_of(S)
        rec = {"mint": mint, "slot": S, "blockTime": blk.get("blockTime"), "leader": l0, "client": c0,
               "ntx": len(blk["transactions"]), "nnv": nnv, "create": cs, "cev": c, "nb": nb, "rows": rows, "nrows": nrows,
               "next": [{"slot": s2_, "leader": client_of(s2_)[0], "client": client_of(s2_)[1], "ntx": len(b2["transactions"]),
                         "nnv": nv_index_list(b2)[1], "blockTime": b2.get("blockTime")} for s2_, b2 in nexts],
               "src": sorted(creates.get(S, [])) + (["extra:" + wanted_extra[mint]["src"]] if mint in wanted_extra else [])}
        if mint in wanted_extra and wanted_extra[mint]["src"] == "ours":
            rec["ours"] = wanted_extra[mint]["ours"]
        with olock:
            out.write(json.dumps(rec) + "\n")
            stats["creates"] += 1
            if rows:
                stats["with_same_slot_tx"] += 1
    for m in wanted_extra:
        if m not in {c["mint"] for _, _, c, _ in found}:
            stats["extra_not_found_in_slot"] += 1
            with olock:
                out.write(json.dumps({"mint": m, "slot": S, "missing": True, "src": ["extra:" + wanted_extra[m]["src"]],
                                      "ours": wanted_extra[m].get("ours")}) + "\n")


def worker(chunk):
    cache = {}
    for S in chunk:
        try:
            process_slot(S, cache)
        except Exception as ex:
            stats["exc"] += 1
            print("EXC", S, repr(ex)[:200], flush=True)
        stats["slots_done"] += 1
        if stats["slots_done"] % 100 == 0:
            print(f"{time.strftime('%H:%M:%S')} slots {stats['slots_done']}/{len(allslots)} {dict(stats)}", flush=True)


chunks = [allslots[i::1] for i in range(1)]
# contiguous chunks so S+1 caching works
k = max(1, (len(allslots) + W - 1) // W)
chunks = [allslots[i:i + k] for i in range(0, len(allslots), k)]
with ThreadPoolExecutor(max_workers=W) as ex:
    list(ex.map(worker, chunks))
out.close()
print("FINISHED", dict(stats), flush=True)
