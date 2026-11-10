#!/usr/bin/env python3
"""APEX-PROBE entry score validation input: raw create + creator-bundle txs of recorded launches, for
`apex_probe --entry-validate CASES --entry-txs OUT` (the probe derives dev / bundle / CreateEvent creator from the txs
exactly as it does from the shreds and compares with the APEX-3 tape values).

Cases: entry_export.py's entry_cases.jsonl (one recorded day). Bundle txs = the tape's rule (s3_sim): the successful txs at
create index +1, +2, ... (consecutive) in the create slot that touch the mint; sigs from the collector's txs chunks.
Raw txs: getTransaction (json, maxSupportedTransactionVersion 1) from --rpc (default: the public mainnet RPC; no keys).
usage: entry_fetch_txs.py CASES OUT [--collect RUNDIR] [--n 260] [--rpc URL] [--seed 7]
"""
import sys, os, json, gzip, re, glob, time, random, base64, urllib.request, collections

a = sys.argv[1:]
def opt(k, d):
    if k in a: i = a.index(k); v = a[i + 1]; del a[i:i + 2]; return v
    return d
RUN = opt("--collect", "/data/tapes/collect/run_20261103_1245")
N = int(opt("--n", "260")); RPC = opt("--rpc", "https://api.mainnet-beta.solana.com"); SEED = int(opt("--seed", "7"))
CASES, OUT = a[0], a[1]
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def d58(s):
    n = 0
    for c in s: n = n * 58 + A58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big"); return b"\0" * (len(s) - len(s.lstrip("1"))) + b

C = [json.loads(l) for l in open(CASES)]
rng = random.Random(SEED)
g1 = [c for c in C if c["sel"] and c["nb"] > 0]; g2 = [c for c in C if c["sel"] and c["nb"] == 0]; g3 = [c for c in C if not c["sel"] and c["nb"] > 0]
for g in (g1, g2, g3): rng.shuffle(g)
pick = g1[:int(N * .58)] + g2[:int(N * .27)]
pick += g3[:N - len(pick)]
print(f"cases {len(pick)}: picks with bundle {min(len(g1), int(N * .58))}, picks w/o {min(len(g2), int(N * .27))}, non-picks with bundle {len(pick) - min(len(g1), int(N * .58)) - min(len(g2), int(N * .27))}", flush=True)

# ---- bundle sigs from the tape chunks (only the chunks / slots needed)
chunks = sorted(glob.glob(f"{RUN}/txs/txs_*.jsonl.gz")); starts = [int(re.search(r"txs_(\d+)", f).group(1)) for f in chunks]
need = collections.defaultdict(set)   # chunk -> slots
for c in pick:
    k = max(i for i, s in enumerate(starts) if s <= c["bt"] + 5) if any(s <= c["bt"] + 5 for s in starts) else 0
    for kk in (k - 1, k, k + 1):
        if 0 <= kk < len(chunks): need[chunks[kk]].add(c["slot"])
HEAD = re.compile(r'\{"s":(\d+),"i":(\d+)')
slotrec = collections.defaultdict(dict)  # slot -> idx -> (sig, err, mints)
t0 = time.time()
for f in sorted(need):
    S = need[f]
    with gzip.open(f, "rt") as fh:
        for line in fh:
            m = HEAD.match(line)
            if not m or int(m.group(1)) not in S: continue
            r = json.loads(line); slotrec[r["s"]][r["i"]] = (r["sig"], r.get("err"), r.get("mints") or [])
print(f"tape: {len(need)} chunks scanned, {time.time() - t0:.0f} s", flush=True)

def rpc(sig):
    q = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}]}).encode()
    for k in range(8):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(RPC, q, {"content-type": "application/json"}), timeout=30))
            if r.get("result"): return r["result"]
        except Exception: pass
        time.sleep(1.5 * (k + 1))
    return None

def txj(res, sig):
    m = res["transaction"]["message"]; la = res["meta"].get("loadedAddresses") or {}; h = m["header"]
    return dict(sig=sig, keys=m["accountKeys"], lw=la.get("writable", []), lr=la.get("readonly", []),
                hdr=[h["numRequiredSignatures"], h["numReadonlySignedAccounts"], h["numReadonlyUnsignedAccounts"]],
                ixs=[[ix["programIdIndex"], ix["accounts"], base64.b64encode(d58(ix["data"])).decode()] for ix in m["instructions"]])

done = set()
if os.path.exists(OUT):
    for l in open(OUT): done.add(json.loads(l)["mint"])
nf = 0
with open(OUT, "a") as fo:
    for j, c in enumerate(pick):
        if c["mint"] in done: continue
        recs = slotrec.get(c["slot"], {})
        cr = recs.get(c["idx"])
        if not cr: print("no create in tape", c["mint"]); continue
        bs = []; k = c["idx"] + 1
        while k in recs and recs[k][1] is None and c["mint"] in recs[k][2]: bs.append(recs[k][0]); k += 1
        res = rpc(cr[0])
        if not res: nf += 1; print("fetch failed", c["mint"], flush=True); continue
        out = dict(mint=c["mint"], create=txj(res, cr[0]), bundle=[])
        ok = True
        for s in bs:
            rb = rpc(s)
            if not rb: ok = False; break
            out["bundle"].append(txj(rb, s)); time.sleep(0.15)
        if not ok: nf += 1; print("bundle fetch failed", c["mint"], flush=True); continue
        fo.write(json.dumps(out) + "\n"); fo.flush()
        if j % 20 == 0: print(f"{j}/{len(pick)} fetched ({time.time() - t0:.0f} s)", flush=True)
        time.sleep(0.15)
print(f"done: {OUT} ({nf} failed)", flush=True)
