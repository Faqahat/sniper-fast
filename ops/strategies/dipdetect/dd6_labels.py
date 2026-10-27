#!/usr/bin/env python3
# Outcome-side labels for every dump of the dd1 universe (used ONLY as training targets / for analysis, never as features):
# who bought within 1000 ms after the dump (stop at the next >= 1 SOL sell, same rule as IMIT1's label): the 3 IMIT1 wallets,
# the top-10 earners, the train-hours cohort; plus all buys / SOL bought in that second.  -> dd6_<day>.npz
import sys, json, zlib
import numpy as np
import dd_lib as L
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd1_build as B1
def main(day):
    d = B1.load(day); z = np.load(f"{L.OUT}/dd1_{day}.npz"); K = z["k"]
    uid = d["uid"]; buy = d["buy"].astype(bool); sol = d["sol"]; arr = d["arr"]; tok = d["tok"]; off = d["off"]; cnt = d["cnt"]
    n = len(K); lab3 = np.zeros(n, np.int8); labT = np.zeros(n, np.int8); labC = np.zeros(n, np.int16); nb = np.zeros(n, np.int16); bs = np.zeros(n, np.float32)
    first_pro = np.full(n, np.nan, np.float32)
    for i, k in enumerate(K.tolist()):
        t = tok[k]; end = int(off[t] + cnt[t]); a0 = arr[k]; seen = set()
        j = k + 1
        while j < end and j < k + 600:
            if arr[j] > a0 + 1000 or ((not buy[j]) and sol[j] >= 1e9): break
            if buy[j]:
                u = int(uid[j]); nb[i] += 1; bs[i] += sol[j] / 1e9
                if u in B1.UPRO and np.isnan(first_pro[i]): first_pro[i] = arr[j] - a0
                if u not in seen:
                    seen.add(u)
                    if u in B1.U3: lab3[i] = 1
                    if u in B1.UT: labT[i] = 1
                    if u in B1.UC: labC[i] += 1
            j += 1
    np.savez(f"{L.OUT}/dd6_{day}.npz", k=K, lab3=lab3, labT=labT, labC=labC, nb1s=nb, bsol1s=bs, first_pro=first_pro)
    print(day, n, "lab3", lab3.mean().round(4), "labT", labT.mean().round(4), "labC>=1", (labC >= 1).mean().round(4), "labC>=2", (labC >= 2).mean().round(4), flush=True)
if __name__ == "__main__":
    for day in sys.argv[1:] or ["R1", "R2", "R3", "R4"]: main(day)
