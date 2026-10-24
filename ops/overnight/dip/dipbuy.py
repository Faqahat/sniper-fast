#!/usr/bin/env python3
# READ-ONLY event study "buy the dip after a large sell, sell the rebound" (pattern of census wallet HkQ7hMjy), on every
# standard SOL launch in R1 (phaseA) + R2 (phaseA_dry).
# Event: a sell >= 1 SOL (any wallet) at token age 1..900 s, curve not near completion. One position per launch at a time.
# Entry (0.5 SOL): E0 = right after the sell (best case) | E1 = after the rest of the sell's slot (start of the next slot)
#                  | E2 = after the next slot too (~212-424 ms late)
# Exit: sell at the state before the first trade in slot >= entry slot + H (H = 3, 5, 8, 12, 20, 40, 60 slots)
# Costs: pump fees from the events both ways, + 0.003 SOL per tx (buy and sell), fill penalty 0.5%.
# Output: per-event rows -> dip/events.jsonl.gz ; summary printed.
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
import rp
from multiprocessing import Pool
B = 0.5; HS = (3, 5, 8, 12, 20, 40, 60)
TXC = float(os.environ.get("TXC", "0.003")); PEN = float(os.environ.get("PEN", "0.005")); MIN_SELL = 1.0e9; MAX_AGE = float(os.environ.get("DIP_MAX_AGE", "900"))
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
def roundtrip(tr, k_in, V, T, fr, H):
    """buy B at state (V,T) (before tr[k_in]); sell at the state before the first trade at slot >= s_in + H"""
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V2 = V + X; T2 = T - q; q = int(q * (1 - PEN))
    s_in = tr[k_in - 1]["s"] if k_in > 0 else tr[0]["s"]
    Vc, Tc = V2, T2; frs = fr
    for t in tr[k_in:]:
        if t["s"] >= s_in + H: break
        if t["buy"]: d = Tc * t["sol"] // (Vc + t["sol"]); Vc += t["sol"]; Tc -= d
        else: so = Vc * t["tok"] // (Tc + t["tok"]); Vc -= so; Tc += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if Vc >= 110e9: break
    so = Vc * q // (Tc + q)
    return so * (1 - frs) / 1e9 - TXC - (B + TXC)
TPS = [(tp, sl, hm) for tp in (1.03, 1.05, 1.08, 1.12, 1.2) for sl in (0.0, 0.85) for hm in (30, 60)]
def roundtrip_tp(tr, k_in, V, T, fr, tp, sl, hmax):
    """buy B at (V,T) before tr[k_in]; after each later trade, if our net exit value / cost >= tp (or <= sl), sell at the state
    before the first trade of the NEXT slot (we react after seeing it); else sell at slot s_in + hmax"""
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); Vc = V + X; Tc = T - q; q = int(q * (1 - PEN))
    s_in = tr[k_in - 1]["s"] if k_in > 0 else tr[0]["s"]; cost = B + TXC; frs = fr; trig_s = None
    for t in tr[k_in:]:
        if trig_s is not None and t["s"] > trig_s: break
        if t["s"] >= s_in + hmax: break
        if t["buy"]: d = Tc * t["sol"] // (Vc + t["sol"]); Vc += t["sol"]; Tc -= d
        else: so = Vc * t["tok"] // (Tc + t["tok"]); Vc -= so; Tc += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if Vc >= 110e9: break
        if trig_s is None:
            val = (Vc * q // (Tc + q)) * (1 - frs) / 1e9 - TXC
            if val / cost >= tp or (sl and val / cost <= sl): trig_s = t["s"]
    so = Vc * q // (Tc + q)
    return so * (1 - frs) / 1e9 - TXC - cost
def work(key):
    run, b = key; out = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        S = c["slot"]; st = rp.structure(tr, c); busy_until = -1
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < MIN_SELL or t.get("syn") or k < st["g_end"]: continue
            age = (t["s"] - S) * rp.SLOT_MS / 1000
            if age < 1 or age > MAX_AGE or t["vsol"] >= 100e9 or t["s"] <= busy_until: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            # entry points
            k0 = k + 1
            k1 = next((j for j in range(k + 1, len(tr)) if tr[j]["s"] > t["s"]), len(tr))
            k2 = next((j for j in range(k1, len(tr)) if tr[j]["s"] > (tr[k1]["s"] if k1 < len(tr) else 10 ** 12)), len(tr))
            pre = tr[k - 1] if k > 0 else None
            p_before = (t["vsol"] + t["sol"]) / (t["vtok"] - t["tok"]); p_after = t["vsol"] / t["vtok"]
            nb = sum(1 for x in tr[:k] if x["buy"]); ns = sum(1 for x in tr[:k] if not x["buy"])
            ge = tr[st["g_end"] - 1]; pb = ge["vsol"] / ge["vtok"]
            w20 = [x for x in tr[max(0, k - 60):k] if t["s"] - x["s"] <= 20]
            peak = max(x["vsol"] / x["vtok"] for x in tr[:k + 1])
            row = dict(m=m, run=run, bt=c["bt"], age=round(age, 2), sell=round(t["sol"] / 1e9, 3), seller=t["user"][:8], ins=t["user"] in st["insiders"],
                       drop=round(p_after / p_before, 4), vsol=round(t["vsol"] / 1e9, 2), nb=nb, ns=ns, pb=round(p_after / pb, 4), dd=round(p_after / peak, 4),
                       b20=round(sum(x["sol"] for x in w20 if x["buy"]) / 1e9, 3), s20=round(sum(x["sol"] for x in w20 if not x["buy"]) / 1e9, 3),
                       u20=len({x["user"] for x in w20 if x["buy"]}), dev=round(sum(x["sol"] for x in tr[:st["g_end"]] if x["buy"]) / 1e9, 3),
                       glued=len(st["glued"]), first_big=not any((not x["buy"]) and x["sol"] >= MIN_SELL for x in tr[st["g_end"]:k]), pnl={})
            for tag, ke in (("E0", k0), ("E1", k1), ("E2", k2)):
                if ke >= len(tr) or ke < 1: continue
                V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
                row["pnl"][tag] = {str(H): round(roundtrip(tr, ke, V, T, fr, H), 5) for H in HS}
                for tp, sl, hm in TPS: row["pnl"][tag][f"tp{tp}_sl{sl}_h{hm}"] = round(roundtrip_tp(tr, ke, V, T, fr, tp, sl, hm), 5)
                row["px_" + tag] = round((V / T) / p_after, 4)
            out.append(row)
            busy_until = t["s"] + 20                     # one position at a time (~4 s)
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): res += o
    with gzip.open(os.environ.get("DIP_OUT", "/home/moiz/sniper/ops/overnight/dip/events.jsonl.gz"), "wt") as f:
        for r in res: f.write(json.dumps(r) + "\n")
    print("events", len(res))
    for tag in ("E0", "E1", "E2"):
        print(f"\nentry {tag}: per-event mean PnL (SOL, 0.5 SOL size) | win | total by hold slots")
        for H in HS:
            v = [r["pnl"][tag][str(H)] for r in res if tag in r["pnl"]]
            print(f"   H={H:2d}: n {len(v)} mean {statistics.mean(v):+.4f} win {sum(1 for x in v if x > 0) / len(v):.0%} total {sum(v):+.1f}")
