# What-if on RECORDED launches with OUR LANDING TIME as the input: our buy is recorded by the leader T ms after the
# create (the same feed-time metric the engine logs in RACE obs), so it lands after every trade that showed up in the
# feed before T ms (outside buys matched to the recording by wallet prefix + size) and before the rest. Price cap
# (--slip-cap-bps) checked at that spot: refused = the priority fee is lost, nothing else. Filled = constant-product
# replay of every later trade with our buy inserted (others' SOL in / tokens out held fixed), sell ALL at the end of
# slot S+k. Costs: pump fee per side, priority fee (always), tips (only when filled), sell tx fee.
# usage: python3 sim_land.py <rec dir> <engine log with RACE obs> [T list ms=15,25,35,50,75,110] [size=1.5]
#        env: PRIO=0.011 TIPS=0.004 CAP_BPS=1500 SELL_FEE=0.0007 SET=fired|all (launch set) EXITS=1,2
import sys, os, re, json, glob, collections

REC, LOG = sys.argv[1], sys.argv[2]
TS = [float(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "15,25,35,50,75,110").split(",")]
SIZE = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5
PRIO = float(os.environ.get("PRIO", "0.011")); TIPS = float(os.environ.get("TIPS", "0.004"))
CAP = int(os.environ.get("CAP_BPS", "1500")); SELL_FEE = float(os.environ.get("SELL_FEE", "0.0007"))
EXITS = [int(x) for x in os.environ.get("EXITS", "1,2").split(",")]

outs = {}
for line in open(LOG, errors="replace"):
    if "RACE obs" not in line: continue
    m = re.search(r"slot=(\d+) mint=(\w+) .* outs=(\S*)", line)
    if not m: continue
    v = []
    for o in m.group(3).split(","):
        p = o.split(":")
        if len(p) >= 4:
            try: v.append((float(p[0]), float(p[1]), p[2], p[3]))
            except ValueError: pass
    outs[(int(m.group(1)), m.group(2))] = v


def pre(t):
    return (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])


def run(r, T):
    S, tr = r["S"], r["trades"]
    if not tr: return None
    fee = ((tr[0].get("fbps") or 0) + (tr[0].get("cbps") or 0)) / 1e4 or 0.0125
    ge = r["glued_end"]
    gl = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] < ge]
    pbV, pbT = (gl[-1]["vsol"], gl[-1]["vtok"]) if gl else pre(tr[0])
    # anchors: outside trades in S that our feed saw, with their feed time
    ob = outs.get((S, r["mint"]), [])
    E = ge - 1      # our buy goes after every trade with idx <= E (E = last glued index by default)
    for ms, sol, flag, w6 in ob:
        if ms > T or flag != "1": continue
        cand = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["user"].startswith(w6) and abs(t["sol"] / 1e9 - sol) <= max(0.02, 0.02 * sol)]
        if cand: E = max(E, min(c["idx"] for c in cand))
    seq = [t for t in tr if not (t["slot"] == S and t["idx"] is not None and t["idx"] <= E)]
    before = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] <= E]
    V, Tk = (before[-1]["vsol"], before[-1]["vtok"]) if before else (pbV, pbT)
    x = SIZE * 1e9 / (1 + fee)
    q_pb = pbT * x / (pbV + x)
    q = Tk * x / (V + x)
    at_px = (V / Tk) / (pbV / pbT)
    if q < q_pb * (1 - CAP / 1e4):
        return dict(refused=True, at_px=at_px, pnl={k: -PRIO for k in EXITS})
    V += x; Tk -= q
    after_buy = (V, Tk)      # the state right after our buy: the exit price when nothing trades before the exit slot
    endst = {}
    for t in seq:
        if t["buy"]: d = Tk * t["sol"] / (V + t["sol"]); V += t["sol"]; Tk -= d
        else: so = V * t["tok"] / (Tk + t["tok"]); V -= so; Tk += t["tok"]
        endst[t["slot"]] = (V, Tk)
    res = {}
    for k in EXITS:
        st = None
        for s in range(S + k, S - 1, -1):
            if s in endst: st = endst[s]; break
        Vk, Tkk = st if st else after_buy
        res[k] = Vk * q / (Tkk + q) * (1 - fee) / 1e9 - SIZE - PRIO - TIPS - SELL_FEE
    return dict(refused=False, at_px=at_px, pnl=res)


L = []
for f in sorted(glob.glob(os.path.join(REC, "*.json"))):
    if f.endswith("_index.json"): continue
    r = json.load(open(f))
    if (r["S"], r["mint"]) not in outs: continue
    L.append(r)
SETS = {
    "rule2 (fired)": lambda r: r["fired"],
    "rule2 + bundle 2-10": lambda r: r["fired"] or ("race reject" in str(r["engine"]) and 2 <= r["gsol"] <= 10),
    "near leaders 5-8 ms": lambda r: (not r["fired"]) and "far leader" in str(r["engine"]) and (r.get("leader_rtt") or 999) <= 8 and 3 <= r["gsol"] <= 5 and r["rule2_largest"],
    "lunar-not-largest": lambda r: "static reject" in str(r["engine"]) and 3 <= r["gsol"] <= 5,
}
print(f"launches with feed timelines: {len(L)}; size {SIZE} SOL, prio {PRIO}, tips {TIPS} (filled only), cap {CAP / 100:.0f}%, exits {EXITS}")
for name, sel in SETS.items():
    rs = [r for r in L if sel(r)]
    if not rs: continue
    print(f"\n== {name}: {len(rs)} launches")
    print(f"   {'land T ms':>9} {'filled':>6} {'refused':>7} " + " ".join(f"{'PnL S+%d' % k:>9}" for k in EXITS) + "   per-launch S+1")
    for T in TS:
        out = [run(r, T) for r in rs]; out = [o for o in out if o]
        filled = [o for o in out if not o["refused"]]
        tot = {k: sum(o["pnl"][k] for o in out) for k in EXITS}
        print(f"   {T:9.0f} {len(filled):6} {len(out) - len(filled):7} " + " ".join(f"{tot[k]:+9.3f}" for k in EXITS) + "   "
              + " ".join(f"{o['pnl'][EXITS[0]]:+.2f}{'R' if o['refused'] else ''}" for o in out))
