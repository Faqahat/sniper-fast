#!/usr/bin/env python3
"""recon step 3 (read-only): per recorded haqq tx in the window, the wallet's SOL delta rebuilt from its parts and compared with
the recorded balance delta (sd = post - pre of the wallet, written by the recorder from tx meta):
  trade cash  = from the pump TradeEvent: buy -(sol + fee + creator_fee [- cashback]); sell +(sol - fee - creator_fee [+ cashback])
  tx fee      = meta fee; tips = recorded tip transfers; rent = new token-account lamports (sd of the account the buy created)
  closes      = +lamports of closed token accounts (sd) - fee - tip
Out: recon/tx.pkl (list of dicts) and r3.txt"""
import json, pickle, base64, struct, collections, sys
import numpy as np
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
RENT = 1488440      # MEASURED: lamports of every token account his router creates (CreateAccountWithSeed, Token-2022)
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
    buy = b[o]; o += 1; user = b58(b[o:o + 32]); o += 32; o += 8
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32; fbps, fee = struct.unpack_from("<QQ", b, o); o += 16
    creator = b58(b[o:o + 32]); o += 32; cbps, cfee = struct.unpack_from("<QQ", b, o); o += 16
    o += 1 + 8 + 8 + 8 + 8
    n = int.from_bytes(b[o:o + 4], "little"); o += 4; ixname = b[o:o + n].decode("utf8", "replace"); o += n
    rest = b[o:]
    return dict(mint=mint, sol=sol, tok=tok, buy=bool(buy), user=user, vsol=vsol, vtok=vtok, fbps=fbps, fee=fee, cbps=cbps, cfee=cfee,
                creator=creator, ixname=ixname, rest=rest.hex())
rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
rows = []; restc = collections.Counter()
for sig, d in rec.items():
    if d["signers"][0] != H: continue
    ix = d.get("ixn") or []; ixs = set(ix)
    sd = dict(d.get("sd") or [])
    tips = sum(v for a, v in (d.get("tips") or []))
    ok = d["err"] is None
    evs = [parse(b) for b in chunks(d.get("ev")) if b[:8] == DISC and len(b) >= 225]
    mine = [e for e in evs if e["user"] == H]
    kind = ("fail" if not ok else "close" if ixs == {"CloseAccount"} else "buy" if any(x.startswith("Buy") for x in ix)
            else "sell" if any(x.startswith("Sell") for x in ix) else "other")
    r = dict(inw=(W0 <= d["bt"] < W1), sig=sig, s=d["s"], i=d["i"], bt=d["bt"], ok=ok, kind=kind, fkind=("buy" if any(x.startswith("Buy") for x in ix) else "sell" if any(x.startswith("Sell") for x in ix) else "close" if "CloseAccount" in ixs else "?"),
             cup=d.get("cup"), code=(d.get("cup") or 0) % 1000 if d.get("cup") else None, txfee=d["fee"], tips=tips if ok else 0, sd=sd.get(H, 0),
             ixn="|".join(ix), init=("InitializeAccount3" in ixs), mint=None, sol=0, tok=0, pfee=0, cfee=0, trade=0, rent=0, nev=len(mine), ixname=None, err=d["err"])
    if mine:
        e = mine[0]
        if W0 <= d["bt"] < W1: restc[(e["ixname"], len(e["rest"]) // 2)] += 1
        r.update(mint=e["mint"], sol=e["sol"], tok=e["tok"], pfee=e["fee"], cfee=e["cfee"], ixname=e["ixname"], buyflag=e["buy"], vsol=e["vsol"], vtok=e["vtok"], creator=e["creator"])
        r["trade"] = sum((-(x["sol"] + x["fee"] + x["cfee"]) if x["buy"] else (x["sol"] - x["fee"] - x["cfee"])) for x in mine)
    elif d.get("mints"):
        r["mint"] = d["mints"][0]
    if ok and kind == "buy":
        # the created token account = an sd account that gained exactly a rent-sized amount and is not curve / fee / tip
        tipacc = {a for a, v in (d.get("tips") or [])}
        cands = [v for a, v in sd.items() if a != H and a not in tipacc and v == RENT]
        r["rent"] = RENT * len(cands)
    if kind == "close":
        r["closed"] = round((sd.get(H, 0) + d["fee"] + tips) / 1488440, 3)
    if ok and kind in ("buy", "sell"):
        r["calc"] = r["trade"] - d["fee"] - tips - (r["rent"] or 0)
    elif not ok:
        r["calc"] = -d["fee"]
    else:
        r["calc"] = None
    r["resid"] = (r["sd"] - r["calc"]) if r["calc"] is not None else None
    rows.append(r)
pickle.dump(rows, open(f"{OUT}/tx.pkl", "wb"))
print("all recorded haqq-signed txs W0-6h..end:", len(rows))
rows = [r for r in rows if r["inw"]]
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
P(f"recorded txs in window: {len(rows):,}")
P("kinds:", dict(collections.Counter((r["kind"]) for r in rows)))
P("event ixname / trailing bytes after ix_name:", dict(restc))
P("rent values on init buys:", collections.Counter(r["rent"] for r in rows if r["kind"] == "buy" and r["init"]).most_common(5))
for k in ("buy", "sell", "fail"):
    rr = [r for r in rows if r["kind"] == k]
    res = np.array([r["resid"] for r in rr if r["resid"] is not None], float)
    P(f"{k}: n={len(rr):,}; resid==0: {(res == 0).sum():,}; |resid|<=1 lamport: {(np.abs(res) <= 1).sum():,}; nonzero: {(res != 0).sum()}; sum resid {res.sum() / 1e9:.9f} SOL; max |resid| {np.abs(res).max() if len(res) else 0}")
    bad = [r for r in rr if r["resid"]][:6]
    for r in bad: P("   nonzero:", r["sig"][:20], r["ixn"], r["ixname"], "nev", r["nev"], "sd", r["sd"], "calc", r["calc"], "resid", r["resid"])
P("closes:", [(r["closed"]) for r in rows if r["kind"] == "close"][:60])
P(f"sum sd (recorded, window) = {sum(r['sd'] for r in rows) / 1e9:+.9f} SOL")
open(f"{OUT}/r3.txt", "w").write("\n".join(L) + "\n")
