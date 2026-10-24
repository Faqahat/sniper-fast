#!/usr/bin/env python3
# TRIGGER HUNT 1 (read-only): every tx touching the group's 77 tokens (g3/p2 raw lines) -> what happened on the token in the 60 s before
# the group's first buy. Prints a manual view for a sample and counts instruction names / signers / gaps right before the buy.
import json, glob, base64, collections, statistics, pickle, gzip, time
G = set(l.strip() for l in open("../g3/grp.txt") if l.strip())
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
MS = set(l.strip() for l in open("../g3/mints.txt") if l.strip())
TX = collections.defaultdict(dict)
for f in glob.glob("../g3/p2/*.jsonl") + glob.glob("../g3/p1/*.jsonl"):
    for line in open(f):
        try: r = json.loads(line)
        except Exception: continue
        for m in (r.get("mints") or []):
            if m in MS: TX[m][r["sig"]] = r
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def ms(r): return int(r["s"]) * 212.0 + int(r["i"]) / max(SS.get(int(r["s"]), 0), int(r["i"]) + 1, 380) * 212.0
def trade(r, m):
    for e in r.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129 and b58(raw[8:40]) == m:
            return ("BUY" if raw[56] == 1 else "SELL", int.from_bytes(raw[40:48], "little") / 1e9, b58(raw[57:89]))
    return None
L = {}
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] in MS: L[c["mint"]] = c
out = []
for m, d in TX.items():
    rows = sorted(d.values(), key=lambda r: (int(r["s"]), int(r["i"])))
    rows = [r for r in rows if str(r.get("err")) in ("None", "null")]
    gb = next((r for r in rows if (r.get("signers") or [None])[0] in G and (trade(r, m) or ("", 0, ""))[0] == "BUY"), None)
    if not gb: continue
    t0 = ms(gb); before = [r for r in rows if ms(r) < t0]
    out.append(dict(m=m, t0=t0, gb=gb, before=before, rows=rows, L=L.get(m)))
pickle.dump(out, gzip.open("pre.pkl.gz", "wb"))
print(f"tokens with a group buy: {len(out)}")
ixc = collections.Counter(); ixc_any = collections.Counter(); lastsig = collections.Counter(); gaps = []; lastside = collections.Counter(); nontrade = collections.Counter()
for o in out:
    b = o["before"]
    if not b: continue
    last = b[-1]; gaps.append((o["t0"] - ms(last)) / 1000)
    tr = trade(last, o["m"]); lastside[(tr[0] if tr else "non-trade")] += 1
    lastsig[(last.get("signers") or ["?"])[0]] += 1
    w30 = [r for r in b if o["t0"] - ms(r) <= 30_000]
    for r in w30:
        for x in set(r.get("ixn") or []): ixc_any[x] += 1
        if not trade(r, o["m"]): nontrade[tuple(sorted(set(r.get("ixn") or [])))[:6]] += 1
print("gap from the previous tx on the token to the group's buy (s): median", round(statistics.median(gaps), 2), "| p10/p90", [round(x, 2) for x in statistics.quantiles(gaps, n=10)[::8]])
print("previous tx kind:", lastside.most_common())
print("signer of the previous tx (repeats):", [(s[:8], n) for s, n in lastsig.most_common(6)])
print("instruction names seen in the 30 s before (tokens containing them):", ixc_any.most_common(25))
print("non-trade txs in the 30 s before:", nontrade.most_common(10))
for o in out[:12]:
    c = o["L"] or {}
    print(f"\n=== {o['m'][:8]} '{(c.get('name') or '')[:20]}' uri {str(c.get('uri'))[:60]} | creator {str(c.get('creator'))[:8]} | group buy at {time.strftime('%m-%d %H:%M:%S', time.gmtime(int(o['gb']['bt']) + 18000))} PKT, token age {(int(o['gb']['s']) - int(c.get('slot') or o['gb']['s'])) * 0.212:.0f} s")
    for r in o["before"][-8:]:
        tr = trade(r, o["m"]); sg = (r.get("signers") or ["?"])[0]
        print(f"   {(ms(r) - o['t0']) / 1000:+8.2f}s  {sg[:8]}{'(dev)' if sg == c.get('creator') else ''}  {tr[0] + ' ' + format(tr[1], '.3f') if tr else 'NONTRADE'}  ixn {(r.get('ixn') or [])[:6]}")
    print(f"   +0.00s  GROUP BUY  ixn {(o['gb'].get('ixn') or [])[:8]}")
