# READ-ONLY (host): FILTERS3.md tables -- "creator dev"-style create-time signals on the unchanged landing model
# (filters.py run(): 1.5 SOL, landing T by leader class, cap 15%, prio 0.011, tips by class, sell at the end of S+2).
# Groups: A in-sample (10-20 evening), B (older + overnight), C (10-21 morning), D (live paper 10:13-12:37), E (live paper
# 12:37-~14:15). Chosen on A, confirmed on B..E. History features use only launches >= LAG slots earlier / on-chain
# transactions before the create slot.
# usage: python3 filters3.py > tables.md      (needs creator_creates.py output for sections 0, 2, 3b)
import os, sys, json, random, statistics, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f3_load import load, LAG, F3

rows, HOURS = load()
G = ["A", "B", "C", "D", "E"]; OOS = ["B", "C", "D", "E"]
R2 = lambda r: r["tipc"] == "lunar" and 3 <= r["gsol"] <= 5 and r["create_ms"] is not None and r["create_ms"] <= 150
E150 = lambda r: r["create_ms"] is not None and r["create_ms"] <= 150


def boot(sel, n=2000, seed=1):
    by = collections.defaultdict(list)
    for r in sel: by[r["creator"]].append(r["p2"])
    keys = list(by); rnd = random.Random(seed); ms = []
    if len(keys) < 3: return None
    for _ in range(n):
        s = [by[keys[rnd.randrange(len(keys))]] for _ in keys]
        tot = sum(sum(x) for x in s); cnt = sum(len(x) for x in s)
        ms.append(tot / cnt)
    ms.sort(); return ms[int(0.05 * n)], ms[int(0.95 * n)]


def cell(sel):
    if not sel: return "-"
    return f"{len(sel)}: {sum(r['p2'] for r in sel) / len(sel):+.3f}"


def oos(sel, ci=True):
    if not sel: return "| - | - | - | - | - | - | - | - | - |"
    p = sorted(r["p2"] for r in sel); n = len(p); h = sum(HOURS[g] for g in OOS)
    b = boot(sel) if ci else None
    return (f"| {n} | {n / h:.1f} | {sum(p):+.2f} | {sum(p) / n:+.3f} | {statistics.median(p):+.3f} | {100 * sum(1 for x in p if x > 0) / n:.0f}% | "
            f"{sum(r['pp2'] for r in sel) / n:+.3f} | {sum(p[:-3]) if n > 3 else 0:+.2f} | " + (f"{b[0]:+.3f} to {b[1]:+.3f} |" if b else "- |"))


HDR = ("| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def table(title, base, variants, note=None):
    print(f"\n### {title}\n")
    if note: print(note + "\n")
    print(HDR)
    for name, f in variants:
        sel = [r for r in rows if base(r) and f(r)]
        print(f"| {name} | " + " | ".join(cell([r for r in sel if r["grp"] == g]) for g in G) + " " + oos([r for r in sel if r["grp"] in OOS]))


ALL = lambda r: True
print("Groups (hours): " + ", ".join(f"{g} {HOURS[g]:.2f} h ({sum(1 for r in rows if r['grp'] == g)} watched, {sum(1 for r in rows if r['grp'] == g and R2(r))} rule #2)" for g in G))
print("Cells: n: S+2 PnL per launch (SOL). OOS = B+C+D+E pooled. +20 ms = landing 20 ms later. CI = bootstrap over creators.")

table("Baselines", ALL, [("all watched launches", ALL), ("all watched, create <= 150 ms", E150), ("rule #2", R2)])

# ---------- 0. prior pump.fun creates (on-chain) ----------
CC = json.load(open(os.path.join(F3, "cc.json"))) if os.path.exists(os.path.join(F3, "cc.json")) else {}
for r in rows:
    c = CC.get(r["creator"])
    r["cc"] = c is not None
    if not c: continue
    tx = c["txs"]; S = r["S"]
    cre = sorted([t for t in tx if t["kind"] == "create" and t["slot"] < S], key=lambda t: t["slot"])
    r["ncre"] = len(cre)
    own = [t for t in tx if t["slot"] == S and t["kind"] == "create" and r["mint"] in (t.get("mints") or [])] or \
          [t for t in tx if t["slot"] == S and t["kind"] == "create"]
    r["c_pre"] = own[0]["pre"] / 1e9 if own and own[0].get("pre") is not None else None
    r["c_post"] = own[0]["post"] / 1e9 if own and own[0].get("post") is not None else None
    olds = [t["slot"] for t in tx if t["kind"] != "unknown"]
    oldest = min(olds) if olds else S
    if not c["trunc"] and c.get("oldest_slot"): oldest = min(oldest, c["oldest_slot"])
    r["win_h"] = max(0, S - oldest) * 0.2164 / 3600
    if c["trunc"] and r["win_h"] < 0.5 and len(cre) <= 10:     # walk never got (far enough) behind this create: unknown
        r["cc"] = False; continue
    # exact unless the walk/history stopped before reaching the wallet's start and we found <= 10 creates before S
    r["ncre_trunc"] = bool(c["trunc"]) and len(cre) <= 10      # lower bound (walk capped / beyond the RPC's horizon)
    # creator's own selling of its EARLIER coins (on-chain; only sells with slot < S)
    sells = [t for t in tx if t["kind"] == "sell" and t["slot"] < S]
    sp = []
    for t0 in cre[-5:]:                                         # up to the last 5 prior creates
        m = [x for x in (t0.get("mints") or []) if x.endswith("pump")] or (t0.get("mints") or [])[:1]
        if not m: continue
        m = m[0]; got = (t0.get("tok") or {}).get(m, 0)
        ss = sorted([s for s in sells if s["slot"] >= t0["slot"] and (s.get("tok") or {}).get(m, 0) < 0], key=lambda s: s["slot"])
        first = ss[0]["slot"] - t0["slot"] if ss else None
        sold30 = -sum(s["tok"][m] for s in ss if s["slot"] - t0["slot"] <= 75)
        sp.append(dict(slot=t0["slot"], first=first, share30=(sold30 / got) if got > 0 else None, settled=S - t0["slot"]))
    r["prev_sp"] = sp
    last = sp[-1] if sp else None
    r["last_first_sell"] = last["first"] if last else None
    r["last_share30"] = last["share30"] if last else None
    r["last_settled"] = last["settled"] if last else None


def nb(r):
    if not r.get("cc"): return None
    n = r["ncre"]
    return "0" if n == 0 else "1" if n == 1 else "2-3" if n <= 3 else "4-10" if n <= 10 else "11+"


if CC:
    cov = sum(1 for r in rows if r.get("cc")); tr = sum(1 for r in rows if r.get("cc") and r["ncre_trunc"])
    note = (f"Coverage: {cov} of {len(rows)} launches have the creator's on-chain history; {tr} of them have a count that is only a LOWER bound "
            f"(history walk capped, <= 10 creates found). Buckets use the count of the creator's pump.fun creates strictly before this create's slot.")
    bk = [("0 prior creates (first-ever)", lambda r: nb(r) == "0"), ("exactly 1 prior", lambda r: nb(r) == "1"), ("2-3 prior", lambda r: nb(r) == "2-3"),
          ("4-10 prior", lambda r: nb(r) == "4-10"), ("11+ prior", lambda r: nb(r) == "11+"),
          ("1 prior, exact count only", lambda r: nb(r) == "1" and not r["ncre_trunc"]),
          ("0 prior, exact count only", lambda r: nb(r) == "0" and not r["ncre_trunc"]),
          ("<= 1 prior", lambda r: nb(r) in ("0", "1")), (">= 2 prior", lambda r: nb(r) in ("2-3", "4-10", "11+"))]
    cl = []
    for g in G:
        gr = [r for r in rows if r["grp"] == g and r.get("cc")]
        w = sorted(r["win_h"] for r in gr if r.get("win_h") is not None)
        cl.append(f"{g}: {len(gr)}/{sum(1 for r in rows if r['grp'] == g)} launches, exact {sum(1 for r in gr if not r['ncre_trunc'])}, "
                  f"median visible history before the create {statistics.median(w) if w else 0:.1f} h")
    note += "\n\nPer group: " + "; ".join(cl) + (". 'Visible history' = from the oldest transaction we classified (or the oldest signature "
            "the RPC returned) to the create; creates older than that are not counted, so '0 prior' means none in that window.")
    table("0a. Number of the creator's PRIOR pump.fun creates (on-chain), all watched launches", ALL, bk, note)
    table("0b. The same inside rule #2", R2, bk)
    # exactly-1-prior split by how that one prior launch did (no look-ahead)
    def one_prior(r): return nb(r) == "1"
    def last_watched(r):                                        # the creator's last earlier WATCHED launch, settled
        h = [q for q in rows if q["creator"] == r["creator"] and q["S"] <= r["S"] - LAG]
        return h[-1] if h else None
    for r in rows:
        if one_prior(r):
            q = last_watched(r); r["_lw"] = q
    sv = [("1 prior, that launch was watched by us", lambda r: one_prior(r) and r.get("_lw") is not None),
          ("1 prior, watched, its model PnL > 0", lambda r: one_prior(r) and r.get("_lw") is not None and r["_lw"]["p2"] > 0),
          ("1 prior, watched, its model PnL <= 0", lambda r: one_prior(r) and r.get("_lw") is not None and r["_lw"]["p2"] <= 0),
          ("1 prior, watched, outside buys S..S+2 >= 1 SOL", lambda r: one_prior(r) and r.get("_lw") is not None and (r["_lw"].get("out2") or 0) >= 1),
          ("1 prior, watched, outside buys S..S+2 < 1 SOL", lambda r: one_prior(r) and r.get("_lw") is not None and (r["_lw"].get("out2") or 0) < 1),
          ("1 prior, not watched by us", lambda r: one_prior(r) and r.get("_lw") is None),
          ("1 prior, creator first sold it <= 75 slots (30 s) after create", lambda r: one_prior(r) and r["last_first_sell"] is not None and r["last_first_sell"] <= 75),
          ("1 prior, creator first sold it > 75 slots after create", lambda r: one_prior(r) and r["last_first_sell"] is not None and r["last_first_sell"] > 75),
          ("1 prior, creator never sold it before this create", lambda r: one_prior(r) and r["last_first_sell"] is None and r["prev_sp"])]
    table("0c. Exactly 1 prior create: split by how that prior launch did (all watched launches)", ALL, sv)
    table("0d. Exactly 1 prior create, inside rule #2", R2, sv)

# ---------- 1. dev buy ----------
def devk(r):
    d = r["dev"]
    if abs(d - round(d)) < 0.005: return "integer SOL (1.0, 2.0, ...)"
    if abs(d * 2 - round(d * 2)) < 0.01: return "half SOL (x.5)"
    if abs(d * 10 - round(d * 10)) < 0.02: return "one decimal (x.1-x.9)"
    return "odd amount"


def share(r): return r["dev"] / (r["dev"] + r["gsol"]) if r["dev"] + r["gsol"] > 0 else None


dv = [(k, (lambda k: lambda r: devk(r) == k)(k)) for k in ("integer SOL (1.0, 2.0, ...)", "half SOL (x.5)", "one decimal (x.1-x.9)", "odd amount")]
dv += [("dev exactly 1.0", lambda r: abs(r["dev"] - 1) < 0.005), ("dev exactly 2.0", lambda r: abs(r["dev"] - 2) < 0.005),
       ("dev exactly 3.0", lambda r: abs(r["dev"] - 3) < 0.005), ("dev exactly 4.0", lambda r: abs(r["dev"] - 4) < 0.005),
       ("dev exactly 5.0", lambda r: abs(r["dev"] - 5) < 0.005)]
sh = [("no bundle (dev share 1.0)", lambda r: r["gsol"] == 0), ("dev share < 0.3", lambda r: r["gsol"] > 0 and share(r) < 0.3),
      ("dev share 0.3-0.5", lambda r: r["gsol"] > 0 and 0.3 <= share(r) < 0.5), ("dev share 0.5-0.8", lambda r: r["gsol"] > 0 and 0.5 <= share(r) < 0.8),
      ("dev share >= 0.8 (with bundle)", lambda r: r["gsol"] > 0 and share(r) >= 0.8)]
table("1a. Dev buy amount, all watched launches with create <= 150 ms", E150, dv)
table("1b. Dev buy amount inside rule #2", R2, dv)
table("1c. Dev buy as a share of (dev + glued bundle), all watched launches with create <= 150 ms", E150, sh)
table("1d. Dev share inside rule #2", R2, sh[1:])
ds = collections.Counter()
for r in rows:
    a, b, c = r.get("dev_lam"), r.get("dev_sized_l"), r.get("dev_cap_l")
    ds["dev_cap missing" if not c else ("dev = dev_sized = dev_cap" if a == b == c else "differ")] += 1
print(f"\ndev / dev_sized / dev_cap fields: {dict(ds)}\n")

# ---------- 2. creator SOL at create ----------
if CC:
    pv = [("creator SOL after create < 0.1", lambda r: r.get("c_post") is not None and r["c_post"] < 0.1),
          ("after create 0.1-1", lambda r: r.get("c_post") is not None and 0.1 <= r["c_post"] < 1),
          ("after create 1-5", lambda r: r.get("c_post") is not None and 1 <= r["c_post"] < 5),
          ("after create 5-20", lambda r: r.get("c_post") is not None and 5 <= r["c_post"] < 20),
          ("after create >= 20", lambda r: r.get("c_post") is not None and r["c_post"] >= 20),
          ("spent >= 90% of its SOL", lambda r: r.get("c_pre") and (r["c_pre"] - r["c_post"]) / r["c_pre"] >= 0.9),
          ("spent 50-90%", lambda r: r.get("c_pre") and 0.5 <= (r["c_pre"] - r["c_post"]) / r["c_pre"] < 0.9),
          ("spent < 50% (keeps most)", lambda r: r.get("c_pre") and (r["c_pre"] - r["c_post"]) / r["c_pre"] < 0.5)]
    print(f"\nCreator SOL known for {sum(1 for r in rows if r.get('c_post') is not None)} of {len(rows)} launches.")
    table("2a. Creator wallet SOL at create (create tx pre/post balance), all watched launches with create <= 150 ms", E150, pv)
    table("2b. The same inside rule #2", R2, pv)

# ---------- 3. creator behaviour on its PREVIOUS launches ----------
if CC:
    fv = [("last prior coin: creator first sold <= 10 slots (4 s)", lambda r: r.get("last_first_sell") is not None and r["last_first_sell"] <= 10),
          ("last prior coin: first sold 11-75 slots (4-30 s)", lambda r: r.get("last_first_sell") is not None and 10 < r["last_first_sell"] <= 75),
          ("last prior coin: first sold > 75 slots (> 30 s)", lambda r: r.get("last_first_sell") is not None and r["last_first_sell"] > 75),
          ("last prior coin: creator never sold (holder)", lambda r: r.get("prev_sp") and r["last_first_sell"] is None),
          ("last prior coin: >= 90% sold within 30 s", lambda r: r.get("last_share30") is not None and r["last_share30"] >= 0.9),
          ("last prior coin: < 50% sold within 30 s", lambda r: r.get("last_share30") is not None and r["last_share30"] < 0.5),
          ("median over last 5 prior coins: first sell <= 75 slots", lambda r: r.get("prev_sp") and statistics.median([(s["first"] if s["first"] is not None else 10 ** 6) for s in r["prev_sp"]]) <= 75),
          ("median over last 5 prior coins: first sell > 75 slots / never", lambda r: r.get("prev_sp") and statistics.median([(s["first"] if s["first"] is not None else 10 ** 6) for s in r["prev_sp"]]) > 75)]
    table("3a. The creator's selling of its EARLIER coins (on-chain, creator wallet only, sells before this create), all watched", ALL, fv)
    table("3b. The same inside rule #2", R2, fv)

# in-log: creator + bundle selling in S..S+2 of the creator's earlier WATCHED launches (block recordings)
for r in rows:
    h = [q for q in rows if q["creator"] == r["creator"] and q["S"] <= r["S"] - LAG]
    r["_h"] = h
    r["h_dump_any"] = any((q.get("dump2") or 0) > 0 for q in h) if h else None
    r["h_dump_last"] = (h[-1].get("dump2") or 0) if h else None
lb = lambda r: len(r["_h"])
lg = [("0 earlier watched launches", lambda r: lb(r) == 0), ("exactly 1", lambda r: lb(r) == 1), ("2-3", lambda r: 2 <= lb(r) <= 3),
      ("4-10", lambda r: 4 <= lb(r) <= 10), ("11+", lambda r: lb(r) >= 11),
      ("exactly 1, it made money on our model", lambda r: lb(r) == 1 and r["_h"][0]["p2"] > 0),
      ("exactly 1, it lost on our model", lambda r: lb(r) == 1 and r["_h"][0]["p2"] <= 0)]
table("0e. Prior launches counted from OUR LOGS only (earlier watched launches by the creator, >= 550 slots earlier), all watched", ALL, lg,
      "Our logs are gapped (5.8 h before today + today's continuous paper log), so this counts only launches we happened to watch.")
table("0f. The same inside rule #2", R2, lg)
dl = [("earlier watched launch: creator/bundle sold in S..S+2 (last one)", lambda r: r["h_dump_last"] is not None and r["h_dump_last"] > 0),
      ("earlier watched launch: no creator/bundle sell in S..S+2 (last one)", lambda r: r["h_dump_last"] is not None and r["h_dump_last"] == 0)]
table("3c. Creator + bundle selling within S..S+2 of the creator's last earlier WATCHED launch (block recordings), all watched", ALL, dl)
table("3d. The same inside rule #2", R2, dl)

# ---------- 4. bundle wallets reused across launches ----------
wal_c = collections.defaultdict(set)
for r in rows:
    for w in r["bmem"]: wal_c[w].add(r["creator"])
seen = collections.defaultdict(list)                            # wallet -> earlier launches with it in the bundle
for r in rows:
    prev = {id(q): q for w in r["bmem"] for q in seen[w]}.values()
    r["b_prev"] = len(prev); r["b_prev_other"] = sum(1 for q in prev if q["creator"] != r["creator"])
    st = [q for q in prev if q["S"] <= r["S"] - LAG]
    r["b_prev_set"] = len(st); r["b_prev_p2"] = sum(q["p2"] for q in st)
    r["b_prev_set_other"] = [q for q in st if q["creator"] != r["creator"]]
    for w in r["bmem"]: seen[w].append(r)
multi = sum(1 for w, cs in wal_c.items() if len(cs) >= 2)
print(f"\nBundle wallets: {len(wal_c)} distinct; {multi} appear in bundles of >= 2 different creators; "
      f"{sum(1 for r in rows if r['bmem'])} launches have a glued bundle.")
bv = [("has bundle, no wallet seen in an earlier bundle", lambda r: r["bmem"] and r["b_prev"] == 0),
      ("bundle wallet seen in an earlier bundle", lambda r: r["b_prev"] > 0),
      ("... in an earlier bundle of ANOTHER creator", lambda r: r["b_prev_other"] > 0),
      ("bundle-REP: earlier launches with these wallets net > 0", lambda r: r["b_prev_set"] > 0 and r["b_prev_p2"] > 0),
      ("bundle-bad: earlier launches with these wallets net <= 0", lambda r: r["b_prev_set"] > 0 and r["b_prev_p2"] <= 0),
      ("bundle-REP from OTHER creators' launches only", lambda r: r["b_prev_set_other"] and sum(q["p2"] for q in r["b_prev_set_other"]) > 0),
      ("bundle-bad from OTHER creators' launches only", lambda r: r["b_prev_set_other"] and sum(q["p2"] for q in r["b_prev_set_other"]) <= 0)]
table("4a. Bundle wallets reused across launches, all watched launches", ALL, bv)
nh = lambda r: not r["_h"]                                      # no earlier (settled) watched launch by this creator
bv2 = [("first-time creator, bundle-REP (wallets' earlier launches net > 0)", lambda r: nh(r) and r["b_prev_set"] > 0 and r["b_prev_p2"] > 0),
       ("first-time creator, bundle-bad (net <= 0)", lambda r: nh(r) and r["b_prev_set"] > 0 and r["b_prev_p2"] <= 0),
       ("first-time creator, bundle wallets all new", lambda r: nh(r) and r["bmem"] and r["b_prev"] == 0)]
table("4c. Does bundle history add anything for creators WITHOUT their own history? (all watched)", ALL, bv2)
table("4b. The same inside rule #2", R2, bv)

# ---------- 5. pro wallets on the creator's earlier launches ----------
for r in rows:
    h = r["_h"]
    pros = [q for q in h if q["pro_in"]]
    r["pro_hist"] = len(pros); r["pro_hist_p2"] = sum(q["p2"] for q in pros); r["h_n"] = len(h)
pv5 = [("creator has earlier watched launches, none bought by a pro in S..S+2", lambda r: r["h_n"] > 0 and r["pro_hist"] == 0),
       ("a pro bought one of the creator's earlier watched launches in S..S+2", lambda r: r["pro_hist"] > 0),
       ("... and those launches were net > 0 on our model", lambda r: r["pro_hist"] > 0 and r["pro_hist_p2"] > 0),
       ("... and those launches were net <= 0", lambda r: r["pro_hist"] > 0 and r["pro_hist_p2"] <= 0)]
print("\nPro wallets seen buying in S..S+2 of watched launches: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(p for r in rows for p in r["pro_in"]).most_common()))
table("5a. Pro snipers on the creator's EARLIER watched launches, all watched", ALL, pv5)
table("5b. The same inside rule #2", R2, pv5)
REP = lambda r: bool(r["_h"]) and sum(q["p2"] for q in r["_h"]) > 0
BAD = lambda r: bool(r["_h"]) and sum(q["p2"] for q in r["_h"]) <= 0
ov = [("REP (FILTERS2, with a 550-slot lag)", REP), ("REP and a pro bought an earlier launch", lambda r: REP(r) and r["pro_hist"] > 0),
      ("REP, no pro on any earlier launch", lambda r: REP(r) and r["pro_hist"] == 0),
      ("bad history, but a pro bought an earlier launch", lambda r: BAD(r) and r["pro_hist"] > 0),
      ("REP or pro bought an earlier launch", lambda r: REP(r) or r["pro_hist"] > 0),
      ("REP or pro history, outside rule #2 (added launches)", lambda r: (REP(r) or r["pro_hist"] > 0) and not R2(r))]
table("5d. Overlap with creator reputation (REP), all watched", ALL, ov)
sk = [("bad history (FILTERS2 skip)", BAD), ("bundle-bad, creator NOT bad history", lambda r: not BAD(r) and r["b_prev_set"] > 0 and r["b_prev_p2"] <= 0),
      ("early outside buy <= 5 ms, creator NOT bad history", lambda r: not BAD(r) and r["early_n"] >= 1),
      ("any skip: bad history OR bundle-bad OR early buy <= 5 ms", lambda r: BAD(r) or (r["b_prev_set"] > 0 and r["b_prev_p2"] <= 0) or r["early_n"] >= 1),
      ("none of the skips", lambda r: not (BAD(r) or (r["b_prev_set"] > 0 and r["b_prev_p2"] <= 0) or r["early_n"] >= 1))]
table("5e. Skip signals beyond FILTERS2's bad history, all watched", ALL, sk)
table("5f. The same skips inside rule #2", R2, sk)
same = [("this launch: a pro buys in S..S+2 (OUTCOME, look-ahead; context only)", lambda r: bool(r["pro_in"])),
        ("this launch: no pro buys in S..S+2 (OUTCOME, context only)", lambda r: not r["pro_in"])]
table("5c. Context only (not usable at create): launches where a pro bought in S..S+2", ALL, same)

# ---------- 6. early outside buys visible before we fire ----------
ev = [("no outside buy in the feed <= 5 ms after the create", lambda r: r["early_n"] == 0),
      (">= 1 outside buy <= 5 ms", lambda r: r["early_n"] >= 1), (">= 1 outside buy <= 3 ms", lambda r: r["early_n3"] >= 1),
      (">= 1 outside buy <= 5 ms with >= 0.5 SOL", lambda r: r["early_sol"] >= 0.5)]
table("6a. Outside buys already in our feed within 5 ms of the create (not creator/bundle wallets), all watched launches", ALL, ev)
table("6b. The same inside rule #2", R2, ev)

json.dump(dict(rows=[{k: v for k, v in r.items() if not k.startswith("_") and k not in ("outs", "b_prev_set_other", "prev_sp")} for r in rows], hours=HOURS),
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "filters3_rows.json"), "w"))
