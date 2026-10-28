#!/usr/bin/env python3
"""recon step 3 (read-only): per recorded E2x1 tx: decode TradeEvent(s), tips (relay via tipmap), CU price/limit, programs,
rent created/closed, and the wallet SOL delta rebuilt from its parts vs the recorded delta.
  trade cash (TradeEvent): buy -(sol + fee + cfee), sell +(sol - fee - cfee)
  wallet delta = trade - txfee - tips - rent_created + rent_closed (+ other, e.g. holder-fee distributions)
Out: tx.pkl (list of dicts, all recorded txs incl. third-party ones touching his wallet), r3.txt"""
import json, pickle, base64, struct, collections
import numpy as np
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
TIP = json.load(open(f"{OUT}/tipmap.json"))
RENTS = {1488440: "spl165", 1513840: "t22_170"}   # MEASURED rent of a 165-byte SPL / 170-byte Token-2022 account (5080 lamports/byte incl. 128 overhead)
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
    tail = b[o:]
    return dict(mint=mint, sol=sol, tok=tok, buy=bool(buy), user=user, vsol=vsol, vtok=vtok, rsol=rsol, rtok=rtok, fbps=fbps, fee=fee, cbps=cbps, cfee=cfee,
                creator=creator, tail=tail.hex())
if __name__ == "__main__":
    rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
    rows = []
    for sig, d in rec.items():
        ix = d.get("ixn") or []; ixs = set(ix); ok = d["err"] is None
        sd = dict(d.get("sd") or [])
        tips = [(a, v) for a, v in (d.get("tips") or [])]
        tipsum = sum(v for a, v in tips) if ok else 0
        evs = [parse(b) for b in chunks(d.get("ev")) if b[:8] == DISC and len(b) >= 225]
        mine = [e for e in evs if e["user"] == H]
        own = d["signers"][0] == H
        kind = ("third" if not own else "fail" if not ok else "buy" if "BuyExactSolIn" in ixs or any(x.startswith("Buy") for x in ixs)
                else "sell" if "Sell" in ixs else "other")
        r = dict(sig=sig, s=d["s"], i=d["i"], bt=d["bt"], ok=ok, err=d["err"], kind=kind, own=own, signers=d["signers"], txfee=d["fee"] if own else 0,
                 cu=d.get("cu"), cup=d.get("cup"), cul=d.get("cul"), tips=tipsum, tip_acc=[a for a, v in tips], tip_amt=[v for a, v in tips],
                 relay="+".join(sorted(set(TIP.get(a, "?" + a[:6]) for a, v in tips))) or "none", progs=d.get("progs"), ixn="|".join(ix),
                 mints=d.get("mints"), sd=sd.get(H, 0), nev=len(mine), mint=(mine[0]["mint"] if mine else (d.get("mints") or [None])[0]),
                 events=mine, trade=0, sol=0, tok=0, pfee=0, cfee=0, rent_c=0, rent_x=0, other=0, tb=d.get("tb"))
        if mine:
            e = mine[0]
            r.update(sol=e["sol"], tok=e["tok"], pfee=e["fee"], cfee=e["cfee"], side=("buy" if e["buy"] else "sell"), vsol=e["vsol"], vtok=e["vtok"], fbps=e["fbps"], cbps=e["cbps"], tail=e["tail"])
            r["trade"] = sum((-(x["sol"] + x["fee"] + x["cfee"]) if x["buy"] else (x["sol"] - x["fee"] - x["cfee"])) for x in mine)
        if own and ok:
            rest = r["sd"] - (r["trade"] - r["txfee"] - tipsum)
            # rent accounts: other accounts in sd with exactly +-rent (created: +, closed: -)
            cre = [v for a, v in sd.items() if a != H and a not in dict(tips) and v in RENTS]
            clo = [-v for a, v in sd.items() if a != H and -v in RENTS]
            r["rent_c"] = sum(cre); r["rent_x"] = sum(clo)
            r["other"] = rest + r["rent_c"] - r["rent_x"]
        elif own and not ok:
            r["other"] = r["sd"] + r["txfee"]
        else:
            r["other"] = r["sd"]
        rows.append(r)
    rows.sort(key=lambda r: (r["s"], r["i"]))
    pickle.dump(rows, open(f"{OUT}/tx.pkl", "wb"))
    L = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); L.append(s)
    P("txs", len(rows), dict(collections.Counter(r["kind"] for r in rows)))
    for k in ("buy", "sell", "fail", "other", "third"):
        rr = [r for r in rows if r["kind"] == k]
        o = np.array([r["other"] for r in rr]); P(f"{k}: n={len(rr)} other==0: {(o == 0).sum()} nonzero {(o != 0).sum()} sum {o.sum() / 1e9:+.9f}")
        for r in [r for r in rr if r["other"]][:5]: P("   ", r["sig"][:16], r["ixn"][:80], "sd", r["sd"], "trade", r["trade"], "fee", r["txfee"], "tips", r["tips"], "rc", r["rent_c"], "rx", r["rent_x"], "other", r["other"], "nev", r["nev"])
    P("tail hex lengths (event bytes after cfee):", collections.Counter(len(r.get("tail", "")) // 2 for r in rows if r["nev"]).most_common(5))
    P("relays own ok:", collections.Counter((r["kind"], r["relay"]) for r in rows if r["own"] and r["ok"]).most_common(30))
    P("tip amounts:", collections.Counter((r["kind"], tuple(r["tip_amt"])) for r in rows if r["own"] and r["ok"]).most_common(30))
    P("cup/cul:", collections.Counter((r["kind"], r["cup"], r["cul"]) for r in rows if r["own"]).most_common(30))
    P("progs:", collections.Counter((r["kind"], tuple(r["progs"] or [])) for r in rows if r["own"]).most_common(12))
    open(f"{OUT}/r3.txt", "w").write("\n".join(L) + "\n")
