#!/usr/bin/env python3
# READ-ONLY, offline: the presentable HTML page on CWiNFA's last 15 snipes (snipes15.json) + key ledger / study numbers
# (pnl.json, q6.json, funding.json, guard.txt, exits.json). Same look as ops/snipers/w9sh/9Sh2fd_snipes.html (its CSS).
# Every tx / wallet / token is a link. Offensive words in token names or wallet prefixes are shown as [masked].
import os, re, json, html, statistics, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "snipes15.json"))); W = D["wallet"]; SN = D["snipes"]
PN = json.load(open(os.path.join(HERE, "pnl.json"))); Q6 = json.load(open(os.path.join(HERE, "q6.json")))
F = json.load(open(os.path.join(HERE, "funding.json")))
CSS = open(os.path.join(HERE, "style_9sh.css")).read()
BAD = re.compile(r"(n[i1]gg|f[a@]gg|retard|kike|chink|spic\b|tranny|cum\b|cum[^a-z]|semen|cuck|fuck|shit|cunt|whore|slut|porn|rape|nazi|hitler|pussy|dick\b|cock\b|foid|jeet)", re.I)
def mask(s):
    if not s: return s
    return "[masked]" if BAD.search(s) else s
e = lambda s: html.escape(str(s)) if s is not None else ""
TX = lambda s: f"https://solscan.io/tx/{s}"; ACC = lambda a: f"https://solscan.io/account/{a}"; GW = lambda a: f"https://gmgn.ai/sol/address/{a}"; GT = lambda m: f"https://gmgn.ai/sol/token/{m}"
def sh(x, a=4, b=4):
    s = f"{x[:a]}…{x[-b:]}"
    return "[masked]" if BAD.search(x[:a]) or BAD.search(x[-b:]) else s
def ln(url, text, cls=""): return f'<a href="{url}" target="_blank" rel="noopener"{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{e(text)}</a>'
utc = lambda t: (datetime.datetime.fromtimestamp(t, datetime.timezone.utc) + datetime.timedelta(hours=5)).strftime("%b %d, %H:%M:%S") if t else "—"   # PKT = UTC+5
def sol(x, d=4): return f"{x:.{d}f}"
def pnl(x): return f'<span class="{"pos" if x > 0 else "neg"}">{x:+.3f}</span>'
ROUTER = "5DVzy5EpG2xVxrwwuyZPDe9EpraUnGh7ZgYABwizzNVu"; DEV = "A5GQaNc37XMKPhn1hbzc12cvBaXj7Uk1qNmMeS9pRfAz"; ALT = "B73XBTEmKwFGR7uu8s3NtHKiQoYPsF2rYHJB87NwxAgv"
SELLT = {"010000": "normal", "010101": "dev/bundle sold (urgent)", "010500": "quick (type 5)", "010601": "take-profit (urgent)", "010701": "instant (urgent)", "010901": "type 9"}
net15 = sum(s["realized"] for s in SN); wins15 = sum(1 for s in SN if s["realized"] > 0)
first15 = sum(1 for s in SN if s["ahead"] == 0)
cost = PN["costs"]; prof = PN["profit"]; w0, w1 = PN["window"]; hrs = (w1 - w0) / 3600
toks = list(PN["tokens"].values()); ntok = len(toks)
def q6(k): return Q6.get(k) or {}
P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>CWiNFA Snipe Study</title><style>{CSS}</style></head><body><div class='wrap'>"]
P.append(f"""<h1>How wallet CWiNFA snipes pump.fun launches</h1>
<p class="mut">Its last {len(SN)} snipes inside our collector data, plus its full on-chain ledger for the last {hrs:.0f} hours. Read-only. Every transaction, wallet and token links to Solscan or GMGN.</p>
<div class="chips"><span class="chip">Wallet {ln(GW(W), sh(W, 6, 4))} · {ln(ACC(W), "Solscan")}</span><span class="chip">These snipes {utc(min(s['buy_bt'] for s in SN))} → {utc(max(s['buy_bt'] for s in SN))} PKT</span><span class="chip">Ledger {utc(w0)} → {utc(w1)} PKT · {ntok:,} round trips</span></div>""")
P.append(f"""<div class="card tldr"><b>In short</b><ul>
<li><b>Its own bot, not a commercial one.</b> Every trade goes through router program {ln(ACC(ROUTER), sh(ROUTER, 6, 4))}, and in the last {hrs:.0f} h nobody else used it ({F['router_sigs_n']:,} router transactions; all 60 sampled were this wallet's). The program's upgrade key also owns the wallet's address lookup table. There is no bot-fee transfer anywhere. <span class="badge m">measured</span> <span class="badge i">"own bot" inferred</span></li>
<li><b>Fixed recipe:</b> every buy spends exactly <b>1 SOL</b>, pays a <b>0.003 SOL</b> priority fee and a <b>0.003 SOL tip</b> to one of about ten landing services, and is sold in <b>one sell</b>, a median <b>7 slots (~1.5 s)</b> later.</li>
<li><b>It is first in line about half the time:</b> {first15} of these {len(SN)}, and 48% of 516 snipes in our windows. Our engine sees its buy a median <b>49 ms</b> after the create (p25 31, p75 109 ms).</li>
<li><b>Loose price guard:</b> the buy fails only if the price is above about <b>1.37×</b> the post-bundle price, which happened 63 times against 1,312 fills. Sells have no guard at all (minimum out = 1 lamport).</li>
<li><b>Result:</b> <b>{prof:+.1f} SOL after every cost</b> in {hrs:.0f} h, about {prof / hrs * 24:+.1f} SOL a day. Win rate is only 38%; take-profit sells and first-in-line fills carry it.</li></ul></div>""")
P.append(f"""<div class="grid">
<div class="stat"><b>{pnl(prof)}</b><span>SOL after all costs, {hrs:.0f} h</span></div>
<div class="stat"><b>{ntok:,}</b><span>snipes (1 buy + 1 sell each)</span></div>
<div class="stat"><b>48%</b><span>first outside buyer (516 in our windows)</span></div>
<div class="stat"><b>49 ms</b><span>median arrival in our feed</span></div>
<div class="stat"><b>0.6%</b><span>priority + tip per 1 SOL buy</span></div>
<div class="stat"><b>{pnl(net15)}</b><span>SOL over these {len(SN)} ({wins15} wins)</span></div></div>""")
# ---------------- anatomy
t = max((s for s in SN if s["ahead"] == 0), key=lambda s: s["realized"])
fol = t["after"][:3]
P.append(f"""<h2>Anatomy of one snipe: {e(mask(t['symbol']))} <span class="badge m">measured</span></h2>
<p>Token {ln(GT(t['mint']), mask(t['name']) or t['symbol'])} ({ln(ACC(t['mint']), sh(t['mint'], 6, 4))}), created {utc(t['create_bt'])} PKT in slot {t['S']} by {ln(GW(t['deployer']), sh(t['deployer'], 6, 4))}.</p>
<ol class="steps">
<li><b>The dev creates the token and buys</b> {sol(t['dev_sol'], 2)} SOL in the same transaction ({ln(TX(t['create_sig']), 'create tx')}). {t['bundle_legs']} more dev buys are glued right behind it ({sol(t['bundle_sol'], 2)} SOL): the dev's bundle.</li>
<li><b>CWiNFA is the first outside buyer</b>, in the same slot, with exactly 1 SOL ({ln(TX(t['buy_sig']), 'buy tx')}). Our engine saw it {t['arrival_ms']:.0f} ms after the create. Its average price was {t['entry_mult']:.3f}× the post-bundle price (its own 1 SOL moves the price ~3%).</li>
<li><b>It paid</b> a {sol(t['fee'] - 0.000005, 4)} SOL priority fee and a {sol(t['tips'][0][1], 4)} SOL tip to {e(t['tips'][0][0])} ({ln(ACC(t['tips'][0][2]), sh(t['tips'][0][2], 6, 4))}).</li>
<li><b>Buyers came in behind it:</b> {', '.join(f"{sol(f['sol'], 2)} SOL ({ln(GW(f['who']), sh(f['who']))})" for f in fol) if fol else 'none in the next slots'}.</li>
<li><b>It sold everything in one sell</b> {t['sell']['hold_slots']} slots later ({ln(TX(t['sell']['sig']), 'sell tx')}, type "{e(SELLT.get(t['sell']['flags'], t['sell']['flags']))}") at {t['sell']['mult']:.3f}× its entry price. Net result after fees and tips: {pnl(t['realized'])} SOL.</li></ol>""")
v0 = next((s for s in SN if str(s["version"]) == "0"), t)
P.append(f"""<h3>Its buy transaction, instruction by instruction</h3><div class="card">
<div class="ix"><span class="n">#1</span><div><b>Advance durable nonce</b> (e.g. {ln(ACC(t['nonce']), sh(t['nonce'], 6, 4))}). It rotates <b>30 nonce accounts</b>, all owned by the wallet, so a buy is signed in advance without a fresh blockhash. All copies of one buy share one nonce, so only one copy can ever land.</div></div>
<div class="ix"><span class="n">#2–4</span><div><b>Compute budget</b> (v0 copies only): 80,000 compute-unit limit at 37.44 M micro-lamports = <b>0.003 SOL priority</b>. The v1 copies carry the same fee in the transaction header. About two thirds of its landed buys are v0 (with lookup table {ln(ACC(ALT), sh(ALT, 6, 4))}) and one third v1.</div></div>
<div class="ix"><span class="n">#5</span><div><b>Its own router</b> {ln(ACC(ROUTER), sh(ROUTER, 6, 4))}: arguments "spend 1,000,000,000 lamports", "minimum tokens out" and an 8-character seed (the first 8 characters of the mint). Inside, the router creates the token account (createAccountWithSeed + InitializeAccount3) and calls pump.fun's <span class="mono">BuyExactQuoteInV3</span>. ~59k compute units in total.</div></div>
<div class="ix"><span class="n">#6</span><div><b>Tip</b>: 0.003 SOL to one landing service. Landed buys used Nozomi 24%, Astralane 20%, Flashblock 19%, Helius 18%, Stellium 7%, Jito 6%, and smaller shares to NextBlock, bloXroute and two unlabelled accounts. One tip per transaction: <i>most likely one signed copy per service, sent at once</i> <span class="badge i">inferred</span>.</div></div>
<p class="small mut">Sell: the same router calls <span class="mono">SellV3</span> for all tokens with a minimum of 1 lamport out (no guard), tip 0.0011 SOL and a ~0 priority fee. When the dev or bundle sells, or a take-profit fires, the sell is sent "urgent": 0.0015 SOL tip + 0.00054 SOL priority.</p></div>""")
# ---------------- cost bar (1 SOL round trip)
nb = cost["n"]
parts = [("pump.fun fee, buy side", cost["buy_fees"] / nb * 100, "#9aa1ab"), ("pump.fun fee, sell side", cost["sell_fees"] / nb * 100, "#c3c7cd"), ("priority fees", (cost["fee_b"] + cost["fee_s"]) / nb * 100, "#4cc38a"), ("tips", (cost["tips_b"] + cost["tips_s"]) / nb * 100, "#2f6fed")]
tot = sum(p[1] for p in parts)
P.append(f"""<h2>What one 1 SOL round trip costs it</h2><div class="card">
<div class="bar">{''.join(f'<span style="width:{p[1] / tot * 100:.1f}%;background:{p[2]}"></span>' for p in parts)}</div>
<div class="legend">{''.join(f'<span><i style="background:{p[2]}"></i>{e(p[0])}: {p[1]:.2f}%</span>' for p in parts)}</div>
<p class="small mut">About {tot:.1f}% of the 1 SOL per round trip, averaged over {nb:,} trades. pump.fun's fees are most of it; landing (priority + tips) is {(cost['fee_b'] + cost['fee_s'] + cost['tips_b'] + cost['tips_s']) / nb * 100:.2f}%. Before any fee its trades made {cost['gross']:+.1f} SOL on the curve; after fees, tips and failed transactions {prof:+.1f} SOL. There is no separate bot fee.</p></div>""")
# ---------------- the 15
P.append(f"""<h2>The {len(SN)} snipes <span class="badge m">measured</span></h2><p class="mut small">Ahead = outside buy transactions between the dev's bundle and its buy (0 = first in line). ms = when our engine saw its buy, after the create. Entry = its average price ÷ the post-bundle price. Result = the sum of its wallet's SOL changes over the buy and the sell, plus the token-account rent it gets back later.</p>
<div class="tbl"><table><tr><th class="l">Token</th><th class="l">Created (PKT)</th><th>Dev + bundle SOL</th><th class="l">Its buy</th><th>Slot</th><th>Ahead</th><th>ms</th><th class="l">Tip</th><th>Entry</th><th class="l">Its sell</th><th>Held</th><th class="l">Sell type</th><th>Result</th></tr>""")
for s in SN:
    se = s["sell"] or {}
    P.append(f"<tr><td class='l'>{ln(GT(s['mint']), mask(s['symbol']) or sh(s['mint']))}</td><td class='l'>{utc(s['create_bt'])}</td><td>{sol(s['dev_sol'], 2)} + {sol(s['bundle_sol'], 2)}</td>"
             f"<td class='l'>{ln(TX(s['buy_sig']), sh(s['buy_sig'], 6, 4))} <span class='badge'>v{s['version']}</span></td><td>+{s['slot_d']}</td><td>{s['ahead']}</td><td>{s['arrival_ms']:.0f}</td>" if s['arrival_ms'] is not None else
             f"<tr><td class='l'>{ln(GT(s['mint']), mask(s['symbol']) or sh(s['mint']))}</td><td class='l'>{utc(s['create_bt'])}</td><td>{sol(s['dev_sol'], 2)} + {sol(s['bundle_sol'], 2)}</td>"
             f"<td class='l'>{ln(TX(s['buy_sig']), sh(s['buy_sig'], 6, 4))} <span class='badge'>v{s['version']}</span></td><td>+{s['slot_d']}</td><td>{s['ahead']}</td><td>—</td>")
    P.append(f"<td class='l'>{e(s['tips'][0][0]) if s['tips'] else '—'}</td><td>{s['entry_mult']:.3f}×</td><td class='l'>{ln(TX(se['sig']), sh(se['sig'], 6, 4)) if se else '—'}</td>"
             f"<td>{se.get('hold_slots', '—')} slots</td><td class='l'>{e(SELLT.get(se.get('flags'), se.get('flags')))}</td><td>{pnl(s['realized'])}</td></tr>")
P.append(f"<tr><td class='l' colspan='12'><b>Total ({wins15} wins, {len(SN) - wins15} losses)</b></td><td><b>{pnl(net15)}</b></td></tr></table></div>")
# ---------------- per block
P.append("<h2>Every launch, buyer by buyer</h2><p class='mut small'>Each section lists the buyers up to its buy in chain order (the dev, the dev's bundle, outside buyers, it highlighted), then the first outside buyers after it. Fee = network fee (base + priority); tips = transfers to landing services.</p>")
for s in SN:
    P.append(f"<details><summary>{e(mask(s['symbol']) or sh(s['mint']))}: {'first in line' if s['ahead'] == 0 else str(s['ahead']) + ' outside buy' + ('s' if s['ahead'] > 1 else '') + ' ahead'}, slot +{s['slot_d']}, result {s['realized']:+.3f} SOL</summary>"
             f"<p class='small mut'>Token {ln(GT(s['mint']), mask(s['name']) or s['mint'])} · deployer {ln(GW(s['deployer']), sh(s['deployer'], 6, 4))} · slot {s['S']} · {ln(TX(s['create_sig']), 'create tx')}</p>"
             "<div class='tbl'><table><tr><th class='l'>Role</th><th>Slot</th><th>Position</th><th class='l'>Wallet</th><th>SOL</th><th>Fee</th><th>Tips</th><th class='l'>Tx</th></tr>")
    for b in s["block"]:
        me = b["role"] == "CWiNFA"
        P.append(f"<tr class='{'me' if me else ''}'><td class='l'>{'<b>CWiNFA</b>' if me else e(b['role'])}</td><td>+{b['slot_d']}</td><td>{b['pos']:+d}</td><td class='l'>{ln(GW(b['who']), sh(b['who']))}</td>"
                 f"<td>{sol(b['sol'], 3)}</td><td>{sol(b['fee'], 4)}</td><td>{sol(b['tips'], 4)}</td><td class='l'>{ln(TX(b['sig']), sh(b['sig'], 5, 3))}</td></tr>")
    for b in s["after"]:
        P.append(f"<tr><td class='l mut'>after it</td><td>+{b['slot_d']}</td><td>{b['pos']:+d}</td><td class='l'>{ln(GW(b['who']), sh(b['who']))}</td><td>{sol(b['sol'], 3)}</td><td>{sol(b['fee'], 4)}</td><td>{sol(b['tips'], 4)}</td><td class='l'>{ln(TX(b['sig']), sh(b['sig'], 5, 3))}</td></tr>")
    P.append("</table></div></details>")
# ---------------- vs us
P.append(f"""<h2>It vs us</h2><div class="tbl"><table><tr><th class="l"></th><th class="l">CWiNFA</th><th class="l">Our engine</th></tr>
<tr><td class="l">Arrival after the create</td><td class="l">median 49 ms in our feed (p25 31, p75 109); 69% land in the create slot</td><td class="l">~75 ms (45 ms after the planned upgrade)</td></tr>
<tr><td class="l">Landing spend</td><td class="l">0.003 SOL priority + 0.003 SOL tip to one of ~10 services per copy (0.6% of 1 SOL)</td><td class="l">larger tips / priority (we model ~2% of 0.5 SOL)</td></tr>
<tr><td class="l">Transaction</td><td class="l">own router, durable nonce (30 accounts), v0 + lookup table and v1 copies, token account by seed</td><td class="l">recent blockhash, Associated Token Account program</td></tr>
<tr><td class="l">Price guard</td><td class="l">fails above ~1.37× the post-bundle price; sells unguarded</td><td class="l">fails above 1.01× the post-bundle price</td></tr>
<tr><td class="l">Size</td><td class="l">always 1 SOL</td><td class="l">0.5 SOL</td></tr>
<tr><td class="l">Exit</td><td class="l">one sell: ~1.5 s normal; same-slot dump when the dev or bundle sells; take-profit around 1.3–1.5×</td><td class="l">sell at the end of the next slot</td></tr></table></div>""")
# ---------------- copy test (owner's rule: profit must come from generic flow, not from specific bots)
RS = json.load(open(os.path.join(HERE, "rescore_summary.json"))); WK = json.load(open(os.path.join(HERE, "walk10_summary.json")))
GS = json.load(open(os.path.join(HERE, "generic_summary.json"))); TOPC = json.load(open(os.path.join(HERE, "after_us_counts.json")))[:10]
FASTN = len(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
def rs(k, f="ours"): return (RS.get(k) or {}).get(f, 0.0)
def wk(k, f="generic_slip"): return ((WK.get(k) or {}).get(f) or [0, 0, 0])
def fl(k): return (WK.get(k) or {}).get("fills", [0, 0])
top_txt = ", ".join(f"{ln(GW(u), sh(u))} ({n})" for u, n, _ in [x for x in TOPC if not x[0].startswith("CWiNFA")][:6])
P.append(f"""<h2>Can we copy it? <span class="badge i">replay, paper only</span></h2>
<p>Exact pump.fun curve replay of the {7875:,} launches with our engine's timelines (Oct 22 22:10 → Oct 23 07:39 PKT): our buy at 45 or 75 ms (block-order placement), our 1% guard, 0.5 SOL. The owner's rule: the profit must come from <b>generic flow</b> (ordinary bots and people), not from specific fast bots buying right after us. So every idea is re-scored with the buys after our entry of CWiNFA and of all {FASTN} <b>fast sniper wallets</b> removed (wallets that buy within 2 slots of the create on 5+ launches and on at least half of their launches), and with followers our buy prices out made to fail ("slip").</p>
<div class="tbl"><table><tr><th class="l">Idea (its deployer list + our gate)</th><th>45 ms</th><th>75 ms</th><th class="l">Verdict</th></tr>
<tr><td class="l">Sell at the end of the next slot: as replayed</td><td>{rs('b|45|base'):+.2f}</td><td>{rs('b|75|base'):+.2f}</td><td class="l" rowspan="2"><b>rejected</b>: depends on CWiNFA and fast snipers</td></tr>
<tr><td class="l">… generic flow only, with slip</td><td>{rs('b|45|noCW_fast_top_slip'):+.2f}</td><td>{rs('b|75|noCW_fast_top_slip'):+.2f}</td></tr>
<tr><td class="l">Its pattern (1 SOL, sell at 1 s): as replayed → generic only</td><td>{rs('b|45|base', 'its'):+.2f} → {rs('b|45|noCW_fast_top_slip', 'its'):+.2f}</td><td>{rs('b|75|base', 'its'):+.2f} → {rs('b|75|noCW_fast_top_slip', 'its'):+.2f}</td><td class="l"><b>rejected</b>: same</td></tr>
<tr><td class="l">Hold 10 s (gate on our own 10 s results), generic only + slip, newer run</td><td>{wk('R2|45|t10|gate')[0]:+.2f} ({fl('R2|45|t10|gate')[0]} fills)</td><td>{wk('R2|75|t10|gate')[0]:+.2f} ({fl('R2|75|t10|gate')[0]} fills)</td><td class="l" rowspan="2"><b>unproven</b>: generic flow carries it on the newer run, the older run is flat</td></tr>
<tr><td class="l">… same, older run (no timelines, pessimistic placement)</td><td>{wk('R1|45|t10|gate')[0]:+.2f}</td><td>{wk('R1|75|t10|gate')[0]:+.2f}</td></tr></table></div>
<p class="small mut">With the fast bots removed, {RS.get('b|45|nobuy|noCW_fast_top', [0, 0])[0] * 100:.0f}% of our 45 ms fills have no outside buy at all between our buy and an end-of-next-slot sell (2% with them). The most frequent buyers right after us are all fast snipers: CWiNFA itself (in {TOPC[0][1]} of our fills), then {top_txt} (number of fills). Bigger bundled pools without its selection lose at every hold, so the value is in its picks, and those picks rise over 2–10 s on generic flow (median 1.048× the post-bundle price at +10 s with every fast bot removed, against 0.945× for skipped bundled launches).</p>""")
P.append(f"""<h2>Method and references</h2><div class="card small">
<p><b>Data.</b> All {len(json.load(open(os.path.join(HERE, 'sigs_CWiNFA.json')))):,} transactions of the wallet the owner's RPC still holds ({utc(w0)} → {utc(w1)} PKT), decoded instruction by instruction; each launch rebuilt in chain order from our collector; arrival times from our engine's logs.</p>
<p><b>Accounts.</b> Wallet {ln(GW(W), W)} · router program {ln(ACC(ROUTER), sh(ROUTER, 8, 4))} · its upgrade key and lookup-table authority {ln(ACC(DEV), sh(DEV, 8, 4))} · lookup table {ln(ACC(ALT), sh(ALT, 8, 4))}.</p>
<p><b>Not known.</b> Who runs it, and how many copies of each buy it sends: durable-nonce copies that lose never appear on chain.</p></div>""")
P.append(f"<footer>Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%b %d, %Y %H:%M')} UTC ({(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5)).strftime('%H:%M')} PKT) from on-chain data (read-only). Scripts: ops/overnight/cwinfa (fetch.py, ledger_cw.py, pnl.py, coll.py, collect15_cw.py, render_cw.py).</footer></div></body></html>")
open(os.path.join(HERE, "CWiNFA_snipes.html"), "w").write("\n".join(P))
print("wrote CWiNFA_snipes.html", sum(len(p) for p in P) // 1024, "KB")
