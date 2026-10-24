#!/usr/bin/env python3
# READ-ONLY, offline: what 9qz7cW attempts vs skips. Population = every launch in the paper feature table
# (table_dump.jsonl.gz, R1 + R2) inside the hours the wallet was active; snipes (first attempt in the create slot or the
# next) and later buys (first attempt >= 2 slots after the create) analysed separately. Attempt rates by feature bucket,
# deployer follow-through, and a held-out check of the strongest simple rule. -> select_q9z.json + printed tables.
import os, json, gzip, collections, statistics, re, math, random
HERE = os.path.dirname(os.path.abspath(__file__))
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_q9z.json"))
Q = json.load(open(os.path.join(HERE, "quote_by_mint.json")))
def num(x):
    if x in (None, "None", ""): return None
    try: return float(x)
    except (TypeError, ValueError): return x
rows = []
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l); rows.append({k: num(v) for k, v in r.items()})
bt = [r["bt"] for r in rows if isinstance(r.get("bt"), float)]
att_bt = sorted(r["bt"] for r in rows if r["mint"] in A)
lo, hi = att_bt[0], att_bt[-1]
P = [r for r in rows if isinstance(r.get("bt"), float) and lo <= r["bt"] <= hi]
for r in P:
    a = A.get(r["mint"], {}).get("9qz7cW")
    r["att"] = a is not None; r["fill"] = bool(a and a[0]); r["off"] = a[1] if a else None
    r["snipe"] = bool(a and a[1] <= 1); r["later"] = bool(a and a[1] >= 2)
    q = Q.get(r["mint"]); r["quote"] = "SOL" if q == "SOL" else ("unknown" if q is None else "other")
    r["dev_signs"] = 1 if r.get("payer") == r.get("creator") else 0
print(f"population: {len(P)} launches in the wallet's active span; attempted {sum(r['att'] for r in P)} (snipes {sum(r['snipe'] for r in P)}, later {sum(r['later'] for r in P)})")
OUT = {}
def tab(name, key, P=P):
    g = collections.defaultdict(lambda: [0, 0, 0])
    for r in P:
        k = key(r); x = g[k]; x[0] += 1; x[1] += r["snipe"]; x[2] += r["later"]
    res = [(k, n, s, l) for k, (n, s, l) in sorted(g.items(), key=lambda kv: str(kv[0]))]
    OUT[name] = res
    print(f"\n{name}:  bucket | launches | snipe-attempt rate | later-attempt rate")
    for k, n, s, l in res:
        if n >= 30: print(f"   {str(k):28} {n:6d}   {s / n * 100:5.1f}% ({s})   {l / n * 100:5.1f}% ({l})")
def b(x, cuts, fmt="{}"):
    if x is None or isinstance(x, str): return "na"
    for c in cuts:
        if x < c: return f"<{c}"
    return f">={cuts[-1]}"
tab("quote", lambda r: r["quote"])
tab("mayhem", lambda r: int(r.get("mayhem") or 0))
tab("dev buy SOL (SOL quote)", lambda r: b(r.get("dev_buy") if r["quote"] == "SOL" else None, [0.01, 0.5, 1, 2, 3, 5]))
tab("glued bundle txs", lambda r: b(r.get("glued_n"), [1, 2, 3, 5]))
tab("glued bundle SOL", lambda r: b(r.get("glued_sol"), [0.01, 1, 3, 6, 10]))
tab("payer is creator", lambda r: int(r.get("payer_is_creator") or 0))
tab("create variant", lambda r: r.get("create_variant"))
tab("deployer prior launches", lambda r: b(r.get("cr_prior_n"), [1, 2, 5, 20, 100]))
tab("deployer recent creates", lambda r: b(r.get("cr_recent_creates"), [1, 2, 5, 10]))
tab("min since deployer's previous create", lambda r: b(r.get("cr_min_since_prev_create"), [1, 5, 15, 60, 240]))
tab("deployer age s", lambda r: b(r.get("cr_age_s"), [600, 3600, 86400, 7 * 86400]))
tab("twitter / website / telegram", lambda r: f"tw{int(r.get('has_tw') or 0)} web{int(r.get('has_web') or 0)} tg{int(r.get('has_tg') or 0)}")
tab("metadata host", lambda r: (r.get("uri_host") or "na") if isinstance(r.get("uri_host"), str) else "na")
tab("image host", lambda r: (r.get("img_host") or "na") if isinstance(r.get("img_host"), str) else "na")
tab("created on", lambda r: (str(r.get("created_on") or "na")[:30]))
tab("hour UTC", lambda r: int(r["hour_utc"]) if isinstance(r.get("hour_utc"), float) else "na")
tab("name has digits", lambda r: int(r.get("name_digits") or 0) > 0)
tab("name upper", lambda r: int(r.get("name_upper") or 0))
tab("symbol == name", lambda r: int(r.get("sym_eq_name") or 0))
tab("funder amount SOL", lambda r: b(r.get("fund_amt"), [0.1, 0.5, 2, 10, 50]))
tab("create slot outside buys", lambda r: b(r.get("slot_buys"), [1, 2, 4, 8, 16]))
# deployer follow-through: of each deployer's launches in the span, how many were sniped
dep = collections.defaultdict(list)
for r in P: dep[r.get("creator")].append(r)
ds = [(d, len(v), sum(x["snipe"] for x in v), sum(x["later"] for x in v)) for d, v in dep.items()]
sn = [x for x in ds if x[2]]
print(f"\ndeployers with >= 1 snipe: {len(sn)}; their launches {sum(x[1] for x in sn)}, sniped {sum(x[2] for x in sn)} ({sum(x[2] for x in sn) / max(1, sum(x[1] for x in sn)) * 100:.0f}%)")
for lo_, hi_ in ((1, 1), (2, 3), (4, 10), (11, 1000)):
    g = [x for x in sn if lo_ <= x[1] <= hi_]
    if g: print(f"   deployers with {lo_}-{hi_} launches: {len(g)} deployers, follow-through {sum(x[2] for x in g)}/{sum(x[1] for x in g)} = {sum(x[2] for x in g) / sum(x[1] for x in g) * 100:.0f}%")
top = sorted(sn, key=lambda x: -x[2])[:15]
print("   top sniped deployers (deployer6, launches, snipes, later):", [(d[:6], n, s, l) for d, n, s, l in top])
OUT["deployers"] = dict(n_sniped_deployers=len(sn), top=[(d, n, s, l) for d, n, s, l in top])
json.dump(OUT, open(os.path.join(HERE, "select_q9z.json"), "w"), default=str)
json.dump({r["mint"]: {k: r.get(k) for k in ("bt", "creator", "payer", "name", "symbol", "quote", "mayhem", "dev_buy", "glued_n", "glued_sol", "cr_prior_n",
                       "cr_recent_creates", "cr_min_since_prev_create", "has_tw", "has_web", "has_tg", "uri_host", "img_host", "created_on", "hour_utc",
                       "slot_buys", "att", "fill", "off", "snipe", "later", "P0_mc_sol", "graduated", "fslot_nb", "f1s_px", "f5s_px", "f15s_px", "dev_sell_first_slot")}
           for r in P}, gzip.open(os.path.join(HERE, "pop_q9z.json.gz"), "wt"))
