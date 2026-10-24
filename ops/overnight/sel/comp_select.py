#!/usr/bin/env python3
# Owner 10-24 04:30 PKT: "check our competitors, see the pools they have made profit on since our runs; are we missing a filter
# that would get us more qualified tokens — potential to expand our selection".
# Every >= 1 SOL dump since WIN_PKT on tokens launched after the extraction start (collector R3 -> phaseA_r3comp), with the frozen
# IMIT1 features / score / envelope and its label (which of the 3 bots bought within 1 s). For each dump:
#   * the 3 bots' realized trip on it (their buy within 1 s after the dump, FIFO against their later sells on the token, 2.5% pump
#     fees + 0.001 SOL tx costs) -> did THEY make money;
#   * OUR P&L if we had bought it, at 60 / 75 / 110 ms after the dump, guard 1.05, TP +5% / SL -10% / 6 slots, DIP_B SOL, the
#     study's follower model (live_exits / realat4 logic).
# Then: their profitable buys by where they sit against our filters (strict pick / wider / under the cut / outside the envelope).
import os, sys, json, time, calendar, collections
os.environ["RP_PHASEA_R3"] = os.environ.get("RP_PHASEA_R3", "phaseA_r3comp"); os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd")
for k, v in dict(SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_HS="4", DIP_BUSY="0", DIP_HLAG="0",
                 DIP_MAX_AGE="1800", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json").items():
    os.environ[k] = v
os.environ.setdefault("DIP_B", "0.35")
D = "/home/moiz/sniper/ops/overnight/sel"; sys.path.insert(0, D)
import numpy as np
import selexit2 as X
import gbdt_np as G
import live_exits as LE
M = json.load(open(f"{D}/IMIT1.json")); FE = M["features"]
TGT = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC",
       "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX"}
EXTRACT_T0 = int(os.environ.get("EXTRACT_T0", "1792787700"))          # the first collector chunk in phaseA_r3comp
WIN = calendar.timegm(time.strptime("2026-" + os.environ.get("WIN_PKT", "10-24 02:15"), "%Y-%m-%d %H:%M")) - 18000
LATS = (60, 75, 110); GUARD = 1.05; EXI = [e for e in LE.EXITS if e[0] == "tp5_sl10_1.3s"][0]

recent = {m for m, c in X.L.items() if c["run"] == "R3" and c["bt"] >= EXTRACT_T0 + 60}   # full tapes only
byb = collections.defaultdict(set)
for m in recent: byb[("R3", X.rp.bucket(m))].add(m)
X.byb = byb
rows = []; tapes = {}
for key in sorted(byb):
    o, _ = X.work(key); rows += o
    for m, tr in X.rp.read_bucket(key[0], key[1], byb[key]).items(): tapes[m] = tr
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
rows.sort(key=lambda r: (r["m"], r["age"])); pm = None; past = []
for r in rows:
    if r["m"] != pm: pm = r["m"]; past = []
    t0 = r["age"] * 1000.0; b = [x for x in past if x < t0]
    r["tgt_n"] = len(b); r["tgt_since"] = (t0 - max(b)) / 1000.0 if b else 1e9
    for w, d in r["lab"].items(): past.append(t0 + d)
XX = np.array([[fv(r, k) for k in FE] for r in rows], float)
env = np.ones(len(rows), bool); why_env = [[] for _ in rows]
for k, op, v in M["envelope"]:
    j = FE.index(k); ok = (XX[:, j] >= v) if op == ">=" else (XX[:, j] <= v)
    for i in np.flatnonzero(~ok): why_env[i].append(f"{k}{'<' if op == '>=' else '>'}{v}")
    env &= ok
B = np.zeros(XX.shape, np.int16)
for j, e in enumerate(M["edges"]):
    b = np.searchsorted(np.array(e), XX[:, j], side="right") + 1; b[np.isnan(XX[:, j])] = 0; B[:, j] = b
f = np.full(len(rows), M["F0"])
for t in M["trees"]: f += M["lr"] * G.pred(t, B)

def ours(tr, k, L):
    """our P&L if we buy L ms after the dump at k (guard, exit as live); None: tape too short; 'blocked': the guard refuses"""
    t = tr[k]; a0 = X.arr(t); fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4; p_after = t["vsol"] / t["vtok"]
    ke = k + 1
    while ke < len(tr) and X.arr(tr[ke]) < a0 + L: ke += 1
    if ke >= len(tr): return None
    if (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after > GUARD: return "blocked"
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, int((a0 + L) // X.SMS))
    nm, tp, sl, cap, mh = EXI; n = len(K_); co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
    ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
    a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
    s_out = co if (a is None and b is None) else (int(S_[a]) + 1 if (b is None or (a is not None and a <= b)) else int(S_[b]) + 1)
    return float(PNL[min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)])

def their_trip(tr, k, w):
    """the wallet's buy(s) within 1 s after the dump, FIFO against its later sells on the token (<= 600 s); net SOL"""
    a0 = X.arr(tr[k]); bought = [t for t in tr[k + 1:] if t.get("user") == w and t["buy"] and X.arr(t) - a0 <= 1000]
    if not bought: return None
    sol_in = sum(t["sol"] for t in bought) / 1e9; tok = sum(t["tok"] for t in bought)
    last = max((t["s"], t["i"]) for t in bought); left = tok; sol_out = 0.0; sold_after = 0
    for t in tr:
        if (t["s"], t["i"]) <= last or t.get("user") != w or t["buy"] or left <= 0: continue
        q = min(left, t["tok"]); sol_out += t["sol"] / 1e9 * q / t["tok"]; left -= q; sold_after += 1
    if left > tok * 0.02: return dict(sol_in=sol_in, pnl=None, open=True)
    return dict(sol_in=sol_in, pnl=sol_out * (1 - 0.0125) - sol_in * (1 + 0.0125) - 0.001, open=False)

out = []
for i, r in enumerate(rows):
    m = r["m"]; tr = tapes.get(m)
    if not tr: continue
    S0 = X.L[m]["slot"]
    k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"]), None)
    if k is None or (tr[k].get("bt") or 0) < WIN: continue
    sc = float(f[i]); tier = "strict" if env[i] and sc >= M["thresholds"]["top2"] else "wider" if env[i] and sc >= M["thresholds"]["top4"] else \
         "top8" if env[i] and sc >= M["thresholds"]["top8"] else "env-low" if env[i] else "out-env"
    trips = {TGT[w]: their_trip(tr, k, w) for w in TGT}
    out.append(dict(m=m, t=tr[k].get("bt"), age=r["age"], sell=r["sell"], drop=round((1 - r["drop"]) * 100, 1), score=round(sc, 3), tier=tier, why_env=why_env[i],
                    lab=sorted(r["lab"]), trips={w: v for w, v in trips.items() if v}, ours={L: ours(tr, k, L) for L in LATS}))
json.dump(out, open(f"{D}/comp_select.json", "w"))
hrs = (max(o["t"] for o in out) - min(o["t"] for o in out)) / 3600 if out else 0
print(f"dumps from {os.environ.get('WIN_PKT', '10-24 02:15')} PKT: {len(out)} over {hrs:.2f} h (tokens launched after the extraction start)")
def summ(sel, name):
    tb = [o for o in sel if o["trips"]]; trips = [v for o in sel for v in o["trips"].values() if not v["open"]]
    win = sum(1 for v in trips if v["pnl"] > 0); pnl = sum(v["pnl"] for v in trips)
    line = f"{name:34s} dumps {len(sel):5d} | bought by the 3 bots {len(tb):4d} ({100 * len(tb) / max(1, len(sel)):4.1f}%) | their closed trips {len(trips):4d}, win {100 * win / max(1, len(trips)):3.0f}%, P&L {pnl:+7.2f}"
    for L in LATS:
        v = [o["ours"][L] for o in sel if o["ours"][L] is not None]
        fills = [x for x in v if x != "blocked"]; blocked = len(v) - len(fills)
        line += f" | us@{L}ms {sum(fills) - 0.0005 * blocked:+6.2f} ({len(fills)} fills)"
    print(line)
for tier in ("strict", "wider", "top8", "env-low", "out-env"):
    summ([o for o in out if o["tier"] == tier], tier)
summ([o for o in out if o["tier"] in ("strict", "wider")], "strict + wider")
oe = [o for o in out if o["tier"] == "out-env" and o["trips"]]
c = collections.Counter(w.split("<")[0].split(">")[0] for o in oe for w in o["why_env"])
print("\nthe 3 bots' buys OUTSIDE our envelope, by the bound that failed:", dict(c.most_common()))
for b in ("age", "drop_pct", "since_buy", "sell"):
    sel = [o for o in oe if any(w.startswith(b) for w in o["why_env"])]
    if sel: summ(sel, f"  out-env because of {b}")
print("\ntop profitable trips of the 3 bots in the window (and our tier):")
tops = sorted(((v["pnl"], w, o) for o in out for w, v in o["trips"].items() if not v["open"]), key=lambda x: -x[0])[:15]
for pnl, w, o in tops: print(f"  {w} {pnl:+.3f} SOL on {o['m'][:8]} age {o['age']:.0f}s dump {o['sell']:.2f} -{o['drop']:.0f}% | our tier {o['tier']} score {o['score']:+.2f} {o['why_env'] if o['tier'] == 'out-env' else ''}")
