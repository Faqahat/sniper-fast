# S4 = S3 list + price guard: robustness on the forward window (sizes, per hour, without top trades, bootstrap CI)
import sys, json, collections, statistics, random, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], name=c.get("name"), res={})
        for Lm in (35, 45, 60, 75):
            ib, na = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            isell = rp.place_ms(tr, c, st, O[m]["outs"], 500, ib)
            r["res"][Lm] = dict(ratio=(tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b, ahead=na, buy_after=tr[ib - 1]["sig"], sell_before=(tr[isell]["sig"] if isell < len(tr) else None),
                                pnl={B: rp.flip(tr, ib, isell, B) for B in (0.25, 0.5, 1.0, 2.0)}, pnl_fee1={B: rp.flip(tr, ib, isell, B, fee_buy_pct=0.01) for B in (0.5, 1.0)})
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); hours = (res[-1]["bt"] - res[0]["bt"]) / 3600
    json.dump(res, open("s4_fwd.json", "w")); SZ = {}
    random.seed(2)
    for G in (0.01, 0.03):
        print(f"\n== S4 guard {G:.0%}: {len(res)} S3 launches in {hours:.1f} h; sell lands 500 ms after the create; fail costs 0.002 SOL")
        for Lm in (35, 45, 60, 75):
            for B in (0.5, 1.0, 2.0):
                v = [(r["res"][Lm]["pnl"][B] if r["res"][Lm]["ratio"] <= 1 + G else -0.002) for r in res if Lm in r["res"]]
                fills = [r for r in res if Lm in r["res"] and r["res"][Lm]["ratio"] <= 1 + G]
                fv = sorted(r["res"][Lm]["pnl"][B] for r in fills)
                bs = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000))
                byh = collections.defaultdict(float)
                for r, x in zip([r for r in res if Lm in r["res"]], v): byh[datetime.datetime.fromtimestamp(r["bt"], datetime.timezone.utc).hour] += x
                SZ[f"{G}_{Lm}_{B}"] = dict(tot=sum(v), fills=len(fills), ci=(bs[50], bs[950]), wo5=sum(fv[:-5]) - 0.002 * (len(v) - len(fv)))
                print(f"   L{Lm} B{B}: total {sum(v):+6.2f} SOL (90% CI {bs[50]:+.2f}..{bs[950]:+.2f}), fills {len(fills)}, win {sum(1 for x in fv if x > 0) / max(1, len(fv)):.0%}, w/o top5 {sum(fv[:-5]) - 0.002 * (len(v) - len(fv)):+.2f}, hours positive {sum(1 for x in byh.values() if x > 0)}/{len(byh)}, per h {sum(v) / hours:+.2f}")
        v1 = [(r["res"][75]["pnl_fee1"][1.0] if r["res"][75]["ratio"] <= 1 + G else -0.002) for r in res if 75 in r["res"]]
        print(f"   L75 B1.0 with 1% buy overhead (nonce fan-out cost): total {sum(v1):+.2f} SOL, per h {sum(v1) / hours:+.2f}")
        SZ[f"{G}_75_1.0_fee1"] = dict(tot=sum(v1))
    json.dump(SZ, open("/home/moiz/sniper/ops/overnight/report/sizes.json", "w"))
