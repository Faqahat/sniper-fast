# development-window check (17:09-00:34) of walk-forward deployer lists by ATTEMPT RATE (attempts / launches seen before t)
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); A = json.load(open("attempts.json"))
DC = "/home/moiz/sniper/ops/snipers/devcheck"
ev = []; launch_ev = []
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt") and m not in L: ev.append((v["bt"], v["signer"], "att"))
for m, c in L.items():
    if not c.get("bt"): continue
    launch_ev.append((c["bt"], c["user"], "launch"))
    if "9Sh2fd" in A.get(m, {}) or "DGmspi" in A.get(m, {}): ev.append((c["bt"], c["user"], "att"))
allev = sorted(ev + launch_ev)
rows = []
with gzip.open("fwd2.jsonl.gz", "rt") as f:
    meta = json.loads(f.readline()); NAMES = meta["rules"]
    for l in f: rows.append(json.loads(l))
rows.sort(key=lambda r: r["bt"]); mid = rows[0]["bt"] + (rows[-1]["bt"] - rows[0]["bt"]) / 2
i = NAMES.index("eos1"); natt = collections.Counter(); nl = collections.Counter(); k = 0; state = {}
for r in rows:
    while k < len(allev) and allev[k][0] < r["bt"]:
        t, d, kind = allev[k]
        if kind == "att": natt[d] += 1
        else: nl[d] += 1
        k += 1
    d = r["signer"]; state[r["mint"]] = (natt[d], nl[d])
for name, f in (("ANY attempt >= 1", lambda a, n: a >= 1), ("attempts >= 2", lambda a, n: a >= 2),
                ("attempts >= 2 and rate >= 5%", lambda a, n: a >= 2 and (n == 0 or a / n >= 0.05)),
                ("attempts >= 2 and rate >= 10%", lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10)),
                ("attempts >= 2 and rate >= 20%", lambda a, n: a >= 2 and (n == 0 or a / n >= 0.20)),
                ("attempts >= 3 and rate >= 10%", lambda a, n: a >= 3 and (n == 0 or a / n >= 0.10))):
    R = [r for r in rows if f(*state[r["mint"]])]
    out = []
    for c in ("L35", "L45", "L60", "L75"):
        v = [r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"]]; a = sum(r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"] and r["bt"] < mid)
        out.append(f"{c} {sum(v):+6.2f} ({a:+.1f}/{sum(v) - a:+.1f})")
    print(f"{name:32} n {len(R):4} | " + " | ".join(out))
