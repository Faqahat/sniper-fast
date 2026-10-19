#!/usr/bin/env python3
"""Analyze PRE-CREATE features vs pump outcome. Joins precreate_raw.json + sample.json,
computes outcomes (max_mult, pump>=1.5x/2x, net R under winner-exit), derives
shared-funder / serial-launcher / market-density features, runs OOS chronological split,
his-vs-pop separation, and +EV pre-buy assessment. Writes precreate_feat.json + REPORT.md."""
import json, statistics as st
from collections import defaultdict

RAW = {r["mint"]: r for r in json.load(open("/root/precreate/precreate_raw.json")) if r}
SAMPLE = json.load(open("/root/precreate/sample.json"))
SPLIT_SLOT = 456742465   # same train/val split as profit_backtest

# ---------------- winner-exit simulate (port of backtest.simulate) ----------------
STEP_SLOTS = 4
WIN_EXIT = {"derisk_frac": 0.30, "ride_mult": 2.0, "trail_frac": 0.85, "cut_r": 0.80,
            "ladder_frac": 0.40, "cap_slots": 20}


def simulate(entry_px, entry_slot, series, P, SLIP, FEE_LEG, SIZE, ENTRY_MULT):
    remaining = 1.0
    amount = 1.0
    peak_r = 1.0
    riding = False
    first = True
    last_sell_slot = entry_slot
    sol_out = 0.0
    legs = 0

    def do_sell(frac, px):
        nonlocal sol_out
        sol_out += frac * (px / (entry_px * ENTRY_MULT)) * (1 - SLIP)

    polls = [(entry_slot, entry_px)] + [(s, p) for (s, p) in series]
    for (slot, px) in polls:
        if remaining <= amount * 1e-6:
            break
        r = px / entry_px
        if r > peak_r:
            peak_r = r
        if not riding and r >= P["ride_mult"]:
            riding = True
        age = slot - entry_slot
        if first:
            qty = amount * P["derisk_frac"]; final = False; first = False
        elif r <= P["cut_r"]:
            qty = remaining; final = True
        elif riding and r <= peak_r * P["trail_frac"]:
            qty = remaining; final = True
        elif age >= P["cap_slots"]:
            qty = remaining; final = True
        elif (not riding) and r < 1.0 and slot > last_sell_slot:
            qty = remaining; final = True
        elif (not riding) and 1.0 <= r < P["ride_mult"] and (slot - last_sell_slot) >= STEP_SLOTS:
            qty = remaining * P["ladder_frac"]; final = False
        else:
            qty = 0.0; final = False
        qty = min(qty, remaining)
        if qty > 0:
            do_sell(qty, px); remaining -= qty; last_sell_slot = slot; legs += 1
            if final or remaining <= amount * 1e-6:
                break
    if remaining > amount * 1e-6:
        lastpx = series[-1][1] if series else entry_px
        do_sell(remaining, lastpx); legs += 1
    gross = sol_out - 1.0
    fee_frac = (1 + legs) * FEE_LEG / SIZE
    return gross - fee_frac


FILLS = {
    "opt": dict(SLIP=0.08, FEE_LEG=0.0008, SIZE=2.0, ENTRY_MULT=1.0),
    "real": dict(SLIP=0.12, FEE_LEG=0.005, SIZE=2.0, ENTRY_MULT=1.05),
}

# ---------------- join + outcomes + derived features ----------------
# serial-launcher: count of launches per creator across the WHOLE sample window
creator_launches = defaultdict(int)
for s in SAMPLE:
    creator_launches[s["creator"]] += 1

# shared-funder fanout: distinct creators each fund_src funded (exclude None)
src_creators = defaultdict(set)
for s in SAMPLE:
    r = RAW.get(s["mint"])
    if r and r.get("fund_src"):
        src_creators[r["fund_src"]].add(s["creator"])
src_fanout = {k: len(v) for k, v in src_creators.items()}

# market density: population creates per preceding 300-slot window (unbiased feed only)
pop_slots = sorted(s["create_slot"] for s in SAMPLE if not s["is_his"])
import bisect
DENS_W = 300  # ~2 min


def density(slot):
    lo = bisect.bisect_left(pop_slots, slot - DENS_W)
    hi = bisect.bisect_left(pop_slots, slot)
    return hi - lo


ROWS = []
for s in SAMPLE:
    r = RAW.get(s["mint"])
    if not r:
        continue
    series = [(x[0], x[1]) for x in s["series"]]
    entry_px = s["entry_px"]
    max_mult = max((p / entry_px for (_sl, p) in series), default=1.0) if series else 1.0
    row = {
        "mint": s["mint"], "creator": s["creator"], "create_slot": s["create_slot"],
        "is_his": s["is_his"], "entry_px": entry_px, "n_poll": len(series),
        # outcomes
        "max_mult": max_mult, "pump15": int(max_mult >= 1.5), "pump20": int(max_mult >= 2.0),
        "netR_opt": simulate(entry_px, s["create_slot"], series, WIN_EXIT, **FILLS["opt"]) if series else None,
        "netR_real": simulate(entry_px, s["create_slot"], series, WIN_EXIT, **FILLS["real"]) if series else None,
        # create flags
        "dev_buy": s.get("dev_buy", 0.0), "creator_fee_bps": s.get("creator_fee_bps", 0),
        "mayhem": s.get("mayhem", 0), "holder_reward": s.get("holder_reward", 0),
        "cashback": s.get("cashback", 0), "cosnipers": s.get("cosnipers", 0),
        "vanilla": int(s.get("creator_fee_bps", 0) == 0 and not s.get("mayhem") and not s.get("holder_reward") and not s.get("cashback")),
        # pre-create features
        "fund_found": r.get("fund_found", False),
        "fund_recency_slots": r.get("fund_recency_slots"),
        "fund_amount": r.get("fund_amount"),
        "fund_src": r.get("fund_src"),
        "src_fanout": src_fanout.get(r.get("fund_src"), 0) if r.get("fund_src") else 0,
        "prior_n": r.get("prior_n"),
        "gap_since_last": r.get("gap_since_last"),
        "serial_launches": creator_launches[s["creator"]],
        "density": density(s["create_slot"]),
        "create_sig_found": r.get("create_sig_found", False),
    }
    ROWS.append(row)

json.dump(ROWS, open("/root/precreate/precreate_feat.json", "w"))

POP = [r for r in ROWS if not r["is_his"]]
HIS = [r for r in ROWS if r["is_his"]]
POP_S = [r for r in POP if r["n_poll"] > 0]   # pop with a price series (outcomes defined)
print("joined rows: %d  pop=%d (series %d)  his=%d" % (len(ROWS), len(POP), len(POP_S), len(HIS)))


# ---------------- helpers ----------------
def rate(rows, key):
    rows = [r for r in rows if r[key] is not None]
    return (sum(r[key] for r in rows) / len(rows)) if rows else float("nan")


def meanR(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    return (sum(v) / len(v)) if v else float("nan")


def band_table(rows, feat, bands, label):
    """bands: list of (name, predicate). Returns list of dicts."""
    out = []
    for name, pred in bands:
        sub = [r for r in rows if r.get(feat) is not None and pred(r.get(feat))]
        if not sub:
            out.append((name, 0, float("nan"), float("nan"), float("nan"), float("nan")))
            continue
        out.append((name, len(sub), rate(sub, "pump15"), rate(sub, "pump20"),
                    meanR(sub, "netR_opt"), meanR(sub, "netR_real")))
    return out


def fmt_table(title, rows_tbl):
    lines = ["  %-22s %5s %7s %7s %9s %9s" % ("band", "n", "p15%", "p20%", "netR_opt", "netR_real")]
    for (name, n, p15, p20, ro, rr) in rows_tbl:
        lines.append("  %-22s %5d %6.1f%% %6.1f%% %+9.4f %+9.4f" % (
            name, n, 100 * p15 if p15 == p15 else 0, 100 * p20 if p20 == p20 else 0,
            ro if ro == ro else 0, rr if rr == rr else 0))
    return title + "\n" + "\n".join(lines)


# ---------------- feature definitions (bands) ----------------
SLOTS_PER_MIN = 150

RECENCY_BANDS = [
    ("fresh <1min(<150)", lambda v: v < 150),
    ("1-5min(150-750)", lambda v: 150 <= v < 750),
    ("5-30min(750-4500)", lambda v: 750 <= v < 4500),
    ("30min-2h(4500-18k)", lambda v: 4500 <= v < 18000),
    (">2h(>=18k)", lambda v: v >= 18000),
]
AMOUNT_BANDS = [
    ("<0.5 SOL", lambda v: v < 0.5),
    ("0.5-1", lambda v: 0.5 <= v < 1),
    ("1-2", lambda v: 1 <= v < 2),
    ("2-5", lambda v: 2 <= v < 5),
    (">=5", lambda v: v >= 5),
]
FANOUT_BANDS = [
    ("solo src(1)", lambda v: v <= 1),
    ("shared 2", lambda v: v == 2),
    ("shared 3-4", lambda v: 3 <= v <= 4),
    ("shared >=5", lambda v: v >= 5),
]
PRIOR_BANDS = [
    ("cold <=2 tx", lambda v: v <= 2),
    ("3-20", lambda v: 3 <= v <= 20),
    ("21-200", lambda v: 21 <= v <= 200),
    (">200", lambda v: v > 200),
]
SERIAL_BANDS = [
    ("1 launch", lambda v: v == 1),
    ("2", lambda v: v == 2),
    ("3-5", lambda v: 3 <= v <= 5),
    (">5", lambda v: v > 5),
]
DENS_BANDS = [
    ("quiet <=1", lambda v: v <= 1),
    ("2-3", lambda v: 2 <= v <= 3),
    ("4-6", lambda v: 4 <= v <= 6),
    (">6 hot", lambda v: v > 6),
]

FEATS = [
    ("fund_recency_slots", RECENCY_BANDS, "CREATOR FUNDING RECENCY (slots before create; 150 slots~=1min)"),
    ("fund_amount", AMOUNT_BANDS, "CREATOR FUNDING AMOUNT (SOL of last inflow)"),
    ("src_fanout", FANOUT_BANDS, "SHARED-FUNDER FANOUT (# distinct creators the funding source funded)"),
    ("prior_n", PRIOR_BANDS, "CREATOR PRE-ACTIVITY (prior tx count in window)"),
    ("serial_launches", SERIAL_BANDS, "SERIAL LAUNCHER (# launches by creator in window)"),
    ("density", DENS_BANDS, "MARKET DENSITY (pop creates in preceding 300 slots)"),
]

report = []
report.append("# PRE-CREATE signal test\n")
report.append("Sample: %d launches joined with pre-create features. Population (unbiased feed) = %d "
              "(%d with a post-create price series -> defined pump outcome); his picks (sniper 4yFAz) = %d.\n"
              % (len(ROWS), len(POP), len(POP_S), len(HIS)))
report.append("Outcomes: pump15 = max price reached >=1.5x entry; pump20 >=2.0x. "
              "netR = net return fraction per snipe under the winner exit "
              "(derisk .30 ride 2.0 trail .85 cut .80 ladder .40 cap 20); "
              "opt fills = 8%% slip / .0008 SOL-leg / entry@floor; "
              "real fills = 12%% slip / .005 SOL-leg / entry 5%% above floor.\n")
report.append("Pre-create features are measured strictly from creator wallet history BEFORE the create slot "
              "(funding inflow, prior activity), so they are knowable at/just before the create.\n")

# baseline
base15 = rate(POP_S, "pump15"); base20 = rate(POP_S, "pump20")
baseRo = meanR(POP_S, "netR_opt"); baseRr = meanR(POP_S, "netR_real")
report.append("## Baseline (all population w/ series)\n  pump15=%.1f%% pump20=%.1f%% netR_opt=%+.4f netR_real=%+.4f  n=%d\n"
              % (100 * base15, 100 * base20, baseRo, baseRr, len(POP_S)))

# ---------------- A. population feature tables (FULL + OOS split) ----------------
report.append("## A. Pre-create feature -> pump outcome (unbiased population)\n")
feat_summary = {}
for feat, bands, desc in FEATS:
    rows_full = band_table(POP_S, feat, bands, desc)
    report.append(fmt_table("### " + desc + "  [FULL]", rows_full) + "\n")
    tr = [r for r in POP_S if r["create_slot"] < SPLIT_SLOT]
    va = [r for r in POP_S if r["create_slot"] >= SPLIT_SLOT]
    rows_tr = band_table(tr, feat, bands, desc)
    rows_va = band_table(va, feat, bands, desc)
    # OOS persistence: report train vs val pump15 per band
    oos = ["  %-22s  train p15=%5.1f%% (n%4d)   val p15=%5.1f%% (n%4d)" % (
        bt[0], 100 * bt[2] if bt[2] == bt[2] else 0, bt[1],
        100 * bv[2] if bv[2] == bv[2] else 0, bv[1]) for bt, bv in zip(rows_tr, rows_va)]
    report.append("  [OOS train(slot<%d) vs val]\n" % SPLIT_SLOT + "\n".join(oos) + "\n")
    feat_summary[feat] = {"full": rows_full, "train": rows_tr, "val": rows_va}

# ---------------- B. on the realistic snipeable (vanilla) subset ----------------
VAN = [r for r in POP_S if r["vanilla"]]
report.append("## B. Same, restricted to VANILLA snipeable population (n=%d) -- what we'd actually buy\n" % len(VAN))
for feat, bands, desc in [FEATS[0], FEATS[2], FEATS[4]]:
    report.append(fmt_table("### " + desc + "  [VANILLA pop]", band_table(VAN, feat, bands, desc)) + "\n")

# ---------------- C. his vs population separation ----------------
report.append("## C. His-picks vs population separation (is pre-create setup part of his selection?)\n")


def dist(rows, feat):
    v = sorted(r[feat] for r in rows if r.get(feat) is not None)
    if not v:
        return None
    n = len(v)
    return dict(n=n, med=v[n // 2], mean=sum(v) / n, p25=v[n // 4], p75=v[3 * n // 4])


for feat in ["fund_recency_slots", "fund_amount", "src_fanout", "prior_n", "serial_launches", "density"]:
    dp = dist(POP, feat); dh = dist(HIS, feat)
    if dp and dh:
        report.append("  %-20s POP med=%10.2f mean=%10.2f  |  HIS med=%10.2f mean=%10.2f" % (
            feat, dp["med"], dp["mean"], dh["med"], dh["mean"]))
# fraction fresh-funded / shared-funder in his vs pop
def frac(rows, pred, feat):
    rr = [r for r in rows if r.get(feat) is not None]
    return (sum(1 for r in rr if pred(r[feat])) / len(rr)) if rr else float("nan")

report.append("")
report.append("  fresh-funded(<1min)   POP=%.1f%%  HIS=%.1f%%" % (
    100 * frac(POP, lambda v: v < 150, "fund_recency_slots"), 100 * frac(HIS, lambda v: v < 150, "fund_recency_slots")))
report.append("  shared-funder(>=3)    POP=%.1f%%  HIS=%.1f%%" % (
    100 * frac(POP, lambda v: v >= 3, "src_fanout"), 100 * frac(HIS, lambda v: v >= 3, "src_fanout")))
report.append("  serial(>1 launch)     POP=%.1f%%  HIS=%.1f%%" % (
    100 * frac(POP, lambda v: v > 1, "serial_launches"), 100 * frac(HIS, lambda v: v > 1, "serial_launches")))
report.append("  cold creator(<=2 tx)  POP=%.1f%%  HIS=%.1f%%" % (
    100 * frac(POP, lambda v: v <= 2, "prior_n"), 100 * frac(HIS, lambda v: v <= 2, "prior_n")))
report.append("")

# coverage / knowability
cov = sum(1 for r in ROWS if r["create_sig_found"]) / len(ROWS)
fundcov = sum(1 for r in ROWS if r["fund_found"]) / len(ROWS)
report.append("## D. Coverage & knowability\n  create anchor found %.1f%%, funding inflow found %.1f%% of launches.\n"
              % (100 * cov, 100 * fundcov))

txt = "\n".join(report)
open("/root/precreate/REPORT_body.md", "w").write(txt)
print(txt)
