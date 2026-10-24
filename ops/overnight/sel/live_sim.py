#!/usr/bin/env python3
# NEAR-LIVE PAPER RUN of the frozen IMIT1 selector (no money, no sends, local only). Newest collector data (run R3, synced every
# ~2 min by work/sync_live.sh) -> every >=1 SOL dump on tokens launched in the last WINDOW_MIN minutes -> watch envelope + IMIT1
# score -> picks (strict = top 2%, wider = top 4%; no re-buy on a token within 5 slots) -> paper trade at entry 35 / 50 / 75 ms
# with the 2% price guard and the tier's exit (TP / SL / 1.3 s time limit) -> each newly CLOSED pick appended once to
# sel/live_trades.jsonl. Same builder as the study (sel/selexit2.py): features and replay identical to the backtest.
# env: WINDOW_MIN (25) | SINCE_PKT 'MM-DD HH:MM' (backlog start instead of the window) | RP_PHASEA_R3 (phaseA_r3live)
import os, sys, json, time, calendar, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3live")
for k, v in dict(SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_B="0.5", DIP_HS="4", DIP_BUSY="0",
                 DIP_HLAG="0", DIP_MAX_AGE="1800", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json").items():
    os.environ[k] = v
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import numpy as np
import selexit2 as X
import gbdt_np as G
D = "/home/moiz/sniper/ops/overnight/sel"
M = json.load(open(f"{D}/IMIT1.json")); FE = M["features"]; LATS = (35, 50, 75)
OUT = f"{D}/live_trades.jsonl"; SEEN = f"{D}/live_seen.json"
seen = set(json.load(open(SEEN))) if os.path.exists(SEEN) else set()
now = time.time()
since = (calendar.timegm(time.strptime("2026-" + os.environ["SINCE_PKT"], "%Y-%m-%d %H:%M")) - 18000) if os.environ.get("SINCE_PKT") \
    else now - float(os.environ.get("WINDOW_MIN", "25")) * 60
recent = {m for m, c in X.L.items() if c["run"] == "R3" and c["bt"] >= since}
byb = collections.defaultdict(set)
for m in recent: byb[("R3", X.rp.bucket(m))].add(m)
X.byb = byb
rows = []; tapes = {}; frontier = 0; last_bt = 0
for key in sorted(byb):
    o, _ = X.work(key); rows += o
    for m, tr in X.rp.read_bucket(key[0], key[1], byb[key]).items():
        tapes[m] = tr
        if tr: frontier = max(frontier, tr[-1]["s"]); last_bt = max(last_bt, tr[-1].get("bt") or 0)
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
rows.sort(key=lambda r: (r["m"], r["age"])); pm = None; past = []
for r in rows:                                  # the three wallets' earlier dip buys on this token (only buys before this dump)
    if r["m"] != pm: pm = r["m"]; past = []
    t0 = r["age"] * 1000.0; b = [x for x in past if x < t0]
    r["tgt_n"] = len(b); r["tgt_since"] = (t0 - max(b)) / 1000.0 if b else 1e9
    for w, d in r["lab"].items(): past.append(t0 + d)
picks = []
if rows:
    XX = np.array([[fv(r, k) for k in FE] for r in rows], float)
    env = np.ones(len(rows), bool)
    for k, op, v in M["envelope"]:
        j = FE.index(k); env &= (XX[:, j] >= v) if op == ">=" else (XX[:, j] <= v)
    B = np.zeros(XX.shape, np.int16)
    for j, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), XX[:, j], side="right") + 1; b[np.isnan(XX[:, j])] = 0; B[:, j] = b
    f = np.full(len(rows), M["F0"])
    for t in M["trees"]: f += M["lr"] * G.pred(t, B)
    last = {}
    for i, r in enumerate(rows):
        if not env[i] or f[i] < M["thresholds"]["top4"]: continue
        if r["m"] in last and r["age"] - last[r["m"]] < 5 * 0.212: continue
        last[r["m"]] = r["age"]; picks.append((r, float(f[i])))
import live_exits as LE                                              # 192 exits: TP x SL x time limit (owner 20:45 PKT)
new = 0; open_n = 0; mism = 0
with open(OUT, "a") as fo:
    for r, sc in picks:
        key = f'{r["m"]}|{r["age"]}'
        if key in seen: continue
        S0 = X.L[r["m"]]["slot"]; s_dump = S0 + round(r["age"] * 1000 / X.SMS)
        if frontier < s_dump + 64: open_n += 1; continue           # the longest exit (12 s) not fully in the data yet
        tr = tapes[r["m"]]
        k = next((j for j, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= X.MIN_SELL and not t.get("syn") and round((t["s"] - S0) * X.SMS / 1000, 2) == r["age"]), None)
        if k is None: continue
        strict = sc >= M["thresholds"]["top2"]
        res = {str(L): LE.detail(X, tr, k, L) for L in LATS}
        SUB = ("tp8_sl5_1.3s", "tp10_sl10_1.3s", "tp5_sl20_12s", "tpnone_slnone_6s", "tpnone_slnone_12s")
        size = {}
        for bsz in (0.25, 1.0, 2.0):                                    # owner 21:55 PKT: other buy sizes, same picks and exits
            X.B = bsz; d = {}
            for L in LATS:
                x = LE.detail(X, tr, k, L); d[str(L)] = None if x is None else ({"f": 0} if not x["f"] else {"f": 1, **{n: x[n] for n in SUB}})
            size[str(bsz)] = d
        X.B = 0.5
        gi = [tuple(g) for g in X.GRID].index(("T", 0.08, 0.05, 6, 1))
        for L in LATS:                                               # cross-check the 1.3 s TP8/SL5 exit against the builder's grid
            x = res[str(L)]
            if x and x["f"] and str(L) in r.get("xg", {}) and abs(r["xg"][str(L)][gi] - x["tp8_sl5_1.3s"][0]) > 2e-5: mism += 1
        rec = dict(key=key, m=r["m"], t=round(X.L[r["m"]]["bt"] + r["age"], 1), age=r["age"], sell=r["sell"], drop=round((1 - r["drop"]) * 100, 1),
                   vsol=r["vsol"], score=round(sc, 3), tier="strict" if strict else "wider", wallets=sorted(r["lab"]), res=res, size=size)
        fo.write(json.dumps(rec) + "\n"); seen.add(key); new += 1
json.dump(sorted(seen), open(SEEN, "w"))
print(f"cycle {time.strftime('%H:%M:%S', time.gmtime(now + 18000))} PKT | tokens {len(recent)} dumps {len(rows)} picks {len(picks)} | new closed trades {new}, "
      f"still open {open_n} | data lag {now - last_bt:.0f} s | grid check mismatches {mism}", flush=True)
