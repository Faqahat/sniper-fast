#!/usr/bin/env python3
# READ-ONLY (owner's RPC): for each watched dev, every SOL-quoted launch in the window and the token's trades from the create to
# ~S+100 slots (~21 s), in exact chain order. Output feeds devreplay_sim.py (entry right after the dev's create, exits, costs).
# usage: RPC_URLS=... TIPMAP_JSON=... python3 -I devreplay_fetch.py <devlist.json> <topN> <out.json>
import sys, os, json, base64, hashlib, collections, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); R1 = os.path.join(HERE, "..", "..", "run1")
BSRC = open(os.path.join(R1, "bundlestudy.py")).read(); ns = {"__file__": os.path.join(R1, "bundlestudy.py"), "__name__": "bs"}
exec(compile(BSRC[:BSRC.index("\ndef one(")], "bundlestudy.py", "exec"), ns); rpc, b58enc = ns["rpc"], ns["b58enc"]
DEVS = json.load(open(sys.argv[1]))[:int(sys.argv[2])]; OUT = sys.argv[3]
SEL = json.load(open(os.path.join(HERE, "sel.json"))); lo = min(b["create_slot"] for b in SEL["bought"]); hi = max(b["create_slot"] for b in SEL["bought"])
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); CD = hashlib.sha256(b"event:CreateEvent").digest()[:8]
def evs(t):
    out = []; ce = None
    for l in (t.get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] == CD and ce is None:
            o = 8
            for _ in range(3): n = int.from_bytes(raw[o:o + 4], "little"); o += 4 + n
            ce = dict(mint=b58enc(raw[o:o + 32]), user=b58enc(raw[o + 64:o + 96]))
        if raw[:8] == TD and len(raw) >= 225:
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            out.append(dict(mint=b58enc(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58enc(raw[57:89]), vsol=u(97), vtok=u(105), fbps=u(161), cbps=u(209)))
    return ce, out
def gettx(sig): return rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
launches = []
for dev in DEVS:
    sigs, before = [], None
    for _ in range(15):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [dev, p]) or []
        if not r: break
        sigs += [s for s in r if s.get("err") is None and lo <= s["slot"] <= hi]; before = r[-1]["signature"]
        if len(r) < 1000 or r[-1]["slot"] < lo: break
    with cf.ThreadPoolExecutor(12) as ex: T = list(ex.map(lambda s: (s, gettx(s["signature"])), sigs))
    n = 0
    for s, t in T:
        if not t: continue
        ce, ev = evs(t)
        if not ce or ce["user"] != dev: continue
        dbuy = [e for e in ev if e["buy"] and e["mint"] == ce["mint"]]
        if not dbuy or dbuy[0]["sol"] == 0: continue          # SOL-quoted launches with a dev buy only
        launches.append(dict(dev=dev, mint=ce["mint"], create_sig=s["signature"], S=t["slot"], bt=t.get("blockTime"), n_create_buyers=len({e["user"] for e in dbuy}))); n += 1
    print(f"dev {dev[:8]}: {len(sigs)} txs in window, {n} SOL launches with a dev buy", flush=True)
def tape(L):
    sigs, before = [], None
    for _ in range(5):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [L["mint"], p]) or []
        if not r: break
        sigs += r; before = r[-1]["signature"]
        if len(r) < 1000 or r[-1]["slot"] <= L["S"]: break
    sigs = [s for s in sigs if s.get("err") is None and L["S"] <= s["slot"] <= L["S"] + 100][-150:]
    E = []
    for s in sigs:
        t = gettx(s["signature"])
        if not t: continue
        _, ev = evs(t)
        for j, e in enumerate(ev):
            if e["mint"] == L["mint"]: E.append(dict(e, slot=t["slot"], sig=s["signature"], j=j))
    L["events"] = E; return L
with cf.ThreadPoolExecutor(12) as ex: launches = list(ex.map(tape, launches))
json.dump(dict(window=[lo, hi], launches=launches), open(OUT, "w"))
print(f"saved {len(launches)} launches with tapes -> {OUT}", flush=True)
