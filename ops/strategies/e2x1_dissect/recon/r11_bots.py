#!/usr/bin/env python3
"""recon step 11 (read-only): bot labels + exact per-bot P&L per day, two views, reconciled to r6.
Label (MEASURED rules): size code (r10 tier) and token age at entry (r9):
  FRESH  = age < 30 s, size 0.7 % of curve vSOL after the trigger trade (1.3 % 'boost' until 10-27 ~09:30 PKT)
  MINUTE = age 30-120 s, size 1.0 % (1.5 % boost until 10-27 ~09:30)
  OLD    = age >= 120 s, size not vSOL-tiered (1.000 SOL cap on 58 %)
  Age decides; within +-3 s of a boundary (block clock is 1 s, creation time vs the bot's clock) the size code decides.
Cash view: every in-day trading tx (buy, sell, failed) -> its lot -> bot; failed txs with no lot -> bot by the mint's age at that time.
  sum over bots == r6 trading total (lamport-exact).
Lot view: lots BOUGHT in the day, followed to their close (any day), open ones marked at the curve quote of the last tape trade.
Out: lots.pkl rewritten (v2: + bot, tier, age_s, age_slots, trig_*, feat_*), bots.pkl, r11.txt"""
import pickle, collections, json, time
import numpy as np
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
W0 = 1793113200; W1 = W0 + 86400; WA = W0 - 86400
DAYS = (("D0", WA, W0), ("D1", W0, W1))
L = pickle.load(open(f"{OUT}/lots.pkl", "rb")); F = pickle.load(open(f"{OUT}/feat.pkl", "rb")); R = pickle.load(open(f"{OUT}/trig.pkl", "rb"))
FA = pickle.load(open(f"{OUT}/fails.pkl", "rb")); R6 = pickle.load(open(f"{OUT}/r6.pkl", "rb"))
TX = {r["sig"]: r for r in pickle.load(open(f"{OUT}/tx.pkl", "rb"))}
for r in pickle.load(open(f"{OUT}/rpc_tx.pkl", "rb")): TX.setdefault(r["sig"], r)
Z = pickle.load(open(f"{OUT}/tape.pkl", "rb")); CR = Z["creates"]
def band_age(a): return "FRESH" if a < 30 else "MINUTE" if a < 120 else "OLD"
CODE = {"0.7%": "FRESH", "1.3%": "FRESH", "1.0%": "MINUTE", "1.5%": "MINUTE"}
for l in L:
    f = F[l["lot_id"]]; t = R[l["lot_id"]]; a = f["age_s"]
    b = band_age(a)
    if (27 <= a <= 33 or 117 <= a <= 135) and t["tier"] in CODE: b = CODE[t["tier"]]
    l["bot"] = b; l["tier"] = t["tier"]; l["age_s"] = a; l["age_slots"] = f["age_slots"]
    for k, v in t.items():
        if k != "tier": l[k] = v
    for k, v in f.items():
        if k not in ("age_s", "age_slots"): l["feat_" + k] = v
# marks for open lots: curve quote at the last tape trade (net of 1.25 % fee approx -> use the lot's own fbps+cbps)
for l in L:
    l["mark"] = 0.0
    if l["is_open"]:
        t = [x for x in Z["trades"][l["mint"]] if x[16]]
        x = t[-1]; vs, vt = x[9], x[10]; tok = l["left"]
        out = vs - vs * vt / (vt + tok); bps = (l["fbps"] or 95) + (l["cbps"] or 30)
        l["mark"] = out * (1 - bps / 1e4) / 1e9; l["mark_bt"] = x[3]
    l["pnl"] = l["pnl_cash"] + l["mark"]
lot_by_id = {l["lot_id"]: l for l in L}
# ---- cash view per tx
def mint_age_bot(mint, bt):
    c = CR.get(mint); return band_age(bt - c["bt"]) if c else "OLD"
fails = {f["sig"]: f for f in FA["fails"]}
sig2lot = {}
for l in L:
    sig2lot[l["buy_sig"]] = l
    for s in l["sells"]: sig2lot.setdefault(s[0], l)
Lines = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); Lines.append(s)
BOTS = ("FRESH", "MINUTE", "OLD")
res = {}
for dn, a, b in DAYS:
    cash = collections.Counter(); n = collections.Counter()
    for sig in R6[dn]["rows"]:
        r = TX[sig]
        if not r["own"]: continue
        if r["ok"] and r["kind"] in ("buy", "sell"):
            if r["kind"] == "sell":
                # a sell can span lots (never happens here: one lot per mint at a time) -> attribute by its lot
                l = sig2lot[sig]
                c = (r["trade"] if r["events"] else (r["sd"] + r["txfee"] + r["tips"] - r["rent_x"])) - r["txfee"] - r["tips"] + r["rent_x"]
            else:
                l = sig2lot[sig]; c = r["trade"] - r["txfee"] - r["tips"] - r["rent_c"] + r["other"]
            cash[l["bot"]] += c; n[(l["bot"], r["kind"])] += 1
        elif not r["ok"]:
            f = fails[sig]; bot = lot_by_id[f["lot_id"]]["bot"] if f["lot_id"] is not None else mint_age_bot(r["mint"], r["bt"])
            cash[bot] -= r["txfee"]; n[(bot, "fail")] += 1
    tot = sum(cash.values())
    P(f"\n## {dn} cash view (every in-day trading lamport; MEASURED)")
    P("| bot | buys | sells | failed | cash SOL |"); P("|---|---|---|---|---|")
    for bt_ in BOTS: P(f"| {bt_} | {n[(bt_, 'buy')]} | {n[(bt_, 'sell')]} | {n[(bt_, 'fail')]} | {cash[bt_] / 1e9:+.9f} |")
    P(f"| ALL | {sum(n[(x, 'buy')] for x in BOTS)} | {sum(n[(x, 'sell')] for x in BOTS)} | {sum(n[(x, 'fail')] for x in BOTS)} | {tot / 1e9:+.9f} |")
    P(f"r6 trading total {R6[dn]['trading'] / 1e9:+.9f}; difference {tot - R6[dn]['trading']} lamports")
    # lot view
    P(f"\n## {dn} lot view (lots bought in the day, followed to close; open lots marked)")
    P("| bot | lots | SOL in | lot P&L | mSOL/lot | ret on SOL in | win | size p50 | age p50 s | hold p10/50/90 s | open | top-5% lots' share of P&L |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|")
    res[dn] = {}
    for bt_ in BOTS + ("ALL",):
        x = [l for l in L if l["day"] == dn and (bt_ == "ALL" or l["bot"] == bt_)]
        p = np.array([l["pnl"] for l in x]); c = np.array([l["cost"] for l in x]); hs = np.array([l["hold_s"] for l in x if l["hold_s"] is not None])
        ps = np.sort(p)[::-1]; k = max(1, len(p) // 20)
        P(f"| {bt_} | {len(x)} | {c.sum():.2f} | **{p.sum():+.3f}** | {1000 * p.mean():+.1f} | {100 * p.sum() / c.sum():+.1f}% | {100 * (p > 0).mean():.0f}% | {np.median(c):.3f} | {np.median([l['age_s'] for l in x]):.0f} | {np.percentile(hs, 10):.0f}/{np.percentile(hs, 50):.0f}/{np.percentile(hs, 90):.0f} | {sum(l['is_open'] for l in x)} | {ps[:k].sum() / p.sum():.0%} |")
        res[dn][bt_] = dict(lots=len(x), pnl=float(p.sum()), cash=cash.get(bt_, sum(cash.values()) if bt_ == "ALL" else 0) / 1e9)
    # bridge
    P(f"bridge {dn}: lot view {sum(l['pnl'] for l in L if l['day'] == dn):+.4f} vs cash {tot / 1e9:+.4f}")
for l in L: l["version"] = 2
pickle.dump(L, open(f"{OUT}/lots.pkl", "wb")); pickle.dump(res, open(f"{OUT}/bots.pkl", "wb"))
open(f"{OUT}/version", "w").write("v2 (bot labels, tier, age, trigger, marks)\n")
open(f"{OUT}/r11.txt", "w").write("\n".join(Lines) + "\n")
