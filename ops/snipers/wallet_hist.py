#!/usr/bin/env python3
# READ-ONLY (owner's RPC via RPC_URLS + Jito's public bundle API). For each candidate sniper wallet: its most recent pump.fun
# BUYS (sells ignored): size, fee paid (priority + labelled tips), how fast after the token's create (slot delta, from the
# mint's own signature list), SOL already in the curve before it (position proxy), the token's creator (variety / same-dev
# signal), and for create-slot buys whether the buy sat in the SAME Jito bundle as the create (insider).
# usage: RPC_URLS=... TIPMAP_JSON=... python3 -I wallet_hist.py <snipe_rows.json> <out.json> [max_buys=40]
import sys, os, json, base64, time, threading, statistics, collections, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); R1 = os.path.join(HERE, "..", "run1")
sys.path.insert(0, R1)
src = open(os.path.join(R1, "bundlestudy.py")).read()
ns = {"__file__": os.path.join(R1, "bundlestudy.py"), "__name__": "bs"}
exec(compile(src[:src.index("\ndef one(")], "bundlestudy.py", "exec"), ns)       # rpc, jito, b58enc, b58dec, txmeta, label
rpc, jito, b58enc, txmeta = ns["rpc"], ns["jito"], ns["b58enc"], ns["txmeta"]
ROWS = json.load(open(sys.argv[1])); OUT = sys.argv[2]; MAXB = int(sys.argv[3]) if len(sys.argv) > 3 else 40
OURS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS")
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])


def events(tx):
    out = []
    for l in (tx.get("meta") or {}).get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] != DISC or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58enc(raw[8:40]), sol=u(40), buy=raw[56] == 1, user=b58enc(raw[57:89]), vsol=u(97), creator=b58enc(raw[177:209])))
    return out


cands = collections.OrderedDict()
for r in sorted(ROWS, key=lambda r: (r["S"], r["pos"])):
    if r["w"] in OURS or r["cheap_early"] or r["sol"] < 0.15: continue
    cands.setdefault(r["w"], []).append(r)
print(f"candidate wallets: {len(cands)}", flush=True)


def hist(w):
    sigs = [s for s in (rpc("getSignaturesForAddress", [w, {"limit": 400}]) or []) if s.get("err") is None]
    buys = []
    for s in sigs:
        if len(buys) >= MAXB: break
        t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: continue
        ev = [e for e in events(t) if e["buy"] and e["user"] == w]
        if not ev: continue
        tm = txmeta(t); fee = tm["prio"] + sum(x[1] for x in tm["tips"])
        e = ev[0]
        buys.append(dict(sig=s["signature"], slot=t["slot"], bt=t.get("blockTime"), mint=e["mint"], creator=e["creator"], sol=sum(x["sol"] for x in ev) / 1e9,
                         fee=fee, tips=tm["tips"], in_curve=(e["vsol"] - e["sol"]) / 1e9 - 30.0, payer=tm["payer"]))
    for b in buys:                                   # how many slots after the token's create? (mint signatures before this buy)
        r = rpc("getSignaturesForAddress", [b["mint"], {"before": b["sig"], "limit": 40}]) or []
        if len(r) < 40:
            b["create_slot"] = r[-1]["slot"] if r else b["slot"]; b["create_sig"] = r[-1]["signature"] if r else None
            b["delta"] = b["slot"] - b["create_slot"]
        else:
            b["delta"] = None
    checked = 0                                       # insider check: create-slot buys sitting in the create's own Jito bundle
    for b in buys:
        if b["delta"] != 0 or not b.get("create_sig") or checked >= 6: continue
        checked += 1
        j = jito("transaction/" + b["sig"])
        bid = j[0]["bundle_id"] if isinstance(j, list) and j else None
        b["jito_bundle"] = bool(bid)
        if bid:
            d = jito("bundle/" + bid)
            sigs_b = (d[0].get("txSignatures") or []) if isinstance(d, list) and d else []
            b["insider"] = b["create_sig"] in sigs_b
        else:
            b["insider"] = False
    return w, buys


res = {}
with cf.ThreadPoolExecutor(int(os.environ.get("THREADS", "4"))) as ex:
    for w, buys in ex.map(hist, list(cands)):
        res[w] = dict(seen_in=[dict(mint=r["mint"], pos=r["pos"], sol=r["sol"], fee=r["fee"], ratio=r["ratio"]) for r in cands[w]], buys=buys)
        sn = [b for b in buys if b["delta"] is not None and b["delta"] <= 2]
        print(f"{w}: {len(buys)} buys, {len(sn)} within 2 slots of create", flush=True)
json.dump(res, open(OUT, "w"))
print("saved", OUT)
