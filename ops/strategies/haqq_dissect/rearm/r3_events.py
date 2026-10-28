#!/usr/bin/env python3
"""REARM step 3 (read-only): per test day, from the day's tape cut (r1_tapes.py), everything the engine could see:
  * T2 triggers: the live detector (presend/real/rlib.detect = src/presend_live.rs Detector rules, whale_pct 6, chain order), with
    the whale's first later sell (the window's end);
  * WHALE DUMPS: single sells >= 6% of supply (6e13 raw) on followed tokens (seen from their create, not mayhem, standard curve),
    with what the engine knows at the end of slot dump+2:
      r2   = the 2-slot result of a 0.40 SOL buyer right after the dump: buy at the post-dump curve (pump fee in), every later trade
             of the token through slot dump+2 applied, sold at that state (pump fee out); SOL, before tx costs ('paid' check);
      age  = (dump slot - create slot) x 0.212 s; post-dump curve SOL; seller and its remaining balance; wallets holding >= 6% at the
             end of slot dump+2 (balances from the create, as the detector); the token's next whale dump (slot, idx, seller);
      t2hit = the dump is a T2 whale's first sell inside its 10-slot window (what normal pre-send already targets).
Our live pre-send fills / sells / landed tries (every AMS and FRA run) are removed from the tape (the replay puts its own in).
Usable hours (dv8 hours.json, recording coverage) only. Out: ev_D<k>.pkl"""
import sys, os, json, pickle, time, hashlib, glob, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import rlib
import dv8lib as L

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
WHALE = 60_000_000_000_000
SIZE = 400_000_000


def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


def our_sighs():
    fn = f"{OUT}/our_sighs.pkl"
    if os.path.exists(fn): return pickle.load(open(fn, "rb"))
    files = glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + \
        glob.glob("/home/moiz/sniper-data/haqq_strat/live/dip_ams_r*.jsonl") + ["/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"]
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


def usable_hours():
    h = json.load(open(f"{L.D}/hours.json"))
    return {r["h"] for r in h["rows"] if r["usable"]}


def main(D):
    t0 = time.time()
    tab = f"{OUT}/tab_D{D}"
    tp = rlib.Tape(tab=tab, with_ours=False)
    tp.skip_sigh = our_sighs()
    keep = ~np.isin(tp.sigh, np.fromiter(tp.skip_sigh, dtype=np.uint64))
    good = usable_hours()
    a_day = L.DAY0 + D * 86400; b_day = a_day + 86400
    ok_t = lambda bt: a_day <= bt < b_day and ((bt + 18000) // 3600 * 3600 - 18000) in good
    ids = tp.ids
    print(f"D{D}: tape {len(tp.s):,} trades, {len(tp.creates):,} creates ({time.time() - t0:.0f} s)", flush=True)
    # ---------------- T2 triggers (live detector)
    trigs = rlib.detect(tp, whale_pct=6.0)
    T2 = []
    for x in trigs:
        if not ok_t(x["bt"]): continue
        ws = None
        for k in x["sells"]:
            if keep[k]: ws = (int(tp.s[k]), int(tp.i[k])); break
        T2.append(dict(kind="t2", mint=x["mint"], slot=x["slot"], idx=x["idx"], j=x["j"], age_slots=x["age_slots"], v2=x["v2"], cashback=x["cashback"],
                       whale_b58=ids[x["whale"]], whale_id=x["whale"], whale_sell=ws, pct=x["pct"], bt=x["bt"], sol=x["sol"]))
    print(f"D{D}: T2 triggers {len(T2):,} ({time.time() - t0:.0f} s)", flush=True)
    t2win = collections.defaultdict(list)          # mint -> [(whale id, trigger slot, whale first sell (slot, idx))]
    for x in T2: t2win[x["mint"]].append((x["whale_id"], x["slot"], x["whale_sell"]))
    # ---------------- whale dumps
    fm = rlib.followed_mints(tp)
    big = np.flatnonzero((tp.tok >= WHALE) & (~tp.buy) & keep)
    mids = np.unique(tp.T["mint"][big]) if tp.T is not None else None
    cand = [int(m) for m in mids if int(m) in fm]
    EV = []
    for mid in cand:
        mint = ids[mid]; c = tp.creates.get(mint)
        if c is None: continue
        a, e = tp.span[mid]
        rows = [k for k in range(a, e) if keep[k]]
        s0 = c["slot"]
        bal = collections.defaultdict(int); nbig = 0
        dumps = []
        # pass 1: balances and dumps
        snap = []                      # per row: number of >= 6% holders after it
        for k in rows:
            u = int(tp.user[k]); b0 = bal[u]
            bal[u] = b0 + (int(tp.tok[k]) if tp.buy[k] else -int(tp.tok[k]))
            nbig += int(bal[u] >= WHALE) - int(b0 >= WHALE)
            snap.append(nbig)
            if (not tp.buy[k]) and tp.tok[k] >= WHALE: dumps.append((len(snap) - 1, k, int(bal[u])))
        if not dumps: continue
        rs = np.array([tp.s[k] for k in rows], np.int64)
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
                           sol=int(tp.sol[k]), vsol=int(tp.vsol[k]), vtok=int(tp.vtok[k]), pre_p=(int(tp.vsol[k]) + int(tp.sol[k])) / max(int(tp.vtok[k]) - int(tp.tok[k]), 1),
                           r2=r2, age_s=(s - s0) * 0.212, age_slots=s - s0, rem=rem, nbig2=snap[r_end - 1] if r_end - 1 >= 0 else 0,
                           nxt=(int(tp.s[nx[1]]), int(tp.i[nx[1]]), ids[int(tp.user[nx[1]])]) if nx else None, kth=q + 1, bt=bt, ok=ok_t(bt), t2hit=t2hit,
                           v2=bool(c.get("v2")), cashback=bool(c.get("cashback"))))
    print(f"D{D}: whale dumps {len(EV):,} on {len(cand):,} followed tokens; usable in day {sum(e['ok'] for e in EV):,} ({time.time() - t0:.0f} s)", flush=True)
    pickle.dump(dict(T2=T2, EV=EV, day=D), open(f"{OUT}/ev_D{D}.pkl", "wb"))


if __name__ == "__main__":
    for d in sys.argv[1].split(","): main(int(d))
