#!/usr/bin/env python3
# STRATEGY CENSUS pass 1 (read-only, offline): every wallet's bonding-curve ROUND TRIPS on R2 + R3 launches (last ~48 h),
# with entry-trigger and exit context for each trip. Realized P&L only:
#   closed trip  = position back to <=1% of its peak tokens: P&L = SOL got (net of pump fees) - SOL spent (incl. pump fees)
#                  - tx fees - tips (once per signature)
#   open trip    = still holding at the end of data, curve NOT complete: remaining tokens valued at their exact curve
#                  liquidation value at the final state (status O)
#   graduated    = still holding when the curve completed (AMM after that, no price here): status G, P&L excluded later
# Standard SOL curves only (vsol 25..200 SOL in the first 50 trades: removes mayhem / odd reserves).
# -> /home/moiz/sniper-data/strategies/trips/{R2,R3}_bNNN.jsonl.gz, one JSON list per trip (FIELDS below)
import sys, os, json, gzip, glob, zlib, collections
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/strategies/trips"
RUNS = {"R2": ("run_20261022_1543", [f"{D}/phaseA_fwd"]),
        "R3": ("run_20261023_1426", [f"{D}/phaseA_r3", "/home/moiz/sniper-data/strategies/phaseA_r3tail"])}
GRADV = 113e9
FIELDS = ["u", "m", "run", "bt", "s0", "i0", "age", "nb", "ns", "spent", "got", "cost", "pnl", "st", "hold", "sx", "b1",
          "vsol", "ins", "cslot", "pay_ne", "fee0", "tip0", "cu0",
          # entry context (others' trades only, window = same slot before us + previous 3 slots)
          "bs_sol", "bs_gap", "bs_drop", "bs_di",       # biggest sell: SOL, slot gap (0 = same slot), price drop it caused, tx-index gap if same slot
          "bb_sol", "bb_gap", "bb_di",                  # biggest buy: SOL, slot gap, index gap if same slot
          "dd3", "ret10", "flow3", "nb3", "ns3",        # drop from 3-slot max price to entry; 10-slot return; net SOL flow; #buys/#sells in window
          "dev_b", "dev_s",                             # creator buy / sell SOL in window
          "pv_u", "pv_side", "pv_sol", "pv_gap", "pv_di", "pv_sametx",   # immediately preceding trade
          "quiet", "ntr", "nbuyers", "ath_r", "bun_r",  # slots since last trade; trades / distinct buyers before; price / ATH; price / post-bundle
          # exit context (last sell of the trip)
          "x_mult", "x_peak", "x_pv_side", "x_pv_sol", "x_pv_gap", "x_bb_sol", "x_bb_gap", "x_bs_sol", "x_inflow", "x_outflow",
          "x_first", "x_fee", "x_tip", "grad", "x_dev", "xs", "may"]
NB = 256

def load_launches(run):
    L = {}
    for l in open(os.path.join(D, RUNS[run][0], "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("err"): continue
        L[c["mint"]] = (c["slot"], c.get("idx") or 0, c.get("creator") or c.get("user"), c.get("user"), c.get("sig"), c.get("bt"), "InitializeMayhemState" in (c.get("ixn") or []))
    return L

LA = {}
def init():
    global LA
    LA = {r: load_launches(r) for r in RUNS}

def read(run, b, mints):
    out = collections.defaultdict(list); seen = set()
    for d in RUNS[run][1]:
        for f in glob.glob(f"{d}/b{b:03d}/*.jsonl.gz"):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    e = line.index('"', 6); m = line[6:e]
                    if m not in mints: continue
                    r = json.loads(line)
                    if r[12]: continue
                    k = (r[5], r[13])
                    if k in seen: continue
                    seen.add(k)
                    tips = r[11] if isinstance(r[11], (int, float)) else 0
                    # s, i, j, bt, sig, payer, fee, cu, tips, user, buy, sol, tok, vsol, vtok, fl, cfl
                    out[m].append((r[2], r[3], r[13], r[4], r[5], r[6], r[7] or 0, r[10] or 0, tips, r[14], r[15] == 1, r[16], r[17], r[18], r[19], r[20] or 0, r[21] or 0))
            except (EOFError, OSError, zlib.error, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t[0], t[1], t[2]))
    return out

def pre_state(t):
    # (vsol, vtok) before this trade
    return (t[13] - t[11], t[14] + t[12]) if t[10] else (t[13] + t[11], t[14] - t[12])

def mint_trips(m, tr, c, run):
    S, cidx, creator, signer, csig, cbt, _may = c
    if not tr: return []
    if any(t[13] < 25e9 or t[13] > 200e9 or not t[14] for t in tr[:50]): return []
    n = len(tr)
    pre = [pre_state(t) for t in tr]
    ppre = [v / tk if tk else 0 for v, tk in pre]                 # price before trade k
    ppost = [t[13] / t[14] if t[14] else 0 for t in tr]            # price after trade k
    grad_k = next((k for k, t in enumerate(tr) if t[13] >= GRADV), None)
    # glued bundle (consecutive buy txs right after the create in the create slot) -> insiders
    ins = {creator, signer}; g_end = 0; prev = cidx
    for k, t in enumerate(tr):
        if t[4] == csig: g_end = k + 1; continue
        if t[0] == S and t[1] in (prev, prev + 1) and t[10]:
            ins.add(t[9]); prev = t[1]; g_end = k + 1
        elif t[0] == S and t[1] > prev + 1: break
        elif t[0] > S: break
    p_bun = ppost[g_end - 1] if g_end > 0 else ppre[0]
    # running ATH (price after each trade), distinct buyers before k
    ath = []; a = 0.0
    for k in range(n): ath.append(a); a = max(a, ppost[k])     # ath[k] = max price after trades < k
    buyers_before = []; bs = set()
    for k in range(n): buyers_before.append(len(bs)); bs.add(tr[k][9]) if tr[k][10] else None
    final_V, final_T = tr[-1][13], tr[-1][14]
    trips = []; open_ = {}
    def entry_ctx(k0):
        t0 = tr[k0]; s0, i0, U = t0[0], t0[1], t0[9]
        bs_sol = 0; bs_gap = -1; bs_drop = 0.0; bs_di = -1; bb_sol = 0; bb_gap = -1; bb_di = -1
        flow = 0; nb3 = 0; ns3 = 0; dev_b = 0; dev_s = 0; pmax = ppre[k0]
        k = k0 - 1
        while k >= 0 and tr[k][0] >= s0 - 3:
            t = tr[k]
            pmax = max(pmax, ppost[k], ppre[k])
            if t[9] != U:
                g = s0 - t[0]
                if t[10]:
                    nb3 += 1; flow += t[11]
                    if t[11] > bb_sol: bb_sol, bb_gap, bb_di = t[11], g, (i0 - t[1] if g == 0 else -1)
                    if t[9] == creator: dev_b += t[11]
                else:
                    ns3 += 1; flow -= t[11]
                    if t[11] > bs_sol:
                        bs_sol, bs_gap, bs_di = t[11], g, (i0 - t[1] if g == 0 else -1)
                        bs_drop = 1 - ppost[k] / ppre[k] if ppre[k] else 0
                    if t[9] == creator: dev_s += t[11]
            k -= 1
        dd3 = 1 - ppre[k0] / pmax if pmax else 0
        # 10-slot return: price before the first trade at slot >= s0-10 vs now
        k = k0 - 1; kk = None
        while k >= 0 and tr[k][0] >= s0 - 10: kk = k; k -= 1
        ret10 = (ppre[k0] / ppre[kk] - 1) if kk is not None and ppre[kk] else 0.0
        if k0 > 0:
            p = tr[k0 - 1]; pv = (p[9][:8], "B" if p[10] else "S", round(p[11] / 1e9, 3), s0 - p[0], (i0 - p[1]) if p[0] == s0 else -1, int(p[4] == t0[4]))
            quiet = s0 - p[0]
        else:
            pv = ("", "", 0, -1, -1, 0); quiet = -1
        return [round(bs_sol / 1e9, 3), bs_gap, round(bs_drop, 4), bs_di, round(bb_sol / 1e9, 3), bb_gap, bb_di,
                round(dd3, 4), round(ret10, 4), round(flow / 1e9, 3), nb3, ns3, round(dev_b / 1e9, 3), round(dev_s / 1e9, 3),
                *pv, quiet, k0, buyers_before[k0], round(ppre[k0] / ath[k0], 4) if ath[k0] else 1.0, round(ppre[k0] / p_bun, 4) if p_bun else 0]
    def exit_ctx(tp, kx):
        t = tr[kx]; sx, ix, U = t[0], t[1], t[9]
        p_in = tp["p_in"]
        x_mult = ppre[kx] / p_in if p_in else 0
        x_peak = max(ppost[k] for k in range(tp["k0"], kx + 1)) / p_in if p_in else 0
        if kx > 0:
            p = tr[kx - 1]; xpv = ("B" if p[10] else "S", round(p[11] / 1e9, 3), sx - p[0])
        else: xpv = ("", 0, -1)
        bb = 0; bbg = -1; bsx = 0; k = kx - 1
        while k >= 0 and tr[k][0] >= sx - 2:
            q = tr[k]
            if q[9] != U:
                if q[10] and q[11] > bb: bb, bbg = q[11], sx - q[0]
                if not q[10] and q[11] > bsx: bsx = q[11]
            k -= 1
        infl = sum(q[11] for q in tr[tp["k0"] + 1:kx] if q[10] and q[9] != U)
        outf = sum(q[11] for q in tr[tp["k0"] + 1:kx] if not q[10] and q[9] != U)
        x_dev = int(any((not q[10]) and q[9] == creator for q in tr[max(tp["k0"], kx - 6):kx]))
        return [round(x_mult, 4), round(x_peak, 4), *xpv, round(bb / 1e9, 3), bbg, round(bsx / 1e9, 3), round(infl / 1e9, 3), round(outf / 1e9, 3)], x_dev
    def close(tp, status, kx):
        U = tp["u"]
        if status == "C":
            xc, x_dev = exit_ctx(tp, kx); hold = tr[kx][0] - tp["s0"]; sx = tr[kx][0]
            x_first = tp["first_sell_s"] - tp["s0"] if tp["first_sell_s"] is not None else -1
            xf, xt = tr[kx][6], tr[kx][8]
        else:
            xc = [0, 0, "", 0, -1, 0, -1, 0, 0, 0]; x_dev = 0; hold = -1; sx = -1
            x_first = tp["first_sell_s"] - tp["s0"] if tp["first_sell_s"] is not None else -1; xf = xt = 0
            if tp["ns"]:
                last_s = tp["last_sell_s"]; hold = last_s - tp["s0"]; sx = last_s
        got = tp["got"]
        if status == "O":                                   # liquidate the rest at the final curve state
            rem = tp["pos"]
            if rem > 0 and final_T:
                so = final_V * rem // (final_T + rem); got += so * (1 - 0.0125)
        pnl = (got - tp["spent"] - tp["cost"]) / 1e9 if status != "G" else None
        row = [U, m, run, tp["bt"], tp["s0"], tp["i0"], tp["s0"] - S, tp["nb"], tp["ns"], round(tp["spent"] / 1e9, 5), round(got / 1e9, 5),
               round(tp["cost"] / 1e9, 6), round(pnl, 5) if pnl is not None else None, status, hold, sx, round(tp["b1"] / 1e9, 4),
               round(pre[tp["k0"]][0] / 1e9, 2), int(U in ins), int(tp["s0"] == S), int(tp["pay_ne"]), tp["fee0"], tp["tip0"], tp["cu0"],
               *tp["ectx"], *xc, x_first, xf, xt, int(grad_k is not None), x_dev, tp["xs"], int(c[6])]
        trips.append(row)
    for k, t in enumerate(tr):
        if grad_k is not None and k > grad_k: break
        U = t[9]
        tp = open_.get(U)
        if t[10]:
            cost_add = 0
            if tp is None:
                tp = open_[U] = dict(u=U, k0=k, s0=t[0], i0=t[1], bt=t[3], nb=0, ns=0, spent=0, got=0, cost=0, pos=0, peak=0, sigs=set(),
                                     b1=t[11], p_in=(t[11] / t[12]) if t[12] else 0, pay_ne=t[5] != U, fee0=t[6], tip0=t[8], cu0=t[7],
                                     first_sell_s=None, last_sell_s=None, ectx=entry_ctx(k), xs=0)
            tp["nb"] += 1; tp["spent"] += t[11] + t[15] + t[16]; tp["pos"] += t[12]; tp["peak"] = max(tp["peak"], tp["pos"])
            if t[4] not in tp["sigs"]: tp["sigs"].add(t[4]); tp["cost"] += t[6] + t[8]
        else:
            if tp is None: continue                          # tokens from elsewhere: not a trip of this wallet
            tp["ns"] += 1
            if t[12] > tp["pos"] * 1.001 and t[12] > 0:        # sells more tokens than this trip holds (tokens moved in): count only ours
                fr_ = max(tp["pos"], 0) / t[12]; tp["xs"] += 1
                tp["got"] += (t[11] - t[15] - t[16]) * fr_; tp["pos"] = 0
            else:
                tp["got"] += t[11] - t[15] - t[16]; tp["pos"] -= t[12]
            if tp["first_sell_s"] is None: tp["first_sell_s"] = t[0]
            tp["last_sell_s"] = t[0]
            if t[4] not in tp["sigs"]: tp["sigs"].add(t[4]); tp["cost"] += t[6] + t[8]
            if tp["pos"] <= 0.01 * tp["peak"]:
                close(tp, "C", k); del open_[U]
    for U, tp in open_.items():
        close(tp, "G" if grad_k is not None else "O", None)
    return trips

def work(key):
    run, b = key; fn = f"{OUT}/{run}_b{b:03d}.jsonl.gz"
    if os.path.exists(fn): return run, b, -1
    L = LA[run]
    mints = {m for m in L if zlib.crc32(m.encode()) % NB == b}
    tra = read(run, b, mints); rows = []
    for m, tr in tra.items():
        try: rows += mint_trips(m, tr, L[m], run)
        except Exception as ex: print("ERR", m, ex, flush=True)
    with gzip.open(fn + ".tmp", "wt", compresslevel=3) as f:
        for r in rows: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.rename(fn + ".tmp", fn)
    return run, b, len(rows)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    json.dump(FIELDS, open(f"{OUT}/FIELDS.json", "w"))
    keys = [(r, b) for r in RUNS for b in range(NB)]
    if len(sys.argv) > 1 and sys.argv[1] == "test": keys = keys[:2] + keys[NB:NB + 1]
    tot = 0; done = 0
    with Pool(int(os.environ.get("PROCS", "9")), initializer=init) as p:
        for run, b, nr in p.imap_unordered(work, keys):
            tot += max(nr, 0); done += 1
            if done % 32 == 0: print(f"{done}/{len(keys)} buckets, {tot} trips", flush=True)
    print("DONE trips", tot, flush=True)
