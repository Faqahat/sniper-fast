#!/usr/bin/env python3
# READ-ONLY, offline: presentable self-contained HTML on 9qz7cW's last create-slot snipes (snipes15.json + facts.json made
# by facts.py). CSS reused from ops/snipers/w9sh/9Sh2fd_snipes.html. Every tx / wallet / token is a link.
import os, json, html, statistics, collections, datetime, re
HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "snipes15.json"))); W = D["wallet"]; SN = D["snipes"]
F = json.load(open(os.path.join(HERE, "facts.json")))
BAD = ["nigg", "nigr", "niga", "fagg", "faggot", "retard", "kike", "chink", "spic", "tranny", "cunt", "fuck", "shit", "bitch", "whore", "slut", "rape", "hitler", "nazi",
       "coon", "dyke", "negro", "neeg", "jew", "pussy", "dick", "cock", "porn", "sex", "anal", "reich"]
BADRE = re.compile("|".join(BAD), re.I)
def mask(s): return "[masked]" if s and BADRE.search(s) else (s or "")
e = html.escape
TX = lambda s: f"https://solscan.io/tx/{s}"; ACC = lambda a: f"https://solscan.io/account/{a}"; GW = lambda a: f"https://gmgn.ai/sol/address/{a}"; GT = lambda m: f"https://gmgn.ai/sol/token/{m}"
def sh(x, a=4, b=4):
    s = f"{x[:a]}…{x[-b:]}"
    return "[masked]" if BADRE.search(x[:a]) else s
def ln(url, text, cls=""): return f'<a href="{url}" target="_blank" rel="noopener"{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{e(text)}</a>'
utc = lambda t: datetime.datetime.fromtimestamp(t + 5 * 3600, datetime.timezone.utc).strftime("%b %d, %H:%M:%S") if t else "—"   # PKT = UTC+5 (owner's time zone)
def sol(x, d=4): return f"{x:.{d}f}" if x is not None else "—"
def pnl(x): return f'<span class="{"pos" if x > 0 else "neg"}">{x:+.3f}</span>'
for s in SN:
    # its buy can sit right behind the create tx, where the collector's glued-bundle rule would call it "dev bundle": it is an outside buyer
    for b in s["block"]:
        if b["who"] == W: b["role"] = "sniper"
    last_ins = max([b["i"] for b in s["block"] if b["role"] != "sniper"] or [0])
    for b in s["block"]: b["pos"] = b["i"] - last_ins
    me = next((b for b in s["block"] if b["who"] == W), None); outs = [b for b in s["block"] if b["role"] == "sniper"]
    if me: s["pos"] = me["pos"]; s["rank"] = 1 + sum(1 for b in outs if b["i"] < me["i"]); s["n_out"] = len(outs)
    bund = [b for b in s["block"] if b["role"] in ("dev bundle", "insider")]
    s["bundle_sol"] = sum(b["sol"] for b in bund); s["bundle_txs"] = len(bund)
    s["tip_total"] = sum(t[2] for t in s["tip_to"]); s["tip_svc"] = ", ".join(sorted({t[0] if len(t[0]) < 20 else t[0][:6] + "…" for t in s["tip_to"]})) or "—"
    s["cost_pct"] = ((s["prio"] or 0) + s["tip_total"]) / s["size"] * 100
    s["first_sell"] = s["sells"][0]["ds"] if s["sells"] else None; s["last_sell"] = s["sells"][-1]["ds"] if s["sells"] else None
    s["label"] = mask(s["symbol"]) or sh(s["mint"])
net = sum(s["result"] for s in SN); wins = sum(1 for s in SN if s["result"] > 0)
CSS = open(os.path.join(HERE, "snipes_css.txt")).read()
P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>9qz7cW Sniper Study</title><style>{CSS}</style></head><body><div class='wrap'>"]
P.append(f"""<h1>How wallet 9qz7cW snipes pump.fun launches</h1>
<p class="mut">A study of its last {len(SN)} create-slot snipes, built only from on-chain data and our collector. Every transaction, wallet and token below links to Solscan or GMGN so you can check it.</p>
<div class="chips"><span class="chip">Wallet {ln(GW(W), sh(W, 6, 4))} · {ln(ACC(W), "Solscan")}</span><span class="chip">Snipes {utc(min(s['create_bt'] for s in SN))} → {utc(max(s['create_bt'] for s in SN))} PKT</span><span class="chip">Ledger: {e(F['ledger_span'])}</span></div>""")
P.append(f"""<div class="card tldr"><b>In one paragraph</b><ul>
{''.join(f'<li>{x}</li>' for x in F['tldr_html'])}</ul></div>""")
P.append(f"""<div class="grid">
<div class="stat"><b>{sum(1 for s in SN if s['rank'] == 1)}/{len(SN)}</b><span>first outside buyer here ({F['first_rate']} of all its create-slot fills)</span></div>
<div class="stat"><b>{F['arr_med']} ms</b><span>median arrival in our feed after the create (we land at ~75 ms)</span></div>
<div class="stat"><b>{F['spend_med']}</b><span>median landing spend per snipe (priority fee or Jito tip)</span></div>
<div class="stat"><b>{F['snipe_pnl']}</b><span>SOL on its snipes in our collector windows (~{F['coll_hours']} h)</span></div>
<div class="stat"><b>{F['later_pnl']}</b><span>SOL on its later (momentum) buys, same windows</span></div>
<div class="stat"><b>{pnl(net)}</b><span>net SOL over these {len(SN)} snipes ({wins} wins)</span></div></div>""")
# anatomy: the snipe with the most sells among the picks (shows the ladder)
t = max(SN, key=lambda s: (len(s["sells"]), s["result"]))
P.append(f"""<h2>Anatomy of one snipe: {e(t['label'])} <span class="badge m">measured</span></h2>
<p>Token {ln(GT(t['mint']), mask(t['name']) or t['label'])} ({ln(ACC(t['mint']), sh(t['mint'], 6, 4))}), created {utc(t['create_bt'])} PKT in block {t['S']} by {ln(GW(t['creator']), sh(t['creator'], 6, 4))}.</p>
<ol class="steps">
<li><b>The dev creates the token and buys in the same transaction</b> ({ln(TX(t['create_sig']), 'create tx')}): {sol(t['dev_sol'], 2)} SOL. {(str(t['bundle_txs']) + (' more buy is' if t['bundle_txs'] == 1 else ' more buys are') + ' glued right behind it (' + sol(t['bundle_sol'], 2) + ' SOL): the dev' + chr(39) + 's bundle.') if t['bundle_txs'] else 'No bundle is glued behind it.'}</li>
<li><b>9qz7cW buys {sol(t['size'], 3)} SOL</b> ({ln(TX(t['buy_sig']), 'buy tx')}) {t['pos']} transactions after the bundle in the same block; it is outside buyer #{t['rank']} of {t['n_out']}. Our engine saw its transaction {sol(t['arr_ms'], 1) if t['arr_ms'] is not None else '—'} ms after the create.</li>
<li><b>It paid</b> {sol(t['prio'], 4)} SOL priority fee{f" and a {sol(t['tip_total'], 4)} SOL tip ({e(t['tip_svc'])})" if t['tip_total'] else ""}: {t['cost_pct']:.1f}% of the buy.</li>
<li><b>It sold in {len(t['sells'])} pieces</b>: {', '.join(f"{x['frac'] * 100:.0f}% after {x['ds']} slots (x{x['x']})" for x in t['sells'][:6])}{' …' if len(t['sells']) > 6 else ''}.</li>
<li><b>Result</b> (every SOL change of its wallet on this token, failed copies included): {pnl(t['result'])} SOL.</li></ol>""")
P.append(f"""<h3>Its buy transaction, instruction by instruction</h3><div class="card">
<div class="ix"><span class="n">#1</span><div><b>Advance durable nonce</b> ({ln(ACC(t['nonce']), sh(t['nonce'], 6, 4)) if t['nonce'] else '—'}; it rotates {F['n_nonce']} nonce accounts). No fresh blockhash is needed, and only one of the copies it sends can land.</div></div>
<div class="ix"><span class="n">#2</span><div><b>Compute limit</b> set to {t['cul'] or '—'} units for {t['cu'] or '—'} used (about 400 spare: the bot pre-computes it). Transaction format v{t['version']}: the priority fee ({sol(t['prio'], 4)} SOL) sits in the v1 header.</div></div>
<div class="ix"><span class="n">#3–4</span><div><b>Creates its token account directly</b> (createAccountWithSeed + initializeAccount3, Token-2022), not through the Associated Token Account program.</div></div>
<div class="ix"><span class="n">#5</span><div><b>pump.fun buy_exact_quote_in</b>: spend a round SOL amount (here {sol(t['size'] * 1.0125, 2)} SOL incl. pump fees) with a minimum-tokens-out limit {F['tol_text']}.</div></div>
<div class="ix"><span class="n">#6</span><div><b>Optional tip transfer</b>: Jito tip accounts, or a vanity "b1oo…" landing account. The same buy also goes out as a priority-fee copy with no tip, and as cheap backup copies through its router program {ln(ACC('2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj'), '2eFuLSK4…')} with 0.001 SOL tips to LandX, Nozomi, Helius, Everstake, Node1.</div></div></div>""")
# cost picture
P.append(f"""<h2>What its landing costs</h2><div class="card">
<p>{F['cost_html']}</p></div>""")
# the snipes table
P.append(f"""<h2>The {len(SN)} snipes <span class="badge m">measured</span></h2><p class="mut small">Position = transactions between the dev's bundle and its buy in the create block. Rank = its place among outside buyers in that block. Arrival = when our engine saw its tx (ms after the create). Result = sum of its wallet's SOL changes on the token (buy, every sell, failed copies).</p>
<div class="tbl"><table><tr><th class="l">Token</th><th class="l">Created (PKT)</th><th>Dev + bundle SOL</th><th class="l">Its buy</th><th>Arrival</th><th>Position</th><th>Rank</th><th>SOL</th><th>Priority</th><th class="l">Tip</th><th>Cost</th><th>Sells</th><th>Held (slots)</th><th>Result</th></tr>""")
for s in SN:
    P.append(f"<tr><td class='l'>{ln(GT(s['mint']), s['label'])}</td><td class='l'>{utc(s['create_bt'])}</td><td>{sol(s['dev_sol'], 2)} + {sol(s['bundle_sol'], 2)}</td>"
             f"<td class='l'>{ln(TX(s['buy_sig']), sh(s['buy_sig'], 6, 4))}</td><td>{sol(s['arr_ms'], 0) if s['arr_ms'] is not None else '—'}</td><td>+{s['pos']}</td><td>{s['rank']}/{s['n_out']}</td><td>{sol(s['size'], 3)}</td><td>{sol(s['prio'], 4)}</td>"
             f"<td class='l'>{(sol(s['tip_total'], 4) + ' ' + e(s['tip_svc'])) if s['tip_total'] else '—'}</td><td>{s['cost_pct']:.1f}%</td><td>{len(s['sells'])}</td><td>{(str(s['first_sell']) + '–' + str(s['last_sell'])) if s['first_sell'] is not None else '—'}</td><td>{pnl(s['result'])}</td></tr>")
P.append(f"<tr><td class='l' colspan='13'><b>Total ({wins} wins, {len(SN) - wins} losses)</b></td><td><b>{pnl(net)}</b></td></tr></table></div>")
P.append(f"<p class='small mut'>{F['table_note']}</p>")
# per-block detail
P.append("<h2>Every create block, buyer by buyer</h2><p class='mut small'>Each section lists the token's buyers in its create block: the dev, the dev's bundle, 9qz7cW (highlighted), and the other snipers with what they paid.</p>")
for s in SN:
    P.append(f"<details><summary>{e(s['label'])} — position +{s['pos']}, rank {s['rank']}/{s['n_out']}, result {s['result']:+.3f} SOL</summary>"
             f"<p class='small mut'>Token {ln(GT(s['mint']), mask(s['name']) or s['mint'])} · creator {ln(GW(s['creator']), sh(s['creator'], 6, 4)) if s['creator'] else '—'} · block {s['S']} · {ln(TX(s['create_sig']), 'create tx')}</p>"
             "<div class='tbl'><table><tr><th class='l'>Role</th><th>Position</th><th class='l'>Wallet</th><th>SOL</th><th>Priority</th><th class='l'>Tips</th><th class='l'>Tx</th></tr>")
    for b in sorted(s["block"], key=lambda b: b["i"]):
        me = b["who"] == W; role = "<b>9qz7cW</b>" if me else e(b["role"])
        tips = ", ".join(f"{e(str(tp[0]))} {sol(tp[1], 4)}" for tp in b["tips"]) or "—"
        P.append(f"<tr class='{'me' if me else ''}'><td class='l'>{role}</td><td>{b['pos']:+d}</td><td class='l'>{ln(GW(b['who']), sh(b['who']))}</td><td>{sol(b['sol'], 3)}</td><td>{sol(b['prio'], 4)}</td><td class='l'>{tips}</td><td class='l'>{ln(TX(b['sig']), sh(b['sig'], 5, 3))}</td></tr>")
    sells = "".join(f"<li>{ln(TX(x['sig']), sh(x['sig'], 5, 3))}: {x['frac'] * 100:.0f}% of the position after {x['ds']} slots at x{x['x']} ({sol(x['sol'], 3)} SOL)</li>" for x in s["sells"])
    P.append(f"</table></div><p class='small'><b>Its sells</b></p><ul class='small'>{sells or '<li>none in the collector window</li>'}</ul></details>")
P.append(f"""<h2>9qz7cW vs us</h2><div class="tbl"><table><tr><th class="l"></th><th class="l">9qz7cW</th><th class="l">Our engine</th></tr>
{''.join(f"<tr><td class='l'>{e(a)}</td><td class='l'>{b}</td><td class='l'>{c}</td></tr>" for a, b, c in F['vs_us'])}</table></div>""")
P.append(f"""<h2>Can we copy it? <span class="badge i">paper replay</span></h2><div class="card">{F['copy_html']}</div>""")
P.append(f"""<h2>Method and references</h2><div class="card small">{F['method_html']}</div>""")
P.append(f"<footer>Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%b %d, %Y %H:%M')} UTC ({(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5)).strftime('%H:%M')} PKT) from on-chain data (read-only). Scripts: ops/overnight/q9z (collect15.py, render15.py, facts.py).</footer></div></body></html>")
open(os.path.join(HERE, "9qz7cW_snipes.html"), "w").write("\n".join(P))
print("wrote 9qz7cW_snipes.html", sum(len(p) for p in P) // 1024, "KB")
