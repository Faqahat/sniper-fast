#!/usr/bin/env python3
# Format live paper trades for the chat (simple): new trades from line OFFSET on, then the top 20 of 192 exits by live P&L at
# 35 ms (with each exit's fair backtest on the 12.3 unseen TEST hours for reference) and our main exit.
# usage: python3 -I live_post.py OFFSET
import sys, json, time
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import live_exits as LE
F = "/home/moiz/sniper/ops/overnight/sel/live_trades.jsonl"; BT = json.load(open("/home/moiz/sniper/ops/overnight/sel/exit_bt.json"))
off = int(sys.argv[1]); R = [json.loads(l) for l in open(F)]
W = {"T": "take-profit", "S": "stop-loss", "L": "time limit"}
def tot(L, nm):
    v = [r["res"].get(L) for r in R]; fills = [x[nm][0] for x in v if x and x["f"]]; sk = sum(1 for x in v if x and not x["f"])
    return sum(fills) - 0.0002 * sk, len(fills), sum(1 for p in fills if p > 0)
# split exits (owner: test as many as possible): half the tokens on a quick exit, half held longer. Approximation: P&L = average of
# the two full-position exits minus one extra sell tx (0.0008); the same formula for the backtest from its totals.
FIRST = ("tp8_sl5_1.3s", "tp10_sl10_1.3s", "tp5_sl10_1.3s"); SECOND = ("tpnone_slnone_6s", "tpnone_sl10_6s", "tpnone_sl20_12s", "tp50_sl10_6s", "tp30_slnone_12s")
SPL = {f"{a}+{b}": (a, b) for a in FIRST for b in SECOND}
for r in R:
    for L, x in r["res"].items():
        if x and x["f"]:
            for nm, (a, b) in SPL.items():
                pa, pb = x[a][0], x[b][0]; x[nm] = [round(0.5 * (pa + pb) - 0.0008, 5), "M", max(x[a][2], x[b][2])]
for nm, (a, b) in SPL.items():
    BT[nm] = {L: [round(0.5 * (BT[a][L][0] + BT[b][L][0]) - 0.0008 * BT[a][L][1], 3), BT[a][L][1], None] for L in BT[a]}
def lab(nm): return ("half " + LE.label(SPL[nm][0]) + " + half " + LE.label(SPL[nm][1])) if nm in SPL else LE.label(nm)
W["M"] = "split"
names = [e[0] for e in LE.EXITS] + list(SPL); rank = sorted(names, key=lambda n: -tot("35", n)[0]); best = rank[0]
for r in R[off:]:
    t = time.strftime("%H:%M:%S", time.gmtime(r["t"] + 18000)); a = r["res"].get("35"); b = r["res"].get("75")
    if not a or not a["f"]: icon, s35 = "➖", "skipped (price already bounced)"
    else:
        m = a[LE.MAIN]; icon = "✅" if m[0] > 0 else "❌"
        s35 = f"{m[0]:+.3f} ({W[m[1]]}, {m[2]:.1f} s) | best-so-far exit {a[best][0]:+.3f}"
    s75 = "skipped" if not b or not b["f"] else f"{b[LE.MAIN][0]:+.3f}"
    who = f" | bots after: {','.join(r['wallets'])}" if r["wallets"] else ""
    print(f"{icon} {t} {'⭐' if r['tier'] == 'strict' else ''}[{r['m'][:6]}…](https://gmgn.ai/sol/token/{r['m']}) dump {r['sell']:.1f} SOL −{r['drop']:.0f}% | 35 ms {s35} | 75 ms {s75}{who}")
if R:
    t0 = time.strftime("%H:%M", time.gmtime(min(r["t"] for r in R) + 18000)); t1 = time.strftime("%H:%M", time.gmtime(max(r["t"] for r in R) + 18000))
    p, n, w = tot("35", LE.MAIN); p75 = tot("75", LE.MAIN)[0]
    print(f"\nLIVE since {t0} PKT ({len(R)} picks, last {t1}). Main exit {LE.label(LE.MAIN)}: 35 ms {p:+.2f} SOL ({w}/{n} won) | 75 ms {p75:+.2f} | rank {rank.index(LE.MAIN) + 1}/{len(names)}")
    print("Buy size (same picks), live P&L at 35 / 75 ms with our main exit and with TP +10% / SL -10% / 1.3 s:")
    for bsz in ("0.25", "0.5", "1.0", "2.0"):
        cells = []
        for nm in (LE.MAIN, "tp10_sl10_1.3s"):
            for L in ("35", "75"):
                v = [(r["res"] if bsz == "0.5" else (r.get("size") or {}).get(bsz, {})).get(L) for r in R]
                f = [x[nm][0] for x in v if x and x.get("f")]; sk = sum(1 for x in v if x and not x.get("f"))
                cells.append(f"{sum(f) - 0.0002 * sk:+.2f}")
        print(f"  {bsz:>4} SOL: main {cells[0]} / {cells[1]} | TP10/SL10 {cells[2]} / {cells[3]}")
    print(f"Top 20 of {len(names)} exits live at 35 ms (live P&L, wins | backtest 12.3 h):")
    for nm in rank[:20]:
        p, n, w = tot("35", nm); print(f"  {lab(nm):30s} {p:+.2f} ({w}/{n}) | bt {BT[nm]['35'][0]:+.2f}")
