#!/usr/bin/env python3
# READ-ONLY, offline: HTML for analyze_sim.py (0.5 SOL placed at a wallet's real landing spot), with Solscan / GMGN links.
import sys, os, json, html
OUT = sys.argv[1]; W = sys.argv[2]
A = json.load(open(os.path.join(OUT, "analysis_sim.json"))); META = json.load(open(os.path.join(OUT, "meta.json")))
TX = lambda s: f"https://solscan.io/tx/{s}"; ACC = lambda a: f"https://gmgn.ai/sol/address/{a}"; TOK = lambda m: f"https://gmgn.ai/sol/token/{m}"
e = html.escape; sh = lambda x, n=6: f"{x[:n]}…{x[-4:]}"; sg = lambda x: f"{x:+.4f}"
toks = A["tokens"]; pick = set(A["pick"])
P = ["""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trend Rule FRZ Test</title>
<style>:root{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd;--pos:#0a7a2f;--neg:#b3261e;--us:#fff4cc;--hd:#f4f4f4}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#eee;--mut:#9a9a9a;--line:#333;--pos:#4cd17a;--neg:#ff7b72;--us:#3a3210;--hd:#1d1d1d}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;max-width:1200px}
h1{font-size:20px}h2{font-size:17px;margin-top:28px;border-top:1px solid var(--line);padding-top:14px}a{color:inherit}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:right;white-space:nowrap}
th{background:var(--hd)}td.l,th.l{text-align:left}.wrap{overflow-x:auto}.pos{color:var(--pos)}.neg{color:var(--neg)}.us td{background:var(--us);font-weight:600}
.mut{color:var(--mut)}.kv td{text-align:left;white-space:normal}code{font-size:12px;word-break:break-all}</style></head><body>"""]
P.append(f"<h1>Trend rules tested on FRZ's last {len(toks)} real buys</h1>")
P.append(f"""<p class="mut">Wallet <a href="{ACC(W)}">{W}</a>. FRZ really bought ~0.001 SOL (a test size), so its own PnL is just fees.
Test: <b>a 0.5 SOL buy placed exactly where FRZ's buy landed</b> (same curve state, same block spot), with Run 2's real costs (buy tx 0.516585 SOL all-in,
sell overhead 0.000091), then every later trade replayed by amount (FRZ's own tiny trades removed). “If sold right after” = our whole bag sold into the curve right after that trade.
Random 5 picked with Python random, seed {A['seed']} (marked ★). MC (chain) = the real on-chain market cap at that trade (what GMGN shows).</p>""")
for title, idx in (("Random 5 (★)", sorted(pick)), (f"All {len(toks)}", list(range(len(toks))))):
    P.append(f"<h2>{e(title)}: PnL in SOL at 0.5 SOL per trade</h2><div class='wrap'><table><tr><th class='l'>rule</th>" + "".join(f"<th>{e(toks[i]['name'])}</th>" for i in idx) + "<th>TOTAL</th><th>realistic</th></tr>")
    for rn, v in A["rules"].items():
        tot = sum(v[i][0] for i in idx); tot2 = sum(v[i][1] for i in idx)
        P.append(f"<tr><td class='l'>{e(rn)}</td>" + "".join(f"<td class='{'pos' if v[i][0] > 0 else 'neg'}'>{sg(v[i][0])}</td>" for i in idx)
                 + f"<td class='{'pos' if tot > 0 else 'neg'}'><b>{sg(tot)}</b></td><td class='{'pos' if tot2 > 0 else 'neg'}'>{sg(tot2)}</td></tr>")
    P.append("</table></div>")
for i, t in enumerate(toks):
    m = t["mint"]; md = META.get(m, {}); b = t["buy"]
    P.append(f"<h2>{'★ ' if i in pick else ''}{e(t['name'])} — {e(md.get('name', ''))}</h2><table class='kv'>")
    P.append(f"<tr><td>Token (CA)</td><td><code>{m}</code> · <a href='{TOK(m)}'>GMGN</a></td></tr>")
    if md: P.append(f"<tr><td>Create</td><td>slot {md['S']} · <a href='{TX(md['create_sig'])}'><code>{md['create_sig']}</code></a> · creator <a href='{ACC(md['creator'])}'><code>{md['creator']}</code></a></td></tr>")
    P.append(f"<tr><td>FRZ real buy</td><td>slot {b['slot']} (S+{b['slot'] - t['S']}) · {b['sol'] / 1e9:.6f} SOL · <a href='{TX(b['sig'])}'><code>{b['sig']}</code></a></td></tr>")
    for s in t["sells"]: P.append(f"<tr><td>FRZ real sell</td><td>slot {s['slot']} (S+{s['slot'] - t['S']}) · <a href='{TX(s['sig'])}'><code>{s['sig']}</code></a></td></tr>")
    P.append(f"<tr><td>FRZ real result</td><td>{t['real']:+.6f} SOL (tiny test size: fees)</td></tr></table>")
    P.append("<div class='wrap'><table><tr><th>#</th><th>S+k</th><th>time</th><th class='l'>side</th><th>SOL</th><th class='l'>wallet</th><th class='l'>tx</th><th>MC chain (SOL)</th><th>if sold right after</th><th class='l'>note</th></tr>")
    for r in t["rows"]:
        if r["n"] is not None and r["n"] < -12: continue
        us = r["tag"].startswith("US"); n = "—" if r["n"] is None else r["n"]
        p = "" if r["pnl"] is None else sg(r["pnl"]); c = "" if r["pnl"] is None else ("pos" if r["pnl"] > 0 else "neg")
        wl = e(r["user"]) if r["user"].startswith("(") else f"<a href='{ACC(r['user'])}' title='{r['user']}'>{sh(r['user'])}</a>"
        P.append(f"<tr class='{'us' if us else ''}'><td>{n}</td><td>{r['sk']}</td><td>{r['time']}</td><td class='l'>{r['side']}</td><td>{r['sol']:.4f}</td><td class='l'>{wl}</td>"
                 f"<td class='l'><a href='{TX(r['sig'])}' title='{r['sig']}'>{sh(r['sig'], 8)}</a></td><td>{r['mc_chain']:.2f}</td><td class='{c}'>{p}</td><td class='l mut'>{e(r['tag'])}</td></tr>")
    P.append("</table></div>")
P.append("</body></html>")
open(os.path.join(OUT, "trend_rules_FRZ_test.html"), "w").write("\n".join(P)); print("wrote", os.path.join(OUT, "trend_rules_FRZ_test.html"))
