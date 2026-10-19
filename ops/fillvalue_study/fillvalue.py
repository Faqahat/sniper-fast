#!/usr/bin/env python3
"""Fill-quality VALUE study: PnL-vs-entry-timing curve for the pump.fun sniper.
Pure historical/paper replay. No live trading.

Method:
  - sample  = /root/profit_backtest/{creates,trajectories}.json (1,140 unbiased create_v2 launches,
              create-slot-anchored bonding-curve price paths; per-TRADE slots = finest granularity).
  - filter  = SHIPPED live filter: sized spendable dev_buy >= 2.0 SOL, creator_fee_bps == 0.
  - ladder  = SHIPPED exit ladder: derisk 0.30, ride 1.40, trail 0.92, cut 0.95, ladder 0.25, cap 40 slots (~9s).
  - for each passing launch, fill at the bonding-curve price at N slots past create, then replay the
    ladder on the subsequent price path (r = px/entry). Per-launch PnL in R (net fraction of size).
Reuses simulate()/stats() faithfully from profit_backtest/backtest.py.
"""
import sys, os, json, statistics as st
# match the report's fill assumptions (so floor is comparable to the backtest baseline)
os.environ.setdefault("SLIP", "0.08"); os.environ.setdefault("FEE_LEG", "0.0008")
os.environ.setdefault("SIZE", "2.0"); os.environ.setdefault("ENTRY_MULT", "1.0")
sys.path.insert(0, "/root/profit_backtest")
import backtest as B   # reuse simulate(), stats(), passes()

# SHIPPED exit ladder (current live config, per task)
EXIT = {"derisk_frac": 0.30, "ride_mult": 1.40, "trail_frac": 0.92,
        "cut_r": 0.95, "ladder_frac": 0.25, "cap_slots": 40}
DEV_MIN = 2.0

CRE = json.load(open("/root/profit_backtest/creates.json"))
TRAJ = {t["mint"]: t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
ROWS = []
for c in CRE:
    t = TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"):
        continue
    ROWS.append({**c, "traj": t})

def passes_shipped(c):
    # is_snipeable (creator_fee==0) + sized spendable dev_buy >= 2.0 SOL.
    if c["creator_fee_bps"] != 0:
        return False
    dev = c["dev_buy"]
    if c.get("dev_buy_wire", 0) >= 1e17:   # unbounded wire sentinel passes any threshold
        dev = max(dev, DEV_MIN)
    return dev >= DEV_MIN

SAMPLE = [c for c in ROWS if passes_shipped(c)]

def price_at(c, k):
    """Bonding-curve price at k slots past create: last trade with slot <= C+k, else the create-slot floor."""
    C = c["create_slot"]; px = c["traj"]["entry_px"]
    for slot, p in c["traj"]["series"]:
        if slot <= C + k:
            px = p
        else:
            break
    return px

def path_after(c, k):
    """Subsequent sell path = trades strictly after the entry slot C+k."""
    C = c["create_slot"]
    return [(s, p) for s, p in c["traj"]["series"] if s > C + k]

def observed_late(c):
    """Paper-trade proxy: the first price VISIBLE ~1 slot late via the RPC `processed` stream.
    = price of the first trade landing at slot >= C+1 (what you first see once your view is ~1 slot old).
    Returns (entry_px, entry_slot, subsequent_path)."""
    C = c["create_slot"]
    for s, p in c["traj"]["series"]:
        if s >= C + 1:
            return p, s, [(s2, p2) for s2, p2 in c["traj"]["series"] if s2 > s]
    # no trade after the create slot -> nothing visible late; fall back to the floor, nothing to sell into
    return c["traj"]["entry_px"], C + 1, []

def pnl_floor(c):
    # best case, same-block-first: fill the dev-buy floor, full create-slot+after path (== backtest floor).
    t = c["traj"]
    net, _, _ = B.simulate(t["entry_px"], t["create_slot"],
                           [(s, p) for s, p in t["series"]], EXIT)
    return net

def pnl_offset(c, k):
    e = price_at(c, k)
    net, _, _ = B.simulate(e, c["create_slot"] + k, path_after(c, k), EXIT)
    return net

def pnl_observed(c):
    e, slot, path = observed_late(c)
    net, _, _ = B.simulate(e, slot, path, EXIT)
    return net

# ---- build the curve ----
OFFSETS = [("floor", None), ("+1", 1), ("+2", 2), ("+3", 3), ("+5", 5), ("observed-late", "obs")]
curve = {}
per_launch = {label: [] for label, _ in OFFSETS}
for c in SAMPLE:
    for label, k in OFFSETS:
        if label == "floor":
            r = pnl_floor(c)
        elif label == "observed-late":
            r = pnl_observed(c)
        else:
            r = pnl_offset(c, k)
        per_launch[label].append(r)

for label, _ in OFFSETS:
    curve[label] = B.stats(per_launch[label])

def fmt(S):
    return (f"n={S['n']:3d}  win={S['win']*100:4.1f}%  mean={S['mean']:+.4f}  "
            f"med={S['median']:+.4f}  tot={S['tot']:+7.2f}  top5%share={S['top5_share']*100:5.1f}%")

print("=" * 96)
print("FILL-QUALITY VALUE STUDY  —  PnL vs entry-timing curve")
print(f"sample = {len(SAMPLE)} launches (shipped filter: dev_buy>=2.0 SOL, creator_fee==0)")
print(f"ladder = derisk .30 ride 1.40 trail .92 cut .95 ladder .25 cap 40 | SLIP={os.environ['SLIP']} FEE/leg={os.environ['FEE_LEG']} SIZE={os.environ['SIZE']}")
print("=" * 96)
hdr = f"{'offset':14s} {'n':>4s} {'win%':>6s} {'meanR':>9s} {'medR':>9s} {'totR':>9s} {'top5%share':>11s}  {'ΔvsFloor':>10s}"
print(hdr); print("-" * len(hdr))
floor_mean = curve["floor"]["mean"]
for label, _ in OFFSETS:
    S = curve[label]
    d = S["mean"] - floor_mean
    print(f"{label:14s} {S['n']:4d} {S['win']*100:6.1f} {S['mean']:+9.4f} {S['median']:+9.4f} "
          f"{S['tot']:+9.2f} {S['top5_share']*100:10.1f}% {d:+10.4f}")

# ---- cost per slot + breakeven (linear fit over floor,+1,+2,+3,+5 using slot index) ----
xs = [0, 1, 2, 3, 5]
ys = [curve["floor"]["mean"], curve["+1"]["mean"], curve["+2"]["mean"], curve["+3"]["mean"], curve["+5"]["mean"]]
n = len(xs); sx = sum(xs); sy = sum(ys); sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, ys))
slope = (n*sxy - sx*sy) / (n*sxx - sx*sx)
intercept = (sy - slope*sx) / n
be = (-intercept/slope) if slope != 0 else float("inf")
print("\n" + "-" * 60)
print(f"linear fit mean_R(slot) = {intercept:+.4f} {slope:+.4f}*slot")
print(f"cost per slot of latency : {slope:+.4f} R/slot  ({slope*float(os.environ['SIZE']):+.4f} SOL/slot @ size {os.environ['SIZE']})")
print(f"breakeven offset (meanR=0): {be:.2f} slots past create")
print(f"floor (ceiling) mean R    : {floor_mean:+.4f}")
print(f"observed-late mean R      : {curve['observed-late']['mean']:+.4f}")
print(f"FILL-QUALITY PRIZE (floor - observed-late): {floor_mean - curve['observed-late']['mean']:+.4f} R  "
      f"({(floor_mean - curve['observed-late']['mean'])*float(os.environ['SIZE']):+.4f} SOL/snipe @ size {os.environ['SIZE']})")

# per-offset step cost (consecutive)
print("\nstep cost (consecutive mean-R drop):")
seq = ["floor", "+1", "+2", "+3", "+5"]
for a, b in zip(seq[:-1], seq[1:]):
    print(f"  {a:>6s} -> {b:<6s}: {curve[b]['mean']-curve[a]['mean']:+.4f} R")

# ---- bonus: priority / co-sniper congestion effect (FLOOR replay, split by cosnipers_slot0) ----
print("\n" + "=" * 96)
print("BONUS: does being earlier within the slot (fewer co-snipers) correlate with better outcomes?")
print("(floor replay, split by # co-snipers in the create slot = create-slot congestion)")
print("=" * 96)
def split_stats(pred):
    idx = [i for i, c in enumerate(SAMPLE) if pred(c)]
    return B.stats([per_launch["floor"][i] for i in idx]), len(idx)
for name, pred in [("0 co-snipers", lambda c: c["traj"]["cosnipers"] == 0),
                   ("1-2 co-snipers", lambda c: 1 <= c["traj"]["cosnipers"] <= 2),
                   (">=3 co-snipers", lambda c: c["traj"]["cosnipers"] >= 3)]:
    S, k = split_stats(pred)
    if S:
        print(f"  {name:16s} n={S['n']:3d}  win={S['win']*100:4.1f}%  floor_meanR={S['mean']:+.4f}  medR={S['median']:+.4f}  totR={S['tot']:+.2f}")
    else:
        print(f"  {name:16s} n=0")
# also: for congested launches, how far above floor does +1 fill push (the realized within-slot cost)
cong = [c for c in SAMPLE if c["traj"]["cosnipers"] >= 1]
if cong:
    r1 = [price_at(c, 0) for c in cong]  # floor
    r2 = [price_at(c, 1)/c["traj"]["entry_px"] for c in cong]
    print(f"\n  on the {len(cong)} create-slot-congested launches: median +1-slot fill = {st.median(r2):.3f}x floor, mean = {sum(r2)/len(r2):.3f}x")

# ---- dump machine-readable curve ----
json.dump({"sample_n": len(SAMPLE), "exit": EXIT, "dev_min": DEV_MIN,
           "curve": {k: curve[k] for k in curve},
           "slope_R_per_slot": slope, "breakeven_slot": be,
           "floor_mean": floor_mean, "observed_late_mean": curve["observed-late"]["mean"],
           "prize_R": floor_mean - curve["observed-late"]["mean"]},
          open("/root/fillvalue_study/curve.json", "w"), indent=2)
print("\nwrote /root/fillvalue_study/curve.json")
