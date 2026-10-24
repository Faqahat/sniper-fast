#!/usr/bin/env python3
# Builds report/DECISION.html: the owner's 17:00 PKT summary (what works, what it needs), from the result files.
import json, gzip, time, html, os, re, statistics
O = "/home/moiz/sniper/ops/overnight"
now = time.strftime("%Y-%m-%d %H:%M", time.gmtime(time.time() + 18000)) + " PKT"
esc = html.escape
def tx(sig, label=None): return f'<a href="https://solscan.io/tx/{sig}">{esc(label or sig[:8])}</a>'
def tok(m, label): return f'<a href="https://gmgn.ai/sol/token/{m}">{esc(label or m[:8])}</a>'
def acct(w): return f'<a href="https://gmgn.ai/sol/address/{w}">{w[:8]}</a>'
# ---- FINAL-2 decision table
DT = json.load(open(f"{O}/decision/decision_table.json"))
def dt(w, L, var, cost): return next(x for x in DT if x["w"] == w and x["L"] == L and x["var"] == var and x["cost"] == cost)
f2rows = ""
for L in ("30", "45", "60", "75"):
    cells = ""
    for w in ("R2 overnight 8.3 h", "R1 daytime tail 3 h"):
        for cost in ("today", "CW-style", "Run 2 fees"):
            x = dt(w, L, "proafter_slip", cost)
            cls = "pos" if x["tot"] > 0 else "neg"
            cells += f'<td class="{cls}">{x["tot"]:+.2f}<br><small>P {x["p"]:.2f}</small></td>'
    f2rows += f"<tr><td>{L} ms</td>{cells}</tr>"
# ---- dip results (richer-feature model, follower slippage imputed; last column: our sell lands 75 ms into its slot)
E = {}
for l in gzip.open(f"{O}/dip/events_timed3_slip_sl75.jsonl.gz", "rt"):
    r = json.loads(l); E[(r["m"], r["age"])] = r
diprows = ""
for L in ("20", "35", "50", "75"):
    cells = ""
    for d in ("R1toR2", "R2toR1"):
        S = json.load(open(f"{O}/dip/sel_x_{L}_8_{d}.json")); sel = [r for r in S if r["score"] >= r["thr5"]]
        a = sum(r["pnl"]["8"] for r in sel)
        b = [E[(r["m"], r["age"])]["pnl"][L]["8"] for r in sel if (r["m"], r["age"]) in E and L in E[(r["m"], r["age"])]["pnl"]]
        span = (max(r["bt"] + r["age"] for r in sel) - min(r["bt"] + r["age"] for r in sel)) / 3600
        cells += f'<td class="{"pos" if a > 0 else "neg"}">{a:+.2f}</td><td class="{"pos" if sum(b) > 0 else "neg"}">{sum(b):+.2f}<br><small>{len(sel)} trades / {span:.0f} h</small></td>'
    diprows += f"<tr><td>{L} ms</td>{cells}</tr>"
EX = json.load(open(f"{O}/census/hk_examples.json"))
exs = sorted(EX, key=lambda r: -r["pnl"])[:4] + sorted(EX, key=lambda r: r["pnl"])[:2]
exrows = "".join(f'<tr><td>{time.strftime("%m-%d %H:%M", time.gmtime(r["bt"] + 18000))}</td><td>{tok(r["mint"], r["name"])}</td><td>{r["age_s"]} s</td>'
                 f'<td>{tx(r["sell_sig"], f"sell {r[chr(115)+chr(101)+chr(108)+chr(108)+chr(95)+chr(115)+chr(111)+chr(108)]} SOL")}</td><td>{tx(r["buy_sig"], "buy 0.5")}</td>'
                 f'<td>{tx(r["exit_sig"], f"sold {r[chr(101)+chr(120)+chr(105)+chr(116)+chr(95)+chr(115)+chr(111)+chr(108)]}")} after {r["hold_slots"]} slots</td>'
                 f'<td class="{"pos" if r["pnl"] > 0 else "neg"}">{r["pnl"]:+.3f}</td></tr>' for r in exs)
DX = json.load(open(f"{O}/dip/dip_examples.json"))
dexrows = "".join(f'<tr><td>{time.strftime("%m-%d %H:%M", time.gmtime(r["created"] + 18000))}</td><td>{tok(r["mint"], r["name"])}</td><td>{r["age"]} s</td>'
                  f'<td>{tx(r["sell_sig"], str(r["sell_sol"]) + " SOL")}</td><td>{tx(r["after_sig"], str(r["ahead"]) + " ahead")}</td><td>{r["entry_px"]:.3f}</td>'
                  f'<td>{tx(r["exit_before_sig"], "this tx") if r["exit_before_sig"] else "-"}</td><td>{r["exit_px"]:.3f}</td><td>{r["buyers_between"]}</td>'
                  f'<td class="{"pos" if r["pnl"] > 0 else "neg"}">{r["pnl"]:+.4f}</td></tr>' for r in DX)
# ---- forward logs (latest block of each)
def last_block(fn, start="==="):
    if not os.path.exists(fn): return "(not started)"
    t = open(fn).read(); i = t.rfind("\n" + start)
    return t[i + 1:] if i >= 0 else t
fwd_dip = last_block(f"{O}/dip/fwd_dip.log")
fwd_f2 = last_block(f"{O}/dryrun/fwd_loop.log")
fwd_f2 = "\n".join(l for l in fwd_f2.splitlines() if l.startswith("===") or "forward launches" in l or "TRACK A" in l or re.match(r"\s+L\d+ (slip|proafter)", l) or re.match(r"\s+\d\dh \|", l))
def fwd_table(block):
    rows = []; test = "?"
    for line in block.splitlines():
        if line.startswith("FORWARD"):
            m0 = re.match(r"FORWARD (\S+) test", line); nm = m0.group(1) if m0 else "?"
            test = {"dip": "8-slot exit", "DIP4": "4-slot exit", "DIP2": "2-slot exit"}.get(nm, nm) + (", spacing 5" if "spacing 5" in line else "")
            m_ = re.search(r"forward dips (\d+) over ([\d.]+) h", line); test += f" ({m_.group(2)} h of data)" if m_ else ""
            continue
        m = re.match(r"\s+(?:DIP\d )?model L(\d+) top\s+5%: (.*)", line)
        if m:
            cells = {L: (n, tot) for L, n, tot in re.findall(r"L(\d+): n (\d+) mean [+-][\d.]+ total ([+-][\d.]+)", m.group(2))}
            rows.append((test, m.group(1), cells)); continue
        g = re.match(r"\s+(?:DIP\d )?model L(\d+) top\s+5% with 2% guard: (.*)", line)
        if g:
            cells = {L: ("", tot) for L, tot in re.findall(r"L(\d+): ([+-][\d.]+)", g.group(2))}
            rows.append((test + " + 2% guard", g.group(1), cells))
    if not rows: return "<p class=\"mut\">(no forward trades yet)</p>"
    h = "<table><tr><th>Test</th><th>Model</th>" + "".join(f"<th>at {L} ms</th>" for L in ("20", "35", "50", "75")) + "</tr>"
    for test, ml, cells in rows:
        h += f"<tr><td>{esc(test)}</td><td>L{ml}</td>" + "".join(
            (f'<td class="{"pos" if float(cells[L][1]) > 0 else "neg"}">{cells[L][1]}' + (f'<br><small>n {cells[L][0]}</small>' if cells[L][0] else '') + '</td>' if L in cells else "<td>-</td>") for L in ("20", "35", "50", "75")) + "</tr>"
    return h + "</table>"
fwd_dip_tab = fwd_table(fwd_dip)
def f2_table(block):
    rows = []; hdr = ""
    for line in block.splitlines():
        if "TRACK A (FINAL-2 live picks after the freeze" in line:
            m_ = re.search(r"freeze: (\d+)", line); hdr = f"{m_.group(1)} picks" if m_ else ""
        m = re.match(r"\s+L(\d+) (slip|proafter_slip)\s+fills\s+(\d+)/\s*(\d+) .*?A4 \(8 s\) ([+-][\d.]+)", line)
        if m: rows.append(m.groups())
    if not rows: return "<p class=\"mut\">(no FINAL-2 forward block)</p>"
    h = f"<table><tr><th>Landing</th><th>Variant</th><th>Fills / picks</th><th>Sell at 8 s</th></tr>"
    for L, var, f, n, a4 in rows:
        h += f'<tr><td>{L} ms</td><td>{"pros\' later buys removed" if var.startswith("proafter") else "slippage"}</td><td>{f} / {n}</td><td class="{"pos" if float(a4) > 0 else "neg"}">{a4}</td></tr>'
    return h + "</table>"
f2_tab = f2_table(fwd_f2)
CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd;--pos:#0a7a2f;--neg:#b3261e;--card:#f6f7f9;--acc:#1a56db}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121212;--fg:#ececec;--mut:#a0a0a0;--line:#333;--pos:#5fd38a;--neg:#ff8a80;--card:#1c1c1e;--acc:#8ab4ff}}
:root[data-theme="dark"]{--bg:#121212;--fg:#ececec;--mut:#a0a0a0;--line:#333;--pos:#5fd38a;--neg:#ff8a80;--card:#1c1c1e;--acc:#8ab4ff}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;max-width:900px}
h1{font-size:21px;margin:4px 0 2px}h2{font-size:17px;margin:22px 0 6px;border-top:1px solid var(--line);padding-top:14px}
.mut{color:var(--mut);font-size:13px}.card{background:var(--card);border-radius:10px;padding:10px 14px;margin:10px 0}
table{border-collapse:collapse;font-size:13px;margin:6px 0;display:block;overflow-x:auto;max-width:100%}td,th{border:1px solid var(--line);padding:4px 6px;text-align:right;white-space:nowrap}
td:first-child,th:first-child{text-align:left}.pos{color:var(--pos)}.neg{color:var(--neg)}a{color:var(--acc)}
pre{background:var(--card);padding:8px;border-radius:8px;font-size:11px;overflow-x:auto;white-space:pre}
li{margin:3px 0}"""
import collections as _co, statistics as _st
try:   # the independent check's corrected census (unique buys, FIFO, unsold remainder marked to market, collector tx costs)
    _R = [json.loads(_l) for _l in gzip.open(f"{O}/verify_dip/v2_out/census_fifo.jsonl.gz", "rt")]
    _W = _co.defaultdict(list)
    for _r in _R: _W[_r["u"]].append(_r)
    _pn = lambda v: sum(x["back"] + x["mtm"] - x["cost"] - x["txc"] for x in v)
    _rows = sorted(((_pn(v), u, v) for u, v in _W.items() if len(v) >= 30), key=lambda z: -z[0])
    census_rows = "".join(f'<tr><td>{acct(u)}</td><td>{len(v)}</td><td class="{"pos" if p > 0 else "neg"}">{p:+.1f}</td><td>{_st.median(x["dt"] for x in v):.0f} ms</td>'
                          f'<td>{_st.mean(x["cost"] for x in v):.2f}</td></tr>' for p, u, v in _rows[:10])
    _big = [v for v in _W.values() if len(v) >= 100]
    census_sum = (f"{len(_R):,} unique round trips by {len(_W):,} wallets; the {len(_big)} wallets with ≥100 trips made "
                  f"{sum(_pn(v) for v in _big):+.0f} SOL net of transaction costs ({sum(1 for v in _big if _pn(v) > 0) / len(_big):.0%} of them positive)")
except Exception as _e:
    census_rows = ""; census_sum = f"(census not available: {_e})"
def _ex_row(x):
    guard = "buy fails (price &gt;2% above the dump), −0.0002" if (x["px"] or 1) > 1.02 else "buys"
    cls = "pos" if x["pnl"] > 0 else "neg"
    return (f'<tr><td>{x["t"]}</td><td>{tok(x["m"], x["m"][:6])}</td><td>{x["age"]:.1f} s</td><td>{tx(x["sig"], "%.2f SOL" % x["sell"])}</td>'
            f'<td><code>{x["disc"]}</code></td><td>{x["px"]:.3f}</td><td class="{cls}">{x["pnl"]:+.4f}</td><td>{guard}</td></tr>')
try:
    direct_ex_rows = "".join(_ex_row(x) for x in json.load(open(f"{O}/dipshadow/direct_examples.json")))
except Exception as _e:
    direct_ex_rows = f"<tr><td colspan=8>examples not available: {_e}</td></tr>"
H = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Strategy Decision Brief</title><style>{CSS}</style></head><body>
<h1>What works, and what it needs</h1><div class="mut">Built {now}. Analysis only: no trades, nothing changed on the server. All times PKT.</div>
<div class="card" style="border-left:4px solid var(--acc)"><b>TL;DR (updated 14:09 PKT)</b><ol>
<li><b>At our current speed nothing makes real money.</b> Our ~75 ms (Run 2, measured) is about replay "82 ms". There, even the best version (direct-sell dip-backrun with a 2% price guard) is only ≈ 1.5–3 SOL/day.</li>
<li><b>Dip-backrun works if we are fast.</b> It buys right after a big pump.fun sell on a young launch (direct sells seen in shreds, routed ones on the executed feed) and sells 2–4 slots later. It has been checked independently twice. At a REAL 35 ms reaction, expect ≈ <b>8–12 SOL/day (≈ $840–1,250/day at $104.6/SOL)</b>. At a real 50 ms ≈ 2–8.5. The range comes from two ways of modelling how the fast bots react to our buy: strict, using their typical accepted price as a hard limit; or their real decoded on-chain limits, which are usually much looser. The higher end is better supported, since we now have every follower's exact limit, but only a live test can rule out bots holding back after seeing our buy. <b>Caution from the first 3 forward hours (12:09–15:00):</b> all picks together are still positive (+0.35 with real follower limits, +0.42 guarded), but the direct-sell picks were negative (−0.14 on 51) while routed picks made +0.49 on 66. So the engine should take both kinds of trigger: direct from shreds, plus routed from the executed feed ~15 ms later (in the six-block test this hybrid gives "35 ms" +21.5, guarded). The 2% price guard, now required (see 2c: 29% of direct sells fail on chain), puts it at the lower end. At a real 50 ms it is only a few SOL/day.</li>
<li><b>It is a real, stable pro niche.</b> 53 pro wallets make ≈ +190 SOL net per ~33 h this way; 79% are profitable, and the winners of the first data run won again in the second. The best (HkQ7hMjy, DYXDDrZC) land about a real 30–35 ms after the sell. They call pump.fun directly with one landing service per leader client and a ~0.001 SOL tip (section 2c/2d).</li>
<li><b>What it needs (your OKs):</b>
  <ul><li>(a) speed: the probe, ≤0.25 SOL of fail-by-design buys (section 4);</li>
  <li>(b) the dip engine: spec ready in <code>ops/dip/ENGINE_V1.md</code>. Triggers from shreds plus Kaldera's transaction stream, which we probably already pay for and which also gives the history; measure it with the zero-cost feed race (<code>ops/gap/feed_race_exec.toml</code>);</li>
  <li>(c) your call: the profit comes from other bots buying right after us. Does that fit "become them"?</li></ul></li>
<li><b>The data collector stops at 20:43 PKT today</b>; restarting it needs your OK, and the forward tests and retraining depend on it.</li></ol></div>
<div class="card"><b>Bottom line</b><ul>
<li><b>Nothing is proven profitable at our current landing speed (~75 ms).</b> Your own 24 h paper engine on the server agrees: 267 paper trades, <b>first in line +11.9 SOL, at our real 74 ms +0.11 SOL</b> (synced file <code>shadow/tg_paper_results.txt</code>, 11:07 PKT).</li>
<li><b>Two strategies work in replay if we land in about 20–35 ms with cheap transactions (both are positive on both data runs at 20 ms):</b> FINAL-2 (buy at the create, corrected after an independent check) and <b>Dip-backrun</b> (new today, learned from a consistently profitable wallet).</li>
<li><b>Why we are slow (from the landing study):</b> our engine sends one transaction that carries every service's tip. The 20 fastest snipers instead sign one copy per service on a durable nonce, and they land a median 39 ms after the create. Our own probes on 10-21 show the same: one route per send landed 17–34 ms after the create, while one transaction to several routes landed 73–148 ms (Run 2 used 5 routes on Jito-client leaders). <b>The first fix is config only: one route per leader client.</b> It can be checked for about 0.1–0.3 SOL with the existing fail-by-design probes. It's a send-path change, so it's <b>your decision</b>.</li>
<li><b>Who pays us (important):</b> in both strategies, the buying that lifts our exit price in the first seconds comes from about <b>540 consistently profitable bots</b> (found in the wallet census), not from ordinary traders and not from the 9 case-study pros. Remove their later buys and both strategies lose. Remove 541 random active wallets instead and both stay positive. So "becoming them" means getting into a trade just ahead of the rest of that bot group. We don't sandwich anyone or see pending transactions, but our profit is their later entry. <b>Please decide whether that fits your rule.</b></li>
<li><b>Dip-backrun is the strongest result, independently checked:</b> the checker rebuilt it from the raw data and got identical numbers, with no look-ahead. But my replay's latency is optimistic for this kind of trade. Corrected to <b>real</b> latency, at 0.5 SOL per trade over the 28.6 h of data:
<ul><li>real 35 ms: <b>about +10 SOL (≈ 8–9 SOL/day)</b>, or +6 to +8 at 0.002 SOL per tx; training only on earlier data gives +5 to +6;</li>
<li>real 50 ms: about 0;</li>
<li>real 75 ms (today): a loss.</li></ul>
Each 10 ms costs about 5 SOL. The wallet we learned it from makes ~+14 SOL per run doing exactly this at ~39 ms.</li>
<li><b>Forward tests run hourly</b> on new data (FINAL-2 since 08:26; Dip models frozen at 10:34). The latest results are below.</li></ul></div>

<h2>1. FINAL-2 (buy first after the dev's bundle, sell at 8 s), corrected</h2>
<p>An independent checker found 3 replay bugs, all in our favour. They are fixed, and our replay now matches the checker within 0.04 SOL. The table shows total SOL at 0.5 SOL per trade, with the pros' later buys removed and follower slippage applied; P = bootstrap chance the total is above zero.</p>
<table><tr><th>Landing</th><th>Overnight, today's fees</th><th>Overnight, CW-style fees</th><th>Overnight, Run 2 fees</th><th>Daytime, today's fees</th><th>Daytime, CW-style</th><th>Daytime, Run 2 fees</th></tr>{f2rows}</table>
<p><b>At 20 ms</b> (our single-route probes on 10-21 landed 17–34 ms), pros' later buys removed: overnight <span class="pos">+4.00</span> (CW-style <span class="pos">+4.84</span>), daytime <span class="pos">+0.54</span> (CW-style <span class="pos">+0.78</span>); 184 of 235 and 55 of 66 attempts fill. This is the only setup positive both overnight and in daytime, and it is still carried by the best trades (without the best 5: −1.34 / −1.26).</p>
<p class="mut">Overnight = R2, 10-22 23:31 → 10-23 08:16 (8.3 h, fully out of sample). Daytime = R1 clean tail, 10-22 14:50–17:53 (3 h). The 5 best trades carry the overnight total. Verdict: weak; positive overnight only, and only with fast landing and cheap fees. <b>The daytime forward test (section 5) loses at every landing speed, even 20 ms.</b></p>

<h2>2. Dip-backrun (new): become wallet {acct("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ")}</h2>
<ul><li><b>Where it came from:</b> a census of all 142k wallets in our data (748k wallet-launch rows). This wallet made +16 SOL in R1 and +15 SOL in R2 over 2,198 round trips, with a 53% win rate and ~0.0008 SOL per transaction. Our replay reproduces its trades exactly.</li>
<li><b>What it does:</b> 71% of its buys land <b>right after a sell of ≥1 SOL in the same block</b> (vs 2.7% for a random buy). It enters about 6 s after the create, at a median ~36 ms after the sell, then sells 1–8 s later into the rebound from ordinary buyers.</li>
<li><b>Copying it, or buying every big dip, loses</b> (−2% to −5% per trade). The edge is in choosing which dips to buy. A model trained on one run and tested on the other picks them (top 5% of dips, sell 8 slots ≈ 1.7 s later, 0.5 SOL).</li></ul>
<table><tr><th>Our buy lands … after the sell</th><th>Train R1 → test R2 (slippage)</th><th>… our sell 75 ms into its slot</th><th>Train R2 → test R1 (slippage)</th><th>… our sell 75 ms into its slot</th></tr>{diprows}</table>
<p class="mut">Timing uses each transaction's position in its block, which correlates 0.96 with our engine's real arrival times. It is about 7 ms off: pessimistic for snipes, but <b>optimistic for this trade</b>, so see the corrected real-latency table below. Follower slippage limits are drawn from 711 decoded real limits (INFERRED); they roughly halve the result. Without slippage, buying right after the sell (0 ms) made +18.6 / +16.5 SOL. At 35 ms the top 5% was positive in 13 of 15 and 13 of 16 PKT hours. Costs assume 0.0008 SOL per transaction, which is what this wallet pays. Verdict: positive in both directions at 20 ms, thin at 35 ms, about break-even or negative at 50 ms, negative at our 75 ms. Frozen models (20 / 35 / 50 ms) are being forward-tested.</p>
<div class="card"><b>Independent check</b> (<code>ops/overnight/verify_dip/VERIFY_DIP.md</code>): everything reproduced exactly from the raw chunks (all 29,810 events, all block totals, five hand-checked trades). No look-ahead that matters. Corrected to <b>real</b> latency, with the fast dip bots' measured price tolerances and our sell timed from our own landing slot (0.5 SOL per trade, total over 28.6 h):
<table><tr><th>Real latency</th><th>0.0008 SOL/tx</th><th>0.002 SOL/tx</th><th>0.003 SOL/tx</th></tr>
<tr><td>20 ms</td><td class="pos">+14.6 … +18.0</td><td class="pos">+11.0 … +14.4</td><td class="pos">+8.1 … +11.5</td></tr>
<tr><td><b>35 ms</b></td><td class="pos"><b>+9.6 … +11.3</b></td><td class="pos">+6.1 … +7.7</td><td class="pos">+3.2 … +4.8</td></tr>
<tr><td>50 ms</td><td class="pos">+1.9 … +2.5</td><td class="neg">−1.9 … −1.3</td><td class="neg">−5.0 … −4.4</td></tr>
<tr><td>75 ms (Run 2 speed)</td><td class="neg">−6.8 … −6.2</td><td class="neg">−10.2 … −9.6</td><td class="neg">−13.1 … −12.5</td></tr></table>
<small>At real 35 ms:
<ul><li>bootstrap 95% range +6.1 … +15.0;</li>
<li>without the best 10 launches +6.3 … +7.9;</li>
<li>training only on earlier blocks +5.0 … +6.3.</li></ul>
0.5 SOL is the right size; 1 SOL does not add. The latency here is real time from the big sell being processed to our buy being processed.<br>
<b>Confirmed with real data (12:05 PKT):</b> I decoded the real slippage limits of 13,294 buyers who followed the selected dips (read-only RPC). The six-block test with those limits gives +13.0 SOL at replay "35 ms" (≈ real 28 ms), all six blocks positive, and +4.4 at replay "50 ms". That lands at about +9 at a real 35 ms, the same as the independent estimate. <b>Expect ≈ 7–8 SOL/day at a real 35 ms (0.5 SOL per trade), and next to nothing by 50 ms.</b></small></div>
<div class="card"><b>The replay's own six-block test</b> (block-position latency units, which run ~7 ms optimistic for this trade, so read "35 ms" here as roughly a real 28 ms). Blocks are ~4–8 h each, day and night. Each block is tested by a model trained on the other five. Sell 4 slots (~0.85 s) after our buy, follower slippage imputed, our sell landing 75 ms into its slot, 0.5 SOL, top 5% of dips:
<table><tr><th>Our buy lands</th><th>03–07</th><th>07–13</th><th>13–21</th><th>21–01</th><th>01–05</th><th>05–10</th><th>Total ~31 h</th></tr>
<tr><td>20 ms</td><td class="pos">+5.37</td><td class="pos">+4.59</td><td class="pos">+3.52</td><td class="pos">+4.61</td><td class="pos">+4.27</td><td class="pos">+5.85</td><td class="pos"><b>+28.2</b></td></tr>
<tr><td>35 ms</td><td class="pos">+3.22</td><td class="pos">+2.83</td><td class="pos">+2.10</td><td class="pos">+2.21</td><td class="pos">+3.32</td><td class="pos">+4.39</td><td class="pos"><b>+18.1</b></td></tr>
<tr><td>50 ms</td><td class="pos">+0.98</td><td class="pos">+2.12</td><td class="pos">+0.52</td><td class="pos">+0.85</td><td class="pos">+1.01</td><td class="pos">+2.27</td><td class="pos"><b>+7.7</b></td></tr>
<tr><td>75 ms (now)</td><td class="neg">−1.06</td><td class="pos">+1.14</td><td class="neg">−0.27</td><td class="neg">−2.07</td><td class="neg">−1.16</td><td class="neg">−0.62</td><td class="neg"><b>−4.1</b></td></tr>
<tr><td>50 ms + 2% price guard</td><td class="pos">+1.27</td><td class="pos">+2.85</td><td class="pos">+1.28</td><td class="pos">+0.91</td><td class="pos">+1.55</td><td class="pos">+2.07</td><td class="pos"><b>+9.9</b></td></tr>
<tr><td>75 ms + 2% price guard</td><td class="pos">+0.08</td><td class="pos">+1.07</td><td class="pos">+0.22</td><td class="neg">−0.88</td><td class="neg">−0.23</td><td class="pos">+0.07</td><td><b>+0.3</b></td></tr></table>
<small>Price guard = the buy's minimum-tokens-out is set from the price right after the big sell, so the buy fails on chain (base + priority fee only) if others pushed the price more than 2% higher before we landed. The wallet we learned this from appears to do the same (about 3 cheap failed attempts per filled buy).</small>
Every block is positive at 20, 35 and 50 ms; at our current 75 ms it loses. At 20–35 ms: +0.009 to +0.025 SOL per trade, 55–75% wins, about 45–50 trades per hour. In these replay units that is roughly 6 SOL/day at "50 ms", 14 at "35 ms" and 22 at "20 ms", assuming ~0.0008 SOL per transaction. <b>Use the corrected real-latency table above for decisions.</b> At 0.003 SOL per transaction, every block stays positive at 20–35 ms, but 50 ms turns about break-even. <b>Shorter holds widen the speed window</b> (12:10 PKT; real follower limits, six-block test, replay units):
<ul><li>selling 2 slots (~0.4 s) after our buy gives +16.9 at "35 ms" and +7.2 at "50 ms" (+9.3 with the 2% guard);</li>
<li>4 slots gives +14.5 and +4.8 (+6.8 with the guard).</li></ul>
"50 ms" here is about a real 43 ms. The exit was picked among four, so treat it as promising; 2-slot models (frozen 12:09) are now in the forward test. <b>Risk</b> (same six-block test, 2-slot exit, 2% guard, 0.5 SOL):
<ul><li>at "35 ms": 1,410 trades over 32 h, max drawdown <b>0.51 SOL</b>, 97% of hours positive, worst hour −0.05, worst single trade −0.30;</li>
<li>at "50 ms": max drawdown 0.34, 88% of hours positive.</li></ul>
Capital needed is about 1–2 SOL, since positions last under a second. <b>Best version so far (12:40 PKT; not yet independently checked):</b> take the next big sell on the same launch 5 slots later instead of 20, sell 2 slots after our buy, real follower limits.
<ul><li>"35 ms": <b>+30.6 SOL over ~33 h</b>, all six blocks positive (+3.6 to +6.3 each).</li>
<li>"50 ms" (≈ real 43 ms): <b>+16.9</b>, all six positive (+1.8 to +4.1).</li></ul>
Scaled the way the independent check scaled the base version, that is roughly <b>12–15 SOL/day at a real 35 ms (≈ $1.3–1.6K/day)</b>. Our own round trip barely moves the curve net, but it isn't modelled. It is in the forward test (2-slot and 4-slot, 5-slot spacing). <b>Fewer, bigger trades</b> (closer to your "few high-quality trades" goal): top 2% of dips at 1 SOL is also positive in all six blocks, at <b>+16.1 SOL over ~31 h at 35 ms</b> (+26.4 at 20 ms). That is about 19 trades per hour, +2% to +4% per trade. Top 1% at 1 SOL gives +10.3 (~10 trades per hour). The 4-slot exit was chosen after seeing 4/6/8/12, but it is consistent with the wallet's own short holds. Models frozen at 10:52 PKT (FRZ-DIP4-L20 / L35) are forward-tested hourly.</div>
<p><b>Our own replayed dip trades</b> (model-selected, entry 35 ms after the sell, sell 4 slots later; prices relative to the price right after the big sell):</p>
<table><tr><th>Created</th><th>Token</th><th>Age</th><th>Big sell</th><th>We land behind</th><th>Entry</th><th>Our sell lands before</th><th>Exit</th><th>Buys between</th><th>PnL</th></tr>{dexrows}</table>
<p><b>Real trades by this wallet</b> (the big sell, its buy right after, its exit):</p>
<table><tr><th>Created</th><th>Token</th><th>Age</th><th>Big sell</th><th>Its buy</th><th>Its exit</th><th>PnL</th></tr>{exrows}</table>

<h2>2b. At TODAY's speed (~75 ms): a thin version that may already work (afternoon, replay units)</h2>
<p>The <b>2% price guard</b> is what makes this possible: the buy fails cheaply (~0.0002 SOL) whenever faster bots already pushed the price more than 2% above the dump price before we landed. About half the attempts fail that way.</p>
<table><tr><th>Setup (0.5 SOL, real follower limits, next dip on a launch allowed 5 slots later)</th><th>"75 ms"</th><th>"100 ms"</th></tr>
<tr><td>Full model, top 5%, sell 2 slots later, 2% guard</td><td class="pos"><b>+7.3</b> (6/6 blocks)</td><td class="pos">+0.8 (4/6)</td></tr>
<tr><td>Same without the guard</td><td>+1.4</td><td class="neg">−7.1</td></tr>
<tr><td><b>Full model, only dumps ≥10%, top 10–20%, guard</b></td><td class="pos"><b>+7.2 … +8.3 (6/6)</b></td><td class="pos"><b>+4.6 (6/6)</b></td></tr>
<tr><td>Pre-dump features only, dumps ≥10%, top 10%, guard</td><td class="pos">+5.6 (6/6)</td><td class="pos">+2.8 (6/6)</td></tr>
<tr><td>Sell 1 slot later (instead of 2), guard</td><td class="pos">+5.8</td><td>—</td></tr>
<tr><td>0.25 SOL instead of 0.5, guard</td><td class="pos">+3.2</td><td>—</td></tr></table>
<p class="mut">Totals over ~33 h of data. Replay "75 ms" is about a real 68 ms, so our real 75 ms sits between the two columns. After the independent check's usual corrections, expect roughly <b>3 SOL/day (≈ $300) at today's speed</b>; the deep-dump version stays positive in every block even at "100 ms". It is real but thin, far from the $1–2K goal, so the speed fix still matters most. A model trained for 75 ms (frozen 12:54 PKT) is now in the hourly forward test with its guard line.</p>
<h2>2c. What a fast engine can see, and how the best dip bot sends (afternoon, 13:13 PKT)</h2>
<p><b>Most pump trades can't be read from shreds:</b> 76% of 1,500 random trades go through routers or bots' own programs. But <b>the dips the model picks are mostly direct pump.fun sells</b> (57–71% of picks vs 41% of all dips), and those carry most of the profit. Checked on 7,719 real trigger transactions (read-only RPC); every one of the 44,535 dips was labelled from our own data (99.8% agreement).</p>
<table><tr><th>Six-block test, top 5%, sell 2 slots later, REAL follower limits (unguarded / 2% guard), SOL per ~33.5 h</th><th>"35 ms"</th><th>"50 ms"</th><th>"75 ms"</th></tr>
<tr><td>All big sells (needs routed sells too)</td><td class="pos">+26.4 / +24.4</td><td class="pos">+13.3 / +13.2</td><td>−0.2 / <span class="pos">+6.3</span></td></tr>
<tr><td><b>Direct sells only</b> (what a shred-fast engine sees)</td><td class="pos"><b>+20.1</b> / +17.2 (6/6 blocks)</td><td class="pos"><b>+11.1</b> / +8.2 (6/6)</td><td class="pos">+3.5 / <b>+5.5</b> (5/6)</td></tr>
<tr><td>≈ SOL per day (direct only)</td><td>~14</td><td>~8 (guarded ~6)</td><td>~2.5 (guarded ~4)</td></tr>
<tr><td>Direct sells from shreds <b>+ routed sells from the executed feed ~15 ms later</b>, 2% guard</td><td class="pos">+21.5 (guarded)</td><td class="pos">+10.3 (guarded)</td><td>—</td></tr>
<tr><td>Direct only at <b>1 SOL</b> per trade (partly estimated limits)</td><td class="pos">+29.6 / +25.6 (~21/day)</td><td class="pos">+13.9 / +11.0 (~10/day)</td><td>+2.8 / <span class="pos">+7.3</span></td></tr></table>
<p class="mut"><b>Speed units matter.</b> "L" is measured by block position, the same way as HkQ7hMjy's median 39 ms, so matching it means the "35–50 ms" columns. For our own REAL latency (sell executed → our buy executed), applying the independent check's measured timing errors to these picks gives a real 35 ms ≈ +16–17 per ~33.5 h. Its stricter model of the fast bots (they skip once our buy moved the price) gives ≈ +11–13. So <b>≈ 8–12 SOL/day at a real 35 ms</b>, and ≈ 2–8.5 at a real 50 ms (<code>ops/dip/PLAN.md</code>, "REAL-latency estimate"). <b>False triggers:</b> 29% of direct pump sell transactions fail on chain, mostly because the seller does not even hold the token. The engine checks the sell's minimum-out against the curve, which catches ~62% of the failing big sells. It always buys with the 2% guard, so any other false trigger costs only a failed buy (~0.0002 SOL, about 0.003 SOL/h). A seller-holdings check would catch more but also drop ~20% of the real profit (some dumpers got their tokens by transfer), so it is not used. Real slippage limits of ~18,700 more buyers were decoded at 13:30–13:40 PKT (read-only RPC); they cut 7–15% at "35–50 ms", as the independent check predicted. Direct picks beat routed picks in every time block at every speed (18 of 18). The first 1.2 h of forward data is too small to judge (15 direct picks, flat); it is scored every ~45 min.</p>
<p>So the engine can take the trigger straight from shreds (three pump sell layouts, decoder checked on 800 real triggers) and the trade history from a feed with execution results. Routed sells reach the pros a few ms later anyway (independent check: about 2–5 ms for HkQ7hMjy, 5.5 ms for the first buyer of any wallet). <b>The history may be up to ~100 ms late</b> at almost no cost (six-block test: direct-only "35 ms" +21.6 with fresh history vs +21.8 with 100 ms late history; but the guarded version loses 7–32%, most at "75 ms"), so a slower, cheaper executed feed is enough. Constant-K's Kaldera, which we already use, is a full Yellowstone gRPC service with transaction streams (<a href="https://www.constant-k.com/yellowstone-grpc/">vendor page</a>), so this feed is probably already paid for (to confirm, and to measure with the zero-cost feed race). Build spec: <code>ops/dip/ENGINE_V1.md</code>.</p>
<p><b>Examples</b> of direct-sell dips the model picked (out-of-sample, entry "50 ms", 0.5 SOL, sell 2 slots later; the big-sell link opens the real trigger transaction on Solscan):</p>
<table><tr><th>PKT</th><th>Token</th><th>Age</th><th>Big sell (tx)</th><th>Sell layout</th><th>Our entry price / dump price</th><th>P&amp;L SOL</th><th>2% guard</th></tr>{direct_ex_rows}</table>
<p><b>How HkQ7hMjy sends</b> (1,415 of its dip buys; tip accounts from our collector, leader clients from the leader schedule): a plain direct pump buy, tip 0.001 SOL plus ~0.00013 SOL priority fee, <b>one landing service per leader client</b>:</p>
<table><tr><th>Leader client (share of slots)</th><th>Its choice (median ms after the big sell)</th></tr>
<tr><td>BAM (38%)</td><td>Nozomi 73% (41 ms)</td></tr><tr><td>Harmonic (30%)</td><td>Nozomi 84% (37 ms)</td></tr>
<tr><td>Jito-Solana (23%)</td><td><b>Helius 24% (29 ms)</b>, no tip 30% (44), Nozomi 19% (44)</td></tr>
<tr><td>Firedancer (7%)</td><td>no tip 67% (43 ms), Nozomi 27% (35)</td></tr></table>
<p class="mut">That matches our config-only speed idea (one route per leader client), except it uses Nozomi on BAM and Firedancer leaders. The speed probe already tests Nozomi alone on every leader. The fastest backrunners (3–20 ms) are a different game: own programs, almost no fee, transactions queued before the dump ("spray"), which we rejected on cost. Details: <code>ops/dip/PLAN.md</code>.</p>

<h2>2d. Who else does this: every wallet that buys right after big sells (census, corrected by the independent check at 14:03 PKT)</h2>
<p>Every buy that landed within 150 ms after a ≥1 SOL sell on a young launch, followed to that wallet's own sells (~33 h of data; each buy counted once, unsold tokens marked to market, transaction costs included): {census_sum}. <b>Skill persists:</b> wallets that were profitable in the first data run made +120 SOL in the second (85% of them positive again). On closed trips, the profitable delay band is <b>0–60 ms</b> after the sell (0–10 ms best, +7%); beyond 60 ms it is about zero or negative. <i>My first census double-counted buys and valued unsold tokens at zero; the independent check fixed both (top wallets are about 30–50% smaller than I first reported).</i></p>
<table><tr><th>Wallet (GMGN)</th><th>Round trips</th><th>P&amp;L SOL (net of tx costs)</th><th>Median delay after the sell</th><th>Mean size SOL</th></tr>{census_rows}</table>
<p class="mut">The top wallets call pump.fun directly and use one landing service per transaction: DYXDDrZC Astralane / speedlanding, HkQ7hMjy Nozomi / Helius, sssssDdM mostly a plain priority fee. DYXDDrZC holds longest (~15 s) and lives off a few big pumps. A plain longer hold with our picks loses (8+ slots worse even after the check's fix), and "hold until a pro sells" lost too.</p>

<h2>3. Who pays us: the test</h2>
<p>Buys after our entry removed for one wallet group at a time (follower slippage on; FINAL-2 = overnight R2, sell at 8 s; dip = 35 ms, 4-slot exit, six blocks):</p>
<table><tr><th>Group removed</th><th>FINAL-2 20 ms</th><th>FINAL-2 45 ms</th><th>FINAL-2 75 ms</th><th>Dip 35 ms</th></tr>
<tr><td>none</td><td class="pos">+6.75</td><td class="pos">+3.43</td><td class="pos">+1.68</td><td class="pos">+18.07</td></tr>
<tr><td>the 9 case-study pros</td><td class="pos">+4.00</td><td class="pos">+2.06</td><td class="pos">+1.07</td><td class="pos">+18.07</td></tr>
<tr><td>321 sniper wallets (+ pros)</td><td class="pos">+2.16</td><td class="pos">+1.31</td><td class="pos">+0.56</td><td class="pos">+17.85</td></tr>
<tr><td>541 random active wallets</td><td class="pos">+3.83</td><td class="pos">+1.87</td><td class="pos">+0.42</td><td class="pos">+11.36</td></tr>
<tr><td><b>541 consistently profitable bots</b></td><td class="neg">−2.46</td><td class="neg">−1.36</td><td class="neg">−1.88</td><td class="neg">−14.11</td></tr></table>
<p><b>Same test on today's best version</b> (direct sells only, real follower limits, sell 2 slots later, six blocks; 14:32 PKT): none removed "35 ms" +20.1 / "50 ms" +11.1 / "75 ms" +3.5; 541 random wallets removed +15.5 / +7.9 / +2.0; <b>the 541 profitable bots removed −7.8 / −10.7 / −15.6</b>. The answer does not change.</p>
<p class="mut">The consistently profitable bots made money in both data runs and in at least 3 of 4 quarters, with ≥30 launches each. They include HkQ7hMjy itself. Across all launches they are only 23% of buy SOL in the first 10 s after the bundle (ordinary wallets 64%, snipers 8%, pros 5%; 1/8 sample, 2,863 launches). But on the trades our models pick, their buying is what lifts the price. In effect, our models learned to predict when that group will buy, and the profit is being in just before them.</p>

<h2>4. What I recommend (each step needs your OK)</h2>
<div class="card"><b>Our 75 ms is probably self-inflicted, and the first fix is config only.</b> Our own probes on 10-21 (<code>ops/run2/RUN2_PLAN.md</code>) show:
<ul><li>One route per send landed fast: buy-shaped probes landed 17–34 ms after the create (BAM 17.6, Jito-client 17.4, Harmonic 27–34).</li>
<li>Multi-route sends in one transaction were slow: 96–148 ms on Harmonic leaders (7 of 7).</li>
<li>Run 2 then sent one transaction to 5 routes on Jito-client leaders (<code>ROUTES</code> in <code>run1_common.sh</code>) and landed at 73–75 ms.</li></ul>
<b>Step 0, ≤0.25 SOL on the FRZ wallet:</b> measure it with buy-shaped probes that fail by design (base plus priority fee only, never a token). They go through one route at a time (helius, nozomi, astralane, landx), then today's multi-route design for comparison.
If single routes land at ≤45 ms after Alpenglow, set <code>ROUTES</code> to one path per leader client. That is a config change, not code.
<br><small>Server check (read-only, 10:46): <code>/root/run1/probe_buy.sh</code>, the probe binary <code>/root/sniper-probe/snipe_engine</code>, the leader list and the configs are all there. The script refuses to start while any <code>snipe_engine</code> runs, and your 24 h paper engine (pid 134197) is running now. One command runs all of it: copy <code>ops/final2/probe_speed.sh</code> and <code>ops/final2/probe_to_pnl.py</code> to <code>/root/run1/</code>, then <code>sudo bash /root/run1/probe_speed.sh</code>. It runs 4 single-route phases plus today's multi-route design, capped at 0.05 SOL each, so about 0.25 SOL at most. Then score with <code>python3 /root/run1/probe_report.py /root/run1/ps_*.jsonl</code>. <code>ops/final2/probe_to_pnl.py</code> turns the measured latencies into the expected dip SOL/day per route, so the go/no-go is in SOL. FRZ needs a ~0.3 SOL top-up.</small></div>
<ol><li><b>Send redesign (later, more speed):</b> one signed copy per service on a durable nonce, each copy carrying only its own tip (Helius on BAM/Jito leaders, speedlanding or nozomi on Harmonic, astralane on Firedancer, LandX everywhere, plus one priority-fee-only copy). Only one copy can land. Details: <code>ops/final2/SEND_DESIGN.md</code>, <code>ops/overnight/landing/LANDING_PATHS.md</code>.</li>
<li><b>Measure each step with the buy-shaped probes</b> before any live buy. The target is ≤45 ms (pros: 39 ms median).</li>
<li><b>Engine:</b> the dip model's scoring and its 35 features are already ported to Rust and match the Python exactly (<code>src/dip.rs</code>, 218 test events, 0 mismatches). It is not wired in or deployed. A zero-cost shadow mode (decisions logged, no sends) needs about a day more. Live, the trade history must come from a feed with execution results: <b>76% of all pump trades go through routers or bots' own programs</b>, which shreds can't decode (1,500 random trades, read-only RPC). The trigger can still come from shreds: <b>57–71% of the dips the model picks are direct pump sells, and they carry 74–86% of the profit</b> (7,719 trigger txs checked). Routed sells reach even the best bots a few ms later (independent check: ~2–5 ms). Details: <code>ops/dip/PLAN.md</code>.</li>
<li><b>If the probe shows ≤45 ms, a sensible order:</b>
<ul><li>(a) the same night, an overnight FINAL-2 test with the single-route config, small and capped. Its engine path (<code>--final2-sock</code>) is built; overnight it was +2.1 to +4.8 SOL per 8.3 h at 20–45 ms with cheap fees, but it is weak in daytime.</li>
<li>(b) meanwhile, build the dip shadow mode (~1 day), shadow-run it, then a small live dip test. Dip is the stronger and more consistent edge.</li></ul></li>
<li><b>Then run whichever strategy the forward tests support,</b> in paper on the server, then with small live size.</li></ol>

<div class="card"><b>Reminder (your OK needed):</b> the 24 h data collector on the server (<code>/root/sniper-collect</code>, run_20261022_1543) ends at <b>20:43 PKT today</b>. Every forward test here reads its data. Restarting it keeps the forward tests running and gives fresh data to retrain the dip model; the market drifts, so the models should be retrained daily.</div>
<h2>5. Forward tests (hourly, on data after each freeze)</h2>
<p><b>Dip-backrun</b> (models frozen 10:34 / 10:47 / 10:52 PKT, the 2-slot DIP2 models at 12:09 and 12:54 PKT; sha256 files in <code>ops/overnight/dip/</code>). Top 5% of dips after the freeze, total SOL at 0.5 SOL per trade with follower slippage, at each entry delay. Each run is cumulative since the freeze:</p>{fwd_dip_tab}
<details><summary class="mut">raw forward log</summary><pre>{esc(fwd_dip)}</pre></details>
<p><b>FINAL-2</b> (frozen 08:26 PKT; corrected replay from the 10:53 run on; cumulative since the freeze, daytime PKT so far):</p>{f2_tab}
<details><summary class="mut">raw forward log</summary><pre>{esc(fwd_f2)}</pre></details>

<h2>6. Tested today and rejected</h2>
<ul><li>A selection model trained directly on our own 45 / 75 ms outcomes: worse than FINAL-2 (negative at every cutoff; FINAL-2 made +3.32 / +1.13 on the same test launches).</li>
<li>Richer dip features (seller history, momentum, bot-cohort counts): no real gain; still nothing at 75 ms.</li>
<li>Dip buys placed first in the next slot (top-of-block, the way wallet ARu4n5mF trades), so that no ms race is needed: negative in every block.</li>
<li>Dips on already-hot tokens (up to 60 min old) with longer holds (to ~1 min): negative in every block at 75–150 ms.</li>
<li>Wider dip triggers (sells ≥0.5 SOL, tokens up to 5 min old): dilute the edge (35 ms +18.1 → +7.1).</li>
<li>Following big buys (≥2 SOL by non-insiders): negative at 35 and 75 ms.</li><li>Copying the census's consistent winners (chosen on R1, copied on R2): negative at every lag and exit, even when 2–8 of them agree.</li>
<li>Buying every big-sell dip with simple filters, including take-profit exits: −1% to −5% per trade.</li>
<li>A time-of-day filter: ordinary buying per launch is about the same overnight and daytime.</li>
<li>The wave-stop exit for FINAL-2: best overnight, worst on the daytime slice.</li>
<li>Dip exits (13:30 PKT, re-checked 14:03): 8–80-slot holds, take-profit at +2/+3/+5%, and "hold until a profitable pro in the same dip sells" were all worse (e.g. at "50 ms": 2 slots +17.3, 10 slots −1.6, ride-with-pro +2.5). Selling 2 or 4 slots after the buy is a tie.</li>
<li>Dip-backrun on graduated tokens' PumpSwap pools (14:36 PKT): the bounce happens instantly (+0.019 per trade only at 0 ms), and at "35–75 ms" it is ≈0 or negative even as an upper bound.</li>
<li>Earlier: S4-style front-running (off-target), later entries 1–180 s, after-sell-out, dev-exit, non-SOL curves.</li></ul>
<p class="mut">Exact commands for the next steps: ops/NEXT_STEPS.md. Files: ops/overnight/STRATEGIES.md (status), verify2/VERIFY_FINAL2.md (independent check), decision/, census/, dip/, copy/, hours/.</p>
</body></html>"""
open(f"{O}/report/DECISION.html", "w").write(H); print("written", len(H))
