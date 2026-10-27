#!/usr/bin/env python3
# INSTANT-BOTS study, step 5 (read-only): who buys right after dumps, on the whole run (not just the probe's 11 dumps).
# A "fast follow" = a successful curve buy in the SAME slot as a dump (sell dropping the price >= MIN_DROP), within GAP block
# positions after it, by a wallet other than the dumper. Per wallet: fast follows by gap bucket (1 / 2-5 / 6-40), how often it
# is the FIRST buy after the dump, its share of all its buys, how many distinct dumpers it follows (+ the top one's share), the
# same-custom-program rate (follower and dumper run the same non-standard program = one operator's tool), the size ratio
# (follow size / dump size), tips / landing services, CU price, and the leader client of the slots.
# usage: python3 -I i5_followers.py PREFIX [min_drop_pct] [min_dump_sol] [gap]   (PREFIX = i4's OUT_PREFIX)
import sys, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/haqq")
import h_lib
pre = sys.argv[1]; MIN_DROP = float(sys.argv[2]) / 100 if len(sys.argv) > 2 else 0.04
MIN_SOL = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3; GAP = int(sys.argv[4]) if len(sys.argv) > 4 else 40
W = json.load(open(pre + "_wallets.json"))
GENERIC = {"", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
def custom(pr): return "|".join(p for p in pr.split("|") if p and p not in GENERIC)
CL = {}
def client(s):
    if s not in CL: CL[s] = h_lib.leader_info(s)[1]
    return CL[s]
A = collections.defaultdict(lambda: collections.defaultdict(list))
EV = []; NDUMP = 0; FIRSTGAP = []; byclient = collections.defaultdict(collections.Counter)
for l in gzip.open(pre + "_dumps.jsonl.gz", "rt"):
    o = json.loads(l); d = o["d"]
    if d["drop"] < MIN_DROP or d["sol"] < MIN_SOL * 1e9: continue
    NDUMP += 1; cl = client(d["s"])
    same = [a for a in o["after"] if a["s"] == d["s"]]
    buys = [a for a in same if a["buy"] and a["u"] != d["u"]]
    fb = buys[0] if buys else None
    FIRSTGAP.append(fb["gap"] if fb else None)
    g = fb["gap"] if fb else None
    byclient[cl]["dumps"] += 1
    if g is not None:
        byclient[cl]["same_slot_buy"] += 1
        if g == 1: byclient[cl]["first_gap1"] += 1
        if g <= 5: byclient[cl]["first_le5"] += 1
        if g <= GAP: byclient[cl]["first_le40"] += 1
    dc = custom(d["pr"])
    rank = 0
    for a in buys:
        if a["gap"] > GAP: break
        rank += 1
        fc = custom(a["pr"])
        x = dict(mint=d["mint"], s=d["s"], di=d["i"], gap=a["gap"], rank=rank, client=cl, dumper=d["u"], dsol=d["sol"], drop=d["drop"], dtip=d["tip"], dtsv=d["tsv"],
                 dpr=dc, sol=a["sol"], tip=a["tip"], tsv=a["tsv"], cup=a["cup"], cul=a["cul"], pr=fc, same_prog=bool(dc) and dc == fc, sig=a["sig"], dsig=d["sig"],
                 shared_signer=bool(a["sg"]) and a["sg"] in (d["u"], d["sg"]))
        A[a["u"]]["ev"].append(x); EV.append(dict(x, u=a["u"]))
print(f"dumps (drop >= {MIN_DROP * 100:.0f}%, >= {MIN_SOL} SOL): {NDUMP}")
fg = [g for g in FIRSTGAP if g is not None]
print(f"first buy after the dump in the same slot: {len(fg)} of {NDUMP} ({100 * len(fg) / NDUMP:.0f}%); gap 1: {sum(1 for g in fg if g == 1)}, 2-5: {sum(1 for g in fg if 2 <= g <= 5)}, "
      f"6-40: {sum(1 for g in fg if 6 <= g <= 40)}, >40: {sum(1 for g in fg if g > 40)}")
print("by leader client: " + "; ".join(f"{c} {v['dumps']} dumps, first buy gap 1 {100 * v['first_gap1'] / max(v['dumps'], 1):.0f}% / <=5 {100 * v['first_le5'] / max(v['dumps'], 1):.0f}% / <=40 {100 * v['first_le40'] / max(v['dumps'], 1):.0f}%"
                                   for c, v in sorted(byclient.items(), key=lambda x: -x[1]['dumps'])))
rows = []
for u, a in A.items():
    ev = a["ev"]; n = len(ev)
    if n < 3: continue
    dd = collections.Counter(e["dumper"] for e in ev)
    rows.append(dict(u=u, n=n, g1=sum(1 for e in ev if e["gap"] == 1), g2_5=sum(1 for e in ev if 2 <= e["gap"] <= 5), g6_40=sum(1 for e in ev if 6 <= e["gap"]),
                     first=sum(1 for e in ev if e["rank"] == 1), buys=W["buys"].get(u, 0), sells=W["sells"].get(u, 0), share=n / max(W["buys"].get(u, 1), 1),
                     dumpers=len(dd), top_dumper=dd.most_common(1)[0][0], top_dumper_share=dd.most_common(1)[0][1] / n,
                     same_prog=sum(1 for e in ev if e["same_prog"]) / n, shared_signer=sum(1 for e in ev if e["shared_signer"]) / n,
                     size_ratio=statistics.median(e["sol"] / max(e["dsol"], 1) for e in ev), sol=statistics.median(e["sol"] for e in ev) / 1e9,
                     tsv=collections.Counter(e["tsv"] or "none" for e in ev).most_common(3), cup=statistics.median((e["cup"] or 0) for e in ev),
                     cul=statistics.median((e["cul"] or 0) for e in ev), pr=collections.Counter(e["pr"][:12] or "-" for e in ev).most_common(2),
                     clients=collections.Counter(e["client"] for e in ev).most_common(4)))
rows.sort(key=lambda r: -r["n"])
json.dump(dict(rows=rows, ev=EV, ndump=NDUMP, byclient={k: dict(v) for k, v in byclient.items()}), open(pre + f"_followers_d{int(MIN_DROP * 100)}_g{GAP}.json", "w"))
print(f"\nwallets with >= 3 fast follows (gap <= {GAP}): {len(rows)}")
print("wallet    follows  g1  g2-5 g6-40 first | buys  share | dumpers top% | same-prog shared-sig | size  sol   | tips / cup / cul | progs | clients")
for r in rows[:70]:
    print(f"{r['u'][:8]}  {r['n']:5d} {r['g1']:4d} {r['g2_5']:4d} {r['g6_40']:5d} {r['first']:5d} | {r['buys']:5d} {r['share']:5.2f} | {r['dumpers']:5d} {100 * r['top_dumper_share']:3.0f}% | "
          f"{100 * r['same_prog']:4.0f}% {100 * r['shared_signer']:4.0f}% | {r['size_ratio']:.2f} {r['sol']:.3f} | {r['tsv']} {r['cup']:.0f} {r['cul']:.0f} | {r['pr']} | {r['clients']}")
