#!/usr/bin/env python3
# READ-ONLY, offline: builds the "become them" FINAL-2 report (report/FINAL2_STRATEGY.html) from saved replay outputs.
# Times PKT (UTC+5). Every token / wallet / transaction is a link (GMGN / Solscan) so the owner can check trades by hand.
import os, json, html, statistics, datetime, random, re
HERE = os.path.dirname(os.path.abspath(__file__)); OV = os.path.dirname(HERE); CORE = os.path.join(OV, "core")
e = html.escape
PKT = datetime.timezone(datetime.timedelta(hours=5))
TX = lambda s: f"https://solscan.io/tx/{s}"; GW = lambda a: f"https://gmgn.ai/sol/address/{a}"; GT = lambda m: f"https://gmgn.ai/sol/token/{m}"
sh = lambda x, a=4, b=4: f"{x[:a]}…{x[-b:]}" if x else "—"
BAD = re.compile(r"n+[i1!]+g+[g]*(?:e+r+|a+h?|u+h?)|f+a+g+(?:g*o+t+)?|r+e+t+a+r+d|k+i+k+e+", re.I)
mask = lambda s: BAD.sub("[masked]", s or "")
def ln(url, text): return f'<a href="{url}" target="_blank" rel="noopener">{e(text)}</a>'
def pnl(x, d=2): return "—" if x is None else f'<span class="{"pos" if x > 0 else "neg" if x < 0 else ""}">{x:+.{d}f}</span>'
pk = lambda t: datetime.datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M:%S")
CSS = open(os.path.join(HERE, "style.css")).read()
EV = json.load(open(os.path.join(HERE, "f2_evidence.json")))
R2 = json.load(open(os.path.join(CORE, "final2_picks_v3_become_B0.5_lands.json")))
R2b = {r["m"]: r for r in json.load(open(os.path.join(CORE, "final2_picks_v3_become_B0.5_tu.json")))}
R1T = [r for r in json.load(open(os.path.join(CORE, "lab_cF2_become_B0.5_c.json"))) if r.get("run") == "R1"]
FWD = json.load(open(os.path.join(OV, "dryrun", "forward_generic.json"))) if os.path.exists(os.path.join(OV, "dryrun", "forward_generic.json")) else None
def agg(R, L, var, ex="t8", cost="cw"):
    """total SOL incl. failed attempts, fills, attempts, median per fill, win share, w/o best 5, halves"""
    ov = {"today": 0.0, "cw": 0.004}[cost]; fc = {"today": 0.005, "cw": 0.003}[cost]
    v = [(r["bt"], r[L][var]) for r in R if r.get(L, {}).get(var)]
    if not v: return None
    fl = [(bt, x["pnl"][ex] + ov) for bt, x in v if x["fill"]]; nf = len(v) - len(fl)
    p = sorted(x for _, x in fl); tot = sum(p) - fc * nf
    t0 = min(bt for bt, _ in v); t1 = max(bt for bt, _ in v); mid = (t0 + t1) / 2
    h1 = sum(x for bt, x in fl if bt < mid) - fc * sum(1 for bt, x in v if not x["fill"] and bt < mid)
    return dict(tot=tot, fills=len(fl), n=len(v), med=statistics.median(p) if p else 0, win=sum(1 for x in p if x > 0) / max(1, len(p)),
                wo5=tot - sum(p[-5:]), h1=h1, h2=tot - h1, hrs=(t1 - t0) / 3600)
P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Become Them: FINAL-2</title><style>{CSS}</style></head><body><div style='background:#b3261e;color:#fff;padding:10px 14px;border-radius:8px;margin:8px 0'><b>SUPERSEDED (10-23 11:55 PKT).</b> These numbers are from before an independent check found 3 replay bugs in our favour. FINAL-2 is now weak (75 ms overnight +1.07, daytime −0.48), and the daytime forward test loses at every landing speed. Read <b>DECISION.html</b> instead.</div><div class='wrap'>"]
now = datetime.datetime.now(PKT).strftime("%Y-%m-%d %H:%M PKT")
P.append(f"""<h1>Become them: FINAL-2 picks, first after the bundle, sell at 8 s</h1>
<p class="mut">Research report, built {now}. Replay and paper forward test only: <b>nothing here was traded</b>. Times are PKT (UTC+5).</p>
<div class="chips"><span class="chip">Confidence: low–medium</span><span class="chip">Overnight PKT only, for now</span><span class="chip">Needs: lower fees, ideally ≤45 ms landing</span><span class="chip">Engine path built, not deployed</span></div>""")
a75 = agg(R2, "75", "proafter_slip"); a45 = agg(R2, "45", "proafter_slip"); t75 = agg(R1T, "75", "proafter_slip"); t45 = agg(R1T, "45", "proafter_slip")
P.append(f"""<div class="card tldr"><b>In short</b><ul>
<li><b>The strategy.</b> Do what the profitable bots (dKMjeGJ4, CWiNFAEk, FiFawH) do, with our own selection. Don't front-run them.
  <ol><li><b>Pick:</b> FINAL-2, our model. It scores every launch at the dev's bundle close and copies no one.</li>
  <li><b>Buy:</b> 0.5 SOL, only if we are first after the bundle (0.5% price guard).</li>
  <li><b>Sell:</b> everything about 8 s later, after the wave of ordinary buyers.</li></ol></li>
<li><b>Overnight (US hours), fully out of sample</b> (10-22 23:31 → 10-23 08:16, {a75['hrs']:.1f} h). The pros' buys after ours are removed and every follower's real slippage limit is applied:
  <ul><li>at 75 ms: {pnl(a75['tot'])} SOL ({a75['fills']} fills);</li>
  <li>at 45 ms: {pnl(a45['tot'])} SOL ({a45['fills']} fills);</li>
  <li>CW-style costs.</li></ul>
  It is positive in every variant, including with <i>all</i> sniper buys after ours removed.</li>
<li><b>Daytime is unproven.</b> FINAL-2 trained on 10-22 up to 14:58 PKT. On the only clean daytime slice after that (14:58–18:00, {t75['hrs']:.1f} h, {t75['fills']} fills at 75 ms) the result is {pnl(t75['tot'])} at 75 ms and {pnl(t45['tot'])} at 45 ms. That is a small sample with a pessimistic placement model. <b>An earlier claim that it was positive in both periods was wrong</b> (in-sample picks), and it is corrected here.</li>
<li><b>It lives or dies on fees and speed.</b> Run 2's fee settings (≈0.0235 SOL per buy, 0.0105 per failed buy) kill it: about 60% of guarded buys fail by design. CW-style sends (0.003 priority + 0.003 tip, nonce fan-out) make it work. Landing at ≤45 ms roughly doubles it.</li>
<li><b>Your decisions:</b>
  <ul><li>a no-send paper run on the server;</li>
  <li>a landing probe of the nonce fan-out (fees only);</li>
  <li>an FRZ test overnight PKT, sized for 100–200 fills.</li></ul>
  Plan: <code>ops/final2/PLAN.md</code>. Send design: <code>ops/final2/SEND_DESIGN.md</code>.</li>
</ul></div>""")
# ---- results table (R2)
def cellrow(lab, R, L):
    out = f"<tr><td class='l'>{e(lab)}</td>"
    for var in ("slip", "proafter_slip", "nosnip"):
        for cost in ("today", "cw"):
            x = agg(R, L, var, cost=cost); out += f"<td>{pnl(x['tot']) if x else '—'}</td>"
    x = agg(R, L, "proafter_slip")
    return out + f"<td>{x['fills']}/{x['n']}</td><td>{pnl(x['med'], 3)}</td><td>{x['win']:.0%}</td><td>{pnl(x['wo5'])}</td><td>{pnl(x['h1'])} / {pnl(x['h2'])}</td></tr>"
hdr = ("<tr><th class='l'>Landing</th><th>slippage<br>today</th><th>slippage<br>CW</th><th>pros' later buys removed<br>today</th><th>pros' later buys removed<br>CW</th>"
       "<th>all sniper buys removed<br>today</th><th>all sniper buys removed<br>CW</th><th>fills</th><th>median / fill</th><th>win</th><th>w/o best 5</th><th>halves</th></tr>")
P.append(f"""<h2>Results, overnight PKT (fully out of sample) <span class="badge m">measured</span></h2>
<p>0.5 SOL per buy, 8 s hold, total SOL including every failed guarded buy. <b>Today</b> = 2% buy overhead and 0.005 per failed buy. <b>CW</b> = CW-style fixed fees at 0.5 SOL: 1.2% overhead and 0.003 per failed buy. The last five columns use the "pros' later buys removed" variant at CW cost.</p>
<div class="tbl"><table>{hdr}{''.join(cellrow(f'{L} ms', R2, L) for L in ('75', '60', '45', '30', '20'))}</table></div>
<p class="small mut">
<b>Pros removed:</b> the buys of the 9 shared wallets after our entry are deleted (dK, CW, FiFawH, 9qz7cW, 9Sh2fd, DGmspi, D24ipY, AHwJSnFN, 4yFAz).<br>
<b>All sniper buys removed:</b> the buys of all 321 fast-sniper wallets after our entry are deleted, so profit can come only from ordinary buyers.<br>
<b>Slippage:</b> each follower's decoded min-out / max-cost is applied, so buyers our buy would push past their limit are dropped. This matched the chain's logged results exactly.</p>""")
P.append(f"""<h2>The only clean daytime slice (10-22 14:58–18:00 PKT) <span class="badge m">measured</span></h2>
<p>Same picks model, scored offline. It uses the old-data placement proxy (no engine timelines that day), which is pessimistic at 45–75 ms. The sample is small.</p>
<div class="tbl"><table>{hdr}{''.join(cellrow(f'{L} ms', R1T, L) for L in ('75', '45', '30'))}</table></div>
<p class="small mut">Market-wide ordinary buying at 14:00–18:00 PKT is normal: 18–20 distinct buyers in the first 60 s per launch, vs 18–25 overnight. Only 10:00–13:00 PKT is thinner. So daytime is <b>unproven, not shown negative</b>. The forward test below is collecting daytime data.</p>""")
# ---- cost / test size
def odds(R, L, ov, fc, N):
    v = [r[L]["proafter_slip"] for r in R if r.get(L, {}).get("proafter_slip")]
    fl = [x["pnl"]["t8"] + (0.02 - ov) * 0.5 for x in v if x["fill"]]; fpr = (len(v) - len(fl)) / max(1, len(fl))
    random.seed(11); return sum(1 for _ in range(3000) if sum(random.choice(fl) for _ in range(N)) - fc * fpr * N > 0) / 3000
rows = ""
for lab, L, ov, fc in (("75 ms, today's costs", "75", 0.02, 0.005), ("75 ms, CW-style", "75", 0.012, 0.003), ("45 ms, CW-style", "45", 0.012, 0.003), ("30 ms, CW-style", "30", 0.012, 0.003)):
    x = agg(R2, L, "proafter_slip", cost="cw" if ov < 0.02 else "today")
    rows += f"<tr><td class='l'>{e(lab)}</td><td>{pnl(x['tot'] * 24 / x['hrs'], 1)}</td>" + "".join(f"<td>{odds(R2, L, ov, fc, N):.0%}</td>" for N in (15, 50, 100, 200)) + "</tr>"
P.append(f"""<h2>Costs, speed and how big a test must be <span class="badge m">measured</span></h2>
<p>Overnight window, pros' buys after ours removed, 8 s hold, 0.5 SOL. The odds columns show the chance that a live total is above zero after N fills (bootstrap from the replay fills). The edge is fat-tailed: most trades are small losses and a few are big wins. <b>A 15-buy test can't confirm or reject it.</b></p>
<div class="tbl"><table><tr><th class="l">Execution</th><th>SOL / 24 h</th><th>15 fills</th><th>50</th><th>100</th><th>200</th></tr>{rows}</table></div>
<p class="small mut">Run 2's real settings (≈3% per buy + 0.0105 per failed buy) give about +0.4 SOL per 8.3 h overnight at 75 ms. That's barely positive. The fee change comes first.</p>""")
# ---- activity check (A7)
def actrow(L):
    v = [r[L]["proafter_slip"] for r in R2 if r.get(L, {}).get("proafter_slip") and r[L]["proafter_slip"]["fill"]]
    out = ""
    for lab, f in (("0", lambda x: x["nb"] == 0), ("1", lambda x: x["nb"] == 1), ("2–3", lambda x: 2 <= x["nb"] <= 3), ("4+", lambda x: x["nb"] >= 4)):
        g = [x for x in v if f(x)]
        if not g: continue
        t8 = sum(x["pnl"]["t8"] + 0.004 for x in g); e1 = sum(x["pnl"]["eos1"] + 0.004 for x in g)
        out += f"<tr><td class='l'>{L} ms · {lab}</td><td>{len(g)}</td><td>{pnl(t8)}</td><td>{sum(1 for x in g if x['pnl']['t8'] + 0.004 > 0)}/{len(g)}</td><td>{pnl(e1)}</td></tr>"
    return out
P.append(f"""<h2>Activity after our buy decides the trade <span class="badge m">measured</span></h2>
<p>Overnight fills, pros' later buys removed, CW-style cost. The deciding number is how many outside buys land after ours by the end of the next slot.</p>
<div class="tbl"><table><tr><th class="l">Landing · buyers after us</th><th>fills</th><th>hold 8 s</th><th>wins</th><th>sell at end of next slot</th></tr>{actrow("75")}{actrow("45")}</table></div>
<p><b>All the profit is in fills that buyers follow right away.</b> With 0–1 followers it's better to sell immediately; with 2 or more, hold 8 s. That rule is the <b>activity check (A7)</b>.
<ul><li>In the replay it beats the plain 8 s sell in every set and landing.</li>
<li>Frozen 09:23 PKT for the forward test.</li>
<li>Built into the engine as <code>--hold-activity-k 1</code> (off by default).</li>
<li>This is your "no activity → you only lose fees" point, measured.</li></ul></p>""")
# ---- cumulative chart
def svg_cum(series, title, w=760, h=190):
    pts = []; cum = 0.0
    for t, x in series: cum += x; pts.append((t, cum))
    if len(pts) < 2: return ""
    t0, t1 = pts[0][0], pts[-1][0]; lo = min(0, min(c for _, c in pts)); hi = max(0.01, max(c for _, c in pts))
    X = lambda t: 40 + (w - 60) * (t - t0) / max(1, t1 - t0); Y = lambda c: 10 + (h - 40) * (hi - c) / (hi - lo)
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(t):.1f},{Y(c):.1f}" for i, (t, c) in enumerate(pts))
    ticks = "".join(f"<text x='{X(t0 + k * (t1 - t0) / 4):.0f}' y='{h - 8}' font-size='11' fill='currentColor' opacity='.6' text-anchor='middle'>{datetime.datetime.fromtimestamp(t0 + k * (t1 - t0) / 4, PKT):%H:%M}</text>" for k in range(5))
    return (f"<div class='card'><b>{e(title)}</b><svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='{e(title)}'>"
            f"<line x1='40' x2='{w - 20}' y1='{Y(0):.1f}' y2='{Y(0):.1f}' stroke='currentColor' opacity='.25'/><path d='{path}' fill='none' stroke='var(--acc)' stroke-width='2'/>"
            f"<text x='4' y='{Y(hi) + 4:.0f}' font-size='11' fill='currentColor' opacity='.6'>{hi:+.1f}</text><text x='4' y='{Y(lo) + 4:.0f}' font-size='11' fill='currentColor' opacity='.6'>{lo:+.1f}</text>{ticks}</svg>"
            f"<p class='small mut'>Cumulative SOL, 0.5 SOL per buy, every attempt included. End: {pnl(cum)} SOL.</p></div>")
for L in ("75", "45"):
    ser = sorted((r["bt"], (r[L]["proafter_slip"]["pnl"]["t8"] + 0.004) if r[L]["proafter_slip"]["fill"] else -0.003) for r in R2 if r.get(L, {}).get("proafter_slip"))
    P.append(svg_cum(ser, f"Overnight, {L} ms: pros' later buys removed, follower slippage, CW-style cost"))
# ---- worked example
best = max((r for r in EV if r["land"].get("75", {}).get("proafter_slip")), key=lambda r: r["land"]["75"]["proafter_slip"]["cw"])
bx = best["land"]["75"]
P.append(f"""<h2>How to check one trade by hand</h2><div class="card"><p>Example: the best modelled trade, {ln(GT(best['m']), mask(best['name']))}, created {pk(best['bt'])} PKT.</p><ol class="steps">
<li><b>Create:</b> {ln(TX(best['create_sig']), 'create transaction')} by {ln(GW(best['deployer']), sh(best['deployer'], 6, 4))}. The dev bought {best['dev']} SOL; the glued bundle had {best['glued']} txs. FINAL-2 picked it live at bundle close.</li>
<li><b>Our buy (75 ms):</b> it lands right behind {ln(TX(bx['after_sig']), 'this transaction')}, with {bx['ahead']} outside buyers ahead. The price there is {bx['ratio']:.3f}× the post-bundle price, so the 0.5% guard passes.</li>
<li><b>Hold 8 s:</b> {bx.get('nb', '—')} outside buys land in the next slot. On GMGN's trade list you can see the wave: a group of four wallets buys at about 2.8 s, many ordinary buyers follow, and the price reaches about 4× by 8–9.5 s. The same four wallets dump together at 9.8 s.</li>
<li><b>Our sell:</b> it lands right before {ln(TX(bx['sell_before_sig']), 'this trade') if bx.get('sell_before_sig') else 'the next trade'}. Result: {pnl(bx['proafter_slip']['cw'], 3)} SOL on 0.5 SOL, with the pros' later buys removed and CW-style costs.</li></ol></div>""")
# ---- all trades
tr = []
for r in EV:
    x = r["land"].get("75")
    if not x: continue
    if not x.get("fill"): continue
    s, pa, ns = (x.get(v, {}).get("cw") for v in ("slip", "proafter_slip", "nosnip"))
    tr.append(f"<tr><td class='l mono'>{pk(r['bt'])}</td><td class='l'>{ln(GT(r['m']), mask(r['name'])[:24])}</td><td>{ln(GW(r['deployer']), sh(r['deployer']))}</td>"
              f"<td>{ln(TX(r['create_sig']), 'create')}</td><td>{ln(TX(x['after_sig']), 'after')} ({x['ahead']})</td><td>{x['ratio']:.3f}</td>"
              f"<td>{ln(TX(x['sell_before_sig']), 'sell')} </td><td>{x.get('nb', '—')}</td><td>{pnl(s, 3)}</td><td>{pnl(pa, 3)}</td><td>{pnl(ns, 3)}</td><td class='small'>{e(','.join(r.get('pros_in') or []) or '—')}</td></tr>"
              if x.get("sell_before_sig") else "")
nfail = sum(1 for r in EV if r["land"].get("75") and not r["land"]["75"].get("fill"))
P.append(f"""<h2>Every overnight fill at 75 ms ({sum(1 for t in tr if t)} trades; {nfail} more picks failed the guard at −0.003 each) <span class="badge m">measured</span></h2>
<p class="small">Columns:</p>
<ul class="small">
<li>"after": the transaction our buy lands right behind, with the number of outside buyers ahead in brackets.</li>
<li>guard: the price there vs the post-bundle price.</li>
<li>"sell": the trade our 8 s sell lands in front of.</li>
<li>buyers: outside buys in the next slot.</li>
<li>PnL columns: SOL at CW-style cost.</li>
<li>pros: shared wallets that also traded this launch.</li>
</ul>
<div class="tbl"><table><tr><th class="l">created (PKT)</th><th class="l">token</th><th>deployer</th><th>create</th><th>we land after</th><th>guard</th><th>sell lands before</th><th>buyers</th><th>slippage</th><th>pros removed</th><th>all snipers removed</th><th>pros in launch</th></tr>{''.join(tr)}</table></div>""")
# ---- the pros
P.append(f"""<h2>What the profitable bots really make (from their own ledgers) <span class="badge m">measured</span></h2>
<div class="tbl"><table><tr><th class="l">Wallet</th><th>Profit</th><th class="l">How</th><th class="l">Copying it under your rule</th></tr>
<tr><td class="l">{ln(GW('dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK'), 'dKMjeGJ4')}</td><td>+197 SOL / 61 h</td><td class="l">~20-way nonce fan-out (42 ms), own create-time picks, sells in pieces 2–12 s, 1.8–12 SOL</td><td class="l">Rejected: profit came from its own buy after ours</td></tr>
<tr><td class="l">{ln(GW('CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J'), 'CWiNFAEk')}</td><td>+14.9 SOL / 61 h</td><td class="l">1 SOL, 0.003 priority + 0.003 tip nonce fan-out (49 ms), hot-dev picks, ~1.5 s exit + take-profit</td><td class="l">Rejected: depends on CW and fast snipers</td></tr>
<tr><td class="l">{ln(GW('FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W'), 'FiFawH')}</td><td>+27.8 SOL / 61 h</td><td class="l">Picks with broad ordinary demand (likely off-chain signals), first in line, holds 5–15 s</td><td class="l">Its picks can't be predicted at create time</td></tr>
<tr><td class="l">{ln(GW('9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw'), '9qz7cWBq')}</td><td>+406 SOL / 61 h</td><td class="l">Snipes lose; 2–35 SOL buys into live waves make the money</td><td class="l">Needs its size</td></tr>
</table></div><p class="small mut">Full reports: <code>ops/overnight/dkmjeg/REPORT_dKMjeG.md</code>, <code>cwinfa/REPORT_CWiNFA.md</code>, <code>fifaw/REPORT_FiFawH.md</code>, <code>q9z/REPORT_9qz7cW.md</code>. All of them: own selection, first after the bundle, hold through the 2–12 s wave, cheap nonce fan-out sends.</p>""")
P.append("""<h2>What did not work <span class="badge m">measured</span></h2><ul>
<li><b>The quick sell</b> (end of the next slot, Run 2 / S4): it loses once the bots' buys after us are removed. Our 5 real PROD fills had zero outside trades between our buy and sell.</li>
<li><b>S4</b> (copying the case bots' dev list): front-running them. With real slippage limits it is −0.32 (old period) / +2.80 (replay) at 75 ms.</li>
<li><b>Later entries</b> (1–180 s after the create, no race): every time and exit is negative. Rule searches are at noise level against shuffled nulls; models are positive in neither direction. On FINAL-2's own picks, entering at 1–12 s loses.</li>
<li><b>Exits:</b> take-profit caps, dev-sell or big-sell exits, following the pros' or snipers' sells, "let winners run" trailing, and piece ladders all lose to a plain 8–10 s sell. A "wave stopped" exit didn't replicate.</li>
<li><b>Other variants:</b> dK-style picks, a looser guard (5–30%), score-based sizing, and non-SOL-quoted curves (fees ~6.6% per round trip).</li></ul>""")
P.append("""<h2>Live path (built on the host, not deployed)</h2><ul>
<li><b>Engine flag</b> <code>--final2-sock</code>:
  <ul><li>at the bundle close the engine asks our FINAL-2 scorer over a local socket; the answer takes 0.85 ms median;</li>
  <li>it buys only on "pick";</li>
  <li>it fails closed.</li></ul>
  The binary is <code>~/sniper-data/work/final2/snipe_engine_final2</code>. The exit is <code>--hold-ms 7700</code>.</li>
<li><b>Scripts:</b> <code>ops/final2/deploy_f2.sh</code> (copy only), <code>ops/final2/paper_f2.sh</code> (server paper run, no sends), <code>ops/final2/f2_flags.sh</code>.</li>
<li><b>Needed first:</b>
  <ul><li>the collector kept running (the current run ends 10-23 20:43 PKT);</li>
  <li>your OK for the paper run and the landing probe.</li></ul></li></ul>""")
if FWD:
    ta = FWD.get("trackA", {})
    rws = "".join(f"<tr><td class='l'>{k.replace('_', ' ')}</td><td>{v['fills']}/{v['attempts']}</td><td>{pnl(v.get('A4'), 3)}</td><td>{pnl(v.get('A2'), 3)}</td></tr>" for k, v in ta.items() if k.split('_')[0] in ('L75', 'L45') )
    P.append(f"""<h2>Forward test (paper, frozen before the data) <span class="badge m">measured</span></h2>
<p>Rules frozen 08:26 / 08:33 / 08:46 PKT (hashes in <code>dryrun/frozen_generic*.json</code>); scored hourly on launches created after the freeze. Last run: {e(FWD.get('evaluated_at', ''))}. Totals use today's costs.</p>
<div class="tbl"><table><tr><th class="l">Landing / variant</th><th>fills</th><th>8 s (A4)</th><th>10 s (A2)</th></tr>{rws}</table></div>""")
P.append("""<h2>Phase 2: our demand model (GDM)</h2><p>A second model trained on the number of ordinary buyers in 2–10 s. Buying if FINAL-2 <i>or</i> GDM picks a launch beats FINAL-2 alone overnight: +8.17 vs +4.82 at 45 ms, pros' later buys removed, and +2.14 vs −0.62 without the best 5 trades. But the version usable live (no token metadata) is mixed. Frozen for the forward test (FRZ-GDM-U); details in <code>ops/overnight/gdm/RESULTS.md</code>.</p>""")
P.append("<p class='small mut'>Files: <code>ops/overnight/BECOME_THEM.md</code>, <code>ops/overnight/STRATEGIES.md</code>, <code>ops/final2/</code>, replay engine <code>ops/overnight/core/rp.py</code>, evaluator <code>core/become_eval.py</code>.</p></div></body></html>")
open(os.path.join(HERE, "FINAL2_STRATEGY.html"), "w").write("\n".join(P))
print("written", os.path.getsize(os.path.join(HERE, "FINAL2_STRATEGY.html")), "bytes")
