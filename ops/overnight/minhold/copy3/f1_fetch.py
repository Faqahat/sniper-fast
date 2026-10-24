#!/usr/bin/env python3
# READ-ONLY RPC: every tx touching WALLET since T0 (default 10-22 02:00 PKT, before R1), raw getTransaction JSON -> raw/<w8>.jsonl.gz
# resumable (skips sigs already saved). The RPC endpoint is read from the owner's config file and never printed or stored.
# usage: python3 -I f1_fetch.py WALLET [T0_unix]
import sys, os, json, time, gzip, urllib.request, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
W = sys.argv[1]; T0 = float(sys.argv[2]) if len(sys.argv) > 2 else 1792702800 - 18000  # 10-22 02:00 PKT
OUT = f"raw/{W[:8]}.jsonl.gz"; SIGF = f"raw/{W[:8]}.sigs.json"
def rpc(m, p, tries=8):
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.5 * (i + 1))
    return None
if os.path.exists(SIGF): sigs = json.load(open(SIGF))
else:
    sigs = []; before = None
    while True:
        page = rpc("getSignaturesForAddress", [W, {"limit": 1000, **({"before": before} if before else {})}])
        if page is None: print("sig page failed; retry later", flush=True); sys.exit(1)
        if not page: break
        sigs += [p for p in page if (p.get("blockTime") or 0) >= T0]
        before = page[-1]["signature"]
        print("sigs", len(sigs), time.strftime("%m-%d %H:%M", time.gmtime((page[-1].get("blockTime") or 0) + 18000)), flush=True)
        if (page[-1].get("blockTime") or 0) < T0 or len(page) < 1000: break
    json.dump(sigs, open(SIGF, "w"))
have = set()
if os.path.exists(OUT):
    try:
        for l in gzip.open(OUT, "rt"):
            try: have.add(json.loads(l)["sig"])
            except Exception: pass
    except (EOFError, OSError): pass
todo = [s for s in sigs if s["signature"] not in have]
print(f"{W[:8]}: sigs {len(sigs)} have {len(have)} todo {len(todo)}", flush=True)
def one(p):
    return p, rpc("getTransaction", [p["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
n = 0; miss = 0
with gzip.open(OUT, "at") as fo, cf.ThreadPoolExecutor(8) as ex:
    for p, t in ex.map(one, todo):
        if not t: miss += 1; continue
        t["sig"] = p["signature"]; fo.write(json.dumps(t, separators=(",", ":")) + "\n"); n += 1
        if n % 500 == 0: print("fetched", n, flush=True)
print(f"done {W[:8]} fetched {n} missing {miss}", flush=True)
