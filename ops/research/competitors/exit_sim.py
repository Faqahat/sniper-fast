# READ-ONLY (host, no RPC): exit-policy test for OUR rule #2 trade on the realistic landing model, with the launch tape
# extended past S+2. Entry = filters.py run() unchanged (landing T by leader class after every outside buy our feed saw,
# glued bundle, late-create rule, 15% cap, 1.5 SOL, prio 0.011, tips by class, pump fee, sell tx 0.0007). Trades after
# the entry are replayed by amount (buys by SOL, sells by tokens) through S+NS using the exact-order recording for its
# window and tapes.py's tape for later slots (order inside a later slot follows the reserves chain).
# Policies (causal): FIXED end of S+k; TP/SL checked at the end of each slot from S+1, executed at the end of the NEXT slot
# (one slot of latency), with a time stop; LADDER = sell a first leg on a pop, the rest on a stop/time stop.
# usage: python3 -I exit_sim.py <filters3_rows.json> <tapes_dir> <launches2.json> <paper launches_ready.json> <rec_dir> [<rec_dir>...]
import sys, os, json, glob, statistics, collections
F3, TD, L2, LP = sys.argv[1:5]; RECS = sys.argv[5:]
SIZE, PRIO, CAP, SELL_FEE = float(os.environ.get("SIZE", "1.5")), float(os.environ.get("PRIO", "0.011")), 1500, float(os.environ.get("SELL_FEE", "0.0007"))
TIP_BY = {"bam": 0.015, "jito": 0.004, "harmonic": 0.001, "other": 0.004}
if os.environ.get("TIP"): TIP_BY = {k: float(os.environ["TIP"]) for k in TIP_BY}          # flat tip override (fee test)
REF_COST = float(os.environ.get("REF_COST", str(PRIO)))                                       # cost of a refused (failed) buy
OURS6 = ("FRZh63", "2g7rYv")
NS = int(os.environ.get("NS", "60"))
SEL = os.environ.get("SEL", "r2nc")
# landing-time override (ms after the create, feed clock): T_OVR="jito=75,harmonic=80" sets a class; T_ADD adds to the rest
T_OVR = {k: float(v) for k, v in (x.split("=") for x in os.environ.get("T_OVR", "").split(",") if x)}
T_ADD = float(os.environ.get("T_ADD", "0"))
rows = json.load(open(F3))["rows"]
OUTS = {}
for f in (L2, LP):
    for l in json.load(open(f))["launches"]:
        if l.get("obs"): OUTS.setdefault(l["mint"], l["obs"]["outs"])
REC = {}
for d in RECS:
    for f in glob.glob(os.path.join(d, "*.json")):
        try: r = json.load(open(f))
        except Exception: continue
        if not isinstance(r, dict) or "trades" not in r: continue
        if r["mint"] not in REC or (r.get("window_slots") or 0) > (REC[r["mint"]].get("window_slots") or 0): REC[r["mint"]] = r


def pre(t):
    return (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])


def clean(r):
    tr = r["trades"]
    if not any(t["user"].startswith(OURS6) for t in tr): return r
    V, Tk = pre(tr[0]); new = []
    for t in tr:
        if t["user"].startswith(OURS6): continue
        t = dict(t)
        if t["buy"]: d = Tk * t["sol"] / (V + t["sol"]); V += t["sol"]; Tk -= d; t["tok"] = d
        else: so = V * t["tok"] / (Tk + t["tok"]); V -= so; Tk += t["tok"]; t["sol"] = so
        t["vsol"], t["vtok"] = V, Tk; new.append(t)
    r = dict(r); r["trades"] = new
    return r


BREAKS = collections.Counter()


def chain_order(evs, V0, mint=None):
    """order one slot's events by the reserves chain (each event's pre-state = previous post-state); fallback: as given.
    A fallback means an event of the mint is missing from the tape (counted in BREAKS)."""
    left = list(evs); out = []; V = V0
    while left:
        nx = [e for e in left if V is not None and abs(pre(e)[0] - V) <= 2]
        if not nx and mint: BREAKS[mint] += 1
        e = nx[0] if nx else left[0]
        out.append(e); left.remove(e); V = e["vsol"]
    return out


def extend(rec, tape):
    """recording trades (exact order, window W) + tape events for slots > S+W, as one list with slot/idx"""
    S = rec["S"]; W = rec.get("window_slots") or 2
    tr = sorted([dict(t) for t in rec["trades"]], key=lambda t: (t["slot"], t["idx"] if t["idx"] is not None else 10 ** 9))
    if not tape: return tr, S + W
    last = tr[-1]["vsol"] if tr else None
    by = collections.defaultdict(list)
    for row in tape["rows"]:
        if row["slot"] <= S + W: continue
        for e in row["ev"]:
            by[row["slot"]].append(dict(mint=e["mint"], sol=e["sol"], tok=e["tok"], buy=e["buy"], user=e["user"], vsol=e["vsol"], vtok=e["vtok"],
                                        slot=row["slot"], idx=None, payer=row["payer"]))
    for s in sorted(by):
        evs = chain_order(by[s], last, rec["mint"])
        for i, e in enumerate(evs): e["idx"] = 10 ** 6 + i
        tr += evs; last = evs[-1]["vsol"]
    return tr, S + NS


def entry(r, tr, outs, T):
    """filters.py run() entry: returns (V, Tk after our buy, q tokens, index of first later trade, at_px) or refused"""
    S = r["S"]; ge = r["glued_end"]
    fee = ((tr[0].get("fbps") or 0) + (tr[0].get("cbps") or 0)) / 1e4 or 0.0125
    gl = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] < ge]
    pbV, pbT = (gl[-1]["vsol"], gl[-1]["vtok"]) if gl else pre(tr[0])
    key = lambda t: (t["slot"], t["idx"] if t["idx"] is not None else 10 ** 9)
    E = (S, ge - 1)
    cm = r.get("create_ms")
    late = cm is not None and cm + T > r.get("slot_ms", 217.4)
    if late: E = max(E, (S, max([t["idx"] for t in tr if t["slot"] == S and t["idx"] is not None] or [ge - 1])))
    for ms, sol, flag, w6 in outs:
        if ms > T or flag != "1" or w6.startswith(OURS6): continue
        mine = [t for t in tr if t["slot"] in (S, S + 1) and t["idx"] is not None and t["buy"] and (t["user"].startswith(w6) or t.get("payer", "").startswith(w6))]
        cand = [t for t in mine if abs(t["sol"] / 1e9 - sol) <= max(0.02, 0.02 * sol)] or mine
        if cand: E = max(E, min(key(c) for c in cand))
    before = [t for t in tr if key(t) <= E]; seq = [t for t in tr if key(t) > E]
    V, Tk = (before[-1]["vsol"], before[-1]["vtok"]) if before else (pbV, pbT)
    x = SIZE * 1e9 / (1 + fee)
    q_pb = pbT * x / (pbV + x); q = Tk * x / (V + x)
    if q < q_pb * (1 - CAP / 1e4): return None, fee, seq
    return (V + x, Tk - q, q, (V / Tk) / (pbV / pbT)), fee, seq


def simulate(st, fee, seq, S, horizon, tips, policy):
    """replay later trades; policy(slot, value_frac_of_cost, state) -> fraction of ORIGINAL tokens to sell now (executed at
    the end of the next slot when delayed). Returns PnL in SOL."""
    V, Tk, q0, _ = st; q = q0; proceeds = 0.0; nsell = 0
    cost = SIZE + PRIO + tips
    pending = None; endst = {}
    i = 0; slots = sorted({t["slot"] for t in seq} | set(range(S, horizon + 1)))
    for s in slots:
        if s > horizon: break
        FLOW["b"] = FLOW["s"] = 0.0
        while i < len(seq) and seq[i]["slot"] == s:
            t = seq[i]; i += 1
            if t["buy"]: d = Tk * t["sol"] / (V + t["sol"]); V += t["sol"]; Tk -= d; FLOW["b"] += t["sol"] / 1e9
            else: so = V * t["tok"] / (Tk + t["tok"]); V -= so; Tk += t["tok"]; FLOW["s"] += so / 1e9
        if s < S + 1: continue
        if pending is not None and q > 0:                 # execute the decision taken at the end of the previous slot
            sell = min(q, pending * q0); so = V * sell / (Tk + sell); V -= so; Tk += sell; q -= sell
            proceeds += so * (1 - fee) / 1e9; nsell += 1; pending = None
        if q <= 0: break
        val = V * q / (Tk + q) * (1 - fee) / 1e9
        frac, now = policy(s, (proceeds + val) / cost, q / q0, s - S)
        if frac > 0:
            if now:
                sell = min(q, frac * q0); so = V * sell / (Tk + sell); V -= so; Tk += sell; q -= sell
                proceeds += so * (1 - fee) / 1e9; nsell += 1
            else: pending = frac
        if q <= 0: break
    if q > 0:                                            # anything left: sold at the horizon state
        so = V * q / (Tk + q); proceeds += so * (1 - fee) / 1e9; nsell += 1
    return proceeds - SIZE - PRIO - tips - SELL_FEE * max(1, nsell)


FLOW = {"b": 0.0, "s": 0.0}


def flowexit(thr, n):
    """sell (next slot) after the first slot from S+1 on where outside selling >= thr x outside buying (buyers drying up)"""
    def p(s, v, left, d):
        if d >= n: return (1.0, True)
        if d >= 1 and FLOW["s"] > 0 and FLOW["s"] >= thr * FLOW["b"]: return (1.0, False)
        return (0, False)
    return p


def fixed(k):
    return lambda s, v, left, d: ((1.0, True) if d >= k else (0, False))


def tpsl(tp, sl, n):
    def p(s, v, left, d):
        if d >= n: return (1.0, True)
        if v >= 1 + tp or (sl is not None and v <= 1 - sl): return (1.0, False)
        return (0, False)
    return p


def ladder(pop, leg, sl, n):
    st = {"done": False}
    def p(s, v, left, d):
        if d >= n: return (1.0, True)
        if sl is not None and v <= 1 - sl: return (1.0, False)
        if not st["done"] and v >= 1 + pop: st["done"] = True; return (leg, False)
        return (0, False)
    return p


POL = {f"fixed S+{k}": (lambda k=k: fixed(k)) for k in (1, 2, 3, 4, 5, 7, 10, 14, 20, 30, 45, 60)}
for tp in (0.1, 0.2, 0.3, 0.5):
    for sl in (None, 0.05, 0.1, 0.2):
        for n in (5, 10, 20, 40):
            POL[f"tp{tp:.0%} sl{('%d%%' % (sl*100)) if sl else '-'} max S+{n}"] = (lambda tp=tp, sl=sl, n=n: tpsl(tp, sl, n))
for pop in (0.1, 0.2):
    for leg in (0.3, 0.5):
        for sl in (None, 0.1):
            for n in (10, 20, 40):
                POL[f"ladder {leg:.0%}@+{pop:.0%} sl{('%d%%' % (sl*100)) if sl else '-'} rest S+{n}"] = (lambda pop=pop, leg=leg, sl=sl, n=n: ladder(pop, leg, sl, n))

def trail(arm, drop, n):
    st = {"peak": 0.0}
    def p(s, v, left, d):
        if d >= n: return (1.0, True)
        st["peak"] = max(st["peak"], v)
        if st["peak"] >= 1 + arm and v <= st["peak"] * (1 - drop): return (1.0, False)
        return (0, False)
    return p


for arm in (0.05, 0.15):
    for drop in (0.05, 0.1):
        for n in (10, 20, 40):
            POL[f"trail arm+{arm:.0%} drop{drop:.0%} max S+{n}"] = (lambda arm=arm, drop=drop, n=n: trail(arm, drop, n))

def split(a, frac, b):
    st = {"done": False}
    def p(s, v, left, d):
        if d >= b: return (1.0, True)
        if d >= a and not st["done"]: st["done"] = True; return (frac, True)
        return (0, False)
    return p


for a, frac, b in ((1, 0.6, 10), (1, 0.6, 20), (2, 0.5, 10), (2, 0.5, 20), (2, 0.7, 14), (2, 0.6, 40)):
    POL[f"split {frac:.0%}@S+{a} rest S+{b}"] = (lambda a=a, frac=frac, b=b: split(a, frac, b))

def cond(m, k_long):
    """momentum hold: if at the end of S+1 the position is up >= m (net of costs), hold to S+k_long, else sell at the end of S+2"""
    st = {"hold": None}
    def p(s, v, left, d):
        if d == 1: st["hold"] = v >= 1 + m
        if d >= 2 and not st["hold"]: return (1.0, True)
        if d >= k_long: return (1.0, True)
        return (0, False)
    return p


for m in (0.0, 0.03, 0.06):
    for k_long in (3, 4, 5, 7):
        POL[f"cond up>={m:.0%}@S+1 hold S+{k_long} else S+2"] = (lambda m=m, k_long=k_long: cond(m, k_long))

for thr in (0.5, 1.0):
    for n in (4, 7, 10):
        POL[f"flow sells>={thr:.1f}x buys max S+{n}"] = (lambda thr=thr, n=n: flowexit(thr, n))

R2 = lambda r: r["tipc"] == "lunar" and 3 <= r["gsol"] <= 5 and r["create_ms"] is not None and r["create_ms"] <= 150
R2NC = lambda r: r["tipc"] == "lunar" and 3 <= r["gsol"] <= 5
sel = {"r2": R2, "r2nc": R2NC, "all": lambda r: True}[SEL]
res = collections.defaultdict(dict); meta = {}; chk = []
for r in rows:
    if not sel(r): continue
    rec = REC.get(r["mint"]); outs = OUTS.get(r["mint"])
    if not rec or outs is None: continue
    tp = os.path.join(TD, r["mint"] + ".tape.json")
    tape = json.load(open(tp)) if os.path.exists(tp) else None
    if (rec.get("window_slots") or 2) < NS and not tape: continue
    rec = clean(dict(rec, create_ms=r["create_ms"], slot_ms=rec.get("slot_ms") or 217.0))
    tr, hz = extend(rec, tape)
    e, fee, seq = entry(rec, tr, outs, T_OVR.get(r["cls"], r["T"] + T_ADD))
    tips = TIP_BY[r["cls"]]
    meta[r["mint"]] = dict(grp=r["grp"], r2=R2(r), p2=r["p2"], refused=e is None, cls=r["cls"], breaks=BREAKS[r["mint"]], tape=bool(tape))
    if e is None:
        for k in POL: res[k][r["mint"]] = -REF_COST
        continue
    for k, mk in POL.items():
        res[k][r["mint"]] = simulate(e, fee, seq, rec["S"], min(hz, rec["S"] + NS), tips, mk())
    chk.append((res["fixed S+2"][r["mint"]], r["p2"]))
if os.environ.get("CLEAN"):
    bad = [m for m, x in meta.items() if x["breaks"] > int(os.environ["CLEAN"])]
    for m in bad:
        meta.pop(m)
        for k in res: res[k].pop(m, None)
    print(f"dropped {len(bad)} launches whose tape has > {os.environ['CLEAN']} reserve-chain breaks (missing events)")
print("tape chain breaks per launch:", sorted(collections.Counter(min(x["breaks"], 5) for x in meta.values()).items()))
print(f"landing T: model by class, overrides {T_OVR or '-'}, +{T_ADD:.0f} ms on the rest")
print(f"launches simulated: {len(meta)} ({SEL}; rule #2 {sum(m['r2'] for m in meta.values())}; refused {sum(m['refused'] for m in meta.values())}); "
      f"model check S+2 vs filters p2: mean |diff| {statistics.mean([abs(a-b) for a,b in chk]):.4f}, sums {sum(a for a,_ in chk):+.2f} vs {sum(b for _,b in chk):+.2f}")
G = {"A (in-sample)": lambda m: m["grp"] == "A", "B": lambda m: m["grp"] == "B", "C-E (10-21)": lambda m: m["grp"] in ("C", "D", "E"), "held-out B-E": lambda m: m["grp"] != "A"}
def stats(vals):
    if not vals: return "-"
    s = sorted(vals)
    return f"{sum(vals):+6.2f} {statistics.mean(vals):+.4f} med {statistics.median(vals):+.4f} win {sum(v>0 for v in vals)/len(vals):3.0%} ex3 {sum(s[:-3]):+6.2f}"
order = sorted(POL, key=lambda k: -sum(v for m, v in res[k].items() if meta[m]["grp"] != "A"))
print("\npolicy                                   | " + " | ".join(f"{g} n={sum(1 for m in meta.values() if f(m))}" for g, f in G.items()))
show = [k for k in POL if k.startswith("fixed")] + [k for k in order if not k.startswith("fixed")][:25]
for k in show:
    print(f"{k:40} | " + " | ".join(stats([v for m, v in res[k].items() if f(meta[m])]) for g, f in G.items()))
print("\ncompetitor-like and conditional exits:")
for k in [k for k in POL if k.startswith(("split", "cond", "trail", "flow"))]:
    print(f"{k:40} | " + " | ".join(stats([v for m, v in res[k].items() if f(meta[m])]) for g, f in G.items()))
# best policies chosen on A only -> held-out
print("\nchosen on A (in-sample) only, then held out:")
bestA = sorted(POL, key=lambda k: -sum(v for m, v in res[k].items() if meta[m]["grp"] == "A"))[:5]
for k in bestA:
    print(f"  {k:40} A {stats([v for m, v in res[k].items() if meta[m]['grp']=='A'])} | held-out {stats([v for m, v in res[k].items() if meta[m]['grp']!='A'])}")
json.dump(dict(meta=meta, res={k: v for k, v in res.items()}), open(os.environ.get("OUTJ", "/dev/null"), "w"))
