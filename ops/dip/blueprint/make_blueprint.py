#!/usr/bin/env python3
# Builds ops/dip/BLUEPRINT_V1.html: the dip-backrun Working Model V1 (owner, 10-24 03:40 PKT: "one doc should get us
# here ... enough for you to recreate it as is"). Live figures (runs, FRZ tests, probes, competitors) are read from the
# records in ops/dip/blueprint/data/ (copied from the server: /root/prod/runs/dip_r*.jsonl + REALIZED lines, budget file);
# study figures (selection, backtests, census, dissections) are quoted from the study logs named next to each one.
# usage: python3 -I make_blueprint.py   (refresh data/ first: see ops/dip/blueprint/refresh.sh)
import json, os, html, statistics, collections, datetime as dt

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "BLUEPRINT_V1.html")
PROD = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"; FRZ = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
TGT = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC",
       "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX"}
PKT = dt.timezone(dt.timedelta(hours=5))

def jl(name): return [json.loads(l) for l in open(os.path.join(D, name)) if l.strip()]
def esc(s): return html.escape(str(s))
def pkt(ns): return dt.datetime.fromtimestamp(ns / 1e9, PKT).strftime("%H:%M:%S")
def gm(m, t=None): return f'<a href="https://gmgn.ai/sol/token/{m}">{esc(t or m[:6] + "…")}</a>'
def gmw(w, t=None): return f'<a href="https://gmgn.ai/sol/address/{w}">{esc(t or w[:8])}</a>'
def tx(s, t): return f'<a href="https://solscan.io/tx/{s}">{esc(t)}</a>'
def sol(x, d=4, plus=True):
    if x is None: return "–"
    c = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{c}">{"+" if (x > 0 and plus) else ""}{x:.{d}f}</span>'
def pct(x, d=0):
    c = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{c}">{"+" if x > 0 else ""}{x:.{d}f}%</span>'
def table(head, rows, num=()):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f'<td class="{"n" if i in num else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'
med = lambda v: statistics.median(v) if v else float("nan")

RTT = json.load(open(os.path.join(D, "leader_rtt_new.json")))["leaders"]
GEO = {r["pk"]: r for r in json.load(open(os.path.join(D, "leader_geo.json")))["rows"]}
def where(pk):
    r = RTT.get(pk, {}); g = GEO.get(pk, {})
    rtt = r.get("rtt"); city = g.get("city") or "?"
    return f"{city} ({rtt:.0f} ms)" if rtt is not None else f"{city} (?)"

def realized(name):
    out, last = {}, None
    for l in open(os.path.join(D, name)):
        if "REALIZED" in l:
            kv = dict(x.split("=", 1) for x in l.split() if "=" in x)
            out[kv["mint"]] = float(kv["pnl"]); last = float(kv["run_realized"])
    return out, last

def run_rows(evs, real):
    """one row per fire: filled (with exit, curve / chain P&L, links) or missed (guard 6042 / deadline 6001)"""
    rows = []
    for f in [e for e in evs if e["ev"] == "fire"]:
        m = f["mint"]; sig = f["buy_sig"]
        pk = next((e for e in evs if e["ev"] == "pick" and e["mint"] == m and e["sig"] == f["dump_sig"]), {})
        bl = next((e for e in evs if e["ev"] == "buy_land" and e.get("sig") == sig), None)
        bf = next((e for e in evs if e["ev"] == "buy_failed" and e.get("sig") == sig), None)
        cl = next((e for e in evs if e["ev"] == "close" and e.get("buy_sig") == sig), {})
        ex = next((e for e in evs if e["ev"] == "exit" and e["mint"] == m and e.get("t", 0) >= f["t_fire"]), {})
        err = json.dumps(cl.get("err") or "")
        feats = pk.get("feats") or [0, 0, 0]
        ms = ((bl or bf)["t"] - f["t_dump_rx"]) / 1e6 if (bl or bf) else None
        tape = sorted([e for e in evs if e["ev"] == "tape" and e["mint"] == m and e["t"] >= f["t_dump_rx"]], key=lambda e: (e["slot"], e["idx"], e["j"]))
        ahead = [e for e in tape if bl and (e["slot"], e["idx"]) < (bl["slot"], bl["idx"]) and e["buy"] and e["user"] not in (PROD, FRZ)]
        sl = cl.get("sell_land")
        behind = [e for e in tape if bl and (bl["slot"], bl["idx"]) < (e["slot"], e["idx"]) < ((sl[0], sl[1]) if sl else (1 << 62, 0)) and e["buy"] and e["user"] not in (PROD, FRZ)]
        sells = [x[0] if isinstance(x, list) else x for x in (cl.get("sell_sigs") or [])]
        rows.append(dict(m=m, t=f["t_dump_rx"], score=pk.get("score", 0), age=pk.get("age", 0), sell=feats[1], drop=feats[2], client=f["client"],
            leader=f["leader"], route=f["route"].replace("route:", ""), paths="+".join(w["path"] for w in f["writes"]), tips=f["tips"] / 1e9,
            filled=bl is not None, ms=ms, dslot=(bl or {}).get("slots_after_dump", (bf or {}).get("slot", f["slot"]) - f["slot"]),
            why="guard (6042)" if "6042" in err else "deadline (6001)" if "6001" in err else cl.get("result", "?"),
            exit=ex.get("why"), xval=ex.get("value"), curve=(cl.get("curve_pnl") or 0) / 1e9 if bl else None, chain=real.get(m) if bl else None,
            buy=sig, sells=sells, dump=f["dump_sig"], decision=f["decision_us"], ahead=ahead, behind=behind))
    return rows

def who(u): return TGT.get(u, u[:6])
def trade_table(rows):
    out = []
    for r in rows:
        if not r["filled"]: continue
        links = tx(r["buy"], "buy") + "".join(" · " + tx(s, "sell") for s in r["sells"]) + " · " + tx(r["dump"], "dump")
        out.append([pkt(r["t"]), gm(r["m"]), f'{r["sell"]:.2f} SOL −{r["drop"]:.0f}%', f'{r["age"]:.1f} s', f'{r["score"]:.2f}', f'{esc(r["client"])}<br>{esc(where(r["leader"]))}',
                    esc(r["paths"]), f'{r["ms"]:.0f} ms (+{r["dslot"]} slot)', ", ".join(f'{who(e["user"])} {e["sol"] / 1e9:.2f}' for e in r["ahead"]) or "none",
                    f'{len(r["behind"])} buys, {sum(e["sol"] for e in r["behind"]) / 1e9:.2f} SOL', f'{esc(r["exit"])}' + (f' x{r["xval"]:.3f}' if r["xval"] else ""),
                    sol(r["curve"]), "<b>" + sol(r["chain"]) + "</b>", links])
    return table(["dump at (PKT)", "token", "dump", "token age", "score", "leader", "paths", "we landed after dump", "bought ahead of us", "after us (to our sell)", "exit", "curve P&L", "chain P&L", "links"],
                 out, num=(11, 12))
def miss_table(rows):
    out = [[pkt(r["t"]), gm(r["m"]), f'{r["sell"]:.2f} SOL −{r["drop"]:.0f}%', f'{r["score"]:.2f}', f'{esc(r["client"])} — {esc(where(r["leader"]))}', esc(r["paths"]),
            f'{r["ms"]:.0f} ms' if r["ms"] is not None else "–", esc(r["why"]), tx(r["buy"], "tx")] for r in rows if not r["filled"]]
    return table(["dump at (PKT)", "token", "dump", "score", "leader", "paths", "our tx executed after dump", "why no fill", "link"], out)

# ---------------- data ----------------
r1 = jl("dip_r1.jsonl"); r2 = jl("dip_r2.jsonl"); real1, tot1 = realized("log_r1.txt"); real2, tot2 = realized("log_r2.txt")
R1 = run_rows(r1, real1); R2 = run_rows(r2, real2)
budget = json.load(open(os.path.join(D, "budget.json")))
# the LAST entry of each run number (a start that ended at once, e.g. a passphrase retry, leaves an extra entry)
lastrun = lambda n: ([r for r in budget["runs"] if r["run"] == n] or [{}])[-1]
b1 = lastrun(1); b2 = lastrun(2)
r2_done = any(e["ev"] == "run_end" for e in r2)
f1 = run_rows(jl("frz_t1.jsonl"), {"HehqjBjoUq92petZT7ZCPys77gz3aPgFGiqmfixSi2Xx": -0.003594}); f2 = run_rows(jl("frz_t2.jsonl"), {})
ALL = R1 + R2
fills = [r for r in ALL if r["filled"]]; wins = [r for r in fills if (r["chain"] or 0) > 0]
miss1 = [r for r in R1 if not r["filled"]]; miss2 = [r for r in R2 if not r["filled"]]
fire_n = len(ALL); fill_n = len(fills)
chain_fills = sum(r["chain"] or 0 for r in fills)
pnl_total = (tot1 or 0) + (tot2 or 0)
land_near = [r["ms"] for r in ALL if r["ms"] is not None and (RTT.get(r["leader"], {}).get("rtt") or 999) < 50]
land_far = [r["ms"] for r in ALL if r["ms"] is not None and (RTT.get(r["leader"], {}).get("rtt") or 999) >= 50]
fast = json.load(open(os.path.join(D, "fast_bots_paths.json")))
pspeed = json.load(open(os.path.join(D, "probe_speed.json"))); prtt = json.load(open(os.path.join(D, "probe_rtt.json")))
pd = jl("probeD.jsonl"); ptim = {e["buy_sig"]: e for e in pd if e["ev"] == "timing"}
probesD = [(("+".join(w["path"] for w in p["writes"])), p["client"], ptim.get(p["buy_sig"], {})) for p in pd if p["ev"] == "probe"]
n_probes = {k: sum(1 for e in jl(f"probe{k}.jsonl") if e["ev"] == "probe") for k in "ABCD"}
far_fills = [r for r in fills + [x for x in f1 if x["filled"]] if (RTT.get(r["leader"], {}).get("rtt") or 999) >= 50]
cur_bal = (budget["runs"][-1].get("end_balance") or budget["runs"][-1]["start_balance"]) / 1e9
left = 0.5 - max(0.0, budget["first_start"] / 1e9 - cur_bal)

# ---------------- html ----------------
S = []
def h2(t, i): S.append(f'<h2 id="s{i}">{i}. {esc(t)}</h2>')
def h3(t): S.append(f"<h3>{t}</h3>")      # callers pass plain text or our own markup
def p(t): S.append(f"<p>{t}</p>")
def box(t): S.append(f'<div class="box">{t}</div>')
def ul(items): S.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")

now = dt.datetime.now(PKT).strftime("%Y-%m-%d %H:%M PKT")
S.append(f'''<h1>DIP-BACKRUN — WORKING MODEL V1 — BLUEPRINT</h1>
<div class="meta"><b>Status:</b> live on the PROD wallet {gmw(PROD, "2g7rYv7y")} since 10-24 02:15 PKT (run 1 done{", run 2 done" if r2_done else ", run 2 in progress"}).
<b>Built:</b> {now}. <b>Engine:</b> <code>snipe_engine --dip</code> build dip8 (sha256 bda7cee16ac9ac85…). <b>Model:</b> IMIT1 (sha256 c720ed613357…).
<b>Keep private:</b> server address, wallet keys and scripts are referenced below.</div>''')

# KPIs
S.append('<div class="grid">' + "".join(f'<div class="kpi"><span>{k}</span><b>{v}</b></div>' for k, v in [
    ("Live P&L (runs 1+2, chain)", sol(pnl_total)), ("Fills / wins", f"{fill_n} / {len(wins)}"), ("Avg P&L per fill", sol(chain_fills / max(1, fill_n))),
    ("Buy attempts that missed", f'<span class="neg">{fire_n - fill_n} of {fire_n} ({100 * (fire_n - fill_n) / max(1, fire_n):.0f}%)</span>'),
    ("haqqiUUX failed txs", "114 of 1,000 (11.4%)"), ("Our landing, nearby leaders", f"median {med(land_near):.0f} ms"),
    ("Size / exit", "0.25 SOL / +5% · −10% · 6 slots"), ("Loss budget left", f"{left:.3f} of 0.5 SOL")]) + "</div>")

S.append('<div class="toc"><b>Contents</b> ' + " · ".join(f'<a href="#s{i}">{i}. {t}</a>' for i, t in enumerate(
    ["The model in one page", "Why it makes money", "Pipeline, step by step", "Selection: IMIT1", "Execution: buy, guard, routes", "Exit and sell", "Safety and operations",
     "Live results", "Landing speed", "Competitors and references", "Considered and dismissed", "Caveats (exact)", "Recreate it", "File and server map"], 1)) + "</div>")

# 1
h2("The model in one page", 1)
box(f'''<b>What it does.</b> On a young pump.fun token, when someone sells ≥ 1 SOL into the bonding curve (a <b>dump</b>), we buy 0.25 SOL
<b>right behind it</b> (same or next slot) if a frozen model, trained to imitate three profitable dip bots, rates that dump in its top 2%.
The buy is protected by a <b>price guard</b> (max 5% above the post-dump price) and a <b>slot deadline</b> (dump slot + 1).
We sell on <b>+5%</b> take-profit, <b>−10%</b> stop-loss, or after <b>6 slots (~1.3 s)</b>, whichever comes first.<br><br>
<b>Why it works when it works.</b> A sharp dump on a fresh, busy token gets bought back within ~1–2 s by a cohort of consistently
profitable bots; we try to sit in front of them. <b>When it does not.</b> The fastest bots buy the bounce 2–40 ms after the dump;
when they beat us, our guard refuses the higher price and we pay only the fee (~0.0005 SOL).<br><br>
<b>So far (live, 0.25 SOL):</b> {fire_n} buy attempts, {fill_n} fills, {len(wins)} wins, chain P&L {sol(pnl_total)} SOL
(run 1 {sol(tot1)} · run 2 {sol(tot2)}{"" if r2_done else " so far"}).''')

# 2
h2("Why it makes money", 2)
p("Measured, not assumed (study logs: memory <i>profit-source-bot-cohort</i>, <i>dip-census</i>; ops/overnight/dip, ops/overnight/verify_dip):")
ul(["<b>The buyers after us are a pro cohort.</b> Removing the later buys of 541 consistently winning wallets turns the dip replay at 35 ms from "
    f"{sol(18.07, 2)} to {sol(-14.11, 2)} SOL (same test with 541 random wallets removed: {sol(11.36, 2)}). Our edge = getting in ahead of them.",
    f"<b>It is a stable pro niche.</b> Corrected census, 33 h: 53 wallets with ≥ 100 dip trips made {sol(189.8, 1)} SOL net, 79% of them positive; "
    "the skill persists across runs (R1-positive wallets +119.8 on R2, 85% positive).",
    f"<b>Speed decides.</b> Census by delay after the dump, closed trips: 0–10 ms {pct(7.3, 1)}, 10–60 ms {pct(0.9, 1)}…{pct(2.0, 1)}, 60 ms+ ≤ 0.",
    "<b>Selection matters as much as speed.</b> Unscored dumps win ~29% (dump-bounce test); the imitation model's picks win 66–89% in the backtest."])

# 3
h2("Pipeline, step by step", 3)
steps = [
 ("Feed", "Executed transactions of the pump program from Constant-K Kaldera <code>yellowstone-tx</code> (gRPC, processed commitment, account filter = pump). Each tx carries its block index, fee, every pump <b>TradeEvent</b> (user, buy/sell, SOL, tokens, virtual reserves after, fee bps, creator-fee bps) and <b>CreateEvent</b>. Shred feeds (kaldera deshred, turbo-kaldera, erpc entries) run beside it for timing only. Measured: the executed feed is 1.6 ms behind the first sighting (p90 5.5 ms)."),
 ("Follow new tokens", "On a CreateEvent the engine opens a <b>token book</b> (launch slot, index, creator, signer, mayhem flag) and decodes the create tx's accounts (bonding curve, creator vault, create_v2 flags). Only tokens created after the engine started are followed."),
 ("Rebuild the tape", "Every TradeEvent of a followed token is appended in chain order (slot, index, event). Out-of-order trades are inserted in place; a gap (pre-state ≠ previous post-state on the constant product) gets a synthetic trade, exactly as the study's <code>rp.repair_gaps</code>."),
 ("Launch structure", "Glued bundle = the create tx plus the unbroken run of buys right after it in the launch slot (index +0/+1). Insiders = creator, signer, glued buyers. <code>g_end</code> = first trade after the glued run."),
 ("Dump detection", "A trade is a dump when: it is a sell ≥ 1 SOL, not synthetic, after <code>g_end</code>, token age 1–1800 s (slot × 212 ms), curve vSOL &lt; 100 SOL after it, and it is the first big sell of its slot."),
 ("Launch filter", "Skip tokens that are mayhem, whose curve ever dropped under 25 SOL vSOL, or whose first 50 trades went above 200 SOL vSOL."),
 ("Envelope", "Inside the 3 bots' envelope only: token age ≤ 343.67 s, price drop ≥ 4.65%, last buy ≤ 3.869 s before the dump, dump ≥ 1.08 SOL."),
 ("Score", "42 features (section 4) → IMIT1 GBDT (400 trees). PICK when score ≥ <b>0.5419</b> (the model's top 2% = “strict”)."),
 ("Pick checks", "Same token: ≥ 5 slots since the last pick (spacing). Token kind: create_v2 only (legacy create skipped); vanilla or holder-reward (cashback, creator-fee, mayhem skipped). One open position at a time. No new buys after the kill switch, the run's buy cap or its time cap. Balance ≥ size + 0.03 SOL."),
 ("Guard + deadline", "min tokens out = the post-dump curve's quote for our spend ÷ <b>1.05</b> (pump error 6042 if the price is &gt; 5% higher when we execute). A Lighthouse <code>assertSysvarClock</code> instruction fails the tx if it lands after <b>dump slot + 1</b> (error 6001)."),
 ("Send", "Pre-built, pre-signed v0 tx (tip transfers, CU limit 100,000, CU price 5,000,000 µL/CU, create ATA, guard, <code>buy_exact_quote_in_v3</code> 0.25 SOL) written on the engine's own warm HTTP/UDP connections to the <b>two fastest paths for the slot's leader client</b> (section 5). Decision → first write measured 0.7–1.7 ms."),
 ("Land", "Our TradeEvent on the executed feed (or the RPC land poll) opens the position at the real token count and cost."),
 ("Exit", "After every later trade on the token: value = curve sell-out of our tokens after fees vs cost. ≥ +5% → sell (take-profit); ≤ −10% → sell (stop-loss); else sell when the slot reaches landing + 5 (lands at +6 ≈ 1.3 s). Wall-clock backstop: 6 × 400 ms + 3 s after the fire."),
 ("Sell", "<code>sell_v3</code> all tokens + close the token account (rent back), to the staked RPC and Nozomi together (one signature), retried each second until a confirmed zero balance, 30 s deadline."),
 ("Record + report", "JSONL per event (dump, pick, fire with decision breakdown, buy_land, exit, sell_land, tape of every trade while we hold, close, timing). <code>report_run.py</code> turns it into the per-trade report with chain P&L."),
]
S.append(table(["#", "step", "exactly"], [[str(i), f"<b>{esc(a)}</b>", b] for i, (a, b) in enumerate(steps, 1)]))

# 4
h2("Selection: IMIT1 (frozen)", 4)
box('''<b>Label:</b> HkQ7hMjy or DYXDDrZC or haqqiUUX buys within 1000 ms after the dump (before the next big sell).
<b>Data:</b> collector runs 10-22 03:08 → 10-23 18:19 PKT. <b>Train:</b> dumps before 10-23 06:00 PKT (fit first 80%, early stop on the last 20%).
<b>Test:</b> 12.3 h after it, never seen. <b>Model:</b> numpy GBDT, 400 trees, learning rate 0.05, histogram bins (<code>edges</code>), file
<code>ops/overnight/sel/IMIT1.json</code>. <b>Cohort:</b> 462 consistently profitable wallets taken from TRAIN hours only (<code>cohort_train.json</code>).
<b>Thresholds:</b> strict (top 2%) 0.5419 — <b>live</b>; wider (top 4%) 0.2109; top 8% −0.1868. <b>AUC on TEST:</b> 0.83.''')
feat = [("age", "token age at the dump, s"), ("sell", "dump size, SOL"), ("drop_pct", "price drop of the dump, %"), ("vsol", "curve vSOL after the dump"),
 ("pb", "price after / price at the end of the glued bundle"), ("dd", "price after / running peak"), ("nb, ns", "buys / sells before the dump"),
 ("b20, s20, u20", "SOL bought / sold, unique buyers in the last 20 slots"), ("dev", "SOL bought in the glued bundle"), ("glued", "glued bundle buys"),
 ("first_big", "1 if no earlier big sell"), ("ins", "1 if the seller is an insider"), ("s_frac", "share of the seller's holding sold (≤ 2)"),
 ("s_pnl", "seller's SOL out − SOL in"), ("s_nb", "seller's buys"), ("s_entry", "seller's first buy slot − launch slot"), ("n_big", "earlier big sells"),
 ("since_big", "slots since the last big sell"), ("ret5, ret20", "price change over 5 / 20 slots before"), ("peak_mult", "running peak / bundle price"),
 ("b3, nb3", "SOL bought / buys in the last 3 slots"), ("sellers20", "unique sellers in 20 slots"), ("uniq_buyers", "unique buyers so far"),
 ("ins_sold", "insiders' tokens sold / bought"), ("net_flow", "SOL bought − sold so far"), ("slotpos", "dump's index / block size"),
 ("prev_sell_ms", "ms since the previous big sell"), ("n_tr", "trades so far"), ("vmax", "max vSOL so far"), ("since_buy", "s since the last buy"),
 ("tgt_n, tgt_since", "the 3 bots' earlier dip buys on this token / s since"), ("coh_n, coh_20", "cohort buyers so far / in the last 20 slots"),
 ("coh_seller", "1 if the seller is in the cohort"), ("coh_sol", "SOL the cohort bought"), ("coh_held", "cohort buyers still holding")]
S.append(table(["feature(s)", "meaning (src/dip_imit.rs features(); same code as the Python study)"], [[f"<code>{esc(a)}</code>", esc(b)] for a, b in feat]))
p("<b>Checks that it is the same model live:</b> Rust port vs Python on 2,097 events: 0 feature / score / event / label mismatches; live trade-by-trade book = batch (0 diffs); "
  "shadow engine vs paper over 16 min: 12 of 12 picks with identical scores (max diff 0.0004).")
h3("Backtest (TEST, 12.3 h, never seen; ops/overnight/sel/SELECTION.md)")
S.append(table(["tier", "picks/h", "win 35 / 50 / 75 ms", "P&L 35 / 50 / 75 ms (0.5 SOL, real follower limits)"], [
    ["strict (top 2%) — live", "14.6", "89% / 85% / 83%", f"{sol(4.34, 2)} / {sol(2.91, 2)} / {sol(1.77, 2)}"],
    ["wider (top 4%)", "33", "73% / 69% / 66%", f"{sol(6.72, 2)} / {sol(4.75, 2)} / {sol(3.04, 2)}"]]))
p(f"Stress: if the 3 imitated wallets never buy after us, TEST keeps 81–84% of the profit. Rule searches for “we win” (instead of imitation) overfit: TEST win 43–61%.")
h3("At OUR real landing (realat3.py: 407 wider TEST picks, 0.25 SOL, TP +5% / SL −10% / 1.3 s, guard 5% not yet: 2%)")
S.append(table(["we land", "35 ms", "50 ms", "75 ms", "100 ms", "110 ms", "125 ms", "150 ms"], [["P&L (SOL)"] + [sol(x, 3) for x in (3.671, 2.535, 1.609, 0.647, 0.496, 0.409, 0.128)],
    ["fills of 407", "221", "159", "119", "88", "82", "73", "60"]]))

# 5
h2("Execution: buy, guard, routes", 5)
S.append(table(["item", "value", "why"], [
 ["size", "0.25 SOL per buy (runs 1–2)", "owner's staged proof; backtest sweet spot is 1 SOL, 2 SOL adds little"],
 ["instruction", "<code>buy_exact_quote_in_v3</code> (17 accounts, buyback fee recipient from the create tx or the known pool vault A7hAgCzF…)", "works for vanilla and holder-reward (flag-agnostic, verified)"],
 ["price guard", "min out = quote ÷ 1.05", "2% blocked 13 of 14 FRZ buys; 5% ≥ 2% at every speed in the backtest; 10–20% lose (section 11)"],
 ["slot deadline", "Lighthouse assertSysvarClock: land by dump slot + 1", "no buys long after the dump"],
 ["compute", "CU limit 100,000 (a buy uses ~78,000); CU price 5,000,000 µL/CU = 0.0005 SOL", "already above ~85% of the bots that beat us (section 10)"],
 ["tips", "0.001 SOL per path, 2 paths (3 when the leader changes at the slot edge); refunded when the buy fails", "providers' minimums"],
 ["fast path", "prebuilt template, presigned nonce, own HTTP/1.1 / HTTP/2 / UDP connections, prewarmed", "decision → first write 0.7–1.7 ms"],
 ["token kinds", "create_v2 vanilla + holder-reward (<code>--dip-allow-holder</code>)", "holder-reward = ~half of all picks; buy+sell simulated OK"]]))
h3("Routes v3 (two fastest paths per leader client; probe D, nearby leaders, 70 probes)")
S.append(table(["leader client", "paths", "probe D: fire → our tx seen (median ms, n)"], [
 ["BAM", "Nozomi + Bolt", "Nozomi 24 (2) · Bolt 30 (5) · LandX 30 (2) · Helius 38 (2)"], ["Firedancer", "Nozomi + LandX", "LandX 20 (2) · Nozomi 28 (3) · Helius 123 (2)"],
 ["Harmonic", "Nozomi + Helius", "Nozomi 31 (3) · Helius 34 (3) · LandX 35 (4)"], ["Jito", "Bolt + Astralane", "Bolt 37 (2) · Astralane 43 (2) · Helius 65 (2)"],
 ["Agave / other / unknown", "Nozomi + Helius / Nozomi + Bolt", "–"]]))

# 6
h2("Exit and sell", 6)
ul(["<b>Take-profit +5% / stop-loss −10%</b>, checked after every trade on the token from the executed feed (value = curve sell-out of our tokens, after pump fees, vs our cost incl. 0.0008 per tx).",
    "<b>Time limit 6 slots (~1.3 s):</b> the sell is sent one slot before, when slot ≥ landing + 5. Taken from HkQ7hMjy's own timer: it sells 25–35% of open trips at slot 6, never before slot 3.",
    "<b>Why not longer:</b> on the 12.3 h TEST the 192-exit grid is flat around +6.6…+7.0 and longer holds earn less; the live paper liked 6–12 s holds (no TP/SL 12 s +5.2 vs +2.2 at 0.5 SOL) but the backtest did not confirm it.",
    "<b>Sell:</b> <code>sell_v3</code> of all tokens + close the token account, sent to staked RPC and Nozomi together (audit rule M-5: every sell also via the fallback, 0.001 tip), retried every 1 s, until a <i>confirmed</i> zero balance; 30 s deadline then a background retry. Every run so far: 0 tokens left over."])

# 7
h2("Safety and operations", 7)
S.append(table(["control", "how"], [
 ["loss budget", "/root/prod/dip_budget.json: first start balance 3.957371 SOL; total loss across ALL dip runs ≤ 0.5 SOL; each run's kill switch = what is left (refused under 0.05)"],
 ["kill switch", "balance + open positions at cost polled every 2 s; below start − cap → no new buys, open positions still exit"],
 ["caps per run", "--max-buys (landed buys), --minutes, one open position, per-buy cap 1.05 × size"],
 ["stop", "Ctrl-c / SIGTERM / SIGHUP = no new buys, open positions finish, then the run ends (dip4+; checked live)"],
 ["one engine per server", "scripts refuse while any snipe_engine runs; the 24 h paper engine of the other strategy is stopped for live runs"],
 ["who starts PROD", "the owner, inside tmux, typing the keystore passphrase; the agent drives only the FRZ test wallet"],
 ["records", "/root/prod/runs/dip_rN.log + .jsonl; report: <code>python3 -I ops/dip/report_run.py dip_rN.jsonl 2g7r…</code>"]]))
S.append('<pre>ssh -p 1996 it@84.32.100.36\ntmux new -s dip\nsudo bash /root/prod/run_dip_prod.sh --run N --trades K --size 0.25    # + optional --guard 1.05 --tier strict --minutes 120</pre>')

# 8
h2("Live results", 8)
h3(f"PROD run 1 — 10-24 02:15–02:43 PKT — {len(R1)} attempts, {sum(r['filled'] for r in R1)} fills — chain {sol(tot1)} SOL — wallet {b1['start_balance'] / 1e9:.4f} → {b1.get('end_balance', 0) / 1e9:.4f}")
S.append(trade_table(R1)); S.append("<details><summary>missed buys (fee only)</summary>" + miss_table(R1) + "</details>")
h3(f"PROD run 2 — from 10-24 03:03 PKT{'' if r2_done else ' (in progress)'} — {len(R2)} attempts, {sum(r['filled'] for r in R2)} fills — chain {sol(tot2)} SOL" + (f" — wallet {b2['start_balance'] / 1e9:.4f} → {b2.get('end_balance', 0) / 1e9:.4f}" if b2.get("end_balance") else ""))
S.append(trade_table(R2)); S.append("<details><summary>missed buys (fee only)</summary>" + miss_table(R2) + "</details>")
h3("Before PROD: FRZ test wallet (0.02 SOL) and the paper run")
S.append(table(["test", "what", "result"], [
 ["FRZ test 1 (01:03–01:33)", "dip3, 2% guard, vanilla only: 14 picks, 7 skipped (holder-reward), 7 fires", f"1 fill (HehqjB: buy → stop-loss → sell in the same slot, curve +0.00001, chain {sol(-0.003594)} = fees), 6 guard blocks; total {sol(-0.006624)}"],
 ["FRZ test 2 (01:35–01:52)", "dip6, holder-reward on, 2% guard", f"5 fires, 0 fills (4 guard, 1 deadline); {sol(-0.002525)}; stop signal checked live"],
 ["landing probes A–D (01:58–03:00)", f"{sum(n_probes.values())} buys that cannot fill (min out = max): A {n_probes['A']}, B {n_probes['B']}, C {n_probes['C']}, D {n_probes['D']}", f"route study, section 9; fees {sol(-0.000505 * sum(n_probes.values()))} SOL (FRZ topped up 0.1 SOL from 2g by the owner)"],
 ["live paper (19:32–02:03, 0.5 SOL)", "274 picks, collector data, TP +8% / SL −5% / 1.3 s", f"{sol(3.67, 2)} at 35 ms (108/167 won), {sol(1.44, 2)} at 75 ms"]]))

# 9
h2("Landing speed", 9)
p(f"Our buys, ms after the dump on our own feed: nearby leaders (&lt; 50 ms RTT from Frankfurt) median <b>{med(land_near):.0f} ms</b> (n {len(land_near)}); far leaders median <b>{med(land_far):.0f} ms</b> (n {len(land_far)}). "
  "The fastest bots land 2–40 ms after the dump.")
h3("Probes by leader distance (A–C, 80 probes, block-position ms after the dump)")
by = collections.defaultdict(list)
for rtt, city, cl, ms, ds in prtt:
    b = "unknown" if rtt is None else "< 2 ms (Frankfurt)" if rtt < 2 else "2–12 ms (Europe)" if rtt < 12 else "12–50 ms" if rtt < 50 else "50–100 ms (US east)" if rtt < 100 else "> 100 ms (US west / Asia)"
    by[b].append((ms, ds))
S.append(table(["leader distance", "n", "median landing", "same slot as the dump"], [[k, str(len(v)), f"{med([x[0] for x in v]):.0f} ms", f"{sum(1 for x in v if x[1] == 0)} of {len(v)}"]
    for k, v in sorted(by.items(), key=lambda kv: ["< 2 ms (Frankfurt)", "2–12 ms (Europe)", "12–50 ms", "50–100 ms (US east)", "> 100 ms (US west / Asia)", "unknown"].index(kv[0]))], num=(1,)))
p("Leaders within 50 ms of our server: 405 of 661, holding 74% of this epoch's slots (/root/fix2/close_leaders_50ms.txt).")
h3("Probe D: seven paths rotated one per probe, nearby leaders only (fire → our tx seen back, ms)")
byp = collections.defaultdict(list)
for path, cl, t in probesD:
    if t.get("fire_to_seen_ms") is not None: byp[path].append(t["fire_to_seen_ms"])
S.append(table(["path", "probes", "median ms"], [[k, str(len(v)), f"{med(v):.0f}"] for k, v in sorted(byp.items(), key=lambda kv: med(kv[1]))], num=(1, 2)))
h3("Sessions A–C (all leaders; A = old routes, B = fast-bot paths, C = Astralane everywhere; block-position ms)")
byc = collections.defaultdict(list)
for r in pspeed:
    if r["ms"] is not None: byc[(r["label"], r["client"], r["paths"])].append(r["ms"])
S.append(table(["session", "leader client", "paths", "n", "median ms"], [[a, b, c, str(len(v)), f"{med(v):.0f}"] for (a, b, c), v in sorted(byc.items())], num=(3, 4)))
h3("Where the time goes (dip8 timing records)")
ul(["Executed feed vs first sighting on any feed: median 1.6 ms (p90 5.5 ms).", "Our decision, first sighting → buy written: 0.7–1.7 ms (queue 36–298 µs, book ~30 µs, score 65–844 µs, checks + logs 135–525 µs, build + sign 123–569 µs, write 74–160 µs).",
    "Send → our tx back on our feed: 24–50 ms by path on nearby leaders; the rest of the gap to the fastest bots is network position (they are co-located / pre-positioned).",
    "<b>Fee is not the lever:</b> on BAM the 16 buys that beat us within 60 ms paid median priority 0.00012 SOL (1.82M µL/CU, tight CU limits); we pay 0.0005 (5M µL/CU). Only whales pay more (85YwZaQa 0.035 SOL → 14.7 ms on Firedancer)."])

# 10
h2("Competitors and references", 10)
S.append(table(["wallet", "what we know (read-only, on chain)", "source"], [
 [gmw("HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "HkQ7hMjy"), f"24 h ledger: {sol(25.4, 1)} SOL/day; 1,821 buys (76/h), all 0.5 SOL, win 53%, mean +0.0145/trip, 21/24 PKT hours positive; buys a median 39 ms after the dump (p10 19, p90 80); profit by delay 0–25 ms +2.95, 25–50 +6.33, 50–75 +6.59, 75–100 +0.53, 100–150 −0.36 (33 h); never sells before slot 3, timer at slot 6; 0.000135 SOL/tx, no tip, Lighthouse guards", "ops/overnight/hkq7/, memory hkq7-dissection"],
 [gmw("haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq", "haqqiUUX"), f"24 h: curve trades {sol(28.1, 1)}, failed −0.04 → ≈ +28 SOL/day; 7,067 buys (295/h), size median 0.27, hold median 28 slots. Last 1,000 txs: <b>114 failed (11.4%)</b>, all pump 6042 like ours; trades through its <b>own program haqqqMGN…</b> (CPI into the same pump buy / sell_v3); paths Helius 25 / 40 (tips ~0.0002), 0slot 3, Astralane 1, rest no tip; CU price median 1.84M µL/CU; lands 21–60 ms after dumps on BAM", "ops/dip/speed/haqq_path.py, fast_bots_paths.py"],
 [gmw("DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "DYXDDrZC"), f"curve trades {sol(12.6, 1)} / 24 h but 42,972 failed attempts (−8.1 SOL) → ≈ +4.5 SOL/day on the curve; census net +18.2 / 33 h (948 trips, 43 ms); 23.6 ms via Astralane on Firedancer", "memory hkq7-dissection, dip-census"],
 ["fast bounce bots", "3Xti8uhq (4 ms), CVPz447t (6–16 ms), 9k78QZyw, 3MHgGwdL, A9KKBd (8.7 ms, Nozomi, Harmonic), 85YwZaQa (14.7 ms, 0.035 SOL priority, Firedancer), omegoMAe, FSz6mptA, EUkuD2J2 (Astralane), J3gZFpvs (16M µL/CU)", "FRZ / run tapes; fast_bots_paths.py"]]))
fb = [r for r in fast if r["ms"] <= 60]
S.append("<details><summary>every buy that beat or followed us in the FRZ tests (path, fee, landing)</summary>" + table(["leader", "ahead of us?", "wallet", "ms after dump", "priority SOL", "CU price", "tips"],
    [[r["client"], "ahead" if r["ahead"] else "after", gmw(next((k for k in TGT if k.startswith(r["user"])), r["user"]), r["user"]), f'{r["ms"]:.0f}', f'{r["prio_sol"]:.5f}', f'{r["cu_price"]:,}', esc(", ".join(f"{s} {x / 1e9:.4f}" for s, x in r["tips"]) or "none")] for r in sorted(fast, key=lambda r: (r["client"], r["ms"]))]) + "</details>")

# 11
h2("Considered and dismissed", 11)
S.append(table(["idea", "evidence", "decision"], [
 ["fixed 4-slot exit", "owner: the most profitable bots don't; HkQ7 timer at slot 6 + soft TP", "TP / SL / 6-slot time limit"],
 ["rule-based selection (search for “we win”)", "overfit: TEST win 43–61%", "imitation GBDT (IMIT1)"],
 ["guard 2%", "blocked 13 of 14 FRZ buys; 5% ≥ 2% at every speed (backtest)", "5% from run 1"],
 ["guard 10 / 15 / 20%", f"15 real blocked buys re-bought at our exact position: 5% {sol(-0.009, 3)}, 10% {sol(-0.057, 3)}, 15% {sol(-0.063, 3)}, 20% {sol(-0.079, 3)}; backtest at 110 ms: 5% {sol(0.543, 2)}, 15% {sol(-0.49, 2)}, 20% {sol(-1.136, 2)}", "keep 5%"],
 ["higher priority fee", "we already outbid ~85% of the bots that beat us; they arrive earlier", "keep 0.0005 SOL"],
 ["only nearby leaders", f"{len(far_fills)} of {len(fills) + 1} live fills were on far leaders: " + ", ".join(f"{r['m'][:6]} {esc(where(r['leader']))} " + sol(r['chain'], 3) for r in far_fills), "no gate in V1; multi-region later (owner)"],
 ["Astralane for every leader", "slow on Firedancer: 123–137 ms (probes B, C)", "Astralane only on Jito"],
 ["direct-to-leader TPU, Haan", "probe D: 50 ms and 49 ms vs Nozomi 30", "not used"],
 ["staked RPC on Harmonic", "69 ms vs Nozomi 50 ms (probes A / B)", "Nozomi + Helius"],
 ["cashback / creator-fee tokens", "our sell not verified on them", "skipped (holder-reward verified by simulation → traded)"],
 ["legacy create tokens", "our TOKEN-2022 accounts would fail", "skipped"],
 ["holds of 6–12 s", "live paper liked them, 12.3 h backtest did not", "1.3 s"],
 ["2 SOL size", "adds little over 1 SOL in the backtest (follower limits)", "scale 0.25 → 1 later"],
 ["earlier strategies", "same-slot launch sniping at our ~75 ms ≈ break-even (10-21 run 2 −0.084); FINAL-2 daytime −0.48; dev-exit, flow filters, after-sell-out, trend rule 3 (0 of ~12k exits positive), non-race strategies: no OOS edge; dev-list S4 on hold", "dip-backrun is the only one with a proven edge"]]))

# 12
h2("Caveats (exact)", 12)
our_miss = fire_n - fill_n
ul([f"<b>Our fail ratio is far above our competitors'.</b> PROD: {our_miss} of {fire_n} buy attempts missed ({100 * our_miss / max(1, fire_n):.0f}%: guard {sum(1 for r in ALL if not r['filled'] and '6042' in r['why'])}, deadline {sum(1 for r in ALL if not r['filled'] and '6001' in r['why'])}); "
    "FRZ: 11 of 12. haqqiUUX: 114 of its last 1,000 txs failed (11.4%; about 25% of its buy attempts, estimated from a 40-tx sample: 16 buys / 24 sells). DYXDDrZC: 42,972 failed attempts in 24 h.",
    f"<b>Speed gap:</b> we land {med(land_near):.0f} ms (nearby, median) / {med(land_far):.0f} ms (far) after the dump; the bounce bots 2–40 ms. We fill mostly when nobody bounces first.",
    f"<b>Tiny sample:</b> {fill_n} fills. The backtest at our real ~110 ms is thin: {sol(0.496, 3)} SOL per 12.3 h at 0.25 SOL (82 fills of 407 picks).",
    "<b>Profit depends on the bot cohort buying after us;</b> without it the same replay loses (−14.11 vs +18.07).",
    "<b>Costs per round trip:</b> buy fee 0.000505 + 2 tips 0.002 (3 when the leader changes) + sell fee 0.000605 + sell tip 0.001 + pump fees ~1.25% each way. At 0.25 SOL that is ~1.6% + 2.5%.",
    "<b>Model drift:</b> trained on 10-22/23 data; the 3 bots can change behaviour; no retraining loop yet.",
    "<b>One region (Frankfurt):</b> 26% of slots belong to leaders ≥ 50 ms away (167–195 ms landings).",
    "<b>Timing field bug:</b> dip8's PoH “leader clock” value is wrong (our entries feed skips most ticks) — ignore <code>land_ms_poh</code>; use <code>fire_to_seen_ms</code>.",
    "<b>Sizes above 0.25 SOL are untested live</b> (price impact on our own fill, follower limits)."])

# 13
h2("Recreate it", 13)
S.append('''<pre># host (development only here): /home/moiz/sniper
cargo build --release --bin snipe_engine                       # engine incl. --dip (src/bin/snipe_engine/dipmode.rs)
# model + cohort -> server
scp -P 1996 ops/overnight/sel/IMIT1.json ops/overnight/sel/cohort_train.json  it@84.32.100.36:/tmp/   # then sudo mv to /root/dip/
# engine -> server (never pipe-deploy and launch in one ssh)
ssh -p 1996 it@84.32.100.36 'sudo tee /root/sniper-dip/snipe_engine_dipN > /dev/null' < target/release/snipe_engine
# config: /root/sniper-dip/dip_probe.toml = dip_shadow.toml (feeds incl. [[feed]] kaldera-tx kind="yellowstone-tx",
#         token_env KALDERA_TOKEN, header x-token; [[send]] staked-rpc, helius, nozomi, astralane, landx-fra3, jito-bundle,
#         harmonic-bundle) + bolt + haan + tpu-direct; tokens only in /root/sniper/deploy/.env
# leader distances: /root/fix2/close5_new.py -> leader_rtt_new.json, close_leaders_50ms.txt
# test first on FRZ:   sudo bash /root/sniper-dip/run_dip_frz.sh frz_tN 2 30 strict 1.05
# landing probes:      sudo bash /root/sniper-dip/run_dip_probe.sh probeX 70 "<routes>" 5000000 "nozomi,bolt,..." /root/fix2/close_leaders_50ms.txt
# PROD (owner, tmux, passphrase):
sudo bash /root/prod/run_dip_prod.sh --run N --trades K --size 0.25
# engine flags used by run_dip_prod.sh:
#  --dip --live --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify --dip-tier strict --dip-allow-holder
#  --dip-tp 0.05 --dip-sl 0.10 --dip-hold-slots 6 --dip-guard 1.05 --dip-spacing-slots 5 --dip-model /root/dip/IMIT1.json
#  --dip-cohort /root/dip/cohort_train.json --spend-lamports 250000000 --max-sol 0.2625 --max-buys K --max-inflight 1
#  --max-loss-sol <budget left> --cu-limit 100000 --cu-price-micro 5000000 --sell-cu-limit 120000 --sell-cu-price-micro 5000000
#  --land-poll-ms 100 --land-timeout-ms 3000 --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi
#  --buy-max-slot-delta 1 --send-path helius --sell-path staked-rpc --no-union-harmonic --env-name PROD
#  --route-by-client "bam=nozomi+bolt;jito=bolt+astralane;harmonic=nozomi+helius;fd=nozomi+landx-fra3;agave=nozomi+helius;other=nozomi+bolt;default=nozomi+bolt"
# report
python3 -I ops/dip/report_run.py dip_rN.jsonl 2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE</pre>''')

# 14
h2("File and server map", 14)
S.append(table(["where", "what"], [
 ["src/bin/snipe_engine/dipmode.rs", "the dip engine loop: book, picks, guard, fire, exits, probes, timing records"], ["src/dip_imit.rs", "IMIT1 port: structure, dump rules, launch filter, 42 features, GBDT, live TokenBook, parity tests"],
 ["src/dip.rs, src/feeds/{mod,grpc}.rs", "TradeEvent / CreateEvent decode; executed-feed info on every arrival"], ["src/bin/snipe_engine.rs", "shared engine: FAST send path (prepare / prepare_on / fire), sells, accounting, kill switch, --simulate --sim-roundtrip"],
 ["ops/prod/run_dip_prod.sh, run_dip_frz.sh, run_dip_probe.sh, transfer_prod.sh", "run scripts (copies on the server under /root/prod and /root/sniper-dip)"], ["ops/dip/report_run.py", "per-run report with chain P&L"],
 ["ops/dip/speed/*.py", "landing studies: dip_speed, probe_speed, probe_timing, fast_bots_paths, guard_whatif, haqq_path"], ["ops/overnight/sel/", "selection study: IMIT1.json, cohort_train.json, SELECTION.md, realat*.py, live_sim.py"],
 ["ops/dip/PLAN.md", "chronological log of the build and every decision"], ["/root/prod/runs/dip_rN.{log,jsonl}", "PROD run records"], ["/root/prod/dip_budget.json", "loss budget across runs"],
 ["server", "Cherry Servers, Frankfurt — ssh -p 1996 it@84.32.100.36"], ["wallets", f"PROD {gmw(PROD, PROD)} · test {gmw(FRZ, FRZ)}"]]))

CSS = """*{box-sizing:border-box}body{background:#fff;color:#000;font:15px/1.5 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0 auto;padding:16px;max-width:1180px}
h1{font-size:24px;border:4px solid #000;padding:12px 14px;margin:0 0 12px;letter-spacing:.5px}
h2{font-size:18px;background:#000;color:#fff;padding:7px 10px;margin:30px 0 10px}h3{font-size:15.5px;border-bottom:3px solid #000;padding-bottom:2px;margin:20px 0 8px}
.meta,.box,.toc{border:2px solid #000;padding:10px 12px;margin:10px 0}.toc a{color:#000}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:8px;margin:12px 0}.kpi{border:3px solid #000;padding:8px 10px}.kpi span{font-size:12px;text-transform:uppercase}.kpi b{display:block;font-size:19px;margin-top:2px}
.wrap{overflow-x:auto;margin:8px 0}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:2px solid #000;padding:4px 6px;text-align:left;vertical-align:top}th{background:#000;color:#fff;font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}.pos{color:#0a7a2f;font-weight:700}.neg{color:#c4161c;font-weight:700}
code{background:#eee;padding:0 3px;font-size:12.5px}pre{border:2px solid #000;padding:10px;overflow-x:auto;background:#f6f6f6;font-size:12px}
a{color:#000}details{margin:6px 0}summary{cursor:pointer;font-weight:600}ul{padding-left:20px}li{margin:3px 0}
@media (max-width:600px){body{padding:12px}h1{font-size:19px}}"""
doc = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dip Model Blueprint</title><style>{CSS}</style></head><body>{"".join(S)}</body></html>'
open(OUT, "w").write(doc)
print(f"wrote {OUT} ({len(doc) / 1e3:.0f} KB): fires {fire_n}, fills {fill_n}, wins {len(wins)}, P&L {pnl_total:+.6f}, run 2 {'done' if r2_done else 'in progress'}")
