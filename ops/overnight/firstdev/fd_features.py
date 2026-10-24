#!/usr/bin/env python3
# create-time features for the first-time-dev launches (enrich: socials, dev wallet freshness, funder; launch: name/symbol)
import json
D = "/home/moiz/sniper-data/collect"; RUN = ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426")
import os; R = json.load(open(os.environ.get("FD_IN", "/home/moiz/sniper/ops/overnight/firstdev/firstdev.json"))); need = {r["m"] for r in R}
E = {}; LN = {}
for run in RUN:
    for l in open(f"{D}/{run}/enrich.jsonl"):
        try: e = json.loads(l)
        except Exception: continue
        if e["mint"] in need: E[e["mint"]] = e
    for l in open(f"{D}/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] in need: LN[c["mint"]] = c
for r in R:
    e = E.get(r["m"], {}); j = ((e.get("meta") or {}).get("json") or {}); c = LN.get(r["m"], {})
    txt = json.dumps(j).lower()
    r.update(tw=int("twitter" in j or "x.com" in txt or "twitter.com" in txt), tg=int("telegram" in j or "t.me/" in txt), web=int(bool(j.get("website"))),
             desc_len=len(j.get("description") or ""), prior_n=e.get("creator_prior_n") or 0, funder=int(bool(e.get("funder"))),
             jito=int(bool(e.get("jito_create"))), name_len=len(c.get("name") or ""))
json.dump(R, open(os.environ.get("FD_FOUT", "/home/moiz/sniper/ops/overnight/firstdev/firstdev_f.json"), "w")); print("features", len(R))
