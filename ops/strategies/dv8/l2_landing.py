#!/usr/bin/env python3
"""DV8 step 1b (read-only): OUR landing model from the live regular fires (MEASURED) + far-leader estimate from pre-send (INFERRED).
Per regular fire (dv8/live_fires.pkl): delay of our FIRST landed copy after the trigger dump in slots and chain-clock ms (cc),
outside same-mint trades between the dump and us (buyers ahead), outcome fill / fail (error code), leader client at our landing slot.
Guard check on the tape: tokens out for our spend at the curve state just before our landed position vs the engine's min_out
-> predicted fill; compared with the real outcome (validates the replay's guard + position mechanics).
Pre-send attempts: send-slot -> landing-slot delay by leader client and near / far (our region's near list) to scale the
regular-fire delay for far leaders (INFERRED).
Out: dv8/l2.txt, dv8/landing_model.json, dv8/fires_tape.pkl (fires + tape-derived fields)"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def q(v, ps=(10, 25, 50, 75, 90)):
    v = np.array([x for x in v if x is not None and x == x], float)
    return " / ".join(f"{np.percentile(v, p):.0f}" for p in ps) if len(v) else "-"


def main():
    F = pickle.load(open(f"{L.D}/live_fires.pkl", "rb"))
    ids, idm = L.ids_map()
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted({idm[f["mint"]] for f in F if f["mint"] in idm}), np.uint32)
    sel = np.isin(T["mint"], mids); TT = np.asarray(T[sel])
    TT = TT[np.lexsort((TT["j"], TT["idx"], TT["slot"], TT["mint"]))]
    um, st = np.unique(TT["mint"], return_index=True); en = np.append(st[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(b)) for m, a, b in zip(um, st, en)}
    ourid = {idm[w] for w in L.WAL.values() if w in idm}
    for f in F:
        if f["t"] is None and f["ds"]: f["t"] = L.slot_time(f["ds"])
        f.update(d_slots=None, d_ms=None, n_ahead=None, b_ahead=None, pred_fill=None, pr_ratio=None)
        if f["us"] is None or f["ds"] is None or f["mint"] not in span: continue
        a, b = span[f["mint"]]; R = TT[a:b]
        sl = R["slot"].astype(np.int64); ix = R["idx"].astype(np.int64)
        key = sl * 100000 + ix; dk = f["ds"] * 100000 + f["di"]; uk = f["us"][0] * 100000 + f["us"][1]
        f["d_slots"] = int(f["us"][0] - f["ds"])
        f["d_ms"] = float(L.cc(f["us"][0], f["us"][1]) - L.cc(f["ds"], f["di"]))
        btw = (key > dk) & (key < uk) & ~np.isin(R["user"], list(ourid))
        f["n_ahead"] = int(btw.sum()); f["b_ahead"] = float((R["sol"][btw & (R["buy"] == 1)] / 1e9).sum())
        f["s_ahead"] = float((R["sol"][btw & (R["buy"] == 0)] / 1e9).sum())
        # state just before our first landed copy; post-dump state
        pre = np.flatnonzero(key < uk); dmp = np.flatnonzero(key == dk)
        if len(pre) and len(dmp) and f["min_out"]:
            k = pre[-1]; v0 = R["vsol"][k] / 1e9; t0 = float(R["vtok"][k])
            vd = R["vsol"][dmp[-1]] / 1e9; td = float(R["vtok"][dmp[-1]])
            sn = f["spend"] / (1 + L.FEE); tok = t0 - v0 * t0 / (v0 + sn); tokd = td - vd * td / (vd + sn)
            f["pred_fill"] = bool(tok >= f["min_out"]); f["pr_ratio"] = float((v0 / t0) / (vd / td)); f["tok_ratio"] = float(tokd / max(tok, 1))
            f["guard_eff"] = float(tokd / f["min_out"])
    pickle.dump(F, open(f"{L.D}/fires_tape.pkl", "wb"))
    ok = [f for f in F if f["d_slots"] is not None]
    P(f"# Our landing, regular dip fires, all live runs (AMS r9-r33, FRA r1-r26 to 10-28 01:15 PKT) - MEASURED")
    P(f"fires {len(F)}; on tape with dump + our landed copy {len(ok)}; outcome counts {dict(collections.Counter(f['out'] for f in F))}")
    errs = collections.Counter(json.dumps(f["us_err"])[:60] for f in F if f["out"] == "fail")
    P("fail error codes (first landed copy): " + "; ".join(f"{k} x{v}" for k, v in errs.most_common(5)))
    P(f"landing RATE (a copy of the fire landed on chain, fill or fail): {100 * sum(f['us'] is not None for f in F) / len(F):.1f}%")
    P(f"fill rate: {100 * sum(f['out'] == 'fill' for f in F) / len(F):.1f}% ({sum(f['out'] == 'fill' for f in F)} / {len(F)})")
    P("\n## Delay of our first landed copy after the dump")
    P("| group | n | fill % | slots after dump: 0 / 1 / 2 / 3+ (%) | cc ms p10/25/50/75/90 | outside trades ahead p10/25/50/75/90 | buy SOL ahead p50 / mean |")
    P("|---|---|---|---|---|---|---|")
    def row(nm, v):
        if not v: return
        ds = np.array([f["d_slots"] for f in v]); fr = 100 * np.mean([f["out"] == "fill" for f in v])
        P(f"| {nm} | {len(v)} | {fr:.0f} | " + " / ".join(f"{100 * np.mean(x):.0f}" for x in (ds == 0, ds == 1, ds == 2, ds >= 3)) +
          f" | {q([f['d_ms'] for f in v])} | {q([f['n_ahead'] for f in v])} | {np.median([f['b_ahead'] for f in v]):.2f} / {np.mean([f['b_ahead'] for f in v]):.2f} |")
    row("all", ok)
    for s in ("FRA", "AMS"): row(s, [f for f in ok if f["srv"] == s])
    for c in ("fd", "harmonic", "bam", "jito", "agave", "other", "?"): row(f"leader {c}", [f for f in ok if f["land_client"] == c])
    row("near (per list)", [f for f in ok if f["land_near"]]); row("far (per list)", [f for f in ok if f["land_near"] is False])
    for lo, hi in ((0, 1793038500 - 2 * 86400), (1793038500 - 2 * 86400, 1793038500 - 86400), (1793038500 - 86400, 1793038500), (1793038500, 2e9)):
        row(f"fired {L.pkt(lo) if lo else 'start'}..{L.pkt(hi) if hi < 2e9 else 'now'}", [f for f in ok if lo <= f["t"] < hi])
    P("\n## Fill rate vs buyers ahead (outside same-mint trades between the dump and our first copy)")
    P("| trades ahead | n | fill % | price at landing / post-dump p50 |"); P("|---|---|---|---|")
    for lo, hi in ((0, 0), (1, 1), (2, 3), (4, 7), (8, 999)):
        v = [f for f in ok if lo <= f["n_ahead"] <= hi]
        if v: P(f"| {lo}-{hi} | {len(v)} | {100 * np.mean([f['out'] == 'fill' for f in v]):.0f} | {np.nanmedian([f['pr_ratio'] or np.nan for f in v]):.3f} |")
    g = [f for f in ok if f["pred_fill"] is not None]
    cm = collections.Counter((f["pred_fill"], f["out"] == "fill") for f in g)
    P(f"\n## Guard mechanics check on the tape (curve state before our copy vs the engine's min_out), n={len(g)}")
    P(f"pred fill & real fill {cm[(True, True)]}, pred fill & real fail {cm[(True, False)]}, pred fail & real fill {cm[(False, True)]}, pred fail & real fail {cm[(False, False)]}"
      f" -> agreement {100 * (cm[(True, True)] + cm[(False, False)]) / max(len(g), 1):.1f}%")
    P(f"effective guard (tokens at post-dump curve / min_out) p10/50/90: {q([f['guard_eff'] * 1000 for f in g], (10, 50, 90))} (x1000)")
    # costs
    P("\n## Tx costs per fire (fee + tips of every landed copy), SOL - MEASURED")
    for o in ("fill", "fail"):
        v = [f["buy_cost"] for f in F if f["out"] == o]
        P(f"- {o}: n {len(v)}, buy-side cost mean {1000 * np.mean(v):.2f} mSOL, p50 {1000 * np.median(v):.2f}; landed copies mean {np.mean([f['nlanded'] for f in F if f['out'] == o]):.2f}")
    v = [f["sell_cost"] for f in F if f["out"] == "fill" and f["sell_cost"] is not None]
    P(f"- sell-side (fills): mean {1000 * np.mean(v):.2f} mSOL")
    # per fire costs by period (recent runs have the nonce fan-out)
    rec = [f for f in F if f["t"] >= 1793038500 - 2 * 86400]
    nf = sum(f["out"] == "fill" for f in rec)
    P(f"- recent runs (from 10-24 23:15): per fill, all buy+sell costs incl failed fires: {1000 * (sum(f['buy_cost'] for f in rec) + sum(f['sell_cost'] or 0 for f in rec if f['out'] == 'fill')) / max(nf, 1):.2f} mSOL (fills {nf}, fails {sum(f['out'] == 'fail' for f in rec)})")
    # ---- pre-send attempts: send slot -> landing slot, near vs far
    PR = pickle.load(open(f"{L.D}/live_presend.pkl", "rb"))
    _, cl, near = L._sched()
    rows = []
    for a in PR:
        if a.get("slot") is None or a.get("send_slot") is None: continue
        ld = L.leader_of(a["slot"])
        if ld is None: continue
        rows.append(dict(srv=a["srv"], dl=int(a["slot"]) - int(a["send_slot"]), cls=L.client_class(cl.get(ld, "")), near=ld in near[a["srv"]],
                         ms=a.get("ms_send_to_rx"), res=a.get("res")))
    P(f"\n## Pre-send attempts (n={len(rows)}): send slot -> landing slot, by landing leader (INFERRED proxy for far leaders)")
    P("| group | n | land slot - send slot: 0 / 1 / 2 / 3+ (%) | ms send->first seen p25/50/75 |"); P("|---|---|---|---|")
    LM = {}
    for nr in (True, False):
        for c in ("all", "fd", "harmonic", "bam", "jito", "agave"):
            v = [r for r in rows if r["near"] == nr and (c == "all" or r["cls"] == c)]
            if len(v) < 30: continue
            dl = np.array([r["dl"] for r in v])
            P(f"| {'near' if nr else 'far'} {c} | {len(v)} | " + " / ".join(f"{100 * np.mean(x):.0f}" for x in (dl <= 0, dl == 1, dl == 2, dl >= 3)) + f" | {q([r['ms'] for r in v], (25, 50, 75))} |")
            LM[f"{'near' if nr else 'far'}_{c}"] = dict(n=len(v), ms50=float(np.nanmedian([r["ms"] if r["ms"] is not None else np.nan for r in v])))
    # landing model: empirical cc-ms sample of the first landed copy, per client class (near, MEASURED); far = near sample + shift (INFERRED)
    model = dict(near={}, far_shift_ms={})
    for c in ("all", "fd", "harmonic", "bam", "jito", "agave"):
        v = [f["d_ms"] for f in ok if (c == "all" or f["land_client"] == c)]
        if len(v) >= 20: model["near"][c] = sorted(v)
    for c in ("all", "fd", "harmonic", "bam", "jito", "agave"):
        a, b = LM.get(f"near_{c}"), LM.get(f"far_{c}")
        if a and b: model["far_shift_ms"][c] = max(0.0, b["ms50"] - a["ms50"])
    model["fill_frac_measured"] = float(np.mean([f["out"] == "fill" for f in F]))
    P("\nfar-leader shift (median send->seen, far - near, ms; INFERRED): " + ", ".join(f"{k} {v:+.0f}" for k, v in model["far_shift_ms"].items()))
    json.dump(model, open(f"{L.D}/landing_model.json", "w"))
    open(f"{L.D}/l2.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
