#!/usr/bin/env python3
# haqq SELL study, step 3: haqq's own ledger from the recording (htx_R*.jsonl.gz). One row per haqq tx (trade, failed attempt,
# close-account, other) with the exact wallet SOL delta (sd), tx fee, tips, rent, token balance before/after (tb).
# Overlapping runs (R3/R4) deduped by signature. Output: /home/moiz/sniper-data/haqq/ledger.json
import json, gzip, base64, collections, time
W = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238]); OUT = "/home/moiz/sniper-data/haqq"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
rows = []; seen = set()
for run in ("R1", "R2", "R3", "R4"):
    for l in gzip.open(f"{OUT}/htx_{run}.jsonl.gz", "rt"):
        r = json.loads(l)
        if r["sig"] in seen: continue
        seen.add(r["sig"])
        dsol = next((d for k, d in r.get("sd") or [] if k == W), 0)
        tips = sum(d for _, d in r.get("tips") or [])
        evs = []
        for e in r.get("ev") or []:
            raw = base64.b64decode(e + "=" * (-len(e) % 4))
            if raw[:8] != TD or len(raw) < 225 or b58(raw[57:89]) != W: continue
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            evs.append(dict(mint=b58(raw[8:40]), sol=u(40), tok=u(48), buy=raw[56] == 1, vsol=u(97), vtok=u(105), fee=u(169), cfee=u(217), fbps=u(161), cbps=u(209)))
        tb = {x[0]: (x[2], x[3]) for x in r.get("tb") or [] if x[1] == W}
        ixs = " ".join(r.get("ixn") or [])
        kind = ("buy" if evs[0]["buy"] else "sell") if evs else ("fail" if r.get("err") else ("close" if "CloseAccount" in ixs else "other"))
        rows.append(dict(run=run, s=r["s"], i=r["i"], bt=r.get("bt") or 0, sig=r["sig"], ok=r.get("err") is None, err=json.dumps(r.get("err"))[:60] if r.get("err") else None,
                         fee=r.get("fee") or 0, cup=r.get("cup"), cul=r.get("cul"), cu=r.get("cu"), tips=tips, tipacc=[k for k, _ in r.get("tips") or []], dsol=dsol,
                         kind=kind, ixn=ixs[:120], mints=r.get("mints") or [], evs=evs, tb=tb, sd=r.get("sd")))
rows.sort(key=lambda x: (x["s"], x["i"]))
json.dump(rows, open(f"{OUT}/ledger.json", "w"))
c = collections.Counter((r["run"], r["kind"]) for r in rows)
print(sorted(c.items()))
# sanity: wallet delta vs event amounts
d = collections.Counter(); ex = []
for r in rows:
    if r["kind"] in ("buy", "sell") and len(r["evs"]) == 1:
        e = r["evs"][0]
        exp = (-(e["sol"] + e["fee"] + e["cfee"]) if e["buy"] else (e["sol"] - e["fee"] - e["cfee"])) - r["fee"] - r["tips"]
        diff = r["dsol"] - exp
        d[(r["kind"], "InitializeAccount3" in r["ixn"], round(diff / 1e5))] += 1
        if len(ex) < 3 and abs(diff) > 1000 and "InitializeAccount3" not in r["ixn"]: ex.append((r["sig"], diff))
print("dsol - expected (units of 1e5 lamports):", d.most_common(12)); print(ex)
