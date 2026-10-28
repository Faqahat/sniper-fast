#!/usr/bin/env python3
"""recon step 13 (read-only): from the RPC sample (gettx*.jsonl): durable-nonce account, pump instruction args
(buy_exact_sol_in: spendable_sol_in, min_tokens_out; sell: amount, min_sol_output), slippage vs fill, tip ix position.
Then the sell-matches-buy test on nonce account and slippage code. Out: ixs.pkl, r13.txt"""
import json, pickle, struct, collections, random, glob
import numpy as np
from r5_rpc import b58d
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"; PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
L = pickle.load(open(f"{OUT}/lots.pkl", "rb")); s2l = {}
for l in L:
    s2l[l["buy_sig"]] = (l, "buy")
    for s in l["sells"]: s2l[s[0]] = (l, "sell")
TX = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
X = {}
for fn in glob.glob(f"{OUT}/gettx*.jsonl"):
    for line in open(fn):
        j = json.loads(line); r = j.get("res")
        if not r or j["sig"] not in s2l: continue
        m = r["transaction"]["message"]
        if m["accountKeys"][0]["pubkey"] != H: continue
        ins = m["instructions"]; d = dict(sig=j["sig"], nonce=None, args=None, disc=None, n_ix=len(ins), bh=m["recentBlockhash"])
        if isinstance(ins[0].get("parsed"), dict) and ins[0]["parsed"]["type"] == "advanceNonce": d["nonce"] = ins[0]["parsed"]["info"]["nonceAccount"]
        for x in ins:
            if x.get("programId") == PUMP:
                b = b58d(x["data"]); d["disc"] = b[:8].hex(); d["args"] = [struct.unpack_from("<Q", b, 8 + 8 * k)[0] for k in range((len(b) - 8) // 8)]; d["argtail"] = b[8 + 8 * ((len(b) - 8) // 8):].hex()
        l, side = s2l[j["sig"]]; d["side"] = side; d["lot"] = l["lot_id"]; d["bot"] = l["bot"]
        t = TX.get(j["sig"])
        if t and t["events"] and d["args"]:
            e = t["events"][0]
            if side == "buy": d["slip"] = d["args"][1] / e["tok"] if e["tok"] else None; d["spend"] = d["args"][0]
            else: d["slip"] = d["args"][1] / e["sol"] if e["sol"] else None; d["amt_vs_tok"] = d["args"][0] / e["tok"] if e["tok"] else None
        X[j["sig"]] = d
pickle.dump(X, open(f"{OUT}/ixs.pkl", "wb"))
print("decoded", len(X), collections.Counter((d["side"], d["disc"], len(d["args"] or []), d["argtail"] if d["args"] else None, d["nonce"] is not None) for d in X.values()))
for side in ("buy", "sell"):
    v = [d for d in X.values() if d["side"] == side and d.get("slip")]
    print(side, "min_out / actual p5/50/95:", np.percentile([d["slip"] for d in v], [5, 25, 50, 75, 95]).round(4) if v else None)
    for b in ("FRESH", "MINUTE", "OLD"):
        w = [d["slip"] for d in v if d["bot"] == b]
        if w: print("  ", b, len(w), np.percentile(w, [10, 50, 90]).round(4))
print("nonce accounts:", collections.Counter(d["nonce"] for d in X.values()).most_common(30))
# sell-matches-buy on nonce
pairs = []
for l in L:
    b = X.get(l["buy_sig"]); ss = [X.get(s[0]) for s in l["sells"]]
    if b and ss and ss[0]: pairs.append((b["nonce"], ss[0]["nonce"]))
if pairs:
    same = np.mean([a == b for a, b in pairs]); sh = [p[1] for p in pairs]
    rs = []
    for k in range(200):
        random.shuffle(sh); rs.append(np.mean([a == b for (a, _), b in zip(pairs, sh)]))
    print(f"nonce sell==buy: {same:.2f} on {len(pairs)} lots; shuffled {np.mean(rs):.2f}")
