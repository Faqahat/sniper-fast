#!/usr/bin/env python3
# LANDING-PATH STUDY, step 5 (READ-ONLY, offline): curated summary tables for LANDING_PATHS.md from landing_stats.json
# (+ leader slot shares from the getSlotLeaders cache). Writes work/summary_tables.md.
# usage: python3 -I l5_summary.py
import json, os, collections

D = "/home/moiz/sniper/ops/overnight/landing"
S = json.load(open(os.path.join(D, "landing_stats.json")))
T = S["tables"]
W = os.path.join(D, "work")


def f(x, nd=0):
    return "–" if x is None else f"{x:.{nd}f}"


t1 = {r["path"]: r for r in T["T1_all"]}
t2b = {r["path"]: r for r in T["T2b_rep_big"]}
t6 = {r["path"]: r for r in T["T6_first"]}
race = {r["path"]: r for r in T["T13_race"]["rows"]}
bycl = T["T13_race"]["by_client_pairwise"]
t3 = T["T3_client"]
md = []

# S1: one row per main path
PATHS = ["landx", "speedlanding", "helius", "jito", "none", "astralane", "nozomi", "bolt", "flashblock", "node1", "soyas", "stellium",
         "0slot", "blockrazor", "nextblock", "rpcfast", "falcon", "lunar", "multi:helius+jito"]
md.append("| Path | All buys: in create slot % · ms p50 · first-buyer ratio (n) | Sniper-sized (repeat wallets, ≥0.5 SOL): in create slot % · ms p50 · tip % of size (n) | Head-to-head race win % (wallet-majority %) | Race: client where it wins most |")
md.append("|---|---|---|---|---|")
for p in PATHS:
    a = t1.get(p); b = t2b.get(p); r = race.get(p); fr = t6.get(p)
    c1 = "–" if not a else f"{f(a['d0'])} · {f(a['ms_p50'])} · {f(fr['ratio'], 2) if fr else '–'} ({a['n']})"
    c2 = "–" if not b else f"{f(b['d0'])} · {f(b['ms_p50'])} · {f(b['tip_pct_med'], 2)} ({b['n']})"
    c3 = "–" if not r else f"{f(r['pairwise'])} ({f(r['wallet_major'])})"
    best = []
    for g in ["BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
        v = (bycl.get(g) or {}).get(p)
        if v and v[1] and v[1] >= 50: best.append((v[0], g, v[1]))
    best.sort(reverse=True)
    c4 = "–" if not best else ", ".join(f"{g} {s:.0f}%" for s, g, n in best[:2])
    label = "none (no tip: priority fee only)" if p == "none" else p
    md.append(f"| {label} | {c1} | {c2} | {c3} | {c4} |")
open(os.path.join(W, "summary_S1.md"), "w").write("\n".join(md) + "\n")

# S2: per leader client
L = json.load(open(os.path.join(W, "rpc/leaders.json")))
cn = json.load(open(os.path.join(W, "rpc/clusternodes_now.json")))["nodes"]
def grp(c):
    if c in ("AgaveBam", "FireBAM"): return "BAM"
    if c in ("HarmonicAgave", "HarmonicFiredancer"): return "Harmonic"
    if c == "JitoLabs": return "Jito-Solana"
    if c in ("Firedancer", "Frankendancer"): return "Firedancer"
    return "other"
cnt = collections.Counter()
for s, l in L.items():
    s = int(s)
    if 459792100 <= s <= 460044300 or 460090400 <= s <= 460241000:
        cnt[grp((cn.get(l) or {}).get("clientId"))] += 1
tot = sum(cnt.values())
md = ["| Leader client | Share of slots | Race leaders (win % vs. the same bots' other paths; races) | Population: best in-create-slot % · ms p50 (n buys) |", "|---|---|---|---|"]
for g in ["BAM", "Jito-Solana", "Harmonic", "Firedancer"]:
    rl = [(v[0], p, v[1]) for p, v in (bycl.get(g) or {}).items() if v and v[1] and v[1] >= 100]
    rl.sort(reverse=True)
    pop = []
    for k, v in t3.items():
        p, gg = k.split("|")
        if gg == g and v["n"] >= 50 and not p.startswith("multi") and p != "other-single": pop.append((v["d0"], p, v))
    pop.sort(reverse=True)
    md.append(f"| {g} | {100 * cnt[g] / tot:.0f}% | " + ", ".join(f"{p} {s:.0f}% ({n})" for s, p, n in rl[:4]) + " | "
              + ", ".join(f"{p} {v['d0']:.0f}% · {f(v['ms50'])} ms ({v['n']})" for _, p, v in pop[:4]) + " |")
md.append(f"| other (Rakurai, Agave, …) | {100 * cnt['other'] / tot:.0f}% | – | – |")
open(os.path.join(W, "summary_S2.md"), "w").write("\n".join(md) + "\n")

# S3: landing time vs being first + benchmark
lt = T["T15_landing_time"]["rows"]
md = ["| Our buy arrives (ms after the create) | First outside buyer, all launches with an outside buy % | First outside buyer, contested launches % | Outside buys ahead (contested, mean) |", "|---|---|---|---|"]
for Tm in [20, 30, 40, 50, 74, 100]:
    a = [r for r in lt if r["T"] == Tm and r["set"].startswith("all")][0]
    c = [r for r in lt if r["T"] == Tm and r["set"].startswith("contested")][0]
    md.append(f"| {Tm}{' (our Run 2 live)' if Tm == 74 else ''} | {f(a['first_pct'])} | {f(c['first_pct'])} | {f(c['mean_ahead'], 2)} |")
open(os.path.join(W, "summary_S3.md"), "w").write("\n".join(md) + "\n")
bm = T["T16_benchmark"]
md = ["| Who | Slice | In create slot % | ms p25 / p50 |", "|---|---|---|---|"]
for r in bm["rows"]:
    who = "Top-20 snipers" if r["set"].startswith("Top") else "All 150 nonce fan-out bots"
    md.append(f"| {who} | {r['client']} | {f(r['d0'])} | {f(r['ms25'])} / {f(r['ms50'])} |")
open(os.path.join(W, "summary_S4.md"), "w").write("\n".join(md) + "\n")
print("slot shares", {k: round(100 * v / tot, 1) for k, v in cnt.items()})
print(open(os.path.join(W, "summary_S1.md")).read()); print(open(os.path.join(W, "summary_S2.md")).read())
print(open(os.path.join(W, "summary_S3.md")).read()); print(open(os.path.join(W, "summary_S4.md")).read())

# S5: representative sniper-sized create-slot buys per path (ms closest to the path's sniper-sized median)
import gzip
B = [json.loads(l) for l in gzip.open(os.path.join(W, "rows_buys.jsonl.gz"), "rt")]
wl = collections.defaultdict(set)
for b in B: wl[b["payer"]].add((b["R"], b["mint"]))
BAD = ["nigg", "fag", "cunt", "rape", "nazi", "hitler", "kike", "spic", "chink", "retard", "whore", "slut", "dick", "cock", "pussy", "fuck", "shit", "bitch", "penis", "anal", "porn", "jew"]
def wp(w): return "[masked]" if any(x in w[:6].lower() for x in BAD) else w[:6]
md = ["| Path | Example (create-slot buy, ≥0.5 SOL, repeat wallet; ms = our feed after the create) |", "|---|---|"]
for p in ["landx", "helius", "speedlanding", "jito", "nozomi", "astralane", "none", "bolt", "flashblock", "0slot"]:
    tgt = (t2b.get(p) or {}).get("ms_p50")
    v = [b for b in B if b["qsol"] and b["path"] == p and b["d"] == 0 and b["sol"] >= 5e8 and len(wl[b["payer"]]) >= 10 and b["ms"] is not None]
    if not v or tgt is None: continue
    v.sort(key=lambda b: abs(b["ms"] - tgt))
    links = []
    for b in v[:2]:
        links.append(f"[{b['ms']:.0f} ms, pos {b['pos']}, {b['sol'] / 1e9:.2f} SOL, tip {b['tip'] / 1e9:.4f}, {b['cgroup']}, {wp(b['payer'])}](https://solscan.io/tx/{b['sig']})")
    md.append(f"| {p} | " + " · ".join(links) + " |")
open(os.path.join(W, "summary_S5.md"), "w").write("\n".join(md) + "\n")
print(open(os.path.join(W, "summary_S5.md")).read())
