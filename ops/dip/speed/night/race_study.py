#!/usr/bin/env python3
# Chain-wide race study, step 2: every >= 1 SOL pump sell (dump) -> the buys of that token by OTHER wallets that land after it in
# the dump's slot or the next one (failed buys included: they landed). Per leader client: same-block rate and tx offset after
# the dump, by who (ours / dip pros / everyone) and by tx shape (tip service, number of tips, CU price). READ-ONLY.
import json, collections, statistics, sys
rows = json.load(open("race_rows.json"))
L = json.load(open("leaders_by_slot.json")); INFO = json.load(open("leader_info.json")); CL = INFO["client"]
OURS = ("2g7rYv7y", "EgxfYgEb")
PROS = ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX", "CZ77onJz", "6VzXcLk9", "G9G3dCBG", "5w8xtjc6", "6n2cCJrr", "8PgC4ngp", "9k78QZyw")
NONCE_T = 1792869120          # our durable-nonce fan-out live from 10-25 00:12 PKT
who = lambda s: "ours" if s.startswith(OURS) else ("pro" if s.startswith(PROS) else "other")
bymint = collections.defaultdict(list)
for k, r in enumerate(rows):
    for m in set(r[10]) | {t[0] for t in r[11]}: bymint[m].append(k)
R = []   # one row per reacting buy
for m, ks in bymint.items():
    for a, k in enumerate(ks):
        d = rows[k]
        if not d[4]: continue
        sells = [t for t in d[11] if t[0] == m and not t[3] and t[1] >= 1_000_000_000]
        if not sells: continue
        s0, i0, dumper = d[0], d[1], sells[0][4]
        cl = CL.get(L.get(str(s0), ""), "?"); cl_next = CL.get(L.get(str(s0 + 1), ""), "?")
        turn_start = L.get(str(s0 - 1)) != L.get(str(s0))
        rank = 0
        for k2 in ks[a + 1:]:
            b = rows[k2]
            if b[0] > s0 + 1: break
            if b[3] == dumper: continue
            is_buy = any(t[0] == m and t[3] for t in b[11]) or (b[8] and not b[4] and m in b[10])
            if not is_buy: continue
            rank += 1
            tips = b[7]; svc = sorted({t[0] for t in tips})
            R.append(dict(cl=cl, cl_next=cl_next, ts=turn_start, same=b[0] == s0, off=b[1] - i0 if b[0] == s0 else None, rank=rank, who=who(b[3]), w=b[3][:8],
                          ok=b[4], ntip=len(tips), svc="+".join(svc) if svc else "none", cup=b[5], ata=b[12], bt=b[13], dump_i=i0, s0=s0, bs=b[0], bi=b[1]))
json.dump(R, open("race_buys.json", "w"))
med = lambda v: round(statistics.median(v), 1) if v else None
def line(tag, v):
    if not v: return
    s = [x for x in v if x["same"]]
    print(f"   {tag:34s} n={len(v):6d} | same block {len(s)/len(v):5.1%} | offset (txs) median {med([x['off'] for x in s])} p25 {sorted([x['off'] for x in s])[len(s)//4] if s else None}")
print(f"reacting buys {len(R)} from {len({(x['dump_i'], x['bt']) for x in R})} dumps")
for cl in ("AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "FireBAM", "Firedancer", "Agave", "Rakurai"):
    v = [x for x in R if x["cl"] == cl]
    if not v: continue
    print(f"\n=== {cl}: reacting buys {len(v)}")
    for w in ("ours", "pro", "other"): line(f"who={w}", [x for x in v if x["who"] == w])
    line("ours, before nonce (multi-tip tx)", [x for x in v if x["who"] == "ours" and x["bt"] and x["bt"] < NONCE_T])
    line("ours, nonce variants (one tip each)", [x for x in v if x["who"] == "ours" and x["bt"] and x["bt"] >= NONCE_T])
    print("   -- pros + others, first 30 reacting buys of each dump, by tip shape:")
    vv = [x for x in v if x["who"] != "ours" and x["rank"] <= 30]
    for svc, n in collections.Counter(x["svc"] for x in vv).most_common(9): line(f"svc={svc}", [x for x in vv if x["svc"] == svc])
    for nt in (0, 1, 2, 3): line(f"tips={nt}{'+' if nt == 3 else ''}", [x for x in vv if (x["ntip"] >= 3 if nt == 3 else x["ntip"] == nt)])
