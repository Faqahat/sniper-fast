#!/usr/bin/env python3
"""VERIFY v1 (read-only; INFERRED replay): G2's FROZEN re-arm rule any:20:30:8:2 run through G2's own engine-faithful replay
(rearm/rsim.run_x + r4_days helpers, imported unchanged) on a FRESH tape the analysts never saw (recordings after the dv8 tape
end, 10-28 01:10:23 PKT = bt 1793131823). Event building is a copy of rearm/r3_events.main + r3b_holders.main with only the
paths and the day/hour filter changed (fresh bt >= FRESH0 and hour coverage >= 0.95 from this tape's own slots.npy).
Our own live pre-send fills/sells/landed tries (all runs incl. FRA r27) are removed, as G2 did.
Out: DATA/fwd_res.pkl (per draw: base and cfg rows + per-window hour) and a printed table.
usage: v1_rsim_fwd.py TAB [--draws 3] [--cfg any:20:30:8:2]"""
import sys, os, json, pickle, time, glob, hashlib, collections, argparse
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/rearm")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/density")
import rlib, sim, dsim, drun, s48lib, rsim
import r4_days as R4

DATA = "/home/moiz/sniper-data/haqq_dissect/verify"
FRESH0 = 1793131823            # last block time on the dv8 tape (10-28 01:10:23 PKT)
WHALE = 60_000_000_000_000
SIZE = 400_000_000


def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


def our_sighs():
    fn = f"{DATA}/our_sighs.pkl"
    if os.path.exists(fn): return pickle.load(open(fn, "rb"))
    files = glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + \
        glob.glob("/home/moiz/sniper-data/haqq_strat/live/dip_ams_r*.jsonl") + ["/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"] + \
        glob.glob(f"{DATA}/live/dip_r*.jsonl")
    out = set()
    for f in files:
        for l in open(f, errors="ignore"):
            if '"presend_live_fill"' in l or '"presend_live_sell_land"' in l or ('"presend_attempt_land"' in l and '"res":"ok"' in l) or '"presend_live_close"' in l:
                try: r = json.loads(l)
                except Exception: continue
                if r.get("sig"): out.add(sh(r["sig"]))
                for s in (r.get("sell_sigs") or []): out.add(sh(s[0]))
    pickle.dump(out, open(fn, "wb"))
    return out


def usable_hours(tab):
    S = np.load(f"{tab}/slots.npy")
    bt = S["bt"].astype(np.int64); sl = S["slot"].astype(np.int64)
    h = (bt + 18000) // 3600 * 3600 - 18000
    out = {}
    for hh in np.unique(h):
        m = h == hh
        exp = sl[m].max() - sl[m].min() + 1
        out[int(hh)] = (int(m.sum()) / exp, int(m.sum()), int(bt[m].min()), int(bt[m].max()))
    return out


def build_events(tab, sighs, good):
    """copy of r3_events.main (T2 triggers + whale dumps) and r3b_holders.main (holder stop), fresh-window filter"""
    tp = rlib.Tape(tab=tab, with_ours=False); tp.skip_sigh = sighs
    keep = ~np.isin(tp.sigh, np.fromiter(tp.skip_sigh, dtype=np.uint64))
    BTE = int(np.load(f"{tab}/slots.npy")["bt"].max()) - 90       # leave room for the exit at the tape end
    ok_t = lambda bt: FRESH0 < bt < BTE and ((bt + 18000) // 3600 * 3600 - 18000) in good
    ids = tp.ids
    trigs = rlib.detect(tp, whale_pct=6.0)
    T2 = []
    for x in trigs:
        if not ok_t(x["bt"]): continue
        ws = None
        for k in x["sells"]:
            if keep[k]: ws = (int(tp.s[k]), int(tp.i[k])); break
        T2.append(dict(kind="t2", mint=x["mint"], slot=x["slot"], idx=x["idx"], j=x["j"], age_slots=x["age_slots"], v2=x["v2"], cashback=x["cashback"],
                       whale_b58=ids[x["whale"]], whale_id=x["whale"], whale_sell=ws, pct=x["pct"], bt=x["bt"], sol=x["sol"]))
    t2win = collections.defaultdict(list)
    for x in T2: t2win[x["mint"]].append((x["whale_id"], x["slot"], x["whale_sell"]))
    fm = rlib.followed_mints(tp)
    big = np.flatnonzero((tp.tok >= WHALE) & (~tp.buy) & keep)
    mids = np.unique(tp.T["mint"][big])
    cand = [int(m) for m in mids if int(m) in fm]
    EV = []; EVH = {}
    for mid in cand:
        mint = ids[mid]; c = tp.creates.get(mint)
        if c is None: continue
        a, e = tp.span[mid]
        rows = [k for k in range(a, e) if keep[k]]
        s0 = c["slot"]
        bal = collections.defaultdict(int); nbig = 0
        dumps = []; snap = []
        for k in rows:
            u = int(tp.user[k]); b0 = bal[u]
            bal[u] = b0 + (int(tp.tok[k]) if tp.buy[k] else -int(tp.tok[k]))
            nbig += int(bal[u] >= WHALE) - int(b0 >= WHALE)
            snap.append(nbig)
            if (not tp.buy[k]) and tp.tok[k] >= WHALE: dumps.append((len(snap) - 1, k, int(bal[u])))
        if not dumps: continue
        rs = np.array([tp.s[k] for k in rows], np.int64)
        snp = np.array(snap); zero = np.flatnonzero(snp == 0)
        for q, (ri, k, rem) in enumerate(dumps):
            s = int(tp.s[k])
            v = int(tp.vsol[k]); t = int(tp.vtok[k]); fr = float(tp.fr[k])
            x = int(SIZE / (1.0 + fr)); qq = (t * x) // (v + x); v += x; t -= qq
            r_end = int(np.searchsorted(rs, s + 2, side="right"))
            for kk in rows[ri + 1:r_end]:
                if tp.buy[kk]:
                    sol = int(tp.sol[kk]); dtk = (t * sol) // (v + sol); v += sol; t -= dtk
                else:
                    tk = int(tp.tok[kk]); so = (v * tk) // (t + tk); v -= so; t += tk
            r2 = (v * qq) // (t + qq) * (1.0 - fr) / 1e9 - SIZE / 1e9
            nx = dumps[q + 1] if q + 1 < len(dumps) else None
            t2hit = any(wid == tp.user[k] and ws is not None and ws == (s, int(tp.i[k])) for wid, ts, ws in t2win.get(mint, []))
            bt = int(tp.blockt[k])
            EV.append(dict(mint=mint, slot=s, idx=int(tp.i[k]), j=int(tp.j[k]), seller=ids[int(tp.user[k])], seller_id=int(tp.user[k]), tok=int(tp.tok[k]),
                           sol=int(tp.sol[k]), vsol=int(tp.vsol[k]), vtok=int(tp.vtok[k]), r2=r2, age_s=(s - s0) * 0.212, age_slots=s - s0, rem=rem,
                           nbig2=snap[r_end - 1] if r_end - 1 >= 0 else 0,
                           nxt=(int(tp.s[nx[1]]), int(tp.i[nx[1]]), ids[int(tp.user[nx[1]])]) if nx else None, kth=q + 1, bt=bt, ok=ok_t(bt), t2hit=t2hit,
                           v2=bool(c.get("v2")), cashback=bool(c.get("cashback"))))
            p = np.searchsorted(zero, r_end)
            z = zero[p] if p < len(zero) else None
            EVH[(mint, s, int(tp.i[k]))] = None if z is None else (int(tp.s[rows[z]]), int(tp.i[rows[z]]))
    return tp, T2, EV, EVH


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("tab"); ap.add_argument("--draws", type=int, default=3); ap.add_argument("--cfg", default="any:20:30:8:2")
    ap.add_argument("--tag", default="fwd"); ap.add_argument("--cov", type=float, default=0.95)
    A = ap.parse_args()
    t0 = time.time()
    hours = usable_hours(A.tab)
    good = {h for h, (cov, n, a, b) in hours.items() if cov >= A.cov and b > FRESH0}
    for h, (cov, n, a, b) in sorted(hours.items()):
        print(f"hour {rlib.pkt(h)} PKT cov {cov:.3f} slots {n} bt {a}..{b} {'USE' if h in good else 'skip'}", flush=True)
    sighs = our_sighs()
    tp, T2, EV, EVH = build_events(A.tab, sighs, good)
    c = R4.parse_cfg(A.cfg)
    REW = R4.re_windows(EV, c, EVH)
    print(f"T2 {len(T2):,}; whale dumps {len(EV):,} (fresh+usable {sum(e['ok'] for e in EV):,}); re windows {len(REW):,} ({time.time() - t0:.0f} s)", flush=True)
    ck = tp.clock()
    store = sim.LazyStore(tp, R4.spans(list(T2) + REW), maxn=4000)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel(); nm = drun.near_map()
    land = dsim.LandingX(D3, pm, nm, probes=("P3",)); model = s48lib.ModelN(D3, drun.s48_clock(), ("P1", "P2", "P3")); view = sim.View()
    RA = argparse.Namespace(size=0.40, k=8, rate=40, noquiet=False, t2win=10, lag=0.0, relag=0.0, guard=False, guard_re=False)
    cfg = R4.make_cfg(RA)
    out = {"base": [], c["name"]: []}
    for d in range(A.draws):
        for name, rw in (("base", []), (c["name"], REW)):
            t1 = time.time()
            res = rsim.run_x(ck, store, list(T2) + rw, cfg, land, model, view, 9100 + d, pm, log=False)
            rows = [R4.row(r) for r in res]
            out[name].append(rows)
            nf = sum(1 for r in res if r.get("filled")); nre = sum(1 for r in res if r.get("filled") and r["trig"]["kind"] == "re")
            print(f"draw {d} {name}: fills {nf} (re {nre}) {time.time() - t1:.0f} s", flush=True)
    S = np.load(f"{A.tab}/slots.npy"); smap = dict(zip(S["slot"].astype(np.int64).tolist(), S["bt"].astype(np.int64).tolist()))
    pickle.dump(dict(out=out, hours={h: hours[h] for h in good}, smap_slots=(S["slot"], S["bt"]), cfg=c, n_t2=len(T2), n_re=len(REW),
                     n_ev=len(EV)), open(f"{DATA}/{A.tag}_res.pkl", "wb"))
    print(f"done {time.time() - t0:.0f} s", flush=True)
