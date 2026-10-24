#!/usr/bin/env python3
# READ-ONLY, offline: dKMjeG_snipes.html — its last 15 SOL-quoted snipes with every tx / wallet / token linked
# (same look as ops/snipers/w9sh/9Sh2fd_snipes.html, CSS reused). Block positions from the collector's phase-A rows.
import os, sys, json, html, datetime, collections, statistics as S, re
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"; sys.path.insert(0, HERE)
from parse import b58d
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = json.load(open(os.path.join(HERE, "ledger.json"))); T = L["tokens"]; ROWS = {r["sig"]: r for r in L["rows"]}
A = json.load(open(os.path.join(HERE, "buy_args.json")))
SUM = json.load(open(os.path.join(HERE, "summary.json"))) if os.path.exists(os.path.join(HERE, "summary.json")) else {}
LA = {}
for run in ("run_20261022_1543", "run_20261021_2207"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        LA.setdefault(c["mint"], c)
BAD = re.compile(r"n[i1]gg|f[a@]gg|r[e3]tard|kike|chink|spic\b|tranny|nazi|hitler|rape|cunt|whore|slut|\bfuck|shit", re.I)
mask = lambda s: "[masked]" if s and BAD.search(s) else s
esc = lambda s: html.escape(str(s))
def short(a, n=6): return f"{a[:n]}…{a[-4:]}"
def tx(sig, label=None): return f'<a href="https://solscan.io/tx/{sig}" target="_blank" rel="noopener">{esc(label or short(sig))}</a>'
def acct(a, label=None, gm=False): return f'<a href="https://{"gmgn.ai/sol/address" if gm else "solscan.io/account"}/{a}" target="_blank" rel="noopener">{esc(label or short(a))}</a>'
def tokl(m, label): return f'<a href="https://gmgn.ai/sol/token/{m}" target="_blank" rel="noopener">{esc(label)}</a>'
PKT = datetime.timezone(datetime.timedelta(hours=5))
def ts(bt): return datetime.datetime.fromtimestamp(bt, PKT).strftime("%b %d, %H:%M:%S")
def sgn(x, d=3): return f'<span class="{"pos" if x >= 0 else "neg"}">{x:+.{d}f}</span>'
# last 15 SOL-quoted snipes (filled buys), newest first
toks = sorted([(x["t0"], m, x) for m, x in T.items() if x["buys"] and x["quote"] == "SOL" and x.get("buy_sig") and x["sells_list"]], reverse=True)[:15]
need = {m for _, m, _ in toks}
byb = collections.defaultdict(set)
for m in need: byb[rp.bucket(m)].add(m)
TR = {}
for b, ms in byb.items():
    for _ in range(3):
        try: TR.update(rp.read_bucket("R2", b, ms)); break
        except Exception: pass
rows = []
for bt, m, x in toks:
    c = LA.get(m, {}); tr = TR.get(m) or []
    name = mask(c.get("name") or "?"); sym = mask(c.get("symbol") or "")
    r = dict(m=m, x=x, name=name, sym=sym, c=c)
    if c and tr:
        st = rp.structure(tr, c); ge = st["g_end"]
        r["dev"] = sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9; r["gsol"] = sum(t["sol"] for t in st["glued"]) / 1e9
        k0 = next((k for k, t in enumerate(tr) if t["user"] == W and t["buy"]), None)
        if k0 is not None:
            b0 = tr[k0]; r["ds"] = b0["s"] - c["slot"]
            r["ahead"] = sum(1 for t in tr[ge:k0] if t["buy"] and t["user"] not in st["insiders"])
            r["pos"] = b0["i"] - (tr[ge - 1]["i"] if ge >= 1 and tr[ge - 1]["s"] == b0["s"] else 0) if b0["s"] == c["slot"] else None
            same = [t for t in tr[ge:] if t["buy"] and t["user"] not in st["insiders"] and t["s"] == b0["s"]]
            seen = []; [seen.append(t["user"]) for t in same if t["user"] not in seen]
            r["rank"] = (seen.index(W) + 1, len(seen)) if W in seen else None
            r["entry_x"] = (b0["sol"] / b0["tok"]) / (tr[ge - 1]["vsol"] / tr[ge - 1]["vtok"]) if ge >= 1 and b0["tok"] else None
    rows.append(r)
br = lambda x: ROWS.get(x["buy_sig"], {})
def svc(r0): return (r0.get("tips") or [["none"]])[0][0]
CSS = open("/home/moiz/sniper/ops/snipers/w9sh/9Sh2fd_snipes.html").read().split("<style>")[1].split("</style>")[0]
H = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>dKMjeG Sniper Study</title><style>{CSS}</style></head><body><div class='wrap'>"]
t_first = ts(toks[-1][0]); t_last = ts(toks[0][0])
H.append("<h1>How wallet dKMjeG snipes pump.fun launches</h1>")
H.append('<p class="mut">A study of its last 15 SOL-quoted snipes, built only from on-chain data (read-only). Every transaction, wallet and token links to Solscan or GMGN.</p>')
H.append(f'<div class="chips"><span class="chip">Wallet {acct(W, "dKMjeG…2CTK", gm=True)} · {acct(W, "Solscan")}</span><span class="chip">Snipes {t_first} → {t_last} PKT (UTC+5)</span>'
         f'<span class="chip">Wider sample: {SUM.get("n_bought", "?")} filled buys, {SUM.get("window", "")}</span></div>')
tl = SUM.get("tldr_html") or []
H.append('<div class="card tldr"><b>In one paragraph</b><ul>' + "".join(f"<li>{b}</li>" for b in tl) + "</ul></div>")
if SUM.get("stats"):
    H.append('<div class="grid">' + "".join(f'<div class="stat"><b>{v}</b><span>{esc(k)}</span></div>' for k, v in SUM["stats"]) + "</div>")
# anatomy of one snipe: most recent Jito-routed winner among the 15
pick = next((r for r in rows if r["x"]["pnl"] > 0 and svc(br(r["x"])) == "jito" and r.get("ds") is not None), rows[0])
x = pick["x"]; b = br(x); c = pick["c"]; amt = (A.get(x["buy_sig"]) or {}).get("amt") or 0; mo = (A.get(x["buy_sig"]) or {}).get("minout")
H.append('<h2>Anatomy of one snipe <span class="badge m">measured</span></h2>')
H.append(f'<p>Token {tokl(pick["m"], pick["name"])} ({acct(pick["m"], short(pick["m"]))}), created {ts(c.get("bt", x["t0"]))} PKT in block {c.get("slot", "?")} by {acct(c.get("user", ""), short(c.get("user", "") or "?"), gm=True)}.</p>')
st = []
if c.get("sig"): st.append(f'<li><b>The dev creates the token</b> ({tx(c["sig"], "create tx")}) and buys {pick.get("dev", 0):.2f} SOL; glued bundle right behind it: {pick.get("gsol", 0):.2f} SOL.</li>')
st.append(f'<li><b>dKMjeG buys {amt / 1e9:.4f} SOL</b> ({tx(x["buy_sig"], "buy tx")}) in block {x["s0"]} ({"the create block" if pick.get("ds") == 0 else f"create block +{pick.get(chr(100) + chr(115))}"}), with {pick.get("ahead", "?")} outside buys ahead of it'
          + (f'; rank {pick["rank"][0]} of {pick["rank"][1]} outside buyers in that block' if pick.get("rank") else "") + ".</li>")
st.append(f'<li><b>It paid</b> a {b.get("tipsum", 0):.4f} SOL tip to {esc(svc(b))} and a {b.get("prio", 0):.5f} SOL priority fee ({(b.get("tipsum", 0) + b.get("prio", 0)) / max(amt / 1e9, 1e-9):.1%} of the buy).</li>')
sl = sorted(x["sells_list"], key=lambda s: s["slot"])
st.append(f'<li><b>It sold in {len(sl)} pieces</b>: ' + ", ".join(f'{tx(s["sig"], f"{s["tok"] / x["buy_tok"]:.0%} at +{(s["slot"] - x["s0"]) * 0.212:.1f} s (×{s["px"] / x["buy_px"]:.2f})")}' for s in sl[:8]) + ".</li>")
st.append(f'<li><b>Net result</b> (all its SOL changes on this token incl. fees, tips, rent): {sgn(x["pnl"])} SOL.</li>')
H.append('<ol class="steps">' + "".join(st) + "</ol>")
H.append('<h3>Its buy transaction, instruction by instruction</h3><div class="card">')
H.append(f'<div class="ix"><span class="n">#1</span><div><b>Advance durable nonce</b> (nonce account {acct(b.get("nonce") or "", short(b.get("nonce") or "?"))}). It rotates just 3 nonce accounts for all buys. Every landing-service copy of a buy uses the same nonce, so only one copy can ever execute.</div></div>')
H.append('<div class="ix"><span class="n">#2</span><div><b>Creates its token account directly</b> (createAccountWithSeed, Token-2022), not through the Associated Token Account program — the same trick as AKbot.</div></div>')
H.append(f'<div class="ix"><span class="n">#3</span><div><b>Calls its own router program</b> {acct("ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8", "ENFJAV…Dve8")} (upgrade authority = dKMjeG itself; no other wallet used it in 1,000 recent calls). It initializes the token account and calls pump.fun <i>BuyExactQuoteInV3</i> with spend {amt} lamports and min tokens out {mo}. '
         f'The last digits of the spend ({amt % 1000}) are a <b>tag for the landing service</b>: every service gets its own tag (jito 42, helius 108, nozomi 168, speedlanding 178, bolt 128, astralane 148, …).</div></div>')
H.append(f'<div class="ix"><span class="n">#4</span><div><b>Tip transfer</b>: {b.get("tipsum", 0):.4f} SOL to a {esc(svc(b))} tip account' + (" — the Jito copy also carries the <span class='mono'>jitodontfront</span> marker and pays no priority fee." if svc(b) == "jito" else ".") + "</div></div>")
H.append(f'<p class="small mut">Transaction format v{esc(b.get("v"))}: the fee is in the header, no compute-budget instructions. Compute used: {b.get("cu")} units. Single signer.</p></div>')
# table
H.append('<h2>The last 15 snipes <span class="badge m">measured</span></h2><p class="mut small">Ahead = outside buys (not the dev, not the glued bundle) that landed before its buy. Rank = its place among outside buyers in that block. Result = the sum of its wallet\'s SOL changes on the token (buy, every sell, failed copies, tips, fees, account rent back). Times are slots × 0.212 s.</p>')
H.append('<div class="tbl"><table><tr><th class="l">Token</th><th class="l">Created (PKT)</th><th>Dev + bundle SOL</th><th class="l">Its buy</th><th>Block</th><th>Ahead</th><th>Rank</th><th>SOL</th><th class="l">Landed via</th><th>Tip</th><th>Priority</th><th>Sells</th><th>Held</th><th>Result</th></tr>')
for r in rows:
    x = r["x"]; b = br(x); amt = (A.get(x["buy_sig"]) or {}).get("amt") or 0; sl = sorted(x["sells_list"], key=lambda s: s["slot"])
    held = f'{(sl[0]["slot"] - x["s0"]) * 0.212:.0f}–{(sl[-1]["slot"] - x["s0"]) * 0.212:.0f} s'
    dvb = f'{r["dev"]:.2f} + {r["gsol"]:.2f}' if "dev" in r else "–"
    blk = ("create" if r.get("ds") == 0 else f'+{r["ds"]}') if r.get("ds") is not None else "–"
    sells = " ".join(tx(s["sig"], str(i + 1)) for i, s in enumerate(sl))
    H.append(f'<tr><td class="l">{tokl(r["m"], r["name"] if r["name"] != "?" else short(r["m"]))}</td><td class="l">{ts(r["c"].get("bt", x["t0"]))}</td><td>{dvb}</td><td class="l">{tx(x["buy_sig"])}</td><td>{blk}</td><td>{r.get("ahead", "–")}</td>'
             f'<td>{(str(r["rank"][0]) + "/" + str(r["rank"][1])) if r.get("rank") else "–"}</td><td>{amt / 1e9:.2f}</td><td class="l">{esc(svc(b))}</td><td>{b.get("tipsum", 0):.4f}</td><td>{b.get("prio", 0):.4f}</td><td>{sells}</td><td>{held}</td><td>{sgn(x["pnl"])}</td></tr>')
tot = sum(r["x"]["pnl"] for r in rows)
H.append(f'</table></div><p class="small mut">Total over these 15: {sgn(tot)} SOL ({sum(1 for r in rows if r["x"]["pnl"] > 0)} wins).</p>')
for sec in SUM.get("sections_html", []): H.append(sec)
H.append(f'<footer>Generated {datetime.datetime.now(PKT).strftime("%b %d, %Y %H:%M")} PKT from on-chain data (read-only, nothing sent). Scripts: ops/overnight/dkmjeg (fetch.py, parse.py, ledger_an.py, infra.py, exits.py, coll.py, sel.py, copy*.py, render.py).</footer></div></body></html>')
open(os.path.join(HERE, "dKMjeG_snipes.html"), "w").write("\n".join(H))
print("wrote dKMjeG_snipes.html", len("\n".join(H)), "bytes;", sum(1 for r in rows if "dev" in r), "of", len(rows), "with block data")
