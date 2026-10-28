#!/usr/bin/env python3
"""LIM step 8 (read-only): looser limits on OUR live pre-send tries at their MEASURED landed positions.
Tries: dv8/live_presend.pkl (live, not dry; landed and on tape = 137.7k tries, 1,144 fills). Each try carries min_out
(= tokens at the reference trade 'pos' scaled for the --presend-drop threshold) and spend.
Windows: tries of one (run, mint) split where the send slot jumps > 20 slots.
Per window and policy g (min_out / (1+g)): walk the landed tries in chain order; the first whose tokens at its landed
state >= min_out/(1+g) fills (the engine's ATA-create guard blocks later fills of the window). g=0 reproduces live.
Variant 'after-cross': a relaxed fill is allowed only if some outside trade after the try's send slot had put the price below the
try's real limit (a dump happened and bounced before we landed) - the direct analogue of the regular guard question.
Exit: timer 2 slots after the fill slot (live pre-send hold), exact curve replay; fol 1.0 / 0.9 / 0.8.
Costs: fill = measured mean buy cost of live pre-send fills (fee+tips) + 1.77 mSOL sell; failed try 5,120 lamports (paid anyway).
Out: data/lim/l8.txt, data/lim/presend_cf.pkl"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L, dv8sim as S
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
GS = [0.0, 0.05, 0.10, 0.15, 0.20, 9.0]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    t0 = time.time()
    PR = [p for p in pickle.load(open(f"{L.D}/live_presend.pkl", "rb")) if not p.get("dry") and p.get("tape")]
    ok_sigs = set()
    cost = {}
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l); cost[(d["s"], d["i"])] = d["fee"] + sum(v for a, v in (d.get("tips") or []))
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[p["mint"]] for p in PR if p["mint"] in idm}), np.uint32)
    TT = np.asarray(T[np.isin(T["mint"], mids)])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    ourid = np.array([idm[w] for w in L.WAL.values() if w in idm], np.uint32)
    print(f"tries {len(PR):,}; tape rows {len(TT):,} ({time.time() - t0:.0f}s)", flush=True)
    by = collections.defaultdict(list)
    for p in PR: by[(p["run"], p["mint"])].append(p)
    W = []
    for (run, mint), v in by.items():
        if mint not in span: continue
        a, b = span[mint]; R = TT[a:b]
        R = R[~(np.isin(R["user"], ourid) | np.isin(R["signer"], ourid))]
        if not len(R): continue
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64); key = sl * 100000 + ix
        vs = R["vsol"] / 1e9; vt = R["vtok"].astype(np.float64); sol = R["sol"] / 1e9; tk = R["tok"].astype(np.float64); bu = R["buy"].astype(bool)
        v.sort(key=lambda p: (p["send_slot"] or 0))
        wins = []; cur = []
        for p in v:
            if cur and (p["send_slot"] or 0) - (cur[-1]["send_slot"] or 0) > 20: wins.append(cur); cur = []
            cur.append(p)
        if cur: wins.append(cur)
        for w in wins:
            tr = []
            for p in w:
                s_, i_, okk = p["tape"]
                r = int(np.searchsorted(key, s_ * 100000 + i_))
                if r < 1: continue
                tokp = S.entry_tokens(vs[r - 1], vt[r - 1], p["spend"] / 1e9)
                # crossing: any outside trade after send slot and before landing whose post-state met the real limit
                lo = int(np.searchsorted(sl, p["send_slot"] or s_))
                cross = False
                if r - 1 >= lo:
                    vv = vs[lo:r]; tt = vt[lo:r]
                    sn = p["spend"] / 1e9 / (1 + S.FEE)
                    cross = bool(((tt - vv * tt / (vv + sn)) >= p["min_out"]).any())
                if p["res"] not in ("6042", "ok"): continue          # deadline / ata_exists / 6005 fail regardless of the price limit
                tr.append(dict(key=s_ * 100000 + i_, r=r, slot=s_, need=p["min_out"] / tokp, ok=okk, cross=cross, spend=p["spend"] / 1e9, res=p["res"], t=p["t"]))
            if not tr: continue
            tr.sort(key=lambda x: x["key"])
            res = {}
            for g in GS:
                for mode in ("static", "after"):
                    f = next((x for x in tr if x["need"] <= 1 + g + 1e-9 and (mode == "static" or x["ok"] or x["cross"] or g == 0)), None)
                    if f is None: res[(g, mode)] = None; continue
                    q = max(int(np.searchsorted(sl, f["slot"] + 2, side="right")) - 1, f["r"] - 1)
                    res[(g, mode)] = (f["ok"], {fo: S.pnl_exact(vs, vt, sol, tk, bu, f["r"], q, f["spend"], fol=fo) for fo in (1.0, 0.9, 0.8)}, f["need"])
            W.append(dict(run=run, srv=run[:3], mint=mint, t=tr[0]["t"], day=L.day_of(tr[0]["t"]), ntries=len(tr), live_fill=any(x["ok"] for x in tr), res=res,
                          tr=[dict(need=x["need"], ok=x["ok"]) for x in tr]))
    pickle.dump(W, open(f"{OUT}/presend_cf.pkl", "wb"))
    agree = collections.Counter((x["need"] <= 1 + 1e-9, x["ok"]) for w in W for x in w.get("tr", []))
    okc = [cost[p["tape"][:2]] for p in PR if p["tape"][2] and p["tape"][:2] in cost]
    CF = (np.mean(okc) / 1e9 if okc else 0.6e-3) + 1.77e-3
    P(f"# Pre-send: looser limits at the MEASURED landed positions of our live tries (windows {len(W)}, tries {sum(w['ntries'] for w in W):,})")
    P(f"fill cost used {1000*CF:.2f} mSOL (buy fee+tips mean of live pre-send fills {'measured' if okc else 'assumed 0.6'} + sell 1.77)")
    P(f"check: g=0 picks the live fill in {sum(1 for w in W if w['res'][(0.0,'static')] is not None and w['res'][(0.0,'static')][0])} windows; live fill windows {sum(w['live_fill'] for w in W)};"
      f" g=0 fills on a non-filled try {sum(1 for w in W if w['res'][(0.0,'static')] is not None and not w['res'][(0.0,'static')][0])}")
    P(f"check per try (6042 + ok tries): tape says fill & live fill {agree[(True,True)]}, tape fill & live 6042 {agree[(True,False)]}, tape fail & live fill {agree[(False,True)]}, both fail {agree[(False,False)]}")
    for mode in ("after", "static"):
        P(f"\n## mode = {mode}: SOL net of fill costs (failed-try fees unchanged), exit 2 slots; fol 1.0 / 0.9 / 0.8")
        P("| limit | fills | fol 1.0 | delta vs live | per extra fill mSOL | fol 0.9 | fol 0.8 | extra fills' need p50 |"); P("|---|---|---|---|---|---|---|---|")
        base = sum((w["res"][(0.0, mode)][1][1.0] - CF) for w in W if w["res"][(0.0, mode)] is not None)
        nb = sum(1 for w in W if w["res"][(0.0, mode)] is not None)
        for g in GS:
            v = [w["res"][(g, mode)] for w in W if w["res"][(g, mode)] is not None]
            tot = {fo: sum(x[1][fo] - CF for x in v) for fo in (1.0, 0.9, 0.8)}
            ex = [x[2] for x in v if not x[0]]
            P(f"| +{int(g*100) if g < 5 else 'none'}% | {len(v)} | {tot[1.0]:+.3f} | {tot[1.0]-base:+.3f} | {1000*(tot[1.0]-base)/max(len(v)-nb,1):+.2f} | {tot[0.9]:+.3f} | {tot[0.8]:+.3f} | {np.median(ex) if ex else float('nan'):.3f} |")
        P("\nper day (fol 1.0), SOL: live-limit / +5% / +10% / +20% / none")
        for d in sorted({w["day"] for w in W}):
            for s in ("FRA", "AMS"):
                vv = [w for w in W if w["day"] == d and w["srv"] == s]
                if not vv: continue
                cells = [sum(w["res"][(g, mode)][1][1.0] - CF for w in vv if w["res"][(g, mode)] is not None) for g in (0.0, 0.05, 0.10, 0.20, 9.0)]
                P(f"- {L.day_name(d)} {s}: windows {len(vv)}: " + " / ".join(f"{c:+.2f}" for c in cells))
    open(f"{OUT}/l8.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
