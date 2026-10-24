#!/usr/bin/env python3
# EVIDENCE CARDS (read-only): one text card + one feature JSON per selected consistent winner (s2_rank.py winners.json).
# Entry-trigger profile vs BASE RATES (all clean trips of all wallets), exit profile, speed, fees/tips, hours (PKT),
# and ~10 example trips with the tape around entry and exit (phase-A trade rows).
# -> /home/moiz/sniper-data/strategies/cards/{wallet}.txt, cards.json, base.json
import sys, os, json, gzip, glob, collections, statistics, random, zlib
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s1_trips as S1
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/strategies"; CD = f"{OUT}/cards"
F = json.load(open(f"{OUT}/trips/FIELDS.json")); X = {k: i for i, k in enumerate(F)}
NSEL = int(os.environ.get("NSEL", "300"))
SLOT = 0.212
PKT = 5 * 3600

def g(r, k): return r[X[k]]
# ------------------------------------------------------------------ binary features (entry / exit)
EF = {
 "sell>=0.5 same slot before":   lambda r: g(r, "bs_gap") == 0 and g(r, "bs_sol") >= 0.5,
 "sell>=1 same slot before":     lambda r: g(r, "bs_gap") == 0 and g(r, "bs_sol") >= 1.0,
 "sell>=0.5 in prev 1-3 slots":  lambda r: 1 <= g(r, "bs_gap") <= 3 and g(r, "bs_sol") >= 0.5,
 "dip>=5% from 3-slot high":     lambda r: g(r, "dd3") >= 0.05,
 "dip>=10% from 3-slot high":    lambda r: g(r, "dd3") >= 0.10,
 "buy>=0.5 same slot before":    lambda r: g(r, "bb_gap") == 0 and g(r, "bb_sol") >= 0.5,
 "buy>=1 same slot before":      lambda r: g(r, "bb_gap") == 0 and g(r, "bb_sol") >= 1.0,
 "buy>=0.5 in prev 1-3 slots":   lambda r: 1 <= g(r, "bb_gap") <= 3 and g(r, "bb_sol") >= 0.5,
 "price +10% in last 10 slots":  lambda r: g(r, "ret10") >= 0.10,
 "price +30% in last 10 slots":  lambda r: g(r, "ret10") >= 0.30,
 "price -10% in last 10 slots":  lambda r: g(r, "ret10") <= -0.10,
 "net flow >=+1 SOL (3 slots)":  lambda r: g(r, "flow3") >= 1.0,
 "net flow <=-1 SOL (3 slots)":  lambda r: g(r, "flow3") <= -1.0,
 "token age <=3 slots":          lambda r: g(r, "age") <= 3,
 "token age <=25 slots (5 s)":   lambda r: g(r, "age") <= 25,
 "token age >300 slots (64 s)":  lambda r: g(r, "age") > 300,
 "token age >1500 slots (5 min)": lambda r: g(r, "age") > 1500,
 "creator sold in window":       lambda r: g(r, "dev_s") > 0,
 "creator bought in window":     lambda r: g(r, "dev_b") > 0,
 "quiet >=20 slots before":      lambda r: g(r, "quiet") >= 20,
 "quiet >=150 slots before":     lambda r: g(r, "quiet") >= 150,
 "prev trade = BUY same slot":   lambda r: g(r, "pv_side") == "B" and g(r, "pv_gap") == 0,
 "prev trade = SELL same slot":  lambda r: g(r, "pv_side") == "S" and g(r, "pv_gap") == 0,
 "prev trade in SAME tx":        lambda r: g(r, "pv_sametx") == 1,
 "<=10 trades before entry":     lambda r: g(r, "ntr") <= 10,
 "curve SOL <35":                lambda r: g(r, "vsol") < 35,
 "curve SOL 35-50":              lambda r: 35 <= g(r, "vsol") < 50,
 "curve SOL 50-70":              lambda r: 50 <= g(r, "vsol") < 70,
 "curve SOL 70-90":              lambda r: 70 <= g(r, "vsol") < 90,
 "curve SOL >=90 (near grad)":   lambda r: g(r, "vsol") >= 90,
 "price >=95% of ATH":           lambda r: g(r, "ath_r") >= 0.95,
 "price <=70% of ATH":           lambda r: g(r, "ath_r") <= 0.70,
 "mayhem launch":                lambda r: g(r, "may") == 1,
 "fee payer != wallet":          lambda r: g(r, "pay_ne") == 1,
 "jito-style tip on entry":      lambda r: (g(r, "tip0") or 0) > 0,
}
XF = {
 "sold right after a BUY (same slot)": lambda r: g(r, "x_pv_side") == "B" and g(r, "x_pv_gap") == 0,
 "buy>=0.5 by others within 2 slots before exit": lambda r: g(r, "x_bb_sol") >= 0.5,
 "sell>=0.5 by others within 2 slots before exit": lambda r: g(r, "x_bs_sol") >= 0.5,
 "creator sold shortly before exit": lambda r: g(r, "x_dev") == 1,
 "single sell": lambda r: g(r, "ns") == 1,
 ">=3 sells (ladder)": lambda r: g(r, "ns") >= 3,
 "scaled in (>=2 buys)": lambda r: g(r, "nb") >= 2,
 "exit below entry price": lambda r: 0 < g(r, "x_mult") < 1.0,
}
def pct(xs, ps=(10, 25, 50, 75, 90)):
    xs = sorted(xs)
    if not xs: return [None] * len(ps)
    return [xs[min(len(xs) - 1, int(p / 100 * len(xs)))] for p in ps]

def profile(rs):
    n = len(rs); out = {}
    for k, f in EF.items(): out["E:" + k] = sum(1 for r in rs if f(r)) / n
    cl = [r for r in rs if g(r, "st") == "C"]
    for k, f in XF.items(): out["X:" + k] = (sum(1 for r in cl if f(r)) / len(cl)) if cl else 0
    return out

def load_all():
    rows = []
    for f in sorted(glob.glob(f"{OUT}/trips/*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r[X["cslot"]] or r[X["ins"]] or r[X["st"]] == "G": continue
            rows.append(r)
    return rows

# ------------------------------------------------------------------ tapes for example trips
def tape_work(key):
    run, b, mints = key
    L = {}
    tra = S1.read(run, b, set(mints))
    return {(run, m): tr for m, tr in tra.items()}

def fmt_tape(tr, k0, kx, U, s0, n_before=6, n_exit=5):
    def px(k):
        t = tr[k]; pre = S1.pre_state(t)
        p0 = pre[0] / pre[1] if pre[1] else 0; p1 = t[13] / t[14] if t[14] else 0
        return (p1 / p0 - 1) * 100 if p0 else 0
    def line(k):
        t = tr[k]; who = "THIS WALLET" if t[9] == U else f"other {t[9][:6]}"
        return f"  slot{t[0] - s0:+d} idx{t[1]:>4} {'BUY ' if t[10] else 'SELL'} {t[11] / 1e9:7.3f} SOL  {who:<16} price {px(k):+6.1f}%  curve {t[13] / 1e9:6.1f} SOL"
    out = ["  -- before entry --"]
    for k in range(max(0, k0 - n_before), k0): out.append(line(k))
    own = [k for k in range(k0, (kx if kx is not None else len(tr) - 1) + 1) if tr[k][9] == U]
    out.append("  -- entry and the wallet's own trades in this trip --")
    for k in own[:6]: out.append(line(k))
    if kx is not None and kx - k0 > 1:
        out.append("  -- right before its exit --")
        for k in range(max(k0 + 1, kx - n_exit), kx + 1): out.append(line(k))
    return out

def card(a, rs, base, tapes):
    U = a["u"]; n = len(rs); P = profile(rs)
    cl = [r for r in rs if g(r, "st") == "C"]
    pn = [g(r, "pnl") for r in rs]
    sp = [g(r, "spent") for r in rs]
    hold = [g(r, "hold") for r in cl if g(r, "hold") is not None and g(r, "hold") >= 0]
    xm = [g(r, "x_mult") for r in cl if g(r, "x_mult")]
    xp = [g(r, "x_peak") for r in cl if g(r, "x_peak")]
    age = [g(r, "age") for r in rs]
    hrs = collections.Counter(); hp = collections.defaultdict(float)
    for r in rs:
        h = ((g(r, "bt") + PKT) // 3600) % 24; hrs[h // 3] += 1; hp[h // 3] += g(r, "pnl")
    L = []
    L.append(f"WALLET {U}")
    L.append(f"Round trips (bonding curve, last ~46 h, insider/create-slot trips removed): {n}  (R2 day 1: {a['n_R2']}, R3 day 2: {a['n_R3']})")
    L.append(f"Realized P&L: {a['pnl']:+.2f} SOL (day1 {a['pnl_R2']:+.2f}, day2 {a['pnl_R3']:+.2f}); closed trips {a['pnl_closed']:+.2f}; positive 6-h blocks {a['blk_pos']}/{a['blk_act']}")
    L.append(f"Win rate {a['win']:.0%}; P&L per SOL traded {a['edge']:+.2%}; mean/trip {statistics.mean(pn):+.4f} SOL, median {statistics.median(pn):+.4f}; P&L without its best 5 trips {a['pnl_wo_top5']:+.2f}")
    L.append(f"Size (SOL spent per trip) p10/p25/p50/p75/p90: {pct(sp)}; first-buy SOL median {statistics.median(g(r, 'b1') for r in rs):.3f}")
    L.append(f"Distinct tokens: {len(set(r[1] for r in rs))}; open at end {a['open_share']:.0%}; mayhem launches {a['may_share']:.0%}")
    L.append(f"Hold (slots, 1 slot = 0.212 s) p10/p25/p50/p75/p90: {pct(hold)}  -> seconds median {statistics.median(hold) * SLOT if hold else None:.1f}")
    L.append(f"Token age at entry (slots) p10/p25/p50/p75/p90: {pct(age)}")
    L.append(f"Curve SOL at entry p10/p50/p90: {pct([g(r, 'vsol') for r in rs], (10, 50, 90))}; price vs ATH at entry p10/p50/p90: {pct([g(r, 'ath_r') for r in rs], (10, 50, 90))}")
    L.append(f"Exit price / entry fill p10/p25/p50/p75/p90: {[round(x, 3) if x else x for x in pct(xm)]}; peak during hold / entry p50/p90: {[round(x, 3) if x else x for x in pct(xp, (50, 90))]}")
    L.append("ENTRY context (share of its entries vs base rate over all traders' entries; lift):")
    for k in EF:
        v = P["E:" + k]; b = base["E:" + k]
        L.append(f"  {k:<32} {v:6.1%}  base {b:6.1%}  x{(v / b) if b else 0:5.1f}")
    same_s = [g(r, "bs_di") for r in rs if g(r, "bs_gap") == 0 and g(r, "bs_sol") >= 0.5]
    same_b = [g(r, "bb_di") for r in rs if g(r, "bb_gap") == 0 and g(r, "bb_sol") >= 0.5]
    L.append(f"Speed: when a >=0.5 SOL sell was in the same slot before it, tx-index distance after that sell p25/p50/p75: {pct(same_s, (25, 50, 75))} (n {len(same_s)});"
             f" same for a >=0.5 SOL buy: {pct(same_b, (25, 50, 75))} (n {len(same_b)})")
    L.append(f"Block position of its entry tx (index in block) p25/p50/p75: {pct([g(r, 'i0') for r in rs], (25, 50, 75))}")
    lead = collections.Counter(g(r, "pv_u") for r in rs if g(r, "pv_side") == "B" and 0 <= g(r, "pv_gap") <= 1)
    leads = collections.Counter(g(r, "pv_u") for r in rs if g(r, "pv_side") == "S" and 0 <= g(r, "pv_gap") <= 1)
    L.append(f"Wallets whose BUY came right before its entry (<=1 slot), top: {[(w, c, f'{c / n:.0%}') for w, c in lead.most_common(4)]}")
    L.append(f"Wallets whose SELL came right before its entry (<=1 slot), top: {[(w, c, f'{c / n:.0%}') for w, c in leads.most_common(4)]}")
    L.append("EXIT context (closed trips):")
    for k in XF:
        v = P["X:" + k]; b = base["X:" + k]
        L.append(f"  {k:<48} {v:6.1%}  base {b:6.1%}")
    fees = [g(r, "fee0") or 0 for r in rs]; tips = [g(r, "tip0") or 0 for r in rs]; cus = [g(r, "cu0") or 0 for r in rs]
    tp = [t for t in tips if t > 0]
    L.append(f"Fees on entry tx: priority+base fee lamports p50/p90 {pct(fees, (50, 90))}; tip paid on {len(tp) / n:.0%} of entries, tip p50 {statistics.median(tp) if tp else 0} lamports;"
             f" compute used p50 {statistics.median(cus)}; fee payer differs from wallet on {P['E:fee payer != wallet']:.0%}")
    L.append(f"Exit tx fees p50: {statistics.median([g(r, 'x_fee') or 0 for r in cl]) if cl else None}; exit tip p50 {statistics.median([g(r, 'x_tip') or 0 for r in cl]) if cl else None}")
    L.append("Active hours PKT (3-h buckets: trips, P&L): " + ", ".join(f"{h * 3:02d}-{h * 3 + 3:02d}h {hrs[h]} {hp[h]:+.1f}" for h in range(8)))
    L.append("P&L by 6-h block (trips, SOL): " + ", ".join(f"{v[0]}:{v[1]:+.1f}" for k, v in a["blocks"].items()))
    # examples
    ex = tapes.get(U, [])
    L.append(f"EXAMPLE TRIPS ({len(ex)}): slot offsets relative to its entry slot; price = price change caused by that trade")
    for r, tl in ex:
        L.append(f"* token {r[1][:8]} age {g(r, 'age')} slots, spent {g(r, 'spent'):.3f}, got {g(r, 'got'):.3f}, P&L {g(r, 'pnl'):+.4f} SOL, hold {g(r, 'hold')} slots, buys {g(r, 'nb')} sells {g(r, 'ns')}, status {g(r, 'st')}")
        L += tl
    return "\n".join(L), P

def pick_examples(rs, rnd):
    cl = [r for r in rs if g(r, "st") == "C"]
    if not cl: return rs[:10]
    cl.sort(key=lambda r: g(r, "pnl"))
    wins = [r for r in cl if g(r, "pnl") > 0]; loss = [r for r in cl if g(r, "pnl") <= 0]
    ex = [cl[-1], cl[0]]
    ex += rnd.sample(wins, min(4, len(wins))) + rnd.sample(loss, min(3, len(loss)))
    rest = [r for r in cl if r not in ex]
    ex += rnd.sample(rest, min(1, len(rest)))
    seen = set(); out = []
    for r in ex:
        k = (r[1], r[4])
        if k not in seen: seen.add(k); out.append(r)
    return out[:10]

if __name__ == "__main__":
    os.makedirs(CD, exist_ok=True)
    win = json.load(open(f"{OUT}/winners.json"))[:NSEL]
    sel = {a["u"] for a in win}
    print("loading trips...", flush=True)
    allr = load_all()
    print("clean trips", len(allr), flush=True)
    base = profile(allr)
    json.dump(base, open(f"{OUT}/base.json", "w"), indent=0)
    byw = collections.defaultdict(list)
    for r in allr:
        if r[0] in sel: byw[r[0]].append(r)
    del allr
    rnd = random.Random(7)
    exs = {u: pick_examples(byw[u], rnd) for u in sel}
    need = collections.defaultdict(set)
    for u, ex in exs.items():
        for r in ex: need[(r[2], zlib.crc32(r[1].encode()) % 256)].add(r[1])
    print("example tapes to read", sum(len(v) for v in need.values()), flush=True)
    T = {}
    with Pool(9) as p:
        for d in p.imap_unordered(tape_work, [(run, b, sorted(ms)) for (run, b), ms in need.items()]): T.update(d)
    tapes = {}
    for u, ex in exs.items():
        out = []
        for r in ex:
            tr = T.get((r[2], r[1]))
            if not tr: continue
            k0 = next((k for k, t in enumerate(tr) if t[0] == g(r, "s0") and t[1] == g(r, "i0") and t[9] == u), None)
            if k0 is None: continue
            kx = None
            if g(r, "st") == "C" and g(r, "sx") is not None and g(r, "sx") >= 0:
                kk = [k for k, t in enumerate(tr) if k >= k0 and t[9] == u and not t[10] and t[0] == g(r, "sx")]
                kx = kk[-1] if kk else None
            out.append((r, fmt_tape(tr, k0, kx, u, g(r, "s0"))))
        tapes[u] = out
    cards = {}
    for a in win:
        u = a["u"]
        txt, P = card(a, byw[u], base, tapes)
        open(f"{CD}/{u}.txt", "w").write(txt)
        cards[u] = dict(a=a, P=P, chars=len(txt))
    json.dump(cards, open(f"{OUT}/cards.json", "w"))
    print("cards", len(cards), "avg chars", sum(c["chars"] for c in cards.values()) // max(1, len(cards)))
