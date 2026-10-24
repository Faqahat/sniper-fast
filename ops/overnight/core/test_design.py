# FRZ/PROD live-test design: S4 forward-window result for buy size B with an ABSOLUTE per-buy fee F (priority + tips) and
# a failed-buy cost FF (priority only; tips revert). Placement: block-order (verifier-matched); exit: end of next slot.
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
FW = json.load(open("/home/moiz/sniper/ops/overnight/report/s4_forward.json"))
L = rp.load_launches(); O = rp.load_obs(); EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
byb = collections.defaultdict(set)
for r in FW: byb[rp.bucket(r["mint"])].add(r["mint"])
FEES = [(0.002, 0.0005), (0.006, 0.001), (0.011, 0.002), (0.024, 0.011)]
res = collections.defaultdict(float); fills = collections.Counter()
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], 75, fa.get(m, []))
        if ib < 1: continue
        ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
        for B in (0.1, 0.25, 0.5, 1.0):
            for F, FF in FEES:
                if not ok: res[(B, F)] -= FF; continue
                o = rp.sim(tr, c, st, ib, B, EX, fee_buy_pct=F / B, fill_pen=0.015)
                if o: res[(B, F)] += o["eos1"]["pnl"]; fills[(B, F)] += 1
json.dump({f"{B}_{F}": v for (B, F), v in res.items()}, open("/home/moiz/sniper/ops/overnight/report/test_design.json", "w"))
print("S4 at 75 ms, forward window 7.4 h: total SOL by buy size (rows) and per-buy fee / failed-buy cost (columns)")
print("        " + "".join(f"{'fee ' + str(F) + '/fail ' + str(FF):>22}" for F, FF in FEES))
for B in (0.1, 0.25, 0.5, 1.0):
    print(f"B {B:<5} " + "".join(f"{res[(B, F)]:>+22.2f}" for F, FF in FEES))
