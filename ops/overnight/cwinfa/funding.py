#!/usr/bin/env python3
# READ-ONLY RPC look-ups for questions 1 and 3 (owner's RPC <= 4 req/s via rpcw; public mainnet-beta ~1.6 req/s):
#  - router program 5DVzy5Ep...: loader, program-data account, upgrade authority, last deploy slot; recent users of the router
#    (signers of a sample of its recent transactions) -> private bot or shared/commercial
#  - the address lookup table and two nonce accounts (authority)
#  - CWiNFA's history BEFORE the owner's RPC horizon (public RPC): first transactions = funding
#  - withdrawal / payment counterparties: activity level (exchange-like or personal)
import os, sys, json, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rpcw
W = rpcw.W; ROUTER = "5DVzy5EpG2xVxrwwuyZPDe9EpraUnGh7ZgYABwizzNVu"; ALT = "B73XBTEmKwFGR7uu8s3NtHKiQoYPsF2rYHJB87NwxAgv"
OUT = {}
def acct(a, ep=None):
    try: return rpcw.rpc("getAccountInfo", [a, {"encoding": "jsonParsed"}], ep=ep)
    except Exception as e: return {"error": str(e)[:100]}
# 1) router program
pa = acct(ROUTER); OUT["router_account"] = pa
try:
    pd = pa["value"]["data"]["parsed"]["info"]["programData"]
    OUT["router_programdata"] = acct(pd)
except Exception as e: OUT["router_programdata"] = {"error": str(e)[:100]}
# 2) who uses the router: signatures (2 pages) then a spread sample of 60 transactions -> fee payers / signers
sigs = []; before = None
for _ in range(3):
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpcw.rpc("getSignaturesForAddress", [ROUTER, p])
    if not r: break
    sigs += r; before = r[-1]["signature"]
    if len(r) < 1000: break
OUT["router_sigs_n"] = len(sigs); OUT["router_sigs_span"] = [sigs[-1]["slot"], sigs[0]["slot"], sigs[-1].get("blockTime"), sigs[0].get("blockTime")] if sigs else None
sample = sigs[:: max(1, len(sigs) // 60)][:60]
payers = collections.Counter()
for s in sample:
    try:
        t = rpcw.rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
        payers[t["transaction"]["message"]["accountKeys"][0]["pubkey"]] += 1
    except Exception: payers["?"] += 1
OUT["router_sample_payers"] = payers.most_common()
# 3) ALT + nonce accounts
OUT["alt"] = acct(ALT)
for n in ("HeFPFRBKPohPsekcqcw89q1sKUcBbdJFnmn7yikvTWQc", "AAW6kUA679zmCbh3HQXBkoGCmEtG8QC6nnBRmqyG8DEX"): OUT["nonce_" + n[:6]] = acct(n)
# 4) history before the owner's RPC horizon (public RPC)
S = json.load(open(os.path.join(HERE, "sigs_CWiNFA.json"))); oldest = S[0]["signature"]
old = []; before = oldest
for i in range(40):
    try: r = rpcw.rpc("getSignaturesForAddress", [W, {"limit": 1000, "before": before}], ep=rpcw.PUB)
    except Exception as e: OUT["old_error"] = str(e)[:200]; break
    if not r: break
    old += r; before = r[-1]["signature"]
    print(f"  public page {i}: {len(r)} sigs, slots {r[0]['slot']}..{r[-1]['slot']}", flush=True)
    if len(r) < 1000: break
OUT["old_n"] = len(old); OUT["old_failed"] = sum(1 for s in old if s.get("err") is not None)
OUT["old_span"] = [old[-1]["slot"], old[0]["slot"], old[-1].get("blockTime"), old[0].get("blockTime")] if old else None
json.dump(old, open(os.path.join(HERE, "sigs_CWiNFA_old.json"), "w"))
first = []
for s in reversed(old[-8:]):
    t = None
    for ep in (rpcw.EP, rpcw.PUB):
        try: t = rpcw.rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}], ep=ep); break
        except Exception: pass
    if not t: first.append(dict(sig=s["signature"], missing=True)); continue
    m = t["transaction"]["message"]; keys = [k["pubkey"] for k in m["accountKeys"]]; meta = t["meta"]
    i = keys.index(W) if W in keys else None
    xf = []
    for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and isinstance(p.get("info"), dict) and "lamports" in p["info"]: xf.append([p["info"].get("source"), p["info"].get("destination"), p["info"]["lamports"] / 1e9, p.get("type")])
    first.append(dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), signer=keys[0], sol_chg=(meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else None,
                      pre=meta["preBalances"][i] / 1e9 if i is not None else None, xfers=xf, logs=[l for l in (meta.get("logMessages") or []) if "Instruction:" in l][:6]))
OUT["first_txs"] = first
# 5) counterparties of the stablecoin withdrawals / payments
CP = {"AguYev2TP6npfnkPHKoEVaXnDxZs5PYoaJxM4t4rHB32": "USDC withdrawals x3", "9fufb3TE9LrXdQpbHzTFCWMpkWeW6P4njL62FFCzALiW": "USDT withdrawals x2",
      "CEs84tEowsXpH8u4VBf8rJSVgSRypFMfXw9CpGRtQgb6": "USDC payments with pi_ memo x2"}
OUT["counterparties"] = {}
for a, why in CP.items():
    info = acct(a)
    try: r = rpcw.rpc("getSignaturesForAddress", [a, {"limit": 1000}])
    except Exception: r = []
    span = (r[0]["blockTime"] - r[-1]["blockTime"]) if r and r[0].get("blockTime") and r[-1].get("blockTime") else None
    OUT["counterparties"][a] = dict(why=why, owner=(info.get("value") or {}).get("owner") if isinstance(info, dict) else None, lamports=(info.get("value") or {}).get("lamports") if isinstance(info, dict) else None,
                                    recent_sigs=len(r), span_s=span, txs_per_hour=round(len(r) / (span / 3600), 1) if span else None)
json.dump(OUT, open(os.path.join(HERE, "funding.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in OUT.items() if k not in ("router_account", "router_programdata", "alt") or True}, default=str)[:6000])
