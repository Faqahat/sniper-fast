#!/usr/bin/env python3
# SPEED TRUTH step 2 (read-only, local raw recording): every tx on the attempt tokens around each fire, fills AND failed txs,
# plus every tx signed by our wallets, plus per-slot max index / tx count (block-size lower bound) for the window slots.
# Input: OUT/attempts_engine.json, OUT/file_first_slot.txt. Output: OUT/chain_txs.json, OUT/slot_stats.json
import json, gzip, base64, re, sys, os, collections
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
HEAD = re.compile(r'^\{"s":(\d+),"i":(\d+)')
LO, HI = 3, 8        # window: dump slot - LO .. dump slot + HI


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


WANT = {}     # slot -> set(mints)
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
                ours = ('2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE' in line) or ('EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR' in line)
                if ws is None and not ours: continue
                i = int(m.group(2))
                if ws is not None:
                    st = stats.setdefault(s, [0, -1]); st[0] += 1; st[1] = max(st[1], i)
                r = json.loads(line)
                mints = set(r.get("mints") or [])
                if not ours and not (mints & ws): continue
                keep.append(dict(s=s, i=i, sig=r["sig"], err=r.get("err"), fee=r.get("fee"), cu=r.get("cu"), cup=r.get("cup"), cul=r.get("cul"),
                                 signer=(r.get("signers") or ["?"])[0], signers=r.get("signers"), mints=sorted(mints), ixn=r.get("ixn"),
                                 tips=[(svc(a), lam) for a, lam in (r.get("tips") or [])], tr=trades(r.get("ev")), bt=r.get("bt"), ours=ours))
    except (EOFError, OSError, json.JSONDecodeError, gzip.BadGzipFile) as ex:
        print("  partial", fn, type(ex).__name__, file=sys.stderr)
    return keep, stats


def main():
    att = json.load(open(f"{tl.OUT}/attempts_engine.json"))
    want = collections.defaultdict(set)
    for a in att:
        for s in range(a["dump_slot"] - LO, a["dump_slot"] + HI + 1): want[s].add(a["mint"])
    lo, hi = min(want), max(want)
    idx = [l.split() for l in open(f"{tl.OUT}/file_first_slot.txt") if len(l.split()) == 2]
    idx = [(f, int(s)) for f, s in idx]
    sel = []
    for run in ("run_20261023_1426", "run_20261024_1425"):
        fs = sorted([x for x in idx if x[0].startswith(run)], key=lambda x: x[1])
        for k, (f, s0) in enumerate(fs):
            s1 = fs[k + 1][1] if k + 1 < len(fs) else s0 + 10_000
            if any(s0 - 600 <= s <= s1 + 600 for s in want):
                sel.append(f"{tl.COLLECT}/{f}")
    print("files", len(sel), "slots wanted", len(want), lo, "->", hi, flush=True)
    with Pool(5, initializer=init, initargs=(dict(want),)) as p:
        res = p.map(one, sel, chunksize=1)
    seen, txs, stats = set(), [], {}
    for keep, st in res:
        for t in keep:
            if t["sig"] in seen: continue
            seen.add(t["sig"]); txs.append(t)
        for s, (n, mx) in st.items():
            o = stats.get(s)
            stats[s] = [max(n, o[0]), max(mx, o[1])] if o else [n, mx]   # the same slot in both recordings: take the larger
    txs.sort(key=lambda t: (t["s"], t["i"]))
    json.dump(txs, open(f"{tl.OUT}/chain_txs.json", "w"))
    json.dump(stats, open(f"{tl.OUT}/slot_stats.json", "w"))
    print("txs kept", len(txs), "ours", sum(t["ours"] for t in txs), "slots with stats", len(stats), "of", len(want))


if __name__ == "__main__":
    main()
