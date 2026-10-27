#!/usr/bin/env python3
# Tables for HOW_PROS_LAND.md from pro_rows_<sol>_<drop>.json (x4_pros.py): per wallet / leader client / dump quartile /
# window slot / leader location / landed route. ms = block clock (INFERRED), positions = MEASURED.
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
rows = json.load(open(f"{lib2.D}/pro_rows_1.0_0.04.json"))
WAL = json.load(open(f"{lib2.D}/wallets.json"))
FIRES = json.load(open(f"{lib2.D}/our_fires.json"))
fire_dumps = {f["dump_sig"] for f in FIRES}
HICU = {"5TFXfcHbVYxdZaw2qBdT9rjRitv6qTvGqtzJQwLnuANw", "D1QuMgpvKjaaEMbyFRpSwzLgec8CgqEeNiMsMQ3zSDb3", "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9",
        "EorGEbt18851FJJTMCC9zhBaDHweftzyvH9SjaFFUsG6", "EprLoV21A4BfU1KgP7AY6ELNmgLXRSpK1uCnhYWECZBQ", "HLU8QbLdvHDSWiQtyc8SGsTTdSdwZ3UKt8cEkG2wv4qk",
        "EJX629cpqnoa7jNRUBsFeevfPLxFWoa4KWWfsX7teLHr", "4oN18efpHpmaStKe759haW5EBqNYiga9qYF8vPkXNT2z", "6vB9VfGpjtSTYdhJ9ZMTLXC32UDCCaKpeQmSVnGNHgXh",
        "5mWe9kLZMvvBHwCjttw1fduPEBF8kRmPoyxf7EFZaJFn", "J3gZFpvsCsmA5zwqXgUpyqNLBoGGcJzmnfRwbHFR6KfU"}
PROS = ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw",
        "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk", "6n2cCJrrEAi4SZbBquj9mffUGAFXhDBmFeQEi3maSRcx", "9u5f8WMfyrHo5ondELytGiN9oNphVK1yVuyp2qomdZCs",
        "G9G3dCBGjM1chfZJHvb722zzzm9FQfZi4KbLVGncGeTy", "5w8xtjc649Z628jVvJkwQE5p9aMhV2cUSWr8RVV9BieU"]
OTHERS = ["GKd5EMzRhbprZXZfsbJczo4SrfF99XZWQA82bazaQr14", "EMKY7r6UekmmR1hREwCaPy835tCDGXGCw8fqibybgqzc", "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP",
          "3MHgGwdLnNayxYZ2eggq2AZFYydXjzBepyTMKzVsyNLq", "E6JasdE89MC5Jg1e6XthZ8Bb2zRMt4LU6Vr1hr8w8NYm", "EjywYBfNFjMC4RMZMLvYhZ6PvjnQNYaJPB6oTA6LUPEm"]
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "OURS-FRA", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "OURS-AMS"}
def name(w):
    if w in OURS: return OURS[w]
    if w == "HICU": return "hicu family (11)"
    return WAL[w]["name"][:8]
by = collections.defaultdict(list)
for r in rows:
    if r["w"] in OURS:
        if r["dump"] not in fire_dumps: continue        # ours: only our dip fires (no pre-send attempts)
    by[r["w"]].append(r)
    if r["w"] in HICU: by["HICU"].append(r)
med = lambda v: round(st.median(v)) if v else None
def pct(v, p):
    v = sorted(v); return round(v[min(len(v) - 1, int(p * len(v)))]) if v else None
ORDER = list(OURS) + PROS + ["HICU"] + OTHERS
def cell(v, need=8):
    if len(v) < need: return f"– ({len(v)})"
    ss = sum(1 for r in v if r["ds"] == 0) / len(v)
    return f"{med([r['ms'] for r in v])} ms · {ss:.0%} ({len(v)})"
out = []
P = out.append
P("### T1. Per wallet (dumps = sells ≥ 1 SOL with ≥ 4% drop, 10-23 19:26 → 10-25 19:02 PKT)")
P("| wallet | reactions | same slot | positions after dump (same slot) p25 / p50 | ms after dump p25 / p50 / p75 | landed routes | CU price (µL) | CU limit | tip (SOL) |")
P("|---|---|---|---|---|---|---|---|---|")
for w in ORDER:
    v = by.get(w) or []
    if len(v) < 10: continue
    ss = [r for r in v if r["ds"] == 0]
    svc = collections.Counter(r["svc"] for r in v)
    P(f"| {name(w)} | {len(v)} | {len(ss)/len(v):.0%} | {pct([r['dpos'] for r in ss],.25)} / {med([r['dpos'] for r in ss])} | "
      f"{pct([r['ms'] for r in v],.25)} / {med([r['ms'] for r in v])} / {pct([r['ms'] for r in v],.75)} | "
      + ", ".join(f"{k} {n/len(v):.0%}" for k, n in svc.most_common(4)) +
      f" | {med([r['cup'] for r in v]):,} | {med([r['cul'] for r in v]):,} | {(st.median([r['tip'] for r in v]))/1e9:.4f} |")
P("")
CL = ["Jito-own", "Jito-relayer", "BAM", "Harmonic", "Firedancer", "Rakurai"]
P("### T2. By the dump's leader client: median ms after the dump · same-slot share (n)")
P("| wallet | " + " | ".join(CL) + " |"); P("|---|" + "---|" * len(CL))
for w in ORDER:
    v = by.get(w) or []
    if len(v) < 10: continue
    P(f"| {name(w)} | " + " | ".join(cell([r for r in v if r['cl'] == c]) for c in CL) + " |")
P("")
P("### T3. By where the dump sat in its block (quartile of position): median ms · same-slot share (n)")
P("| wallet | Q1 (first 25%) | Q2 | Q3 | Q4 (last 25%) |"); P("|---|---|---|---|---|")
for w in ORDER:
    v = by.get(w) or []
    if len(v) < 10: continue
    P(f"| {name(w)} | " + " | ".join(cell([r for r in v if r['q'] == q]) for q in range(4)) + " |")
P("")
P("### T4. By the dump's slot inside the leader's 4-slot window: median ms · same-slot share (n)")
P("| wallet | slot 1 (short block, ≤144 ms) | slot 2 | slot 3 | slot 4 (last before hand-over) |"); P("|---|---|---|---|---|")
for w in ORDER:
    v = by.get(w) or []
    if len(v) < 10: continue
    P(f"| {name(w)} | " + " | ".join(cell([r for r in v if r['k'] == k]) for k in range(4)) + " |")
P("")
LOC = ["FRA", "AMS", "EU-other", "N-America", "Asia"]
P("### T5. By where the dump's leader is (RTT from our FRA / AMS servers; geo): median ms · same-slot share (n)")
P("| wallet | " + " | ".join(LOC) + " |"); P("|---|" + "---|" * len(LOC))
for w in ORDER:
    v = by.get(w) or []
    if len(v) < 10: continue
    P(f"| {name(w)} | " + " | ".join(cell([r for r in v if r['loc'] == l], 5) for l in LOC) + " |")
P("")
P("### T6. Landed route per leader client (which of the wallet's copies won): share of its same-slot landings · median ms")
for w in PROS + ["HICU"] + OTHERS[:2]:
    v = [r for r in (by.get(w) or []) if r["ds"] == 0]
    if len(v) < 30: continue
    P(f"- **{name(w)}**")
    for c in CL[:5]:
        vc = [r for r in v if r["cl"] == c]
        if len(vc) < 10: continue
        svc = collections.Counter(r["svc"] for r in vc)
        P(f"  - {c} (n={len(vc)}): " + ", ".join(f"{k} {n/len(vc):.0%} @{med([r['ms'] for r in vc if r['svc']==k])} ms" for k, n in svc.most_common(5)))
open(f"{lib2.D}/tables_main.md", "w").write("\n".join(out))
print("\n".join(out))
