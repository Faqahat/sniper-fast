#!/usr/bin/env python3
"""Long run report: one HTML page from the stage outputs (bots.json, operators.json, leaders-report.json, ours.json,
ours.jsonl, bundles.json) plus the hand-written findings (findings.html). usage: report.py <out.html> <run label>"""
import json, sys, os, html, collections

OUT, LABEL = sys.argv[1], sys.argv[2]
ld = lambda f, d=None: json.load(open(f)) if os.path.exists(f) else d
bots = ld("bots.json", {}); ops = ld("operators.json", {}); lr = ld("leaders-report.json", {}); ours = ld("ours.json", {})
bund = ld("bundles.json", {}); extra = ld("extra.json", {}); rbl = ld("race-by-leader.json", {}); plat = ld("platforms.json", {})
ours_rows = [json.loads(l) for l in open("ours.jsonl")] if os.path.exists("ours.jsonl") else []
findings = open("findings.html").read() if os.path.exists("findings.html") else "<p>Findings are written once the run ends.</p>"
E = html.escape
short = lambda k: (k or "?")[:8]
def num(x, d=0):
    if x is None: return "–"
    if isinstance(x, float): return f"{x:,.{d}f}"
    return f"{x:,}" if isinstance(x, int) else E(str(x))

def table(cols, rows, cls=""):
    h = "".join(f"<th>{E(c)}</th>" for c in cols)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

def bars(items, unit="%", maxv=None, pair=None):
    """horizontal bars; items = [(label, value, value2?)]: value2 drawn as a thin base-rate marker"""
    if not items: return ""
    m = maxv or max(max(v for _, v, *_ in items), max((x[2] for x in items if len(x) > 2 and x[2] is not None), default=0)) or 1
    rows = []
    for it in items:
        lab, v = it[0], it[1]; b = it[2] if len(it) > 2 else None
        w = 100 * v / m
        mk = f'<span class="base" style="left:{100 * b / m:.1f}%" title="base {b}{unit}"></span>' if b is not None else ""
        rows.append(f'<div class="bar"><span class="bl">{E(str(lab))}</span><span class="bt"><span class="bf" style="width:{w:.1f}%"></span>{mk}</span><span class="bv">{num(v, 1)}{unit}{f" <em>vs {num(b, 1)}{unit}</em>" if b is not None else ""}</span></div>')
    return '<div class="bars">' + "".join(rows) + "</div>"

# ---------------------------------------------------------------- sections
S = []
# our trades
if ours:
    v = ours.get("verdicts", {})
    tiles = [("trades", ours["trades"]), ("landed", ours["landed"]), ("wins", ours["wins"]),
             ("trading profit (wins)", f'{ours.get("trade_profit_lamports", ours["profit_lamports"]) / 1e9:.6f} SOL'), ("fees, all trades", f'{ours["fees_lamports"] / 1e9:.4f} SOL'),
             ("rent parked (refundable)", f'{ours.get("rent_parked_lamports", 0) / 1e9:.5f} SOL')]
    S.append(("ours", "Our trades", "".join(f'<div class="tile"><b>{num(b)}</b><span>{E(a)}</span></div>' for a, b in tiles).join(['<div class="tiles">', '</div>'])
        + "<h3>Why each trade won or lost</h3>" + bars([(k, 100 * n / max(1, ours["trades"])) for k, n in sorted(v.items(), key=lambda x: -x[1])])
        + "<p class='note'>phantom: the trigger itself failed on chain, so there was no gap. taken: another bot moved the pool first. gone: nobody visible took it, but the price was no longer there for us.</p>"
        + "<h3>The path race: whose copy the leader took first</h3>"
        + table(["path", "first to land", "ms after trigger p10", "p50"], [[E(p), num(n), num((ours["race_ms_by_path"].get(p) or {}).get("p10")), num((ours["race_ms_by_path"].get(p) or {}).get("p50"))] for p, n in ours["race_first_landed_by_path"].items()])
        + "<h3>Trade arms</h3>" + table(["arm (paths / fee)", "trades", "landed", "wins", "ms after trigger p50", "fee p50"],
            [[E(k), num(x["n"]), num(x["landed"]), num(x["wins"]), num(x["ms_p50"]), num(x["fee_p50"])] for k, x in sorted(ours["by_arm"].items())])
        + "<h3>Who took our gaps</h3>" + table(["taker", "times"], [[f"<code>{E(short(k))}</code>", num(n)] for k, n in ours["takers"].items()])
        + f'<p>Takers moved the pool p10/p50/p90 {" / ".join(num(x, 1) for x in ours["taker_ms_p10_p50_p90"])} ms after the trigger; our landed copies ran p10/p50/p90 {" / ".join(num(x, 1) for x in ours["ours_ms_all_p10_p50_p90"])} ms after it.</p>'))

# the field
W = sorted(bots.values(), key=lambda b: -b["profit_sol"])
if W:
    rows = []
    for b in W[:40]:
        ms = b["win_ms_p10_p50_p90"]
        rows.append([f'<code>{E(short(b["signer"]))}</code>', E(b["kind"]), num(b["wins"]), num(b["with_result"]), f'{b["profit_sol"]:.4f}',
            num(ms[1], 1) if ms[1] is not None else "–", num(b["same_slot_wins"]), num((b["prio_share_of_gross_p10_p50_p90"] or [None, None])[1], 2),
            f'{num(b["win_cu_price_p50"])} / {num(b["fail_cu_price_p50"])}', f'{b["nonce_pct"]}%', f'{b["tipless_pct"]}%',
            E(", ".join(f"{k} {v}" for k, v in list(b["senders"].items())[:4])), E("/".join(str(x) for x in b["copies_per_trigger_p50_p90"])),
            E(", ".join(list(b["venues"])[:3]))])
    S.append(("field", "The field: every arbitrage bot we saw", f'<p>{len(bots)} bots ({sum(1 for b in W if b["kind"] == "winner")} winning, the rest spraying), ranked by profit over the run.</p>'
        + table(["bot", "kind", "wins", "results", "profit SOL", "win ms p50", "same-slot wins", "priority / gross p50", "µlam/CU win / miss", "nonce", "no tip", "senders (tips)", "copies / trigger p50/p90", "venues"], rows, "dense")))
    opsrows = [[f'<code>{E(short(k))}</code>', num(len(v["signers"])), num(v["wins"]), num(v["n"]), f'{v["profit_sol"]:.4f}', E(", ".join(short(s) for s in v["signers"][:6]))] for k, v in list(ops.items())[:20]]
    S.append(("ops", "Operators: bots sharing a program", table(["program", "wallets", "wins", "transactions", "profit SOL", "wallets"], opsrows)))

# leaders
if lr:
    parts = []
    for d, title in (("rtt", "Leader distance from Cherry"), ("client", "Leader client"), ("jito", "Jito / BAM"), ("dz", "DoubleZero"), ("country", "Country")):
        allw = (lr.get("wins_by", {}).get("ALL") or {}).get(d) or {}
        items = [(k, x["wins_pct"], x["base_pct"]) for k, x in list(allw.items())[:8]]
        msd = lr.get("win_ms_by", {}).get(d, {})
        parts.append(f"<div class='panel'><h3>{E(title)}</h3>" + bars(items) + table(["", "wins", "win ms p50"], [[E(k), num(x["n"]), num(x["p50"], 1)] for k, x in sorted(msd.items(), key=lambda y: -y[1]["n"])[:8]]) + "</div>")
    aff = []
    for b, lst in (lr.get("bot_leader_affinity") or {}).items():
        for x in lst[:2]:
            i = x.get("info") or {}
            aff.append([f"<code>{E(short(b))}</code>", f"<code>{E(short(x['leader']))}</code>", f"{x['wins_pct']}%", f"{x['slots_pct']}%", E(f"{i.get('city')}, {i.get('country')}"), num(i.get("rtt_ms"), 1), E(str(i.get("version"))), "BAM" if i.get("bam") else "jito" if i.get("jito") else "–", "yes" if i.get("dz") else "no"])
    S.append(("leaders", "Leaders: where wins happen", "<p class='note'>Bars: share of wins on each kind of leader; the marker is how often that kind of leader led (the base rate). A bar well past its marker means winning is easier there.</p><div class='grid'>" + "".join(parts) + "</div>"
        + "<h3>Bots that win on particular leaders far more than chance</h3>" + table(["bot", "leader", "share of its wins", "share of slots", "where", "RTT ms", "version", "jito", "DZ"], aff)))
    fb = lr.get("feeds_by", {})
    frows = []
    for g in ("ALL", "dz:on DZ", "dz:not DZ", "rtt:<1ms (same DC)", "rtt:1-5ms (Frankfurt/near)", "rtt:5-20ms (EU)", "rtt:20-100ms (US east, far EU)", "rtt:>100ms (US west, Asia)"):
        if g in fb:
            best = sorted(fb[g].items(), key=lambda x: -x[1]["first_pct"])
            frows.append([E(g.replace("dz:", "").replace("rtt:", "")), E(" · ".join(f"{f} {v['first_pct']}%" for f, v in best[:4])), E(" · ".join(f"{f} {v['mean_lag_ms']}" for f, v in best[:4]))])
    S.append(("feeds", "Feeds: who shows a transaction first", table(["leaders", "first to deliver (share)", "mean lag behind the first, ms"], frows)))

if rbl:
    rows = []
    for dim, title in (("jito", "Jito / BAM"), ("dz", "DoubleZero"), ("rtt", "distance"), ("client", "client"), ("tpu", "TPU address")):
        for c, x in sorted(rbl.get(dim, {}).items(), key=lambda y: -y[1]["n"]):
            rows.append([E(title), E(c), num(x["n"]), E(" · ".join(f"{p} {n}" for p, n in list(x["first"].items())[:4])),
                         E(" · ".join(f"{p} {v}" for p, v in sorted(x["ms_p50"].items(), key=lambda y: y[1] if y[1] is not None else 1e9)[:4]))])
    S.append(("racelead", "Our path race by kind of leader", "<p class='note'>Race trades only: every path fired the same trade at once, so the landed path is the one that reached that leader first.</p>"
        + table(["by", "leaders", "trades", "first to land", "ms after trigger p50 (fastest paths)"], rows)))
if plat:
    rows = []
    for b, v in plat.items():
        rows.append([E(b if b.startswith("ALL") else short(b)), num(v["n"]), num(v["distinct_signers"]),
                     E(" · ".join(f"{short(r)} {n}" for r, n in v["routers"][:4])), E(" · ".join(f"{short(r)} {n}" for r, n in v["paid_to"][:5]))])
    S.append(("platforms", "Whose trades the winners backrun", "<p class='note'>The trigger transactions behind each bot's wins: the router program they went through and the accounts they paid (platform fee wallets, sender tips). The first row is a baseline sample of every winner's triggers.</p>"
        + table(["bot", "triggers", "distinct traders", "routers", "paid to"], rows)))
if bund:
    S.append(("bundles", "Jito bundles among wins", table(["bot", "wins checked", "in a bundle", "trigger in the same bundle"],
        [[f"<code>{E(short(b))}</code>", num(v["checked"]), num(v["in_bundle"]), num(v["trigger_in_same_bundle"])] for b, v in bund.items()])))

nav = "".join(f'<a href="#{k}">{E(t)}</a>' for k, t, _ in S)
body = "".join(f'<section id="{k}"><h2>{E(t)}</h2>{c}</section>' for k, t, c in S)
page = f"""<title>{E(LABEL)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* layout: a single reading column for findings, wide data sections below; trading-desk palette, amber marks us */
:root {{ --bg:#f6f7f9; --panel:#ffffff; --ink:#18202b; --mute:#5b6676; --line:#dde2ea; --accent:#b36b00; --bar:#3c6e9f; --base:#18202b;
  --display:"IBM Plex Sans Condensed", "Arial Narrow", sans-serif; --body:"IBM Plex Sans", system-ui, sans-serif; --mono:"IBM Plex Mono", ui-monospace, monospace; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#11161d; --panel:#18202a; --ink:#e3e8ef; --mute:#93a0b2; --line:#2a3542; --accent:#f0a634; --bar:#6fa3d6; --base:#e3e8ef; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#11161d; --panel:#18202a; --ink:#e3e8ef; --mute:#93a0b2; --line:#2a3542; --accent:#f0a634; --bar:#6fa3d6; --base:#e3e8ef; color-scheme:dark }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.55 var(--body); padding-inline:16px; padding-block:24px 64px; }}
main {{ max-width:1180px; margin:0 auto; display:flex; flex-direction:column; gap:28px; }}
h1 {{ font:600 2rem/1.15 var(--display); margin:0; text-wrap:balance; }}
h2 {{ font:600 1.35rem/1.2 var(--display); margin:0 0 12px; text-wrap:balance; }}
h3 {{ font:600 1rem/1.3 var(--display); margin:20px 0 8px; letter-spacing:.02em; text-transform:uppercase; color:var(--mute); }}
.sub {{ color:var(--mute); margin:6px 0 0; }}
nav {{ display:flex; flex-wrap:wrap; gap:6px 14px; font-size:.9rem; }} nav a {{ color:var(--accent); text-decoration:none; }} nav a:hover {{ text-decoration:underline; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:20px; min-width:0; }}
.findings {{ max-width:72ch; }} .findings p, .findings li {{ margin:0 0 10px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }}
.tile {{ border:1px solid var(--line); border-radius:4px; padding:10px 12px; display:flex; flex-direction:column; }}
.tile b {{ font:500 1.4rem var(--mono); font-variant-numeric:tabular-nums; }} .tile span {{ color:var(--mute); font-size:.85rem; }}
.tw {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:.86rem; }}
th {{ text-align:left; font:500 .78rem var(--body); color:var(--mute); border-bottom:1px solid var(--line); padding:6px 8px; white-space:nowrap; }}
td {{ border-bottom:1px solid var(--line); padding:5px 8px; font-variant-numeric:tabular-nums; vertical-align:top; }}
table.dense td {{ font-size:.8rem; padding:4px 6px; }} code {{ font:500 .82rem var(--mono); color:var(--accent); }}
.bars {{ display:flex; flex-direction:column; gap:5px; }}
.bar {{ display:grid; grid-template-columns:minmax(90px,190px) 1fr minmax(90px,auto); gap:8px; align-items:center; font-size:.85rem; }}
.bl {{ color:var(--mute); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.bt {{ position:relative; height:12px; background:color-mix(in srgb, var(--line) 60%, transparent); border-radius:2px; }}
.bf {{ position:absolute; inset:0 auto 0 0; background:var(--bar); border-radius:2px; }}
.base {{ position:absolute; top:-3px; bottom:-3px; width:2px; background:var(--base); }}
.bv {{ font:400 .8rem var(--mono); }} .bv em {{ color:var(--mute); font-style:normal; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:18px; }} .panel {{ min-width:0; }}
.note {{ color:var(--mute); font-size:.85rem; }}
@media (max-width:520px) {{ .bar {{ grid-template-columns:90px 1fr; }} .bv {{ grid-column:2; }} }}
</style>
<main>
<header><h1>{E(LABEL)}</h1><p class="sub">{E(extra.get("subtitle", ""))}</p></header>
<nav><a href="#findings">Findings</a>{nav}</nav>
<section id="findings" class="findings"><h2>Findings</h2>{findings}</section>
{body}
</main>"""
open(OUT, "w").write(page)
print(f"wrote {OUT} ({len(page)//1024} KB, {len(S)} sections)")
