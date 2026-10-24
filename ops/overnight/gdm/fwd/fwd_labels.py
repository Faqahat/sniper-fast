#!/usr/bin/env python3
# GDM forward test, step 3: labels (market label a, generic buyers c, glued wallets) + the gf_launches-style summary
# (deployer, post-bundle price, m10) for R2 launches created in [lo, hi), read from OUR phase-A dir. Same definitions
# as gdm/labels_pass.py and core/gf_stage1.py (no replay part). Wallet lists = the frozen file's (321 snipers + 9 pros).
# usage: RP_PHASEA_R2=phaseA_gdmfwd python3 -I fwd_labels.py <lo_bt> <hi_bt> <out.json>
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
assert os.environ.get("RP_PHASEA_R2") == "phaseA_gdmfwd"
LO, HI, OUTF = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
FZ = json.load(open("/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"))
DROP = set(FZ["wallet_lists"]["sniper"]) | set(FZ["wallet_lists"]["pro"])
SL = rp.SLOT_MS / 1000.0; HS = (3, 5, 8, 10, 15)
L = rp.load_launches()
todo = [m for m, c in L.items() if c["run"] == "R2" and c.get("bt") and LO <= c["bt"] < HI and "InitializeMayhemState" not in (c.get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[rp.bucket(m)].add(m)
def rebase_after(tr, g_end, drop, ins):
    out = list(tr[:g_end]); V = T = None
    for t in tr[g_end:]:
        if t["user"] in drop and t["user"] not in ins:
            if V is None: V, T = (out[-1]["vsol"], out[-1]["vtok"]) if out else (None, None)
            continue
        if V is None: out.append(t); continue
        x = dict(t)
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; x["tok"] = d
        else:
            so = V * t["tok"] // (T + t["tok"]) if T + t["tok"] > 0 else 0; V -= so; T += t["tok"]; x["sol"] = so
        x["vsol"], x["vtok"] = V, T; out.append(x)
    return out
def px_at(tr, k, p0):
    p = p0
    for t in tr:
        if t["s"] > k: break
        if t["vtok"]: p = t["vsol"] / t["vtok"]
    return p
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); lab = {}; ls = {}
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c); ins = st["insiders"]
        g = tr[st["g_end"] - 1] if st["g_end"] >= 1 else tr[0]; p_b0 = g["vsol"] / g["vtok"]
        ls[m] = dict(run="R2", bt=c["bt"], dep=c["user"], S=S, p_b=p_b0, m10=round(px_at(tr, S + int(10 / SL), p_b0) / p_b0, 4))
        if st["g_end"] < 1: continue
        p_b = p_b0
        r = dict(run="R2", bt=c["bt"], bw=sorted({t["user"] for t in st["glued"]}), ng=len(st["glued"]))
        pn = rebase_after(tr, st["g_end"], DROP, ins)
        r["a"] = [round(px_at(pn, S + int(h / SL), p_b) / p_b, 5) for h in HS]
        r["raw"] = [round(px_at(tr, S + int(h / SL), p_b) / p_b, 5) for h in HS]
        r["amax10"] = round(max([p_b] + [t["vsol"] / t["vtok"] for t in pn[st["g_end"]:] if t["s"] <= S + int(10 / SL) and t["vtok"]]) / p_b, 5)
        k2, k10 = S + int(2 / SL), S + int(10 / SL)
        gen = [t for t in tr[st["g_end"]:] if t["user"] not in ins and t["user"] not in DROP and t["s"] <= k10]
        g210 = [t for t in gen if t["buy"] and t["s"] > k2]; g010 = [t for t in gen if t["buy"]]
        r["c"] = [len({t["user"] for t in g210}), round(sum(t["sol"] for t in g210) / 1e9, 4), len({t["user"] for t in g010}), round(sum(t["sol"] for t in g010) / 1e9, 4),
                  round(sum(t["sol"] for t in gen if not t["buy"]) / 1e9, 4)]
        lab[m] = r
    return lab, ls
if __name__ == "__main__":
    LAB, LS = {}, {}
    with Pool(6) as p:
        for a, b in p.imap_unordered(work, sorted(byb)): LAB.update(a); LS.update(b)
    json.dump(dict(lo=LO, hi=HI, res=LAB, ls=LS), open(OUTF + ".tmp", "w")); os.replace(OUTF + ".tmp", OUTF)
    print(f"forward labels: {len(LAB)} launches with labels, {len(LS)} launch summaries, bt in [{LO:.0f}, {HI:.0f})", flush=True)
