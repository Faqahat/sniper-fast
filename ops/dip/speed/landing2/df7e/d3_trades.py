#!/usr/bin/env python3
# DF7eRXHn study, pass 3 (read-only, local). One row per buy attempt of the wallet (landed ok + landed failed) with:
#   trigger context on the same mint (prior trades), curve size, token age, position after the trigger, his size, the paired sell, P&L (curve SOL).
# Output: /home/moiz/sniper-data/landing2/df7e/buys.json
import sys, json, gzip, glob, collections, bisect
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
D = "/home/moiz/sniper-data/landing2/df7e"; W = "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"
BLK = {}
for f in sorted(glob.glob(f"{lib2.D}/x_r3/B_*") + glob.glob(f"{lib2.D}/x_r4/B_*")):
    for k, v in json.load(open(f)).items():
        s = int(k); b = BLK.get(s)
        if b is None: BLK[s] = list(v)
        else: b[0] = max(b[0], v[0]); b[1] += v[1]; b[2] = b[2] or v[2]
def n_of(s): b = BLK.get(s); return b[0] + 1 if b else 500
def ms(s, i): return lib2.tms(s, i, n_of(s))
def bt(s):
    for d in range(0, 50):
        b = BLK.get(s - d)
        if b and b[2]: return b[2]
    return None
TR = collections.defaultdict(list)       # mint -> trades [s, i, sig, signer0, user, mint, buy, sol, vsol, vtok, fee, cup, cul, cu, tip, svcs, nsig]
for l in gzip.open(f"{D}/T_mints.jsonl.gz", "rt"):
    r = json.loads(l); TR[r[5]].append(r)
for m in TR:
    _u = {}
    for r in TR[m]: _u.setdefault((r[2], r[6], r[7]), r)
    TR[m] = sorted(_u.values(), key=lambda r: (r[0], r[1]))
KEYS = {m: [(r[0], r[1]) for r in v] for m, v in TR.items()}
WR = list({r[2]: r for r in (json.loads(l) for l in open(f"{D}/W_df7e.jsonl"))}.values())   # dedupe (chunk overlap)
WR.sort(key=lambda r: (r[0], r[1]))
def kind(ixn): return "buy" if any(x.startswith("Buy") for x in ixn) else ("sell" if any(x.startswith("Sell") for x in ixn) else "other")
V0 = 30_000_000_000
rows = []
for s, i, sig, sg, err, fee, cup, cul, cu, mints, progs, ixn, tips, sdp in WR:
    if kind(ixn) != "buy": continue
    m = mints[0] if mints else None
    v = TR.get(m, []); ks = KEYS.get(m, [])
    j = bisect.bisect_left(ks, (s, i))
    prior = v[:j]
    me = v[j] if j < len(v) and v[j][2] == sig else None
    x = dict(s=s, i=i, sig=sig, ok=err is None, err=err, fee=fee, cup=cup, cul=cul, cu=cu, mint=m, route=lib2.route(tips, sdp),
             tip=sum(t[1] for t in tips) + sum(a[1] for a in sdp if a[0] in lib2.UNK), n=n_of(s), ms_abs=ms(s, i), bt=bt(s))
    x["sol"] = me[7] if me else None
    # curve before
    if prior:
        p = prior[-1]
        x["vsol_before"] = p[8]
    else:
        x["vsol_before"] = None
    # token age: first trade seen; created in window if first buy started at 30 SOL virtual
    if v:
        f0 = v[0]
        st0 = f0[8] - f0[7] if f0[6] == 1 else f0[8] + f0[7]
        x["created_in_window"] = abs(st0 - V0) < 5_000_000
        x["age_slots"] = s - f0[0]
        x["age_s"] = (bt(s) - bt(f0[0])) if (bt(s) and bt(f0[0])) else None
    x["n_prior"] = len(prior)
    # trigger window: prior trades in the last 3 slots (excluding his own)
    win = [p for p in prior if s - p[0] <= 3 and p[4] != W]
    sells = [p for p in win if p[6] == 0]
    buys = [p for p in win if p[6] == 1]
    if sells:
        big = max(sells, key=lambda p: p[7])
        vb = big[8] + big[7]
        x["dump"] = dict(sig=big[2], s=big[0], i=big[1], sol=big[7], drop=round(1 - (big[8] / vb) ** 2, 4), user=big[4],
                         ds=s - big[0], dpos=(i - big[1]) if s == big[0] else None, dms=round(ms(s, i) - ms(big[0], big[1]), 1))
        # trades between that sell and him
        x["dump"]["between"] = sum(1 for p in prior if (p[0], p[1]) > (big[0], big[1]))
        x["dump"]["between_buys"] = sum(1 for p in prior if (p[0], p[1]) > (big[0], big[1]) and p[6] == 1 and p[4] != W)
    else: x["dump"] = None
    x["win_buy_sol"] = sum(p[7] for p in buys); x["win_sell_sol"] = sum(p[7] for p in sells); x["win_n"] = len(win)
    # last trade before him
    if prior:
        p = prior[-1]; x["last"] = dict(buy=p[6], sol=p[7], ds=s - p[0], user=p[4], sig=p[2])
    # longer context: last 25 slots (~5 s) net flow, price change over 25 slots and 150 slots
    def vat(slot):
        k = bisect.bisect_left(ks, (slot, 0)) - 1
        return v[k][8] if k >= 0 else None
    for L in (5, 25, 150):
        a = vat(s - L); x[f"vsol_m{L}"] = a
    w25 = [p for p in prior if s - p[0] <= 25 and p[4] != W]
    x["flow25"] = sum(p[7] if p[6] else -p[7] for p in w25); x["n25"] = len(w25)
    x["peak_vsol"] = max((p[8] for p in prior), default=None)
    # his position in token: prior own buys on this mint
    x["own_prior_buys"] = sum(1 for p in prior if p[4] == W and p[6] == 1)
    rows.append(x)
# pair sells: per mint, his landed trades in order
pos = collections.defaultdict(list)
for m, v in TR.items():
    for r in v:
        if r[4] == W: pos[m].append(r)
SELLS = {}
for m, v in pos.items():
    held = []; 
    for r in v:
        if r[6] == 1: held.append(r)
        else:
            tot = sum(h[7] for h in held) or 1
            for h in held: SELLS.setdefault(h[2], []).append((r, h[7] / tot))
            held = []
for x in rows:
    ss0 = SELLS.get(x["sig"])
    ss = [a for a, _ in ss0] if ss0 else None
    if x["ok"] and ss:
        x["sell_share"] = [b for _, b in ss0]; x["group"] = round(1 / ss0[0][1]) if ss0[0][1] else None
        x["sell_sol"] = sum(r[7] * b for r, b in ss0); x["n_sells"] = len(ss)
        last = ss[-1]; first = ss[0]
        x["hold_slots"] = first[0] - x["s"]; x["hold_ms"] = round(ms(first[0], first[1]) - x["ms_abs"], 1)
        x["sell_sigs"] = [r[2] for r in ss]; x["sell_fee"] = sum(r[10] or 0 for r in ss); x["sell_tip"] = sum(r[14] or 0 for r in ss)
        # buys in the group (several buys before a sell)
        x["group_buys"] = None
        # path of price after entry: max/min vsol between buy and sell (others' trades)
        v = TR[x["mint"]]; ks = KEYS[x["mint"]]
        a = bisect.bisect_right(ks, (x["s"], x["i"])); b = bisect.bisect_left(ks, (first[0], first[1]))
        mid = [r for r in v[a:b] if r[4] != W]
        x["mid_n"] = len(mid); x["mid_buy_sol"] = sum(r[7] for r in mid if r[6]); x["mid_sell_sol"] = sum(r[7] for r in mid if not r[6])
        x["mid_max_vsol"] = max((r[8] for r in mid), default=None); x["mid_min_vsol"] = min((r[8] for r in mid), default=None)
        x["vsol_after_buy"] = TR[x["mint"]][a - 1][8] if a > 0 else None
        x["vsol_before_sell"] = v[b - 1][8] if b > 0 else None
json.dump(rows, open(f"{D}/buys.json", "w"))
print(len(rows), sum(1 for x in rows if x["ok"]), sum(1 for x in rows if x.get("sell_sol") is not None))
