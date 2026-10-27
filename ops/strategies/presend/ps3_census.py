#!/usr/bin/env python3
# Step 1c: rank wallets that look like pre-placers: many FAILED pump txs (cheap conditional failures) + a high share of their
# successful buys landing right after a >= 2% same-slot dump (ps1). Census = presend/raw/*.census.json (all signers, R1..R4).
import json, glob, zlib, collections
import ps_common as C
cen = collections.defaultdict(lambda: [0, 0, 0, 0])
for f in glob.glob(f"{C.OUT}/raw/*.census.json"):
    for w, v in json.load(open(f)).items():
        c = cen[w]
        for k in range(4): c[k] += v[k]
fast = {r["uid"]: r for r in json.load(open(f"{C.OUT}/ps1_wallets.json"))}
rows = []
for w, (ok, fl, f6, okb) in cen.items():
    u = zlib.crc32(w.encode()); r = fast.get(u)
    if fl < 200: continue
    rows.append(dict(w=w, ok=ok, failed=fl, f_slip=f6, ok_buys=okb, fail_share=fl / (ok + fl), fast=(r or {}).get("fast", 0), fshare=(r or {}).get("share", 0.0),
                     buys_tape=(r or {}).get("buys", 0), ntok=(r or {}).get("ntok", 0), days=(r or {}).get("days", {})))
rows.sort(key=lambda r: -r["fast"])
print("signers with >= 200 failed pump txs (R1..R4 raw), sorted by fast fills (<= 10 ms after a >= 2% same-slot dump, tape proxy)")
print(f"{'wallet':45s} {'ok':>7s} {'failed':>7s} {'slip/chk':>8s} {'fail%':>5s} {'fast':>5s} {'fast%':>5s} {'tapebuys':>8s} {'tok':>4s}")
for r in rows[:70]:
    print(f"{r['w']:45s} {r['ok']:7d} {r['failed']:7d} {r['f_slip']:8d} {100 * r['fail_share']:5.0f} {r['fast']:5d} {100 * r['fshare']:5.0f} {r['buys_tape']:8d} {r['ntok']:4d} {r['days']}")
json.dump(rows, open(f"{C.OUT}/ps3_census.json", "w"))
