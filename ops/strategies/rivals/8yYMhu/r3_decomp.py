#!/usr/bin/env python3
"""8yYMhu step 3 (read-only): per recorded tx touching the wallet (ext/*.jsonl): decode TradeEvent(s), tips (relay via the recorder
tipmap), CU price/limit, kind, rent created/closed, wallet SOL delta rebuilt from parts.
  trade cash (TradeEvent): buy -(sol + fee + cfee), sell +(sol - fee - cfee)
  wallet delta sd = trade - txfee - tips - rent_created + rent_closed + other
Out: DATA/tx.pkl (list of dicts sorted by slot, idx), DATA/r3.txt"""
import json, pickle, base64, struct, collections, glob, os, sys
import numpy as np
W = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"
D = "/home/moiz/sniper-data/rivals/8yYMhu"
TIP = json.load(open("/home/moiz/sniper-data/e2x1_dissect/recon/tipmap.json"))
RENTS = {2039280: "spl165", 1488440: "spl165b", 1513840: "t22_170", 2074080: "t22_170b"}
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s
def chunks(evs):
    for e in evs or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            yield b
def parse(b):
    o = 8; mint = b58(b[o:o + 32]); o += 32
    sol, tok = struct.unpack_from("<QQ", b, o); o += 16
    buy = b[o]; o += 1; user = b58(b[o:o + 32]); o += 32; ts = struct.unpack_from("<q", b, o)[0]; o += 8
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32; fbps, fee = struct.unpack_from("<QQ", b, o); o += 16
    creator = b58(b[o:o + 32]); o += 32; cbps, cfee = struct.unpack_from("<QQ", b, o); o += 16
    return dict(mint=mint, sol=sol, tok=tok, buy=bool(buy), user=user, vsol=vsol, vtok=vtok, rsol=rsol, rtok=rtok, fbps=fbps, fee=fee, cbps=cbps, cfee=cfee, creator=creator)
def kind_of(own, ok, ixs):
    if not own: return "third"
    if not ok: return "fail"
    if any(x.startswith("Buy") for x in ixs): return "buy"
    if "Sell" in ixs: return "sell"
    return "other"
if __name__ == "__main__":
    rec = {}
    files = sorted(glob.glob(f"{D}/ext/*.done"))
    for fd in files:
        for l in open(fd[:-5] + ".jsonl"):
            try: d = json.loads(l)
            except Exception: continue
            if d["sig"] in rec and len(l) <= rec[d["sig"]]["_len"]: continue
            d["_len"] = len(l); rec[d["sig"]] = d
    rows = []
    for sig, d in rec.items():
        ix = d.get("ixn") or []; ixs = set(ix); ok = d["err"] is None
        sd = {a: v for a, v in (d.get("sd") or [])}
        tips = [(a, v) for a, v in (d.get("tips") or [])]
        own = (d.get("signers") or ["?"])[0] == W
        tipsum = sum(v for a, v in tips) if ok else 0
        evs = [parse(b) for b in chunks(d.get("ev")) if b[:8] == DISC and len(b) >= 225]
        mine = [e for e in evs if e["user"] == W]
        k = kind_of(own, ok, ix)
        r = dict(sig=sig, s=d["s"], i=d["i"], bt=d["bt"], ok=ok, err=d["err"], kind=k, own=own, signers=d.get("signers"), txfee=d["fee"] if own else 0,
                 cu=d.get("cu"), cup=d.get("cup"), cul=d.get("cul"), tips=tipsum, tip_acc=[a for a, v in tips], tip_amt=[v for a, v in tips],
                 relay="+".join(sorted(set(TIP.get(a, "?" + a[:6]) for a, v in tips))) or "none", progs=d.get("progs"), ixn="|".join(ix),
                 mints=d.get("mints"), sd=sd.get(W, 0), nev=len(mine), mint=(mine[0]["mint"] if mine else (d.get("mints") or [None])[0]),
                 events=mine, allev=len(evs), trade=0, rent_c=0, rent_x=0, other=0, tb=d.get("tb"), src="rec")
        if mine:
            r["trade"] = sum((-(x["sol"] + x["fee"] + x["cfee"]) if x["buy"] else (x["sol"] - x["fee"] - x["cfee"])) for x in mine)
        if own and ok:
            rest = r["sd"] - (r["trade"] - r["txfee"] - tipsum)
            tipacc = set(a for a, v in tips)
            r["rent_c"] = sum(v for a, v in sd.items() if a != W and a not in tipacc and v in RENTS)
            r["rent_x"] = sum(-v for a, v in sd.items() if a != W and -v in RENTS)
            r["other"] = rest + r["rent_c"] - r["rent_x"]
        elif own:
            r["other"] = r["sd"] + r["txfee"]
        else:
            r["other"] = r["sd"]
        rows.append(r)
    rows.sort(key=lambda r: (r["s"], r["i"]))
    pickle.dump(rows, open(f"{D}/tx.pkl", "wb"))
    L = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); L.append(s)
    P("files", len(files), "txs", len(rows), dict(collections.Counter(r["kind"] for r in rows)))
    for k in ("buy", "sell", "fail", "other", "third"):
        rr = [r for r in rows if r["kind"] == k]
        if not rr: continue
        o = np.array([r["other"] for r in rr]); P(f"{k}: n={len(rr)} other==0: {(o == 0).sum()} nonzero {(o != 0).sum()} sum {o.sum() / 1e9:+.9f}")
        for r in [r for r in rr if r["other"]][:6]: P("   ", r["sig"][:16], r["ixn"][:80], "sd", r["sd"], "trade", r["trade"], "fee", r["txfee"], "tips", r["tips"], "rc", r["rent_c"], "rx", r["rent_x"], "other", r["other"], "nev", r["nev"])
    P("relays own ok:", collections.Counter((r["kind"], r["relay"]) for r in rows if r["own"] and r["ok"]).most_common(30))
    P("tip amounts (k mSOL):", collections.Counter((r["kind"], tuple(round(a / 1e6, 2) for a in r["tip_amt"])) for r in rows if r["own"] and r["ok"]).most_common(20))
    P("fails:", collections.Counter((json.dumps(r["err"])[:60]) for r in rows if r["kind"] == "fail").most_common(20))
    open(f"{D}/r3.txt", "w").write("\n".join(L) + "\n")
