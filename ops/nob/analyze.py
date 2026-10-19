#!/usr/bin/env python3
# Analysis of ds.jsonl: his buys, bundles, no-bundle outcomes, feature scan, rules, time-split validation.
import json, math, collections, random, statistics as st, sys

D = "/root/nob/"
N_POP = 107544  # successful creates in the ledger window (mint-authority sigs)
rows = [json.loads(l) for l in open(D + "ds.jsonl")]
rand_all = [r for r in rows if r["in_rand"]]
F = len(rand_all) / N_POP
WN = 1 / F
P = print


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def fmt(x, n=2):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{n}f}"
    return str(x)


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


std = lambda r: (not r["quote"]) and r["v0_std"]
for r in rows:
    r["snipe"] = r["his"] and r.get("h_off") is not None and 0 <= r["h_off"] <= 1
    r["neg"] = r["in_rand"] and not r["his"]

P("=" * 100)
P(f"SAMPLE: rows={len(rows)}  random rows parsed={len(rand_all)} of {N_POP} creates  f={F:.4f} (weight {WN:.1f})")
P(f"his bought mints with a parsed create block: {sum(r['his'] for r in rows)}; snipes (offset 0/1): {sum(r['snipe'] for r in rows)}")
P(f"his mints that also fell in the random sample: {sum(1 for r in rows if r['his'] and r['in_rand'])}")

# ---------------------------------------------------------------- 1. his buys
P("\n" + "=" * 100 + "\n1. HIS BUYS")
H = [r for r in rows if r["his"]]
P("offset (buy slot - create slot):", sorted(collections.Counter(r["h_off"] for r in H).items())[:6])
P("quote (non-SOL) pools bought:", sum(r["quote"] for r in H), " mayhem:", sum(r["mayhem"] for r in H),
  " | random sample: quote %.1f%%  mayhem %.1f%%" % (100 * mean([r["quote"] for r in rand_all]), 100 * mean([r["mayhem"] for r in rand_all])))
P(f"SOL in per buy: p10 {fmt(q([r['h_sol'] for r in H], .1))} med {fmt(med([r['h_sol'] for r in H]))} p90 {fmt(q([r['h_sol'] for r in H], .9))}  total {sum(r['h_sol'] for r in H):.1f} SOL")
P(f"PnL (wallet SOL delta incl. fees/tips, + ATA rent refund): total {sum(r['h_pnl'] for r in H):+.2f} SOL; failed-tx fees attributed {sum(r['h_failfee'] for r in H):.2f} SOL; net {sum(r['h_pnl_net'] for r in H):+.2f}")
try:
    ua = json.load(open(D + "fail_unattrib.json"))
    P(f"unattributed failed txs: {ua['unattrib_fail_n']} costing {ua['unattrib_fail_fee_sol']:.2f} SOL (sprays on launches he never filled)")
except Exception:
    pass
P(f"hold: first sell after {fmt(med([r['h_first_sell_s'] for r in H]),1)} s median, last sell after {fmt(med([r['h_hold_s'] for r in H]),1)} s; unsold share med {fmt(med([r['h_unsold'] for r in H]),3)}")


def side_table(G, label):
    n = len(G)
    if not n:
        P(f"  {label}: n=0")
        return
    pn = [r["h_pnl"] for r in G]
    pnn = [r["h_pnl_net"] for r in G]
    rt = [r["h_ret"] for r in G if r["h_ret"] is not None]
    P(f"  {label:<28} n={n:4d}  fill p25/med/p75 {fmt(q([r['h_fill'] for r in G],.25),3)}/{fmt(med([r['h_fill'] for r in G]),3)}/{fmt(q([r['h_fill'] for r in G],.75),3)}"
      f"  pre-px med {fmt(med([r['h_pre'] for r in G]),3)}  size med {fmt(med([r['h_sol'] for r in G]))}"
      f"  PnL sum {sum(pn):+7.2f} (net of failed fees {sum(pnn):+7.2f})  mean/trade {sum(pn)/n:+.3f}  ret med {fmt(med(rt),3)} mean {fmt(mean(rt),3)}  win {100*sum(1 for x in pn if x>0)/n:.0f}%")


P("\nHis fill and PnL, no-bundle vs bundled (snipes only, standard SOL launches):")
HS = [r for r in rows if r["snipe"] and std(r)]
side_table([r for r in HS if r["nb"]], "NO-BUNDLE (glued<=0.3 SOL)")
side_table([r for r in HS if r["nb"] and r["glued"] == 0], "  of which no glued run")
side_table([r for r in HS if not r["nb"]], "BUNDLED (>0.3 SOL)")
for lo, hi in ((0.3, 2), (2, 5), (5, 1e9)):
    side_table([r for r in HS if not r["nb"] and lo < r["gsol"] <= hi], f"  bundle {lo}-{hi if hi<1e8 else 'inf'} SOL")
side_table([r for r in HS if r["h_off"] == 0], "offset 0 (same slot)")
side_table([r for r in HS if r["h_off"] == 1], "offset 1")
side_table([r for r in HS if r["h_off"] == 0 and r["nb"]], "offset 0 & no-bundle")
side_table([r for r in HS if r["h_off"] == 1 and r["nb"]], "offset 1 & no-bundle")
P("  SOL ahead of him in the create slot (offset-0 buys): " +
  str(sorted(collections.Counter(min(5, int(r.get('h_ahead_sol') or 0)) for r in HS if r['h_off'] == 0).items())))

# ---------------------------------------------------------------- 2. universe / bundles
P("\n" + "=" * 100 + "\n2. UNIVERSE AND CREATOR BUNDLES (random sample = population estimate)")
RS = [r for r in rand_all if std(r)]
P(f"random rows: {len(rand_all)}; standard SOL-quoted: {len(RS)} ({100*len(RS)/len(rand_all):.1f}%)")
nbR = [r for r in RS if r["nb"]]
P(f"  glued run present: {100*mean([r['glued']>0 for r in RS]):.1f}%   glued SOL > 0.3: {100*mean([not r['nb'] for r in RS]):.1f}%   no-bundle: {len(nbR)} ({100*len(nbR)/len(RS):.1f}%)")
P(f"  among creates with any same-slot buy: bundled share {100*mean([not r['nb'] for r in RS if r['glued']>0 or r['x_s_indep_buys']>0]):.1f}%")
B = [r for r in RS if not r["nb"]]
P(f"  bundled: glued SOL med {fmt(med([r['gsol'] for r in B]))}  price/floor after bundle med {fmt(med([r['bmult'] for r in B]),3)}  p75 {fmt(q([r['bmult'] for r in B],.75),3)}")
P(f"  his snipes: no-bundle {sum(r['nb'] for r in HS)} / {len(HS)} = {100*mean([r['nb'] for r in HS]):.1f}%  (population {100*len(nbR)/len(RS):.1f}%)")
P(f"  his snipes per day ~{len(HS)/4.4:.0f}; base rate in standard creates {len(HS)/(len(RS)*WN)*100:.2f}%; in no-bundle {sum(r['nb'] for r in HS)/(len(nbR)*WN)*100:.2f}%")

# ---------------------------------------------------------------- 3. outcomes on no-bundle
P("\n" + "=" * 100 + "\n3. NO-BUNDLE OUTCOMES (price/floor path first 60 s; entry 1.02x at create; TP +30% or time stop; 1.25%/side)")
NB = [r for r in rows if std(r) and r["nb"] and r.get("path_ok") and (r["snipe"] or r["neg"])]
P(f"no-bundle rows with path: his snipes {sum(r['snipe'] for r in NB)}, random others {sum(r['neg'] for r in NB)}")
keys = ["peak3", "peak10", "peak40", "px60", "ret_e102_tp130_3", "ret_e102_tp130_10", "ret_e102_tp130_40", "ret_e105_tp130_10"]


def outrow(G, label, adj=False):
    pre = "adj_" if adj else ""
    s = f"  {label:<34} n={len(G):4d} "
    for k in keys:
        v = [r.get(pre + k) for r in G]
        if k.startswith("ret"):
            s += f" {k[4:]}: mean {fmt(mean(v),3)} win {100*mean([x>0 for x in v if x is not None]) if v else 0:.0f}%"
        else:
            s += f" {k} med {fmt(med(v),2)} p75 {fmt(q(v,.75),2)}"
    P(s)


outrow([r for r in NB if r["neg"]], "random no-bundle (not his)")
outrow([r for r in NB if r["neg"] and (r.get('n_ok60') or 0) > 3], "  random nb with >3 ok txs in 60s")
outrow([r for r in NB if r["neg"] and not r["mayhem"]], "  random nb, not mayhem")
outrow([r for r in NB if r["neg"] and r["x_s_indep_buys"] >= 1], "  random nb, >=1 other indep buy in S")
outrow([r for r in NB if r["neg"] and r["x_s_indep_buys"] >= 3], "  random nb, >=3 other indep buys in S")
outrow([r for r in NB if r["neg"] and not r["mayhem"] and r["dev_sol"] >= 0.5], "  random nb, not mayhem, dev>=0.5")
outrow([r for r in NB if r["snipe"]], "his no-bundle snipes RAW path")
outrow([r for r in NB if r["snipe"]], "his no-bundle snipes HIS-ADJUSTED", adj=True)
pct = lambda xs: fmt(100 * mean(xs), 1) if xs else "-"
P("  runner (TP30 hit within 10 s at 1.02 entry) rate: random nb %s%% | his nb raw %s%% adj %s%%" % (
    pct([r["ret_e102_tp130_10"] > 0.2 for r in NB if r["neg"]]),
    pct([r["ret_e102_tp130_10"] > 0.2 for r in NB if r["snipe"]]),
    pct([r["adj_ret_e102_tp130_10"] > 0.2 for r in NB if r["snipe"]])))
P("  same, TP30 within 40 s: random nb %s%% | his nb raw %s%% adj %s%%" % (
    pct([r["ret_e102_tp130_40"] > 0.2 for r in NB if r["neg"]]),
    pct([r["ret_e102_tp130_40"] > 0.2 for r in NB if r["snipe"]]),
    pct([r["adj_ret_e102_tp130_40"] > 0.2 for r in NB if r["snipe"]])))

# ---------------------------------------------------------------- feature machinery
NUM = ["dev_sol", "cleft_sol", "dev_frac", "cu_price", "prio_sol", "ctip_sol", "nkeys", "cpre_sol", "cnv", "cnv_frac", "hour", "n_len", "s_len", "n_words",
       "desc_len", "tweet_age_s", "meta_nkeys", "n_socials", "cr_nprior", "cr_nprior_ok", "cr_age_h", "cr_idle_s", "cr_nlaunch",
       "cr_last_launch_h", "cr_prior_maxsig", "cr_prior_maxpx", "cr_fund_sol", "cr_funder_n", "nsig", "cu_limit", "cr_nfunders"]
CAT = ["uri_cid", "ins0", "mayhem", "tail_last", "client", "ctip", "ctip_label", "keytip", "progs", "payer_is_creator", "user_is_creator", "txver",
       "uri_host", "tw_kind", "tw_host", "web_host", "img_host", "created_on", "has_showname", "has_community", "meta_keys",
       "n_upper", "n_lower", "n_emoji", "n_digit", "n_nonascii", "n_punct", "s_upper", "s_lower", "s_emoji", "s_digit", "s_nonascii",
       "s_punct", "sym_in_name", "sym_eq_name", "mint_pump", "has_desc", "has_tw", "has_tg", "has_web", "img_named_mint",
       "img_other_mint", "cr_capped", "cr_prior_ran", "cr_funder_hub", "meta_ok", "desc_url", "meta_name_eq", "cr_age_censored", "t22"]
META_F = {"desc_len", "tweet_age_s", "meta_nkeys", "n_socials", "tw_kind", "tw_host", "web_host", "img_host", "created_on", "has_showname",
          "has_community", "meta_keys", "has_desc", "has_tw", "has_tg", "has_web", "img_named_mint", "img_other_mint", "meta_ok", "desc_url", "meta_name_eq"}


def val(r, k):
    v = r.get(k)
    if isinstance(v, bool):
        return int(v)
    return v


class Cond:
    def __init__(self, k, op, t):
        self.k, self.op, self.t = k, op, t

    def __call__(self, r):
        v = r.get(self.k)
        if self.op == "==":
            return v == self.t
        if self.op == "!=":
            return v != self.t
        if v is None:
            return self.op == "isnone"
        if self.op == "isnone":
            return False
        if self.op == ">=":
            return v >= self.t
        if self.op == "<":
            return v < self.t

    def __repr__(self):
        t = self.t
        if isinstance(t, float):
            t = f"{t:.4g}"
        return f"{self.k}{self.op}{t}" if self.op != "isnone" else f"{self.k} missing"


def stats_of(G, sel):
    pos = [r for r in G if r["snipe"]]
    neg = [r for r in G if r["neg"]]
    tp = sum(1 for r in pos if sel(r))
    fp = sum(1 for r in neg if sel(r))
    npos = len(pos)
    fpw = fp * WN
    prec = tp / (tp + fpw) if tp + fpw else 0
    base = npos / (npos + len(neg) * WN) if npos else 0
    rec = tp / npos if npos else 0
    return dict(tp=tp, fp=fp, npos=npos, nneg=len(neg), prec=prec, rec=rec, lift=prec / base if base else 0, base=base,
                sel_share=(tp + fpw) / (npos + len(neg) * WN) if npos + len(neg) else 0,
                prec_s=tp / (tp + (fp + 0.5) * WN) if tp else 0)


def ret_of(G, sel, k="adj_ret_e102_tp130_10"):
    num = den = 0
    wins = 0
    for r in G:
        if not sel(r) or r.get(k) is None:
            continue
        w = 1 if r["snipe"] else (WN if r["neg"] else 0)
        num += w * r[k]
        den += w
        wins += w * (r[k] > 0)
    return (num / den if den else None), (wins / den if den else None)


def gen_conds(G, exclude=()):
    cs = []
    neg = [r for r in G if r["neg"]]
    pos = [r for r in G if r["snipe"]]
    for k in NUM:
        if k in exclude:
            continue
        vs = sorted(set(round(x, 6) for x in (r.get(k) for r in neg + pos) if x is not None))
        if len(vs) < 2:
            continue
        qs = set()
        for src in (neg, pos):
            xs = sorted(x for x in (r.get(k) for r in src) if x is not None)
            if xs:
                for p in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
                    qs.add(xs[int(p * (len(xs) - 1))])
        for t in sorted(qs):
            cs.append(Cond(k, ">=", t))
            cs.append(Cond(k, "<", t))
        if any(r.get(k) is None for r in G):
            cs.append(Cond(k, "isnone", None))
    for k in CAT:
        if k in exclude:
            continue
        c1 = collections.Counter(r.get(k) for r in pos)
        c0 = collections.Counter(r.get(k) for r in neg)
        for v in set(c1) | set(c0):
            if c1[v] >= 3 or c0[v] >= 10:
                cs.append(Cond(k, "==", v))
                cs.append(Cond(k, "!=", v))
    return cs


def AND(cs):
    return lambda r: all(c(r) for c in cs)


def show(label, G, sel):
    s = stats_of(G, sel)
    rr, rw = ret_of([r for r in G if r.get("path_ok")], sel)
    return (f"{label:<62} his {s['tp']:3d}/{s['npos']:<3d} rec {100*s['rec']:5.1f}%  neg {s['fp']:4d}/{s['nneg']:<4d} "
            f"prec {100*s['prec']:5.2f}%  lift {s['lift']:5.1f}  sel {100*s['sel_share']:5.1f}%  adjX10 {fmt(rr,3)} win {fmt(100*rw if rw is not None else None,0)}%")


class MaskSet:
    """bitmask evaluation of conditions over a fixed row list (fast beam search)"""
    def __init__(self, G):
        self.G = G
        self.pos = sum(1 << i for i, r in enumerate(G) if r["snipe"])
        self.neg = sum(1 << i for i, r in enumerate(G) if r["neg"])
        self.npos = self.pos.bit_count()
        self.nneg = self.neg.bit_count()
        self.base = self.npos / (self.npos + self.nneg * WN) if self.npos else 0
        self.cache = {}

    def mask(self, c):
        k = repr(c)
        if k not in self.cache:
            self.cache[k] = sum(1 << i for i, r in enumerate(self.G) if c(r))
        return self.cache[k]

    def st(self, m):
        tp = (m & self.pos).bit_count()
        fp = (m & self.neg).bit_count()
        prec = tp / (tp + fp * WN) if tp + fp else 0
        return dict(tp=tp, fp=fp, rec=tp / self.npos if self.npos else 0, prec=prec,
                    prec_s=tp / (tp + (fp + 0.5) * WN) if tp else 0, lift=prec / self.base if self.base else 0)


def beam(G, cs, rec_min, depth=3, width=8):
    M = MaskSet(G)
    full = (1 << len(G)) - 1
    best = []
    frontier = [([], full)]
    cm = [(c, M.mask(c)) for c in cs]
    for d in range(depth):
        cand = []
        for path, pm in frontier:
            for c, m in cm:
                if any(c.k == p.k for p in path):
                    continue
                nm = pm & m
                s = M.st(nm)
                if s["rec"] < rec_min:
                    continue
                cand.append((s["prec_s"], path + [c], nm))
        cand.sort(key=lambda x: -x[0])
        seen = set()
        frontier = []
        for sc, pth, nm in cand:
            key = tuple(sorted(map(repr, pth)))
            if key in seen:
                continue
            seen.add(key)
            frontier.append((pth, nm))
            best.append((sc, pth))
            if len(frontier) >= width:
                break
    best.sort(key=lambda x: -x[0])
    return best


# ---------------------------------------------------------------- splits
EDGE = 457_470_000  # first ~2 h of the ledger: RPC refuses history lookups there (no creator/path data) -> excluded
NBall = [r for r in rows if std(r) and r["nb"] and (r["snipe"] or r["neg"]) and r["slot"] >= EDGE]
P(f"\n[analysis set] no-bundle standard launches after the ledger edge: his {sum(r['snipe'] for r in NBall)}, random others {sum(r['neg'] for r in NBall)}; "
  f"missing creator data {sum(1 for r in NBall if not r.get('cr_ok'))}, missing path {sum(1 for r in NBall if not r.get('path_ok'))}, missing metadata {sum(1 for r in NBall if not r.get('meta_ok'))}")
slots_neg = sorted(r["slot"] for r in NBall if r["neg"])
cut60 = slots_neg[int(0.6 * len(slots_neg))]
cut40 = slots_neg[int(0.4 * len(slots_neg))]
SPLITS = [("A: train first 60% -> test last 40%", [r for r in NBall if r["slot"] < cut60], [r for r in NBall if r["slot"] >= cut60]),
          ("B: train last 60% -> test first 40%", [r for r in NBall if r["slot"] >= cut40], [r for r in NBall if r["slot"] < cut40])]

P("\n" + "=" * 100 + "\n4. LABEL A (his no-bundle snipes) — base rates")
for nm, tr, te in SPLITS:
    a, b = stats_of(tr, lambda r: True), stats_of(te, lambda r: True)
    P(f"  split {nm}: train his {a['npos']} neg {a['nneg']} base {100*a['base']:.3f}% | test his {b['npos']} neg {b['nneg']} base {100*b['base']:.3f}%")

P("\n  Descriptive: his no-bundle snipes vs random no-bundle (all / non-mayhem). Numeric: p25/p50/p75")
HN = [r for r in NBall if r["snipe"]]
RN = [r for r in NBall if r["neg"]]
RNM = [r for r in RN if not r["mayhem"]]
for k in NUM:
    a = [q([r.get(k) for r in G], p) for G in (HN, RN, RNM) for p in (.25, .5, .75)]
    miss = [100 * mean([r.get(k) is None for r in G]) for G in (HN, RN, RNM)]
    P(f"    {k:<18} his {fmt(a[0],3)}/{fmt(a[1],3)}/{fmt(a[2],3)}  rand {fmt(a[3],3)}/{fmt(a[4],3)}/{fmt(a[5],3)}  rand-nonmayhem {fmt(a[6],3)}/{fmt(a[7],3)}/{fmt(a[8],3)}  missing% {miss[0]:.0f}/{miss[1]:.0f}/{miss[2]:.0f}")
for k in CAT:
    ch = collections.Counter(r.get(k) for r in HN)
    cr = collections.Counter(r.get(k) for r in RN)
    cm = collections.Counter(r.get(k) for r in RNM)
    top = [v for v, _ in (ch + cr).most_common(6)]
    P(f"    {k:<18} " + "  ".join(f"[{str(v)[:28]}] {100*ch[v]/len(HN):.0f}/{100*cr[v]/len(RN):.0f}/{100*cm[v]/max(1,len(RNM)):.0f}%" for v in top))


def eval_folds(label, sel):
    """full sample + 3 equal time folds (by random-sample slot terciles)"""
    t1, t2 = slots_neg[len(slots_neg) // 3], slots_neg[2 * len(slots_neg) // 3]
    folds = [[r for r in NBall if r["slot"] < t1], [r for r in NBall if t1 <= r["slot"] < t2], [r for r in NBall if r["slot"] >= t2]]
    s = stats_of(NBall, sel)
    rr, rw = ret_of([r for r in NBall if r.get("path_ok")], sel, "ret_e102_tp130_10")
    ra, _ = ret_of([r for r in NBall if r.get("path_ok")], sel, "adj_ret_e102_tp130_10")
    out = f"  {label:<58} ALL his {s['tp']}/{s['npos']} rec {100*s['rec']:.0f}% neg {s['fp']} prec {100*s['prec']:.2f}% lift {s['lift']:.1f} X10 {fmt(rr,3)} adjX10 {fmt(ra,3)} |"
    for G in folds:
        x = stats_of(G, sel)
        out += f" {x['tp']}/{x['npos']},{x['fp']},L{x['lift']:.1f}"
    P(out)


P("\n  Pre-specified simple rules (not fit). Folds = 3 time terciles: his_pass/his_total, random_neg_pass, Lift")
HAND = [("all no-bundle", lambda r: True),
        ("not mayhem", lambda r: not r["mayhem"]),
        ("not mayhem & dev>=0.5", lambda r: not r["mayhem"] and r["dev_sol"] >= 0.5),
        ("not mayhem & dev>=1.0", lambda r: not r["mayhem"] and r["dev_sol"] >= 1.0),
        ("not mayhem & dev>=2.0", lambda r: not r["mayhem"] and r["dev_sol"] >= 2.0),
        ("not mayhem & creator bal>=3", lambda r: not r["mayhem"] and r["cpre_sol"] >= 3),
        ("not mayhem & dev>=0.5 & bal>=2", lambda r: not r["mayhem"] and r["dev_sol"] >= 0.5 and r["cpre_sol"] >= 2),
        ("not mayhem & txver==0", lambda r: not r["mayhem"] and r["txver"] == "0"),
        ("not mayhem & progs==6EF8rr>AToken>6EF8rr", lambda r: not r["mayhem"] and r["progs"] == "6EF8rr>AToken>6EF8rr"),
        ("not mayhem & dev>=0.5 & no create tip", lambda r: not r["mayhem"] and r["dev_sol"] >= 0.5 and not r["ctip"]),
        ]
for lab, sel in HAND:
    eval_folds(lab, sel)

BEAMS = []
for excl_name, excl in (("ALL FEATURES", set()), ("NO METADATA-JSON FEATURES (on-chain + creator only)", META_F)):
    P("\n" + "=" * 100 + f"\n5. UNIVARIATE SCAN, label A, split A  [{excl_name}]")
    tr, te = SPLITS[0][1], SPLITS[0][2]
    trB, teB = SPLITS[1][1], SPLITS[1][2]
    cs = gen_conds(tr, excl)
    res = []
    Mtr = MaskSet(tr)
    for c in cs:
        s = Mtr.st(Mtr.mask(c))
        if s["rec"] < 0.15 or s["tp"] < 5:
            continue
        res.append((s["prec_s"], c, s))
    res.sort(key=lambda x: -x[0])
    P(f"  {len(cs)} candidate conditions; top 30 by smoothed train precision (rec>=15%); test stats + split-B test")
    shown = set()
    k = 0
    for sc, c, s in res:
        if c.k in shown and k > 10:
            continue
        shown.add(c.k)
        t = stats_of(te, c)
        tB = stats_of(teB, c)
        flag = ""
        if s["lift"] > 1.3 and t["lift"] < 1.0:
            flag = "  <-- FLIPS"
        elif s["lift"] > 1.3 and t["lift"] < 0.6 * s["lift"]:
            flag = "  <-- decays"
        P(f"  {repr(c):<44} TR rec {100*s['rec']:5.1f}% lift {s['lift']:5.2f} ({s['tp']}/{s['fp']}) | TE rec {100*t['rec']:5.1f}% lift {t['lift']:5.2f} ({t['tp']}/{t['fp']}) | B-TE lift {tB['lift']:5.2f}{flag}")
        k += 1
        if k >= 30:
            break

    P("\n" + "=" * 100 + f"\n6. RULES (beam search, <=3 conditions, fit on train only) [{excl_name}]")
    for nm, tr, te in SPLITS:
        cs = gen_conds(tr, excl)
        P(f"\n  --- split {nm}")
        for rmin in (0.8, 0.6, 0.4):
            bs = beam(tr, cs, rmin)
            if not bs:
                continue
            sc, pth = bs[0]
            sel = AND(pth)
            BEAMS.append((f"[{excl_name[:6]}|{nm[:1]}|r{int(rmin*100)}] " + " & ".join(map(repr, pth)), sel))
            P(f"  target recall {int(rmin*100)}%: " + " & ".join(map(repr, pth)))
            P("     " + show("TRAIN", tr, sel))
            P("     " + show("TEST", te, sel))

P("\n  Beam rules re-checked on 3 time terciles (his_pass/his_total, random_neg_pass, Lift):")
for lab, sel in BEAMS:
    eval_folds(lab[:58], sel)

# ---------------------------------------------------------------- logistic + tree checks
P("\n" + "=" * 100 + "\n7. MODEL CHECKS (logistic L2, depth-3 tree) — fit on train, ranked on test")


def design(G, ref):
    cats = {}
    for k in CAT:
        c = collections.Counter(r.get(k) for r in ref if r["snipe"]) + collections.Counter(r.get(k) for r in ref if r["neg"])
        cats[k] = [v for v, n in c.most_common(8) if n >= 8]
    cols = []
    for k in NUM:
        cols.append(("num", k))
        cols.append(("nan", k))
    for k in CAT:
        for v in cats[k]:
            cols.append(("cat", k, v))
    stats = {}
    for col in cols:
        if col[0] == "num":
            xs = [math.copysign(math.log1p(abs(r.get(col[1]))), r.get(col[1])) for r in ref if r.get(col[1]) is not None]
            m = sum(xs) / len(xs) if xs else 0
            sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 if xs else 1
            stats[col] = (m, sd or 1)

    def vec(r):
        v = []
        for col in cols:
            if col[0] == "num":
                x = r.get(col[1])
                if x is None:
                    v.append(0.0)
                else:
                    m, sd = stats[col]
                    v.append((math.copysign(math.log1p(abs(x)), x) - m) / sd)
            elif col[0] == "nan":
                v.append(1.0 if r.get(col[1]) is None else 0.0)
            else:
                v.append(1.0 if r.get(col[1]) == col[2] else 0.0)
        return v
    return cols, vec


def fit_logit(X, y, w, d, lam=0.02, it=300, lr=0.5):
    """X: list of sparse rows [(j, v)], weighted L2 logistic, plain gradient descent"""
    b = [0.0] * d
    b0 = 0.0
    W = sum(w)
    for _ in range(it):
        g = [0.0] * d
        g0 = 0.0
        for xi, yi, wi in zip(X, y, w):
            z = b0 + sum(b[j] * v for j, v in xi)
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = (p - yi) * wi
            g0 += e
            for j, v in xi:
                g[j] += e * v
        b0 -= lr * g0 / W
        for j in range(d):
            b[j] -= lr * (g[j] / W + lam * b[j])
    return b0, b


def prec_at_recall(G, score):
    pos = sorted((score(r) for r in G if r["snipe"]), reverse=True)
    out = []
    for rt in (0.8, 0.6, 0.4, 0.2):
        if not pos:
            continue
        k = max(1, int(math.ceil(rt * len(pos))))
        thr = pos[k - 1]
        s = stats_of(G, lambda r: score(r) >= thr)
        rr, rw = ret_of(G, lambda r: score(r) >= thr)
        out.append(f"rec {100*s['rec']:.0f}%: prec {100*s['prec']:.2f}% lift {s['lift']:.1f} (his {s['tp']}, neg {s['fp']}) X10 {fmt(rr,3)}")
    return out


for excl_name, excl in (("all features", set()), ("no metadata-JSON", META_F)):
    for nm, tr, te in SPLITS:
        cols, vec = design(tr, tr)
        cols_idx = [i for i, c in enumerate(cols) if c[1] not in excl]
        sp = lambda r: [(jj, v) for jj, v in enumerate(vec(r)[i] for i in cols_idx) if v]
        TR = [r for r in tr if r["snipe"] or r["neg"]]
        X = [sp(r) for r in TR]
        y = [1 if r["snipe"] else 0 for r in TR]
        npos = sum(y)
        w = [len(y) * (0.5 / npos if yi else 0.5 / (len(y) - npos)) for yi in y]
        b0, b = fit_logit(X, y, w, len(cols_idx))
        top = sorted(zip([cols[i] for i in cols_idx], b), key=lambda x: -abs(x[1]))[:14]
        scores = {}
        for r in tr + te:
            scores[id(r)] = b0 + sum(b[j] * v for j, v in sp(r))
        sc = lambda r: scores[id(r)]
        P(f"\n  logistic [{excl_name}] split {nm}")
        P("    top coefs: " + ", ".join(f"{('='.join(map(str,c[1:])))}:{v:+.2f}" for c, v in top))
        P("    TRAIN " + " | ".join(prec_at_recall(tr, sc)))
        P("    TEST  " + " | ".join(prec_at_recall(te, sc)))


# tiny CART
def tree_fit(G, cs, depth, minw=8):
    pos = [r for r in G if r["snipe"]]
    neg = [r for r in G if r["neg"]]
    if depth == 0 or len(pos) < 6:
        return None
    wp, wn = 1.0, (len(pos) / max(1, len(neg)))  # balanced

    def gini(a, b):
        t = a + b
        return 0 if t == 0 else 1 - (a / t) ** 2 - (b / t) ** 2
    best = None
    tot_p, tot_n = len(pos) * wp, len(neg) * wn
    for c in cs:
        a = sum(1 for r in pos if c(r)) * wp
        b = sum(1 for r in neg if c(r)) * wn
        if a + b < minw * wp or (tot_p - a) + (tot_n - b) < minw * wp:
            continue
        g = ((a + b) * gini(a, b) + (tot_p - a + tot_n - b) * gini(tot_p - a, tot_n - b)) / (tot_p + tot_n)
        if best is None or g < best[0]:
            best = (g, c)
    if best is None:
        return None
    c = best[1]
    L = [r for r in G if c(r)]
    R = [r for r in G if not c(r)]
    return (c, tree_fit(L, cs, depth - 1, minw), tree_fit(R, cs, depth - 1, minw))


def tree_leaves(t, path=()):
    if t is None:
        yield path
        return
    c, l, r = t
    yield from tree_leaves(l, path + ((c, True),))
    yield from tree_leaves(r, path + ((c, False),))


for nm, tr, te in SPLITS[:1]:
    cs = gen_conds(tr)
    t = tree_fit(tr, cs, 3)
    P(f"\n  depth-3 tree (balanced Gini) split {nm}; leaves ranked by train precision")
    leaves = []
    for path in tree_leaves(t):
        sel = (lambda pth: (lambda r: all(c(r) == want for c, want in pth)))(path)
        leaves.append((stats_of(tr, sel)["prec"], path, sel))
    leaves.sort(key=lambda x: -x[0])
    for p, path, sel in leaves:
        lab = " & ".join(("" if want else "NOT ") + repr(c) for c, want in path)
        P("    " + show("TR " + lab[:58], tr, sel))
        P("    " + show("TE " + lab[:58], te, sel))

# ---------------------------------------------------------------- label B
P("\n" + "=" * 100 + "\n8. LABEL B: rules for the realistic X10 return (entry 1.02x, TP +30% or 10 s; his own trades removed from the curve), no-bundle, fit on train")
NBp = [r for r in NBall if r.get("path_ok")]
trp = [r for r in NBp if r["slot"] < cut60]
tep = [r for r in NBp if r["slot"] >= cut60]
P("  population (weighted) X10 mean/win: train %s / test %s" % (ret_of(trp, lambda r: True), ret_of(tep, lambda r: True)))
P("  his snipes subset X10 mean/win (RAW path, includes his own buy): train %s test %s" % (
    ret_of([r for r in trp if r['snipe']], lambda r: True, 'ret_e102_tp130_10'), ret_of([r for r in tep if r['snipe']], lambda r: True, 'ret_e102_tp130_10')))
P("  his snipes subset adj-X10 mean/win (his own trades removed):     train %s test %s" % (
    ret_of([r for r in trp if r['snipe']], lambda r: True, 'adj_ret_e102_tp130_10'), ret_of([r for r in tep if r['snipe']], lambda r: True, 'adj_ret_e102_tp130_10')))


def ret_stats(G, sel, k="adj_ret_e102_tp130_10"):
    n_raw = sum(1 for r in G if sel(r) and r.get(k) is not None)
    m, w = ret_of(G, sel, k)
    return n_raw, m, w


for excl_name, excl in (("all", set()), ("no meta-JSON", META_F)):
    cs = gen_conds(trp, excl)
    res = []
    base_m, _ = ret_of(trp, lambda r: True)
    for c in cs:
        nr = sum(1 for r in trp if c(r) and r["neg"])
        if nr < 25:
            continue
        m, w = ret_of(trp, c)
        if m is None:
            continue
        res.append((m, c))
    res.sort(key=lambda x: -x[0])
    P(f"\n  [{excl_name}] top 20 single conditions by train mean X10 (>=25 random rows); test")
    for m, c in res[:20]:
        n1, m1, w1 = ret_stats(trp, c)
        n2, m2, w2 = ret_stats(tep, c)
        P(f"    {repr(c):<44} TR n={n1:4d} mean {fmt(m1,3)} win {fmt(100*w1,0)}% | TE n={n2:4d} mean {fmt(m2,3)} win {fmt(100*w2 if w2 is not None else None,0)}%")
    # 2-condition combos from top 40
    top = [c for _, c in res[:40]]
    combos = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            if top[i].k == top[j].k:
                continue
            sel = AND([top[i], top[j]])
            nr = sum(1 for r in trp if sel(r) and r["neg"])
            if nr < 20:
                continue
            m, w = ret_of(trp, sel)
            combos.append((m, [top[i], top[j]]))
    combos.sort(key=lambda x: -x[0])
    P(f"  [{excl_name}] top 8 two-condition combos by train mean X10 (>=20 random rows); test")
    for m, pth in combos[:8]:
        sel = AND(pth)
        n1, m1, w1 = ret_stats(trp, sel)
        n2, m2, w2 = ret_stats(tep, sel)
        P(f"    {' & '.join(map(repr,pth)):<70} TR n={n1:4d} mean {fmt(m1,3)} win {fmt(100*w1,0)}% | TE n={n2:4d} mean {fmt(m2,3)} win {fmt(100*w2 if w2 is not None else None,0)}%")
P("\n" + "=" * 100 + "\n9. RETURNS OF THE MAIN RULES (population-weighted, his own trades removed; split-A TEST period = last 40%)")
RK = [("X3", "adj_ret_e102_tp130_3"), ("X10", "adj_ret_e102_tp130_10"), ("X40", "adj_ret_e102_tp130_40"), ("X10@1.00", "adj_ret_e100_tp130_10"), ("X10@1.05", "adj_ret_e105_tp130_10")]
tep_all = [r for r in SPLITS[0][2] if r.get("path_ok")]
trp_all = [r for r in SPLITS[0][1] if r.get("path_ok")]
for lab, sel in HAND + BEAMS:
    out = f"  {lab[:58]:<58}"
    for G, nmG in ((trp_all, "TR"), (tep_all, "TE")):
        n_r = sum(1 for r in G if sel(r) and r["neg"])
        n_h = sum(1 for r in G if sel(r) and r["snipe"])
        out += f" | {nmG} rand {n_r:4d} his {n_h:3d}:"
        for nmk, k in RK:
            m, w = ret_of(G, sel, k)
            out += f" {nmk} {fmt(m,3)}"
        m, w = ret_of(G, sel, "adj_ret_e102_tp130_10")
        out += f" win {fmt(100*w if w is not None else None,0)}%"
    P(out)
P("  (rand = random non-his rows selected, weight %.1f each; his = his snipes selected, weight 1)" % WN)

P("\n  Inside each rule: his picks vs the other launches that pass the same rule (all periods, adj path).")
P("  If his picks still beat the rest, he selects beyond the rule (or attracts followers); if not, the rule captures his edge.")
ALLP = [r for r in NBall if r.get("path_ok")]
for lab, sel in HAND + BEAMS:
    hs = [r for r in ALLP if sel(r) and r["snipe"]]
    ns = [r for r in ALLP if sel(r) and r["neg"]]
    def mm(G, k):
        v = [r.get(k) for r in G if r.get(k) is not None]
        return (sum(v) / len(v)) if v else None
    P(f"  {lab[:58]:<58} his n={len(hs):3d} adjX10 {fmt(mm(hs,'adj_ret_e102_tp130_10'),3)} peak10 med {fmt(med([r['adj_peak10'] for r in hs]),2)} TP-hit10 {fmt(100*mean([r['adj_ret_e102_tp130_10']>0.2 for r in hs]) if hs else None,0)}%"
      f" | others n={len(ns):4d} X10 {fmt(mm(ns,'ret_e102_tp130_10'),3)} peak10 med {fmt(med([r['peak10'] for r in ns]),2)} TP-hit10 {fmt(100*mean([r['ret_e102_tp130_10']>0.2 for r in ns]) if ns else None,0)}%")
P("\n" + "=" * 100 + "\n10. LABEL A' = his FILLED snipes + launches he ATTEMPTED (failed buy txs) but never filled")
ATT = [r for r in NBall if r["neg"] and r.get("attempted")]
P(f"  attempted-not-filled launches in the random no-bundle sample: {len(ATT)} (pop. est. ~{len(ATT)*WN:.0f}) vs filled no-bundle snipes {sum(r['snipe'] for r in NBall)}")


def stats_A2(G, sel):
    tp = sum(1 for r in G if r["snipe"] and sel(r)) + WN * sum(1 for r in G if r["neg"] and r.get("attempted") and sel(r))
    Pw = sum(1 for r in G if r["snipe"]) + WN * sum(1 for r in G if r["neg"] and r.get("attempted"))
    fp = WN * sum(1 for r in G if r["neg"] and not r.get("attempted") and sel(r))
    Nw = WN * sum(1 for r in G if r["neg"] and not r.get("attempted"))
    prec = tp / (tp + fp) if tp + fp else 0
    base = Pw / (Pw + Nw) if Pw else 0
    na = sum(1 for r in G if r["neg"] and r.get("attempted") and sel(r))
    return f"rec {100*tp/Pw if Pw else 0:5.1f}% prec {100*prec:5.2f}% lift {prec/base if base else 0:4.1f} (att rows passing {na})"


for lab, sel in HAND + BEAMS:
    P(f"  {lab[:58]:<58} ALL {stats_A2(NBall, sel)} | A-test {stats_A2(SPLITS[0][2], sel)}")
P("\nDONE")
