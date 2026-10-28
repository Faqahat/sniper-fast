#!/usr/bin/env python3
"""recon step 7 (read-only): per-bot P&L two ways and the exact bridge between them.
 (a) cash flow in the window (r6 section 3, exact lamports; failed-tx fees included; rent excluded)
 (b) lot P&L of lots OPENED in the window, followed to their real close (recordings to 10-28 02:14 PKT), marked only if still open
     (exact curve quote at the tape's last state), minus the bot's failed-tx fees in the window.
 Bridge: (a) = (b) - [after-W1 sells of window lots] + [in-window sells of pre-window lots] (+ unmatched sells) (- marks)
Also compares (b) with the earlier per-code D5 numbers (pos/p1.pkl code-matched lots, tape-based).
Out: recon/r7.txt"""
import json, pickle, collections, sys, os, random, time
import numpy as np
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
rows = pickle.load(open(f"{OUT}/table.pkl", "rb"))["rows"]
LZ = pickle.load(open(f"{OUT}/lots.pkl", "rb")); LOTS, UNM = LZ["lots"], LZ["unm"]
L = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); L.append(s)
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 18000))
# (a)
A = collections.Counter(); NF = collections.Counter(); FF = collections.Counter()
for r in rows:
    if r["cls"] == "fail": A[r["code"]] -= r["txfee"]; FF[r["code"]] += r["txfee"]; NF[r["code"]] += 1
    elif r["cls"] in ("buy", "sell"): A[r["code"]] += r["trade"] - r["txfee"] - r["tips"]
    elif r["cls"] == "swap_sell": A[r["code"]] += r["wsol_d"] - r["txfee"] - r["tips"]
A = {k: v / 1e9 for k, v in A.items()}; FF = {k: v / 1e9 for k, v in FF.items()}
# (b) and bridge terms
Bt = collections.defaultdict(lambda: collections.Counter())
for l in LOTS:
    c = l["code"]; b = Bt[c]
    if l["inw"]:
        b["lots"] += 1; b["cost"] += l["cost"]; b["btxc"] += l["btxc"]
        b["out_w"] += l["out_w"]; b["stxc_w"] += l["stxc_w"]; b["out_after"] += l["out_after"]; b["stxc_after"] += l["stxc_after"]
        b["mark"] += l["mark_end"]; b["open_end"] += l["left"] > 0
        b["pnl"] += l["pnl"]; b["win"] += l["pnl"] > 0
        b["closed_w1"] += (l["close_bt"] is not None and l["close_bt"] < W1)
        b["swap"] += l["swap"]
        b["mark_w1"] += l.get("mark_w1", 0.0); b["open_w1"] += l.get("tok_w1", 0) > 0.5
        hold = (l["close_bt"] - l["bt"]) if l["close_bt"] else None
        if hold is not None: b.setdefault("holds", None)
    elif l["bt"] < W0:
        # pre-window lot: its in-window sells are part of (a)
        b["pre_out_w"] += l["out_w"]; b["pre_stxc_w"] += l["stxc_w"]
um = collections.Counter()
for u in UNM:
    if u["inw"]: um[u["code"]] += u["P"] - u["C"]
codes = sorted(set(A) | set(c for c in Bt if Bt[c]["lots"]), key=lambda c: -(A.get(c, 0)))
P("## Per-bot P&L two ways (SOL; MEASURED exact cash; code = CU price mod 1000)")
P("| code | lots opened | SOL in (cost) | lot P&L (b) before failed fees | failed txs | failed fees | **(b) lot P&L** | mSOL/lot | win | open at end | **(a) cash in window** | bridge: -after-W1 sells | +pre-window lots sold in window | +unmatched | (a) rebuilt | diff |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
T = collections.Counter()
for c in codes:
    b = Bt[c]
    bl = b["pnl"]; bb = bl - FF.get(c, 0)
    after = b["out_after"] - b["stxc_after"]; pre = b["pre_out_w"] - b["pre_stxc_w"]
    rebuilt = bb - after - b["mark"] + pre + um.get(c, 0) / 1e9
    a = A.get(c, 0)
    P(f"| {c} | {b['lots']:,} | {b['cost']:.3f} | {bl:+.4f} | {NF.get(c, 0):,} | {FF.get(c, 0):.4f} | **{bb:+.4f}** | {1000 * bb / max(b['lots'], 1):+.2f} | {b['win'] / max(b['lots'], 1):.0%} | {b['open_end']} | **{a:+.4f}** | {-after:+.4f} | {pre:+.4f} | {um.get(c, 0) / 1e9:+.4f} | {rebuilt:+.4f} | {a - rebuilt:+.2e} |")
    for k, v in (("lots", b["lots"]), ("cost", b["cost"]), ("bl", bl), ("nf", NF.get(c, 0)), ("ff", FF.get(c, 0)), ("bb", bb), ("a", a), ("after", -after), ("pre", pre), ("um", um.get(c, 0) / 1e9), ("reb", rebuilt), ("win", b["win"]), ("open", b["open_end"])): T[k] += v
P(f"| ALL | {T['lots']:,} | {T['cost']:.3f} | {T['bl']:+.4f} | {T['nf']:,} | {T['ff']:.4f} | **{T['bb']:+.4f}** | {1000 * T['bb'] / T['lots']:+.2f} | {T['win'] / T['lots']:.0%} | {T['open']} | **{T['a']:+.4f}** | {T['after']:+.4f} | {T['pre']:+.4f} | {T['um']:+.4f} | {T['reb']:+.4f} | {T['a'] - T['reb']:+.2e} |")
# compare with the earlier per-code D5 table (pos/p1.pkl, tape-based code-matched lots, cnet)
try:
    sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
    import plib
    Bp, LOp, Tp = plib.load()
    old = collections.Counter(); oldn = collections.Counter()
    for l in LOp:
        if l["day"] == 5 and l.get("code") is not None:
            old[l["code"]] += l["cnet"]; oldn[l["code"]] += 1
    P("\n## (b) vs the earlier per-code table for the same day (pos/p1.pkl D5, code-matched lots, tape prices x bps fees, estimated tx costs)")
    P("| code | lots now | lots p1 | (b) now | p1 D5 | diff |")
    P("|---|---|---|---|---|---|")
    for c in codes:
        b = Bt[c]; bb = b["pnl"] - FF.get(c, 0)
        P(f"| {c} | {b['lots']:,} | {oldn.get(c, 0):,} | {bb:+.3f} | {old.get(c, 0):+.3f} | {bb - old.get(c, 0):+.3f} |")
    P(f"| ALL | {T['lots']:,} | {sum(oldn.values()):,} | {T['bb']:+.3f} | {sum(old.values()):+.3f} | {T['bb'] - sum(old.values()):+.3f} |")
except Exception as ex:
    P("p1 comparison failed:", repr(ex)[:200])
P("\n## Bot profile in the window (lots opened in the window; MEASURED)")
P("| code | lots | size p50 SOL | hold p10/p50/p90 s | sold in >1 piece | lots with a PumpSwap sell | best lot | worst lot | P&L of top 1% lots |")
P("|---|---|---|---|---|---|---|---|---|")
for c in codes:
    lw = [l for l in LOTS if l["inw"] and l["code"] == c]
    if not lw: continue
    hs = np.array([l["close_bt"] - l["bt"] for l in lw if l["close_bt"] is not None], float)
    pn = np.sort(np.array([l["pnl"] for l in lw]))
    k = max(1, len(pn) // 100)
    P(f"| {c} | {len(lw):,} | {np.median([l['cost'] for l in lw]):.3f} | {np.percentile(hs, 10):.0f} / {np.percentile(hs, 50):.0f} / {np.percentile(hs, 90):.0f} | {sum(1 for l in lw if len(set(x[0] for x in l['sells'])) > 1) / len(lw):.0%} | {sum(l['swap'] for l in lw)} | {pn[-1]:+.3f} | {pn[0]:+.3f} | {pn[-k:].sum():+.3f} |")
pickle.dump(dict(A=A, Bt={k: dict(v) for k, v in Bt.items()}, FF=FF, NF=NF), open(f"{OUT}/r7.pkl", "wb"))
open(f"{OUT}/r7.txt", "w").write("\n".join(L) + "\n")
