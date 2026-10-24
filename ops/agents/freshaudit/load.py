#!/usr/bin/env python3
# helpers: load extracted rows (x/<run>/*.jsonl.gz) into memory
import os, gzip, json, glob, collections
X = "/home/moiz/sniper/ops/agents/freshaudit/x"
OURS = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
def chunks(run, t0=0, t1=10**12):
    fs = sorted(glob.glob(os.path.join(X, run, "txs_*.jsonl.gz")))
    return [f for f in fs if t0 <= int(os.path.basename(f)[4:14]) <= t1]
def load(run, t0=0, t1=10**12, kinds=("D", "F", "O"), aggs=False):
    D, F, O = [], {}, []
    SL = {}; RELAY = collections.Counter(); RELAYTIP = collections.Counter(); SG = collections.defaultdict(lambda: [0, 0, 0, 0, collections.Counter()])
    for f in chunks(run, t0, t1):
        try:
            for line in gzip.open(f, "rt"):
                k = line[2]
                if k == "D" and "D" in kinds: D.append(json.loads(line)[1])
                elif k == "F" and "F" in kinds:
                    r = json.loads(line)[1]; F[r["sig"]] = r
                elif k == "O" and "O" in kinds: O.append(json.loads(line)[1])
                elif k == "S" and line.startswith('["SLOTS'):
                    if aggs: SL.update({int(a): b for a, b in json.loads(line)[1].items()})
                elif aggs and line.startswith('["RELAY'):
                    x = json.loads(line); RELAY.update(x[1]); RELAYTIP.update(x[2])
                elif aggs and line.startswith('["SIGNERS'):
                    for g, v in json.loads(line)[1].items():
                        a = SG[g]; a[0] += v[0]; a[1] += v[1]; a[2] += v[2]; a[3] += v[3]; a[4].update(v[4])
        except (EOFError, OSError) as e:
            print("WARN", f, e)
    return dict(D=D, F=F, O=O, SL=SL, RELAY=RELAY, RELAYTIP=RELAYTIP, SG=SG)
def by_mint(F):
    M = collections.defaultdict(list)
    for r in F.values():
        ms = set(r["mints"]) | {e[0] for e in r["ev"]}
        for m in ms: M[m].append(r)
    for m in M: M[m].sort(key=lambda r: (r["s"], r["i"]))
    return M
def relays(r): return ",".join(sorted({t[0] for t in r["tips"]})) or "-"
def tipsum(r): return sum(t[1] for t in r["tips"])
def trade_of(r, m):
    for e in r["ev"]:
        if e[0] == m: return e
    return None
def is_buy_attempt(r, m):
    e = trade_of(r, m)
    if e is not None: return e[1] == 1
    return any(x.startswith("Buy") for x in r["ixn"]) or any("buy" in x.lower() for x in r["ixn"])
