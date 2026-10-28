#!/usr/bin/env python3
"""copypaper: RUNNING.md (human table, PKT) from out/results.jsonl + out/trades.jsonl. Usage: cp_table.py [results] [trades] [out.md]"""
import sys, json, os, datetime as dt
D = "/home/moiz/sniper-data/e2x1_dissect/copypaper/out"
res_f = sys.argv[1] if len(sys.argv) > 1 else f"{D}/results.jsonl"
tr_f = sys.argv[2] if len(sys.argv) > 2 else f"{D}/trades.jsonl"
out_f = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "RUNNING.md")
PKT = dt.timezone(dt.timedelta(hours=5))
now = dt.datetime.now(PKT).strftime("%m-%d %H:%M PKT")
R = [json.loads(l) for l in open(res_f)] if os.path.exists(res_f) else []
R = [r for r in R if r.get("mode") == "frozen"]
T = [json.loads(l) for l in open(tr_f)] if os.path.exists(tr_f) else []
L = []
P = L.append
P(f"# copypaper RUNNING — paper copy-trade of the E2x1 cluster (frozen rules in FROZEN.md), updated {now}")
P("PAPER ONLY. SOL after 2.9 mSOL/trip + 0.3 mSOL/revert. Columns: raw | f20fast = raw with 20% of other buys in the 10 slots after our entry removed (pass-bar row) | f20hold = 20% of ALL other buys over the hold removed (harsh, info) | cal = raw − (−4.4+28.1×S) mSOL per attempt | stop = −20% stop variant.")
P("")
P("| window (PKT) | sig | fills | raw | f20fast | f20hold | **cal** | raw stop | cal stop | E2x1 raw/cal (n) | Groz raw/cal (n) | top5 raw | raw ex-top5 | cal ex-top5 | t/o | PS | run raw | run f20fast | run cal | run cal ex-top5 |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
cum = dict(raw=0.0, f20fast=0.0, cal=0.0, f20=0.0, raw_stop=0.0, cal_stop=0.0, signals=0, fills=0.0)
for r in R:
    for k in cum: cum[k] += r.get(k, 0)
    allt = [t for t in T if t["window"] <= r["start"]]
    srt = sorted((t["raw"] for t in allt), reverse=True); srtc = sorted((t["cal"] for t in allt), reverse=True)
    rx = (sum(srt) - sum(srt[:5])) / 1e9; cx = (sum(srtc) - sum(srtc[:5])) / 1e9
    P(f"| {r['start_pkt']}–{r['end_pkt'][6:]} | {r['signals']} | {r['fills']:.0f} | {r['raw']:+.2f} | {r['f20fast']:+.2f} | {r['f20']:+.2f} | **{r['cal']:+.2f}** | {r['raw_stop']:+.2f} | {r['cal_stop']:+.2f} | "
      f"{r['raw_E2x1']:+.2f}/{r['cal_E2x1']:+.2f} ({r['n_E2x1']}) | {r['raw_Groz']:+.2f}/{r['cal_Groz']:+.2f} ({r['n_Groz']}) | {r['top5_raw']:+.2f} | {r['raw_ex_top5']:+.2f} | {r['cal_ex_top5']:+.2f} | "
      f"{r['timeouts']} | {r['ps_exits']} | {cum['raw']:+.2f} | {cum['f20fast']:+.2f} | {cum['cal']:+.2f} | {cx:+.2f} |")
if R:
    srt = sorted((t["raw"] for t in T), reverse=True); srtc = sorted((t["cal"] for t in T), reverse=True); srtf = sorted((t["f20fast"] for t in T), reverse=True)
    rx = (sum(srt) - sum(srt[:5])) / 1e9; cx = (sum(srtc) - sum(srtc[:5])) / 1e9; fx = (sum(srtf) - sum(srtf[:5])) / 1e9
    hrs = sum(r["end"] - r["start"] for r in R) / 3600
    P("")
    P(f"**Running total over {hrs:.0f} h ({cum['signals']} signals, {cum['fills']:.0f} fills):** raw {cum['raw']:+.2f} | f20fast {cum['f20fast']:+.2f} | f20hold {cum['f20']:+.2f} | **cal {cum['cal']:+.2f}** | stop: raw {cum['raw_stop']:+.2f} / cal {cum['cal_stop']:+.2f} | "
      f"top-5 trades removed: raw {rx:+.2f}, f20fast {fx:+.2f}, cal {cx:+.2f}")
    ok = cum["cal"] > 0 and cum["f20fast"] > 0 and rx >= 0 and cx >= 0
    P(f"**Pass bar (48 h: cal > 0 AND f20fast > 0 AND ex-top-5 raw ≥ 0 AND ex-top-5 cal ≥ 0): {'PASS so far' if ok else 'FAIL so far'}** ({hrs:.0f}/48 h scored)")
    lk = [r for r in R if not r.get("lookahead_ok", True)]
    if lk: P(f"WARNING: {len(lk)} window(s) scored without full 1800 s look-ahead (tape ended early).")
    tr = sorted(T, key=lambda t: -t["raw"])
    P("")
    P("Top 5 / bottom 5 trades so far (expected over the 21 landing draws; GMGN links):")
    P("| when (PKT) | wallet | token | size SOL | fill | hold s | exit | raw mSOL | cal mSOL |")
    P("|---|---|---|---|---|---|---|---|---|")
    for t in tr[:5] + tr[-5:]:
        P(f"| {t['pkt']} | {t['wallet']} | [{t['mint'][:8]}](https://gmgn.ai/sol/token/{t['mint']}) | {t['S']:.2f} | {t['fill']:.2f} | {t['hold_s']:.0f} | {t['kind']}{' PS' if t['ps'] else ''} | {t['raw'] / 1e6:+.1f} | {t['cal'] / 1e6:+.1f} |")
else:
    P("(no windows scored yet)")
open(out_f, "w").write("\n".join(L) + "\n")
print("\n".join(L[-6:]))
