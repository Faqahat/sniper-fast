#!/usr/bin/env python3
# coverage of decoded follower slippage limits (core/slip_args.jsonl) among follower buys (non-insider, <= 10 s after the
# create) of each pick list -> how much the "slip" / "proafter_slip" variants can drop followers at all
import sys, os, json, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_gf")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); SLIP = rp.load_slip(); PK = "/home/moiz/sniper/ops/overnight/gdm/picks"
lists = {a.split("=")[0]: set(json.load(open(f"{PK}/{a.split('=')[1]}"))) for a in sys.argv[1:]}
allm = set().union(*lists.values()); byb = collections.defaultdict(set)
for m in allm:
    if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
tot = collections.Counter(); kn = collections.Counter()
for (run, b), ms in byb.items():
    for m, tr in rp.read_bucket(run, b, ms).items():
        S0 = L[m]["slot"]; st = rp.structure(tr, L[m])
        for t in tr[st["g_end"]:]:
            if t["buy"] and t["user"] not in st["insiders"] and t["s"] <= S0 + 50:
                for k, v in lists.items():
                    if m in v: tot[k] += 1; kn[k] += t["sig"] in SLIP
for k in lists: print(f"{k:14s} picks {len(lists[k]):4d} | follower buys <= 10 s with known slippage limit: {kn[k]}/{tot[k]} ({kn[k] / max(1, tot[k]):.0%})")
