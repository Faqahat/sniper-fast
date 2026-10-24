#!/usr/bin/env python3
# READ-ONLY, RESUMABLE: every signature of the wallet back to MIN_SLOT (owner's CK RPC, rate-limited ~4 req/s total),
# then every transaction (failed ones too) cached raw to txc/<sig>.json. Nothing is ever sent.
# usage: python3 -I fetch.py <wallet> [min_slot]
import sys, os, json, time, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rpc
W = sys.argv[1]; MIN_SLOT = int(sys.argv[2]) if len(sys.argv) > 2 else 459_300_000
C = os.path.join(HERE, "txc"); os.makedirs(C, exist_ok=True)
SF = os.path.join(HERE, "sigs.json")
sigs = json.load(open(SF)) if os.path.exists(SF) else []
have_sig = {s["signature"] for s in sigs}
# 1) newest signatures first (until we hit what we already have), then older pages until MIN_SLOT / end of RPC history
new, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc.rpc("getSignaturesForAddress", [W, p])
    if not isinstance(r, list) or not r: break
    stop = False
    for s in r:
        if s["signature"] in have_sig: stop = True; break
        new.append(s)
    if stop or len(r) < 1000: break
    before = r[-1]["signature"]
sigs = new + sigs
# older history
while sigs and sigs[-1]["slot"] > MIN_SLOT:
    r = rpc.rpc("getSignaturesForAddress", [W, {"limit": 1000, "before": sigs[-1]["signature"]}])
    if not isinstance(r, list) or not r: break
    sigs += [s for s in r if s["signature"] not in have_sig]
    print(f"  sigs {len(sigs)} oldest slot {sigs[-1]['slot']} bt {sigs[-1].get('blockTime')}", flush=True)
    if len(r) < 1000: break
json.dump(sigs, open(SF, "w"))
print(f"{W[:6]}: {len(sigs)} signatures, slots {sigs[-1]['slot']}..{sigs[0]['slot']}, failed {sum(1 for s in sigs if s.get('err'))}", flush=True)
have = lambda s: os.path.exists(os.path.join(C, s + ".json"))
todo = [s["signature"] for s in sigs if not have(s["signature"]) and s["slot"] >= MIN_SLOT]
print(f"  to fetch {len(todo)}", flush=True)
done = [0]; miss = []
def one(sig):
    if have(sig): done[0] += 1; return
    t = rpc.get_tx(sig)
    if t:
        tmp = os.path.join(C, sig + ".json.tmp"); json.dump(t, open(tmp, "w")); os.replace(tmp, os.path.join(C, sig + ".json"))
    else: miss.append(sig)
    done[0] += 1
    if done[0] % 500 == 0: print(f"  fetched {done[0]}/{len(todo)} (missing {len(miss)})", flush=True)
with cf.ThreadPoolExecutor(int(os.environ.get("DK_THREADS", "8"))) as ex: list(ex.map(one, todo))
json.dump(miss, open(os.path.join(HERE, "missing.json"), "w"))
print(f"done; missing {len(miss)}", flush=True)
