"""Parse a getTransaction (jsonParsed) result into the same row shape as r3 (wallet delta, pump trade events, CU-price code,
rent of created token accounts, closes, wraps/unwraps, transfers). Read-only helper."""
import base64, struct
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB = "ComputeBudget111111111111111111111111111111"
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
RENT = 1488440


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def b58d(s):
    n = 0
    for c in s: n = n * 58 + A58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b


def parse_trade(b):
    o = 8; mint = b58(b[o:o + 32]); o += 32
    sol, tok = struct.unpack_from("<QQ", b, o); o += 16
    buy = b[o]; o += 1; user = b58(b[o:o + 32]); o += 32; o += 8
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32; fbps, fee = struct.unpack_from("<QQ", b, o); o += 16
    o += 32; cbps, cfee = struct.unpack_from("<QQ", b, o)
    return dict(mint=mint, sol=sol, tok=tok, buy=bool(buy), user=user, vsol=vsol, vtok=vtok, fbps=fbps, fee=fee, cbps=cbps, cfee=cfee)


def all_ix(res):
    msg = res["transaction"]["message"]
    for x in msg["instructions"]: yield 1, x
    for g in res["meta"].get("innerInstructions") or []:
        for x in g["instructions"]: yield 2, x


def parse(res):
    msg = res["transaction"]["message"]; meta = res["meta"]
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg["accountKeys"]]
    # v0/v1 with lookup tables: loaded addresses appended
    la = meta.get("loadedAddresses") or {}
    keys_all = keys + (la.get("writable") or []) + (la.get("readonly") or [])
    hi = keys_all.index(H) if H in keys_all else None
    sd = (meta["postBalances"][hi] - meta["preBalances"][hi]) if hi is not None else 0
    r = dict(sig=res["transaction"]["signatures"][0], s=res["slot"], i=res.get("transactionIndex"), bt=res["blockTime"], ok=meta["err"] is None,
             err=meta["err"], txfee=meta["fee"], payer=keys[0], sd=sd, cup=None, code=None, events=[], trade=0, rent=0, n_created=0,
             n_closed=0, closed_lamports=0, wrap=0, unwrap=0, transfers=[], progs=sorted(set(x.get("programId", "") for _, x in all_ix(res))),
             top=[(x.get("program") or x.get("programId", "")[:8]) + ":" + (x["parsed"]["type"] if isinstance(x.get("parsed"), dict) else "") for x in msg["instructions"]],
             pre=meta["preBalances"][hi] if hi is not None else None, post=meta["postBalances"][hi] if hi is not None else None,
             ptb=meta.get("preTokenBalances") or [], qtb=meta.get("postTokenBalances") or [])
    for lvl, x in all_ix(res):
        pid = x.get("programId")
        if pid == CB and lvl == 1 and "data" in x:
            d = b58d(x["data"])
            if d and d[0] == 3 and len(d) >= 9: r["cup"] = struct.unpack_from("<Q", d, 1)[0]; r["code"] = r["cup"] % 1000
        if pid == PUMP and lvl == 2 and "data" in x:
            d = b58d(x["data"])
            if d[:8] == CPI and d[8:16] == DISC and len(d) >= 8 + 225:
                e = parse_trade(d[8:])
                if e["user"] == H: r["events"].append(e)
        p = x.get("parsed")
        if isinstance(p, dict):
            t = p.get("type"); info = p.get("info") or {}
            if x.get("program") == "system" and t in ("createAccountWithSeed", "createAccount") and info.get("source") == H:
                r["n_created"] += 1; r["rent"] += int(info.get("lamports", 0))
            if x.get("program") == "system" and t == "transfer":
                r["transfers"].append((lvl, info.get("source"), info.get("destination"), int(info.get("lamports", 0))))
            if x.get("program", "").startswith("spl-token") and t == "closeAccount" and info.get("destination") == H:
                r["n_closed"] += 1
    for e in r["events"]:
        r["trade"] += -(e["sol"] + e["fee"] + e["cfee"]) if e["buy"] else (e["sol"] - e["fee"] - e["cfee"])
    return r
