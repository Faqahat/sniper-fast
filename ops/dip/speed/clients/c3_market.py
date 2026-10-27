#!/usr/bin/env python3
"""CLIENTS study (10-25, read-only): market-wide ordering facts per leader client from the raw chain recordings
(every pump tx incl. failed, with block index, CU price/limit, tip labels). MEASURED.

For every big sell (>= 1 SOL, successful) on a bonding curve, the buys on the same mint after it:
  - same-slot share of the first reacting buy (index gap > 3), by client and by the dump's slot position in the leader's turn
  - per tip path (helius / nozomi / jito / astralane / 0slot / none / ...): how fast its reacting buys land (index gap, B-clock ms)
Per block: ordering vs CU price (share of adjacent pump-tx pairs in descending CU price; 0.5 = no relation).
usage: c3_market.py OUT.json [files_step]
"""
import gzip, json, os, sys, collections, glob, base64
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/truth")
import tl  # read-only helpers: leader(), leader_client(), client_class()

RUNS = ["/home/moiz/sniper-data/collect/run_20261023_1426/txs", "/home/moiz/sniper-data/collect/run_20261024_1425/txs"]
SMS = 212.0
DUMP_MIN = 1_000_000_000


DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])   # pump TradeEvent (same parser as speed/truth/a2_chain.py)
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def svc(acc):
    if acc in TIP: return TIP[acc]
    return "nozomi" if acc.startswith("noz") else "other"


def trades(evs):
    out = []
    for e in evs or []:
        try: b = base64.b64decode(e)
        except Exception: continue
        if len(b) < 113 or b[:8] != DISC: continue
        u = lambda o: int.from_bytes(b[o:o + 8], "little")
        out.append(dict(mint=b58(b[8:40]), sol=u(40), buy=b[56] == 1))
    return out


def path_of(tips):
    if not tips: return "none"
    labs = sorted({svc(a) for a, b in tips})
    return labs[0] if len(labs) == 1 else "multi"


def is_buy_attempt(t):
    if t.get("tr"):
        return bool(t["tr"][0].get("buy"))
    return any(n.startswith("Buy") for n in (t.get("ixn") or []))


def do_file(fn):
    slots = collections.defaultdict(list)
    try:
        for line in gzip.open(fn, "rt"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            d["tr"] = trades(d.get("ev")); d.pop("ev", None); d.pop("tb", None); d.pop("sd", None)
            slots[d["s"]].append(d)
    except Exception as e:
        return {"err": str(e)}
    out = {"dumps": [], "blocks": []}
    if not slots: return out
    lo, hi = min(slots), max(slots)   # slots cut by the file boundary are partial: skipped
    for s, txs in slots.items():
        if s in (lo, hi): continue
        txs.sort(key=lambda t: t["i"])
        n = max(t["i"] for t in txs) + 1
        # block ordering vs cu price: adjacent pump txs with a cu price, both successful or both any
        cups = [t.get("cup") for t in txs if t.get("cup") is not None]
        desc = asc = 0
        for a, b in zip(cups, cups[1:]):
            if a > b: desc += 1
            elif a < b: asc += 1
        nf = sum(1 for t in txs if t.get("err"))
        out["blocks"].append([s, n, len(txs), nf, desc, asc])
        nxt = slots.get(s + 1)
        for k, t in enumerate(txs):
            tr = t.get("tr") or []
            if t.get("err") or not tr or tr[0].get("buy") or tr[0].get("sol", 0) < DUMP_MIN:
                continue
            mint = tr[0]["mint"]
            di = t["i"]
            reacts = []
            for u in txs[k + 1:]:
                if mint in (u.get("mints") or []) and is_buy_attempt(u) and u["i"] - di > 3:
                    reacts.append([0, u["i"], path_of(u.get("tips")), u.get("cup"), u.get("cul"), 1 if u.get("err") else 0, (u.get("signers") or [""])[0][:8]])
                    if len(reacts) >= 6: break
            nxt_first = None
            if s + 1 == hi: nxt = None
            if nxt is not None and len(reacts) < 6:
                for u in sorted(nxt, key=lambda x: x["i"]):
                    if mint in (u.get("mints") or []) and is_buy_attempt(u):
                        nxt_first = [1, u["i"], path_of(u.get("tips")), u.get("cup"), u.get("cul"), 1 if u.get("err") else 0, (u.get("signers") or [""])[0][:8]]
                        break
            out["dumps"].append([s, di, n, tr[0]["sol"], reacts, nxt_first, nxt is not None])
    return out


def main():
    outp = sys.argv[1]
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    files = []
    for r in RUNS:
        files += sorted(glob.glob(os.path.join(r, "txs_*.jsonl.gz")))[::step]
    with Pool(4) as p:
        res = p.map(do_file, files, chunksize=1)
    dumps, blocks = [], []
    for r in res:
        if "err" in r: continue
        dumps += r["dumps"]; blocks += r["blocks"]
    # annotate client and turn position
    cache = {}
    def info(s):
        if s not in cache:
            ld = tl.leader(s)
            c = tl.leader_client(ld) if ld else None
            cache[s] = (ld, c, tl.turn_pos(s) if ld else None)
        return cache[s]
    for d in dumps:
        ld, c, tp = info(d[0]); d += [c, tp]
    for b in blocks:
        ld, c, tp = info(b[0]); b += [c, tp]
    json.dump({"dumps": dumps, "blocks": blocks, "files": len(files)}, open(outp, "w"))
    print("files", len(files), "dumps", len(dumps), "blocks", len(blocks))


if __name__ == "__main__":
    main()
