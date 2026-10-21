# READ-ONLY (host): tables for FILTERS2.md -- NON-bundle create-time signals (creator reputation, text, create-tx details,
# leader identity, activity regime) on the same realistic landing model as FILTERS.md (p2 = PnL selling at the end of S+2,
# pp2 = the same landing 20 ms later). Groups: A = in-sample evening (10-20), B = older + overnight, C = 10-21 morning to
# 10:13, D = today's live paper log after C (10:13-~12:40 UTC). A is where anything was chosen; B/C/D are the checks.
# usage: python3 filters2.py > tables.md      (needs f2_load.py inputs; RPC section only if creator_hist.py output exists)
import sys, time, random, statistics, collections, re
import f2_load

rows, H = f2_load.load()
G = ("A", "B", "C", "D")
lun = lambda r: r["tipc"] == "lunar"
early = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150
b35 = lambda r: 3 <= r["gsol"] <= 5
R2 = lambda r: lun(r) and b35(r) and early(r)
rep = lambda r: r["c_prev_n"] >= 1 and r["c_prev_p2"] > 0               # creator's earlier watched launches net positive
repbad = lambda r: r["c_prev_n"] >= 1 and r["c_prev_p2"] <= 0
first = lambda r: r["c_prev_n"] == 0


def stats(rs, gs):
    rs = [r for r in rs if r["grp"] in gs]; n = len(rs); h = sum(H[g] for g in gs)
    if not n: return None
    p = [r["p2"] for r in rs]
    return dict(n=n, ph=n / h, fil=sum(1 for r in rs if not r["refused"]), t2=sum(p), m2=sum(p) / n, med=statistics.median(p),
                win=sum(1 for x in p if x > 0) / n, worst=min(p), tp=sum(r["pp2"] for r in rs), x3=sum(sorted(p, reverse=True)[3:]),
                nc=len({r["creator"] for r in rs}))


HDR = ("| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")


def fmt(s):
    if not s: return "| 0 | - | - | - | - | - | - | - | - | - |"
    return (f"| {s['n']} | {s['ph']:.1f} | {s['nc']} | {s['t2']:+.2f} | {s['m2']:+.3f} | {s['med']:+.3f} | {100 * s['win']:.0f}% | {s['worst']:+.2f} "
            f"| {s['tp']:+.2f} | {s['x3']:+.2f} |")


def table(title, variants, note=None, groups=G):
    print(f"\n#### {title}\n")
    if note: print(note + "\n")
    print(HDR)
    for name, sel in variants:
        rs = [r for r in rows if sel(r)]
        for g in groups:
            print(f"| {name if g == groups[0] else ''} | {g} " + fmt(stats(rs, (g,))))


def compact(title, variants, note=None, base=lambda r: True):
    """one line per variant: n / per launch / total per group"""
    print(f"\n#### {title}\n")
    if note: print(note + "\n")
    print("| variant | " + " | ".join(f"{g}: n, per launch, total" for g in G) + " |\n|---|" + "---|" * len(G))
    for name, sel in variants:
        cells = []
        for g in G:
            s = stats([r for r in rows if base(r) and sel(r)], (g,))
            cells.append(f"{s['n']}, {s['m2']:+.3f}, {s['t2']:+.2f}" if s else "0")
        print(f"| {name} | " + " | ".join(cells) + " |")


def boot(sel, gs, cluster=True, B=2000, seed=7):
    rs = [r for r in rows if r["grp"] in gs and sel(r)]
    if len(rs) < 2: return f"n={len(rs)}"
    random.seed(seed)
    v = [r["p2"] for r in rs]
    if cluster:
        c = collections.defaultdict(list)
        for r in rs: c[r["creator"]].append(r["p2"])
        ks = list(c); ms = []
        for _ in range(B):
            xs = [x for k in (random.choice(ks) for _ in ks) for x in c[k]]
            ms.append(sum(xs) / len(xs))
    else:
        ms = [sum(random.choice(v) for _ in v) / len(v) for _ in range(B)]
    ms.sort()
    return f"{sum(v) / len(v):+.3f} [{ms[int(B * .05)]:+.3f}, {ms[int(B * .95) - 1]:+.3f}] n={len(v)}"


sec = sys.argv[1] if len(sys.argv) > 1 else "all"
if sec == "dump":                                       # the joined per-launch table (no raw signature lists)
    import json
    keep = [{k: v for k, v in r.items() if k not in ("vbt",)} for r in rows]
    json.dump(dict(rows=keep, hours=H, groups=dict(A=["dry1h", "run1"], B=["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"],
                                                       C=["morning"], D=["today"])), open(sys.argv[2], "w"))
    print(f"{len(keep)} rows -> {sys.argv[2]}"); sys.exit(0)
print(f"<!-- generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by ops/research/filters2.py -->")

if sec in ("all", "overview"):
    print("\n#### Data per period\n\n| group | hours | watched launches | /h | rule #2 | /h | distinct creators | launches by a creator seen before (in our logs) |\n|---|---|---|---|---|---|---|---|")
    for g in G:
        rs = [r for r in rows if r["grp"] == g]
        print(f"| {g} | {H[g]:.2f} | {len(rs)} | {len(rs) / H[g]:.0f} | {sum(1 for r in rs if R2(r))} | {sum(1 for r in rs if R2(r)) / H[g]:.1f} "
              f"| {len({r['creator'] for r in rs})} | {sum(1 for r in rs if r['c_prev_n'] >= 1)} ({100 * sum(1 for r in rs if r['c_prev_n'] >= 1) / len(rs):.0f}%) |")

if sec in ("all", "rep"):
    rep_added = lambda r: rep(r) and not R2(r)
    table("1a. Creator reputation from OUR OWN earlier launches, all watched launches", [
        ("all watched", lambda r: True),
        ("first time we see the creator", first),
        ("creator seen before, earlier launches net POSITIVE (REP)", rep),
        ("creator seen before, earlier launches net zero/negative", repbad)],
        note="Reputation = the sum of the modelled S+2 PnL of the same creator's EARLIER watched launches (any log, strictly before this "
             "launch). The creator's previous launch was more than 2 min earlier for 106 of the 112 REP launches (median 29 min), so its "
             "S+2 result was settled; REP restricted to those 106 gives +0.121 / +0.083 / +0.065 / +0.047 per launch (A/B/C/D).")
    table("1b. The same split inside rule #2", [
        ("rule #2", R2),
        ("rule #2, first-time creator", lambda r: R2(r) and first(r)),
        ("rule #2, REP creator", lambda r: R2(r) and rep(r)),
        ("rule #2, creator with net zero/negative history", lambda r: R2(r) and repbad(r)),
        ("rule #2 SKIPPING creators with net zero/negative history", lambda r: R2(r) and not repbad(r))])
    table("1c. REP as an ADDITIONAL trigger (outside rule #2) and combined", [
        ("REP minus rule #2 (added launches)", rep_added),
        ("REP minus rule #2, create <=150 ms", lambda r: rep_added(r) and early(r)),
        ("rule #2 OR REP", lambda r: R2(r) or rep(r)),
        ("rule #2 OR (REP and create <=150 ms)", lambda r: R2(r) or (rep(r) and early(r)))])
    print("\n#### 1d. Per-launch S+2 PnL: mean with a bootstrap 90% interval (resampling CREATORS, 2000x)\n")
    print("| variant | A | B | C | D | B+C+D (out of sample) |\n|---|---|---|---|---|---|")
    for name, sel in [("rule #2", R2), ("REP", rep), ("REP minus rule #2", rep_added),
                      ("creator history net zero/negative", repbad), ("first-time creator", first), ("rule #2 OR REP", lambda r: R2(r) or rep(r))]:
        print(f"| {name} | " + " | ".join(boot(sel, (g,)) for g in G) + f" | {boot(sel, ('B', 'C', 'D'))} |")
    compact("1e. Variants of the reputation rule (all watched launches)", [
        ("REP: earlier launches net positive (sum)", rep),
        ("last earlier launch positive", lambda r: r["c_prev_n"] >= 1 and r["c_last_p2"] > 0),
        ("earlier launches net > +0.05 SOL", lambda r: r["c_prev_n"] >= 1 and r["c_prev_p2"] > 0.05),
        ("MODEL-FREE: last earlier launch's price at end of S+2 >= 1.1x its post-bundle price", lambda r: r["c_prev_n"] >= 1 and r["c_prev_mkt_last"] >= 1.1),
        ("MODEL-FREE: last earlier launch's price < 1.1x", lambda r: r["c_prev_n"] >= 1 and r["c_prev_mkt_last"] < 1.1),
        ("MODEL-FREE: an earlier launch got >= 2 SOL outside buys in S..S+2", lambda r: r["c_prev_n"] >= 1 and r["c_prev_out_max"] >= 2),
        ("REP, 1 earlier launch", lambda r: rep(r) and r["c_prev_n"] == 1),
        ("REP, 2-3 earlier launches", lambda r: rep(r) and 2 <= r["c_prev_n"] <= 3),
        ("REP, 4+ earlier launches", lambda r: rep(r) and r["c_prev_n"] >= 4),
        ("REP, no bundle", lambda r: rep(r) and r["glued"] == 0),
        ("REP, bundle 2-5 SOL", lambda r: rep(r) and 2 <= r["gsol"] <= 5),
        ("REP, bundle > 5 SOL", lambda r: rep(r) and r["gsol"] > 5),
        ("REP, Harmonic leader", lambda r: rep(r) and r["cls"] == "harmonic"),
        ("REP, Jito-client leader", lambda r: rep(r) and r["cls"] == "jito"),
        ("REP, BAM leader", lambda r: rep(r) and r["cls"] == "bam"),
        ("REP, create > 150 ms", lambda r: rep(r) and not early(r))])
    print("\nREP with other exits/landing (per launch): " + "; ".join(
        f"{g}: sell at end of S+1 {sum(r['p1'] for r in rows if r['grp'] == g and rep(r)) / max(1, sum(1 for r in rows if r['grp'] == g and rep(r))):+.3f}, "
        f"S+2 landing +20 ms {sum(r['pp2'] for r in rows if r['grp'] == g and rep(r)) / max(1, sum(1 for r in rows if r['grp'] == g and rep(r))):+.3f}" for g in G))
    # does the reputation predict the next launch's MARKET (model-free) response?
    print("\n#### 1f. Model-free check: the launch's own market response in S..S+2 (price at end of S+2 / post-bundle price)\n")
    print("| set | grp | n | median price ratio | share >= 1.1x | median outside buy SOL S..S+2 |\n|---|---|---|---|---|---|")
    for name, sel in [("REP", rep), ("creator history net zero/negative", repbad), ("first-time creator", first)]:
        for g in G:
            rs = [r for r in rows if r["grp"] == g and sel(r) and "mkt2" in r]
            if not rs: continue
            print(f"| {name if g == 'A' else ''} | {g} | {len(rs)} | {statistics.median(r['mkt2'] for r in rs):.2f} | "
                  f"{100 * sum(1 for r in rs if r['mkt2'] >= 1.1) / len(rs):.0f}% | {statistics.median(r['out2'] for r in rs):.2f} |")
    # frozen list: built ONLY from earlier periods, applied unchanged to a later period (the precomputed-cache use case)
    import json, os
    LH = {l: v["hours"] for l, v in json.load(open(os.path.join(f2_load.FILT, "launches2.json")))["spans"].items()}
    LH["today"] = H["D"]
    print("\n#### 1g. Frozen list: good/bad creator lists built from earlier periods only, applied unchanged later\n")
    print(HDR)
    for label, src, later_logs in [("list from A+B+C (10-20 12:40 .. 10-21 10:13) -> D (today)", ("A", "B", "C"), ("today",)),
                                   ("list from A only (10-20 evening) -> later logs (edge3, edge5, night, morning, today)", ("A",),
                                    ("edge3", "edge5", "night", "morning", "today"))]:
        hist = collections.defaultdict(float); seen = set()
        for r in rows:
            if r["grp"] in src: hist[r["creator"]] += r["p2"]; seen.add(r["creator"])
        good = {c for c in seen if hist[c] > 0}; bad = seen - good
        hrs = sum(LH[l] for l in later_logs)
        for name, sel in [(f"{label}: good-list creators ({len(good)})", lambda r: r["creator"] in good),
                          ("same, not rule #2", lambda r: r["creator"] in good and not R2(r)),
                          (f"bad-list creators ({len(bad)})", lambda r: r["creator"] in bad),
                          ("creators not on either list", lambda r: r["creator"] not in seen)]:
            rs = [dict(r, grp="X") for r in rows if r["log"] in later_logs and sel(r)]
            H["X"] = hrs
            print(f"| {name} | {'+'.join(sorted({r['grp'] for r in rows if r['log'] in later_logs}))} " + fmt(stats(rs, ("X",))))
    logs = ["dry1h", "run1", "cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night", "morning", "today"]
    print("\n#### 1h. Per log (n: S+2 PnL SOL); A = dry1h + run1, B = cov..night, C = morning, D = today\n")
    print("| variant | " + " | ".join(logs) + " |\n|---|" + "---|" * len(logs))
    for name, sel in [("rule #2", R2), ("REP", rep), ("REP minus rule #2", rep_added), ("creator history net zero/negative", repbad)]:
        cells = []
        for l in logs:
            rs = [r for r in rows if r["log"] == l and sel(r)]
            cells.append(f"{len(rs)}: {sum(r['p2'] for r in rs):+.2f}" if rs else "0")
        print(f"| {name} | " + " | ".join(cells) + " |")
    # concentration
    print("\n#### 1i. Concentration: REP launches per creator (top 5 by S+2 total, per group)\n")
    for g in G:
        c = collections.defaultdict(list)
        for r in rows:
            if r["grp"] == g and rep(r): c[r["creator"][:6]].append(r["p2"])
        top = sorted(c.items(), key=lambda kv: -sum(kv[1]))
        tot = sum(sum(v) for v in c.values())
        print(f"- {g}: {len(c)} creators, total {tot:+.2f}; top: " + ", ".join(f"{k} {len(v)}x {sum(v):+.2f}" for k, v in top[:5]) +
              f"; total without the best creator {tot - (sum(top[0][1]) if top else 0):+.2f}")
    table("1j. Bad history as a SKIP on the wider triggers of FILTERS.md (C6 added launches, C7 no-bundle Harmonic)", [
        ("C6 added (any tip, bundle 2-5, <=150 ms, not rule #2)", lambda r: early(r) and 2 <= r["gsol"] <= 5 and not R2(r)),
        ("C6 added, skipping bad-history creators", lambda r: early(r) and 2 <= r["gsol"] <= 5 and not R2(r) and not repbad(r)),
        ("C7 (no bundle, Harmonic, <=150 ms)", lambda r: early(r) and r["glued"] == 0 and r["cls"] == "harmonic"),
        ("C7, skipping bad-history creators", lambda r: early(r) and r["glued"] == 0 and r["cls"] == "harmonic" and not repbad(r))])

if sec in ("all", "text"):
    caps = lambda s: bool(s) and s.upper() == s and any(c.isalpha() for c in s)
    nonascii = lambda s: any(ord(c) > 127 for c in (s or ""))
    dig = lambda s: any(c.isdigit() for c in (s or ""))
    KW = {"AI/bot": r"(\bai\b|agent|gpt|bot|intellig|robot|neural|agi)", "politics": r"(trump|elon|musk|biden|donald|maga|president|kamala|vance)",
          "animal": r"(cat|dog|inu|pepe|frog|hamster|doge|shib|monkey|ape|bear|bull|penguin|chicken|beaver|kitty|puppy|bird)",
          "coin/money": r"(coin|token|cash|money|gold|rich|moon|pump)"}
    def kw(r):
        s = ((r.get("name") or "") + " " + (r.get("sym") or "")).lower()
        for k, p in KW.items():
            if re.search(p, s): return k
        return "none"
    def uripat(u):
        u = u or ""
        if "j7tracker" in u: return "j7tracker /metadata/<id>.json"
        if "ipfs.io/ipfs/bafkrei" in u: return "ipfs bafkrei (CIDv1)"
        if "ipfs.io/ipfs/Qm" in u: return "ipfs Qm (CIDv0)"
        if "uxento" in u: return "uxento"
        return "other"
    TEXT = [("name length <= 5", lambda r: (r["name_len"] or 0) <= 5), ("name length 6-10", lambda r: 6 <= (r["name_len"] or 0) <= 10),
            ("name length 11-20", lambda r: 11 <= (r["name_len"] or 0) <= 20), ("name length > 20", lambda r: (r["name_len"] or 0) > 20),
            ("symbol ALL CAPS", lambda r: caps(r["sym"])), ("symbol not all caps", lambda r: not caps(r["sym"])),
            ("symbol == name", lambda r: (r["sym"] or "").lower() == (r["name"] or "").lower()),
            ("digits in name/symbol", lambda r: dig(r["name"]) or dig(r["sym"])), ("non-ASCII (emoji, CJK, filler) in name/symbol", lambda r: nonascii(r["name"]) or nonascii(r["sym"]))]
    TEXT += [("uri " + p, (lambda p: lambda r: uripat(r["uri"]) == p)(p)) for p in ("j7tracker /metadata/<id>.json", "ipfs bafkrei (CIDv1)", "ipfs Qm (CIDv0)", "uxento", "other")]
    TEXT += [("keyword " + k, (lambda k: lambda r: kw(r) == k)(k)) for k in list(KW) + ["none"]]
    compact("2a. Text features, all watched launches with create <= 150 ms", TEXT, base=early)
    compact("2b. Text features inside rule #2", TEXT, base=R2)

if sec in ("all", "tx"):
    rnd = lambda r: abs(r["dev"] * 2 - round(r["dev"] * 2)) < 1e-6
    TX = [("dev buy a multiple of 0.5 SOL", rnd), ("dev buy any other amount", lambda r: not rnd(r)),
          ("dev buy kind 1 (exact SOL in)", lambda r: r["kind"] == 1), ("dev buy kind 2 (token amount + SOL cap)", lambda r: r["kind"] == 2), ("dev buy kind 3", lambda r: r["kind"] == 3),
          ("cu 333333 / 300000 (j7tracker default)", lambda r: (r["cu_price"], r["cu_limit"]) == (333333, 300000)), ("cu_price 0", lambda r: not r["cu_price"]),
          ("cu_price >= 1,000,000", lambda r: (r["cu_price"] or 0) >= 1_000_000),
          ("largest create transfer 0", lambda r: not r["tip_lam"]), ("largest create transfer < 0.0025", lambda r: 0 < r["tip_lam"] < 2_500_000),
          ("largest create transfer = 0.0025 (j7 Lunar default)", lambda r: r["tip_lam"] == 2_500_000), ("largest create transfer 0.0025-0.01", lambda r: 2_500_000 < r["tip_lam"] <= 10_000_000),
          ("largest create transfer > 0.01", lambda r: r["tip_lam"] > 10_000_000),
          ("no lookup table / v1 / Token-2022 (pump create_v2 tools)", lambda r: not r["luts"]), ("nix >= 7", lambda r: (r["nix"] or 0) >= 7), ("nsig > 2", lambda r: (r["nsig"] or 0) > 2)]
    compact("3a. Create-tx details, all watched launches with create <= 150 ms", TX, base=early)
    print("\nInside rule #2 the create tx is one tool's fingerprint: of the rule #2 launches, " +
          f"{sum(1 for r in rows if R2(r) and (r['cu_price'], r['cu_limit'], r['nkeys'], r['nix'], r['luts'], r['tip_lam']) == (333333, 300000, 15, 6, 1, 2_500_000))} of {sum(1 for r in rows if R2(r))} "
          "have cu_price 333333, cu_limit 300000, 15 keys, 6 instructions, 1 lookup table and a 0.0025 SOL Lunar transfer (j7tracker defaults). "
          "The rest: " + ", ".join(f"{r['grp']} {r['mint'][:6]} {r['host']} {r['p2']:+.3f}" for r in rows if R2(r) and (r['cu_price'], r['cu_limit'], r['nkeys'], r['nix'], r['luts'], r['tip_lam']) != (333333, 300000, 15, 6, 1, 2_500_000)) + ".")
    compact("3b. Dev-buy amount inside rule #2", TX[:5], base=R2)

if sec in ("all", "leader"):
    byA = collections.defaultdict(list)
    for r in rows:
        if r["grp"] == "A": byA[r["leader"]].append(r["p2"])
    skip = sorted(l for l, v in byA.items() if len(v) >= 5 and sum(v) / len(v) < -0.02)
    print(f"\n#### 4. Leader skip list (chosen on A: leaders with >= 5 watched launches in A and mean S+2 < -0.02 SOL)\n\nSkip list: "
          + ", ".join(f"{l[:8]} ({collections.Counter(r['cls'] for r in rows if r['leader'] == l).most_common(1)[0][0]}, A {len(byA[l])}: {sum(byA[l]) / len(byA[l]):+.3f})" for l in skip))
    table("4a. Skip-list leaders vs the rest", [
        ("all watched, skip-list leaders", lambda r: r["leader"] in skip), ("all watched, other leaders", lambda r: r["leader"] not in skip),
        ("rule #2 on skip-list leaders", lambda r: R2(r) and r["leader"] in skip), ("rule #2 without skip-list leaders", lambda r: R2(r) and r["leader"] not in skip)])
    print("\n#### 4b. Leaders the owner asked about (all watched launches; n, per launch, total)\n")
    print("| leader | class | " + " | ".join(G) + " | rule #2 (all groups) |\n|---|---|---|---|---|---|---|")
    for pre in ("C8Bey3LK", "HEL1USMZ", "Fd7btgyS", "EvnRmnMr", "JUPiTERr", "Awes4Tr6", "CMPSSdrT", "3JotfSFP"):
        rs = [r for r in rows if (r["leader"] or "").startswith(pre)]
        if not rs: continue
        cells = []
        for g in G:
            s = stats(rs, (g,)); cells.append(f"{s['n']}, {s['m2']:+.3f}, {s['t2']:+.2f}" if s else "0")
        s2 = stats([r for r in rs if R2(r)], G)
        print(f"| {pre} | {collections.Counter(r['cls'] for r in rs).most_common(1)[0][0]} | " + " | ".join(cells) + f" | {s2['n']}, {s2['m2']:+.3f}, {s2['t2']:+.2f} |" if s2 else f"| {pre} | - | " + " | ".join(cells) + " | 0 |")

if sec in ("all", "regime"):
    hour = lambda r: time.gmtime(r["bt"]).tm_hour if r["bt"] else -1
    REG = [("creates seen in the previous 10 min < 30/min", lambda r: r["act_all"] is not None and r["act_all"] < 30),
           ("30-45/min", lambda r: r["act_all"] is not None and 30 <= r["act_all"] < 45),
           ("45-60/min", lambda r: r["act_all"] is not None and 45 <= r["act_all"] < 60),
           (">= 60/min", lambda r: r["act_all"] is not None and r["act_all"] >= 60),
           ("UTC 00-06", lambda r: 0 <= hour(r) < 6), ("UTC 06-12", lambda r: 6 <= hour(r) < 12), ("UTC 12-18", lambda r: 12 <= hour(r) < 18), ("UTC 18-24", lambda r: 18 <= hour(r) < 24)]
    compact("5a. Activity regime and hour, rule #2 launches", REG, base=R2)
    compact("5b. Activity regime and hour, all watched launches with create <= 150 ms", REG, base=early)

if sec in ("all", "rpc") and any("rpc" in r for r in rows):
    have = [r for r in rows if r.get("rpc")]
    print(f"\n#### 6. On-chain creator history (public RPC; only signatures before the create slot)\n\nCoverage: {len(have)} of {len(rows)} launches.\n")
    W = [("wallet's prior txs <= 3 (fresh wallet)", lambda r: r.get("w_prior") is not None and r["w_prior"] <= 3),
         ("prior txs 4-20", lambda r: r.get("w_prior") is not None and 4 <= r["w_prior"] <= 20),
         ("prior txs 21-1000", lambda r: r.get("w_prior") is not None and 21 <= r["w_prior"] <= 1000),
         ("prior txs > 1000 (or history not fully listed)", lambda r: r.get("w_prior") is not None and (r["w_prior"] > 1000 or not r["w_complete"])),
         ("wallet age < 10 min", lambda r: r.get("w_age_s") is not None and r["w_age_s"] < 600),
         ("wallet age >= 10 min (history window ~23 h)", lambda r: r.get("w_age_s") is not None and r["w_age_s"] >= 600),
         ("creator vault: no earlier pump trades (first coin)", lambda r: r.get("v_n") == 0),
         ("vault: 1-99 earlier trades", lambda r: r.get("v_n") is not None and 1 <= r["v_n"] < 100),
         ("vault: 100-999 earlier trades", lambda r: r.get("v_n") is not None and 100 <= r["v_n"] < 1000),
         ("vault: >= 1000 earlier trades", lambda r: r.get("v_n") is not None and r["v_n"] >= 1000),
         ("vault: earlier trades in the last hour >= 100", lambda r: (r.get("v_1h") or 0) >= 100),
         ("vault: earlier trades, none in the last hour", lambda r: (r.get("v_n") or 0) > 0 and (r.get("v_1h") or 0) == 0)]
    compact("6a. Creator wallet and creator-vault history, all watched launches with create <= 150 ms", W, base=early)
    compact("6b. The same inside rule #2", W, base=R2)
    frep = lambda r: r.get("f_prev_n", 0) >= 1 and r["f_prev_p2"] > 0
    fbad = lambda r: r.get("f_prev_n", 0) >= 1 and r["f_prev_p2"] <= 0
    compact("6c. Funder reputation: earlier watched launches of creators with the SAME first funder (no look-ahead)", [
        ("funder's earlier launches net positive", frep), ("funder's earlier launches net zero/negative", fbad),
        ("first-time creator, funder net positive", lambda r: first(r) and frep(r)), ("first-time creator, funder net zero/negative", lambda r: first(r) and fbad(r)),
        ("first-time creator, funder never seen", lambda r: first(r) and r.get("rpc") and r.get("f_prev_n", 0) == 0)])
    # funder: shared first funders
    fc = collections.Counter(r.get("funder") for r in have if r.get("funder"))
    nf = collections.Counter()
    for r in have:
        if r.get("funder"): nf[r["funder"]] += 0
    crs = collections.defaultdict(set)
    for r in have:
        if r.get("funder"): crs[r["funder"]].add(r["creator"])
    multi = {f for f, c in crs.items() if len(c) >= 3}
    print(f"\nFirst funders: {len(crs)} distinct; {len(multi)} funded >= 3 of our creators, covering "
          f"{sum(1 for r in have if r.get('funder') in multi)} launches.\n")
    print("| funder | creators | launches | " + " | ".join(G) + " |\n|---|---|---|---|---|---|---|")
    for f in sorted(multi, key=lambda f: -len(crs[f]))[:12]:
        rs = [r for r in have if r.get("funder") == f]
        cells = []
        for g in G:
            s = stats(rs, (g,)); cells.append(f"{s['n']}, {s['m2']:+.3f}" if s else "0")
        print(f"| {f[:8]} | {len(crs[f])} | {len(rs)} | " + " | ".join(cells) + " |")
