# read-only helpers for the head-to-head analysis
import os, json, gzip, glob, base64, collections
W = "/home/moiz/sniper/ops/agents/headtohead/work"
TIPMAP = json.load(open("/home/moiz/sniper/ops/agents/tipmap.json"))
OURS = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def trades_of(r):
    out = []
    for e in r.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] != TRADE or len(raw) < 225: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append(dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, user=b58(raw[57:89]), vsol=u(97), vtok=u(105),
                        fbps=u(161), fee=u(169), cbps=u(209), cfee=u(217)))
    return out
def relay(acct):
    if acct in TIPMAP: return TIPMAP[acct]
    if acct.startswith("noz"): return "nozomi?"
    return "?"
def errcode(err):
    if not err: return None
    if isinstance(err, dict) and "InstructionError" in err:
        ix, e = err["InstructionError"]
        if isinstance(e, dict) and "Custom" in e: return f"ix{ix}:{e['Custom']}"
        return f"ix{ix}:{e}"
    return json.dumps(err)[:40]
def load_ext():
    """mint -> list of tx records (deduped by sig) sorted by (s, i); each record gets 'tr' (decoded trades) and 'ec' (error code)"""
    by = collections.defaultdict(dict)
    for f in sorted(glob.glob(W + "/ext/*.jsonl.gz")):
        for line in gzip.open(f, "rt"):
            r = json.loads(line)
            r["tr"] = trades_of(r); r["ec"] = errcode(r.get("err"))
            for m in r.get("mints") or []:
                by[m][r["sig"]] = r
    return {m: sorted(v.values(), key=lambda r: (r["s"], r["i"])) for m, v in by.items()}
def tokens_out(vsol, vtok, sol_in):
    # pump constant product (virtual reserves), integer floor
    return vtok - (vsol * vtok + (vsol + sol_in) - 1) // (vsol + sol_in)
