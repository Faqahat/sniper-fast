#!/usr/bin/env python3
# Step 3 of 3 for "are the dumpers related to the dev?" (owner 10-25 ~16:45 PKT).
#   python3 dev_link.py --wallets   -> out/wallets.json (the wallets dev_link_fund.py traces)
#   python3 dev_link.py             -> the report (needs out/fills.json, out/scan1.json, out/scan2.json, out/fund.json)
# For every closed fill (out/fills.json from loss_causes.py) each wallet that matters is put in one class for that token:
#   dev         = the create signer / creator / payer
#   dev-linked  = MEASURED links only: signed or bought inside the create's Jito bundle; funded by the dev or the dev
#                 funded it; same first funder as the dev or as a bundle wallet (funder not a busy hub); or trades
#                 mostly this creator's tokens (>= 2 of them and >= 50% of what it bought in 24 h)
#   early-fresh = INFERRED likely dev wallets: bought within 10 slots of the create, traded <= 5 tokens in the 24 h recording,
#                 no measured link (a fresh wallet that snipes the launch and dumps with the others)
#   launch      = bought in the launch slot or the next 10 slots, a busy/broad wallet (sniper bots), no link found
#   unlinked    = everyone else
# Wallets we could not trace (busy: more than 4,000 transactions) are "unlinked" unless the recording links them.
import json, os, sys, collections
D = os.path.dirname(os.path.abspath(__file__)); OUT = f"{D}/out"
F = json.load(open(f"{OUT}/fills.json")); S1 = json.load(open(f"{OUT}/scan1.json"))
PER, BUND, LAUNCH, ENR = S1["per"], S1["bund"], S1["launch"], S1["enrich"]
BYSIG = {r["sig"]: r for rs in PER.values() for r in rs}; BYSIG.update(BUND)
def devset(m):
    c = LAUNCH.get(m) or {}
    return {x for x in (c.get("creator"), c.get("user"), c.get("payer")) if x}
def bundle_wallets(m):
    e = ENR.get(m) or {}; jc = e.get("jito_create") or {}; ws = set()
    for s in jc.get("txs") or []:
        r = BYSIG.get(s)
        if r: ws.update(r["signers"]); ws.update(t[1] for t in r["tr"])
    return ws - {m}
def launch_buyers(m, upto=10):
    c0 = (LAUNCH.get(m) or {}).get("slot") or 0; ws = {}
    for r in PER.get(m, []):
        if r["err"] or r["s"] > c0 + upto: continue
        for t in r["tr"]:
            if t[0] == m and t[2]: ws.setdefault(t[1], r["s"] - c0)
    return ws
def dumper_of(r):
    if r["kind"] == "ps": return r.get("dumper")
    x = BYSIG.get(r.get("dump_sig") or "")
    if x:
        s = [t for t in x["tr"] if t[0] == r["mint"] and not t[2]]
        if s: return max(s, key=lambda t: t[3])[1]
    return r.get("dumper")
if "--wallets" in sys.argv:
    W = set()
    for r in F:
        m = r["mint"]; W |= devset(m) | bundle_wallets(m)
        d = dumper_of(r)
        if d: W.add(d)
        sold = collections.Counter()
        for t in r["trades"]:
            if not t["buy"]: sold[t["user"]] += t["sol"] / 1e9
        W.update(w for w, v in sold.items() if v >= 0.05)
    W -= {r["mint"] for r in F}
    json.dump(sorted(W), open(f"{OUT}/wallets.json", "w")); print(len(W), "wallets -> out/wallets.json"); sys.exit()
S2 = json.load(open(f"{OUT}/scan2.json")); ACT, CRE = S2["act"], S2["creators"]
FU = json.load(open(f"{OUT}/fund.json")); FW, HUB = FU["w"], FU["hub"]
def funder(w):
    f = (FW.get(w) or {}).get("funder")
    return None if not f or (HUB.get(f) or {}).get("hub") else f
def crew(w, m):
    a = ACT.get(w) or {}; cr = CRE.get(m)
    bought = [k for k, x in a.items() if not k.startswith("signed:") and x[0] > 0]
    same = [k for k in bought if CRE.get(k) == cr]
    return cr and len(same) >= 2 and len(same) >= 0.5 * len(bought)
def breadth(w):
    return len([k for k in (ACT.get(w) or {}) if not k.startswith("signed:")])
# private (non-hub) funders of any dev wallet in our set = serial-dev networks; per-token funders of the wallets that sold
DEVF = {funder(d) for r in F for d in devset(r["mint"])} - {None}
SELLF = collections.defaultdict(collections.Counter)
for r in F:
    for u in {t["user"] for t in r["trades"] if not t["buy"]}:
        if funder(u): SELLF[r["mint"]][funder(u)] += 1
def known(w):
    x = FW.get(w) or {}
    return "busy bot" if x.get("busy") else "young (funder seen)" if x.get("funder") else "old (> 3.4 days, funder out of reach)" if w in FW else "not traced (< 0.05 SOL)"
CACHE = {}
def classify(w, m):
    k = (w, m)
    if k in CACHE: return CACHE[k]
    dv = devset(m); bw = bundle_wallets(m); lb = launch_buyers(m)
    why = []
    if w in dv: res = ("dev", ["creator"])
    else:
        if w in bw: why.append("in the create's Jito bundle")
        fw = funder(w)
        if fw and fw in dv: why.append("funded by the dev")
        if any(funder(d) == w for d in dv): why.append("funded the dev")
        if fw and any(funder(d) == fw for d in dv): why.append("same funder as the dev")
        if fw and (fw in bw or any(funder(b) == fw for b in bw if b != w)): why.append("funded by / same funder as a bundle wallet")
        if crew(w, m): why.append("trades mostly this creator's tokens")
        if fw and fw in DEVF and not any(funder(d) == fw for d in dv): why.append("same private funder as another token's dev (serial-dev network)")
        if fw and SELLF[m][fw] >= 2: why.append(f"one private funder behind {SELLF[m][fw]} sellers on this token")
        if why: res = ("dev-linked", why)
        elif w in lb and breadth(w) <= 5: res = ("early-fresh", [f"bought at launch +{lb[w]} slots, {breadth(w)} tokens in 24 h"])
        elif w in lb: res = ("launch", [f"bought at launch +{lb[w]} slots"])
        else: res = ("unlinked", [])
    CACHE[k] = res; return res
ORDER = ["dev", "dev-linked", "early-fresh", "launch", "unlinked"]
rows = []
for r in F:
    if r.get("pnl") is None: continue
    m = r["mint"]; d = dumper_of(r)
    dc = classify(d, m)[0] if d else "unknown"
    g = collections.Counter(); who = collections.defaultdict(float); nb = 0; bs = 0.0
    for t in r["trades"]:
        if t["buy"]: nb += 1; bs += t["sol"] / 1e9; continue
        c = classify(t["user"], m)[0]; g[c] += t["sol"] / 1e9; who[t["user"]] += t["sol"] / 1e9
    rows.append(dict(r=r, d=d, dc=dc, g=g, who=who, nb=nb, bs=bs))
lose = sorted([x for x in rows if x["r"]["pnl"] <= 0], key=lambda x: x["r"]["pnl"]); win = [x for x in rows if x["r"]["pnl"] > 0]
traced = [w for w in FW if FW[w].get("funder")]; busy = [w for w in FW if FW[w].get("busy")]
print(f"{len(rows)} closed fills ({len(lose)} losers {sum(x['r']['pnl'] for x in lose):+.3f} SOL, {len(win)} winners {sum(x['r']['pnl'] for x in win):+.3f} SOL)")
print(f"wallets traced {len(FW)}: first funder found {len(traced)}, busy (> 4,000 txs, no funder) {len(busy)}; hub funders {sum(1 for h in HUB.values() if h.get('hub'))}")
print(f"tokens with a Jito create bundle: {sum(1 for m in {x['r']['mint'] for x in rows} if (ENR.get(m) or {}).get('jito_create'))} of {len({x['r']['mint'] for x in rows})}")
print("\n1) THE DUMP WE BOUGHT AFTER (normal fills: the big sell; pre-send: the whale that armed it), by who sold it:")
for name, grp in (("losers", lose), ("winners", win)):
    c = collections.defaultdict(lambda: [0, 0.0])
    for x in grp: c[x["dc"]][0] += 1; c[x["dc"]][1] += x["r"]["pnl"]
    print(f"   {name:8}: " + " | ".join(f"{k} {c[k][0]} ({c[k][1]:+.3f})" for k in ORDER + ["unknown"] if c[k][0]))
print("   P&L per dumper class (all fills):")
for k in ORDER + ["unknown"]:
    xs = [x["r"]["pnl"] for x in rows if x["dc"] == k]
    if xs: print(f"      {k:<11} {len(xs):3d} fills  {sum(xs):+.4f} SOL  avg {sum(xs)/len(xs):+.4f}  win {sum(1 for v in xs if v > 0)}/{len(xs)}")
print("\n2) SELLS BY OTHERS WHILE WE HELD (SOL), by who sold:")
for name, grp in (("losers", lose), ("winners", win)):
    t = collections.Counter()
    for x in grp: t.update(x["g"])
    tot = sum(t.values()) or 1
    print(f"   {name:8}: " + " | ".join(f"{k} {t[k]:.2f} ({100*t[k]/tot:.0f}%)" for k in ORDER))
print("   fills where a dev or dev-linked wallet sold while we held: losers "
      f"{sum(1 for x in lose if x['g']['dev'] + x['g']['dev-linked'] > 0)}/{len(lose)}, winners {sum(1 for x in win if x['g']['dev'] + x['g']['dev-linked'] > 0)}/{len(win)}"
      f"; with early-fresh too: losers {sum(1 for x in lose if x['g']['dev'] + x['g']['dev-linked'] + x['g']['early-fresh'] > 0)}/{len(lose)},"
      f" winners {sum(1 for x in win if x['g']['dev'] + x['g']['dev-linked'] + x['g']['early-fresh'] > 0)}/{len(win)}")
print("   how much of that selling we could trace (SOL, losers): " + ", ".join(f"{k} {v:.1f}" for k, v in sorted(
    collections.Counter({k: sum(t["sol"] / 1e9 for x in lose for t in x["r"]["trades"] if not t["buy"] and known(t["user"]) == k)
                         for k in ("young (funder seen)", "old (> 3.4 days, funder out of reach)", "busy bot", "not traced (< 0.05 SOL)")}).items(), key=lambda z: -z[1])))
print("\n3) LOSERS: the biggest seller group while we held (no group >= 0.05 SOL = costs / thin):")
c = collections.defaultdict(lambda: [0, 0.0])
for x in lose:
    tot = sum(x["g"].values()); k = "costs / thin" if tot < 0.05 else max(ORDER, key=lambda z: x["g"][z])
    x["cause"] = k; c[k][0] += 1; c[k][1] += x["r"]["pnl"]
for k, (n, s) in sorted(c.items(), key=lambda z: z[1][1]): print(f"   {k:<13} {n:3d} fills {s:+.4f} SOL")
print("\n4) BIGGEST LOSERS (<= -0.02 SOL): dumper class; top sellers while we held (SOL, class: why)")
for x in [x for x in lose if x["r"]["pnl"] <= -0.02]:
    r = x["r"]; m = r["mint"]
    top = sorted(x["who"].items(), key=lambda z: -z[1])[:3]
    tl = "; ".join(f"{w[:6]} {v:.2f} {classify(w, m)[0]}" + (f" ({', '.join(classify(w, m)[1])})" if classify(w, m)[0] in ("dev-linked", "early-fresh") else "") for w, v in top)
    print(f"   {r['run']:<12} {m[:8]} {r['pnl']:+.4f} {'PRESEND' if r['kind']=='ps' else 'normal'} | dump by {(x['d'] or '?')[:6]} = {x['dc']}"
          + (f" ({', '.join(classify(x['d'], m)[1])})" if x['dc'] in ('dev-linked', 'early-fresh') else "") + f" | {tl}")
json.dump([dict(run=x["r"]["run"], mint=x["r"]["mint"], pnl=x["r"]["pnl"], kind=x["r"]["kind"], dumper=x["d"], dumper_class=x["dc"],
                dumper_why=classify(x["d"], x["r"]["mint"])[1] if x["d"] else [], sells=dict(x["g"]), cause=x.get("cause"),
                sellers=[dict(w=w, sol=round(v, 4), cls=classify(w, x["r"]["mint"])[0], why=classify(w, x["r"]["mint"])[1],
                              funder=(FW.get(w) or {}).get("funder"), first_sig=(FW.get(w) or {}).get("first_sig"))
                         for w, v in sorted(x["who"].items(), key=lambda z: -z[1])])
           for x in rows], open(f"{OUT}/dev_link.json", "w"), indent=1)
print("\nper fill detail: out/dev_link.json")
