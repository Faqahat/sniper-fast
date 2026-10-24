#!/usr/bin/env python3
# Claim 4 follow-up: bootstrap CIs within trigger-slot-position strata (HkQ7hMjy, and first buyer of any wallet), all triggers.
import json, random, statistics
exec(open("/home/moiz/sniper/ops/overnight/verify_dip/v2_hk_routed.py").read().split('if __name__ == "__main__":')[0])
EA = [json.loads(l) for l in open(f"{SH}/trig_sigs_all.jsonl")]
lab = lambda e: (1 if TX[e["sig"]] == "top" else 0) if e.get("sig") in TX and TX[e["sig"]] in ("top", "routed") else FL.get(f'{e["m"]}|{e["age"]}')
def strat(get, name):
    print(f"\n{name}")
    pooled = []
    for lo, hi in ((0, 0.25), (0.25, 0.5), (0.5, 1.01)):
        a = []; b = []
        for e in EA:
            l_ = lab(e); p = e.get("slotpos")
            if l_ is None or p is None or not (lo <= p < hi): continue
            d = get(e)
            if d is not None: (a if l_ == 1 else b).append(d)
        lo95, hi95, pneg = boot_med_diff(a, b, n=2000)
        print(f"   slot position {lo:.2f}-{hi:.2f}: direct n {len(a)} med {statistics.median(a):.1f} | routed n {len(b)} med {statistics.median(b):.1f} | diff {statistics.median(b) - statistics.median(a):+.1f} [{lo95:+.1f}, {hi95:+.1f}]")
        pooled.append((len(a) + len(b), statistics.median(b) - statistics.median(a)))
    print(f"   size-weighted stratified diff {sum(n * d for n, d in pooled) / sum(n for n, _ in pooled):+.1f} ms")
strat(lambda e: hk(e, True), "HkQ7hMjy first same-slot buy (ms, proxy)")
strat(lambda e: next((x[3] for x in e.get("fol", []) if x[1] == 1 and x[4] == 0), None), "first same-slot buy by ANY wallet (ms, proxy)")
