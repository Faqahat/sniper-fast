#!/usr/bin/env python3
# READ-ONLY, offline: 9qz7cW's transaction machinery from the collector's raw txs (raw_q9z.jsonl.gz) + the RPC signature
# list (error codes) + fetched txs (txc/, for nonce accounts / tip recipients / priority fees outside the collector).
#  - landed buys by variant: direct pump.fun buy + durable nonce with (Jito tip | priority fee | transfer to another
#    account) vs the router program 2eFuLSK4 (no nonce, 0.001 SOL landing-service tip)
#  - failed txs by error (program, code) and kind (buy / sell), with their fees
#  - visible copies per buy (failed copies on the same mint in the same or next slot)
#  - nonce accounts, tip recipients, CU limits, tx version
import os, json, gzip, glob, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
ROUTER = "2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; PAMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
S = json.load(open(os.path.join(HERE, "sigs.json"))); ERR = {s["signature"]: s.get("err") for s in S}
RAW = [json.loads(l) for l in gzip.open(os.path.join(HERE, "raw_q9z.jsonl.gz"), "rt")]
def q(xs, ps=(0.1, 0.25, 0.5, 0.75, 0.9)):
    xs = sorted(x for x in xs if x is not None)
    return [round(xs[int(p * (len(xs) - 1))], 6) for p in ps] if xs else None
def ekey(e):
    if not e: return None
    ie = e.get("InstructionError") if isinstance(e, dict) else None
    if ie: return f"ix{ie[0]}:{ie[1] if isinstance(ie[1], str) else 'Custom ' + str(ie[1].get('Custom'))}"
    return json.dumps(e)[:40]
def kind(r):
    ix = r[11]; pr = r[10]
    if any("Buy" in x for x in ix): return "buy"
    if any("Sell" in x for x in ix): return "sell"
    if ROUTER in pr and PUMP not in pr and PAMM not in pr: return "router (sell-shaped, no pump call)"
    if PUMP in pr and ROUTER not in pr: return "direct pump (buy-shaped)"
    if ROUTER in pr: return "router + pump/AMM"
    return "other"
print("== raw collector txs signed by it:", len(RAW), "successful", sum(1 for r in RAW if not r[5]), "failed", sum(1 for r in RAW if r[5]))
print("   n signers per tx:", collections.Counter(r[15] for r in RAW))
# ---- landed buys by variant
B = [r for r in RAW if not r[5] and any("Buy" in x for x in r[11])]
var = collections.Counter(); spend = collections.defaultdict(list)
for r in B:
    prio = (r[6] or 5000) - 5000; tips = [(TM.get(a), l) for a, l in r[12]]
    if ROUTER in r[10]: v = "router 2eFuLSK4 (tip %s)" % ("/".join(sorted({t for t, _ in tips})) or "none")
    elif any(t == "jito" for t, _ in tips): v = "direct + Jito tip"
    elif prio > 0: v = "direct + priority fee"
    else: v = "direct, other transfer (e.g. b1ooMngj)"
    var[v] += 1; spend[v].append((prio + sum(l for _, l in tips)) / 1e9)
print("\n== landed buys by variant (collector):")
for v, n in var.most_common(): print(f"   {v:42} {n:5d}  spend SOL q {q(spend[v])}")
# ---- failed txs by error and kind
F = [r for r in RAW if r[5]]
g = collections.defaultdict(lambda: [0, 0])
for r in F:
    k = (kind(r), ekey(ERR.get(r[4])) or "?")
    g[k][0] += 1; g[k][1] += (r[6] or 0)
print("\n== failed txs in the collector by kind and error (count, total fee SOL, mean fee):")
for k, (n, fee) in sorted(g.items(), key=lambda kv: -kv[1][0])[:18]:
    print(f"   {k[0]:36} {k[1]:24} {n:6d}  {fee / 1e9:8.3f}  {fee / n / 1e9:.6f}")
print(f"   total failed fee {sum(r[6] or 0 for r in F) / 1e9:.2f} SOL on {len(F)} txs")
allerr = collections.Counter(ekey(s.get("err")) for s in S if s.get("err"))
print("\n== all failed signatures (RPC list, 2.6 days):", sum(allerr.values()))
for k, n in allerr.most_common(12): print(f"   {k:28} {n}")
# ---- visible copies per landed buy: its other txs on the same mint in the same / next slot
bym = collections.defaultdict(list)
for r in RAW:
    if r[9]: bym[r[9][0]].append(r)
cp = []; cp_err = collections.Counter(); cp_kind = collections.Counter()
for r in B:
    same = [x for x in bym[r[9][0]] if x is not r and x[5] and 0 <= x[1] - r[1] <= 1 and kind(x) in ("buy", "direct pump (buy-shaped)", "router + pump/AMM", "other")]
    cp.append(len(same))
    for x in same: cp_err[ekey(ERR.get(x[4]))] += 1; cp_kind[kind(x)] += 1
print("\n== failed buy copies visible on chain per landed buy (same mint, same or next slot):", collections.Counter(min(c, 5) for c in cp).most_common(), "| their errors", cp_err.most_common(6), cp_kind.most_common(4))
# ---- failed SELL copies right after each landed sell
SL = [r for r in RAW if not r[5] and any("Sell" in x for x in r[11])]
sc = []
for r in SL:
    sc.append(sum(1 for x in bym[r[9][0]] if x[5] and 0 <= x[1] - r[1] <= 1 and kind(x).startswith("router (sell")))
print("== failed sell copies (router, same/next slot) per landed sell:", collections.Counter(min(c, 6) for c in sc).most_common(), "mean", round(statistics.mean(sc), 2))
print("   landed sells:", len(SL), "tips on sells:", collections.Counter("/".join(sorted({TM.get(a, a[:6]) for a, _ in r[12]})) or "none" for r in SL).most_common(6), "fee q", q([r[6] for r in SL]))
# ---- fetched txs: nonce accounts, tip recipients, versions, CU limit margin
NON = collections.Counter(); REC = collections.Counter(); VER = collections.Counter(); CUM = []; PRI = []
for f in glob.glob(os.path.join(HERE, "txc", "*.json.gz"))[:6000]:
    try: tx = json.load(gzip.open(f, "rt"))
    except Exception: continue
    VER[tx.get("version")] += 1
    m = tx["transaction"]["message"]; meta = tx["meta"]
    isbuy = any("Instruction: Buy" in l for l in meta.get("logMessages") or [])
    for ix in m["instructions"]:
        p = ix.get("parsed")
        if isinstance(p, dict) and p.get("type") == "advanceNonce": NON[p["info"]["nonceAccount"]] += 1
        if isbuy and isinstance(p, dict) and p.get("type") == "transfer" and p["info"].get("source") == W: REC[TM.get(p["info"]["destination"], p["info"]["destination"])] += 1
    cfg = m.get("transactionConfig") or {}
    if isbuy and meta.get("err") is None and cfg.get("computeUnitLimit") and meta.get("computeUnitsConsumed"): CUM.append(cfg["computeUnitLimit"] - meta["computeUnitsConsumed"])
    if isbuy and meta.get("err") is None: PRI.append((cfg.get("priorityFee") or 0) / 1e9)
print("\n== fetched txs (outside the collector):", sum(VER.values()), "versions", VER)
print("   durable-nonce accounts used:", NON.most_common(8))
print("   transfer recipients inside buy txs:", REC.most_common(12))
print("   buy CU limit minus CU used q", q(CUM), "| priority fee field (SOL) on landed buys q", q(PRI))
