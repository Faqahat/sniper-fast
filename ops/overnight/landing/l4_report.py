#!/usr/bin/env python3
# LANDING-PATH STUDY, step 4 (READ-ONLY, offline): statistics + markdown tables from the step-2 rows and the step-3
# RPC sample. Writes work/tables.md (all tables) and ../landing_stats.json (machine-readable).
# usage: python3 -I l4_report.py
import os, json, gzip, collections, math, re

W = "/home/moiz/sniper/ops/overnight/landing/work"
OUTJ = "/home/moiz/sniper/ops/overnight/landing/landing_stats.json"
OUTM = os.path.join(W, "tables.md")
OURS_MS = 74.0           # our live Run 2 landings: 73.0 and 75.1 ms after the create (RUN2_RESULTS.md)
BAD = ["nigg", "nigga", "fag", "cunt", "rape", "nazi", "hitler", "kike", "spic", "chink", "retard", "whore", "slut", "dick", "cock", "pussy",
       "fuck", "shit", "bitch", "penis", "anal", "porn", "jew"]


def mask(s):
    if s is None: return s
    low = s.lower()
    return "[masked]" if any(b in low for b in BAD) else s


def wp(w):           # wallet prefix for display
    return mask(w[:6]) if w else "?"


def mw(w):           # full wallet for the JSON, masked when its prefix is offensive
    return "[masked]" if w and mask(w[:8]) == "[masked]" else w


def q(v, p):
    if not v: return None
    v = sorted(v)
    k = (len(v) - 1) * p; f = math.floor(k); c = math.ceil(k)
    return v[f] if f == c else v[f] + (v[c] - v[f]) * (k - f)


def pct(a, b):
    return (100.0 * a / b) if b else None


def f1(x, nd=1):
    return "–" if x is None else f"{x:.{nd}f}"


def sol(x, nd=4):
    return "–" if x is None else f"{x:.{nd}f}"


B = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_buys.jsonl.gz"), "rt")]
F = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_fail.jsonl.gz"), "rt")]
LCH = [json.loads(l) for l in gzip.open(os.path.join(W, "launches.jsonl.gz"), "rt")]
N_ALL_BUYS = len(B); N_NONSOL_BUYS = sum(1 for b in B if not b.get("qsol"))
B = [b for b in B if b.get("qsol")]          # SOL-quoted curves only (other quotes: event amounts are quote-token units, buys go through swaps)
F = [f for f in F if f.get("qsol")]
LCH = [x for x in LCH if x.get("qsol")]
RS = {}
if os.path.exists(os.path.join(W, "rpc/txsample.jsonl")):
    for l in open(os.path.join(W, "rpc/txsample.jsonl")):
        try: x = json.loads(l)
        except Exception: continue
        RS[x["sig"]] = x
meta = json.load(open(os.path.join(W, "build_meta.json")))

# ---------- derived fields ----------
mint_launch = {(x["R"], x["mint"]): x for x in LCH}
wallet_launches = collections.defaultdict(set)
for b in B: wallet_launches[b["payer"]].add((b["R"], b["mint"]))
for b in B:
    s = b["sol"] / 1e9
    b["solv"] = s
    b["tipv"] = b["tip"] / 1e9
    b["priov"] = b["prio"] / 1e9
    b["feev"] = b["fee"] / 1e9
    b["tip_pct"] = 100 * b["tipv"] / s if s > 0 else None
    b["prio_pct"] = 100 * b["priov"] / s if s > 0 else None
    b["cost_pct"] = 100 * (b["tipv"] + b["feev"]) / s if s > 0 else None
    b["rep"] = len(wallet_launches[b["payer"]]) >= 10
    cf = b.get("cfrac")
    b["cpos"] = "?" if cf is None else ("early" if cf < 1 / 3 else ("mid" if cf < 2 / 3 else "late"))

MIN_N = 30
pc = collections.Counter(b["path"] for b in B)


def pgroup(p):
    if pc[p] >= MIN_N: return p
    return "multi:other" if p.startswith("multi:") else "other-single"


for b in B: b["pg"] = pgroup(b["path"])


def path_stats(rows):
    n = len(rows)
    if not n: return None
    ms = [r["ms"] for r in rows if r["ms"] is not None]
    d0 = sum(1 for r in rows if r["d"] == 0)
    d1 = sum(1 for r in rows if r["d"] == 1)
    return dict(
        n=n, wallets=len({r["payer"] for r in rows}), launches=len({(r["R"], r["mint"]) for r in rows}),
        d0=pct(d0, n), d1=pct(d1, n), d2p=pct(n - d0 - d1, n),
        first=pct(sum(1 for r in rows if r["pos"] == 0), n),
        pos_med=q([r["pos"] for r in rows], .5), pos_p25=q([r["pos"] for r in rows], .25),
        n_ms=len(ms), ms_p10=q(ms, .10), ms_p25=q(ms, .25), ms_p50=q(ms, .5), ms_p75=q(ms, .75),
        ms_le_ours=pct(sum(1 for x in ms if x <= OURS_MS), len(ms)) if ms else None,
        size_med=q([r["solv"] for r in rows], .5),
        tip_med=q([r["tipv"] for r in rows], .5), tip_pct_med=q([r["tip_pct"] for r in rows if r["tip_pct"] is not None], .5),
        prio_med=q([r["priov"] for r in rows], .5), prio_pct_med=q([r["prio_pct"] for r in rows if r["prio_pct"] is not None], .5),
        cost_pct_med=q([r["cost_pct"] for r in rows if r["cost_pct"] is not None], .5),
        v1=pct(sum(1 for r in rows if r["v1"]), n),
        adj=pct(sum(1 for r in rows if r["adj"]), n))


OUT = {"meta": {}, "tables": {}}
md = []


def table(title, rows, cols, note=None):
    md.append(f"\n### {title}\n")
    if note: md.append(note + "\n")
    md.append("| " + " | ".join(c[0] for c in cols) + " |")
    md.append("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        md.append("| " + " | ".join(c[1](r) for c in cols) + " |")


PATH_COLS = [
    ("Path", lambda r: r["path"]), ("Buys", lambda r: str(r["n"])), ("Wallets", lambda r: str(r["wallets"])),
    ("In create slot %", lambda r: f1(r["d0"])), ("Next slot %", lambda r: f1(r["d1"])), ("Later %", lambda r: f1(r["d2p"])),
    ("1st outside buyer %", lambda r: f1(r["first"])), ("Pos. median", lambda r: f1(r["pos_med"], 0)),
    ("ms p25 / p50 / p75 (n)", lambda r: f"{f1(r['ms_p25'], 0)} / {f1(r['ms_p50'], 0)} / {f1(r['ms_p75'], 0)} ({r['n_ms']})"),
    ("≤74 ms %", lambda r: f1(r["ms_le_ours"], 0)),
    ("Size SOL", lambda r: sol(r["size_med"], 2)), ("Tip SOL", lambda r: sol(r["tip_med"], 4)), ("Tip % size", lambda r: f1(r["tip_pct_med"], 2)),
    ("Prio SOL", lambda r: sol(r["prio_med"], 5)), ("Prio % size", lambda r: f1(r["prio_pct_med"], 2)),
    ("v1 tx %", lambda r: f1(r["v1"], 0))]


def path_table(rows, title, key="pg", note=None, min_n=MIN_N, store=None):
    g = collections.defaultdict(list)
    for r in rows: g[r[key]].append(r)
    out = []
    for p, v in g.items():
        if len(v) < min_n: continue
        s = path_stats(v); s["path"] = p; out.append(s)
    out.sort(key=lambda s: -(s["d0"] or 0))
    table(title, out, PATH_COLS, note)
    if store: OUT["tables"][store] = out
    return out


# ---------- 0. data summary ----------
nb = collections.Counter(b["R"] for b in B)
nl = collections.Counter(x["R"] for x in LCH)
nl_b = collections.Counter(x["R"] for x in LCH if x["n_buys"] > 0)
OUT["meta"] = dict(scope="SOL-quoted launches only", nonsol_buys_excluded=N_NONSOL_BUYS, launches=dict(nl), launches_with_outside_buy=dict(nl_b), outside_buys=dict(nb), failed_outside_txs=len(F),
                   buys_with_ms=sum(1 for b in B if b["ms"] is not None), r2_buys_obs_launch=sum(1 for b in B if b["R"] == "R2" and mint_launch[(b["R"], b["mint"])]["has_obs"]),
                   snipers_data_driven=len(meta["snipers"]), d=dict(collections.Counter(b["d"] for b in B)), ours_ms=OURS_MS,
                   glued_by_jito_bundle=meta["stat"].get("glued_by_jito_bundle"), rpc_sample=len(RS))
md.append("## Tables (generated by l4_report.py)\n")
md.append(f"SOL-quoted launches only ({N_NONSOL_BUYS} of {N_ALL_BUYS} outside buys were on other-quote curves and are left out). "
          f"Data: R1 {nl['R1']} launches ({nl_b['R1']} with an outside buy in S..S+3, {nb['R1']} buys); R2 {nl['R2']} launches ({nl_b['R2']} with one, {nb['R2']} buys). "
          f"Failed outside txs in S..S+3: {len(F)}. Buys with an engine arrival time (R2, 10-22 17:10 UTC on): {OUT['meta']['buys_with_ms']}.\n")

# ---------- 1. main path tables ----------
path_table(B, "T1. All outside OK buys in S..S+3, by landing path (both runs, MEASURED)", store="T1_all",
           note="Path = services of the tip accounts the buy tx paid (tipmap.json); 'none' = no known tip account (priority fee only, or a tip paid in another tx). "
                "ms = arrival in our engine's feed after the create (R2 17:10 UTC on only). Pos. = OK outside buys ahead in chain order (0 = first). "
                "Size/tip/prio are medians per buy.")
path_table([b for b in B if b["R"] == "R1"], "T1a. Run R1 only (10-21 22:07 → 10-22 13:00 UTC)", store="T1_R1")
path_table([b for b in B if b["R"] == "R2"], "T1b. Run R2 only (10-22 15:43 → 10-23 00:35 UTC)", store="T1_R2")
path_table([b for b in B if b["rep"]], "T2. Repeat wallets only (wallet bought ≥10 launches in S..S+3) — excludes most dev side-wallets and one-off users", store="T2_rep")
path_table([b for b in B if b["rep"] and b["solv"] >= 0.5], "T2b. Repeat wallets, buys ≥0.5 SOL (sniper-sized)", store="T2b_rep_big", min_n=20)

# ---------- 2. leader client split ----------
def cell_stats(rows):
    n = len(rows)
    ms = [r["ms"] for r in rows if r["ms"] is not None]
    return dict(n=n, d0=pct(sum(1 for r in rows if r["d"] == 0), n), ms50=q(ms, .5), nms=len(ms))


def cross(rows, key2, order2, title, store, min_n=15, note=None, paths=None):
    g = collections.defaultdict(list)
    for r in rows: g[(r["pg"], r[key2])].append(r)
    paths = paths or [p for p, _ in collections.Counter(r["pg"] for r in rows).most_common() if sum(len(g[(p, k)]) for k in order2) >= 100]
    res = {}
    md.append(f"\n### {title}\n")
    if note: md.append(note + "\n")
    md.append("| Path | " + " | ".join(order2) + " |")
    md.append("|---|" + "|".join("---" for _ in order2) + "|")
    for p in paths:
        cells = []
        for k in order2:
            v = g.get((p, k), [])
            s = cell_stats(v); res[f"{p}|{k}"] = s
            cells.append("–" if s["n"] < min_n else f"{f1(s['d0'], 0)}% / {f1(s['ms50'], 0)} ms ({s['n']})")
        md.append(f"| {p} | " + " | ".join(cells) + " |")
    OUT["tables"][store] = res


CG = ["BAM", "Jito-Solana", "Harmonic", "Firedancer", "Rakurai", "Agave"]
cross(B, "cgroup", CG, "T3. By the landing slot's leader client: in-create-slot % / median ms (n buys)", "T3_client",
      note="Leader = getSlotLeaders for the buy's slot; client = getClusterNodes clientId (now), fallback older snapshots. Cells with <15 buys: –.")
cross([b for b in B if b["rep"]], "cgroup", CG, "T3b. Same, repeat wallets only", "T3b_client_rep")
cross(B, "cpos", ["early", "mid", "late"], "T4. By where the create sits in its block (create index / max index seen in the slot): in-create-slot % / median ms (n)", "T4_cpos",
      note="early = first third of the block, late = last third (INFERRED proxy for time-in-slot; the block's true tx count is ≥ the max index we saw).")
cross(B, "region", ["Frankfurt/DE", "EU-other", "N-America", "Asia"], "T5. By the landing leader's region (leader_geo.json, epoch 1063): in-create-slot % / median ms (n)", "T5_region")

# ---------- 3. first outside buyer ----------
firsts = collections.Counter(); allp = collections.Counter()
for b in B: allp[b["pg"]] += 1
nfl = 0
for x in LCH:
    if x["first"]:
        nfl += 1
for b in B:
    if b["pos"] == 0: firsts[b["pg"]] += 1
rows = []
for p, n in allp.most_common():
    if n < MIN_N: continue
    rows.append(dict(path=p, share_all=pct(n, len(B)), share_first=pct(firsts[p], nfl), ratio=(pct(firsts[p], nfl) / pct(n, len(B))) if n else None, n_first=firsts[p]))
rows.sort(key=lambda r: -(r["ratio"] or 0))
table("T6. Who is the FIRST outside buyer (launches with ≥1 outside buy in S..S+3)", rows,
      [("Path", lambda r: r["path"]), ("Share of all buys %", lambda r: f1(r["share_all"])), ("Share of first buys %", lambda r: f1(r["share_first"])),
       ("Ratio (first/all)", lambda r: f1(r["ratio"], 2)), ("Launches won", lambda r: str(r["n_first"]))],
      note=f"{nfl} launches. Ratio > 1 = the path wins the first slot more often than its usage share.")
OUT["tables"]["T6_first"] = rows

# ---------- 4. within-wallet comparison ----------
# cells = (wallet, leader client group); compare paths inside a cell, then weight by buys
cells = collections.defaultdict(list)
for b in B:
    if b["path"] == "none" or not b["path"].startswith("multi:"):
        cells[(b["payer"], b["cgroup"])].append(b)
    else:
        cells[(b["payer"], b["cgroup"])].append(b)
lift = collections.defaultdict(lambda: [0.0, 0, 0.0, 0])   # path -> [sum n*(d0_p - d0_cell), n, sum nms*(ms_p - ms_cell), nms]
pairs = collections.Counter()
for key, v in cells.items():
    byp = collections.defaultdict(list)
    for b in v: byp[b["pg"]].append(b)
    good = {p: x for p, x in byp.items() if len(x) >= 5}
    if len(good) < 2: continue
    tot = sum(len(x) for x in good.values())
    d0c = sum(1 for x in good.values() for b in x if b["d"] == 0) / tot
    msall = [b["ms"] for x in good.values() for b in x if b["ms"] is not None]
    msc = q(msall, .5)
    for p, x in good.items():
        n = len(x); d0p = sum(1 for b in x if b["d"] == 0) / n
        lift[p][0] += n * (d0p - d0c); lift[p][1] += n
        mp = [b["ms"] for b in x if b["ms"] is not None]
        if len(mp) >= 3 and msc is not None:
            lift[p][2] += len(mp) * (q(mp, .5) - msc); lift[p][3] += len(mp)
        pairs[p] += 1
rows = []
for p, (s, n, sm, nm) in lift.items():
    if n < 30: continue
    rows.append(dict(path=p, cells=pairs[p], n=n, d0_lift=100 * s / n, ms_lift=(sm / nm) if nm else None, n_ms=nm))
rows.sort(key=lambda r: -r["d0_lift"])
table("T7. Within-wallet comparison (same wallet, same leader client; paths with ≥5 buys each)", rows,
      [("Path", lambda r: r["path"]), ("Wallet×client cells", lambda r: str(r["cells"])), ("Buys", lambda r: str(r["n"])),
       ("In-create-slot vs. same wallet's other paths (pp)", lambda r: f"{r['d0_lift']:+.1f}"),
       ("Median ms vs. same wallet's other paths", lambda r: "–" if r["ms_lift"] is None else f"{r['ms_lift']:+.0f} ({r['n_ms']})")],
      note="Controls for the wallet's own detection speed, location and sizing. Positive pp / negative ms = this path lands earlier than the same bot's other paths. "
           "Caveat: for durable-nonce fan-out bots the landed path is the race winner, so its slot/ms reflect the launch, not the path; use T13 for those.")
OUT["tables"]["T7_within"] = rows

# ---------- 5. fastest consistent snipers ----------
byw = collections.defaultdict(list)
for b in B: byw[b["payer"]].append(b)
srows = []
for w, v in byw.items():
    L = {(b["R"], b["mint"]) for b in v}
    if len(L) < 20: continue
    first_per_launch = {}
    for b in sorted(v, key=lambda b: (b["s"], b["i"])):
        first_per_launch.setdefault((b["R"], b["mint"]), b)
    fv = list(first_per_launch.values())
    ms = [b["ms"] for b in fv if b["ms"] is not None]
    pm = collections.Counter(b["pg"] for b in fv)
    rs = [RS[b["sig"]] for b in v if b["sig"] in RS and not RS[b["sig"]].get("missing")]
    srows.append(dict(w=mw(w), wp=wp(w), launches=len(L), d0=pct(sum(1 for b in fv if b["d"] == 0), len(fv)),
                      first=pct(sum(1 for b in fv if b["pos"] == 0), len(fv)), pos_med=q([b["pos"] for b in fv], .5),
                      ms50=q(ms, .5), ms25=q(ms, .25), nms=len(ms), paths=", ".join(f"{p} {100 * n / len(fv):.0f}%" for p, n in pm.most_common(3)),
                      size=q([b["solv"] for b in fv], .5), tip_pct=q([b["tip_pct"] for b in fv if b["tip_pct"] is not None], .5),
                      prio_pct=q([b["prio_pct"] for b in fv if b["prio_pct"] is not None], .5), cost_pct=q([b["cost_pct"] for b in fv if b["cost_pct"] is not None], .5),
                      v1=pct(sum(1 for b in fv if b["v1"]), len(fv)), adj=sum(1 for b in fv if b["adj"]),
                      nonce=(f"{sum(1 for x in rs if x.get('nonce'))}/{len(rs)}" if rs else "–"),
                      ver=(",".join(sorted({str(x.get('ver')) for x in rs})) if rs else "–"),
                      ex=min(fv, key=lambda b: (b["d"], b["ms"] if b["ms"] is not None else 9e9, b["pos"]))["sig"], _rawtmp=w))
srows.sort(key=lambda r: (-(r["d0"] or 0), r["pos_med"]))
for r in srows: r["_raw"] = r.pop("_rawtmp")
OUT["tables"]["T8_snipers"] = [{k: v for k, v in r.items() if k != "_raw"} for r in srows]
table("T8. Fastest consistent snipers (wallets with ≥20 launches bought in S..S+3; first buy per launch), top 30 by in-create-slot share", srows[:30],
      [("Wallet", lambda r: r["wp"]), ("Launches", lambda r: str(r["launches"])), ("In create slot %", lambda r: f1(r["d0"], 0)),
       ("1st outside %", lambda r: f1(r["first"], 0)), ("Pos. med", lambda r: f1(r["pos_med"], 0)), ("ms p50 (n)", lambda r: f"{f1(r['ms50'], 0)} ({r['nms']})"),
       ("Paths", lambda r: r["paths"]), ("Size", lambda r: sol(r["size"], 2)), ("Tip %", lambda r: f1(r["tip_pct"], 2)), ("Prio %", lambda r: f1(r["prio_pct"], 2)),
       ("v1 %", lambda r: f1(r["v1"], 0)), ("Nonce (RPC sample)", lambda r: r["nonce"]), ("Example", lambda r: f"[tx](https://solscan.io/tx/{r['ex']})")])

# ---------- 6. v1 / nonce vs landing ----------
def vrow(name, rows):
    s = path_stats(rows) if rows else None
    return dict(name=name, **(s or {"n": 0}))


vr = [vrow("v1 tx (fee in header) — all", [b for b in B if b["v1"]]), vrow("legacy/v0 (compute-budget ix) — all", [b for b in B if not b["v1"]]),
      vrow("v1 — repeat wallets", [b for b in B if b["v1"] and b["rep"]]), vrow("legacy/v0 — repeat wallets", [b for b in B if not b["v1"] and b["rep"]])]
for pth in ["landx", "helius", "nozomi", "astralane", "jito", "none"]:
    vr.append(vrow(f"{pth}: v1", [b for b in B if b["v1"] and b["path"] == pth]))
    vr.append(vrow(f"{pth}: legacy/v0", [b for b in B if not b["v1"] and b["path"] == pth]))
rsb = [(b, RS[b["sig"]]) for b in B if b["sig"] in RS and not RS[b["sig"]].get("missing") and RS[b["sig"]].get("grp") in ("A_top", "B_ok")]
vr.append(vrow("RPC sample: durable nonce", [b for b, x in rsb if x.get("nonce")]))
vr.append(vrow("RPC sample: no nonce", [b for b, x in rsb if not x.get("nonce")]))
rsr = [(b, RS[b["sig"]]) for b in B if b["sig"] in RS and RS[b["sig"]].get("grp") == "B_ok" and not RS[b["sig"]].get("missing")]
vr.append(vrow("RPC random OK sample: nonce", [b for b, x in rsr if x.get("nonce")]))
vr.append(vrow("RPC random OK sample: no nonce", [b for b, x in rsr if not x.get("nonce")]))
vr = [r for r in vr if r["n"]]
table("T9. Tx format vs landing", vr, [("Group", lambda r: r["name"]), ("Buys", lambda r: str(r["n"])), ("Wallets", lambda r: str(r.get("wallets", "–"))),
      ("In create slot %", lambda r: f1(r.get("d0"))), ("1st outside %", lambda r: f1(r.get("first"))),
      ("ms p25 / p50 (n)", lambda r: f"{f1(r.get('ms_p25'), 0)} / {f1(r.get('ms_p50'), 0)} ({r.get('n_ms', 0)})"), ("Tip % size", lambda r: f1(r.get("tip_pct_med"), 2))],
      note="v1 = no compute-budget instruction but fee > 5000 × signers (fee set in the v1 header; INFERRED from the collector fields, checked against RPC 'version' in the sample).")
OUT["tables"]["T9_format"] = vr
# check the v1 inference against the RPC version field
chk = collections.Counter()
for b in B:
    x = RS.get(b["sig"])
    if x and not x.get("missing"): chk[(b["v1"], str(x.get("ver")))] += 1
OUT["meta"]["v1_inference_check"] = {f"{k[0]}|{k[1]}": v for k, v in chk.items()}
nonce_rate = collections.Counter()
for b, x in rsr: nonce_rate[(b["pg"], bool(x.get("nonce")))] += 1
OUT["meta"]["nonce_random_sample_by_path"] = {f"{k[0]}|{k[1]}": v for k, v in nonce_rate.items()}

# ---------- 7. separate-tx fan-out natural experiment ----------
# wallets whose landed buys come through >=2 different single-service paths (each buy pays exactly one service) and that use a
# durable nonce (RPC sample) or v1: only one of the per-service copies can land, so the landed path = the copy that won the race.
fan = []
for w, v in byw.items():
    L = {(b["R"], b["mint"]) for b in v}
    if len(L) < 15: continue
    single = [b for b in v if b["path"] != "none" and not b["path"].startswith("multi:")]
    pm = collections.Counter(b["path"] for b in single)
    if len(single) < 15 or len(pm) < 2 or pm.most_common(1)[0][1] > 0.9 * len(single): continue
    rs = [RS[b["sig"]] for b in v if b["sig"] in RS and not RS[b["sig"]].get("missing")]
    dup = sum(1 for k in L if sum(1 for b in v if (b["R"], b["mint"]) == k) > 1)
    fan.append(dict(w=mw(w), wp=wp(w), launches=len(L), single=len(single), mix=", ".join(f"{p} {100 * n / len(single):.0f}%" for p, n in pm.most_common(6)),
                    d0=pct(sum(1 for b in v if b["d"] == 0), len(v)), nonce=(f"{sum(1 for x in rs if x.get('nonce'))}/{len(rs)}" if rs else "–"),
                    v1=pct(sum(1 for b in v if b["v1"]), len(v)), dup_launches=dup, mixd={p: n for p, n in pm.items()},
                    ms_by={p: q([b["ms"] for b in single if b["path"] == p and b["ms"] is not None], .5) for p in pm}))
fan.sort(key=lambda r: -r["launches"])
OUT["tables"]["T10_fanout"] = fan
table("T10. Wallets whose landed buys switch between single-service paths (possible separate-tx fan-out race)", fan[:25],
      [("Wallet", lambda r: r["wp"]), ("Launches", lambda r: str(r["launches"])), ("Single-path buys", lambda r: str(r["single"])),
       ("Landed path mix", lambda r: r["mix"]), ("In create slot %", lambda r: f1(r["d0"], 0)), ("Nonce (sample)", lambda r: r["nonce"]),
       ("v1 %", lambda r: f1(r["v1"], 0)), ("Launches with 2+ buys", lambda r: str(r["dup_launches"]))],
      note="If such a wallet sends one copy per service with a durable nonce, only the fastest copy can land, so the landed mix = race wins. "
           "Without a nonce several copies can land (then 'launches with 2+ buys' is high) and the mix is just routing.")

# ---------- 8. failed txs (RPC sample) ----------
fs = [x for x in RS.values() if x.get("grp") in ("C_failbuy", "C_failnoix") and not x.get("missing")]
fr = collections.Counter(); frn = collections.Counter()
for x in fs:
    tk = x.get("tip_keys") or []
    p = "none" if not tk else (tk[0] if len(tk) == 1 else "multi:" + "+".join(tk))
    (fr if x["grp"] == "C_failbuy" else frn)[p] += 1
nfb = sum(1 for f in F if f["buyix"]); nfn = sum(1 for f in F if f["noix"])
rows = []
for p in sorted(set(fr) | set(frn), key=lambda p: -(fr[p] + frn[p])):
    est_b = nfb * fr[p] / max(1, sum(fr.values())); est_n = nfn * frn[p] / max(1, sum(frn.values()))
    ok = pc.get(p, 0)
    rows.append(dict(path=p, s_failbuy=fr[p], s_noix=frn[p], est_failbuy=est_b, est_noix=est_n, ok=ok,
                     fail_rate_buyix=pct(est_b, est_b + ok) if (est_b + ok) else None))
OUT["tables"]["T11_fail"] = rows
table("T11. Failed outside txs in S..S+3 by path (RPC sample of failed txs → path; scaled to all failed txs)", rows[:16],
      [("Path", lambda r: r["path"]), ("Sample: failed buy ix", lambda r: str(r["s_failbuy"])), ("Sample: guard fail (no pump ix)", lambda r: str(r["s_noix"])),
       ("Est. failed buys", lambda r: f1(r["est_failbuy"], 0)), ("OK buys", lambda r: str(r["ok"])), ("Est. fail rate of buy attempts %", lambda r: f1(r["fail_rate_buyix"], 0))],
      note=f"Population: {nfb} failed txs with a pump.fun buy instruction, {nfn} failed txs that never reached pump.fun (a bot's own guard program aborting), "
           f"{len(F) - nfb - nfn} other. Failed txs are dominated by a few spam wallets; the rate is a property of those bots more than of the path. Tips revert on failure.")

# ---------- 9. our 74 ms in context ----------
ms0 = [b["ms"] for b in B if b["ms"] is not None]
d0ms = [b["ms"] for b in B if b["ms"] is not None and b["d"] == 0]
by_launch = collections.defaultdict(list)
for b in B:
    if b["ms"] is not None: by_launch[(b["R"], b["mint"])].append(b["ms"])
n_ahead = [sum(1 for x in v if x < OURS_MS) for v in by_launch.values()]
OUT["meta"]["ours_context"] = dict(share_of_matched_buys_faster=pct(sum(1 for x in ms0 if x < OURS_MS), len(ms0)),
                                   share_of_create_slot_buys_faster=pct(sum(1 for x in d0ms if x < OURS_MS), len(d0ms)),
                                   launches_with_buys=len(by_launch), mean_buys_ahead_at_74=(sum(n_ahead) / len(n_ahead)) if n_ahead else None,
                                   share_launches_with_any_buy_before_74=pct(sum(1 for x in n_ahead if x > 0), len(n_ahead)))
# examples per path
ex = {}
for p in [r["path"] for r in OUT["tables"]["T1_all"]]:
    v = [b for b in B if b["pg"] == p and b["d"] == 0 and b["ms"] is not None]
    if not v: v = [b for b in B if b["pg"] == p and b["d"] == 0]
    if not v: continue
    v.sort(key=lambda b: (b["ms"] if b["ms"] is not None else b["pos"]))
    pick = [v[0], v[len(v) // 2]]
    ex[p] = [dict(sig=b["sig"], ms=b["ms"], pos=b["pos"], d=b["d"], sol=round(b["solv"], 3), tip=round(b["tipv"], 5), wallet=wp(b["payer"]), client=b["cgroup"]) for b in pick]
OUT["examples"] = ex
md.append("\n### T12. Example transactions per path (fastest and median create-slot buy)\n")
md.append("| Path | Fastest | Median |")
md.append("|---|---|---|")
for p, v in ex.items():
    cells = [f"[{x['ms'] if x['ms'] is not None else '–'} ms, pos {x['pos']}, {x['sol']} SOL, {x['client']}](https://solscan.io/tx/{x['sig']})" for x in v]
    md.append(f"| {p} | " + " | ".join(cells) + " |")


# ---------- 10. race among nonce fan-out wallets (natural experiment) ----------
def nonce_info(v):
    rs = [RS[b["sig"]] for b in v if b["sig"] in RS and not RS[b["sig"]].get("missing") and "nonce" in RS[b["sig"]]]
    return sum(1 for x in rs if x.get("nonce")), len(rs)


race_w = []
for w, v in byw.items():
    L = {(b["R"], b["mint"]) for b in v}
    if len(L) < 15: continue
    firstb = {}
    for b in sorted(v, key=lambda b: (b["s"], b["i"])): firstb.setdefault((b["R"], b["mint"]), b)
    fv = list(firstb.values())
    pm = collections.Counter(b["pg"] for b in fv)
    used = [p for p, n in pm.items() if n >= max(2, 0.05 * len(fv))]
    if len(used) < 2 or pm.most_common(1)[0][1] > 0.9 * len(fv): continue
    dup = sum(1 for b in v) - len(fv)
    nn, nt = nonce_info(v)
    if dup > 0.05 * len(L) or nt == 0 or nn < 0.66 * nt: continue
    race_w.append((w, [b for b in fv if b["pg"] in used]))


def pairs_of(cells):
    pr = collections.defaultdict(lambda: [0, 0]); wm = collections.defaultdict(lambda: [0, 0])
    for c in cells:
        ks = sorted(c)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b2 = ks[i], ks[j]
                pr[(a, b2)][0] += c[a]; pr[(a, b2)][1] += c[b2]
                if c[a] != c[b2]: wm[(a, b2)][0 if c[a] > c[b2] else 1] += 1
    return pr, wm


def share_vs_all(pr, a):
    num = den = 0
    for (x, y), (wx, wy) in pr.items():
        if a == x: num += wx; den += wx + wy
        elif a == y: num += wy; den += wx + wy
    return ((100 * num / den) if den else None), den


def pget(pr, a, b2):
    if (a, b2) in pr: return pr[(a, b2)]
    if (b2, a) in pr: return pr[(b2, a)][::-1]
    return [0, 0]


cells_all = []; cells_by = collections.defaultdict(list); wins_tot = collections.Counter(); present = collections.Counter()
grp_wins = collections.defaultdict(collections.Counter); win_rows = collections.defaultdict(list)
for w, fv in race_w:
    cm = collections.defaultdict(collections.Counter)
    for b in fv:
        cm[b["cgroup"]][b["pg"]] += 1; win_rows[b["pg"]].append(b)
    for g, c in cm.items():
        if sum(c.values()) < 5: continue
        cells_all.append(c); cells_by[g].append(c)
        for a in c: present[a] += 1; wins_tot[a] += c[a]; grp_wins[g][a] += c[a]
pr, wm = pairs_of(cells_all)
svc_list = [a for a, _ in wins_tot.most_common() if wins_tot[a] >= 20]
rows = []
for a in svc_list:
    sh, den = share_vs_all(pr, a)
    wmaj = [0, 0]
    for (x, y), (wx, wy) in wm.items():
        if a == x: wmaj[0] += wx; wmaj[1] += wy
        elif a == y: wmaj[0] += wy; wmaj[1] += wx
    rr = win_rows[a]
    rows.append(dict(path=a, wins=wins_tot[a], cells=present[a], pairwise=sh, races=den, wallet_major=pct(wmaj[0], sum(wmaj)),
                     tip_med=q([b["tipv"] for b in rr], .5), tip_pct=q([b["tip_pct"] for b in rr if b["tip_pct"] is not None], .5),
                     prio_pct=q([b["prio_pct"] for b in rr if b["prio_pct"] is not None], .5), size=q([b["solv"] for b in rr], .5),
                     d0=pct(sum(1 for b in rr if b["d"] == 0), len(rr)), ms50=q([b["ms"] for b in rr if b["ms"] is not None], .5)))
rows.sort(key=lambda r: -(r["pairwise"] or 0))
by_client_rows = {}
for g in ["BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
    prg, _ = pairs_of(cells_by[g])
    by_client_rows[g] = {a: share_vs_all(prg, a) for a in svc_list}
OUT["tables"]["T13_race"] = dict(n_wallets=len(race_w), wallets=[wp(w) for w, _ in race_w], rows=rows,
                                  pairs={f"{a}|{b}": v for (a, b), v in pr.items() if v[0] + v[1] >= 10},
                                  by_client_pairwise={g: {a: v for a, v in d.items()} for g, d in by_client_rows.items()},
                                  wins_by_client={g: dict(c) for g, c in grp_wins.items()})
table(f"T13. Race among {len(race_w)} durable-nonce fan-out wallets: which path's copy lands (same wallet, same leader client)", rows,
      [("Path", lambda r: r["path"]), ("Landed buys", lambda r: str(r["wins"])), ("Wallet×client cells", lambda r: str(r["cells"])),
       ("Pairwise win share % (races)", lambda r: f"{f1(r['pairwise'], 0)} ({r['races']})"), ("Wallet-majority share %", lambda r: f1(r["wallet_major"], 0)),
       ("Winners: in create slot %", lambda r: f1(r["d0"], 0)), ("Winners: ms p50", lambda r: f1(r["ms50"], 0)),
       ("Tip SOL (tip % size)", lambda r: f"{sol(r['tip_med'], 4)} ({f1(r['tip_pct'], 2)})"), ("Prio % size", lambda r: f1(r["prio_pct"], 2))],
      note="Wallets: ≥15 launches, first buy per launch, ≥2 paths each ≥5% of their launches, ≤5% extra buys (double landings), durable nonce in the RPC sample. "
           "If such a wallet sends one copy per path at the same time (INFERRED from nonce + switching paths + no double buys), the landed path = the copy that arrived first. "
           "Pairwise share = A's wins / (A's + B's wins) summed over wallet×client cells where both won at least once; wallet-majority = share of those cells where A won more often. "
           "We only see winners: a path a wallet sends to but never wins with is invisible, and each wallet's own tip per path is part of the race.")
top = [r["path"] for r in rows][:11]
md.append("\nPairwise detail (row A vs column B: A's share of the races; races counted):\n")
md.append("| A \\ B | " + " | ".join(top) + " |")
md.append("|---|" + "|".join("---" for _ in top) + "|")
for a in top:
    cc = []
    for b2 in top:
        if a == b2: cc.append("·"); continue
        wa, wb = pget(pr, a, b2)
        cc.append("–" if wa + wb < 10 else f"{100 * wa / (wa + wb):.0f}% ({wa + wb})")
    md.append(f"| {a} | " + " | ".join(cc) + " |")
md.append("\nPairwise win share by the landing leader's client (races counted):\n")
md.append("| Path | BAM | Jito-Solana | Harmonic | Firedancer |")
md.append("|---|---|---|---|---|")
for a in top:
    cc = []
    for g in ["BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
        sh, den = by_client_rows[g].get(a, (None, 0))
        cc.append("–" if not den or den < 20 else f"{sh:.0f}% ({den})")
    md.append(f"| {a} | " + " | ".join(cc) + " |")
md.append("\nShare of each client's landed buys among these wallets (%):\n")
md.append("| Client | " + " | ".join(top) + " | n |")
md.append("|---|" + "|".join("---" for _ in top) + "|---|")
for g in ["BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
    c = grp_wins.get(g, collections.Counter()); n = sum(c.values())
    md.append(f"| {g} | " + " | ".join(f1(pct(c[a], n), 0) for a in top) + f" | {n} |")

# per-client race matrices for the main paths
KEYS = ["helius", "jito", "landx", "speedlanding", "nozomi", "astralane", "none", "bolt", "flashblock", "0slot"]
OUT["tables"]["T13b_race_matrix_by_client"] = {}
for gname, gs in [("BAM + Jito-Solana", ("BAM", "Jito-Solana")), ("Harmonic", ("Harmonic",)), ("Firedancer", ("Firedancer",))]:
    cells = []
    for w, fv in race_w:
        for gg in gs:
            c = collections.Counter(b["pg"] for b in fv if b["cgroup"] == gg)
            if sum(c.values()) >= 5: cells.append(c)
    prg, _ = pairs_of(cells)
    OUT["tables"]["T13b_race_matrix_by_client"][gname] = {f"{a}|{b2}": pget(prg, a, b2) for a in KEYS for b2 in KEYS if a < b2 and sum(pget(prg, a, b2)) >= 15}
    md.append(f"\nRace matrix on {gname} leaders (row A's share vs column B; races; – = fewer than 15):\n")
    md.append("| A \\ B | " + " | ".join(KEYS) + " |")
    md.append("|---|" + "|".join("---" for _ in KEYS) + "|")
    for a in KEYS:
        cc = []
        for b2 in KEYS:
            if a == b2: cc.append("·"); continue
            wa, wb = pget(prg, a, b2)
            cc.append("–" if wa + wb < 15 else f"{100 * wa / (wa + wb):.0f}% ({wa + wb})")
        md.append(f"| {a} | " + " | ".join(cc) + " |")

# benchmark: what the fastest consistent snipers achieve
def bench(rows):
    ms = [b["ms"] for b in rows if b["ms"] is not None]
    return dict(n=len(rows), d0=pct(sum(1 for b in rows if b["d"] == 0), len(rows)), ms25=q(ms, .25), ms50=q(ms, .5), nms=len(ms))
top20 = [r["_raw"] for r in srows if r["launches"] >= 50][:20]
trows = []
for w in top20:
    fb = {}
    for b in sorted(byw[w], key=lambda b: (b["s"], b["i"])): fb.setdefault((b["R"], b["mint"]), b)
    trows += list(fb.values())
allrw = [b for _, fv in race_w for b in fv]
brow = []
for name, rows_ in [("Top-20 fastest consistent snipers (≥50 launches)", trows), ("All durable-nonce fan-out wallets (T13)", allrw)]:
    for g in ["all", "BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
        v = rows_ if g == "all" else [b for b in rows_ if b["cgroup"] == g]
        brow.append(dict(set=name, client=g, **bench(v)))
    if name.startswith("Top"):
        for cp in ["early", "mid", "late"]:
            brow.append(dict(set=name, client=f"create {cp} in block", **bench([b for b in rows_ if b["cpos"] == cp])))
pmix = collections.Counter(b["pg"] for b in trows)
nn_, nt_ = nonce_info([b for w in top20 for b in byw[w]])
OUT["tables"]["T16_benchmark"] = dict(top20=[wp(w) for w in top20], rows=brow, path_mix={p: pct(n, len(trows)) for p, n in pmix.most_common()},
                                      nonce_sampled=[nn_, nt_], v1_share=pct(sum(1 for b in trows if b["v1"]), len(trows)))
table("T16. Benchmark: where the best fan-out snipers land (first buy per launch)", brow,
      [("Set", lambda r: r["set"]), ("Slice", lambda r: r["client"]), ("Buys", lambda r: str(r["n"])), ("In create slot %", lambda r: f1(r["d0"], 0)),
       ("ms p25 / p50 (n)", lambda r: f"{f1(r['ms25'], 0)} / {f1(r['ms50'], 0)} ({r['nms']})")],
      note="Top-20 = T8 order (in-create-slot share), wallets with ≥50 launches: " + ", ".join(wp(w) for w in top20) + ". "
           + "Their landed path mix: " + ", ".join(f"{p} {100 * n / len(trows):.0f}%" for p, n in pmix.most_common(8))
           + f". Durable nonce in {nn_} of {nt_} sampled txs; v1 format {pct(sum(1 for b in trows if b['v1']), len(trows)):.0f}% of their buys.")

# ---------- 11. within-wallet v1 vs legacy ----------
vcell = collections.defaultdict(lambda: {True: [], False: []})
for b in B: vcell[(b["payer"], b["pg"])][b["v1"]].append(b)
dd = []; dm = []; nb_ = 0
for k, v in vcell.items():
    if len(v[True]) >= 5 and len(v[False]) >= 5:
        a = sum(1 for b in v[True] if b["d"] == 0) / len(v[True]); c_ = sum(1 for b in v[False] if b["d"] == 0) / len(v[False])
        n = len(v[True]) + len(v[False]); dd.append((n, a - c_)); nb_ += n
        m1 = [b["ms"] for b in v[True] if b["ms"] is not None]; m0 = [b["ms"] for b in v[False] if b["ms"] is not None]
        if len(m1) >= 3 and len(m0) >= 3: dm.append((len(m1) + len(m0), q(m1, .5) - q(m0, .5)))
OUT["tables"]["T14_v1_within"] = dict(cells=len(dd), buys=nb_, d0_diff_pp=(100 * sum(n * x for n, x in dd) / sum(n for n, _ in dd)) if dd else None,
                                      ms_diff=(sum(n * x for n, x in dm) / sum(n for n, _ in dm)) if dm else None, ms_cells=len(dm))
md.append(f"\n### T14. Same wallet, same path: v1 vs legacy/v0 txs\n\n{len(dd)} wallet×path cells with ≥5 buys of each format ({nb_} buys): "
          f"in-create-slot difference v1 − legacy = {f1(OUT['tables']['T14_v1_within']['d0_diff_pp'])} pp; median-ms difference = "
          f"{f1(OUT['tables']['T14_v1_within']['ms_diff'], 0)} ms over {len(dm)} cells with ms.\n")

# ---------- 12. what landing time T buys us (R2 launches with engine timelines) ----------
lt = []
cover = collections.Counter()
for b in B:
    if b["R"] == "R2" and mint_launch[(b["R"], b["mint"])]["has_obs"]:
        cover["buys"] += 1; cover["matched"] += b["ms"] is not None
byl = collections.defaultdict(list)
for b in B:
    if b["R"] == "R2" and mint_launch[(b["R"], b["mint"])]["has_obs"]: byl[(b["R"], b["mint"])].append(b)
contested = {k for k, v in byl.items() if len({b["payer"] for b in v if b["d"] <= 1}) >= 3}
for T in [10, 20, 30, 40, 50, 74, 100, 150]:
    for name, keys in [("all launches with ≥1 outside buy", list(byl)), ("contested (≥3 outside wallets in S..S+1)", sorted(contested))]:
        ahead = []; first = 0
        for k in keys:
            n_ahead = sum(1 for b in byl[k] if b["ms"] is not None and b["ms"] < T)
            ahead.append(n_ahead); first += n_ahead == 0
        lt.append(dict(T=T, set=name, launches=len(keys), first_pct=pct(first, len(keys)), mean_ahead=(sum(ahead) / len(ahead)) if ahead else None,
                       med_ahead=q(ahead, .5)))
OUT["tables"]["T15_landing_time"] = dict(rows=lt, coverage=dict(cover))
table("T15. If our buy arrived T ms after the create: share of launches where we would be the first outside buyer, and outside buys ahead (R2, engine clock)", lt,
      [("T ms", lambda r: str(r["T"])), ("Launch set", lambda r: r["set"]), ("Launches", lambda r: str(r["launches"])),
       ("First outside buyer %", lambda r: f1(r["first_pct"], 0)), ("Mean buys ahead", lambda r: f1(r["mean_ahead"], 2))],
      note=f"Only buys matched to the engine timeline count as 'ahead' ({cover['matched']} of {cover['buys']} buys in these launches matched), so this slightly flatters late T.")

json.dump(OUT, open(OUTJ, "w"), indent=1, default=str)
open(OUTM, "w").write("\n".join(md) + "\n")
print("wrote", OUTM, OUTJ)
print(json.dumps(OUT["meta"], indent=1, default=str)[:3000])
