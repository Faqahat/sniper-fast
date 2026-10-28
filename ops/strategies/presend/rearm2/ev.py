#!/usr/bin/env python3
"""Per day (23:15 PKT boundaries): T2 triggers (rlib.detect = presend_live.rs Detector, 6%) with the QUIET arm signals, and every
whale dump (single sell >= 6% of supply) on followed tokens with what the engine knows at the end of slot dump+2 (holders >= 6%
with balances, the next whale dump, the 'no >= 6% holder left' trade, QUIET signals of the largest remaining holder at dump+3).
Our two wallets' trades are removed from the tape. Usable hours only. Read-only. Out: ev_<day>.pkl
usage: ev.py DAYK TAB HOURS_JSON [END_BT]"""
import sys, os, json, pickle, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import rlib
W = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2"
DAY0 = 1793038500 - 5 * 86400
WHALE = 60_000_000_000_000
OUR = ("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE")
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
QB = None


def wdf(wb58, s0, bt0):
    d = [nf for s, bt, nf in QB.get(wb58, []) if s + 2 < s0 and bt >= bt0 - 86400 and bt <= bt0]
    return float(np.mean(d)) if d else -1.0


def qsig(tp, rows, upto, s0, bt0, wb58, ids):
    """rows: token row indices (chain order, ours removed); upto = number of rows before the trigger"""
    pre = rows[:upto]
    since = s0 - int(tp.s[pre[-1]]) if pre else 9999
    bal = collections.defaultdict(int); seen = set()
    for k in pre:
        u = int(tp.user[k]); bal[u] += int(tp.tok[k]) if tp.buy[k] else -int(tp.tok[k]); seen.add(u)
    coh = sum(1 for u in seen if ids[u] in COH and bal[u] > 0)
    fb = sum(1 for u in seen if ids[u] in FB)
    f = wdf(wb58, s0, bt0)
    return dict(since_last=since, coh_hold=coh, fb_n=fb, wh_fol=f, all4=bool(since >= 1 and coh == 0 and fb < 2 and f < 2.24))


def main(D, tab, hours, end_bt):
    global QB
    t0 = time.time()
    QB = pickle.load(open(f"{W}/qbook.pkl", "rb"))
    tp = rlib.Tape(tab=tab, with_ours=False)
    ids = tp.ids; idm = tp.id_map()
    our_ids = {idm[w] for w in OUR if w in idm}
    keep = ~np.isin(tp.user, np.array(sorted(our_ids), dtype=np.int64)) if our_ids else np.ones(len(tp.s), bool)
    good = {r["h"] for r in json.load(open(hours))["rows"] if r["usable"]}
    a_day = DAY0 + D * 86400; b_day = min(a_day + 86400, end_bt)
    def ok_t(bt): return a_day <= bt < b_day and ((bt // 3600) * 3600 in good or bt >= (end_bt // 3600) * 3600)
    print(f"D{D}: tape {len(tp.s):,} ({time.time() - t0:.0f} s)", flush=True)
    trigs = rlib.detect(tp, whale_pct=6.0)
    T2 = []
    rows_of = {}
    def rows(mid):
        if mid not in rows_of:
            a, e = tp.span[mid]; rows_of[mid] = [k for k in range(a, e) if keep[k]]
        return rows_of[mid]
    for x in trigs:
        if not ok_t(x["bt"]): continue
        ws = None
        for k in x["sells"]:
            if keep[k]: ws = (int(tp.s[k]), int(tp.i[k])); break
        rr = rows(x["mid"]); up = rr.index(x["k"]) if x["k"] in rr else len([k for k in rr if (tp.s[k], tp.i[k], tp.j[k]) < (x["slot"], x["idx"], x["j"])])
        q = qsig(tp, rr, up, x["slot"], x["bt"], ids[x["whale"]], ids)
        T2.append(dict(kind="t2", mint=x["mint"], slot=x["slot"], idx=x["idx"], j=x["j"], age_slots=x["age_slots"], v2=x["v2"], cashback=x["cashback"],
                       whale_b58=ids[x["whale"]], whale_id=x["whale"], whale_sell=ws, pct=x["pct"], bt=x["bt"], sol=x["sol"], q=q, create_slot=x["create_slot"]))
    print(f"D{D}: T2 {len(T2):,}, quiet all4 {sum(t['q']['all4'] for t in T2):,} ({time.time() - t0:.0f} s)", flush=True)
    t2win = collections.defaultdict(list)
    for x in T2: t2win[x["mint"]].append((x["whale_id"], x["whale_sell"]))
    fm = rlib.followed_mints(tp)
    big = np.flatnonzero((tp.tok >= WHALE) & (~tp.buy) & keep)
    mids = np.unique(tp.T["mint"][big])
    EV = []
    for mid in (int(m) for m in mids):
        if mid not in fm: continue
        mint = ids[mid]; c = tp.creates.get(mint)
        if c is None: continue
        rr = rows(mid); s0 = c["slot"]
        bal = collections.defaultdict(int); nbig = 0; snap = np.zeros(len(rr), np.int32); dumps = []
        bal_hist = []
        for q, k in enumerate(rr):
            u = int(tp.user[k]); b0 = bal[u]
            bal[u] = b0 + (int(tp.tok[k]) if tp.buy[k] else -int(tp.tok[k]))
            nbig += int(bal[u] >= WHALE) - int(b0 >= WHALE); snap[q] = nbig
            if (not tp.buy[k]) and tp.tok[k] >= WHALE: dumps.append((q, k, int(bal[u])))
        if not dumps: continue
        rs = np.array([tp.s[k] for k in rr], np.int64)
        zero = np.flatnonzero(snap == 0)
        for qd, (ri, k, rem) in enumerate(dumps):
            s = int(tp.s[k]); bt = int(tp.blockt[k])
            r_end = int(np.searchsorted(rs, s + 2, side="right"))
            # holders >= 6% at the end of slot dump+2
            b2 = collections.defaultdict(int)
            for kk in rr[:r_end]:
                u = int(tp.user[kk]); b2[u] += int(tp.tok[kk]) if tp.buy[kk] else -int(tp.tok[kk])
            hold = sorted(((b, u) for u, b in b2.items() if b >= WHALE), reverse=True)
            r_e0 = int(np.searchsorted(rs, s, side="right")); b0_ = collections.defaultdict(int)
            for kk in rr[:r_e0]:
                u = int(tp.user[kk]); b0_[u] += int(tp.tok[kk]) if tp.buy[kk] else -int(tp.tok[kk])
            hold0 = sorted(((b, u) for u, b in b0_.items() if b >= WHALE), reverse=True)
            zi = np.searchsorted(zero, r_end); nobig = (int(tp.s[rr[zero[zi]]]), int(tp.i[rr[zero[zi]]])) if zi < len(zero) else None
            nx = dumps[qd + 1] if qd + 1 < len(dumps) else None
            qh = None
            if hold:
                r3 = int(np.searchsorted(rs, s + 3, side="left"))
                qh = qsig(tp, rr, r3, s + 3, bt, ids[hold[0][1]], ids)
            t2hit = any(wid == tp.user[k] and ws == (s, int(tp.i[k])) for wid, ws in t2win.get(mint, []))
            EV.append(dict(mint=mint, slot=s, idx=int(tp.i[k]), j=int(tp.j[k]), seller=ids[int(tp.user[k])], seller_id=int(tp.user[k]), tok=int(tp.tok[k]),
                           sol=int(tp.sol[k]), vsol=int(tp.vsol[k]), age_s=(s - s0) * 0.212, age_slots=s - s0, rem=rem, nbig2=len(hold), nbig0=len(hold0), maxpct0=(hold0[0][0] / 1e13 if hold0 else 0.0),
                           holders=[(u, b) for b, u in hold], maxpct=(hold[0][0] / 1e13 if hold else 0.0), nobig=nobig, qh=qh,
                           nxt=(int(tp.s[nx[1]]), int(tp.i[nx[1]]), ids[int(tp.user[nx[1]])]) if nx else None, kth=qd + 1, bt=bt, ok=ok_t(bt), t2hit=t2hit,
                           v2=bool(c.get("v2")), cashback=bool(c.get("cashback")), create_slot=s0))
    print(f"D{D}: whale dumps {len(EV):,}; usable {sum(e['ok'] for e in EV):,}; with holder {sum(e['ok'] and e['nbig2'] > 0 for e in EV):,} ({time.time() - t0:.0f} s)", flush=True)
    hrs = sorted({h for h in good if a_day <= h < b_day} | ({(end_bt // 3600) * 3600} if a_day <= end_bt < a_day + 86400 else set()))
    pickle.dump(dict(T2=T2, EV=EV, day=D, a=a_day, b=b_day, hours=hrs, tab=tab), open(f"{W}/ev_D{D}.pkl", "wb"))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1 << 40)
