#!/usr/bin/env python3
# PASS 1 (read-only, offline). One collect run: phase-A bucket rows -> per (wallet, token) round-trip PnL pieces.
#   pairs/bNNN.jsonl.gz  : every wallet whose FIRST curve buy on a launch landed <= EARLY slots after the create (plus
#                          early failed-only attempts, plus creator / glued-bundle / creator-Jito-bundle roles, flagged)
#   other/bNNN.jsonl.gz  : per-wallet totals over all remaining (wallet, token) pairs of the bucket (later buys, sell-only)
#   launch/bNNN.jsonl.gz : per-launch info (dev buy, glued bundle, P0, curve completed, mayhem, metadata, price path)
# PnL per pair (lamports): buys cost sol + protocol fee + creator fee; sells return sol - both fees; plus the tx fee + tips
#   of the pair's txs (payer == wallet pays all; a relayed tx is split among its trading users); failed txs (err) cost
#   their fee only (their trade events are reverted, so they are NOT replayed); tokens still held at the end are valued
#   by selling them into the last curve state (fees deducted); 'gopen' = curve completed (moved to the AMM, no price
#   here) while the wallet still held > 5% of what it bought.
# Only SOL-quoted launches: first trade starts at 30 SOL / 1.073e15 virtual reserves and max vsol <= 200 SOL.
# usage: python3 -I w1_pairs.py <phaseA dir> <run dir> <out dir> [procs]
import sys, os, json, gzip, glob, collections, zlib
from multiprocessing import Pool
A, RUN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]; PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 8
EARLY = 10; GRAD = 114_000_000_000; ABSURD = 200_000_000_000
L = {}; E = {}

def load():
    for l in open(os.path.join(RUN, "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("err"): continue
        L.setdefault(c["mint"], c)
    for l in open(os.path.join(RUN, "enrich.jsonl")):
        try: r = json.loads(l)
        except Exception: continue
        m = r.get("mint")
        if m not in L or m in E: continue
        meta = r.get("meta") or {}; js = meta.get("json") if isinstance(meta.get("json"), dict) else {}
        jc = r.get("jito_create") or {}
        E[m] = (1 if js.get("twitter") else 0, 1 if js.get("website") else 0, 1 if js.get("telegram") else 0, len(str(js.get("description") or "")),
                r.get("creator_prior_n"), tuple(jc.get("txs") or ()), jc.get("tip"), (r.get("funder") or {}).get("from_"),
                str(js.get("createdOn") or "")[:40], len(r.get("creator_recent_creates") or []))

def sellval(q, V, T, bps):
    if q <= 0 or T <= 0: return 0
    return int(V * q // (T + q) * (1 - bps / 1e4))

def work(bdir):
    b = os.path.basename(bdir)
    TR = collections.defaultdict(list); XR = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(bdir, "*.jsonl.gz"))):
        try:
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    r = json.loads(line)
                    if r[1] not in L: continue
                    if r[0] == "T": TR[r[1]].append(r)
                    elif r[12] or r[14]: XR[r[1]].append((r[2], r[3], r[5], r[6], r[7], r[12], r[14]))   # failed tx / token moves only
        except (EOFError, OSError, zlib.error): pass
    pairs = []; other = {}; linfo = []; stats = collections.Counter()
    def oth(w):
        o = other.get(w)
        if o is None: o = other[w] = [0, 0, 0, 0, 0, 0, 0, 0]   # n_tok, bsol, ssol, fee, efee, lval, n_gopen, pnl
        return o
    for m, rows in TR.items():
        c = L[m]; e = E.get(m) or (0, 0, 0, 0, None, (), None, None, "", 0)
        seen = set(); tr = []; errs = []
        for r in sorted(rows, key=lambda r: (r[2], r[3], r[13])):
            k = (r[5], r[13])
            if k in seen: continue
            seen.add(k); (errs if r[12] else tr).append(r)
        stats["mints"] += 1
        if not tr: stats["no_ok_trades"] += 1; continue
        t0 = tr[0]
        V0 = t0[18] - t0[16] if t0[15] == 1 else t0[18] + t0[16]
        T0 = t0[19] + t0[17] if t0[15] == 1 else t0[19] - t0[17]
        maxv = max(r[18] for r in tr)
        if not (29_900_000_000 <= V0 <= 30_100_000_000) or maxv > ABSURD:
            stats["not_sol_quote"] += 1; continue
        stats["sol_launches"] += 1
        S = c["slot"]; ci = c.get("idx"); cs = c.get("sig"); creator = c.get("creator") or c.get("user"); signer = c.get("user")
        may = int("InitializeMayhemState" in (c.get("ixn") or []))
        # glued bundle exactly as b_launch.py (on successful trades)
        g = []; prev = ci; gi = 0; dev_buy = 0
        for k, t in enumerate(tr):
            if t[5] == cs:
                gi = k + 1
                if t[15] == 1: dev_buy += t[16]
                continue
            if ci is None: break
            if t[2] == S and t[3] in (prev, prev + 1) and t[15] == 1: g.append(t); prev = t[3]; gi = k + 1
            elif t[2] == S and t[3] > prev + 1: break
            elif t[2] > S: break
        gusers = {t[14] for t in g}
        jset = set(e[5]); jusers = {t[14] for t in tr if t[5] in jset and t[5] != cs}
        roles = {}
        for u in (creator, signer):
            if u: roles[u] = "creator"
        for u in gusers:
            roles.setdefault(u, "glued")
        for u in jusers:
            roles.setdefault(u, "jito")
        pre = tr[gi - 1] if gi > 0 else None
        P0 = (pre[18] / pre[19]) if (pre and pre[19]) else (V0 / T0)
        grad_k = next((k for k, t in enumerate(tr) if t[18] >= GRAD), None)
        # per-sig info for fee attribution
        sig_users = collections.defaultdict(set); sig_info = {}
        for t in tr:
            sig_users[t[5]].add(t[14]); sig_info.setdefault(t[5], (t[6], t[7], t[11]))
        # replay: per-wallet aggregates
        W = {}; bal = collections.defaultdict(int); gbal = None
        cur_sig = None; committed = 0; committed_sol = 0; cur_out = False; cur_sol = 0; all_buy_sigs = set()
        dev_sell_s = None; first_out_sell_s = None; nbuy_out_5 = 0; nbuy_out_slot = 0; out_buy_sigs5 = set()
        early = []
        for k, t in enumerate(tr):
            u = t[14]; buy = t[15] == 1; d = t[2] - S
            if k >= gi and t[5] != cur_sig:
                if cur_out: committed += 1; committed_sol += cur_sol
                cur_sig = t[5]; cur_out = False; cur_sol = 0
            w = W.get(u)
            if w is None:
                w = W[u] = dict(fk=None, nb=0, ns=0, bsol=0, ssol=0, tb=0, ts=0, s1=None, sl=None, bt_ls=None, fee=0, efee=0, xo=0, xi=0)
            if buy:
                if w["fk"] is None:
                    Vp = t[18] - t[16]; Tp = t[19] + t[17]
                    w.update(fk=k, fs=d, fi=t[3], fsig=t[5], fbt=t[4], fsol=t[16], ftok=t[17],
                             ahead=committed if k >= gi else -1, ahead_sol=committed_sol if k >= gi else 0,
                             ahead_all=len(all_buy_sigs - {t[5]}),
                             mult=round((Vp / Tp) / P0, 4) if Tp else None, fcup=t[8], ffee=t[7], ftips=t[11], fself=int(t[6] == u))
                w["nb"] += 1; w["bsol"] += t[16] + t[20] + t[21]; w["tb"] += t[17]; bal[u] += t[17]
                all_buy_sigs.add(t[5])
                if k >= gi and u not in roles:
                    cur_out = True; cur_sol += t[16]
                    if d <= 5 and t[5] not in out_buy_sigs5:
                        out_buy_sigs5.add(t[5]); nbuy_out_5 += 1
                        if d == 0: nbuy_out_slot += 1
                    if len(early) < 15 and (not early or early[-1][0] != u): early.append([u, d, round(t[16] / 1e9, 4), t[3]])
            else:
                w["ns"] += 1; w["ssol"] += t[16] - t[20] - t[21]; w["ts"] += t[17]; bal[u] -= t[17]
                if w["s1"] is None: w["s1"] = d
                w["sl"] = d; w["bt_ls"] = t[4]
                if u in (creator, signer) and dev_sell_s is None: dev_sell_s = d
                if u not in roles and first_out_sell_s is None: first_out_sell_s = d
            if grad_k is not None and k == grad_k: gbal = dict(bal)
        # fees (successful txs): payer gets all if it traded in the tx, else split among the tx's users
        for sg, us in sig_users.items():
            payer, fee, tips = sig_info[sg]
            if payer in us: W[payer]["fee"] += fee + tips
            else:
                for u in us: W[u]["fee"] += (fee + tips) / len(us)
        # failed txs: fee only, to the payer
        fails = collections.defaultdict(lambda: [0, 0, None])   # payer -> [n, fee, first slot delta]
        fseen = set()
        for r in errs:
            if r[5] in fseen: continue
            fseen.add(r[5]); f_ = fails[r[6]]; f_[0] += 1; f_[1] += r[7]; f_[2] = r[2] - S if f_[2] is None else min(f_[2], r[2] - S)
        for (s, i, sg, payer, fee, err, tb) in XR.get(m, ()):
            if err and sg not in fseen:
                fseen.add(sg); f_ = fails[payer]; f_[0] += 1; f_[1] += fee; f_[2] = s - S if f_[2] is None else min(f_[2], s - S)
            if tb and not err:
                for x in tb:
                    if len(x) >= 4 and x[0] == m and x[1] in W:
                        dlt = (x[3] or 0) - (x[2] or 0)
                        if dlt < 0: W[x[1]]["xo"] -= dlt
                        elif dlt > 0: W[x[1]]["xi"] += dlt
        last = tr[-1]; Ve, Te = last[18], last[19]; bps = (last[22] or 95) + (last[23] or 30)
        grad = int(maxv >= GRAD)
        # price path vs P0 (end-of-checkpoint prices)
        px = {}; hz = [(5, "p1s"), (25, "p5s"), (150, "p30s"), (300, "p60s"), (1500, "p5m")]; hi = 0; pk60 = 0; pk5m = 0; prev_p = 1.0
        for t in tr[gi:]:
            d = t[2] - S
            while hi < len(hz) and d > hz[hi][0]: px[hz[hi][1]] = round(prev_p, 4); hi += 1
            p = (t[18] / t[19]) / P0 if t[19] else 0; prev_p = p
            if d <= 300: pk60 = max(pk60, p)
            if d <= 1500: pk5m = max(pk5m, p)
        last_p = (Ve / Te) / P0 if Te else 0
        for _, nm in hz[hi:]: px[nm] = round(last_p, 4)
        linfo.append(dict(m=m, S=S, bt=c.get("bt"), creator=creator, signer=signer, payer=c.get("payer"), name=(c.get("name") or "")[:40],
                          symbol=(c.get("symbol") or "")[:20], ixn0=(c.get("ixn") or [""])[0], may=may, maxv=round(maxv / 1e9, 2), grad=grad,
                          dev_buy=dev_buy, glued_n=len({t[5] for t in g}), glued_w=len(gusers), glued_sol=sum(t[16] for t in g),
                          jito_n=len(jset), jito_tip=e[6], jito_w=len(jusers), P0=P0, n_tr=len(tr), n_buyers=len({t[14] for t in tr if t[15] == 1}),
                          vol=sum(t[16] for t in tr), dev_sell_s=dev_sell_s, first_out_sell_s=first_out_sell_s, out_buys_slot=nbuy_out_slot,
                          out_buys_5=nbuy_out_5, pk60=round(pk60, 3), pk5m=round(pk5m, 3), last_p=round(last_p, 4), last_s=last[2] - S,
                          tw=e[0], web=e[1], tg=e[2], desc=e[3], cpn=e[4], funder=e[7], created_on=e[8], crc=e[9], early=early, **px))
        # emit pairs
        for u, w in W.items():
            q = max(0, w["tb"] - w["ts"] + w["xi"] - w["xo"])
            lval = sellval(q, Ve, Te, bps)
            held_g = (gbal or {}).get(u, 0) if grad_k is not None else 0
            gopen = int(grad and w["tb"] > 0 and held_g > 0.05 * w["tb"])
            f_ = fails.pop(u, None)
            if f_: w["efee"] += f_[1]
            pnl = w["ssol"] + lval - w["bsol"] - w["fee"] - w["efee"]
            role = roles.get(u)
            if (w["fk"] is not None and w["fs"] <= EARLY) or role:
                rec = dict(m=m, w=u, S=S, role=role, may=may, grad=grad, gopen=gopen, nb=w["nb"], ns=w["ns"], bsol=w["bsol"], ssol=w["ssol"],
                           tb=w["tb"], ts=w["ts"], fee=round(w["fee"]), efee=w["efee"], nfail=f_[0] if f_ else 0, xo=w["xo"], xi=w["xi"], left=q, lval=lval,
                           pnl=round(pnl), s1=w["s1"], sl=w["sl"], bt_ls=w["bt_ls"])
                if w["fk"] is not None:
                    for kk in ("fs", "fi", "fsig", "fbt", "fsol", "ftok", "ahead", "ahead_sol", "ahead_all", "mult", "fcup", "ffee", "ftips", "fself"): rec[kk] = w[kk]
                pairs.append(rec)
            else:
                o = oth(u); o[0] += 1; o[1] += w["bsol"]; o[2] += w["ssol"]; o[3] += w["fee"]; o[4] += w["efee"]; o[5] += lval; o[6] += gopen; o[7] += pnl
        # failed attempts by wallets with no successful trade on this launch
        for u, f_ in fails.items():
            if f_[2] is not None and f_[2] <= EARLY:
                pairs.append(dict(m=m, w=u, S=S, role=roles.get(u), may=may, grad=grad, gopen=0, nb=0, ns=0, bsol=0, ssol=0, tb=0, ts=0, fee=0,
                                  efee=f_[1], nfail=f_[0], xo=0, xi=0, left=0, lval=0, pnl=-f_[1], s1=None, sl=None, bt_ls=None, failed_only=1, fail_s=f_[2]))
            else:
                o = oth(u); o[4] += f_[1]; o[7] -= f_[1]
    os.makedirs(os.path.join(OUT, "pairs"), exist_ok=True); os.makedirs(os.path.join(OUT, "other"), exist_ok=True); os.makedirs(os.path.join(OUT, "launch"), exist_ok=True)
    with gzip.open(os.path.join(OUT, "pairs", b + ".jsonl.gz"), "wt", compresslevel=3) as f:
        for r in pairs: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    with gzip.open(os.path.join(OUT, "other", b + ".jsonl.gz"), "wt", compresslevel=3) as f:
        for u, o in other.items(): f.write(json.dumps([u] + [round(x) for x in o], separators=(",", ":")) + "\n")
    with gzip.open(os.path.join(OUT, "launch", b + ".jsonl.gz"), "wt", compresslevel=3) as f:
        for r in linfo: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    return dict(stats)

if __name__ == "__main__":
    load(); os.makedirs(OUT, exist_ok=True)
    bd = sorted(glob.glob(os.path.join(A, "b*")))
    if len(sys.argv) > 5: bd = bd[:int(sys.argv[5])]
    tot = collections.Counter()
    with Pool(PROCS) as p:
        for k, st in enumerate(p.imap_unordered(work, bd), 1):
            tot.update(st)
            if k % 32 == 0: print(f"{k}/{len(bd)} buckets {dict(tot)}", flush=True)
    print("DONE", dict(tot), flush=True)
