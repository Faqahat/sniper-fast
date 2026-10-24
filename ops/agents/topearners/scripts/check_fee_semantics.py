# verify TradeEvent sol/fee semantics vs the payer's SOL delta on simple single-trade txs
import sys, json, gzip, base64, collections
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
path = sys.argv[1]; n = 0; res = collections.Counter(); ex = []
for line in gzip.open(path, "rt"):
    r = json.loads(line)
    if r.get("err"): continue
    evs = []
    for e in r.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] == TRADE and len(raw) >= 225: evs.append(raw)
    if len(evs) != 1: continue
    raw = evs[0]; u = lambda o: int.from_bytes(raw[o:o + 8], "little")
    user = b58(raw[57:89]); buy = raw[56]; sol = u(40); fl = u(169); cfl = u(217)
    payer = r["signers"][0]
    if payer != user: continue
    sd = dict(r["sd"]); d = sd.get(payer, 0)
    tips = sum(x[1] for x in r["tips"])
    # rent: count accounts with +2039280 (ATA) created
    rent = sum(v for k, v in r["sd"] if v in (2039280, 2074080))
    rentref = sum(-v for k, v in r["sd"] if k != payer and v in (-2039280, -2074080))
    if buy:
        pred = -(sol + fl + cfl) - r["fee"] - tips
    else:
        pred = (sol - fl - cfl) - r["fee"] - tips
    diff = d - pred
    res[(buy, diff == 0, diff == -rent, diff == rentref)] += 1
    if len(ex) < 6 and diff != 0 and diff != -rent: ex.append((buy, sol, fl, cfl, r["fee"], tips, d, diff, rent, r["sd"][:6], r["ixn"]))
    n += 1
    if n > 20000: break
print(res)
for x in ex: print(x)
