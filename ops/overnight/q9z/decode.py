#!/usr/bin/env python3
# READ-ONLY: decode a few of 9qz7cW's buy / sell / failed transactions instruction by instruction (version, signers,
# fee, compute budget, nonce vs blockhash, tips by landing service, programs, CU, pump.fun trade events, error logs).
# Picks samples from the collector rows (rows_q9z.json + attempts_q9z.json). -> decoded.json + printed summary.
# usage: Q9Z_RATE=0.6 python3 -I decode.py
import sys, os, json, gzip, base64, collections, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
def trade_events(tx):
    out = []
    for l in (tx.get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != TD or len(raw) < 129: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58(raw[8:40]), sol=u(40) / 1e9, tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), ts=int.from_bytes(raw[89:97], "little", signed=True),
                        vsol=u(97) / 1e9, vtok=u(105)))
    return out
def summarize(sig, tx):
    m = tx["transaction"]["message"]; meta = tx["meta"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in m["accountKeys"]]
    signers = [k["pubkey"] for k in m["accountKeys"] if isinstance(k, dict) and k.get("signer")]
    ixs = []
    for ix in m["instructions"]:
        p = ix.get("parsed"); pid = ix.get("programId")
        if isinstance(p, dict):
            info = p.get("info") or {}
            d = dict(prog=pid[:10], type=p.get("type"))
            if p.get("type") == "transfer" and "lamports" in info:
                d.update(to=info.get("destination"), sol=info["lamports"] / 1e9, svc=TM.get(info.get("destination"), ""))
            if p.get("type") == "advanceNonce": d.update(nonce=info.get("nonceAccount"), auth=info.get("nonceAuthority"))
            if p.get("type") in ("createAccountWithSeed", "createAccount"): d.update(lamports=info.get("lamports"), space=info.get("space"), seed=info.get("seed"))
            ixs.append(d)
        else:
            ixs.append(dict(prog=pid, data=(ix.get("data") or "")[:24], nacc=len(ix.get("accounts") or [])))
    inner = collections.Counter()
    for inn in meta.get("innerInstructions") or []:
        for ix in inn["instructions"]:
            p = ix.get("parsed")
            inner[(ix.get("programId") or "")[:12] + ":" + (p.get("type") if isinstance(p, dict) else "raw")] += 1
    i = keys.index(W) if W in keys else None
    errlog = [l for l in meta.get("logMessages") or [] if "rror" in l or "failed" in l][:4]
    return dict(sig=sig, slot=tx["slot"], bt=tx.get("blockTime"), version=tx.get("version"), fee=meta["fee"], err=meta.get("err"), cu=meta.get("computeUnitsConsumed"),
                signers=signers, nkeys=len(keys), blockhash=m.get("recentBlockhash"), ixs=ixs, inner=dict(inner),
                sol_chg=(meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else None,
                events=trade_events(tx), errlog=errlog, lut=bool(m.get("addressTableLookups")), logs_n=len(meta.get("logMessages") or []))
if __name__ == "__main__":
    R = json.load(open(os.path.join(HERE, "rows_q9z.json"))); A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_q9z.json"))
    L = {}
    for run in ("run_20261021_2207", "run_20261022_1543"):
        for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            L.setdefault(c["mint"], c)
    random.seed(3)
    buys = [t for t in R["T"] if t[16] == 1 and t[2] in L]
    def off(t): return t[3] - L[t[2]]["slot"]
    pick = {}
    pick["buy_d0"] = random.sample([t[6] for t in buys if off(t) == 0], 4)
    pick["buy_d1"] = random.sample([t[6] for t in buys if off(t) == 1], 2)
    pick["buy_late"] = random.sample([t[6] for t in buys if off(t) >= 5], 3)
    sells = [t for t in R["T"] if t[16] == 0]
    pick["sell"] = random.sample([t[6] for t in sells], 4)
    X = [x for x in R["X"] if x[13] == 1]
    # failed: by ixn pattern (empty = fast fail in its program; with Buy = pump-level failure)
    pick["fail_fast"] = random.sample([x[6] for x in X if not x[14]], 3)
    pick["fail_pump"] = random.sample([x[6] for x in X if "BuyExactQuoteInV3" in x[14]], 3)
    pick["fail_bigfee"] = random.sample([x[6] for x in X if x[8] > 5_000_000], 2)
    out = {}
    for k, sigs in pick.items():
        for s in sigs:
            tx = rpc("getTransaction", [s, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
            if not tx: print("miss", k, s); continue
            with gzip.open(os.path.join(HERE, "txc", s + ".json.gz"), "wt") as f: json.dump(tx, f)
            d = summarize(s, tx); d["kind"] = k; out[s] = d
            print(f"\n== {k} {s[:16]} slot {d['slot']} v{d['version']} fee {d['fee']} cu {d['cu']} err {d['err']} signers {len(d['signers'])} lut {d['lut']} solchg {d['sol_chg']}")
            for ix in d["ixs"]: print("   ", ix)
            print("    inner", d["inner"])
            for e in d["events"]: print("    ev", {k2: v for k2, v in e.items() if k2 != 'mint'}, e["mint"][:8])
            for l in d["errlog"]: print("    log", l[:160])
    json.dump(out, open(os.path.join(HERE, "decoded.json"), "w"), indent=1)
