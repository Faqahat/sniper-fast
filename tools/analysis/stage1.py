#!/usr/bin/env python3
"""Long run, stage 1 (per segment): join every arbitrage-like transaction (rivals.jsonl, shred time) with
  - its executed result (exec.jsonl: Haan's PumpSwap stream) or, on our pools, the pool moves it made (moves.log),
  - its position on the leader's PoH clock (poh.log),
  - the trigger it reacted to: the last other transaction that moved one of its pools before it (moves + poh),
  - when each feed delivered it (txarr.log),
and write <seg>/joined.jsonl.gz plus per-slot feed statistics <seg>/feedslots.json.
usage: stage1.py <segment dir>"""
import json, sys, os, subprocess, gzip, collections, bisect

SEG = sys.argv[1].rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
WSOL = "So11111111111111111111111111111111111111112"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw


def sig8(sig): return b58d(sig)[:8].hex()


def lines(name):
    """plain file, or its .zst through bun"""
    p = os.path.join(SEG, name)
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["bun", os.path.join(HERE, "unzst.js"), p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout
        pr.wait()


meta = json.load(open(os.path.join(SEG, "meta.json")))
FEEDS = meta["feeds"]

# 1. rivals (shred time)
riv = {}
for l in lines("rivals.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    riv[r["sig"]] = r
print(f"{SEG}: {len(riv)} arbitrage-like transactions", file=sys.stderr)
want8 = {sig8(s): s for s in riv}

# 2. pool moves: who moved which of our pools
movers = collections.defaultdict(list)   # pool -> [(sig, slot)]
moved_by = collections.defaultdict(set)  # sig -> pools
for l in lines("moves.log"):
    p = l.split()
    if len(p) < 4: continue
    sg, slot, pool = p[0], int(p[1]), p[2]
    movers[pool].append((sg, slot))
    moved_by[sg].add(pool)
for sg in moved_by:
    if sg not in want8.values(): want8.setdefault(sig8(sg), sg)

# 3. executed results for the rivals, and the signer and result of every pool mover (to name triggers' signers)
res = {}
mover_exec = {}
for l in lines("exec.jsonl"):
    if '"sig"' not in l: continue
    try: e = json.loads(l)
    except Exception: continue
    if e["sig"] in riv: res[e["sig"]] = e
    elif e["sig"] in moved_by: mover_exec[e["sig"]] = (e["signer"], e["ok"])

# 4. PoH positions for every rival and every mover
poh = {}
for l in lines("poh.log"):
    p = l.split()
    if len(p) == 3 and p[0] in want8 and p[0] not in poh: poh[p[0]] = (int(p[1]), float(p[2]))
pos = lambda sig: poh.get(sig8(sig))
key = lambda p: p[0] * 400 + p[1]

# 5. arrivals per feed (rivals) + per slot feed statistics (every forwarded transaction)
arr = {}
fs = collections.defaultdict(lambda: [[0, 0, 0] for _ in FEEDS])   # slot -> per feed [seen, first, lag µs sum]
for l in lines("txarr.log"):
    p = l.split()
    if len(p) < 3 + len(FEEDS): continue
    slot = int(p[1]); d = p[3:3 + len(FEEDS)]
    st = fs[slot]
    for i, x in enumerate(d):
        if x == "-": continue
        v = int(x); st[i][0] += 1; st[i][2] += v
        if v == 0: st[i][1] += 1
    if p[0] in want8 and want8[p[0]] in riv: arr[want8[p[0]]] = d

# 6. triggers: per pool, movers sorted on the PoH clock
order = {}
for pool, ms in movers.items():
    xs = sorted((key(pos(s)), s) for s, _ in ms if pos(s))
    order[pool] = xs
signer_of = {s: v[0] for s, v in mover_exec.items()} | {s: r["signer"] for s, r in riv.items()}

out = gzip.open(os.path.join(SEG, "joined.jsonl.gz"), "wt")
n_trig = 0
for s, r in riv.items():
    e = res.get(s)
    pr = pos(s)
    trig = None
    if pr and r["pools"]:
        kr = key(pr)
        best = None
        for pool in r["pools"]:
            xs = order.get(pool)
            if not xs: continue
            i = bisect.bisect_left(xs, (kr, ""))
            while i > 0:
                i -= 1
                k, t = xs[i]
                if t == s or signer_of.get(t) == r["signer"]: continue
                if best is None or k > best[0]: best = (k, t, pool)
                break
        if best and kr - best[0] < 2000:
            trig = {"sig": best[1], "pool": best[2], "ms": round(kr - best[0], 3), "signer": signer_of.get(best[1])}
            n_trig += 1
    tips = [(t[2] or ("?" + t[0][:6]), t[1]) for t in r["tips"] if t[0] != r["signer"]]
    profit = None
    if e: profit = e["sol"] + int(e["tok"].get(WSOL, "0"))
    j = {"sig": s, "slot": r["slot"], "signer": r["signer"], "why": r["why"], "prog": (r["progs"] or [None])[0], "progs": r["progs"],
         "venues": r["venues"], "agg": r["agg"], "pools": r["pools"], "cu_limit": r["cu_limit"], "cu_price": r["cu_price"], "v1_fee": r["v1_fee"],
         "tips": tips, "nonce": r["nonce"], "v": r["v"], "n_sig": r["n_sig"], "alts": r["alts"], "disc": (r["head"] or ["", 0, 0])[0][:16],
         "dlen": (r["head"] or ["", 0, 0])[1], "n_keys": r["n_keys"], "feed": r["feed"], "t": r["t"],
         "poh": pr, "arr": arr.get(s), "moved": sorted(moved_by.get(s, ())),
         "ok": e["ok"] if e else (True if moved_by.get(s) else None), "err": e["err"] if e else None, "why_err": e["why"] if e else None,
         "fee": e["fee"] if e else None, "cu": e["cu"] if e else None, "idx": e["idx"] if e else None, "profit": profit,
         "tok_other": sorted(k for k, v in (e["tok"] if e else {}).items() if k != WSOL and v != "0"), "trig": trig}
    out.write(json.dumps(j) + "\n")
out.close()
json.dump({"feeds": FEEDS, "slots": {str(k): v for k, v in fs.items()}}, open(os.path.join(SEG, "feedslots.json"), "w"))
print(f"{SEG}: results {len(res)}, poh {sum(1 for s in riv if pos(s))}, triggers linked {n_trig}, arrivals {len(arr)}, slots {len(fs)}", file=sys.stderr)
