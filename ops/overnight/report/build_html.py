#!/usr/bin/env python3
# READ-ONLY, offline: builds the overnight strategy report (S4_STRATEGY.html) from the saved replay / dry-run outputs.
# Every token, wallet and transaction is a link (GMGN / Solscan) so the owner can check each trade by hand.
import os, json, html, statistics, collections, datetime, random, re, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); OV = os.path.dirname(HERE)
e = html.escape
TX = lambda s: f"https://solscan.io/tx/{s}"; ACC = lambda a: f"https://solscan.io/account/{a}"
GW = lambda a: f"https://gmgn.ai/sol/address/{a}"; GT = lambda m: f"https://gmgn.ai/sol/token/{m}"
sh = lambda x, a=4, b=4: f"{x[:a]}…{x[-b:]}" if x else "—"
BAD = re.compile(r"n+[i1!]+g+[g]*(?:e+r+|a+h?|u+h?)|f+a+g+(?:g*o+t+)?|r+e+t+a+r+d|k+i+k+e+", re.I)
def mask(s): return BAD.sub("[masked]", s or "")
def ln(url, text): return f'<a href="{url}" target="_blank" rel="noopener">{e(text)}</a>'
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%m-%d %H:%M:%S") if t else "—"
def pnl(x, d=3): return "—" if x is None else f'<span class="{"pos" if x > 0 else "neg" if x < 0 else ""}">{x:+.{d}f}</span>'
FAIL = 0.005
# ---------------------------------------------------------------- data
FW = json.load(open(os.path.join(HERE, "s4_forward.json")))
R1 = json.load(open(os.path.join(HERE, "r1_guard.json")))
ST = json.load(open(os.path.join(HERE, "stress_s4.json")))
DR = [json.loads(l) for l in open(os.path.join(OV, "dryrun", "dryrun_trades.jsonl"))]
FZ = json.load(open(os.path.join(OV, "dryrun", "frozen.json"))); FZH = hashlib.sha256(open(os.path.join(OV, "dryrun", "frozen.json"), "rb").read()).hexdigest()
FW.sort(key=lambda r: r["bt"]); fw_h = (FW[-1]["bt"] - FW[0]["bt"]) / 3600; fw_mid = FW[0]["bt"] + (FW[-1]["bt"] - FW[0]["bt"]) / 2
def summ(vals, hours, bts=None, mid=None, boot=True):
    v = [x for x in vals]; s = sorted(v); fills = [x for x in v if x != -FAIL]
    random.seed(7)
    ci = sorted(sum(random.choices(v, k=len(v))) for _ in range(1000)) if (boot and v) else None
    h = None
    if bts is not None:
        byh = collections.defaultdict(float)
        for x, t in zip(v, bts): byh[datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%d %H")] += x
        h = (sum(1 for x in byh.values() if x > 0), len(byh))
    return dict(n=len(v), fills=len(fills), tot=sum(v), win=(sum(1 for x in fills if x > 0) / len(fills)) if fills else 0,
                per_h=sum(v) / hours if hours else 0, wo5=sum(s[:-5]) if len(s) > 5 else sum(s), ci=(ci[50], ci[950]) if ci else None, hours_pos=h,
                h1=sum(x for x, t in zip(v, bts) if t < mid) if (bts and mid) else None, h2=sum(x for x, t in zip(v, bts) if t >= mid) if (bts and mid) else None)
fw_s = {}
for Lm in ("45", "60", "75"):
    R = [r for r in FW if Lm in r["land"]]
    fw_s[Lm] = summ([r["land"][Lm]["pnl"] for r in R], fw_h, [r["bt"] for r in R], fw_mid)
# old data (R1, block-position landing proxy), hold 1 s exit, 1% guard, same fail cost
R1.sort(key=lambda r: r["bt"]); r1_h = (R1[-1]["bt"] - R1[0]["bt"]) / 3600; r1_mid = R1[0]["bt"] + (R1[-1]["bt"] - R1[0]["bt"]) / 2
r1_s = {}
for Lm in ("35", "45", "60", "75"):
    R = [r for r in R1 if Lm in r["res"]]
    vals = [(r["res"][Lm][1]["eos1"] if r["res"][Lm][0] <= 1.01 else -FAIL) for r in R]
    r1_s[Lm] = summ(vals, r1_h, [r["bt"] for r in R], r1_mid)
# timing margin of the 75 ms fills (margin.txt from margin_s4.py)
import re as _re
_ml = next(l for l in open(os.path.join(HERE, "margin.txt")) if l.startswith("L75"))
_cnt = {k: int(n) for k, n in _re.findall(r"(\+10-25|<\+10 ms|\+25-50|\+50-100|\+100 ms\+|no later trade): n (\d+)", _ml)}
MG = (_cnt.get("+10-25", 0) + _cnt.get("<+10 ms", 0), sum(_cnt.values()))
# stress tests
st_rows = []
for var, lab in (("base", "As modeled (block-order placement)"), ("sell800", "Our sell lands at 800 ms instead of 500 ms"),
                 ("drop9", "The 3 case-study wallets fail after our buy (their buys removed)"), ("drop30", "…and 30% of all other buyers in the next second are removed too"),
                 ("shift1", "Worst case: one more buyer always lands ahead of us (guard re-checked)")):
    row = [lab]
    for Lm in (45, 60, 75):
        k = f"{var}_{Lm}"; v = [r["res"][k] for r in ST if r["res"].get(k) is not None]
        nfail = sum(1 for x in v if abs(x + 0.002) < 1e-12)      # stress run charged 0.002 per failed buy: re-charge at FAIL
        row.append((sum(v) - (FAIL - 0.002) * nfail, len(v) - nfail))
    st_rows.append(row)
# dry run (frozen strategies, forward data after the freeze)
T_S4 = datetime.datetime(2026, 10, 23, 1, 10, tzinfo=datetime.timezone.utc).timestamp()
T_DR0 = datetime.datetime(2026, 10, 23, 0, 35, tzinfo=datetime.timezone.utc).timestamp()
DR.sort(key=lambda r: r["bt"])
dr_last = max((r["bt"] for r in DR), default=T_DR0)
def dr_val(r, Lm, ex="eos1", G=0.01):
    x = r["land"].get(str(Lm))
    if not x: return None
    if x.get("guard_ratio") is None or x["guard_ratio"] > 1 + G: return -FAIL
    return x["sell500"] if ex == "sell500" else x["pnl"][ex]
dr_s = {}
for lab, t0 in (("clean", T_S4), ("all", T_DR0)):
    for Lm in (45, 60, 75):
        R = [r for r in DR if r["bt"] >= t0 and r.get("s3any") and str(Lm) in r["land"]]
        hrs = max(1e-9, (dr_last - t0) / 3600)
        dr_s[(lab, Lm)] = summ([dr_val(r, Lm) for r in R], hrs, [r["bt"] for r in R], None, boot=len(R) > 5)
# ---------------------------------------------------------------- page
CSS = open(os.path.join(HERE, "style.css")).read()
P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Dev-List Guarded Snipe</title><style>{CSS}</style></head><body><div class='wrap'>"]
a75 = fw_s["75"]; a45 = fw_s["45"]; a60 = fw_s["60"]; r75 = r1_s["75"]; r45 = r1_s["45"]
NG = json.load(open(os.path.join(HERE, "noguard.json"))); NUL = json.load(open(os.path.join(HERE, "null.json")))
SZ = json.load(open(os.path.join(HERE, "sizes.json"))); EXR = json.load(open(os.path.join(HERE, "s4_exits.json"))); LM = json.load(open(os.path.join(HERE, "lists_many.json")))
h1s75 = sum(r["land"]["75"]["pnl_hold1s"] if r["land"]["75"].get("filled") else -FAIL for r in FW if "75" in r["land"])
P.append(f"""<h1>A strategy that holds up at our landing speed</h1>
<p class="mut">Overnight study, 2026-10-23. Built only from on-chain data and our own engine's live timelines. Nothing was traded. Every token, wallet and transaction below links to GMGN or Solscan.</p>
<div class="chips"><span class="chip">Replay window 10-22 17:09 → 10-23 00:34 UTC ({fw_h:.1f} h, real place in line)</span><span class="chip">Old data 10-21 22:07 → 10-22 07:00 UTC ({r1_h:.1f} h)</span><span class="chip">Dry run since 00:35 UTC (frozen rules)</span><span class="chip">Independently re-computed</span></div>
<div class="card tldr"><b>In short</b><ul>
<li><b>Selection:</b> only launches whose <b>create transaction is signed by a deployer that 9Sh2fd / DGmspi keep sniping</b>: 2+ of their attempts, on 10%+ of that deployer's launches, counted only from data before each launch.</li>
<li><b>Buy:</b> 0.5 SOL with a <b>price guard</b>. The buy carries a minimum-tokens-out, so it <b>fails</b> if anyone bought ahead of us after the dev's bundle (price more than 1% above the post-bundle price). A failed buy costs only its fee, counted here as {FAIL} SOL.</li>
<li><b>Sell:</b> everything at the end of the slot after our buy, about 0.2–0.4 s later, in one sell. Selling in pieces, holding longer, trailing stops and take-profit ladders all did worse.</li>
<li><b>Result at our measured 75 ms landing:</b>
  <ul class="tight">
  <li>{pnl(a75['tot'], 2)} SOL over {a75['n']} attempts and {a75['fills']} fills in {fw_h:.1f} h, which is {a75['per_h']:+.2f} SOL/h at 0.5 SOL;</li>
  <li>{a75['hours_pos'][0]} of {a75['hours_pos'][1]} hours positive; 90% range {a75['ci'][0]:+.2f} to {a75['ci'][1]:+.2f};</li>
  <li>{pnl(a75['wo5'], 2)} without the 5 best trades.</li>
  </ul>
  At 45 ms: {pnl(a45['tot'], 2)} SOL. Old data, with a pessimistic landing model: {pnl(r75['tot'], 2)} at 75 ms and {pnl(r45['tot'], 2)} at 45 ms.</li>
<li><b>The guard is what makes it work at 75 ms.</b> Without it, the same picks and exit give {pnl(NG['eos1_75'], 2)} at 75 ms (1 s hold: {pnl(NG['hold1s_75'], 2)}). With it, we only fill when we are first after the bundle.</li>
<li><b>Checked twice.</b> An independent verifier rebuilt every trade from raw chain data with its own code and found two problems, both fixed below. Its corrected numbers and ours agree within 0.02 SOL.</li>
<li><b>Not proven live yet.</b> The next step is a small FRZ test (your OK needed); see the last section.</li></ul></div>""")
P.append(f"""<div class="grid">
<div class="stat"><b>{pnl(a75['tot'], 2)}</b><span>SOL, replay at 75 ms, {fw_h:.1f} h, 0.5 SOL size</span></div>
<div class="stat"><b>{a75['fills']}/{a75['n']}</b><span>buys filled / attempted (the rest failed on the guard)</span></div>
<div class="stat"><b>{a75['win']:.0%}</b><span>of fills won after all fees</span></div>
<div class="stat"><b>{a75['hours_pos'][0]}/{a75['hours_pos'][1]}</b><span>hours positive</span></div>
<div class="stat"><b>{pnl(a75['wo5'], 2)}</b><span>SOL without the 5 best trades</span></div>
<div class="stat"><b>{pnl(r75['tot'], 2)}</b><span>SOL on old data at 75 ms ({r75['fills']} fills, pessimistic)</span></div></div>""")
# ---- the rules
P.append(f"""<h2>The strategy (S4), rule by rule</h2><ol class="steps">
<li><b>Know the deployers.</b> Watch the profitable dev-list snipers {ln(GW('9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1'), '9Sh2fd')} and {ln(GW('DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3'), 'DGmspi')}. Every buy they try (filled or failed) tells us which deployer they follow. A deployer goes on our list after 2+ of their attempts if they try at least 10% of that deployer's launches. The deployer is the wallet that <b>signs</b> the create: 39% of launches put a different, fresh wallet in the "creator" field. The list today has 92 deployers; most of the profit came from deployers they had followed for 2+ days.</li>
<li><b>Wait for the dev's bundle</b> (median 1.6 ms after the create in our feed), then send the buy. Size 0.5 SOL.</li>
<li><b>Price guard.</b> Minimum tokens out = the tokens 0.5 SOL buys right after the bundle, minus 1%. If another buyer lands first, the buy fails instead of filling late. At 75 ms we fill {a75['fills']} of {a75['n']} ({a75['fills'] / a75['n']:.0%}).</li>
<li><b>Sell everything at the end of the slot after our buy</b> (one sell, about 0.2–0.4 s later; engine <code>--hold-slots 1</code>). This sells into the snipers and copy-bots that arrive right after us. A 1 s hold gives {pnl(h1s75, 2)} at 75 ms instead.</li></ol>
<p class="small mut">Costs in every number: pump.fun fee on both sides (from the trade events), 2% buy overhead (priority + tip), 0.0005 SOL per sell, a 1.5% worse fill than the model (see validation), and {FAIL} SOL per failed (guarded) buy.</p>""")
# ---- results tables
def row_s(lab, s, extra=""):
    ci = f"{s['ci'][0]:+.2f} … {s['ci'][1]:+.2f}" if s.get("ci") else "—"
    hp = f"{s['hours_pos'][0]}/{s['hours_pos'][1]}" if s.get("hours_pos") else "—"
    halves = f"{s['h1']:+.2f} / {s['h2']:+.2f}" if s.get("h1") is not None else "—"
    return f"<tr><td class='l'>{lab}</td><td>{s['n']}</td><td>{s['fills']}</td><td>{pnl(s['tot'], 2)}</td><td>{s['per_h']:+.2f}</td><td>{s['win']:.0%}</td><td>{pnl(s['wo5'], 2)}</td><td>{ci}</td><td>{halves}</td><td>{hp}</td></tr>"
HDR = "<tr><th class='l'>Landing (ms after the create)</th><th>Attempts</th><th>Fills</th><th>Total SOL</th><th>SOL/h</th><th>Fill win</th><th>w/o top 5</th><th>90% range</th><th>Halves</th><th>Hours +</th></tr>"
P.append(f"""<h2>Replay with our real place in line <span class="badge m">measured</span></h2>
<p>Every launch our shadow engine watched from 10-22 17:09 to 10-23 00:34 UTC. Our buy goes where our engine's own arrival clock puts it: every outside transaction it saw before our landing time is ahead of us. Then everyone's real trades are replayed on the bonding curve with our buy and sell inserted.</p>
<div class="tbl"><table>{HDR}{''.join(row_s(f'{Lm} ms', fw_s[Lm]) for Lm in ('45', '60', '75'))}</table></div>
<p class="small mut">Our live buys landed 73–75 ms after the create (Run 2). The landing study says 35–50 ms is reachable with nonce fan-out (section below).</p>""")
LC = json.load(open(os.path.join(HERE, "landing_curve.json")))
P.append(f"""<h3>If our landing is faster or slower</h3><div class="tbl"><table><tr><th class='l'>Landing (ms after the create)</th>{''.join(f'<th>{k}</th>' for k in LC)}</tr>
<tr><td class='l'>Total SOL, same 269 attempts</td>{''.join(f'<td>{pnl(v["tot"], 2)}</td>' for v in LC.values())}</tr>
<tr><td class='l'>Fills</td>{''.join(f'<td>{v["fills"]}</td>' for v in LC.values())}</tr></table></div>
<p class="small"><b>Risk in the same window (75 ms, 0.5 SOL):</b> the worst single trade was −0.030 SOL (fees on a flat price); no fill lost more than 10%; the deepest drawdown was −0.20 SOL; the longest losing run was 20 attempts, mostly guard fails at −0.005 each. Selling at the end of the next slot leaves little time for the price to fall.</p>
<p class="small">S4 stays positive up to about 130 ms and breaks even around 150 ms. Past that, the only launches we are still first on are the ones nobody wants. Every 15 ms faster adds roughly +0.7 to +1.5 SOL per 7.4 h at 0.5 SOL; 30 ms would make about 2.5× today's number.</p>""")
P.append(f"""<h2>Same rules on older data <span class="badge m">measured</span> <span class="badge i">landing estimated</span></h2>
<p>10-21 22:07 → 10-22 07:00 UTC, before our engine logged arrival times. Our place in line is estimated from each transaction's position in its block. On the replay window this estimate matched the real place at 35 ms and was <b>pessimistic</b> at 60–75 ms.</p>
<div class="tbl"><table>{HDR}{''.join(row_s(f'{Lm} ms', r1_s[Lm]) for Lm in ('35', '45', '60', '75'))}</table></div>""")
st_html = "".join(f"<tr><td class='l'>{e(r[0])}</td>" + "".join(f"<td>{pnl(t, 2)} <span class='mut small'>({n} fills)</span></td>" for t, n in r[1:]) + "</tr>" for r in st_rows)
P.append(f"""<h2>Stress tests <span class="badge m">measured</span></h2>
<p>Where could the replay be too kind? Same window, 0.5 SOL, total SOL. (Exit in this table: the sell lands 500 ms after the create, placed by our arrival clock like the buy. The main table sells at the end of the next slot.)</p>
<div class="tbl"><table><tr><th class='l'>Test</th><th>45 ms</th><th>60 ms</th><th>75 ms</th></tr>{st_html}</table></div>
<p class="small">The last line is the one that hurts. If one more buyer always got in ahead of us, the guard would fail on most launches, which is why <b>landing time matters</b>. But on {MG[1] - MG[0]} of the {MG[1]} fills at 75 ms, the next outside buyer reaches our feed 25 ms or more after us, or never shows up. A few ms of jitter does not flip those.</p>""")
# ---- dry run
def dr_rows(lab):
    out = ""
    for Lm in (45, 60, 75):
        s = dr_s[(lab, Lm)]
        out += row_s(f"{Lm} ms", s)
    return out
P.append(f"""<h2>Dry run: frozen rules on new data <span class="badge m">measured</span></h2>
<p>The rules were written down and hashed <b>before</b> this data existed (file <code>ops/overnight/dryrun/frozen.json</code>, sha256 <code>{FZH[:16]}…</code>). Every 15 minutes the host copies the server's new launches and our engine's timelines, places our simulated buy and sell exactly as above, and logs the result. Data through {utc(dr_last)} UTC.</p>
<h3>Clean test: launches after 01:10 UTC (the moment the guard rule was frozen)</h3>
<div class="tbl"><table>{HDR}{dr_rows('clean')}</table></div>
<h3>All launches after 00:35 UTC (the guard rule was chosen at 01:10 without looking at these trades)</h3>
<div class="tbl"><table>{HDR}{dr_rows('all')}</table></div>""")


# ---- cumulative PnL chart (inline SVG): replay window and dry run, S4 at 75 ms
def svg_cum(series, title, w=760, h=180):
    pts = []; cum = 0.0
    for t, x in series: cum += x; pts.append((t, cum))
    if len(pts) < 2: return ""
    t0, t1 = pts[0][0], pts[-1][0]; lo = min(0, min(c for _, c in pts)); hi = max(0.01, max(c for _, c in pts))
    X = lambda t: 40 + (w - 60) * (t - t0) / max(1, t1 - t0); Y = lambda c: 10 + (h - 40) * (hi - c) / (hi - lo)
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(t):.1f},{Y(c):.1f}" for i, (t, c) in enumerate(pts))
    ticks = "".join(f"<text x='{X(t0 + k * (t1 - t0) / 4):.0f}' y='{h - 8}' font-size='11' fill='currentColor' opacity='.6' text-anchor='middle'>{datetime.datetime.fromtimestamp(t0 + k * (t1 - t0) / 4, datetime.timezone.utc):%H:%M}</text>" for k in range(5))
    return (f"<div class='card'><b>{e(title)}</b><svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='{e(title)}'>"
            f"<line x1='40' x2='{w - 20}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' stroke='currentColor' opacity='.25'/>"
            f"<path d='{path}' fill='none' stroke='var(--acc)' stroke-width='2'/>"
            f"<text x='4' y='{Y(hi) + 4:.0f}' font-size='11' fill='currentColor' opacity='.6'>{hi:+.1f}</text><text x='4' y='{Y(lo) + 4:.0f}' font-size='11' fill='currentColor' opacity='.6'>{lo:+.1f}</text>{ticks}</svg>"
            f"<p class='small mut'>Cumulative SOL at 0.5 SOL per trade, every attempt included (failed guard = −0.005). End: {pnl(cum, 2)} SOL.</p></div>")
fw_series = [(r["bt"], r["land"]["75"]["pnl"]) for r in FW if "75" in r["land"]]
P.append(svg_cum(fw_series, "S4 at 75 ms — replay window (10-22 17:09 → 10-23 00:34 UTC)"))
dr_series = sorted((r["bt"], dr_val(r, 75)) for r in DR if r.get("s3any") and r["land"].get("75") and r["bt"] >= T_S4)
P.append(svg_cum(dr_series, "S4 at 75 ms — dry run on new data (frozen rules, since 01:10 UTC)"))
# ---- worked example: how to check one trade by hand
best = max((r for r in FW if r["land"].get("75", {}).get("filled")), key=lambda r: r["land"]["75"]["pnl"])
bx = best["land"]["75"]
P.append(f"""<h2>How to check one trade by hand</h2>
<div class="card"><p>Example: the best fill at 75 ms, {ln(GT(best['mint']), mask(best['name'] or best['symbol'] or best['mint']))}, created {utc(best['bt'])} UTC.</p><ol class="steps">
<li><b>Dev and bundle:</b> open the {ln(TX(best['create_sig']), 'create transaction')}. The signer {ln(GW(best['deployer']), sh(best['deployer'], 6, 4))} is on our deployer list (attempted {best['att_before']} times by the case-study wallets before this launch, out of {best['launches_before']} launches we saw). The dev bought {best['dev_buy']} SOL; {len(best['bundle'])} bundle transactions ({best['bundle_sol']} SOL) follow it. Market cap after the bundle: {best['mc_bundle_sol']} SOL.</li>
<li><b>Our buy:</b> landing 75 ms after the create, it goes right behind {ln(TX(bx['after_sig']), 'this transaction')}, with {bx['ahead']} outside buyers ahead. The price there is {bx['ratio']:.3f}× the post-bundle price, so the 1% guard passes and we fill at a market cap of {bx['mc_fill_sol']} SOL.</li>
<li><b>After us:</b> {bx['buys_after']} buys and {bx['sells_after']} sells land before our sell; check them on GMGN's trade list for this token.</li>
<li><b>Our sell:</b> it lands right before {ln(TX(bx['sell_before_sig']), 'this transaction') if bx.get('sell_before_sig') else 'the next trade'}, at a market cap of about {bx['mc_sell_sol']} SOL. Result after every fee: {pnl(bx['pnl'])} SOL on 0.5 SOL.</li></ol>
<p class="small mut">Every row in the trade tables below has the same links: create, the transaction we land behind, and the transaction our sell lands in front of.</p></div>""")

# ---- DGmspi's ladders (owner: "check his ladders")
DGL = json.load(open(os.path.join(HERE, "dg_ladders.json"))); DGR = json.load(open(os.path.join(HERE, "dg_recent_ladders.json")))
ex_rows2 = "".join(f"<tr><td class='l'>{e(k)}</td><td>{pnl(v['45']['tot'], 2)}</td><td>{pnl(v['75']['tot'], 2)}</td><td>{v['75']['sells']:.1f}</td></tr>" for k, v in DGL.items())
def lad_line(m, x):
    b = x["buy"]; n = len(x["sells"]); dur = (x["sells"][-1]["bt"] - b["bt"]) if n else 0
    return f"<tr><td class='l'>{ln(GT(m), sh(m, 6, 4))}</td><td class='l'>{b['quote']}</td><td>{x['cost']:.2f}</td><td>{n}</td><td>{dur}s</td><td>{pnl(x['got'] - x['cost'], 3)}</td><td>{(x['got'] - x['cost']) / x['cost']:+.1%}</td></tr>"
recent = sorted(DGR.items(), key=lambda kv: -len(kv[1]["sells"]))[:8]
P.append(f"""<h2>DGmspi's ladders, checked on chain (your screenshot) <span class="badge m">measured</span></h2>
<p>DGmspi's last 3 hours, decoded transaction by transaction (WORLD = {ln(GT('GcTNbHJUW5uZYRtzPnEp2KRcpVbxbqKtw3Mzf6Zxpump'), 'GcTNbH…pump')}):</p>
<div class="tbl"><table><tr><th class='l'>Token</th><th class='l'>Quote</th><th>Buy SOL</th><th>Sells</th><th>Over</th><th>PnL SOL</th><th>PnL %</th></tr>{''.join(lad_line(m, x) for m, x in recent)}</table></div>
<ul class="tight">
<li><b>WORLD</b> (82 sells, +47%) is a PUMP-quoted token: 3 WSOL is swapped to PUMP inside the buy.
  <ul class="tight">
  <li>Sold 25% after 1 slot at ×1.15, then 8–10% chunks up to slot 13.</li>
  <li>Then <b>5% of whatever was left every ~5 s for 6 minutes</b>. The price kept climbing (×1.3 → ×2.75), and the slow sell-down captured it.</li>
  </ul></li>
<li><b>Most SOL-quoted tokens:</b> a big "lightning" sell of 50–75% within 0–2 slots at about ×1.0–1.1, then a few pieces over 5–60 s. Results +4% to +11%.</li>
<li><b>The loser:</b> AEgZa5k3, a 6.75 SOL buy, sold 10% of what was left every ~10 s while the price fell, then dumped the rest at ×0.60: −1.26 SOL.</li>
</ul>
<p><b>Their ladder shapes on OUR S4 entries</b> (same {fw_h:.1f} h, total SOL):</p>
<div class="tbl"><table><tr><th class='l'>Exit</th><th>45 ms</th><th>75 ms</th><th>Sells per trade</th></tr>{ex_rows2}</table></div>
<p class="small"><b>Verdict:</b> their ladders win for them because they enter at about 40 ms with 1.8–3 SOL and catch the runners from the start. On our entries, every version that keeps a remainder does worse than one quick sell. The exact WORLD ladder loses money at 75 ms.</p>""")
# ---- per-trade evidence (dry run + replay)
def trade_rows(R, get_land, cols):
    out = []
    for r in R:
        x = get_land(r)
        if not x: continue
        tok = mask(f"{r.get('name') or ''} ({r.get('symbol') or ''})")
        out.append(f"<tr><td class='l'>{utc(r['bt'])}</td><td class='l'>{ln(GT(r['mint']), tok[:28])}</td><td class='l'>{ln(GW(r['deployer']), sh(r['deployer']))}</td>"
                   f"<td class='l'>{ln(TX(r['create_sig']), 'create')}</td>" + cols(r, x) + "</tr>")
    return "".join(out)
def fw_cols(r, x):
    l45 = r["land"].get("45", {})
    return (f"<td class='l'>{ln(TX(x['after_sig']), 'lands after')} <span class='mut small'>({x['ahead']} ahead)</span></td><td>{x['ratio']:.3f}</td>"
            f"<td>{x.get('mc_fill_sol', 0):.1f}</td><td>{x.get('mc_sell_sol', 0):.1f}</td>"
            f"<td class='l'>{ln(TX(x['sell_before_sig']), 'sell lands before') if x.get('sell_before_sig') else '—'}</td><td>{pnl(x['pnl'])}</td><td>{pnl(l45.get('pnl'))}</td>")
fills75 = [r for r in FW if r["land"].get("75", {}).get("filled")]
P.append(f"""<h2>Every replay fill at 75 ms ({len(fills75)} trades) <span class="badge m">measured</span></h2>
<p class="small mut">"lands after" = the transaction our buy would land right behind. Price ratio = price there ÷ price right after the dev's bundle (≤1.01 passes the guard). MC = market cap in SOL. "sell lands before" = the transaction our sell lands in front of, at the end of the slot after our buy. PnL in SOL at 0.5 SOL, after every fee; the last column is the same launch at 45 ms.</p>
<details><summary>Show all {len(fills75)} trades</summary><div class="tbl"><table><tr><th class='l'>Create (UTC)</th><th class='l'>Token</th><th class='l'>Deployer</th><th class='l'>Create tx</th><th class='l'>Our buy</th><th>Price ratio</th><th>MC fill</th><th>MC sell</th><th class='l'>Our sell</th><th>PnL 75 ms</th><th>PnL 45 ms</th></tr>
{trade_rows(fills75, lambda r: r['land'].get('75'), fw_cols)}</table></div></details>""")
def dr_cols(r, x):
    v = dr_val(r, 75); v45 = dr_val(r, 45)
    return (f"<td class='l'>{ln(TX(x['after_sig']), 'lands after')} <span class='mut small'>({x['ahead']} ahead)</span></td><td>{x['guard_ratio']:.3f}</td>"
            f"<td>{'fill' if v is not None and v != -FAIL else 'guard fail'}</td><td>{pnl(v)}</td><td>{pnl(v45)}</td>")
drs = [r for r in DR if r.get("s3any") and r["land"].get("75")]
P.append(f"""<h2>Every dry-run attempt ({len(drs)}) <span class="badge m">measured</span></h2>
<details><summary>Show the dry-run trades</summary><div class="tbl"><table><tr><th class='l'>Create (UTC)</th><th class='l'>Token</th><th class='l'>Deployer</th><th class='l'>Create tx</th><th class='l'>Our buy at 75 ms</th><th>Price ratio</th><th>Result</th><th>PnL 75 ms</th><th>PnL 45 ms</th></tr>
{trade_rows(drs, lambda r: r['land'].get('75'), dr_cols)}</table></div></details>""")



# ---- lessons from the successful wallets the owner shared (cross-wallet screen + follow tests + sizing tests)
P.append("""<h2>Lessons from the successful wallets <span class="badge m">measured</span></h2>
<p>Two families, from our collected data (10-21 22:07 → 10-23 00:35) and replays at our place in line:</p>
<ol class="steps">
<li><b>First-in-line flippers</b> (dKMjeGJ4 +45 SOL, AHwJSnFN +11, CWiNFAEk +5):
  <ul class="tight">
  <li>They earn almost only when they are the first buyer: dKMjeGJ4 +36 of its +45 SOL; CWiNFAEk +7.0 when first, −1.1 when not.</li>
  <li>AHwJSnFN and CWiNFAEk fail rather than fill late, which is our price guard.</li>
  <li>dKMjeGJ4's money is in its fastest landings: +25 SOL on 53 buys within 25 ms of the create.</li>
  <li>They size up on bigger dev buys and bundles, and sell within seconds.</li>
  </ul>
  <b>Adopted:</b> the guard (S4), sizing up on big launches (S4GM / S4G_1SOL), selling in one quick piece, and the landing upgrade as the main lever.</li>
<li><b>Pickers who hold longer</b> (2maW7x2X, 4Yy3xBZn, retAumPG, HnFPB3iA, 6Kj5ChEZ, FeCAXCyH…):
  <ul class="tight">
  <li>They are profitable even with 1–3 buyers ahead, holding 5 s to 4 min. They choose 1+ s after the create, after watching the first second of trading.</li>
  <li>Their picks bought at our 75 ms would make +12 to +38 SOL, but that is look-ahead: we cannot know their pick that early.</li>
  <li><b>Following them</b> (buy right after their buy, hold 10 s to 2 min, or sell when they sell) <b>loses in both periods for almost all of them</b>.</li>
  </ul>
  Not adopted.</li>
<li><b>The deployer's identity is the edge, not the launch's looks.</b>
  <ul class="tight">
  <li>Launches that look like our list's (j7tracker/uxento tool, 2–3-tx bundle, 3–5 SOL dev buy) but come from deployers we don't copy lose with the guard: −3.8 replay, −7.6 old.</li>
  <li>Scoring deployers by how much buying their past launches drew does not find new good ones at 75 ms.</li>
  <li>Good deployers have a following of bots and buyers who jump in after their launches. The profitable snipers' attempts are the best way we have found to identify them.</li>
  </ul></li>
<li><b>Exact-first beats nearly-first.</b> Fills where even a tiny buy got in before us lose on average. A 0.5% guard instead of 1% is slightly better in both periods (75 ms: +4.07 vs +4.01 replay, +1.18 vs +0.88 old). The proposed flags use 0.5%.</li>
</ol>""")
# ---- improvements found after the first freeze (walk-forward, both periods) + size stress + non-SOL curves
EXP = json.load(open(os.path.join(HERE, "exp.json"))); QS = json.load(open(os.path.join(HERE, "q_s4.json")))
def ecell(x): return f"<td>{pnl(x['tot'], 2)} <span class='mut small'>({x['fills']}/{x['n']})</span></td>" if x else "<td>—</td>"
order = ["S4 (9Sh2fd+DGmspi list) 0.5", "S4 + gate (drop deployers whose own fills avg < 0)", "S4 + size 1.0 when own history >= 3 fills avg >= +0.02", "S4 + gate + size",
         "MULTI list (7 wallets) 0.5", "MULTI list + gate", "MULTI list + gate + size", "AUTO: any deployer with >= 3 own fills avg >= +0.02 (no copying)"]
nice = {"S4 (9Sh2fd+DGmspi list) 0.5": "S4 as above (0.5 SOL)", "S4 + gate (drop deployers whose own fills avg < 0)": "S4 + quality gate: skip a deployer whose own past fills average below 0",
        "S4 + size 1.0 when own history >= 3 fills avg >= +0.02": "S4 + 1 SOL on deployers with 3+ good fills", "S4 + gate + size": "<b>S4 + gate + size (S4GS)</b>",
        "MULTI list (7 wallets) 0.5": "deployer lists of 7 snipers, no gate", "MULTI list + gate": "7-sniper lists + gate", "MULTI list + gate + size": "7-sniper lists + gate + size",
        "AUTO: any deployer with >= 3 own fills avg >= +0.02 (no copying)": "AUTO: deployers chosen only by our own past results (no copying)"}
rows = "".join(f"<tr><td class='l'>{nice[k]}</td>{ecell(EXP[k]['75']['R2'])}{ecell(EXP[k]['75']['R1'])}{ecell(EXP[k]['45']['R2'])}{ecell(EXP[k]['45']['R1'])}</tr>" for k in order if k in EXP)
EXP2 = json.load(open(os.path.join(HERE, "exp2.json")))
nice2 = {"S4G_1SOL": "<b>S4G with every buy at 1 SOL (S4G_1SOL, no engine change)</b>", "S4GM": "S4G, 1 SOL when market cap after the bundle ≥ 36 SOL (dKMjeGJ4-style)",
         "S4GSM": "S4G, 1 SOL when good history or MC ≥ 36", "S4G_BIG_ONLY": "S4G only on MC ≥ 36 launches, 1 SOL"}
rows += "".join(f"<tr><td class='l'>{nice2[k]}</td>{ecell(EXP2[k]['75']['R2'])}{ecell(EXP2[k]['75']['R1'])}{ecell(EXP2[k]['45']['R2'])}{ecell(EXP2[k]['45']['R1'])}</tr>" for k in nice2 if k in EXP2)
qv = lambda run, Lm: sum(r["res"][str(Lm)] for r in QS if r["run"] == run and str(Lm) in r["res"])
P.append(f"""<h2>Improvements found later in the night <span class="badge m">measured</span></h2>
<p>Every rule here is walk-forward: each decision uses only what was known before that launch, including our own simulated results on that deployer, counted 60 s after each launch. Total SOL, with fills/attempts:</p>
<div class="tbl"><table><tr><th class='l'>Strategy</th><th>75 ms replay</th><th>75 ms old data</th><th>45 ms replay</th><th>45 ms old data</th></tr>{rows}</table></div>
<ul class="tight">
<li><b>The quality gate and sizing up on proven deployers improve both periods.</b> S4GS at 75 ms: replay {pnl(EXP['S4 + gate + size']['75']['R2']['tot'], 2)} vs {pnl(EXP['S4 (9Sh2fd+DGmspi list) 0.5']['75']['R2']['tot'], 2)}; old data {pnl(EXP['S4 + gate + size']['75']['R1']['tot'], 2)} vs {pnl(EXP['S4 (9Sh2fd+DGmspi list) 0.5']['75']['R1']['tot'], 2)}. The gated list is built every 15 min (<code>deployer_list_gated.txt</code>, 85 deployers). Sizing needs a small engine change.</li>
<li><b>At 1 SOL under stress</b> (S4 picks, 75 ms): +8.62 SOL as modeled; +5.99 if the case-study wallets fail after us; +2.00 if 30% of other early buyers also vanish. At 0.5 SOL the same tests give +4.01 / +2.67 / +0.62.</li>
<li><b>Copying more snipers' lists only works with the gate.</b> Without it, the 7-sniper list loses (−9.5 SOL on old data).</li>
<li><b>Non-SOL-quoted curves</b> (PUMP / USDC / other quotes; about a third of the listed deployers' launches) are <b>not</b> worth adding to the engine. Same rules there: {qv('R2', 75):+.2f} (replay) / {qv('R1', 75):+.2f} (old data) SOL at 75 ms.</li>
<li>These variants were frozen at 02:24 UTC (<code>dryrun/frozen2.json</code>) for a clean forward test. Results are in the dry-run section once the data is synced.</li>
</ul>""")
# ---- dynamic evidence sections (all from the corrected runs)
def tot_cell(x): return f"<td>{pnl(x, 2)}</td>"
nul_rows = "".join(f"<tr><td class='l'>Every launch whose deployer had {b['lo']}–{b['hi'] if b['hi'] < 10 ** 8 else '∞'} earlier launches</td><td>{b['n']}</td>{tot_cell(b['tot'])}</tr>" for b in NUL["by_prior"])
P.append(f"""<h2>Is the deployer list doing real work? <span class="badge m">measured</span></h2>
<p>The same guarded quick flip was run on other selections in the same window, at 75 ms and 0.5 SOL (1 s hold):</p>
<div class="tbl"><table><tr><th class='l'>Selection</th><th>Launches</th><th>Total SOL</th></tr>{nul_rows}
<tr><td class='l'>20 random lists of 92 serial deployers (same size as ours)</td><td>—</td><td class='l'>{min(NUL['random']):+.2f} … {max(NUL['random']):+.2f} (all negative)</td></tr>
<tr><td class='l'><b>Our list (S4, copied from 9Sh2fd / DGmspi)</b></td><td>{a75['n']}</td>{tot_cell(h1s75)}</tr></table></div>
<p>The guard alone does not make money. The list copied from the case-study wallets is what makes the difference: it beat all 20 random lists of the same size.</p>
<p><b>The list lasts.</b> A list frozen 10, 19 or 29 hours before the replay window, with no updates at all, still made +3.55 / +3.46 / +3.27 SOL at 75 ms in that window, versus +4.01 with live updates. A daily refresh is enough, and S4 does not collapse if the case-study wallets stop for a day.</p>""")
def szr(Lm):
    g = lambda B: SZ.get(f"0.01_{Lm}_{B}", {}).get("tot")
    return f"<tr><td class='l'>{Lm} ms</td>" + "".join(f"<td>{pnl(g(B), 2)}</td>" for B in (0.5, 1.0, 2.0)) + (f"<td>{pnl(SZ.get('0.01_75_1.0_fee1', {}).get('tot'), 2)}</td>" if Lm == 75 else "<td>—</td>") + "</tr>"
P.append(f"""<h2>Size and fees <span class="badge m">measured</span></h2>
<p>S4, replay window ({fw_h:.1f} h). Here the sell lands 500 ms after the create, and a failed buy costs 0.002 SOL. Total SOL by buy size:</p>
<div class="tbl"><table><tr><th class='l'>Landing</th><th>0.5 SOL</th><th>1 SOL</th><th>2 SOL</th><th>1 SOL at 1% buy overhead (nonce fan-out)</th></tr>{szr(45)}{szr(60)}{szr(75)}</table></div>
<p class="small">Bigger size scales almost linearly in the replay. But bigger buys also push the price more for the snipers behind us, and more of them may fail; see the stress test with 30% fewer buyers. <b>Start small and scale only after live fills match the replay.</b> Failed guarded buys pay their priority fee. At today's PROD priority fee of about 0.011 SOL per transaction, about {a75['n'] - a75['fills']} failed buys per 7.4 h cost about {(a75['n'] - a75['fills']) * (0.011 - FAIL):.1f} SOL more than assumed. A lower priority fee with a tip keeps more, because tips revert on a failed transaction.</p>""")
NICE = {"hold0.3s": "sell all ~0.3 s after the buy", "eos1": "sell all at the end of the next slot (S4)", "tp1.1_eos2": "take profit at +10%, else sell after 2 slots",
        "eos2": "sell all after 2 slots", "hold1s": "sell all ~1 s after the buy", "pD_25at_slots1_3_6_10": "25% at 1 / 3 / 6 / 10 slots",
        "pB_50fsell_50trail1.3_.2_c60": "half at the first sell, half on a 20% trailing stop", "twap_10pct_every2s_20s": "10% every 2 s for 20 s",
        "pK_20pct_each_new_high_10pct": "20% at each new +10% high", "pC_33@1.2_33@1.5_34@2_sl.85_c30": "33% at +20%, 33% at +50%, 34% at 2×",
        "pH_77@1.3_rest_trail.3_c300": "77% at +30%, then trail the rest", "pI_50eos0_50hold10s": "half at once, half after 10 s",
        "pJ_50eos1_25@1.5_25trail.25_c60": "half fast, 25% at +50%, trail the rest", "lad_33@1.3_33@1.6_trail": "33% at +30%, 33% at +60%, trail the rest",
        "hold10s": "hold 10 s", "hold30s": "hold 30 s", "trail1.5_0.25": "trailing stop after +50%"}
exr = {x["rule"]: {c["L"]: c["tot"] for c in x["cells"]} for x in EXR}
ex_rows = "".join(f"<tr><td class='l'>{e(NICE[k])}</td>{tot_cell(exr[k][45])}{tot_cell(exr[k][75])}</tr>" for k in NICE if k in exr)
TD = json.load(open(os.path.join(HERE, "test_design.json")))
FEEC = [(0.002, 0.0005), (0.006, 0.001), (0.011, 0.002), (0.024, 0.011)]
td_rows = "".join(f"<tr><td class='l'>{B} SOL</td>" + "".join(f"<td>{pnl(TD.get(f'{B}_{F}'), 2)}</td>" for F, FF in FEEC) + "</tr>" for B in (0.1, 0.25, 0.5, 1.0))
P.append(f"""<h2>Fees decide whether a small test can work <span class="badge m">measured</span></h2>
<p>S4 at 75 ms, same {fw_h:.1f} h, exit at the end of the next slot. Total SOL by buy size and by the <b>absolute</b> fee per buy (priority + tips). A failed guarded buy pays only its priority fee, because tips revert.</p>
<div class="tbl"><table><tr><th class='l'>Buy size</th><th>0.002 per buy / 0.0005 per fail</th><th>0.006 / 0.001</th><th>0.011 / 0.002</th><th>0.024 / 0.011 (about Run 2)</th></tr>{td_rows}</table></div>
<p class="small"><b>At Run 2's fees, a 0.1–0.25 SOL test loses even though the strategy works.</b> The fixed fees eat the edge, and about 2 in 3 attempts are failed buys that still pay the priority fee. Test at 0.5 SOL with a lower priority fee (tips revert on failure), or at 0.25 SOL only with fees of 0.006 SOL or less per buy.</p>""")
P.append(f"""<h2>Your question: "monitor the price and sell in pieces over time"</h2>
<div class="card warn"><b>It does not work for our entries.</b> Every way of selling in pieces or holding longer did worse than one sell right after the buy. Same S4 trades, total SOL:
<div class="tbl"><table><tr><th class='l'>Exit</th><th>45 ms</th><th>75 ms</th></tr>{ex_rows}</table></div>
<p><b>Why:</b> after our entry the price climbs for well under a second while the snipers and copy-bots buy, then it fades. The ladders only pay for the case-study wallets because they buy earlier (about 40 ms) and bigger, and pick launches that keep running. Even their own presets lose in the final "clear" sells (−32.5 / −16.8 SOL over 6 days); the take-profit steps carry them.</p></div>""")
names = {"9Sh2fd": "9Sh2fd", "DGmspi": "DGmspi", "AHwJSn": "AHwJSnFN", "dKMjeG": "dKMjeGJ4", "CWiNFA": "CWiNFAEk", "A21wCG": "A21wCG8H", "3yrJE1": "3yrJE1A8", "FeCAXC": "FeCAXCyH", "6Kj5Ch": "6Kj5ChEZ", "5g8bvi": "5g8bviwg", "haqqiU": "haqqiUUX"}
lm_rows = "".join(f"<tr><td class='l'>{e(names.get(w, w))}</td>" + "".join(f"<td>{pnl(LM[w][k]['tot'], 2)} <span class='mut small'>({LM[w][k]['fills']}/{LM[w][k]['n']})</span></td>" for k in ("R2_45", "R2_75", "R1_45", "R1_75")) + "</tr>" for w in names if w in LM)
# leads: pruning + market-cap effect, computed here from the evidence rows
mcg = collections.defaultdict(list)
for r in FW:
    x = r["land"].get("75")
    if x and x.get("filled"): mcg["<36" if r["mc_bundle_sol"] < 36 else "36+"].append(x["pnl"])
P.append(f"""<h2>Possible improvements (found overnight, not yet forward-tested)</h2>
<ul>
<li><b>Bigger dev/bundle launches did better.</b> Fills with market cap after the bundle under 36 SOL averaged {statistics.mean(mcg['<36']) if mcg['<36'] else 0:+.3f} SOL each ({len(mcg['<36'])} fills). Fills at 36 SOL or more averaged {statistics.mean(mcg['36+']) if mcg['36+'] else 0:+.3f} ({len(mcg['36+'])}). Not used yet; it could be noise.</li>
<li><b>Lists copied from other profitable snipers.</b> Same guarded flip, list built only from our collector data (no ledger history). Total SOL, with fills/attempts:
<div class="tbl"><table><tr><th class='l'>List source</th><th>replay 45 ms</th><th>replay 75 ms</th><th>old data 45 ms</th><th>old data 75 ms</th></tr>{lm_rows}</table></div>
Only the 9Sh2fd / DGmspi lists are positive in both periods. AHwJSnFN's list is frozen in the dry run as S5 for a clean forward test.</li>
</ul>""")

# ---- dissections of the wallets the owner shared (filled in as the studies finish)
DIS = [("FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W", "fifaw", "REPORT_FiFawH.md", "FiFawH_snipes.html"),
       ("dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK", "dkmjeg", "REPORT_dKMjeG.md", "dKMjeG_snipes.html"),
       ("CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J", "cwinfa", "REPORT_CWiNFA.md", "CWiNFA_snipes.html"),
       ("9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw", "q9z", "REPORT_9qz7cW.md", "9qz7cW_snipes.html")]
def md_verdict(path, max_lines=14):
    if not os.path.exists(path): return None
    lines = [l.rstrip() for l in open(path) if l.strip()]
    body = []
    for l in lines[1:]:
        if l.startswith("## ") and body: break
        body.append(l)
    txt = "\n".join(body[:max_lines])
    txt = e(txt)
    txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
    return "<br>".join(txt.split("\n"))
dis_html = ""
for w, d, rep, htm in DIS:
    v = md_verdict(os.path.join(OV, d, rep))
    dis_html += f"<details><summary>{e(w[:8])}… {ln(GW(w), 'GMGN')} · {'report ready' if v else 'study still running'}</summary><div class='small'>{v or 'The full study is still running; this section fills in when it is done.'}"
    dis_html += f"<p class='mut'>Full report: <code>ops/overnight/{d}/{rep}</code>; snipe-by-snipe page: <code>ops/overnight/{d}/{htm}</code></p></div></details>"
P.append(f"""<h2>Dissections of the wallets you shared</h2><p>Each wallet: bot / infrastructure, ground-truth profit, funding links, selection, entry and exits, and what we can copy (tested with our replay).</p>{dis_html}""")
P.append(open(os.path.join(HERE, "sections.html")).read())
P.append("</div></body></html>")
out = os.path.join(HERE, "S4_STRATEGY.html")
open(out, "w").write("\n".join(P))
print("wrote", out, f"{os.path.getsize(out) / 1024:.0f} KB")
