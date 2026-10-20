# Build the what-if report page (static HTML + a small size/fee selector) from sim_window.py output.
# usage: python3 make_report.py <sim.json> <out.html> "<run label>" <sol_usd>
import sys, json, html, time

D = json.load(open(sys.argv[1])); OUT = sys.argv[2]; LABEL = sys.argv[3]; USD = float(sys.argv[4])
rows = D["rows"]
fired = [r for r in rows if r["fired"]]
others = [r for r in rows if not r["fired"]]

# live max-inflight 2: a position is open from its create slot S to ~S+4 (buy in S, sell lands ~S+4)
for r in fired:
    open_ = [o for o in fired if o is not r and o["S"] <= r["S"] <= o["S"] + 4 and o["S"] < r["S"]]
    r["overlap"] = len(open_) >= 2

slim = []
for r in rows:
    k5 = str(r["k5"])
    slim.append(dict(
        mint=r["mint"], name=(r.get("name") or "")[:28], sym=(r.get("symbol") or "")[:12], t=r.get("block_time"), fired=r["fired"], engine=r["engine"],
        dev=round(r["dev"], 2), bundle=round(r["gsol"], 2), rule2=r["rule2"], client=r.get("leader_client") or "?", rtt=r.get("leader_rtt"),
        city=r.get("leader_city") or "?", outS=r["outside_buys_S"], peak5=round(r["peak5"], 3), low5=round(r["low5"], 3), peak60=round(r["peak60"], 3),
        k5=r["k5"], overlap=r.get("overlap", False),
        sim={key: dict(fill=round(v["fill_x"], 3), n3=round(v["out"]["3"]["pnl"], 4), n3px=round(v["out"]["3"]["px"], 3),
                       s5=round(v["out"][k5]["pnl"], 4), s5px=round(v["out"][k5]["px"], 3),
                       extra={k: round(o["pnl"], 4) for k, o in v["out"].items()}) for key, v in r["sim"].items()},
        real={key: dict(n3=round(v["out"]["3"]["pnl"], 4), s5=round(v["out"][k5]["pnl"], 4)) for key, v in r["sim_real"].items()}))

sizes = D["sizes"]; fees = D["fees"]
t0 = min([r["block_time"] for r in rows if r.get("block_time")] or [0]); t1 = max([r["block_time"] for r in rows if r.get("block_time")] or [0])
span = f"{time.strftime('%H:%M', time.gmtime(t0))}–{time.strftime('%H:%M', time.gmtime(t1))} UTC" if t0 else "?"
data_js = json.dumps(dict(rows=slim, sizes=sizes, fees=fees, usd=USD))

page = """<title>Dry-Run What-If</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* layout: controls + totals on top, the fired-token table as the spine, skipped launches below */
:root { --bg:#f5f6f8; --panel:#fff; --fg:#141b24; --muted:#5c6876; --line:#dfe3e9; --accent:#0d6b86;
  --pos:#1b7a46; --pos-bg:#e3f4ea; --neg:#b3261e; --neg-bg:#fbe7e5; --warn:#8a5a00; --warn-bg:#fbefd5;
  --display:"Archivo","Helvetica Neue",Arial,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0e1319; --panel:#151c24; --fg:#e4e9ef; --muted:#97a3b2; --line:#29323d;
  --accent:#5cc2de; --pos:#6fd39f; --pos-bg:#15352a; --neg:#ff8a80; --neg-bg:#3a1a18; --warn:#f0c46a; --warn-bg:#3a2d10; color-scheme:dark } }
:root[data-theme="dark"] { --bg:#0e1319; --panel:#151c24; --fg:#e4e9ef; --muted:#97a3b2; --line:#29323d;
  --accent:#5cc2de; --pos:#6fd39f; --pos-bg:#15352a; --neg:#ff8a80; --neg-bg:#3a1a18; --warn:#f0c46a; --warn-bg:#3a2d10; color-scheme:dark }
body { background:var(--bg); color:var(--fg); font-family:var(--display); font-size:14.5px; line-height:1.5; }
.page { max-width:1180px; margin:0 auto; padding-block:24px 60px; padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); display:grid; gap:22px; }
.eyebrow { font-family:var(--mono); font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }
h1 { font-size:clamp(24px,4vw,32px); margin:4px 0 6px; font-weight:800; text-wrap:balance; }
h2 { font-size:19px; margin:0 0 8px; font-weight:700; }
p { margin:0; max-width:80ch; } .muted { color:var(--muted); }
.controls { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:center; }
.controls label { font-size:13px; color:var(--muted); display:flex; gap:8px; align-items:center; }
select { font:inherit; font-family:var(--mono); padding:5px 8px; border-radius:6px; border:1px solid var(--line); background:var(--panel); color:var(--fg); }
select:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.totals { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; display:grid; gap:4px; min-width:0; }
.card .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; }
.card .v { font-family:var(--mono); font-size:22px; font-variant-numeric:tabular-nums; }
.card .s { font-family:var(--mono); font-size:12.5px; color:var(--muted); }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:4px 0; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th, td { padding:7px 9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; white-space:nowrap; }
thead th { font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--panel); }
td.n { font-family:var(--mono); font-variant-numeric:tabular-nums; text-align:right; }
.pos { color:var(--pos); } .neg { color:var(--neg); }
.chip { display:inline-block; font-size:11px; font-weight:600; padding:1px 7px; border-radius:999px; }
.chip.warn { color:var(--warn); background:var(--warn-bg); } .chip.neg { color:var(--neg); background:var(--neg-bg); } .chip.pos { color:var(--pos); background:var(--pos-bg); }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.matrix td, .matrix th { text-align:right; } .matrix th:first-child, .matrix td:first-child { text-align:left; }
ul.notes { margin:0; padding-left:18px; display:grid; gap:5px; max-width:85ch; color:var(--muted); font-size:13px; }
code { font-family:var(--mono); font-size:12.5px; }
</style>
<div class="page">
<header>
  <div class="eyebrow">Sniper · what-if on a 1-hour dry run · """ + html.escape(LABEL) + """</div>
  <h1>Dry-Run What-If</h1>
  <p class="muted">Every token the engine fired on (the exact live selection), simulated as a buy right after the creator's bundle and a full sell at n+3 slots and at 5 s. Window """ + span + """.</p>
</header>

<section class="controls" aria-label="Simulation settings">
  <label for="size">Buy size <select id="size"></select></label>
  <label for="fee">Landing fee <select id="fee"></select></label>
  <span class="muted" style="font-size:13px">SOL = $""" + f"{USD:.2f}" + """</span>
</section>

<section class="totals" id="totals"></section>

<section>
  <h2>All sizes and fees (fired tokens)</h2>
  <div class="panel scroll"><table class="matrix" id="matrix"></table></div>
</section>

<section>
  <h2>Fired tokens (what live would have bought)</h2>
  <div class="panel scroll"><table id="fired"></table></div>
</section>

<section>
  <h2>Skipped rule-#2 neighbours (for optimization only)</h2>
  <p class="muted" style="margin-bottom:8px">Launches with a Lunar tip and a 2–9.5 SOL creator bundle that our gates did not fire on, with the engine's reason. Same simulation; not part of the totals above.</p>
  <div class="panel scroll"><table id="others"></table></div>
</section>

<section>
  <h2>How it was simulated</h2>
  <ul class="notes">
    <li><b>Entry</b>: our buy is inserted right after the creator's glued bundle in the create slot, ahead of every outside buyer (an ideal landing). Our own buy moves the price (the "fill" column, x the post-bundle price).</li>
    <li><b>Exits</b>: everything is sold against the curve state at the end of slot n+3 (n = the create slot), or at the end of the slot 5 s later (23 slots at the measured ~216 ms/slot). Every other trade is replayed in its real order; our tokens change their fills.</li>
    <li><b>Costs</b>: pump fee on both sides (from the trade events, 1.25%), the landing fee (3% or 4% of size, priority + tips), 0.0005 SOL sell fee. Absolute PnL = SOL back − size − all fees.</li>
    <li><b>Realistic landing</b>: the "at our real landing" card puts the same buy after the first 100 txs of the create slot, where our live buys have actually landed.</li>
    <li><b>Live differences</b>: live holds at most 2 positions; a token marked "2 open" would have been skipped. Live also stops at −0.5 SOL or on the profit lock; the running total shows where.</li>
    <li><b>Recording</b>: every token's full trade history (exact order to S+30, every trade to 60 s) is saved on the server under <code>/root/sim/rec_*</code> and on the host under <code>~/sniper-data/sim/</code>, so any size, fee or exit can be re-run.</li>
  </ul>
</section>
</div>
<script>
const D = """ + data_js + """;
const $ = s => document.querySelector(s);
const fmt = (x, d = 3) => (x > 0 ? "+" : "") + x.toFixed(d);
const cls = x => x > 0 ? "pos" : (x < 0 ? "neg" : "");
const t = s => s ? new Date(s * 1000).toISOString().slice(11, 19) : "?";
const tok = r => `<a href="https://gmgn.ai/sol/token/${r.mint}" target="_blank" rel="noopener">${(r.sym || r.mint.slice(0, 6))}</a>`;
for (const s of D.sizes) $("#size").insertAdjacentHTML("beforeend", `<option value="${s}">${s} SOL</option>`);
for (const f of D.fees) $("#fee").insertAdjacentHTML("beforeend", `<option value="${f}">${f}%</option>`);
function key() { return `${+$("#size").value}|${+$("#fee").value}`; }
function render() {
  const k = key(), F = D.rows.filter(r => r.fired), O = D.rows.filter(r => !r.fired);
  const sum = (arr, f) => arr.reduce((a, r) => a + (r.sim[k] ? f(r) : 0), 0);
  const n3 = sum(F, r => r.sim[k].n3), s5 = sum(F, r => r.sim[k].s5);
  const w3 = F.filter(r => r.sim[k] && r.sim[k].n3 > 0).length, w5 = F.filter(r => r.sim[k] && r.sim[k].s5 > 0).length;
  const rn3 = F.reduce((a, r) => a + (r.real[k] ? r.real[k].n3 : 0), 0), rs5 = F.reduce((a, r) => a + (r.real[k] ? r.real[k].s5 : 0), 0);
  $("#totals").innerHTML = `
    <div class="card"><span class="k">Sell at n+3 slots</span><span class="v ${cls(n3)}">${fmt(n3)} SOL</span><span class="s">${fmt(n3 * D.usd, 0)} USD · ${w3}/${F.length} winners</span></div>
    <div class="card"><span class="k">Sell at 5 s</span><span class="v ${cls(s5)}">${fmt(s5)} SOL</span><span class="s">${fmt(s5 * D.usd, 0)} USD · ${w5}/${F.length} winners</span></div>
    <div class="card"><span class="k">At our real landing (+100 txs)</span><span class="v ${cls(rn3)}">${fmt(rn3)} SOL</span><span class="s">n+3 · 5 s ${fmt(rs5)} SOL</span></div>
    <div class="card"><span class="k">Fired tokens</span><span class="v">${F.length}</span><span class="s">${F.filter(r => r.overlap).length} would hit the 2-position limit live</span></div>`;
  let m = "<thead><tr><th>Size · fee</th><th>n+3 total SOL</th><th>n+3 wins</th><th>5 s total SOL</th><th>5 s wins</th></tr></thead><tbody>";
  for (const s of D.sizes) for (const f of D.fees) {
    const kk = `${s}|${f}`;
    const a = F.reduce((x, r) => x + (r.sim[kk] ? r.sim[kk].n3 : 0), 0), b = F.reduce((x, r) => x + (r.sim[kk] ? r.sim[kk].s5 : 0), 0);
    const wa = F.filter(r => r.sim[kk] && r.sim[kk].n3 > 0).length, wb = F.filter(r => r.sim[kk] && r.sim[kk].s5 > 0).length;
    m += `<tr${kk === k ? ' style="font-weight:700"' : ""}><td>${s} SOL · ${f}%</td><td class="n ${cls(a)}">${fmt(a)}</td><td class="n">${wa}/${F.length}</td><td class="n ${cls(b)}">${fmt(b)}</td><td class="n">${wb}/${F.length}</td></tr>`;
  }
  $("#matrix").innerHTML = m + "</tbody>";
  const head = live => `<thead><tr><th>Time</th><th>Token</th><th>Dev</th><th>Bundle</th><th>Leader</th><th>Outside buys in S</th><th>Fill</th><th>n+3 price</th><th>n+3 PnL SOL</th><th>5 s price</th><th>5 s PnL SOL</th><th>Peak 5 s</th><th>Low 5 s</th><th>Peak 60 s</th>${live ? "<th>Running n+3</th><th>Running 5 s</th><th>Live</th>" : "<th>Why skipped</th>"}</tr></thead>`;
  let run3 = 0, run5 = 0, body = "";
  for (const r of F) {
    const s = r.sim[k]; if (!s) continue; run3 += s.n3; run5 += s.s5;
    body += `<tr><td>${t(r.t)}</td><td>${tok(r)}</td><td class="n">${r.dev}</td><td class="n">${r.bundle}</td><td>${r.client} ${r.rtt == null ? "" : r.rtt.toFixed(1) + " ms"}</td><td class="n">${r.outS}</td>
      <td class="n">${s.fill.toFixed(2)}x</td><td class="n">${s.n3px.toFixed(2)}x</td><td class="n ${cls(s.n3)}">${fmt(s.n3)}</td><td class="n">${s.s5px.toFixed(2)}x</td><td class="n ${cls(s.s5)}">${fmt(s.s5)}</td>
      <td class="n">${r.peak5.toFixed(2)}x</td><td class="n">${r.low5.toFixed(2)}x</td><td class="n">${r.peak60.toFixed(2)}x</td>
      <td class="n ${cls(run3)}">${fmt(run3)}</td><td class="n ${cls(run5)}">${fmt(run5)}</td><td>${r.overlap ? '<span class="chip warn">2 open</span>' : ""}</td></tr>`;
  }
  $("#fired").innerHTML = head(true) + "<tbody>" + (body || `<tr><td colspan="17" class="muted">No fires in this window.</td></tr>`) + "</tbody>";
  let ob = "";
  for (const r of O) {
    const s = r.sim[k]; if (!s) continue;
    ob += `<tr><td>${t(r.t)}</td><td>${tok(r)}</td><td class="n">${r.dev}</td><td class="n">${r.bundle}</td><td>${r.client} ${r.rtt == null ? "" : r.rtt.toFixed(1) + " ms"}</td><td class="n">${r.outS}</td>
      <td class="n">${s.fill.toFixed(2)}x</td><td class="n">${s.n3px.toFixed(2)}x</td><td class="n ${cls(s.n3)}">${fmt(s.n3)}</td><td class="n">${s.s5px.toFixed(2)}x</td><td class="n ${cls(s.s5)}">${fmt(s.s5)}</td>
      <td class="n">${r.peak5.toFixed(2)}x</td><td class="n">${r.low5.toFixed(2)}x</td><td class="n">${r.peak60.toFixed(2)}x</td><td class="muted">${r.engine}</td></tr>`;
  }
  $("#others").innerHTML = head(false) + "<tbody>" + (ob || `<tr><td colspan="15" class="muted">None recorded.</td></tr>`) + "</tbody>";
}
try { const p = JSON.parse(localStorage.getItem("whatif-sel") || "null"); if (p) { $("#size").value = p.s; $("#fee").value = p.f; } } catch (e) {}
$("#size").addEventListener("change", () => { try { localStorage.setItem("whatif-sel", JSON.stringify({ s: $("#size").value, f: $("#fee").value })); } catch (e) {} render(); });
$("#fee").addEventListener("change", () => { try { localStorage.setItem("whatif-sel", JSON.stringify({ s: $("#size").value, f: $("#fee").value })); } catch (e) {} render(); });
render();
</script>
"""
open(OUT, "w").write(page)
print("wrote", OUT, len(page), "bytes;", len(fired), "fired,", len(others), "others")
