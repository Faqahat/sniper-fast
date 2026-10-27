#!/usr/bin/env python3
# Owner 10-25 ~16:30 PKT: "from our last trades, especially the biggest losses, did we lose because of a DEV sell or the market?"
# Read-only. For every closed fill in the given runs (normal dip buys: fire/tape/close; pre-send live: presend_live_*), take the
# trades on the token between our buy and our sell (the engine's tape), and split who sold while we held:
#   dev (create signer / creator / payer, recorder launches.jsonl) | the dumper we bought after (normal: the dump tx's signer via
#   one read-only getTransaction; pre-send: the whale that armed the window) | everyone else; plus the outside buys.
# A loser's cause = the biggest seller group (by SOL) while we held; "no sellers" = the price did not fall on sells (costs / thin).
# usage: python3 loss_causes.py dip_r15 dip_r16 dip_ams_r16 dip_ams_r17
import json, os, re, sys, glob, collections, urllib.request
from concurrent.futures import ThreadPoolExecutor
R = "/home/moiz/sniper-data/runs"
DEV = {}
for d in sorted(glob.glob("/home/moiz/sniper-data/collect/run_2026102*/launches.jsonl")):
    for l in open(d):
        try: c = json.loads(l)
        except Exception: continue
        DEV[c["mint"]] = {x for x in (c.get("user"), c.get("creator"), c.get("payer")) if x}
URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()   # never printed
def signer(sig):
    if not sig: return None
    try:
        req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
              "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}).encode(), headers={"content-type": "application/json"})
        t = json.load(urllib.request.urlopen(req, timeout=30)).get("result")
        return t["transaction"]["message"]["accountKeys"][0] if t else None
    except Exception: return None
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
fills = []
for run in sys.argv[1:]:
    reg = "ams" if "ams" in run else "fra"
    f = f"{R}/{reg}/runs/{run}.jsonl"; lg = f"{R}/{reg}/runs/{run}.log"
    pnl = collections.defaultdict(list)
    for l in open(lg, errors="ignore"):
        m = re.search(r"PRESEND LIVE REALIZED (\S+) ([-+0-9.]+) SOL", l) or re.search(r"REALIZED mint=(\S+) pnl=([-+0-9.]+)", l)
        if m: pnl[("ps" if "PRESEND" in l else "n", m.group(1))].append(float(m.group(2)))
    tapes = collections.defaultdict(list); fire = {}; arm = {}
    recs = []
    for l in open(f):
        if '"ev":"dump"' in l or '"ev":"presend_attempt' in l or '"ev":"presend_' in l and 'presend_live' not in l: continue
        try: o = json.loads(l)
        except Exception: continue
        recs.append(o)
    for o in recs:
        e = o.get("ev"); m = o.get("mint")
        if e == "fire": fire[m] = o
        elif e == "presend_live_arm": arm[(o.get("trig") or {}).get("mint", m)] = o
        elif e in ("tape", "presend_live_tape"): tapes[(e, m)].append(o)
        elif e in ("close", "presend_live_close") and o.get("result") == "sold" and o.get("land") and o.get("sell_land"):
            kind = "ps" if e.startswith("presend") else "n"
            tp = tapes[("presend_live_tape" if kind == "ps" else "tape", m)]
            b = (o["land"][0], o["land"][1]); s = (o["sell_land"][0], o["sell_land"][1])
            p = pnl[(kind, m)].pop(0) if pnl.get((kind, m)) else None
            dumper = None; dump_sig = None
            if kind == "n": dump_sig = (fire.get(m) or {}).get("dump_sig")
            else: dumper = ((arm.get(m) or {}).get("trig") or {}).get("wallet")
            fills.append(dict(run=run, kind=kind, mint=m, pnl=p, b=b, s=s, curve=o.get("curve_pnl"), exit=o.get("exit_why"), held=o.get("held_s"),
                              trades=[t for t in tp if b < (t["slot"], t["idx"]) < s and t.get("user") not in OURS], dump_sig=dump_sig, dumper=dumper))
            tapes[("presend_live_tape" if kind == "ps" else "tape", m)] = []
with ThreadPoolExecutor(6) as ex:
    sg = list(ex.map(lambda r: signer(r["dump_sig"]) if r["kind"] == "n" else r["dumper"], fills))
for r, w in zip(fills, sg): r["dumper"] = w
def split(r):
    dev = DEV.get(r["mint"], set()); g = collections.Counter(); nb = 0; bs = 0.0
    for t in r["trades"]:
        sol = t["sol"] / 1e9
        if t["buy"]: nb += 1; bs += sol; continue
        who = "dev" if t["user"] in dev else "dumper" if r["dumper"] and t["user"] == r["dumper"] else "other"
        g[who] += sol
    return g, nb, bs, bool(dev)
out = []
for r in fills:
    if r["pnl"] is None: continue
    g, nb, bs, devk = split(r)
    tot = sum(g.values())
    cause = "no outside sells (costs / thin)" if tot < 0.05 else max(g, key=g.get)
    out.append(dict(r, g=g, nb=nb, bs=bs, devk=devk, cause=cause, sold=tot))
lose = sorted([r for r in out if r["pnl"] <= 0], key=lambda r: r["pnl"]); win = [r for r in out if r["pnl"] > 0]
print(f"{len(out)} closed fills with chain P&L ({len(lose)} losers, {len(win)} winners); dev known for {sum(r['devk'] for r in out)}")
print("\nLOSERS, biggest first (sells by others while we held, SOL: dev / the dumper or whale / everyone else; outside buys):")
for r in lose:
    g = r["g"]
    print(f"  {r['run']:<12} {'PRESEND' if r['kind']=='ps' else 'normal ':7} {r['mint'][:8]} {r['pnl']:+.4f}  held {r['held'] or 0:.1f}s ({r['exit']})  "
          f"sells dev {g['dev']:.2f} / dumper {g['dumper']:.2f} / other {g['other']:.2f} | buys {r['nb']} ({r['bs']:.2f} SOL)  => {r['cause']}{'' if r['devk'] else '  [dev unknown]'}")
def agg(name, g):
    if not g: return
    c = collections.defaultdict(lambda: [0, 0.0])
    for r in g: c[r["cause"]][0] += 1; c[r["cause"]][1] += r["pnl"]
    print(f"\n{name}: {len(g)} fills, {sum(r['pnl'] for r in g):+.4f} SOL")
    for k, (n, s) in sorted(c.items(), key=lambda x: x[1][1]): print(f"   {k:<32} {n:3d} fills  {s:+.4f} SOL")
agg("LOSERS by cause", lose); agg("WINNERS by cause (same split, for comparison)", win)
big = [r for r in lose if r["pnl"] <= -0.03]; agg("BIG LOSERS (<= -0.03) by cause", big)
print(f"\ndev sold during the hold: losers {sum(1 for r in lose if r['g']['dev'] > 0)}/{len(lose)}, winners {sum(1 for r in win if r['g']['dev'] > 0)}/{len(win)}")
if os.environ.get("LC_DUMP"):   # every closed fill with its hold-time tape, for dev_link.py
    json.dump(out, open(os.environ["LC_DUMP"], "w"))
