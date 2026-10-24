#!/usr/bin/env python3
# READ-ONLY: for the wallet's top create-signers, how many of the signer's launches (last ~2 days, owner RPC) did the wallet
# attempt (bought or failed)? 100% = it fires on every launch of that dev (a dev list); much less = some other filter on top.
# usage: coverage.py <devs.json> <att.json> <sigs cachedir> <sig_summary.json> <out.json>
import sys, os, json, time, urllib.request
DV, AT, SIGC, SUM, OUT = sys.argv[1:6]
CK = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(CK, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "error" in r: raise RuntimeError(str(r["error"])[:200])
            return r["result"]
        except Exception as e: err = e; time.sleep(min(8, 0.5 * 2 ** i))
    raise RuntimeError(f"{m}: {err}")
lo = rpc("minimumLedgerSlot", []) + 60000; hi = rpc("getSlot", [{"commitment": "confirmed"}])
def sigs_of(addr, lo):
    out, before = [], None
    while True:
        p = {"limit": 1000, "commitment": "confirmed"}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [addr, p]) or []
        out += [s for s in r if s["slot"] >= lo]; 
        if not r or r[-1]["slot"] < lo or len(r) < 1000: return out
        before = r[-1]["signature"]
# attempted create sigs (bought + failed): oldest signature on the mint before the wallet's tx
att = {}
for f in (DV, AT):
    for m, v in json.load(open(f)).items():
        p = os.path.join(SIGC, m + ".json")
        if os.path.exists(p):
            s = json.load(open(p))
            if s and len(s) < 1000: att[s[-1]["signature"]] = dict(m=m, src="bought" if f == DV else "failed", slot=s[-1]["slot"])
U = {s["signature"]: s["slot"] for s in sigs_of("TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM", lo) if s.get("err") is None}
print(f"window slots {lo}..{hi}: {len(U)} pump.fun creates; wallet attempted {sum(1 for s in att if s in U)} of them", flush=True)
top = json.load(open(SUM))["top"]; res = {}
for dev, n in top:
    cs = [s["signature"] for s in sigs_of(dev, lo) if s.get("err") is None and s["signature"] in U]
    a = [s for s in cs if s in att]
    res[dev] = dict(creates=len(cs), attempted=len(a), bought=sum(1 for s in a if att[s]["src"] == "bought"), skipped=[s for s in cs if s not in att][:200])
    print(f"   {dev}: {len(cs):4} launches in window; attempted {len(a):4} ({len(a) / max(1, len(cs)):.0%}), bought {res[dev]['bought']}", flush=True)
json.dump(dict(lo=lo, hi=hi, n_universe=len(U), devs=res), open(OUT, "w"))
