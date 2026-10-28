#!/usr/bin/env python3
"""Where our execution money goes per PKT day (MEASURED counts and fees from chain) and what each recipe step would save
(unit costs MEASURED where we have them; INFERRED parts named). Out: sniper-data/haqq_dissect/exec/t9_savings.txt"""
import pickle, collections
D = "/home/moiz/sniper-data/haqq_dissect/exec"
rows = pickle.load(open(f"{D}/txs.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
m = 1e-6   # lamports -> mSOL
days = ["10-25", "10-26", "10-27"]
P("## Our execution spend per PKT day, both wallets (MEASURED on chain), SOL")
P(f"{'day':6} {'psFill':>6} {'psTries':>8} {'regFill':>7} {'regFail':>7} {'sells':>5} | {'sells':>6} {'psTries':>7} {'psFillTx':>8} {'regFillTx':>9} {'regFail':>7} {'close':>6} {'TOTAL':>6}")
V = {}
for d in days:
    R = [r for r in rows if r["w"] in ("FRA", "AMS") and r["day"] == d]
    psf = [r for r in R if r["fee"] < 10000 and r["kind"] in ("buy", "other") and r["ok"]]
    psx = [r for r in R if r["fee"] < 10000 and r["kind"] in ("buy", "other") and not r["ok"]]
    rgf = [r for r in R if r["fee"] >= 400000 and r["kind"] in ("buy", "other") and r["ok"]]
    rgx = [r for r in R if r["fee"] >= 400000 and r["kind"] in ("buy", "other") and not r["ok"]]
    se = [r for r in R if r["kind"] == "sell"]; cl = [r for r in R if r["kind"] == "close"]
    c = dict(sells=sum(r["fee"] + r["tip"] for r in se), psx=sum(r["fee"] for r in psx), psf=sum(r["fee"] + r["tip"] for r in psf),
             rgf=sum(r["fee"] + r["tip"] for r in rgf), rgx=sum(r["fee"] for r in rgx), cl=sum(r["fee"] for r in cl))
    V[d] = dict(n_psf=len(psf), n_psx=len(psx), n_rgf=len(rgf), n_rgx=len(rgx), n_se=len(se), **c)
    tot = sum(c.values())
    P(f"{d:6} {len(psf):6} {len(psx):8} {len(rgf):7} {len(rgx):7} {len(se):5} | " + " ".join(f"{1e-9*c[k]:{w}.3f}" for k, w in (("sells", 6), ("psx", 7), ("psf", 8), ("rgf", 9), ("rgx", 7), ("cl", 6))) + f" {1e-9*tot:6.3f}")
P("")
# unit costs (lamports)
BASE = 5000
cur = dict(sell=1805000, rg_fire_fee=505000)
# recipe steps
# S1 (no speed risk): sells CU limit 120k -> 55k at the same 5M uL/CU (prio 600k -> 275k) and one tip per nonce variant (nozomi 1.0 / helius 0.2):
#     expected tip = share_noz*1.0 + (1-share_noz)*0.2 mSOL; buys: seeded token account + pass existing WSOL account (-31k CU, MEASURED 27,040 + 7,339
#     ATA CU vs ~3,200 for CreateAccountWithSeed + InitializeAccount3) -> CU limit 100k -> 66k at the same 5M uL/CU: prio 500k -> 330k per fire.
# S2: S1 + haqq sell recipe: prio 120k lamports, helius-swqos 0.2 / no-tip / 0slot variants on one nonce (haqq landed mix 72/21/7 -> E[tip]=0.151 mSOL)
# S3: S2 + regular-fire priority cut to 120k lamports (haqq level) -> SPEED RISK (CU price wins close pairs: BAM 79%, Harmonic 66%) -> A/B first
def recipe(v, step, share_noz=0.75):
    sells = v["n_se"]; fires = v["n_rgf"] + v["n_rgx"]
    s_old = v["sells"]; r_old = v["rgf"] + v["rgx"]
    if step == "S1":
        s_new = sells * (BASE + 275000 + 1e6 * (share_noz * 1.0 + (1 - share_noz) * 0.2))
        r_new = r_old - fires * (500000 - 330000)
    elif step == "S2":
        s_new = sells * (BASE + 120000 + 0.72 * 200000 + 0.07 * 100000)
        r_new = r_old - fires * (500000 - 330000)
    elif step == "S3":
        s_new = sells * (BASE + 120000 + 0.72 * 200000 + 0.07 * 100000)
        r_new = r_old - fires * (500000 - 120000)
    return s_old - s_new, r_old - r_new
P("## Savings per day by recipe step (SOL/day). sells = all sells (pre-send + regular fills); regular = regular fires (fills + failed)")
P(f"{'day':6} {'S1 sells':>9} {'S1 reg':>7} {'S1 tot':>7} | {'S2 sells':>9} {'S2 reg':>7} {'S2 tot':>7} | {'S3 tot':>7} | {'S1 sells @noz50..90%':>22}")
acc = collections.defaultdict(list)
for d in days:
    v = V[d]; s1 = recipe(v, "S1"); s2 = recipe(v, "S2"); s3 = recipe(v, "S3")
    lo = recipe(v, "S1", 0.9)[0]; hi = recipe(v, "S1", 0.5)[0]
    P(f"{d:6} {1e-9*s1[0]:9.3f} {1e-9*s1[1]:7.3f} {1e-9*sum(s1):7.3f} | {1e-9*s2[0]:9.3f} {1e-9*s2[1]:7.3f} {1e-9*sum(s2):7.3f} | {1e-9*sum(s3):7.3f} | {1e-9*lo:9.3f}..{1e-9*hi:.3f}")
    for k, x in (("S1", sum(s1)), ("S2", sum(s2)), ("S3", sum(s3)), ("S2s", s2[0]), ("S2r", s2[1])): acc[k].append(1e-9 * x)
P("mean/day: " + ", ".join(f"{k} {sum(v)/len(v):.3f} (days {min(v):.3f}..{max(v):.3f})" for k, v in acc.items()))
P("")
P("## Split by strategy (3-day mean, SOL/day): pre-send fills carry their sells; regular fills carry theirs + failed fires")
for k in ("psf", "rgf"):
    n = sum(V[d]["n_" + k] for d in days) / 3
    P(f"{k}: fills/day {n:.0f}; S2 sell saving {n*(1805000-(BASE+120000+0.72*200000+0.07*100000))*1e-9:.3f} SOL/day")
fires = sum(V[d]["n_rgf"] + V[d]["n_rgx"] for d in days) / 3
P(f"regular fires/day {fires:.0f}: seeded-account + tight CU (same CU price) saving {fires*170000*1e-9:.3f} SOL/day; S3 priority cut {fires*380000*1e-9:.3f} SOL/day (speed risk)")
pst = sum(V[d]["n_psx"] for d in days) / 3
P(f"pre-send failed tries/day {pst:.0f} at 5,120 lamports = {pst*5120*1e-9:.3f} SOL/day; base fee is 5,000 of it, so no tx-shape change can cut it below {pst*5000*1e-9:.3f} SOL/day while the tries still land")
open(f"{D}/t9_savings.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
