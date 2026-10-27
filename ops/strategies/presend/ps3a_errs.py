#!/usr/bin/env python3
# per candidate wallet (raw rows): ok / failed by side, top error codes, fees, tips, own programs, uid
import gzip, json, glob, collections, zlib, sys
import ps_common as C
st = collections.defaultdict(lambda: dict(n=0, side=collections.Counter(), err=collections.Counter(), fee_fail=[], tip_ok=[], own=collections.Counter(), cup=[], cul=[], ixn=collections.Counter(), days=collections.Counter(), mints=set()))
for f in sorted(glob.glob(f"{C.OUT}/raw/R*_*.jsonl.gz")):
    day = f.split("/")[-1][:2]
    for l in gzip.open(f, "rt"):
        r = json.loads(l); s = st[r["w"]]; s["n"] += 1; s["days"][day] += 1
        ix = " ".join(r["ixn"]); side = "B" if "Buy" in ix else ("S" if "Sell" in ix else "O")
        s["side"][(side, r["err"] is None)] += 1
        if r["err"]: s["err"][r["err"]] += 1; s["fee_fail"].append(r["fee"] or 0)
        else: s["tip_ok"].append(r["tips"])
        for p in r["own"]: s["own"][p[:8]] += 1
        s["cup"].append(r["cup"] or 0); s["cul"].append(r["cul"] or 0); s["ixn"][ix[:70]] += 1
        if r["mints"]: s["mints"].add(r["mints"][0])
fast = {r["uid"]: r for r in json.load(open(f"{C.OUT}/ps1_wallets.json"))}
med = lambda x: sorted(x)[len(x) // 2] if x else None
out = {}
for w, s in sorted(st.items(), key=lambda x: -fast.get(zlib.crc32(x[0].encode()), {}).get("fast", 0)):
    u = zlib.crc32(w.encode()); fr = fast.get(u, {})
    print(f"\n{w} uid {u} rows {s['n']} days {dict(s['days'])} mints {len(s['mints'])} | tape buys {fr.get('buys')} fast {fr.get('fast')} share {fr.get('share', 0):.2f} SOLfast {fr.get('sol_fast')}")
    print(f"   side(ok?) {dict(s['side'])}  err {s['err'].most_common(4)}")
    print(f"   fail fee med {med(s['fee_fail'])}  tip(ok) med {med(s['tip_ok'])}  cup med {med(s['cup'])}  cul med {med(s['cul'])}  own {s['own'].most_common(3)}")
    print(f"   ixn {s['ixn'].most_common(3)}")
    out[w] = dict(uid=u, n=s["n"], side={f"{k[0]}{'ok' if k[1] else 'X'}": v for k, v in s["side"].items()}, err=s["err"].most_common(6),
                  fee_fail_med=med(s["fee_fail"]), tip_ok_med=med(s["tip_ok"]), cup_med=med(s["cup"]), cul_med=med(s["cul"]), own=s["own"].most_common(3),
                  mints=len(s["mints"]), fast=fr.get("fast"), share=fr.get("share"), buys=fr.get("buys"))
json.dump(out, open(f"{C.OUT}/ps3a_errs.json", "w"), indent=0)
