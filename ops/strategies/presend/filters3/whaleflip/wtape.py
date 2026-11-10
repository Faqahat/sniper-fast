"""WHALEFLIP chain tapes from w2's raw rows (MEASURED; every successful pump.fun tx on our filled mints, chain order).
Per mint: list of tx dicts {s, i, sig, sg, cl, own: {owner: (pre, post)}, curve_post, vsol, vtok, seller, sold, buyer, bought}
  curve = the owner present in the most txs of that mint (the bonding curve); vtok = curve balance + 73e12, vsol = K / vtok
  (K = 30e9 x 1073e12, pump's virtual reserves; checked against the engine's own states in w4).
Block-position clock (c37lib): cc(s, i) = s*212 + (i+0.5)/(maxi(s)+1)*212 ms (maxi from every raw tx of the slot)."""
import os, json, glob, pickle, collections
D = "/home/it/sniper-data/filters3/whaleflip"
K = 30_000_000_000 * 1_073_000_000_000_000
VOFF = 73_000_000_000_000
SMS = 212.0
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}


def build():
    cache = f"{D}/tapes.pkl"
    if os.path.exists(cache): return pickle.load(open(cache, "rb"))
    raw = collections.defaultdict(dict); maxi = {}
    for fn in sorted(glob.glob(f"{D}/raw/*/txs_*.jsonl")):
        for l in open(fn):
            d = json.loads(l)
            for m in {x[0] for x in d["tb"]}:
                raw[m][d["sig"]] = d
        mx = json.load(open(fn + ".maxi.json"))
        for s, i in mx.items():
            s = int(s)
            if i > maxi.get(s, -1): maxi[s] = i
    tapes = {}
    for m, txs in raw.items():
        cnt = collections.Counter()
        for d in txs.values():
            for x in d["tb"]:
                if x[0] == m: cnt[x[1]] += 1
        curve = cnt.most_common(1)[0][0]
        rows = []
        for d in sorted(txs.values(), key=lambda d: (d["s"], d["i"])):
            own = {}
            for mm, o, pre, post in d["tb"]:
                if mm != m: continue
                a, b = own.get(o, (0, 0)); own[o] = (a + (pre or 0), b + (post or 0))
            if curve not in own: continue
            cp = own[curve][1]
            vtok = cp + VOFF; vsol = K / vtok
            dl = {o: b - a for o, (a, b) in own.items() if o != curve}
            sel = min(dl.items(), key=lambda kv: kv[1], default=(None, 0))
            buy = max(dl.items(), key=lambda kv: kv[1], default=(None, 0))
            rows.append({"s": d["s"], "i": d["i"], "sig": d["sig"], "sg": d["sg"], "cl": d["cl"], "own": {o: v for o, v in own.items() if o != curve},
                         "cpre": own[curve][0], "cpost": cp, "vsol": vsol, "vtok": vtok, "p": vsol / vtok,
                         "seller": sel[0] if sel[1] < 0 else None, "sold": -sel[1] if sel[1] < 0 else 0,
                         "buyer": buy[0] if buy[1] > 0 else None, "bought": buy[1] if buy[1] > 0 else 0,
                         "ours": any(o in OURS for o in own) or d["sg"] in OURS})
        tapes[m] = {"curve": curve, "rows": rows}
    out = {"tapes": tapes, "maxi": maxi}
    pickle.dump(out, open(cache, "wb"))
    return out


def cc(maxi, s, i):
    mx = maxi.get(s)
    if mx is None or mx < i: mx = max(i, 400)
    return s * SMS + (i + 0.5) / (mx + 1) * SMS


def price_pre(row):
    """price just before this tx (curve pre balance)"""
    vt = row["cpre"] + VOFF
    return (K / vt) / vt
