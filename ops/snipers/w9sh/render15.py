#!/usr/bin/env python3
# READ-ONLY, offline: the presentable HTML report on 9Sh2fd's last 15 create-block snipes (snipes15.json + deep.json + the
# 343-launch population from ../bs43.json + ../bs_more.json). Every tx / wallet / token is a link.
import os, json, html, statistics, collections, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "snipes15.json"))); W = D["wallet"]; SN = D["snipes"]
DEEP = json.load(open(os.path.join(HERE, "deep.json")))["txs"]
POP = [x for f in ("../bs43.json", "../bs_more.json") for x in json.load(open(os.path.join(HERE, f))) if x]
e = html.escape
TX = lambda s: f"https://solscan.io/tx/{s}"; ACC = lambda a: f"https://solscan.io/account/{a}"; GW = lambda a: f"https://gmgn.ai/sol/address/{a}"; GT = lambda m: f"https://gmgn.ai/sol/token/{m}"
sh = lambda x, a=4, b=4: f"{x[:a]}…{x[-b:]}"
def ln(url, text, cls=""): return f'<a href="{url}" target="_blank" rel="noopener"{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{e(text)}</a>'
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%b %d, %H:%M:%S") if t else "—"
def sol(x, d=4): return f"{x:.{d}f}"
def pnl(x): return f'<span class="{"pos" if x > 0 else "neg"}">{x:+.3f}</span>'
LANDX = "LandX4wXzvDyWfq1XXn4StRjwPjzqb7je2kqDGLoT9L"; AKFEE = "AKbotZVF3zr9i4Cz2Lv34s6SydytjdidruoGTnvwPxFh"; AKPROG = "akbotssnVdpbCyjxbZJbspZspRcXJqzLjqteNBMJF9i"
# ---- derived numbers ----
for s in SN:
    after = [b for b in s["block"] if b["cls"] == "sniper" and b["pos"] > s["pos"]]
    s["paid_more_after"] = [b for b in after if b["fee"] > s["prio"] + sum(t[1] for t in s["tips"])]
    s["max_after"] = max(after, key=lambda b: b["fee"]) if after else None
    s["landx"] = sum(t[1] for t in s["tips"] if t[0] == "landx"); s["tip_total"] = sum(t[1] for t in s["tips"])
    s["botamt"] = s["botfee"]["amt"] if s["botfee"] else 0
    s["cost_pct"] = (s["prio"] + s["tip_total"] + s["botamt"]) / s["size"] * 100
    sb = sorted(s["sells"], key=lambda x: x["slot"])
    s["first_sell_s"] = (sb[0]["bt"] - s["bt"]) if sb and sb[0]["bt"] and s["bt"] else None
    s["last_sell_s"] = (sb[-1]["bt"] - s["bt"]) if sb and sb[-1]["bt"] and s["bt"] else None
    s["dev_s"] = (s["bt"] - s["create_bt"]) if s["bt"] and s["create_bt"] else None
net = sum(s["realized"] for s in SN); wins = sum(1 for s in SN if s["realized"] > 0)
buys_all = [t for t in DEEP if any(ev["buy"] for ev in t["ev"])]
d0 = sum(1 for t in buys_all if t.get("delta") == 0); d1 = sum(1 for t in buys_all if t.get("delta") == 1)
lx_all = sum(1 for t in buys_all if any(tp[0] == "landx" for tp in t["tips"]))
bot_fee_txs = sum(1 for t in DEEP if not t["ev"] and t["sol_chg"] is not None and -0.2 < t["sol_chg"] < -0.001)
# population: first-outside-buyer rate by landing service
rows = []
for x in POP:
    out = [r for r in x["rows"] if r["cls"] == "sniper" and r["buy"] and r["ok"] and r["sol"] >= 0.15]
    for k, r in enumerate(out): rows.append((k == 0, sorted({t[0] for t in r["tips"]}) or ["none"], r["pos"]))
svc = collections.defaultdict(list)
for first, ss, pos in rows:
    for s_ in ss: svc[s_].append((first, pos))
svc_rows = sorted([(k, len(v), sum(f for f, _ in v) / len(v), statistics.median(p for _, p in v)) for k, v in svc.items() if len(v) >= 15], key=lambda r: -r[2])
tto = next(s for s in SN if (s["symbol"] or "") == "TTO")
CSS = """
:root{--bg:#fbfbfa;--panel:#fff;--ink:#16181d;--mut:#6b7280;--line:#e7e7e4;--soft:#f3f3f1;--acc:#2f6fed;--accs:#e8effd;--pos:#0f7a3d;--neg:#b42318;--hi:#fff7d6;--chip:#eef0f3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e1013;--panel:#15181d;--ink:#e8eaed;--mut:#9aa1ab;--line:#262a31;--soft:#1b1f25;--acc:#7aa2ff;--accs:#1c2740;--pos:#4cc38a;--neg:#ff7a70;--hi:#3a3210;--chip:#222730}}
:root[data-theme="dark"]{--bg:#0e1013;--panel:#15181d;--ink:#e8eaed;--mut:#9aa1ab;--line:#262a31;--soft:#1b1f25;--acc:#7aa2ff;--accs:#1c2740;--pos:#4cc38a;--neg:#ff7a70;--hi:#3a3210;--chip:#222730}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:28px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}h2{font-size:20px;margin:44px 0 12px;letter-spacing:-.01em}h3{font-size:16px;margin:22px 0 8px}
p{margin:8px 0}.mut{color:var(--mut)}.small{font-size:13px}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}.chip{background:var(--chip);border-radius:999px;padding:3px 10px;font-size:12.5px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 18px;margin:12px 0}
.tldr{border-left:4px solid var(--acc)}.tldr ul{margin:6px 0 0;padding-left:20px}.tldr li{margin:4px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.stat b{display:block;font-size:22px;letter-spacing:-.01em}.stat span{color:var(--mut);font-size:12.5px}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
th{background:var(--soft);font-weight:600;font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:none}td.l,th.l{text-align:left}tr.me td{background:var(--hi)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;background:var(--chip);color:var(--mut);margin-left:6px;vertical-align:middle}
.badge.m{background:#e6f4ea;color:#11642f}.badge.i{background:#fff1e0;color:#8a4b00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .badge.m{background:#14301f;color:#7fdca5}:root:not([data-theme="light"]) .badge.i{background:#3a2a12;color:#f3c27a}}
.steps{counter-reset:s;list-style:none;padding:0;margin:8px 0}.steps li{position:relative;padding:10px 12px 10px 46px;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:8px 0}
.steps li:before{counter-increment:s;content:counter(s);position:absolute;left:12px;top:10px;width:24px;height:24px;border-radius:50%;background:var(--accs);color:var(--acc);font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center}
.ix{display:grid;grid-template-columns:34px 1fr;gap:8px;align-items:start;padding:8px 0;border-bottom:1px dashed var(--line)}.ix:last-child{border-bottom:none}.ix .n{font-weight:700;color:var(--acc)}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--soft);margin:8px 0 4px}.bar span{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12.5px;color:var(--mut)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
details{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:8px 0;padding:0 14px}summary{cursor:pointer;padding:12px 0;font-weight:600;list-style:none}summary::-webkit-details-marker{display:none}
summary:after{content:"＋";float:right;color:var(--mut)}details[open] summary:after{content:"－"}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:720px){.cols{grid-template-columns:1fr}}
footer{margin-top:48px;color:var(--mut);font-size:12.5px}
"""
P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>9Sh2fd Sniper Study</title><style>{CSS}</style></head><body><div class='wrap'>"]
P.append(f"""<h1>How wallet 9Sh2fd snipes pump.fun launches</h1>
<p class="mut">A study of his last {len(SN)} create-block snipes, built only from on-chain data. Every transaction, wallet and token below links to Solscan or GMGN so you can check it.</p>
<div class="chips"><span class="chip">Wallet {ln(GW(W), sh(W, 6, 4))} · {ln(ACC(W), "Solscan")}</span><span class="chip">Snipes {utc(min(s['bt'] for s in SN))} → {utc(max(s['bt'] for s in SN))} UTC</span><span class="chip">Wider sample: {len(buys_all)} buys, Oct 20–22</span></div>""")
P.append(f"""<div class="card tldr"><b>In one paragraph</b><ul>
<li>He is a <b>same-block sniper</b>: {d0} of his last {len(buys_all)} buys landed in the token's create block and {d1} in the next block.</li>
<li>He is <b>not an insider</b>: he is never inside the dev's bundle, and Jito's bundle API confirms it. He is simply the <b>first outside buyer</b> every time: {sum(1 for s in SN if s['rank'] == 1)} of {len(SN)} here, and 42 of 43 in the wider sample.</li>
<li>He most likely gets that position by paying a <b>LandX tip</b>, a separate transfer to a fast-landing service, of about <b>2% of each buy</b> (0.06 SOL on 2.96 SOL). GMGN's "Gas" column does not show it: it only shows his 0.0025–0.005 SOL priority fee. <span class="badge i">strong evidence, see below</span></li>
<li>His buy is a <b>lean "v1" transaction with a durable nonce</b> (about 50k compute units, half of ours), so it can be signed and sent the instant the create appears.</li>
<li>After every buy he sends a <b>1% fee</b> to {ln(ACC(AKFEE), sh(AKFEE, 6, 4))}. The name matches his router program "akbots", so it is most likely a commercial sniping bot's fee <span class="badge i">inferred</span>.</li></ul></div>""")
fl = statistics.median(s["pos"] for s in SN)
P.append(f"""<div class="grid">
<div class="stat"><b>{sum(1 for s in SN if s['rank'] == 1)}/{len(SN)}</b><span>first outside buyer</span></div>
<div class="stat"><b>+{fl:.0f}</b><span>median position (transactions after the dev's bundle)</span></div>
<div class="stat"><b>0/{len(SN)}</b><span>inside the dev's bundle</span></div>
<div class="stat"><b>~2.1%</b><span>LandX tip on a 2.96 SOL buy</span></div>
<div class="stat"><b>1%</b><span>bot fee, paid after each buy</span></div>
<div class="stat"><b>{pnl(net)}</b><span>net SOL over these {len(SN)} ({wins} wins)</span></div></div>""")
# ---- anatomy: TTO ----
t = tto; ma = t["max_after"]
P.append(f"""<h2>Anatomy of one snipe: TTO <span class="badge m">measured</span></h2>
<p>Token {ln(GT(t['mint']), t['name'] or t['symbol'])} ({ln(ACC(t['mint']), sh(t['mint'], 6, 4))}), created {utc(t['create_bt'])} UTC in block {t['S']}.</p>
<ol class="steps">
<li><b>The dev creates the token and buys in the same transaction</b> ({ln(TX(t['create_sig']), 'create tx')}): {sol(t['dev_sol'], 2)} SOL. {t['bundle_legs']} more creator buys are glued right behind it ({sol(t['bundle_sol'], 2)} SOL): this is the dev's bundle.</li>
<li><b>He is the first outside buyer</b>, {t['pos']} transactions after the dev's bundle in the same block, with {sol(t['size'], 4)} SOL ({ln(TX(t['buy_sig']), 'buy tx')}). Of the {t['n_out']} outside buyers in this block he was #{t['rank']}.</li>
<li><b>He paid</b> a 0.0025 SOL priority fee plus a {sol(t['landx'], 4)} SOL LandX tip.{f" Someone paying {sol(ma['fee'], 4)} SOL landed <i>after</i> him ({ln(GW(ma['who']), sh(ma['who']))}, {ln(TX(ma['sig']), 'tx')})." if ma and ma['fee'] > t['tip_total'] + t['prio'] else ""}</li>
<li><b>He sold in {len(t['sells'])} pieces</b>: the first {'within the same second as' if t['first_sell_s'] == 0 else str(t['first_sell_s']) + ' s after'} his buy, the last {t['last_sell_s']} s after it.</li>
<li><b>He paid the 1% bot fee</b>, {sol(t['botamt'], 6)} SOL to {ln(ACC(AKFEE), sh(AKFEE, 6, 4))}, in a separate transaction ({ln(TX(t['botfee']['sig']), 'fee tx')}) {t['botfee']['bt'] - t['bt'] if t['botfee'] and t['botfee']['bt'] else '?'} s later. Net result for this snipe: {pnl(t['realized'])} SOL.</li></ol>""")
P.append(f"""<h3>His buy transaction, instruction by instruction</h3><div class="card">
<div class="ix"><span class="n">#1</span><div><b>Advance durable nonce</b> (nonce account {ln(ACC(t['nonce']), sh(t['nonce'], 6, 4))}). With a nonce he needs no fresh blockhash, so he can sign the buy the moment the create is seen. The same signed transaction can also go to several endpoints and still land only once.</div></div>
<div class="ix"><span class="n">#2</span><div><b>Tip transfer to LandX</b>: {sol(t['landx'], 4)} SOL to {ln(ACC(LANDX), sh(LANDX, 6, 4))}, one of LandX's 10 tip accounts (LandX1…–LandX9…, LandXXx…). <i>This is most likely what buys his position (see the evidence section).</i> GMGN does not count it as gas.</div></div>
<div class="ix"><span class="n">#3–4</span><div><b>Creates his token account directly</b> (createAccountWithSeed + initializeAccount3) instead of through the Associated Token Account program. This saves compute.</div></div>
<div class="ix"><span class="n">#5</span><div><b>pump.fun buy</b> of {sol(t['size'], 4)} SOL.</div></div>
<p class="small mut">Transaction format v{t['version']}: the fee is set in the transaction header, not with compute-budget instructions. Compute used: {t['cu']:,} units. Single signer.</p></div>""")
# ---- fee breakdown ----
s296 = [s for s in SN if abs(s["size"] - 2.963) < 0.01 and s["landx"] > 0]
lx296 = statistics.median(s["landx"] for s in s296) if s296 else 0.0618; pr296 = statistics.median(s["prio"] for s in s296) if s296 else 0.005
parts = [("pump.fun fee (buy side, 1.25%)", 1.25, "#9aa1ab"), ("LandX tip", lx296 / 2.963 * 100, "#2f6fed"), ("bot fee", 1.0, "#e8a33d"), ("priority fee", pr296 / 2.963 * 100, "#4cc38a")]
tot = sum(p[1] for p in parts)
P.append(f"""<h2>What one 2.96 SOL buy costs him</h2><div class="card">
<div class="bar">{''.join(f'<span style="width:{p[1] / tot * 100:.1f}%;background:{p[2]}"></span>' for p in parts)}</div>
<div class="legend">{''.join(f'<span><i style="background:{p[2]}"></i>{e(p[0])}: {p[1]:.2f}%</span>' for p in parts)}</div>
<p class="small mut">About {tot:.1f}% of the buy before the token moves, plus pump.fun's 1.25% again when he sells. Only the LandX tip is about landing. GMGN's "Gas" shows just the {pr296:.4f} SOL priority fee.</p></div>""")
# ---- the 15 snipes ----
P.append("""<h2>The 15 snipes <span class="badge m">measured</span></h2><p class="mut small">Position = transactions between the dev's bundle and his buy in the same block. Rank = his place among outside buyers of that token in that block. Result = the sum of his wallet's SOL changes over the buy, every sell and the 1% fee.</p>
<div class="tbl"><table><tr><th class="l">Token</th><th class="l">Created (UTC)</th><th>Dev + bundle SOL</th><th class="l">His buy</th><th>Position</th><th>Rank</th><th>SOL</th><th>Priority</th><th>LandX tip</th><th>Bot fee</th><th>Total cost</th><th>Sells</th><th>Held</th><th>Result</th></tr>""")
for s in SN:
    tipcell = sol(s["landx"], 4) if s["landx"] else (f"{sol(s['tip_total'], 4)} ({e(s['tips'][0][0])})" if s["tips"] else "—")
    P.append(f"<tr><td class='l'>{ln(GT(s['mint']), s['symbol'] or sh(s['mint']))}</td><td class='l'>{utc(s['create_bt'])}</td><td>{sol(s['dev_sol'], 2)} + {sol(s['bundle_sol'], 2)}</td>"
             f"<td class='l'>{ln(TX(s['buy_sig']), sh(s['buy_sig'], 6, 4))}</td><td>+{s['pos']}</td><td>{s['rank']}/{s['n_out']}</td><td>{sol(s['size'], 3)}</td><td>{sol(s['prio'], 4)}</td><td>{tipcell}</td>"
             f"<td>{ln(TX(s['botfee']['sig']), sol(s['botamt'], 4)) if s['botfee'] else '—'}</td><td>{s['cost_pct']:.1f}%</td><td>{len(s['sells'])}</td><td>{(str(s['first_sell_s']) + '–' + str(s['last_sell_s']) + ' s') if s['first_sell_s'] is not None else '—'}</td><td>{pnl(s['realized'])}</td></tr>")
P.append(f"<tr><td class='l' colspan='13'><b>Total ({wins} wins, {len(SN) - wins} losses)</b></td><td><b>{pnl(net)}</b></td></tr></table></div>")
P.append(f"""<p class="small mut">Pattern in the results (measured, not analyzed further): when the token does not move, he exits in 2 sells and loses about 4–13%. When it runs, he scales out in 6–11 sells. Over these {len(SN)} snipes the winners paid for the losers.</p>""")
# ---- per-block detail ----
P.append("<h2>Every block, buyer by buyer</h2><p class='mut small'>Each section lists the token's buyers in its create block: the dev, the dev's bundle, him (highlighted), and the other snipers with what they paid. Buyers who paid more but still landed after him show that fee alone did not decide position.</p>")
for s in SN:
    more = len(s["paid_more_after"])
    P.append(f"<details><summary>{e(s['symbol'] or sh(s['mint']))} — position +{s['pos']}, rank {s['rank']}/{s['n_out']}{f', {more} paid more but landed after him' if more else ''}</summary>"
             f"<p class='small mut'>Token {ln(GT(s['mint']), s['name'] or s['mint'])} · creator {ln(GW(s['creator']), sh(s['creator'], 6, 4)) if s['creator'] else '—'} · block {s['S']} · {ln(TX(s['create_sig']), 'create tx')}</p>"
             "<div class='tbl'><table><tr><th class='l'>Role</th><th>Position</th><th class='l'>Wallet</th><th>SOL</th><th>Priority</th><th class='l'>Tips</th><th>Total paid</th><th class='l'>Jito bundle</th><th class='l'>Tx</th></tr>")
    for b in sorted(s["block"], key=lambda b: b["pos"]):
        role = {"create": "dev (create)", "glued": "dev bundle", "creator-bundle": "dev bundle (Jito)"}.get(b["cls"], "sniper")
        me = b["who"] == W
        if me: role = "<b>9Sh2fd</b>"
        tips = ", ".join(f"{e(tp[0])} {sol(tp[1], 4)}" for tp in b["tips"]) or "—"
        P.append(f"<tr class='{'me' if me else ''}'><td class='l'>{role}</td><td>{b['pos']:+d}</td><td class='l'>{ln(GW(b['who']), sh(b['who']))}</td><td>{sol(b['sol'], 3)}</td><td>{sol(b['prio'], 4)}</td><td class='l'>{tips}</td><td>{sol(b['fee'], 4)}</td><td class='l'>{'yes' if b['bundle'] else 'no'}</td><td class='l'>{ln(TX(b['sig']), sh(b['sig'], 5, 3))}</td></tr>")
    P.append("</table></div></details>")
# ---- comparison ----
P.append(f"""<h2>Him vs us</h2><div class="tbl"><table><tr><th class="l"></th><th class="l">9Sh2fd</th><th class="l">Our engine (Runs 1–2)</th></tr>
<tr><td class="l">Where the buy lands</td><td class="l">first outside buyer; median +{fl:.0f} txs after the dev's bundle</td><td class="l">+140 to +240 txs after the bundle (Run 1); 73–75 ms after the create (Run 2)</td></tr>
<tr><td class="l">Landing spend</td><td class="l">one service (LandX), tip ≈ 1.2–2.1% of the buy</td><td class="l">5 routes with ~0.001 SOL tips each (LandX included) + 0.011 SOL priority</td></tr>
<tr><td class="l">Priority fee</td><td class="l">0.0025–0.005 SOL</td><td class="l">0.011 SOL</td></tr>
<tr><td class="l">Transaction</td><td class="l">v1, durable nonce, ~50k compute units, own token account</td><td class="l">recent blockhash (cached), ~100k compute-unit limit, Associated Token Account program</td></tr>
<tr><td class="l">Buy size</td><td class="l">two tiers: 1.78 and 2.96 SOL</td><td class="l">0.5–1.5 SOL</td></tr>
<tr><td class="l">Extra cost</td><td class="l">1% bot fee after every buy</td><td class="l">none</td></tr></table></div>""")
# ---- population evidence ----
P.append(f"""<h2>Is it really the LandX tip? <span class="badge m">measured</span> <span class="badge i">inferred</span></h2>
<p>Across {len(POP)} recorded launches ({len(rows)} outside buys in create blocks), this is how often a buyer using each landing service was the <b>first</b> outside buyer:</p>
<div class="tbl"><table><tr><th class="l">Landing service (tip in the tx)</th><th>Buys</th><th>First outside buyer</th><th>Median position</th></tr>
{''.join(f"<tr><td class='l'>{e(k)}</td><td>{n}</td><td>{f * 100:.0f}%</td><td>+{p:.0f}</td></tr>" for k, n, f, p in svc_rows)}</table></div>
<p class="small mut">LandX users come first far more often than Helius, Nozomi or Astralane users. That is strong evidence, but not proof: LandX publishes nothing about how it routes, and some of the difference may come from who uses it. The clean test is to send our own buy-shaped test transactions through LandX with his tip sizes and compare positions. Failed test buys refund the tip, so each test costs only the priority fee.</p>""")
# ---- method / references ----
P.append(f"""<h2>Method and references</h2><div class="card small">
<p><b>Data.</b> His {len(DEEP)} most recent successful transactions ({len(buys_all)} buys) were read from the chain. Each create block was rebuilt in exact order with full transaction details, and every buyer was checked against Jito's public bundle API (<span class="mono">bundles.jito.wtf/api/v1/bundles/transaction/&lt;sig&gt;</span>). Buyers in the creator's bundle, or in Jito bundles linked to the creator, count as the dev's side.</p>
<p><b>Fees.</b> "Priority" = network fee minus the 5,000-lamport base. "Tips" = SOL transfers inside the transaction to known tip accounts of landing services. "Bot fee" = his separate transfer of exactly 1% of the previous buy to {ln(ACC(AKFEE), sh(AKFEE, 6, 4))}: {bot_fee_txs} such transfers in his recent history.</p>
<p><b>Accounts.</b> Wallet {ln(GW(W), W)} · router program for USDC/PUMP-quoted tokens {ln(ACC(AKPROG), sh(AKPROG, 8, 4))} · bot fee wallet {ln(ACC(AKFEE), sh(AKFEE, 8, 4))} · LandX tip account {ln(ACC(LANDX), sh(LANDX, 8, 4))} · nonce account {ln(ACC(tto['nonce']), sh(tto['nonce'], 8, 4))} · funded on Oct 17 with 13.70 SOL from {ln(ACC('5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9'), '5tzFki…uAi9')} (pays many wallets at once; looks like an exchange).</p>
<p><b>Not known.</b> Who runs "AK bots" (no public documentation found) and how LandX orders the transactions it receives.</p></div>""")
P.append(f"<footer>Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%b %d, %Y %H:%M')} UTC from on-chain data (read-only). Scripts: ops/snipers/w9sh (deep.py, collect15.py, render15.py) and ops/run1/bundlestudy.py.</footer></div></body></html>")
open(os.path.join(HERE, "9Sh2fd_snipes.html"), "w").write("\n".join(P))
print("wrote 9Sh2fd_snipes.html", sum(len(p) for p in P) // 1024, "KB")
