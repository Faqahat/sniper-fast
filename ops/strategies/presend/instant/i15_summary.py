#!/usr/bin/env python3
# INSTANT-BOTS study, step 15 (read-only): the final mechanism shares for buys landing right after dumps (same slot), by block gap:
#   SELLER-OWN  = the seller's own tool: a signer shared with the sell, OR the same PRIVATE custom program as the sell at gap <= 5
#                 (a program with < 100 distinct traders in the run, or the J7pourVw volume service; public routers/terminals excluded),
#                 OR the rotation template (buy with CU price 500, CU limit 200k, no tip, at gap 1-5; sampled: same Jito bundle as the sell);
#   PRE-SENT    = the buyer (or a sibling wallet with its exact program set) had failed / no-op attempts on the token just before;
#   OTHER       = neither. Split into "chance" vs "excess" with the mirror test: the same wallets' buys at the same distance BEFORE
#                 dumps (a buy that was going to land anyway is as likely just before a dump as just after it).
# usage: python3 -I i15_summary.py PREFIX OUT.json [X_DIR]   (PREFIX = /home/moiz/sniper-data/presend_instant/r4; X_DIR = pass-1 extracts)
import sys, json, gzip, glob, collections
pre, outp = sys.argv[1], sys.argv[2]
C = json.load(open(pre + "_classes.json"))
GENERIC = {"", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
def custom(pr): return "|".join(p for p in pr.split("|") if p and p not in GENERIC)
# programs used by >= 100 distinct traders in the run = public routers / terminals (a shared program there says nothing about the owner)
XD = sys.argv[3] if len(sys.argv) > 3 else pre.rsplit("/", 1)[0] + "/x_" + pre.rsplit("/", 1)[1]
users = collections.defaultdict(set)
for f in sorted(glob.glob(f"{XD}/T_*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        for p in (r[18] or "").split("|"):
            if p and p not in GENERIC and len(users[p]) < 100: users[p].add(r[5])
SERVICE = {"J7pourVwqP1VtRNBiFNqbdGxwkx7ta2LHAURURRRJqmd"}      # volume-bot service (many users); seller + buyers verified in one bundle
def private(cp): return bool(cp) and all(len(users[p]) < 100 or p in SERVICE for p in cp.split("|"))
def rot(r): return r["cup"] == 500 and r["cul"] == 200000 and not r["tsv"] and r["gap"] <= 5
def seller_own(r):
    if set(r["signers"]) & set(r["dsigners"]): return True
    cp = custom(r["my_progs"])
    if cp and cp == custom(r["d_progs"]) and private(cp) and r["gap"] <= 5: return True
    return rot(r)
def cls(r):
    if seller_own(r): return "SELLER-OWN"
    if r["cls"] in ("P", "P2") or (r["cls"] == "B" and r["own_before"] > 0): return "PRE-SENT"
    return "OTHER"
fam = {"SELLER-OWN": set(), "PRE-SENT": set()}
for r in C:
    k = cls(r)
    if k in fam: fam[k].add(r["u"])
# mirror test on the census: buys at +g after vs -g before, same slot, wallets outside the SELLER-OWN / PRE-SENT sets and not rotation-template
bef = collections.Counter(); aft = collections.Counter(); ndump = 0
for l in gzip.open(pre + "_dumps.jsonl.gz", "rt"):
    o = json.loads(l); d = o["d"]
    if d["drop"] < 0.04 or d["sol"] < 0.3e9: continue
    ndump += 1
    for x, sgn in [(x, -1) for x in o["before"]] + [(x, 1) for x in o["after"]]:
        if x["s"] != d["s"] or not x["buy"] or x["u"] == d["u"]: continue
        if x["u"] in fam["SELLER-OWN"] or x["u"] in fam["PRE-SENT"] or (x["cup"] == 500 and x["cul"] == 200000 and not x["tsv"]): continue
        g = (d["i"] - x["i"]) if sgn < 0 else (x["i"] - d["i"])
        if 1 <= g <= 40: (bef if sgn < 0 else aft)[g] += 1
B = [("gap 1", 1, 1), ("gap 2-5", 2, 5), ("gap 6-10", 6, 10), ("gap 11-20", 11, 20), ("gap 21-40", 21, 40), ("gap 1-10 (~<=1 ms on our feed)", 1, 10)]
res = dict(ndump=ndump, rows=[])
print(f"dumps (>= 4% drop, >= 0.3 SOL, same-slot buys after them): {ndump}")
print("bucket                          buys | SELLER-OWN | PRE-SENT | OTHER (mirror: same wallets' buys at the same distance BEFORE dumps -> chance; excess = after - before)")
for lab, lo, hi in B:
    rows = [r for r in C if lo <= r["gap"] <= hi]
    c = collections.Counter(cls(r) for r in rows); n = len(rows)
    b = sum(bef[g] for g in range(lo, hi + 1)); a = sum(aft[g] for g in range(lo, hi + 1))
    res["rows"].append(dict(bucket=lab, n=n, seller=c["SELLER-OWN"], pre=c["PRE-SENT"], other=c["OTHER"], mirror_before=b, mirror_after=a))
    print(f"{lab:31s} {n:5d} | {c['SELLER-OWN']:5d} {100 * c['SELLER-OWN'] / max(n, 1):3.0f}% | {c['PRE-SENT']:5d} {100 * c['PRE-SENT'] / max(n, 1):3.0f}% | "
          f"{c['OTHER']:5d} {100 * c['OTHER'] / max(n, 1):3.0f}% (mirror before {b}, after {a}: chance ~{min(b, a)}, excess {a - b:+d})")
json.dump(res, open(outp, "w"), indent=1)
json.dump({r["sig"]: cls(r) for r in C}, open(outp.replace(".json", "_cls.json"), "w"))
