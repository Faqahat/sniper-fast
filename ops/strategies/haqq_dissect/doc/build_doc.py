#!/usr/bin/env python3
"""Builds the owner's HTML playbook from the analysts' audited example files + hand-written verified text.
Out: /home/moiz/sniper/ops/strategies/haqq_dissect/doc/haqq_playbook.html"""
import json, html, os
D = "/home/moiz/sniper-data/haqq_dissect"
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
esc = html.escape
def link(url, text): return f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(text)}</a>'
def short(u): return (u.rsplit("/", 1)[-1].split("?")[0])[:6] + "…"
def sol(x, d=3):
    try: x = float(x)
    except Exception: return "–"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="num {cls}">{x:+.{d}f}</span>'
def tx_links(urls, label):
    urls = [u for u in (urls or []) if u]
    return " ".join(link(u, f"{label}{'' if len(urls) == 1 else ' ' + str(i + 1)}") for i, u in enumerate(urls)) or "–"

def bot_example_table(examples, kind):
    rows = []
    for e in examples:
        if kind == "major":
            sells = e.get("sell_txs") or []
            trig = e.get("trigger") or {}
            tr = trig if isinstance(trig, str) else f"{trig.get('type', trig.get('seller_type', ''))} {('−%.0f%%' % trig['drop_pct']) if trig.get('drop_pct') is not None else ''}".strip()
            rows.append(f"<tr><td>{esc(str(e.get('time_pkt', '')))}</td><td>{link(e['gmgn'], short(e['gmgn']))}</td><td class='num'>{float(e.get('size_sol', 0)):.2f}</td>"
                        f"<td class='num'>{float(e.get('hold_s', 0)):.1f} s</td><td>{sol(e.get('pnl_sol'), 4)}</td><td>{esc(tr)}</td>"
                        f"<td>{link(e['buy_tx'], 'buy')} {tx_links(sells, 'sell')}</td></tr>")
        else:
            sells = [e.get("sell_tx"), e.get("sell_tx2")]
            trig = e.get("trigger")
            tr = trig if isinstance(trig, str) else json.dumps(trig)[:60] if trig else ""
            hold = e.get("hold_s"); hold = f"{float(hold):.1f} s" if hold is not None else f"{e.get('hold_slots', '')} slots"
            rows.append(f"<tr><td>{esc(str(e.get('time_pkt', '')))}</td><td>{link(e['gmgn'], short(e['gmgn']))}</td><td class='num'>{float(e.get('size_sol', 0)):.3f}</td>"
                        f"<td class='num'>{hold}</td><td>{sol(e.get('pnl_sol'), 4)}</td><td>{esc(str(tr))[:70]}</td>"
                        f"<td>{link(e['buy_tx'], 'buy') if e.get('buy_tx') else ''} {tx_links(sells, 'sell')}</td></tr>")
    return ("<div class='tw'><table class='ex'><thead><tr><th>Buy (PKT)</th><th>Token</th><th>SOL</th><th>Held</th><th>P&amp;L SOL</th><th>Trigger</th><th>Txs</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")

def claims_block(code, v, kind):
    out = []
    for c in v["claims"]:
        ex = c["examples"]
        n = c.get("matching_lots")
        out.append(f"<details class='claim'><summary><span class='claimtxt'>{esc(c['claim'])}</span>"
                   f"<span class='meta'>{len(ex)} example trades{(' · %s matching lots' % f'{n:,}') if n else ''}</span></summary>{bot_example_table(ex, kind)}</details>")
    return "".join(out)

bots = json.load(open(f"{D}/bots/examples.json"))
minor = json.load(open(f"{D}/minor/examples.json"))
vs = json.load(open(f"{D}/vs248/examples.json"))
sel = json.load(open(f"{D}/select/examples.json"))
acc = json.load(open("/home/moiz/sniper-data/accept_owner/summary.json"))

BOT_META = {  # 24 h exact (recon, 10-26 23:15 -> 10-27 23:15) and 6-day (pos p4) figures
    247: ("Launch-Dump Sniper", 1045, "+8.907", "+89.9", "0.40", "4.1 s", "Buys 0–1 slot after the dev or a launch bundler sells ≥5%, on tokens under ~5 s old. No price limit. Sells within 2 s into the buy wave when it bounces, otherwise on a 15–30 slot timer."),
    248: ("Big-Dump Rebounder", 2081, "+11.808", "+83.6", "0.40 (0.25→0.30→0.40)", "4.2 s", "Buys 0–2 slots after a big, busy dump (bigger drop = more likely), any seller, tokens up to ~60 s old; one lot per token; often stacks behind 247. No price limit. Quick sell on the bounce, or a ~65-slot timer when the token keeps running."),
    244: ("Binary-Timer Dipper", 1416, "+3.416", "+20.5", "0.25 (+0.01 tier)", "9 s", "Dump buys on young tokens plus buys on busy young tokens. No price limit. Sells on fixed 8/16/32/64-slot timers; a third of lots sell 50% first."),
    226: ("Band Bouncer", 403, "+1.562", "+12.2", "0.50", "0.9 s", "Buys 0–5 slots after a dev or creation-slot bundler dump, usually alongside 247/248, with a band order (fills only between 0.90× and 1.09× the post-dump price). 2–7 slot timer, cut short by profit."),
    234: ("Dead-Curve Fisher", 568, "+1.375", "+5.2", "0.50–1.25", "20 min", "Buys in the same slot when a sell takes the curve back to the 30-SOL launch floor. Take-profit or long timers (50 slots to 32 min). A lottery: its top 10 lots make two-thirds of its gross."),
    231: ("Band Bouncer Jr.", 62, "+0.693", "+3.6", "0.25", "1.5 s", "Dev dumps on brand-new tokens, band order, exits at 5/8/20 slots."),
    251: ("4-Second Momentum Flipper", 129, "+0.602", "+0.7", "0.10–0.40", "4 s", "Buys after heavy outside buying on older tokens; sells on a 19–20 slot timer."),
    249: ("Probe-then-Scale Tester", 0, "0", "−0.02", "0.01 → 0.395", "42 s", "Live paper trading: ran at 0.01 SOL, scaled to 0.395, lost, switched off after 10-25."),
    252: ("Micro Momentum Probe", 0, "0", "−0.50", "0.01", "<1 s", "0.01 SOL live test of a 2–3 slot strategy; stopped."),
}

css = r"""
:root{--bg:#f5f6f3;--surface:#ffffff;--ink:#17201c;--muted:#5d6a64;--line:#dde3df;--accent:#0b6e65;--accent-soft:#e3f1ee;--good:#177245;--bad:#b3261e;--warn:#9a5b06;--chip:#eef1ee;
--f-display:"Archivo",system-ui,sans-serif;--f-body:"IBM Plex Sans",system-ui,sans-serif;--f-mono:"IBM Plex Mono",ui-monospace,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e1412;--surface:#151d1a;--ink:#e4ebe7;--muted:#97a59f;--line:#26322d;--accent:#3cc9b6;--accent-soft:#123029;--good:#5fd58f;--bad:#f28b82;--warn:#f2b552;--chip:#1c2622;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0e1412;--surface:#151d1a;--ink:#e4ebe7;--muted:#97a59f;--line:#26322d;--accent:#3cc9b6;--accent-soft:#123029;--good:#5fd58f;--bad:#f28b82;--warn:#f2b552;--chip:#1c2622;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:15px;line-height:1.55}
.wrap{max-width:980px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 64px}
h1,h2,h3{font-family:var(--f-display);text-wrap:balance;line-height:1.15;margin:0}
h1{font-size:clamp(28px,6vw,44px);font-weight:800;letter-spacing:-.01em}
h2{font-size:clamp(21px,3.6vw,27px);font-weight:750;margin-top:44px;padding-top:18px;border-top:1px solid var(--line)}
h3{font-size:18px;font-weight:700;margin-top:22px}
p{margin:.6em 0;max-width:68ch}
.lead{font-size:17px;color:var(--ink)}
.sub{color:var(--muted);font-size:14px}
.eyebrow{font-family:var(--f-mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
a{color:var(--accent);text-underline-offset:2px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.num{font-family:var(--f-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.pos{color:var(--good)}.neg{color:var(--bad)}
.tw{overflow-x:auto;margin:10px 0;border:1px solid var(--line);border-radius:8px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12px;letter-spacing:.03em;white-space:nowrap}
tr:last-child td{border-bottom:none}
td.r,th.r{text-align:right}
.pill{display:inline-block;font-family:var(--f-mono);font-size:11px;letter-spacing:.05em;padding:2px 8px;border-radius:99px;border:1px solid var(--line);background:var(--chip);white-space:nowrap}
.pill.ok{color:var(--good);border-color:color-mix(in srgb,var(--good) 40%,var(--line))}
.pill.rp{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,var(--line))}
.pill.no{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,var(--line))}
.pill.ask{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin:14px 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.card h3{margin-top:0}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13.5px;margin-top:8px}
.kv dt{color:var(--muted)}.kv dd{margin:0}
.big{font-family:var(--f-mono);font-size:26px;font-weight:600}
details.claim{border:1px solid var(--line);border-radius:8px;background:var(--surface);margin:8px 0}
details.claim>summary{cursor:pointer;padding:10px 12px;list-style:none;display:flex;flex-direction:column;gap:2px}
details.claim>summary::-webkit-details-marker{display:none}
details.claim>summary .claimtxt::before{content:"+ ";font-family:var(--f-mono);color:var(--accent)}
details[open].claim>summary .claimtxt::before{content:"– "}
.meta{font-family:var(--f-mono);font-size:12px;color:var(--muted)}
details.claim .tw{margin:0 10px 10px}
table.ex td{white-space:nowrap}
.bot{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:16px;margin:16px 0}
.bot .code{font-family:var(--f-mono);font-size:13px;color:var(--muted)}
.bot h3{margin-top:4px;font-size:21px}
.stats{display:flex;flex-wrap:wrap;gap:8px 22px;margin:10px 0 6px}
.stat .l{font-size:12px;color:var(--muted)}.stat .v{font-family:var(--f-mono);font-size:16px}
ul{padding-left:20px}li{margin:4px 0;max-width:72ch}
.note{font-size:13.5px;color:var(--muted)}
.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13.5px;margin-top:14px}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

def bot_card(code, data, kind):
    name, lots24, pnl24, pnl6, size, hold, desc = BOT_META[code]
    return (f"<section class='bot' id='bot{code}'><div class='code'>bot code {code} · last 3 digits of the compute price</div><h3>{esc(name)}</h3>"
            f"<p>{esc(desc)}</p><div class='stats'>"
            f"<div class='stat'><div class='l'>24 h P&amp;L (exact)</div><div class='v'>{sol(pnl24, 2)} SOL</div></div>"
            f"<div class='stat'><div class='l'>24 h lots</div><div class='v'>{lots24:,}</div></div>"
            f"<div class='stat'><div class='l'>6 days</div><div class='v'>{sol(pnl6, 1)} SOL</div></div>"
            f"<div class='stat'><div class='l'>Size</div><div class='v'>{esc(size)}</div></div>"
            f"<div class='stat'><div class='l'>Hold (median)</div><div class='v'>{esc(hold)}</div></div></div>"
            + (claims_block(code, data, kind) if data else "") + "</section>")

parts = []
A = parts.append
A("<title>haqq Dissected</title><meta name='claude:viewport-fit-sides' content='cover'>")
A("<link rel='preconnect' href='https://fonts.googleapis.com'><link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>")
A("<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Archivo:wght@700;800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap'>")
A(f"<style>{css}</style><div class='wrap'>")
A(open(os.path.join(os.path.dirname(__file__), "body_top.html")).read())
# bots
A("<h2 id='bots'>His bots, one by one</h2><p>Every claim below opens to at least 5 real trades: the token on GMGN (filtered to haqq) and the buy and sell transactions on Solscan. All 1,000+ linked transactions were checked against our recordings: real, signed by haqq, and carrying the bot code shown.</p>")
for code in (247, 248):
    A(bot_card(code, bots[str(code)], "major"))
for code in (244, 226, 234, 231, 251, 249, 252):
    A(bot_card(code, minor[str(code)], "minor"))
A(open(os.path.join(os.path.dirname(__file__), "body_mid.html")).read())
# vs248 evidence
VS = [("2_timing_same_dump_we_first_248_pays_more", "Same dump: we land first, bot 248 pays more"),
      ("3_limit_we_failed_248_filled", "Same dump: our price limit failed (6042), bot 248 filled"),
      ("1a_gate_refused_248_bought", "Our filter refused the dump, bot 248 bought it"),
      ("1c_trigger_dev_chunk_refused", "Dev chunk-sell we never bought, bot 248 did"),
      ("1d_run_gap_no_engine", "Bot 248 trade while no engine of ours was running"),
      ("8_head_to_head_random", "Random shared dumps: our result vs bot 248's")]
A("<h3>Evidence: bot 248 vs our engine</h3>")
for key, title in VS:
    rows = []
    for e in vs.get(key, []):
        o = e.get("ours") if isinstance(e.get("ours"), dict) else None
        b = e.get("bot248") or {}
        ours_txt = (link(o["buy_tx"], "our buy") + " " + tx_links(o.get("sell_txs"), "sell") + f" {sol((o.get('net_msol') or 0) / 1000, 4)}") if o else esc(str(e.get("ours", ""))[:60])
        b_txt = (link(b["buy_tx"], "248 buy") + " " + tx_links(b.get("sell_txs"), "sell") + f" {sol((b.get('net_msol') or 0) / 1000, 4)}") if b.get("buy_tx") else ""
        when = b.get("buy_pkt") or (o or {}).get("buy_pkt", "")
        rows.append(f"<tr><td>{esc(str(when))}</td><td>{link(e['gmgn'], short(e['gmgn']))}</td><td>{ours_txt}</td><td>{b_txt}</td></tr>")
    A(f"<details class='claim'><summary><span class='claimtxt'>{esc(title)}</span><span class='meta'>{len(rows)} examples</span></summary>"
      f"<div class='tw'><table class='ex'><thead><tr><th>Time (PKT)</th><th>Token</th><th>Ours (net SOL)</th><th>Bot 248 (net SOL)</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>")
# selection evidence
A("<h3>Evidence: what his selection looks like</h3>")
for key, exs in sel.items():
    rows = "".join(f"<tr><td>{esc(e.get('time_pkt', ''))}</td><td>{link(e['gmgn'], short(e['gmgn']))}</td><td>{esc(e.get('seller', '')[:6])}…</td><td class='num'>{e.get('seller_creates_before', '')}</td>"
                   f"<td class='num'>{e.get('drop_pct', '')}%</td><td>{'247 ' if e.get('bought247') else ''}{'248' if e.get('bought248') else ''}{'none' if not (e.get('bought247') or e.get('bought248')) else ''}</td>"
                   f"<td>{sol((e.get('haqq_net_msol') or 0) / 1000, 4) if (e.get('bought247') or e.get('bought248')) else '–'}</td></tr>" for e in exs)
    A(f"<details class='claim'><summary><span class='claimtxt'>{esc(key)}</span><span class='meta'>{len(exs)} examples</span></summary>"
      f"<div class='tw'><table class='ex'><thead><tr><th>Time (PKT)</th><th>Token</th><th>Seller</th><th>Seller's creates</th><th>Drop</th><th>haqq bought</th><th>haqq net</th></tr></thead><tbody>{rows}</tbody></table></div></details>")
A(open(os.path.join(os.path.dirname(__file__), "body_strat.html")).read())
# owner's tokens
A("<h2 id='tokens'>Your test tokens</h2><p>The four tokens you picked by hand. None of the analysts was shown them; they are the acceptance check. Times PKT; P&amp;L is gross SOL from the chain.</p>")
for t in acc:
    rows = "".join(f"<tr><td>{r['code']} · {esc(BOT_META.get(r['code'], ('?',))[0])}</td><td class='num'>{r['n_buy']} / {r['n_sell']}</td><td class='num'>{r['sol_in']:.3f}</td><td>{sol(r['pnl'], 3)}</td>"
                   f"<td>{' '.join(link('https://solscan.io/tx/' + b['sig'], 'buy ' + b['t']) for b in r['buys'])} {' '.join(link('https://solscan.io/tx/' + s['sig'], 'sell ' + s['t']) for s in r['sells'])}</td></tr>" for r in t["bots"])
    ours = " · ".join(f"{o['who']} {o['side']} {o['sol']:.3f} SOL at slot +{o['s']} ({link('https://solscan.io/tx/' + o['sig'], 'tx')})" for o in t["ours"]) or "no fill"
    A(f"<h3>{esc(t['name'])} <span class='sub'>({link('https://gmgn.ai/sol/token/' + t['mint'] + '?maker=' + H, 'GMGN')})</span></h3>"
      f"<div class='tw'><table><thead><tr><th>haqq bot</th><th>Buys / sells</th><th>SOL in</th><th>P&amp;L</th><th>Txs</th></tr></thead><tbody>{rows}</tbody></table></div>"
      f"<p class='note'>Us: {ours}; {t['our_failed']} failed tries.</p>")
A(open(os.path.join(os.path.dirname(__file__), "body_tokens_note.html")).read())
A(open(os.path.join(os.path.dirname(__file__), "body_end.html")).read())
A("</div>")
open(os.path.join(os.path.dirname(__file__), "haqq_playbook.html"), "w").write("\n".join(parts))
print("ok", sum(len(p) for p in parts), "bytes")
