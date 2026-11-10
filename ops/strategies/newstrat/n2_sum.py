import json, sys
import nlib as L
CL = ["BOTW", "BOTL", "MID", "RET", "DEV"]
for name in ["9pQQ", "8PgC", "E2x1", "OURS"]:
    print("==", name)
    for r in L.RUNS[:4]:
        try: d = json.load(open(f"{L.OUT}/source_{r}.json"))
        except FileNotFoundError: continue
        x = d.get(name)
        if not x: continue
        fw = x["flow_win"]; fl = x["flow_lose"]
        tot = {c: sum(fw[c]) for c in CL}
        early = {c: sum(fw[c][:2]) for c in CL}     # < 90 ms
        mid = {c: sum(fw[c][2:4]) for c in CL}      # 90 ms - 3 slots
        late = {c: sum(fw[c][4:]) for c in CL}      # 3 slots +
        zg = x["zerosum_good_mints"]; zb = x["zerosum_bad_mints"]
        print(L.DAY[r], f"trips {x['trips']} net {x['net']:+.1f} | WIN-trip net inflow by class (SOL) <90ms / 90ms-3sl / >3sl:",
              " ".join(f"{c} {early[c]:+.0f}/{mid[c]:+.0f}/{late[c]:+.0f}" for c in CL))
        print("      LOSE-trip net inflow total:", " ".join(f"{c} {sum(fl[c]):+.0f}" for c in CL))
        print(f"      zero-sum on {x['n_good']} mints it won (clean): payers", {k: v for k, v in zg.items()}, f"| on {x['n_bad']} mints it lost:", zb)
print({L.DAY[r]: json.load(open(f"{L.OUT}/source_{r}.json"))["wallet_classes"] for r in L.RUNS[:4]})
