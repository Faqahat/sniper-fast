#!/usr/bin/env python3
"""Build one deduped table of haqq's and our wallets' txs (landed AND failed) from the extracted raw-recording lines.
Out: sniper-data/haqq_dissect/exec/txs.pkl (pandas DataFrame). Read-only."""
import json, glob, base64, struct, collections, pickle, sys
import time
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
W = {"haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqq", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "AMS"}
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
DISC = bytes.fromhex("bddb7fd34ee661ee")
def trade(evs, user):
    out = []
    for e in evs or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] != DISC or len(b) < 129: continue
            mint = b58(b[8:40]); sol, tok = struct.unpack_from("<QQ", b, 40); buy = b[56]; u = b58(b[57:89])
            vsol, vtok = struct.unpack_from("<QQ", b, 97)
            if u == user: out.append((mint, sol, tok, buy, vsol, vtok))
    return out
seen = set(); rows = []
for f in sorted(glob.glob("/home/moiz/sniper-data/haqq_dissect/exec/ext/*.jsonl")):
    run = f.split("/")[-1].split("__")[0]
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        s0 = r["signers"][0]
        if s0 not in W or r["sig"] in seen: continue
        seen.add(r["sig"])
        ixn = r.get("ixn") or []
        kb = [x for x in ixn if x.startswith(("Buy", "Sell"))]
        kind = ("buy" if kb[0].startswith("Buy") else "sell") if kb else ("close" if ixn and all(x == "CloseAccount" for x in ixn) else "other")
        tr = trade(r.get("ev"), s0)
        tips = r.get("tips") or []
        sd = dict(r.get("sd") or [])
        paths = [TIP.get(k, "nozomi" if k.startswith("noz") else "?" + k[:5]) for k, d in tips]
        e = r.get("err"); ecode = None; eidx = None
        if e:
            try:
                ie = e["InstructionError"]; eidx = ie[0]; ecode = ie[1]["Custom"] if isinstance(ie[1], dict) and "Custom" in ie[1] else str(ie[1])
            except Exception: ecode = str(e)[:40]
        rows.append(dict(w=W[s0], run=run, s=r["s"], i=r["i"], bt=r["bt"], sig=r["sig"], ok=e is None, ecode=ecode, eidx=eidx, fee=r.get("fee") or 0,
                         cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"), kind=kind, ixn="|".join(ixn), progs="|".join(p[:6] for p in r.get("progs") or []),
                         mint=(tr[0][0] if tr else (r.get("mints") or [None])[0]), sol=(tr[0][1] if tr else 0), tok=(tr[0][2] if tr else 0), ntr=len(tr),
                         vsol=(tr[0][4] if tr else 0), vtok=(tr[0][5] if tr else 0),
                         tip=sum(d for k, d in tips), ntip=len(tips), path="+".join(sorted(set(paths))) if paths else "notip", sd_self=sd.get(s0, 0),
                         nsig=len(r["signers"])))
for r in rows: r["day"] = time.strftime("%m-%d", time.gmtime(r["bt"] + 5 * 3600))
pickle.dump(rows, open("/home/moiz/sniper-data/haqq_dissect/exec/txs.pkl", "wb"))
c = collections.Counter((r["w"], r["day"]) for r in rows)
for k in sorted(c): print(k, c[k])
c = collections.Counter((r["w"], r["kind"], r["ok"]) for r in rows)
for k in sorted(c): print(k, c[k])
