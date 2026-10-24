#!/usr/bin/env python3
# AFTER A LIVE S4 RUN (read-only): for every round trip of OUR wallet in the collected data, rebuild the trade with the
# replay engine and compare with what really happened on chain:
#   A) exact: our buy and sells re-inserted at their real chain positions -> must match to the lamport (data/math check)
#   B) model: our buy placed by the arrival-time model at our real landing ms (from our engine's obs), sells at their real
#      positions -> tells whether the replay's place-in-line assumption matches our live landings
# usage: RP_PHASEA_R2=phaseA_dry python3 -I verify_live.py <wallet> [since_unix]
import sys, json, collections, statistics, time
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = sys.argv[1]; SINCE = float(sys.argv[2]) if len(sys.argv) > 2 else 0
L = rp.load_launches(); O = rp.load_obs()
cand = [m for m, c in L.items() if c["run"] == "R2" and (c.get("bt") or 0) >= SINCE]
byb = collections.defaultdict(set)
for m in cand: byb[rp.bucket(m)].add(m)
res = []
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue          # non-SOL quote: not traded by our engine
        mine = [(k, t) for k, t in enumerate(tr) if t["user"] == W]
        buys = [(k, t) for k, t in mine if t["buy"]]; sells = [(k, t) for k, t in mine if not t["buy"]]
        if len(buys) != 1 or not sells: continue
        kb, tb = buys[0]; c = L[m]; fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
        real_in = tb["sol"] * (1 + fr) / 1e9; real_out = sum(t["sol"] * (1 - fr) for _, t in sells) / 1e9
        path = [t for t in tr if t["user"] != W]
        def run(entry):
            V, T = (path[entry - 1]["vsol"], path[entry - 1]["vtok"]) if entry > 0 else (30e9, 1.073e15)
            X = tb["sol"]; q = int(T * X // (V + X)); V += X; T -= q
            spos = [(sum(1 for u in tr[:k] if u["user"] != W), t["tok"] / tb["tok"]) for k, t in sells]
            got = 0.0; left = q; si = 0
            for j in range(entry, len(path) + 1):
                while si < len(spos) and spos[si][0] == j:
                    kk = min(left, int(q * spos[si][1])) if si < len(spos) - 1 else left
                    so = V * kk // (T + kk); V -= so; T += kk; got += so * (1 - fr) / 1e9; left -= kk; si += 1
                if j == len(path): break
                t = path[j]
                if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
                else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
            return got
        kpath = sum(1 for u in tr[:kb] if u["user"] != W)
        gA = run(kpath)
        arr = [o[0] for o in O.get(m, {}).get("outs", []) if W.startswith(o[3])]
        if arr:
            st = rp.structure(path, c); fa = rp.read_failed("R2", b, {m}).get(m, [])
            idx, _ = rp.place_bo2(path, c, st, [o for o in O[m]["outs"] if not W.startswith(o[3])], arr[0], fa)
            gB = run(idx)
        else: gB = None
        res.append(dict(m=m, name=c.get("name"), real_in=real_in, real_out=real_out, A_out=gA, B_out=gB, land_ms=arr[0] if arr else None, idx_model=idx if arr else None, idx_real=kpath))
print(f"{W[:8]}: {len(res)} round trips in the collected data since {time.strftime('%m-%d %H:%M', time.gmtime(SINCE))}")
for r in res:
    print(f"   {r['m'][:8]} {str(r['name'])[:18]:18} landed {r['land_ms']} ms | real in {r['real_in']:.4f} out {r['real_out']:.4f} | exact replay out {r['A_out']:.4f} (diff {r['A_out'] - r['real_out']:+.5f}) | model place {r['idx_model']} vs real {r['idx_real']}" + (f", model out {r['B_out']:.4f}" if r['B_out'] is not None else ""))
if res:
    print(f"TOTAL real PnL (curve, before priority/tips) {sum(r['real_out'] - r['real_in'] for r in res):+.4f} | exact replay {sum(r['A_out'] - r['real_in'] for r in res):+.4f} | model {sum((r['B_out'] or r['A_out']) - r['real_in'] for r in res):+.4f}")
