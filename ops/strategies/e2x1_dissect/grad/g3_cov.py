#!/usr/bin/env python3
"""grad agent, step 3: COVERAGE CHECK of recorded PumpSwap trades vs public RPC (read-only).
For ~10 graduated tokens: every successful tx touching the pool in the first 2 minutes after the migration tx
(getSignaturesForAddress on the pool, public RPC) vs the recorder's PumpSwap Buy/Sell events for that pool.
Misses are checked: is the tx in the raw recording at all? does it really contain a PumpSwap trade on that pool (getTransaction)?
Writes /home/moiz/sniper-data/e2x1_dissect/grad/cov.json"""
import sys, os, json, pickle, glob, gzip, hashlib, random, base64, struct
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/recon")
import rpc

G = "/home/moiz/sniper-data/e2x1_dissect/grad"
WIN = 566                       # 2 min of slots (0.212 s/slot)
BUYE = bytes.fromhex("67f4521f2cf57777"); SELLE = bytes.fromhex("3e2f370aa503dc2a")
def sigh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")

Z = np.load(G + "/tape.npz"); M = pickle.load(open(G + "/meta.pkl", "rb"))
PS = Z["ps"]; pools = M["pools"]; pid = {p: k for k, p in enumerate(pools)}
lots = pickle.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/lots.pkl", "rb"))
gm = [l["mint"] for l in lots if l.get("swap_sell") and l["day"] == "D1"]
mig_by_mint = {d["mint"]: d for d in M["mig"]}
pick = [mig_by_mint[m] for m in gm if m in mig_by_mint][:6]
random.seed(7)
others = [d for d in M["mig"] if d["quote"].startswith("So111") and 1793113200 <= d["bt"] <= 1793196000 and d["mint"] not in gm]
pick += random.sample(others, 5)

chunks = sorted(glob.glob("/home/moiz/sniper-data/collect/run_202610*_14*/txs/*.jsonl.gz"))
cstart = [(int(os.path.basename(c)[4:14]), c) for c in chunks]
def raw_lines(pool, bt0, bt1):
    """recorded raw lines mentioning the pool between block times bt0..bt1 (chunks overlapping)"""
    out = {}
    for t, c in cstart:
        if t > bt1 + 5 or t + 330 < bt0: continue
        with gzip.open(c, "rt") as f:
            for line in f:
                if pool in line:
                    r = json.loads(line); out[r["sig"]] = (r["s"], r["err"])
    return out

res = []
for d in pick:
    pool, s0 = d["pool"], d["slot"]
    p = pid.get(pool)
    rec = PS[(PS["pool"] == p) & (PS["slot"] >= s0) & (PS["slot"] <= s0 + WIN)] if p is not None else PS[:0]
    rec_h = set(int(x) for x in rec["sigh"])
    raw = raw_lines(pool, d["bt"] - 5, d["bt"] + 200)
    after = sorted([(s, sg) for sg, (s, e) in raw.items() if s > s0 + WIN])
    before = after[0][1] if after else None
    sigs = []; cur = before
    for page in range(30):
        prm = {"limit": 1000, "until": d["sig"]}
        if cur: prm["before"] = cur
        j = rpc.call("getSignaturesForAddress", [pool, prm])
        r = j.get("result") or []
        sigs += r
        if len(r) < 1000: break
        cur = r[-1]["signature"]
        if r[-1]["slot"] < s0: break
    win = [x for x in sigs if s0 <= x["slot"] <= s0 + WIN]
    ok = [x for x in win if x.get("err") is None]
    miss = [x for x in ok if sigh(x["signature"]) not in rec_h]
    miss_raw = [x for x in miss if x["signature"] not in raw]
    # check a few misses: do they hold a PumpSwap trade on this pool?
    chk = []
    rs = random.Random(11); smp = rs.sample(miss, min(25, len(miss)))
    for x in smp:
        t = rpc.call("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}]).get("result")
        if not t: chk.append((x["signature"], "no tx")); continue
        logs = t["meta"].get("logMessages") or []
        nev = 0
        for l in logs:
            if l.startswith("Program data: "):
                b = base64.b64decode(l[14:] + "=" * (-len(l[14:]) % 4))
                if b[:8] in (BUYE, SELLE): nev += 1
        trunc = any("Log truncated" in l for l in logs)
        chk.append((x["signature"], dict(ps_events=nev, log_truncated=trunc, in_raw=x["signature"] in raw, version=t.get("version"),
                                         ixn=[l[26:] for l in logs if l.startswith("Program log: Instruction: ")][:6])))
    n_tr = sum(1 for _, c in chk if isinstance(c, dict) and c["ps_events"] > 0)
    row = dict(n_checked=len(chk), n_checked_with_trade=n_tr, est_missed_trades=round(len(miss) * n_tr / max(len(chk), 1)), sigs=[x["signature"] for x in ok], mint=d["mint"], pool=pool, mig_slot=s0, mig_bt=d["bt"], e2x1=d["mint"] in gm, rpc_txs=len(win), rpc_ok=len(ok),
               rec_events=len(rec), rec_txs=len(rec_h), rpc_ok_recorded=len(ok) - len(miss), miss=len(miss), miss_not_in_raw=len(miss_raw),
               raw_lines=sum(1 for s, e in raw.values() if s0 <= s <= s0 + WIN), check=chk)
    print(json.dumps({k: v for k, v in row.items() if k not in ("check", "sigs")}), flush=True)
    for c in chk:
        if isinstance(c[1], dict) and c[1]["ps_events"] > 0: print("   TRADE MISSED", c, flush=True)
    res.append(row)
json.dump(res, open(G + "/cov.json", "w"), indent=1)
tot_rec = sum(r["rpc_ok_recorded"] for r in res); est = sum(r["est_missed_trades"] for r in res)
print(f"TOTAL recorded trade txs {tot_rec}; RPC-only txs {sum(r['miss'] for r in res)}, sampled {sum(r['n_checked'] for r in res)} of them, "
      f"{sum(r['n_checked_with_trade'] for r in res)} held a PumpSwap trade -> est. missed trades {est}; coverage ~ {tot_rec / max(tot_rec + est, 1):.1%}")
