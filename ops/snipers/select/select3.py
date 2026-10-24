#!/usr/bin/env python3
# READ-ONLY (owner's RPC). Token selection of 3 related sniper wallets vs ALL pump.fun launches in the same hours.
# Universe = a random sample of creates (signatures of pump's mint-authority account, which only creates touch).
# Features come from each create tx: dev buy, quote, launcher program, metadata host, tips by landing service,
# name/symbol, multi-wallet create; plus the creator's activity (signature count around the create).
# usage: RPC_URLS=... TIPMAP_JSON=... python3 -I select3.py <out.json> [sample=2500]
import sys, os, json, base64, hashlib, random, collections, concurrent.futures as cf, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); R1 = os.path.join(HERE, "..", "..", "run1"); WD = os.path.join(HERE, "..", "w9sh")
src = open(os.path.join(R1, "bundlestudy.py")).read()
ns = {"__file__": os.path.join(R1, "bundlestudy.py"), "__name__": "bs"}
exec(compile(src[:src.index("\ndef one(")], "bundlestudy.py", "exec"), ns)
rpc, b58enc, txmeta, label = ns["rpc"], ns["b58enc"], ns["txmeta"], ns["label"]
OUT = sys.argv[1]; NSAMP = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
WALLETS = {"9Sh2fd": "deep.json", "D24ipY": "deep_d24.json", "DGmspi": "deep_dgms.json"}
TDISC = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CDISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
STD = {"ComputeBudget111111111111111111111111111111", "11111111111111111111111111111111", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
# 1) bought snipes (create block or the next one)
bought = []
for w, f in WALLETS.items():
    for t in json.load(open(os.path.join(WD, f)))["txs"]:
        for e in t["ev"]:
            if e["buy"] and t.get("delta") is not None and t["delta"] <= 1 and t.get("create_sig"):
                bought.append(dict(w=w, mint=e["mint"], create_sig=t["create_sig"], create_slot=t["create_slot"], size=e["sol"] / 1e9, delta=t["delta"])); break
lo = min(b["create_slot"] for b in bought); hi = max(b["create_slot"] for b in bought)
print(f"bought snipes: {collections.Counter(b['w'] for b in bought)}; create slots {lo}..{hi}", flush=True)
# 2) universe: every create signature in [lo, hi], then a random sample
sigs, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", ["TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM", p]) or []
    if not r: break
    sigs += [s for s in r if s.get("err") is None and lo <= s["slot"] <= hi]; before = r[-1]["signature"]
    if r[-1]["slot"] < lo or len(r) < 1000: break
print(f"universe: {len(sigs)} creates in the window (oldest reached slot {r[-1]['slot'] if r else '-'})", flush=True)
random.seed(7); samp = random.sample(sigs, min(NSAMP, len(sigs)))
todo = {s["signature"] for s in samp} | {b["create_sig"] for b in bought}
def host(u):
    try: return urllib.parse.urlparse(u).netloc or u[:20]
    except Exception: return "?"
def feat(sig):
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return sig, None
    msg = t["transaction"]["message"]; meta = t["meta"]; la = meta.get("loadedAddresses") or {}
    keys = list(msg["accountKeys"]) + la.get("writable", []) + la.get("readonly", [])
    top = [keys[ix["programIdIndex"]] for ix in msg["instructions"]]
    launcher = next((p for p in top if p not in STD and p != PUMP), "pump direct" if PUMP in top else "?")
    ce = None; buys = []
    for l in meta.get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] == CDISC and ce is None:
            o = 8; v = []
            for _ in range(3):
                n = int.from_bytes(raw[o:o + 4], "little"); v.append(raw[o + 4:o + 4 + n].decode("utf-8", "replace")); o += 4 + n
            ce = dict(name=v[0], symbol=v[1], uri=v[2], mint=b58enc(raw[o:o + 32]), user=b58enc(raw[o + 64:o + 96]))
        if raw[:8] == TDISC and len(raw) >= 129 and raw[56] == 1:
            buys.append((b58enc(raw[57:89]), int.from_bytes(raw[40:48], "little") / 1e9))
    if not ce: return sig, None
    tm = txmeta(t); ins = [l.split("Instruction: ")[1] for l in meta.get("logMessages") or [] if "Instruction: " in l]
    lt = max(((label(keys[ix["accounts"][1]]) or "unlabelled"), 0) for ix in [] ) if False else None
    return sig, dict(mint=ce["mint"], creator=ce["user"], name=ce["name"], symbol=ce["symbol"], host=host(ce["uri"]), uri=ce["uri"], slot=t["slot"], bt=t.get("blockTime"),
                     launcher=launcher, create_ix=next((i for i in ins if i.startswith("Create")), "?"), dev_sol=sum(s for u, s in buys if u == ce["user"]),
                     n_buy_wallets=len({u for u, _ in buys}), tx_buy_sol=sum(s for _, s in buys), quote="SOL" if any(s > 0 for _, s in buys) else ("none" if not buys else "other"),
                     tips=tm["tips"], prio=tm["prio"], payer_is_creator=tm["payer"] == ce["user"], nsig=len(tm["signers"]))
with cf.ThreadPoolExecutor(12) as ex: F = {s: f for s, f in ex.map(feat, list(todo)) if f}
print(f"create txs parsed: {len(F)} of {len(todo)}", flush=True)
# 3) creator activity: signatures of the creator in the 24 h before this create (capped at 1000)
cre = {f["creator"]: f for f in F.values()}
def act(c):
    f = cre[c]; r = rpc("getSignaturesForAddress", [c, {"limit": 1000}]) or []
    n24 = sum(1 for s in r if s.get("blockTime") and f["bt"] and 0 <= f["bt"] - s["blockTime"] <= 86400)
    return c, dict(n_total=len(r), n24_before=n24, oldest_bt=r[-1].get("blockTime") if r else None)
with cf.ThreadPoolExecutor(12) as ex: A = dict(ex.map(act, list(cre)))
json.dump(dict(bought=bought, universe=[s["signature"] for s in samp], n_universe_total=len(sigs), features=F, creators=A), open(OUT, "w"))
print("saved", OUT, flush=True)
