#!/usr/bin/env python3
"""HAQQ_STRAT step 5 (read-only): latency, haqq vs us, and why we skipped the dumps he bought.
Clock for BOTH sides: the tape's chain clock cc(s, i) = s*212 + i / n_s * 212 (n_s = recorded block size); event = the dump's tx.
Our side: every landed tx of ours (fill or failed, any copy) after the engine's trigger dump, from tab/ours.jsonl matched by sig
  (regular fires: all nonce copies; pre-send: attempts the engine logged as landed). Engine's own ms_after_d_a / rx_ms_after_dump
  are quoted next to it.
His side: his landed txs (fills AND failed buys) from the raw recording, first one on the mint after the same dump (<= 10 slots).
Head to head: events where both landed a buy tx after the same dump.
Skips: every haqq DIP / DIP_LATE first buy while one of our engines was live -> why we had no landed tx on that dump.
Out: haqq_strat/s5.txt, s5.json, h2h.pkl"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
from hs_lib import *
TAB = "/home/moiz/sniper-data/haqq_model/tab"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    S = np.load(f"{TAB}/slots.npy"); s0 = int(S["slot"].min())
    bsz = np.zeros(int(S["slot"].max()) - s0 + 1, np.int32); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1
    def cc(s, i):
        k = s - s0; n = bsz[k] if 0 <= k < len(bsz) else 0
        n = n if n > 0 else 400
        return s * 212.0 + i / max(float(n), i + 1.0) * 212.0
    ours = {}
    for l in open(f"{TAB}/ours.jsonl"):
        d = json.loads(l); ours[d["sig"]] = (d["s"], d["i"], d["err"] is not None, d["signers"][0], d["fee"], sum(v for a, v in d.get("tips") or []),
                                             [svc(a) for a, v in d.get("tips") or []])
    hq = collections.defaultdict(list)
    for l in open(f"{D}/haqq_raw.jsonl"):
        d = json.loads(l)
        if not d["mints"]: continue
        isb = any("Buy" in x for x in d["ixn"])
        if isb: hq[d["mints"][0]].append((d["s"], d["i"], d["err"] is not None, d["fee"], sum(v for a, v in d.get("tips") or []), [svc(a) for a, v in d.get("tips") or []], d.get("cu"), d.get("cul")))
    for k in hq: hq[k].sort()
    L = pickle.load(open(f"{D}/live.pkl", "rb"))
    lots = pickle.load(open(f"{D}/lots24.pkl", "rb"))
    hlot = {}
    for r in lots:
        b = r["b"]
        if b.get("d_slot") is not None: hlot.setdefault((b["mint"], b["d_slot"], b["d_i"]), []).append(r)
    # tape rows for wallets-between counts
    ids = json.load(open(f"{TAB}/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    T = np.load(f"{TAB}/trades.npy", mmap_mode="r")
    ev = []
    for run, R in L.items():
        srv = run[:3]
        # regular fires
        for bs, f in R["fires"].items():
            dmp = R["dumps"].get(f["dump_sig"]); tm = R["timing"].get(bs) or {}
            ds, di = (dmp["slot"], dmp["idx"]) if dmp else (tm.get("dslot"), tm.get("didx"))
            if ds is None: continue
            landed = [ours[s] for s in f["sigs"] if s in ours]
            first = min(landed) if landed else None
            ld = R["land"].get(bs) or next((R["land"][s] for s in f["sigs"] if s in R["land"]), None)
            ev.append(dict(run=run, srv=srv, kind="regular", mint=f["mint"], ds=ds, di=di, client=client_class(f.get("client") or ""),
                           us=first, fill=bool(first and not first[2]), eng_ms=(ld or {}).get("rx_ms"), t=f["t"] or (dmp or {}).get("t") or (ld or {}).get("t") or R["start"]))
        # pre-send: landed attempts grouped per dump
        g = collections.defaultdict(list)
        for a in R["pattempts"]:
            if a["slot"] is None or a["dslot"] is None: continue
            g[(a["mint"], a["dslot"], a["didx"])].append(a)
        for (m, ds, di), v in g.items():
            okv = [a for a in v if a["res"] == "ok"]
            fa = min(okv or v, key=lambda a: (a["slot"], a["idx"]))
            o = ours.get(fa["sig"])
            pos = (fa["slot"], fa["idx"], fa["res"] != "ok", None, fa.get("fee"), 0, [])
            ev.append(dict(run=run, srv=srv, kind="presend", mint=m, ds=ds, di=di, client=client_class(fa.get("client") or ""),
                           us=o or pos, fill=bool(okv), eng_ms=fa.get("ms_a"), eng_nb=fa.get("n_between"), t=fa["t"] or R["start"], ddrop=fa.get("ddrop"), dsol=fa.get("dsol")))
    ev = [e for e in ev if W0 <= e["t"] < W1 + 3600]
    P(f"# Latency and head to head; window {pkt(W0)} -> {pkt(W1)} PKT (+ AMS r32/r33 to {pkt(W1 + 3600)} where the tape allows)")
    # wallets between from tape
    mints = sorted({e["mint"] for e in ev} | {k[0] for k in hlot})
    mid = np.array([idm[m] for m in mints if m in idm], np.uint32)
    sel = np.isin(T["mint"], mid); TT = T[sel]
    o = np.lexsort((TT["idx"], TT["slot"], TT["mint"])); TT = TT[o]
    um, st_ = np.unique(TT["mint"], return_index=True); en_ = np.append(st_[1:], len(TT))
    span = {ids[int(m)]: (int(a), int(e)) for m, a, e in zip(um, st_, en_)}
    our_ids = {idm.get("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", -1), idm.get("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", -1)}
    h_id = idm["haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]

    def between(m, a, b, excl):
        if m not in span: return None, None
        lo, hi = span[m]; sl = TT["slot"][lo:hi].astype(np.int64); ix = TT["idx"][lo:hi].astype(np.int64)
        key = sl * 100000 + ix
        j0 = np.searchsorted(key, a[0] * 100000 + a[1], side="right"); j1 = np.searchsorted(key, b[0] * 100000 + b[1], side="left")
        us_ = TT["user"][lo:hi][j0:j1]; bu = TT["buy"][lo:hi][j0:j1].astype(bool)
        m_ = bu & ~np.isin(us_, list(excl))
        return int(len(set(us_[m_].tolist()))), bool(np.isin(us_[bu], [h_id]).any())
    rows = []
    for e in ev:
        d = (e["ds"], e["di"]); dcc = cc(*d)
        u = e["us"]
        e["u_ms"] = cc(u[0], u[1]) - dcc if u else None
        e["u_slots"] = u[0] - d[0] if u else None
        e["u_idx"] = (u[1] - d[1]) if (u and u[0] == d[0]) else None
        if u: e["u_nw"], e["h_before_us"] = between(e["mint"], d, (u[0], u[1]), our_ids | {h_id})
        hv = [x for x in hq.get(e["mint"], []) if (x[0], x[1]) > d and x[0] <= d[0] + 10]
        h = hv[0] if hv else None
        e["h"] = h; e["h_ms"] = cc(h[0], h[1]) - dcc if h else None; e["h_fill"] = bool(h and not h[2])
        e["h_lots"] = hlot.get((e["mint"], d[0], d[1]), [])
        rows.append(e)
    pickle.dump(rows, open(f"{D}/h2h.pkl", "wb"))
    # ---------------- our latency table
    P("\n## Our side: landed buy txs after the trigger dump (chain clock; MEASURED)")
    P("| path | events | landed | fills | slots after p10/50/90 | same slot | index gap p10/50/90 | ms after p10/50/90 | wallets between p10/50/90 | engine ms p50 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    J = {}
    for k in ("regular", "presend"):
        for fo in (False, True):
            v = [e for e in rows if e["kind"] == k and e["us"] and (e["fill"] or not fo)]
            if not v: continue
            nm = f"{k} {'fills' if fo else 'all landed'}"
            P(f"| {nm} | {sum(1 for e in rows if e['kind'] == k)} | {len(v)} | {sum(e['fill'] for e in v)} | {pct([e['u_slots'] for e in v])} | {100 * np.mean([e['u_slots'] == 0 for e in v]):.0f}% | "
              f"{pct([e['u_idx'] for e in v if e['u_idx'] is not None])} | {pct([e['u_ms'] for e in v])} | {pct([e['u_nw'] for e in v])} | {np.median([e['eng_ms'] for e in v if e['eng_ms'] is not None]) if any(e['eng_ms'] is not None for e in v) else float('nan'):.0f} |")
            J[nm] = [float(x) for x in np.percentile([e["u_ms"] for e in v], (10, 50, 90))]
    # his latency on all his DIP buys (from s3) for the same table
    hd = [r["b"] for r in lots if r["t"] == "DIP"]
    P(f"| haqq DIP first buys (fills) | {len(hd)} | | | {pct([b['d_slots'] for b in hd])} | {100 * np.mean([b['d_slots'] == 0 for b in hd]):.0f}% | {pct([b['d_idx'] for b in hd if b['d_idx'] is not None])} | {pct([b['d_ms'] for b in hd])} | {pct([b['d_nw'] for b in hd])} | |")
    J["haqq DIP"] = [float(x) for x in np.percentile([b["d_ms"] for b in hd], (10, 50, 90))]
    # ---------------- head to head
    P("\n## Head to head on the same dump (both landed a buy tx after it; MEASURED)")
    P("| set | dumps | we first | median ms (us / him) | median gap him - us, ms | p10/p90 gap | same slot both |")
    P("|---|---|---|---|---|---|---|")
    H2 = {}
    for nm, f in (("all, regular", lambda e: e["kind"] == "regular"), ("all, pre-send", lambda e: e["kind"] == "presend"),
                  ("our FILLS vs his FILLS, regular", lambda e: e["kind"] == "regular" and e["fill"] and e["h_fill"]),
                  ("our FILLS vs his FILLS, pre-send", lambda e: e["kind"] == "presend" and e["fill"] and e["h_fill"]),
                  ("our FAILS (regular)", lambda e: e["kind"] == "regular" and not e["fill"])):
        v = [e for e in rows if f(e) and e["us"] and e["h"]]
        if not v: P(f"| {nm} | 0 | | | | | |"); continue
        gap = np.array([e["h_ms"] - e["u_ms"] for e in v]); wf = np.mean([(e["us"][0], e["us"][1]) < (e["h"][0], e["h"][1]) for e in v])
        P(f"| {nm} | {len(v)} | {100 * wf:.0f}% | {np.median([e['u_ms'] for e in v]):.0f} / {np.median([e['h_ms'] for e in v]):.0f} | {np.median(gap):+.0f} | {np.percentile(gap, 10):+.0f} / {np.percentile(gap, 90):+.0f} | {100 * np.mean([e['us'][0] == e['h'][0] for e in v]):.0f}% |")
        H2[nm] = dict(n=len(v), we_first=float(wf), gap50=float(np.median(gap)))
    P("\nBy leader client (regular + pre-send, both landed):")
    P("| client | dumps | we first | our ms p50 | his ms p50 |"); P("|---|---|---|---|---|")
    for cl in ("jito", "bam", "harmonic", "fd", "agave", "other", "?"):
        v = [e for e in rows if e["us"] and e["h"] and e["client"] == cl]
        if v: P(f"| {cl} | {len(v)} | {100 * np.mean([(e['us'][0], e['us'][1]) < (e['h'][0], e['h'][1]) for e in v]):.0f}% | {np.median([e['u_ms'] for e in v]):.0f} | {np.median([e['h_ms'] for e in v]):.0f} |")
    # how often he shows up on our events, and his P&L there
    P("\nhaqq on OUR events:")
    for k in ("regular", "presend"):
        for fo in (True, False):
            v = [e for e in rows if e["kind"] == k and e["us"] and e["fill"] == fo]
            if not v: continue
            hl = [x for e in v for x in e["h_lots"]]
            P(f"- {k} {'fills' if fo else 'failed/landed-late'}: {len(v)} events; he landed a buy {100 * np.mean([e['h'] is not None for e in v]):.0f}%, filled {100 * np.mean([e['h_fill'] for e in v]):.0f}%; "
              f"his lots there {len(hl)}, net {sum(x['net'] for x in hl):+.2f} SOL ({1000 * np.mean([x['net'] for x in hl]) if hl else 0:+.1f} mSOL/lot)")
    # ---------------- tx shape
    P("\n## Tx shape (landed buy txs, window; MEASURED)")
    hb = [x for v in hq.values() for x in v]
    hbw = [x for x in hb if not x[2]]
    sv = collections.Counter((x[5][0] if x[5] else "no tip") for x in hbw)
    P(f"haqq landed buys {len(hbw):,} (+{sum(x[2] for x in hb):,} failed buys): fee p50 {np.median([x[3] for x in hbw]) / 1e9:.6f} SOL, tip p50 {np.median([x[4] for x in hbw]) / 1e9:.6f}, "
      f"CU used p50 {np.median([x[6] for x in hbw if x[6]]):.0f}, CU limit p50 {np.median([x[7] for x in hbw if x[7]]):.0f}; landed path: " + ", ".join(f"{k} {100 * c / len(hbw):.0f}%" for k, c in sv.most_common(7)))
    ob = [v for v in ours.values() if not v[2] and v[1] is not None]
    ou = collections.Counter((v[6][0] if v[6] else "no tip") for v in ours.values() if not v[2])
    P(f"ours landed txs {len(ob):,}: fee p50 {np.median([v[4] for v in ob]) / 1e9:.6f}, tip p50 {np.median([v[5] for v in ob]) / 1e9:.6f}; path: " + ", ".join(f"{k} {100 * c / len(ob):.0f}%" for k, c in ou.most_common(7)))
    json.dump(dict(our=J, h2h=H2), open(f"{D}/s5.json", "w"), indent=1)
    open(f"{D}/s5.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
