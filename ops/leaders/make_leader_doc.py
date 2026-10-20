# Build the leader-region scaling document (static HTML) from leader_regions_*.json.
# usage: python3 make_leader_doc.py <leader_regions.json> <out.html>
import json, sys, html

D = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
R = D["regions"]
esc = html.escape

STATUS = {"Frankfurt (DE)": ("live", "Covered now")}
PLAN = {
    "Amsterdam (NL)": ("next", "Next location"),
    "London (UK)": ("later", "Candidate"),
    "US East (NY/NJ/Ashburn)": ("later", "Candidate"),
    "Lithuania (Šiauliai)": ("later", "Candidate"),
    "Singapore": ("later", "Candidate"),
    "Tokyo (JP)": ("later", "Candidate"),
    "US West": ("later", "Candidate"),
}


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def rtt(x):
    return "no reply" if x is None else (f"{x:.1f} ms" if x >= 1 else f"{x:.2f} ms")


def prov_name(p):
    return p.replace(", Inc.", "").replace(" Inc.", "").replace(" Inc", "").replace(" LLC", "").replace(", LLC", "").replace("UAB ", "").replace(" Networks", "")


rows = []
for r in R:
    st, label = STATUS.get(r["region"], PLAN.get(r["region"], ("skip", "Skipped")))
    provs = ", ".join(f"{esc(prov_name(p))} {pct(s)}" for p, s in r["providers"][:3])
    clients = ", ".join(f"{esc(c)} {pct(s, 0)}" for c, s in r["clients"][:3])
    rows.append(f"""<tr>
  <th scope="row">{esc(r['region'])}</th>
  <td class="num share"><span class="track"><span class="bar" style="width:{min(100, r['slot_share'] / 0.35 * 100):.1f}%"></span></span><span>{pct(r['slot_share'])}</span></td>
  <td class="num">{r['r2']} <small>({pct(r['r2_share'], 0)})</small></td>
  <td class="num">{rtt(r['rtt_med'])}</td>
  <td class="num">{r['leaders']}</td>
  <td><span class="pill {st}">{label}</span></td>
  <td class="wrap">{provs}</td>
  <td class="wrap">{clients}</td>
</tr>""")

details = []
for r in R:
    if r["slot_share"] < 0.004:
        continue
    tops = "".join(f"""<tr><td class="mono">{esc(t['pk'][:4])}…{esc(t['pk'][-4:])}</td><td class="num">{pct(t['share'], 2)}</td><td class="num">{rtt(t['rtt'])}</td>
<td>{esc(t['client'])}</td><td>{esc(t['city'] or '?')}</td><td class="wrap">{esc(prov_name((t['asn'] or '?').split(' ', 1)[-1]))}</td><td class="mono">{esc((t['asn'] or '?').split(' ')[0])}</td></tr>""" for t in r["top"])
    cities = ", ".join(f"{esc(c)} {pct(s)}" for c, s in r["cities"])
    provs = "".join(f"<li><b>{esc(prov_name(p))}</b> <span class='mono'>{pct(s)}</span></li>" for p, s in r["providers"])
    details.append(f"""<details>
<summary><span class="dname">{esc(r['region'])}</span><span class="dmeta">{pct(r['slot_share'])} of slots · {r['leaders']} leaders · {rtt(r['rtt_med'])} from Frankfurt</span></summary>
<div class="dbody">
  <div class="dgrid">
    <div><h4>Hosting providers (share of all slots)</h4><ul class="plist">{provs}</ul></div>
    <div><h4>Cities</h4><p>{cities}</p><h4>Leader clients</h4><p>{", ".join(f"{esc(c)} {pct(s, 0)}" for c, s in r['clients'])}</p></div>
  </div>
  <h4>Biggest leaders here</h4>
  <div class="scroll"><table class="tight"><thead><tr><th>Validator</th><th>Slots</th><th>RTT</th><th>Client</th><th>City</th><th>Provider</th><th>ASN</th></tr></thead><tbody>{tops}</tbody></table></div>
</div>
</details>""")

page = f"""<title>Solana Leader Regions</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* layout: one reading column; the region table is the spine, details fold below it */
:root {{
  --bg: #f6f7f9; --panel: #ffffff; --fg: #17202b; --muted: #5b6878; --line: #dde2e8;
  --accent: #0b6e8a; --bar: #9fd3e2; --live: #1f7a4d; --live-bg: #e2f3ea; --next: #8a5a00; --next-bg: #fbefd5;
  --later: #4b5563; --later-bg: #eceff3; --skip: #6b7280; --skip-bg: #f1f2f4;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif; --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #0f141a; --panel: #161d25; --fg: #e5eaf0; --muted: #96a3b3; --line: #2a3440;
  --accent: #5cc2de; --bar: #1f5466; --live: #6fd39f; --live-bg: #16372a; --next: #f0c46a; --next-bg: #3a2d10;
  --later: #c2cad5; --later-bg: #232c37; --skip: #9aa4b1; --skip-bg: #1d242d; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #0f141a; --panel: #161d25; --fg: #e5eaf0; --muted: #96a3b3; --line: #2a3440;
  --accent: #5cc2de; --bar: #1f5466; --live: #6fd39f; --live-bg: #16372a; --next: #f0c46a; --next-bg: #3a2d10;
  --later: #c2cad5; --later-bg: #232c37; --skip: #9aa4b1; --skip-bg: #1d242d; color-scheme: dark }}
body {{ background: var(--bg); color: var(--fg); font-family: var(--display); font-size: 15px; line-height: 1.55; }}
.wrap-page {{ max-width: 1100px; margin: 0 auto; padding-block: 28px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 28px; }}
header {{ display: grid; gap: 8px; }}
.eyebrow {{ font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }}
h1 {{ font-size: clamp(26px, 4vw, 36px); line-height: 1.15; margin: 0; font-weight: 800; text-wrap: balance; }}
h2 {{ font-size: 20px; margin: 0 0 10px; font-weight: 700; }}
h4 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 14px 0 6px; font-weight: 600; }}
p {{ margin: 0; max-width: 72ch; }}
.lede {{ color: var(--muted); max-width: 78ch; }}
.facts {{ display: flex; flex-wrap: wrap; gap: 10px 26px; font-family: var(--mono); font-size: 13px; color: var(--muted); }}
.facts b {{ color: var(--fg); font-weight: 500; }}
section {{ display: grid; gap: 12px; }}
.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
thead th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 600; white-space: nowrap; }}
tbody th {{ font-weight: 600; white-space: nowrap; }}
.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }}
td.num small {{ color: var(--muted); }}
.share {{ display: flex; align-items: center; gap: 8px; min-width: 130px; }}
.track {{ display: inline-block; width: 64px; height: 8px; background: var(--line); border-radius: 2px; overflow: hidden; flex: none; }}
.bar {{ display: block; height: 100%; background: var(--accent); }}
.wrap {{ min-width: 180px; color: var(--muted); font-size: 13px; }}
.pill {{ display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
.pill.live {{ color: var(--live); background: var(--live-bg); }} .pill.next {{ color: var(--next); background: var(--next-bg); }}
.pill.later {{ color: var(--later); background: var(--later-bg); }} .pill.skip {{ color: var(--skip); background: var(--skip-bg); }}
.steps {{ display: grid; gap: 10px; counter-reset: s; padding: 0; margin: 0; list-style: none; }}
.steps li {{ counter-increment: s; display: grid; grid-template-columns: 30px 1fr; gap: 10px; }}
.steps li::before {{ content: counter(s); font-family: var(--mono); color: var(--accent); font-weight: 500; }}
.steps b {{ font-weight: 700; }}
details {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }}
details + details {{ margin-top: 8px; }}
summary {{ cursor: pointer; padding: 14px 18px; display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }}
summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 10px; }}
.dname {{ font-weight: 700; }} .dmeta {{ font-family: var(--mono); font-size: 13px; color: var(--muted); }}
.dbody {{ padding: 0 18px 16px; display: grid; gap: 4px; }}
.dgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0 24px; }}
.dgrid > div {{ min-width: 0; }}
.plist {{ margin: 0; padding-left: 18px; }} .plist li {{ margin: 2px 0; }}
.mono {{ font-family: var(--mono); font-size: 13px; }}
table.tight td, table.tight th {{ padding: 6px 8px; font-size: 13px; }}
code {{ font-family: var(--mono); font-size: 13px; background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; }}
pre {{ font-family: var(--mono); font-size: 13px; background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 12px; overflow-x: auto; margin: 0; }}
.note {{ font-size: 13px; color: var(--muted); }}
ul.caveats {{ margin: 0; padding-left: 18px; display: grid; gap: 6px; max-width: 80ch; }}
</style>
<div class="wrap-page">
<header>
  <div class="eyebrow">Sniper · scaling map · epoch {D['epoch']}</div>
  <h1>Solana Leader Regions</h1>
  <p class="lede">Where the block leaders sit, which hosting providers run them, and which ones our Frankfurt sniper skips today. Use it to pick the next server location.</p>
  <div class="facts">
    <span>Measured from <b>84.32.100.36</b> (Cherry Servers, Frankfurt)</span>
    <span>Leaders <b>{sum(r['leaders'] for r in R)}</b></span>
    <span>Rule-#2 launches attributed <b>{D['r2_total']}</b></span>
    <span>Date <b>2026-10-20</b></span>
  </div>
</header>

<section>
  <h2>Scale-out order</h2>
  <div class="panel">
    <ol class="steps">
      <li><div><b>Frankfurt: live.</b> 33.5% of slots and 42% of today's rule-#2 launches. We buy at leaders under 5 ms (98% of Frankfurt's slots). Mostly TeraSwitch, then Allnodes, Latitude.sh and Cherry Servers.</div></li>
      <li><div><b>Amsterdam: next.</b> 22.1% of slots and 17% of rule-#2 launches, about 6 ms from Frankfurt. From Frankfurt these launches lost money in the simulation (snipers sitting in Amsterdam get in first), so they need a server in Amsterdam itself. TeraSwitch AMS holds 16.4% of all slots; Servers.com 4.2%; Cherry Servers also has an Amsterdam site (0.7%).</div></li>
      <li><div><b>London.</b> 10.0% of slots, 11% of rule-#2 launches, 11 ms away. Two thirds of London's slots are Harmonic leaders. TeraSwitch London and Galaxy Digital.</div></li>
      <li><div><b>US East (Newark / Ashburn / Secaucus).</b> 10.5% of slots, 8% of rule-#2 launches. Half are BAM leaders. TeraSwitch, Galaxy Digital (Secaucus).</div></li>
      <li><div><b>Lithuania, Singapore, Tokyo, US West.</b> 3.6–5.1% of slots each. Lithuania is all Cherry Servers (Šiauliai), our own provider.</div></li>
    </ol>
  </div>
  <p class="note">TeraSwitch hosts the largest share of leaders in almost every region. A server in the same TeraSwitch facility as a region's leaders is the closest we can get to them.</p>
</section>

<section>
  <h2>All regions</h2>
  <div class="panel scroll">
    <table>
      <thead><tr><th>Region</th><th>Share of slots</th><th>Rule-#2 launches</th><th>RTT from Frankfurt</th><th>Leaders</th><th>Status</th><th>Top providers (share of all slots)</th><th>Leader clients</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>

<section>
  <h2>Region details</h2>
  <div>{''.join(details)}</div>
</section>

<section>
  <h2>How this was measured</h2>
  <div class="panel">
    <ul class="caveats">
      <li><b>Share of slots</b>: each leader's slots in epoch {D['epoch']}'s leader schedule, out of all slots. It tracks stake, so it changes slowly.</li>
      <li><b>RTT from Frankfurt</b>: the lowest of 3 pings from our server to each leader's TPU / gossip IP; the region value is the median leader. About 2% of slots belong to leaders that don't answer ping.</li>
      <li><b>Rule-#2 launches</b>: the {D['r2_total']} real rule-#2 launches seen in today's dry runs (about 2 hours), by the location of their create-slot leader. A small sample; it shows where our launches come from, not exact shares.</li>
      <li><b>Location and provider</b>: IP geolocation (ip-api.com) with the network owner (ASN). City names can be approximate, e.g. some Frankfurt IPs show as "Frankfurt (Oder)" or a suburb.</li>
      <li><b>Covered</b>: leaders under 5 ms from our server, the filter the sniper uses today. The list refreshes every 6 hours.</li>
    </ul>
  </div>
  <h4>Rebuild this map from any server</h4>
  <pre>sudo bash /root/fix2/refresh_close.sh            # ping every leader -> leader_rtt_new.json, close list
sudo python3 /root/leaders/leader_geo.py          # add city + hosting provider -> leader_geo.json</pre>
  <p class="note">Source and scripts: host repo <code>ops/leaders/</code> (data file <code>leader_regions_e{D['epoch']}.json</code>).</p>
</section>
</div>
"""
open(OUT, "w").write(page)
print("wrote", OUT, len(page), "bytes")
