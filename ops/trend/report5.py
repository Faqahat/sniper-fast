#!/usr/bin/env python3
# READ-ONLY, offline: build the Rule 3 (trend) report from analyze5.py's analysis.json: one self-contained HTML page with
# every trade after our real buy (Solscan / GMGN links), our PnL if sold right after each trade, and the rule table.
import sys, os, json, html
OUT = sys.argv[1]
A = json.load(open(os.path.join(OUT, "analysis.json")))
META = json.load(open(os.path.join(OUT, "meta.json")))
TX = lambda s: f"https://solscan.io/tx/{s}"
ACC = lambda a: f"https://gmgn.ai/sol/address/{a}"
TOK = lambda m: f"https://gmgn.ai/sol/token/{m}"
SCT = lambda m: f"https://solscan.io/token/{m}"
e = html.escape
GMGN_BOUGHT_USD = {"Lucknow": 158.64, "lysis": 158.53, "GEGA": 53.35, "chud": 53.36, "JFTO": 53.55}
def sh(x, n=6): return f"{x[:n]}…{x[-4:]}"
def sol(x, d=4): return f"{x:+.{d}f}"
P = []
P.append("""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trend Rule Data</title>
<style>
:root{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd;--pos:#0a7a2f;--neg:#b3261e;--us:#fff4cc;--hd:#f4f4f4}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#eee;--mut:#9a9a9a;--line:#333;--pos:#4cd17a;--neg:#ff7b72;--us:#3a3210;--hd:#1d1d1d}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;max-width:1200px}
h1{font-size:20px}h2{font-size:17px;margin-top:28px;border-top:1px solid var(--line);padding-top:14px}
a{color:inherit}table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:right;white-space:nowrap}
th{background:var(--hd);position:sticky;top:0}td.l,th.l{text-align:left}.wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.pos{color:var(--pos)}.neg{color:var(--neg)}.us td{background:var(--us);font-weight:600}.mut{color:var(--mut)}.kv td{text-align:left;white-space:normal}
code{font-size:12px;word-break:break-all}
</style></head><body>""")
P.append("<h1>Rule 3 (trend) — our 5 real Rule #2 buys, every trade after them</h1>")
P.append("""<p class="mut">Wallet <a href="%s">2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE</a>. All data from the chain (public RPC, read-only).
<b>Entry = our real buy</b> (real tx, real price). <b>“If sold right after this trade”</b> = our real tokens sold into the curve right after that trade:
SOL out = vSOL × tokens / (vTok + tokens) (pump.fun bonding curve), minus pump fee (same bps as our real sell), minus our real sell tx fee, plus the token-account rent back;
PnL = that minus everything our buy tx really cost. Trades after our real sell are replayed as if we had held (others’ amounts unchanged).
<b>#</b> = number of other people's trades since our buy (what the rules count; our own real sells show “—”, rows before our buy are negative). “End of slot” column = more realistic: our sell lands after the rest of that slot’s trades (~0.1–0.2 s later). Times are block times (UTC, 1 s resolution); S+k = slots after the create (~0.21 s each).</p>""" % ACC("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"))
# rule table
names = [t["name"] for t in A["tokens"]]
P.append("<h2>Exit rules on the 5 trades (PnL in SOL, real sizes)</h2><div class='wrap'><table><tr><th class='l'>rule</th>" + "".join(f"<th>{e(n)}</th>" for n in names) + "<th>TOTAL</th><th>TOTAL, sell lands end of slot</th></tr>")
for rn, v in A["rules"].items():
    cells = "".join(f"<td class='{'pos' if p > 0 else 'neg'}'>{sol(p)}{'' if (n is not None or rn.startswith(('hold', 'BEST', 'up '))) else '*'}</td>" for p, _, n in v)
    tot = sum(p for p, _, _ in v); tot2 = sum(x for _, x, _ in v)
    P.append(f"<tr><td class='l'>{e(rn)}</td>{cells}<td class='{'pos' if tot > 0 else 'neg'}'><b>{sol(tot)}</b></td><td class='{'pos' if tot2 > 0 else 'neg'}'>{sol(tot2)}</td></tr>")
P.append("</table></div><p class='mut'>* rule never triggered within ~85 s → held to the end of the window. “BEST possible” is hindsight (the single best moment), not a rule.</p>")
# per token
for t in A["tokens"]:
    m = t["mint"]; md = META.get(m, {}); b = t["buy"]
    P.append(f"<h2>{e(t['name'])} — {e(md.get('name', ''))}</h2><table class='kv'>")
    P.append(f"<tr><td>Token (CA)</td><td><code>{m}</code> · <a href='{TOK(m)}'>GMGN</a> · <a href='{SCT(m)}'>Solscan</a></td></tr>")
    if md: P.append(f"<tr><td>Create</td><td>slot {md['S']} · <a href='{TX(md['create_sig'])}'><code>{md['create_sig']}</code></a> · creator <a href='{ACC(md['creator'])}'><code>{md['creator']}</code></a></td></tr>")
    P.append(f"<tr><td>Our buy</td><td>slot {b['slot']} (S+{b['slot'] - t['S']}) · {b['sol'] / 1e9:.4f} SOL into the curve · {b['tok'] / 1e6:,.0f} tokens · whole tx cost {t['cost']:.6f} SOL · <a href='{TX(b['sig'])}'><code>{b['sig']}</code></a></td></tr>")
    for s in t["sells"]:
        P.append(f"<tr><td>Our sell</td><td>slot {s['slot']} (S+{s['slot'] - t['S']}) · {s['sol'] / 1e9:.4f} SOL out of the curve · {s['tok'] / 1e6:,.0f} tokens · <a href='{TX(s['sig'])}'><code>{s['sig']}</code></a></td></tr>")
    chk = "" if t["chk"] is None else f" · same formula at our real sell point: {t['chk']:+.6f}"
    P.append(f"<tr><td>Real result</td><td><b class='{'pos' if t['realized'] > 0 else 'neg'}'>{t['realized']:+.6f} SOL</b> (sum of our wallet's SOL changes in these txs){chk}</td></tr></table>")
    P.append("<div class='wrap'><table><tr><th>#</th><th>S+k</th><th>time</th><th class='l'>side</th><th>SOL</th><th class='l'>wallet</th><th class='l'>tx</th><th>MC (SOL)</th><th>≈MC ($)</th><th>if sold right after</th><th>end of slot</th><th class='l'>note</th></tr>")
    rows = t["rows"]
    usd = GMGN_BOUGHT_USD.get(t["name"], 0) / t["size"] if t["size"] else 0
    P.append(f"<p class='mut'>≈MC($) uses SOL = ${usd:.2f} (GMGN's “Bought $” for our buy ÷ our SOL), so it lines up with GMGN's MC column.</p>")
    for r in rows:
        if r["k"] < -12: continue
        us = r["tag"].startswith("US")
        eos = ""
        if r.get("pnl") is not None and r.get("n"):
            same = [x for x in rows if x.get("n") and x["slot"] == r["slot"]]
            eos = sol(same[-1]["pnl"])
        pnl = "" if r.get("pnl") is None else sol(r["pnl"])
        cls = "" if r.get("pnl") is None else ("pos" if r["pnl"] > 0 else "neg")
        mcv = r["mc_replay"] if (r.get("mc_replay") is not None and r["k"] > 0) else r["mc_chain"]
        note = r["tag"] + ("" if r["k"] <= 0 or r.get("held_real", True) else " (replayed: after our real sell)")
        num = r['n'] if r.get('n') else ('0' if r['k'] == 0 else ('—' if r['k'] > 0 else r['k']))
        P.append(f"<tr class='{'us' if us else ''}'><td>{num}</td><td>{r['sk']}</td><td>{r['time']}</td><td class='l'>{r['side']}</td><td>{r['sol']:.4f}</td>"
                 f"<td class='l'><a href='{ACC(r['user'])}' title='{r['user']}'>{sh(r['user'])}</a></td><td class='l'><a href='{TX(r['sig'])}' title='{r['sig']}'>{sh(r['sig'], 8)}</a></td>"
                 f"<td>{mcv:.2f}</td><td>{mcv * usd / 1000:.2f}K</td><td class='{cls}'>{pnl}</td><td>{eos}</td><td class='l mut'>{e(note)}</td></tr>")
    P.append("</table></div>")
P.append("<p class='mut'>Full rows with complete signatures and wallets: the CSV files next to this page.</p></body></html>")
open(os.path.join(OUT, "trend_rule3_5trades.html"), "w").write("\n".join(P))
print("wrote", os.path.join(OUT, "trend_rule3_5trades.html"))
