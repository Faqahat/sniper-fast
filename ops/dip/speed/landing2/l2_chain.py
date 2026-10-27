#!/usr/bin/env python3
# LANDING2 step 2 (read-only, local raw recording run_20261024_1425): every tx on each fired token from dump slot -3 to +8
# (fills AND failed txs) + every tx signed by our wallets in those slots + per-slot (pump tx count, max index).
# Output: OUT/chain_txs.json, OUT/slot_stats.json, OUT/file_first_slot.txt
import json, gzip, base64, re, sys, os, collections, glob
from multiprocessing import Pool

OUT = "/home/moiz/sniper-data/landing2"
COLLECT = "/home/moiz/sniper-data/collect"
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
HEAD = re.compile(r'^\{"s":(\d+),"i":(\d+)')
LO, HI = 3, 8
OURS = ("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR")


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n: n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def svc(acc):
    if acc in TIP: return TIP[acc]
    return "nozomi" if acc.startswith("noz") else "?" + acc[:6]


def trades(evs):
    out = []
    for e in evs or []:
        try: b = base64.b64decode(e)
        except Exception: continue
        if len(b) < 113 or b[:8] != DISC: continue
        u = lambda o: int.from_bytes(b[o:o + 8], "little")
        fb, cb = (u(161), u(209)) if len(b) >= 217 else (0, 0)
        out.append(dict(mint=b58(b[8:40]), sol=u(40), tok=u(48), buy=b[56] == 1, user=b58(b[57:89]), vsol=u(97), vtok=u(105), fbps=fb, cbps=cb))
    return out


def first_slot(fn):
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if m: return fn, int(m.group(1))
    except Exception:
        pass
    return fn, None


WANT = {}
def init(want):
    global WANT
    WANT = want


def one(fn):
    keep, stats = [], {}
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = HEAD.match(line)
                if not m: continue
                s = int(m.group(1))
                ws = WANT.get(s)
                if ws is None: continue
                i = int(m.group(2))
                st = stats.setdefault(s, [0, -1]); st[0] += 1; st[1] = max(st[1], i)
                ours = (OURS[0] in line) or (OURS[1] in line)
                r = None
                if not ours:
                    if not any(mt in line for mt in ws): continue
                r = json.loads(line)
                mints = set(r.get("mints") or [])
                if not ours and not (mints & ws): continue
                keep.append(dict(s=s, i=i, sig=r["sig"], err=r.get("err"), fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"),
                                 signer=(r.get("signers") or ["?"])[0], mints=sorted(mints), ixn=r.get("ixn"),
                                 tips=[(svc(a), lam) for a, lam in (r.get("tips") or [])], tr=trades(r.get("ev")), bt=r.get("bt"), ours=ours))
    except (EOFError, OSError, json.JSONDecodeError, gzip.BadGzipFile) as ex:
        print("  partial", fn, type(ex).__name__, file=sys.stderr)
    return keep, stats


def main():
    fires = json.load(open(f"{OUT}/fires_engine.json"))
    want = collections.defaultdict(set)
    for a in fires:
        for s in range(a["dump_slot"] - LO, a["dump_slot"] + HI + 1): want[s].add(a["mint"])
    files = sorted(glob.glob(f"{COLLECT}/run_20261024_1425/txs/txs_*.jsonl.gz"))
    with Pool(8) as p:
        fs = p.map(first_slot, files)
    fs = sorted([(f, s) for f, s in fs if s], key=lambda x: x[1])
    open(f"{OUT}/file_first_slot.txt", "w").write("".join(f"{f} {s}\n" for f, s in fs))
    sel = []
    for k, (f, s0) in enumerate(fs):
        s1 = fs[k + 1][1] if k + 1 < len(fs) else s0 + 10_000
        if any(s0 - 600 <= s <= s1 + 600 for s in want): sel.append(f)
    print("files", len(sel), "of", len(fs), "| slots wanted", len(want), min(want), "->", max(want), flush=True)
    with Pool(8, initializer=init, initargs=(dict(want),)) as p:
        res = p.map(one, sel, chunksize=1)
    seen, txs, stats = set(), [], {}
    for keep, st in res:
        for t in keep:
            if t["sig"] in seen: continue
            seen.add(t["sig"]); txs.append(t)
        for s, (n, mx) in st.items():
            o = stats.get(s)
            stats[s] = [max(n, o[0]), max(mx, o[1])] if o else [n, mx]
    txs.sort(key=lambda t: (t["s"], t["i"]))
    json.dump(txs, open(f"{OUT}/chain_txs.json", "w"))
    json.dump(stats, open(f"{OUT}/slot_stats.json", "w"))
    print("txs kept", len(txs), "ours", sum(t["ours"] for t in txs), "slots with stats", len(stats), "of", len(want))


if __name__ == "__main__":
    main()
