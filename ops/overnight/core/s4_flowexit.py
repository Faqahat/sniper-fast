# S4 exit improvement test: "sell when the buying stops" (momentum extension) vs the fixed end-of-next-slot exit
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
FW = json.load(open("/home/moiz/sniper/ops/overnight/report/s4_forward.json"))
L = rp.load_launches(); O = rp.load_obs()
byb = collections.defaultdict(set)
for r in FW: byb[rp.bucket(r["mint"])].add(r["mint"])
VAR = [(n, x, f) for f in (0, 1) for n in (0.0, 0.5, 1.0, 2.0) for x in (1, 2, 4, 8)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, bt=c["bt"], res={})
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r["res"][Lm] = None; continue
            r["res"][Lm] = {f"{n}_{x}_{f}": rp.sim_flow(tr, c, st, ib, 0.5, n, x, first_slot=f) for n, x, f in VAR}
        out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"]); mid = res[0]["bt"] + (res[-1]["bt"] - res[0]["bt"]) / 2
    rows = []
    for n, x, f in VAR:
        k = f"{n}_{x}_{f}"; cells = []
        for Lm in (45, 75):
            v = [(r["bt"], (r["res"][Lm][k] if r["res"].get(Lm) else -0.005)) for r in res if Lm in r["res"]]
            tot = sum(y for _, y in v); a = sum(y for t, y in v if t < mid)
            cells.append((tot, a, tot - a))
        rows.append((cells[1][0], k, cells))
    rows.sort(reverse=True)
    print("exit = sell at the end of slot (buy slot + first), extended one slot at a time while that slot's net outside buying >= N SOL, max X extra slots")
    print("variant N_X_first | L45 total (halves) | L75 total (halves)")
    for _, k, cells in rows[:14]: print(f"   {k:12} | " + " | ".join(f"{t:+6.2f} ({a:+.2f}/{b:+.2f})" for t, a, b in cells))
    base = [r for r in rows if r[1] == "0.0_1_1"]
