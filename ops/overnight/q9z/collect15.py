#!/usr/bin/env python3
# READ-ONLY: data for the HTML page on 9qz7cW's last N create-slot snipes (SOL-quoted, filled, R2 collector window).
# Per snipe: token, creator, create tx, dev buy + glued bundle, its buy (position after the bundle, rank among outside
# buyers of the block, size, priority fee, tips by landing service, nonce, CU, version), every buyer of the create block
# (role, position, wallet, SOL, priority, tips, tx), its sells (time, share, price multiple) and the realized SOL result
# (exact lamport deltas of all its txs on the mint). Sources: collector rows (rp.read_bucket), raw collector txs (tips
# by account), owner's RPC for its buy txs (paced). -> snipes15.json
import sys, os, json, gzip, glob, zlib, collections, re
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("Q9Z_RATE", "0.6")
import rp
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json"))); L = rp.load_launches(); O = rp.load_obs()
picks = sorted([r for r in PL.values() if r["run"] == "R2" and r["beh"] == "snipe" and r["off"] == 0 and r["filled"] and r["quote"] == "SOL" and r.get("buy_sig") and r.get("d_slot") == 0],
               key=lambda r: -r["bt"])[:N]
mints = {r["m"] for r in picks}
# raw txs of these mints (tips by account, signers) - one pass over the R2 raw files
D = "/home/moiz/sniper-data/collect/run_20261022_1543/txs"
SL = {r["m"]: r["S"] for r in picks}
def work(f):
    out = {}
    try:
        for line in gzip.open(f, "rt"):
            if not any(m in line for m in mints): continue
            r = json.loads(line)
            ms = [m for m in (r.get("mints") or []) if m in mints]
            if not ms or r["s"] - SL[ms[0]] > 1: continue
            out[r["sig"]] = dict(s=r["s"], i=r["i"], fee=r.get("fee"), tips=r.get("tips") or [], signers=r.get("signers") or [], cu=r.get("cu"), err=r.get("err"), progs=r.get("progs") or [])
    except (EOFError, OSError, zlib.error): pass
    return out
from multiprocessing import Pool
RAWX = {}
lo = min(r["bt"] for r in picks) - 900; hi = max(r["bt"] for r in picks) + 900
files = [f for f in sorted(glob.glob(os.path.join(D, "*.jsonl.gz"))) if lo <= int(re.findall(r"(\d+)", os.path.basename(f))[0]) <= hi]
with Pool(8) as p:
    for o in p.imap_unordered(work, files): RAWX.update(o)
print("raw txs for the picks:", len(RAWX), "from", len(files), "files", flush=True)
byb = collections.defaultdict(set)
for m in mints: byb[rp.bucket(m)].add(m)
TR = {}
for b, ms in byb.items(): TR.update(rp.read_bucket("R2", b, ms))
out = []
for p in picks:
    m = p["m"]; c = L[m]; tr = TR.get(m, []); S = c["slot"]; st = rp.structure(tr, c)
    blk = []; ins = st["insiders"]; gsigs = {t["sig"] for t in st["glued"]}
    seen = set(); bundle_last_i = max([t["i"] for t in tr if t["sig"] in gsigs or t["sig"] == c.get("sig")] or [c.get("idx") or 0])
    for t in tr:
        if t["s"] != S or not t["buy"] or t["sig"] in seen: continue
        seen.add(t["sig"]); rx = RAWX.get(t["sig"], {})
        role = "dev (create)" if t["sig"] == c.get("sig") else ("dev bundle" if t["sig"] in gsigs else ("insider" if t["user"] in ins else "sniper"))
        tips = [(TM.get(a, a[:6]), l / 1e9) for a, l in rx.get("tips", [])]
        blk.append(dict(i=t["i"], pos=t["i"] - bundle_last_i, role=role, who=t["user"], sol=t["sol"] / 1e9, prio=max(0, (t["fee"] or 5000) - 5000) / 1e9, tips=tips, sig=t["sig"]))
    me = next((b for b in blk if b["who"] == W), None)
    outs = [b for b in blk if b["role"] == "sniper"]
    rank = 1 + sum(1 for b in outs if me and b["i"] < me["i"])
    bt = rpc("getTransaction", [p["buy_sig"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    nonce = ver = cu = cul = prio = None; tip_to = []
    if bt:
        mm = bt["transaction"]["message"]; ver = bt.get("version"); cu = bt["meta"].get("computeUnitsConsumed")
        cfg = mm.get("transactionConfig") or {}; cul = cfg.get("computeUnitLimit"); prio = (cfg.get("priorityFee") or 0) / 1e9
        for ix in mm["instructions"]:
            pp = ix.get("parsed")
            if isinstance(pp, dict) and pp.get("type") == "advanceNonce": nonce = pp["info"]["nonceAccount"]
            if isinstance(pp, dict) and pp.get("type") == "transfer" and pp["info"].get("source") == W: tip_to.append((TM.get(pp["info"]["destination"], pp["info"]["destination"]), pp["info"]["destination"], pp["info"]["lamports"] / 1e9))
    arr = None
    if m in O:
        mo = sorted(x for x in O[m]["outs"] if x[3] == "9qz7cW"); arr = mo[0][0] if mo else None
    out.append(dict(mint=m, name=c.get("name"), symbol=c.get("symbol"), creator=c.get("creator"), signer=c.get("user"), create_sig=c.get("sig"), S=S, create_bt=c.get("bt"),
                    dev_sol=p.get("dev_sol"), bundle_sol=p.get("bundle_sol"), bundle_txs=p.get("bundle_txs"), buy_sig=p["buy_sig"], buy_bt=c.get("bt"), size=p["buy_sol"],
                    pos=me["pos"] if me else None, rank=rank, n_out=len(outs), prio=prio, tip_to=tip_to, nonce=nonce, version=ver, cu=cu, cul=cul, arr_ms=arr,
                    sells=p.get("sells") or [], result=p["sol_result"], n_fail=p["n_fail"], fail_fee=p["fail_fee"], block=blk, ahead=p.get("ahead"), entry_x=p.get("entry_x")))
    print(f"{(c.get('symbol') or '')[:10]:10} S {S} pos {me['pos'] if me else None} rank {rank}/{len(outs)} size {p['buy_sol']:.3f} prio {prio} tips {tip_to} v{ver} nonce {bool(nonce)} sells {len(p.get('sells') or [])} result {p['sol_result']:+.3f} arr {arr}", flush=True)
json.dump(dict(wallet=W, snipes=out), open(os.path.join(HERE, "snipes15.json"), "w"), indent=1)
