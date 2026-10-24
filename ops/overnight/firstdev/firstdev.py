#!/usr/bin/env python3
# FIRST-TIME DEVS (owner 22:10 PKT): every recorded launch whose creator never launched a token before (no earlier creates in the
# collector's creator history AND not seen creating anything earlier in our own data). If we had bought 0.5 SOL of each:
#   entry A = first in line right after the creator's launch bundle (best a sniper can do)
#   entry B = one slot later (~our real landing, ~74 ms+)
# exits: hold 1 s / 5 s / 30 s / 2 min / 10 min, sell right after the dev's first sell, hold to the end (or graduation), and the
# top of the curve (impossible, upper bound). Pump fees both ways + 0.0008 SOL per tx. No follower slippage limits (optimistic).
import os, sys, json, glob, collections, statistics, time
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "1"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
B = 0.5e9; TXC = 0.0008; LAT_B = float(os.environ.get("LAT_B", "60"))
SSZ = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
L = rp.load_launches()
D = "/home/moiz/sniper-data/collect"; RUN = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426"}
prior = {}
for tag, run in RUN.items():
    for l in open(f"{D}/{run}/enrich.jsonl"):
        try: r = json.loads(l)
        except Exception: continue
        prior[r["mint"]] = (len(r.get("creator_recent_creates") or []), r.get("creator_prior_n"))
first_seen = {}
for m, c in sorted(L.items(), key=lambda x: x[1]["bt"]):
    cr = c.get("creator") or c.get("user"); first_seen.setdefault(cr, m)
FIRST = {m for m, c in L.items() if m in prior and prior[m][0] == 0 and first_seen.get(c.get("creator") or c.get("user")) == m}
HOLDS = {"1s": 5, "5s": 24, "30s": 141, "2min": 566, "10min": 2830}
byb = collections.defaultdict(set)
for m in FIRST: byb[(L[m]["run"], rp.bucket(m))].add(m)
def sim(tr, ke, fr, creator):
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    s0 = tr[ke - 1]["s"]; frs = fr; val = lambda: (V * q / (T + q)) * (1 - frs) / 1e9 - TXC - (B / 1e9 + TXC)
    out = {}; peak = val(); dev_done = False
    for t in tr[ke:]:
        for nm, h in HOLDS.items():
            if nm not in out and t["s"] >= s0 + h: out[nm] = val()
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        v = val(); peak = max(peak, v)
        if not dev_done and not t["buy"] and t["user"] == creator: out["dev_sell"] = v; dev_done = True
        if V >= 114e9: break
    end = val()
    for nm in HOLDS: out.setdefault(nm, end)
    out.setdefault("dev_sell", end); out["end"] = end; out["peak"] = peak
    return out
def work(key):
    res = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem") or "InitializeMayhemState" in (c.get("ixn") or []): continue
        st = rp.structure(tr, c); creator = c.get("creator") or c.get("user"); ge = max(st["g_end"], 1)
        if ge >= len(tr): continue
        fr = ((tr[0]["fbps"] or 95) + (tr[0]["cbps"] or 30)) / 1e4
        a = sim(tr, ge, fr, creator)
        arr = lambda t: t["s"] * 212.0 + t["i"] / max(SSZ.get(t["s"], 400), t["i"] + 1) * 212.0
        a0 = arr(tr[ge - 1]); kb = next((k for k in range(ge, len(tr)) if arr(tr[k]) >= a0 + LAT_B), None)
        b = sim(tr, kb, fr, creator) if kb else None
        dev_buy = sum(t["sol"] for t in tr[:ge] if t["user"] == creator and t["buy"]) / 1e9
        bund = [t for t in tr[:ge] if t["buy"] and t["user"] != creator]
        res.append(dict(m=m, run=c["run"], bt=c["bt"], A=a, B=b, dev_buy=dev_buy, grad=max(t["vsol"] for t in tr) >= 114e9,
                        bundle_n=len({t["user"] for t in bund}), bundle_sol=sum(t["sol"] for t in bund) / 1e9, vsol_entry=tr[ge - 1]["vsol"] / 1e9,
                        create_fee=(c.get("fee") or 0) / 1e9))
    return res
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): R += o
    json.dump(R, open(os.environ.get("FD_OUT", "/home/moiz/sniper/ops/overnight/firstdev/firstdev.json"), "w"))
    hrs = (max(L[m]["bt"] for m in L) - min(L[m]["bt"] for m in L)) / 3600
    print(f"launches recorded: {len(L)} | first-time devs: {len(FIRST)} ({len(FIRST) / len(L):.0%}) | usable tapes: {len(R)} | graduated: {sum(r['grad'] for r in R)}")
    for ent in ("A", "B"):
        v = [r[ent] for r in R if r[ent]]
        print(f"\nentry {ent} ({'first in line after the launch bundle' if ent == 'A' else 'one slot later, ~our real speed'}), 0.5 SOL each, {len(v)} trades:")
        for ex in ("1s", "5s", "30s", "2min", "10min", "dev_sell", "end", "peak"):
            p = [x[ex] for x in v]
            print(f"  {ex:9s} total {sum(p):+9.2f} SOL | per trade {statistics.mean(p):+.4f} | win {sum(1 for x in p if x > 0) / len(p):.0%} | best {max(p):+.2f} worst {min(p):+.2f}")
