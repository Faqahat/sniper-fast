#!/usr/bin/env python3
# READ-ONLY: (1) the wallet's first transactions (public mainnet-beta has the full history) -> who funded it and how;
# (2) upgrade authority of each of its programs; (3) the nonce account's creator; (4) quick looks at linked wallets.
import sys, os, json, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
W = rpcu.W
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58e(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
OLD = json.load(open("sigs_FiFawH_old.json")); first = list(reversed(OLD[-60:]))     # 60 oldest, oldest first
os.makedirs("txc_first", exist_ok=True); out = {"first_txs": []}
def gettx(sig, ep):
    f = os.path.join("txc_first", sig + ".json")
    if os.path.exists(f): return json.load(open(f))
    try: t = rpcu.rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=ep, tries=3)
    except RuntimeError: return None                     # public RPC rate limit: skip (the 50 oldest are cached)
    if t: json.dump(t, open(f, "w"))
    time.sleep(0.35); return t
for s in first:
    t = gettx(s["signature"], rpcu.PUB)
    if not t: continue
    m = t["transaction"]["message"]; meta = t["meta"]; keys = [k["pubkey"] for k in m["accountKeys"]]
    i = keys.index(W) if W in keys else None
    xf = []
    for ix in m["instructions"] + [ix for g in (meta.get("innerInstructions") or []) for ix in g["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and isinstance(p.get("info"), dict):
            inf = p["info"]
            if p.get("type") in ("transfer", "transferChecked", "createAccount", "createAccountWithSeed") and (W in (inf.get("source"), inf.get("destination"), inf.get("authority"), inf.get("newAccount")) or inf.get("multisigAuthority") == W):
                xf.append(dict(type=p["type"], src=inf.get("source"), dst=inf.get("destination") or inf.get("newAccount"), lamports=inf.get("lamports"), amt=(inf.get("tokenAmount") or {}).get("uiAmount") or inf.get("amount"), mint=inf.get("mint")))
    out["first_txs"].append(dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), err=meta.get("err") is not None, signer=[k["pubkey"] for k in m["accountKeys"] if k.get("signer")],
                                 sol_chg=(meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else None, post_bal=meta["postBalances"][i] / 1e9 if i is not None else None,
                                 progs=[ix.get("programId") for ix in m["instructions"]], xfers=xf, logs=[l for l in (meta.get("logMessages") or []) if "Instruction:" in l][:6]))
# program upgrade authorities
PROGS = {"B78FW9mVQT2fDhsW7ChvqTBhZzhCbRrtWYC6K5oa7xuv": "buy (SOL-quoted, guarded)", "9f2uHxWdaB5nRgjRgsUe4T1LtyzejLNnxuzLfvyMyyxP": "buy (SOL-quoted)",
         "9uGqm7Xh7Vq2EzqTNHVG5Ca4echELK1UjDq9W9Qg5kzF": "buy (other-quote: swap + buy)", "5gP7LHpRndFJSjANFB2ZBJtPJ3KhcPf2xgSNKVD7tAfK": "buy (LaunchLab: swap + buy)",
         "2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG": "sell (SOL-quoted, by %)", "6iemSi2wHcEJoAwEdG69VznRPGHWJr6Y2VRSyj6m9h45": "sell (other-quote: sell + swap)",
         "BCzSQSmV988WPnCM6MXToLvBaL8dmj8uJWG1MaceenvX": "sell (LaunchLab: sell + swap)", "F7hMV94qDyUXuv5HirXYJhU59AjuPfJMFaZFbwzLD62r": "copy-bot program used by DeFG8i (references FiFawH)",
         "FATLh4eHQa4QnB56KxiyGJTTzdj9zBo6kN5DdhzXtBne": "DxhpC9c4's program (shares the AsTz tip account)"}
out["programs"] = {}
for p, what in PROGS.items():
    try:
        a = rpcu.rpc("getAccountInfo", [p, {"encoding": "jsonParsed"}])["value"]
        pd = a["data"]["parsed"]["info"]["programData"] if a and isinstance(a["data"], dict) else None
        info = rpcu.rpc("getAccountInfo", [pd, {"encoding": "jsonParsed", "dataSlice": {"offset": 0, "length": 0}}])["value"] if pd else None
        ua = info["data"]["parsed"]["info"].get("authority") if info and isinstance(info.get("data"), dict) else None
        slot = info["data"]["parsed"]["info"].get("slot") if info and isinstance(info.get("data"), dict) else None
        out["programs"][p] = dict(what=what, programdata=pd, upgrade_authority=ua, deployed_slot=slot)
    except Exception as e:
        out["programs"][p] = dict(what=what, error=str(e)[:120])
# nonce account state
try:
    v = rpcu.rpc("getAccountInfo", ["4kT5gqyZkLqkFV3J5yRwqF3qCxmvExTtZiyf4saT3Cah", {"encoding": "jsonParsed"}])["value"]
    out["nonce"] = v["data"]["parsed"]["info"] if v else None
except Exception as e: out["nonce"] = str(e)[:120]
json.dump(out, open("funding.json", "w"), indent=1)
for x in out["first_txs"][:60]:
    print(x["slot"], x["bt"], x["sig"][:12], "err" if x["err"] else "", "signer", [s[:8] for s in x["signer"]], "chg", x["sol_chg"], "bal", x["post_bal"], [(f["type"], (f["src"] or "")[:8], (f["dst"] or "")[:8], f["lamports"] and f["lamports"] / 1e9, f["amt"], (f["mint"] or "")[:6]) for f in x["xfers"]][:4], x["logs"][:2])
for p, v in out["programs"].items(): print(p[:10], v)
print("nonce", out["nonce"])
