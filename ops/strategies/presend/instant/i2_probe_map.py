#!/usr/bin/env python3
# INSTANT-BOTS study, step 2 (read-only): the live probe's "instant" events (a buy within 1 ms of the dump on the AMS feed) mapped to
# the chain rows of the raw recording (pass-1 extracts): full wallets / signatures, block positions, tips, CU price / limit,
# programs, the leader's client; plus every other trade and every FAILED tx on the same mint from 3 slots before the dump to
# the slot after it (who was trying to buy, and how).
# usage: python3 -I i2_probe_map.py PROBE.jsonl X_DIR OUT.json
import sys, json, glob, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/haqq")
import h_lib
probe, xdir, outp = sys.argv[1], sys.argv[2], sys.argv[3]
recs = [json.loads(l) for l in open(probe) if '"presend_attempt_land"' in l]
EV = {}
for o in recs:
    d = o.get("d")
    if not d: continue
    ib = o.get("instant_before_us") or []; ia = o.get("instant_after_us") or []
    if not ib and not ia: continue
    k = (o["mint"], d["slot"], d["idx"])
    e = EV.setdefault(k, dict(mint=o["mint"], d=d, inst_users=set(), n_our_landings=0, our=[]))
    e["inst_users"] |= set(ib + ia); e["n_our_landings"] += 1
    e["our"].append(dict(slot=o["slot"], idx=o["idx"], res=o["res"], ms_after_d_rx=o.get("ms_after_d_rx"), ms_after_d_a=o.get("ms_after_d_a"), sig=o["sig"]))
mints = {k[0] for k in EV}; slots = {k[1] for k in EV}
lo, hi = min(slots) - 4, max(slots) + 2
T = collections.defaultdict(list); F = collections.defaultdict(list)
for f in sorted(glob.glob(f"{xdir}/T_*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        if lo <= r[0] <= hi and r[6] in mints: T[r[6]].append(r)
for f in sorted(glob.glob(f"{xdir}/F_*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        if not any(m in l for m in mints): continue
        r = json.loads(l)
        if lo <= r[0] <= hi:
            for m in r[4]:
                if m in mints: F[m].append(r)
def trow(r):
    return dict(s=r[0], i=r[1], j=r[2], sig=r[3], signers=r[4], user=r[5], buy=bool(r[7]), sol=r[8] / 1e9, price=r[10] / r[11], fee=r[12], cup=r[13], cul=r[14], cu=r[15],
                tip=r[16], tipsvc=r[17], progs=r[18], ixn=r[20])
out = []
for k, e in sorted(EV.items(), key=lambda x: (x[0][1], x[0][2])):
    m, s, i = k
    tape = sorted(T[m], key=lambda r: (r[0], r[1], r[2]))
    d = next((r for r in tape if r[0] == s and r[1] == i), None)
    if d is None: out.append(dict(mint=m, slot=s, idx=i, missing=True)); continue
    ld, cl, rtt, cc = h_lib.leader_info(s)
    rows = []
    for r in tape:
        if s - 3 <= r[0] <= s + 1:
            x = trow(r); x["rel"] = "dump" if (r[0], r[1]) == (s, i) else ("before" if (r[0], r[1]) < (s, i) else "after")
            x["gap"] = (r[1] - i) if r[0] == s else None
            x["instant"] = r[5][:8] in e["inst_users"] and x["buy"] and x["rel"] == "after"
            rows.append(x)
    fails = []
    for r in sorted(F[m], key=lambda r: (r[0], r[1])):
        if s - 3 <= r[0] <= s + 1:
            fails.append(dict(s=r[0], i=r[1], sig=r[2], signers=r[3], err=r[5], fee=r[6], cup=r[7], cul=r[8], cu=r[9], progs=r[10], ixn=r[11],
                              rel="before" if (r[0], r[1]) < (s, i) else "after", gap=(r[1] - i) if r[0] == s else None))
    out.append(dict(mint=m, slot=s, idx=i, leader=ld, client=cl, dump=trow(d), drop_pct=e["d"]["drop_pct"], inst_users=sorted(e["inst_users"]),
                    n_our_landings=e["n_our_landings"], our=e["our"], feed=dict(dump_t=e["d"]["t"], dump_first=e["d"]["first_rx"]), tape=rows, fails=fails))
json.dump(out, open(outp, "w"), indent=1)
for x in out:
    if x.get("missing"): print("MISSING", x); continue
    d = x["dump"]
    print(f"\n== {x['mint'][:8]} slot {x['slot']} idx {x['idx']} leader {x['client']} | dump {d['user'][:8]} {d['sol']:.3f} SOL drop {x['drop_pct']:.1f}% "
          f"tip {d['tip']} {d['tipsvc']} cup {d['cup']} cul {d['cul']} progs {d['progs'][:60]} | our landings {x['n_our_landings']}")
    for r in x["tape"]:
        if r["rel"] == "before" and r["s"] < x["slot"] - 1: continue
        flag = "INSTANT" if r["instant"] else ""
        print(f"   {r['rel']:6s} s{r['s'] - x['slot']:+d} i{r['i']:4d} gap {r['gap']} {'BUY ' if r['buy'] else 'SELL'} {r['user'][:8]} {r['sol']:.3f} tip {r['tip']} {r['tipsvc']:12s} cup {r['cup']} cul {r['cul']} {r['progs'][:50]} {flag}")
    fc = collections.Counter((f["signers"][0][:8], f["rel"], f["err"]) for f in x["fails"])
    print("   fails:", dict(fc.most_common(12)))
