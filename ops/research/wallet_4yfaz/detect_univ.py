# READ-ONLY (host, no RPC): every create our engines DETECTED (first=1 lines) in local engine-log copies, with the engine's
# verdict; joined with 4yFAz's bought mints -> which of our verdicts his picks got, and his pick rate per verdict.
# usage: python3 detect_univ.py <trades_rows.json> <log> [<log> ...]   writes detect_univ.json
import sys, re, json, collections
KV = re.compile(r"(\w+)=(\S*)")
rows = json.load(open(sys.argv[1])); his = {r["mint"]: r for r in rows}
U = {}; spans = {}
for p in sys.argv[2:]:
    name = p.rsplit("/", 1)[-1]
    for line in open(p, errors="replace"):
        if "DETECT" not in line or "first=1" not in line: continue
        d = dict(KV.findall(line.split("DETECT", 1)[1]))
        m = d.get("mint")
        if not m or m in U: continue
        d["log"] = name; d["slot"] = int(d["slot"]); U[m] = d
        s = spans.setdefault(name, [d["slot"], d["slot"]]); s[0] = min(s[0], d["slot"]); s[1] = max(s[1], d["slot"])
json.dump(U, open("detect_univ.json", "w"))
print("detected creates", len(U))
# his buys inside any log span
inspan = [r for r in rows if any(a <= r["slot"] <= b + 5 for a, b in spans.values())]
seen = [r for r in inspan if r["mint"] in U]
print(f"his buys inside a log's slot span: {len(inspan)}; detected by our engine: {len(seen)}")
vc = collections.Counter(U[r["mint"]].get("verdict") for r in seen)
uc = collections.Counter(d.get("verdict") for m, d in U.items())
print("verdict of his picks (n, his pnl sum, mean):")
for v, n in vc.most_common():
    xs = [r["pnl"] for r in seen if U[r["mint"]].get("verdict") == v]
    print(f"  {v:28} {n:4}  of {uc[v]:6} detected ({n/uc[v]:.2%})  pnl {sum(xs):+.2f}  mean {sum(xs)/len(xs):+.3f}")
print("all verdicts in universe:", uc.most_common())
for r in inspan:
    if r["mint"] not in U: print("  not detected:", r["mint"], r["slot"])
