#!/usr/bin/env python3
# READ-ONLY, offline: token name / symbol / creator from each create tx's pump.fun CreateEvent (txcache from trend5.py)
import sys, os, json, base64, hashlib
OUT = sys.argv[1]
RAW = json.load(open(os.path.join(OUT, "raw.json")))
D = hashlib.sha256(b"event:CreateEvent").digest()[:8]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
meta = {}
for mint, R in RAW.items():
    if not R.get("create"): continue
    tx = json.load(open(os.path.join(OUT, "txcache", R["create"][1] + ".json")))
    for l in tx["meta"]["logMessages"]:
        if not l.startswith("Program data: "): continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        raw = base64.b64decode(s)
        if raw[:8] != D: continue
        o = 8; out = []
        for _ in range(3):
            n = int.from_bytes(raw[o:o + 4], "little"); out.append(raw[o + 4:o + 4 + n].decode("utf-8", "replace")); o += 4 + n
        m = b58(raw[o:o + 32]); bc = b58(raw[o + 32:o + 64]); user = b58(raw[o + 64:o + 96]); creator = b58(raw[o + 96:o + 128]) if len(raw) >= o + 128 else user
        if m == mint: meta[mint] = dict(name=out[0], symbol=out[1], uri=out[2], bonding_curve=bc, user=user, creator=creator, create_sig=R["create"][1], S=R["create"][0])
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
for m, x in meta.items(): print(x["symbol"], m, "creator", x["creator"], "curve", x["bonding_curve"])
