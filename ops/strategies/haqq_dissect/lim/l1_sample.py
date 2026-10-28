#!/usr/bin/env python3
"""LIM step 1a (read-only): list every haqq BUY tx (filled AND failed) from his raw recordings, multi-day, and draw a
stratified sample for a public-RPC fetch of the instruction args (the recordings carry no ix data).
Sources: /home/moiz/sniper-data/haqq/htx_R1..R4.jsonl.gz (10-22 03:08 -> 10-25 06:45 PKT) and
/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl (10-25 19:20 -> 10-28 00:41 PKT).
Out: data/lim/hbuys.pkl (all buy txs: s, i, bt, sig, err, mint, ixn, fee, tips), data/lim/rpc_todo.json (sample)."""
import json, gzip, glob, pickle, random, collections, time
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
DAY0 = 1793038500 - 5 * 86400
rows = {}
def add(d):
    if not d.get("signers") or d["signers"][0] != HAQQ: return
    ix = d.get("ixn") or []
    if not any("Buy" in x for x in ix): return
    rows[d["sig"]] = dict(s=d["s"], i=d["i"], bt=d["bt"], sig=d["sig"], err=d["err"], mint=(d.get("mints") or [None])[0], ixn=ix,
                          fee=d.get("fee"), tips=sum(v for a, v in (d.get("tips") or [])), cu=d.get("cu"), cul=d.get("cul"), cup=d.get("cup"))
for f in sorted(glob.glob("/home/moiz/sniper-data/haqq/htx_R*.jsonl.gz")):
    for l in gzip.open(f, "rt"): add(json.loads(l))
for l in open("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl"): add(json.loads(l))
R = sorted(rows.values(), key=lambda r: (r["s"], r["i"]))
pickle.dump(R, open(f"{OUT}/hbuys.pkl", "wb"))
c = collections.Counter((int((r["bt"] - DAY0) // 86400), r["err"] is None) for r in R)
print("haqq buy txs", len(R), sorted(c.items()))
random.seed(7); todo = []
by = collections.defaultdict(list)
for r in R: by[(int((r["bt"] - DAY0) // 86400), r["err"] is None)].append(r)
for k, v in sorted(by.items()):
    n = 110 if k[1] else 110
    todo += [dict(sig=r["sig"], s=r["s"], i=r["i"], ok=k[1], day=k[0]) for r in random.sample(v, min(n, len(v)))]
json.dump(todo, open(f"{OUT}/rpc_todo.json", "w"))
print("sample", len(todo))
