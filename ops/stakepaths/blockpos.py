#!/usr/bin/env python3
# READ-ONLY: samples recent blocks via getBlock and measures, for pump.fun creation
# blocks, where same-slot buyers of the new mint land (tx index) and which sender
# they tipped (from published tip-account lists). Also tags the leader's client.
# usage: blockpos.py <rpc_url> <n_blocks> <out_json>
import json, sys, time, urllib.request, collections, statistics

RPC, N, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
VOTE = "Vote111111111111111111111111111111111111111"


def rpc(method, params):
    req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


tips = {}
for prov, v in json.load(open("/root/arbx-fast/data/sender-tip-accounts.json")).items():
    if not isinstance(v, dict):
        continue
    ta = v.get("tip_accounts")
    if isinstance(ta, str):
        try:
            ta = eval(ta, {"__builtins__": {}})
        except Exception:
            ta = []
    for a in ta or []:
        if isinstance(a, str):
            tips.setdefault(a, prov)

nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
tip_slot = rpc("getSlot", [{"commitment": "confirmed"}])["result"]
start = tip_slot - N - 5
leaders = rpc("getSlotLeaders", [start, N])["result"]

rows, blocks = [], []
from concurrent.futures import ThreadPoolExecutor


def fetch(slot):
    try:
        return rpc("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1,
                                       "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}])
    except Exception:
        return {}


with ThreadPoolExecutor(max_workers=4) as ex:
    fetched = list(ex.map(fetch, [start + i for i in range(N)]))
for i in range(N):
    slot = start + i
    b = fetched[i]
    if "result" not in b or not b["result"]:
        continue
    txs = b["result"]["transactions"]
    leader = leaders[i]
    client = nodes.get(leader, {}).get("clientId", "?")
    ntx = len(txs)
    nonvote_idx = 0
    creates = []  # (idx, mint)
    per = []
    for idx, t in enumerate(txs):
        keys = (t.get("transaction") or {}).get("message", {}).get("accountKeys") or []
        isvote = VOTE in keys
        prov = next((tips[k] for k in keys if k in tips), "none")
        meta = t.get("meta") or {}
        mints = {tb["mint"] for tb in (meta.get("postTokenBalances") or [])}
        logs = meta.get("logMessages") or []
        is_create = PUMP in keys and any(l.startswith("Program log: Instruction: Create") for l in logs)
        per.append((idx, nonvote_idx, isvote, prov, mints, meta.get("err") is None, is_create, keys[0]))
        if not isvote:
            nonvote_idx += 1
        if is_create:
            m = [x for x in mints if x.endswith("pump")] or list(mints)
            if m:
                creates.append((idx, m[0]))
    nnv = nonvote_idx
    blocks.append({"slot": slot, "leader": leader, "client": client, "ntx": ntx, "nonvote": nnv, "creates": len(creates),
                   "create_nv_idx": [next(p[1] for p in per if p[0] == c) for c, _ in creates],
                   "provseq": [p[3] for p in per if not p[2]]})
    for cidx, mint in creates:
        for (idx, nvi, isvote, prov, mints, ok, isc, payer) in per:
            if idx > cidx and mint in mints and not isvote:
                rows.append({"slot": slot, "client": client, "create_idx": cidx, "idx": idx, "nv_idx": nvi,
                             "nonvote": nnv, "prov": prov, "ok": ok, "payer": payer, "mint": mint})

json.dump({"blocks": blocks, "rows": rows}, open(OUT, "w"))
print(f"sampled {len(blocks)} blocks ({start}..{start+N-1}); create-blocks {sum(1 for b in blocks if b['creates'])}; same-slot buyer txs {len(rows)}")
cl = collections.Counter(b["client"] for b in blocks)
print("leader clients in sample:", dict(cl))
by = collections.defaultdict(list)
for r in rows:
    by[r["prov"]].append(r)
print(f"{'sender(tip acct)':24s} {'n':>4s} {'ok%':>5s} {'med nv_idx':>10s} {'med frac':>8s} {'med gap after create':>20s}")
for p, rs in sorted(by.items(), key=lambda x: statistics.median([r['nv_idx'] / max(1, r['nonvote']) for r in x[1]])):
    fr = statistics.median([r["nv_idx"] / max(1, r["nonvote"]) for r in rs])
    print(f"{p:24s} {len(rs):4d} {100*sum(r['ok'] for r in rs)/len(rs):5.0f} {statistics.median([r['nv_idx'] for r in rs]):10.0f} {fr:8.2f} {statistics.median([r['idx']-r['create_idx'] for r in rs]):20.0f}")
print("by leader client (median nonvote-position fraction of same-slot buyers, per sender, n>=3):")
bc = collections.defaultdict(list)
for r in rows:
    bc[(r["client"], r["prov"])].append(r["nv_idx"] / max(1, r["nonvote"]))
for (c, p), v in sorted(bc.items()):
    if len(v) >= 3:
        print(f"  {c:20s} {p:24s} n={len(v):4d} med_frac={statistics.median(v):.2f}")
