#!/usr/bin/env python3
"""FRONT addendum step 3 (read-only): FRA r27 (k8, after the dv8 tape end) on the same footing as g2 (a)/(b).
Decodes the pump.fun TradeEvents of FRA27's armed mints from the raw lines pulled by g0_r27raw.sh (slots > 462200814), block sizes from
the per-slot max tx index, then per dump (outside sell, drop >= 5 %, sell >= 0.5 SOL, curve > 30.52) in an armed window: front value
vf (0.40 SOL right after the dump, wave exit, as f1) and our first landed try after it.
Out: sniper-data/haqq_dissect/front/g3_r27_rows.pkl (same fields as g2_rows), g3_trades.npz"""
import json, glob, pickle, collections, sys, base64, struct, os
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import dv8lib as L, dv8sim as S
from decode import parse_trade, DISC
from xsim import Pos
from x12_wave import ev as wave_ev
from x7_ourexits import delays
OUT = "/home/moiz/sniper-data/haqq_dissect/front"; RD = f"{OUT}/r27"
OURS = set(L.WAL.values()); SIZE = 0.40; WAVE = ("RIDE", 150, 150, 700); HZ = 8


def main():
    RU = pickle.load(open(f"{OUT}/g1_runs.pkl", "rb")); x = RU["FRA27"]
    mints = {a["mint"] for a in x["arms"]}
    bs = {}
    for f in glob.glob(f"{RD}/*.si"):
        for l in open(f):
            try: s, i = l[5:].split(',"i":'); s = int(s); i = int(i)
            except Exception: continue
            if i + 1 > bs.get(s, 0): bs[s] = i + 1
    rows = []
    for f in sorted(glob.glob(f"{RD}/*.mint.jsonl")):
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            if d.get("err") is not None: continue
            sg = d["signers"][0]; j = 0
            for e in d.get("ev") or []:
                for ch in e.split(" "):
                    try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
                    except Exception: continue
                    k = b.find(DISC)
                    if k < 0: continue
                    t = parse_trade(b[k:])
                    if t is None or t[0] not in mints: continue
                    mint, sol, tok, buy, user, vsol, vtok, _, _ = t
                    rows.append((d["s"], d["i"], j, mint, user, sg, int(buy), sol, tok, vsol, vtok)); j += 1
    rows = sorted(set(rows), key=lambda r: (r[3], r[0], r[1], r[2]))
    print(f"r27 trades {len(rows):,} on {len({r[3] for r in rows})} mints; slots with size {len(bs):,}", flush=True)
    def cc(s, i): n = bs.get(s, 400); return s * L.SMS + i / max(n, i + 1) * L.SMS
    DR, DT, _ = delays()
    bym = collections.defaultdict(list)
    for r in rows: bym[r[3]].append(r)
    trw = collections.defaultdict(list)
    for t in x["tries"]:
        if t.get("slot") is not None and t.get("idx") is not None: trw[(t["w"], t["mint"])].append(t)
    out = []
    for a in x["arms"]:
        if a["arm_slot"] is None or a["mint"] not in bym: continue
        v = trw.get((a["w"], a["mint"]), [])
        end = a["end_slot"] if a["end_slot"] is not None else (max([t["send_slot"] for t in v]) if v else a["arm_slot"] + 10)
        A = bym[a["mint"]]
        ou = np.array([(r[4] in OURS or r[5] in OURS) for r in A])
        Ao = [r for r, o in zip(A, ou) if not o]
        if len(Ao) < 3: continue
        sl = np.array([r[0] for r in Ao], np.int64); ix = np.array([r[1] for r in Ao]); bu = np.array([r[6] for r in Ao], bool)
        so = np.array([r[7] for r in Ao]) / 1e9; tk = np.array([r[8] for r in Ao], float); vs = np.array([r[9] for r in Ao]) / 1e9; vt = np.array([r[10] for r in Ao], float)
        ccr = np.array([cc(r[0], r[1]) for r in Ao]); px = vs / np.maximum(vt, 1)
        for jd in range(1, len(Ao)):
            if bu[jd] or so[jd] < 0.5 or vs[jd] <= 30.52 or not (a["arm_slot"] <= sl[jd] <= end) or Ao[jd][4] == L.HAQQ: continue
            drop = 1 - px[jd] / px[jd - 1]
            if drop < 0.05: continue
            ds, di = int(sl[jd]), int(ix[jd])
            hi = int(np.searchsorted(sl, ds + HZ, side="right"))
            cc0 = float(ccr[jd]) + 0.01
            p = dict(dcc=(ccr[jd + 1:hi] - cc0), bu=bu[jd + 1:hi].copy(), so=so[jd + 1:hi].copy(), tk=tk[jd + 1:hi].copy(), V0=float(vs[jd]), T0=float(vt[jd]),
                     sin=SIZE / (1 + S.FEE), cost=SIZE, fee=S.FEE, off_in_slot=cc0 - (cc0 // L.SMS) * L.SMS)
            P_ = Pos(p, 1.0); vf = (wave_ev(P_, WAVE, DR, DT) - 1) * SIZE if P_.n else (P_.v_pre - 1) * SIZE
            fr = [(int(sl[q]), int(ix[q]), float(ccr[q] - ccr[jd])) for q in range(jd + 1, hi) if bu[q]][:6]
            aft = [t for t in v if (t["slot"], t["idx"]) > (ds, di) and t["slot"] <= ds + 2]
            rec = dict(run="FRA27", g="k8 cli40/cfg20", mint=a["mint"], ds=ds, di=di, drop=float(drop), vf=float(vf), day=L.day_of(1793136368), nbef=0,
                       f1ms=fr[0][2] if fr else None, real=x["real"].get((a["w"], a["mint"])))
            if aft:
                t = min(aft, key=lambda t: (t["slot"], t["idx"]))
                rec.update(ms=cc(t["slot"], t["idx"]) - ccr[jd], same=t["slot"] == ds, bp=t["idx"] / max(bs.get(t["slot"], 400), t["idx"] + 1),
                           ahead=sum(1 for f in fr if (f[0], f[1]) < (t["slot"], t["idx"])), ok=t.get("res") == "ok", anyok=any(z.get("res") == "ok" for z in aft),
                           client=t["client"])
            out.append(rec)
    pickle.dump(out, open(f"{OUT}/g3_r27_rows.pkl", "wb"))
    np.savez_compressed(f"{OUT}/g3_trades.npz", rows=np.array([(r[0], r[1], r[2], r[6], r[7], r[8], r[9], r[10]) for r in rows], np.int64),
                        mint=np.array([r[3] for r in rows]), signer=np.array([r[5] for r in rows]))
    print(f"FRA27 dumps in armed windows {len(out)}; paying {sum(r['vf'] >= 0.03 for r in out)}")


if __name__ == "__main__":
    main()
