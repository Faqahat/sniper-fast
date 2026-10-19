#!/usr/bin/env python3
# READ-ONLY offline analysis: classify every create-slot / next-block buyer as CREATOR-BUNDLE vs INDEPENDENT and build
# the independent-sniper tables (by sender, by leader client), plus our wallet's reference row.
# usage: analyze.py creates.jsonl wallets.jsonl bundles.json > report.txt   (also writes buyers.jsonl)
import json, sys, collections, statistics, math
sys.path.insert(0, "/root/indep")
from common import floor_px, VSOL0

CR, WA, BU = sys.argv[1], sys.argv[2], sys.argv[3]
OUR = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
FRESH_S = 1800      # wallet first seen <= 30 min before the create
FRESH_N = 10        # ... with <= 10 prior txs

recs = [json.loads(l) for l in open(CR)]
recs = [r for r in recs if not r.get("missing")]
# dedupe (a mint may be written twice if its slot was both a rand and an extra slot)
seen, R = set(), []
for r in recs:
    if r["mint"] in seen:
        continue
    seen.add(r["mint"]); R.append(r)
W = {}
for l in open(WA):
    try:
        x = json.loads(l); W[x["w"]] = x
    except Exception:
        pass
try:
    BUN = json.load(open(BU))
except Exception:
    BUN = {}


def grp(c):
    if c in ("AgaveBam", "FireBAM"): return "BAM"
    if c in ("HarmonicAgave", "HarmonicFiredancer"): return "Harmonic"
    if c == "JitoLabs": return "JitoSolana"
    if c == "Agave": return "Agave"
    if c in ("Firedancer", "Frankendancer"): return "Firedancer"
    return "other"


def sender(tx):
    t = [x for x in tx.get("tips") or [] if x[1] > 0]
    labs = sorted({x[0] for x in t})
    if len(labs) == 1:
        return labs[0]
    if len(labs) > 1:
        return "multi:" + "+".join(labs)
    if tx.get("keytip"):
        return tx["keytip"][0] + "(key-only)"
    return "none"


def tip_lam(tx):
    return sum(x[1] for x in tx.get("tips") or [])


def funders(w):
    x = W.get(w)
    if not x: return set()
    return {f[0] for f in x.get("fund") or [] if f[0] and f[0] != w}


def fund_sigs(w):
    x = W.get(w)
    if not x: return set()
    return {f[2] for f in x.get("fund") or []}


# ---------- build buyer events
B = []          # buyer events
FAILS = []      # failed buy attempts
CREATES = []
for r in R:
    S = r["slot"]; c = r["create"]; cr = r["cev"]["creator"]; cp = c["payer"]
    devset = {cr, cp}
    dev_lam = 0
    for e in c["ev"]:
        if e["buy"] and e["user"] in devset:
            dev_lam = e["vsol"] - VSOL0
    fp = floor_px(max(0, dev_lam))
    nb = sorted(r["nb"], key=lambda x: x["d"])
    run = 0
    for x in nb:
        if x["d"] <= 0: continue
        if x["d"] == run + 1 and x["mint_ev"] > 0 and not x["err"]:
            run += 1
        else:
            break
    nxt = r["next"][0] if r["next"] else None
    base_next = (r["nnv"] - 1 - c["nv"])  # non-vote txs after the create in S
    cum = {S: 0}
    acc = base_next
    for n in r["next"]:
        cum[n["slot"]] = acc
        acc += n["nnv"]
    bun = BUN.get(c["sig"]) or {}
    bun_txs = set(bun.get("txs") or [])
    ours_sig = (r.get("ours") or {}).get("sig")
    seq = []
    for e in c["ev"]:
        if e["buy"] and e["user"] not in devset and e["sol"] > 0 and e["tok"] > 0:
            seq.append(dict(tx=c, e=e, sd=0, off=0, in_create=True, slot=S, client=r["client"]))
    txs = [(x, 0) for x in r["rows"]]
    for x in r["nrows"]:
        k = [n["slot"] for n in r["next"]].index(x["slot"]) + 1 if x["slot"] in [n["slot"] for n in r["next"]] else 9
        if k == 1 or x["sig"] == ours_sig:
            txs.append((x, k))
    for x, k in txs:
        off = (x["nv"] - c["nv"]) if k == 0 else cum.get(x["slot"], 0) + x["nv"] + 1
        clientx = r["client"] if k == 0 else next((n["client"] for n in r["next"] if n["slot"] == x["slot"]), "?")
        if x["err"]:
            FAILS.append(dict(mint=r["mint"], sd=k, off=off, sender=sender(x), client=clientx, payer=x["payer"], slot=x["slot"], idx=x["idx"],
                              signers=x.get("signers"), cu_price=x.get("cu_price"), tip=tip_lam(x)))
            continue
        for e in x["ev"]:
            if e["buy"] and e["sol"] > 0 and e["tok"] > 0:
                seq.append(dict(tx=x, e=e, sd=k, off=off, in_create=False, slot=x["slot"], client=clientx))
    seq.sort(key=lambda z: (z["slot"], z["tx"]["idx"]))
    # creator wallet's own buys glued right behind the create (create w/o buy + separate dev buy) also count as dev
    while seq and seq[0]["sd"] == 0 and seq[0]["e"]["user"] in devset and (seq[0]["in_create"] or seq[0]["off"] <= max(run, 1)):
        dev_lam = seq[0]["e"]["vsol"] - VSOL0
        seq.pop(0)
    fp = floor_px(max(0, dev_lam))
    sa = 0
    cre = dict(mint=r["mint"], slot=S, creator=cr, cpayer=cp, client=r["client"], dev=dev_lam, run=run, bt=r.get("blockTime"),
               n_same=sum(1 for z in seq if z["sd"] == 0), n_next=sum(1 for z in seq if z["sd"] == 1), src=r["src"],
               create_sender=sender(c), in_jito_bundle=bun.get("in_bundle"), bundle_n=len(bun_txs))
    CREATES.append(cre)
    for i, z in enumerate(seq):
        e = z["e"]; x = z["tx"]
        fill = (e["sol"] / e["tok"]) / fp if e["tok"] else None
        tiny = ((e["vsol"] - e["sol"]) / (VSOL0 + max(0, dev_lam))) ** 2
        B.append(dict(mint=r["mint"], cslot=S, slot=z["slot"], sd=z["sd"], rank=i, off=z["off"], in_create=z["in_create"],
                      user=e["user"], payer=x["payer"], sig=x["sig"], sender=sender(x), tip=tip_lam(x), cu_price=x.get("cu_price"),
                      cu_limit=x.get("cu_limit"), fee=x.get("fee"), prio=(x.get("fee") or 0) - 5000 * len(x.get("signers") or [1]), cuu=x.get("cuu"), sol=e["sol"], fill=fill, tiny=tiny, sol_ahead=sa, client=z["client"],
                      cclient=r["client"], creator=cr, cpayer=cp, glued=(z["sd"] == 0 and (z["in_create"] or z["off"] <= run)),
                      same_tip_as_create=(sender(x) == cre["create_sender"] and sender(x) != "none"),
                      jito_bundle=(x["sig"] in bun_txs and x["sig"] != c["sig"]) or (z["in_create"] and bool(bun.get("in_bundle"))),
                      ours=(e["user"] == OUR or x["payer"] == OUR), create_bt=r.get("blockTime"), dev=dev_lam, src=r["src"]))
        sa += e["sol"]

print(f"creates parsed: {len(CREATES)}  (rand={sum(1 for c in CREATES if 'rand' in c['src'])}, fill-launches={sum(1 for c in CREATES if any('fill' in s for s in c['src']))}, ours={sum(1 for c in CREATES if any('ours' in s for s in c['src']))})")
print(f"buyer events (create tx + create slot + next block): {len(B)}; failed buy attempts {len(FAILS)}")

# ---------- reuse index: wallet -> launches (creator clusters)
creator_f = {}
for c in CREATES:
    creator_f[c["mint"]] = {c["creator"], c["cpayer"]} | funders(c["creator"]) | funders(c["cpayer"])
# hub funders: fund wallets that show up under >=4 distinct creators
f_creators = collections.defaultdict(set)
for b in B:
    for f in funders(b["user"]):
        f_creators[f].add(b["creator"])
for c in CREATES:
    for f in funders(c["creator"]):
        f_creators[f].add(c["creator"])
HUB = {f for f, s in f_creators.items() if len(s) >= 4}
print(f"funder hubs (fund wallets under >=4 distinct creators; ignored as links): {len(HUB)}")


def ccl(mint):
    return {x for x in creator_f[mint] if x not in HUB}


u_launch = collections.defaultdict(dict)  # user -> mint -> creator
for b in B:
    u_launch[b["user"]][b["mint"]] = b["creator"]

cluster_of_creator = {}
# union creators sharing a non-hub funder
par = {}
def find(a):
    while par.get(a, a) != a:
        par[a] = par.get(par[a], par[a]); a = par[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: par[ra] = rb
for c in CREATES:
    for f in funders(c["creator"]) - HUB:
        union(c["creator"], "F:" + f)
mint_cluster = {c["mint"]: find(c["creator"]) for c in CREATES}

# ---------- classification
by_mint = collections.defaultdict(list)
for b in B:
    by_mint[b["mint"]].append(b)
for b in B:
    u = b["user"]; fu = funders(u) - HUB; cl = ccl(b["mint"])
    w = W.get(u, {})
    b["a"] = b["in_create"] or u in (b["creator"], b["cpayer"])
    b["b"] = bool((fu & cl) or (u in (funders(b["creator"]) | funders(b["cpayer"]))) or
                  (fund_sigs(u) & (fund_sigs(b["creator"]) | fund_sigs(b["cpayer"]))))
    ml = u_launch[u]
    clusters = collections.Counter(mint_cluster.get(m) for m in ml)
    top = clusters.most_common(1)[0] if clusters else (None, 0)
    b["c"] = len(ml) >= 2 and top[1] >= 2 and clusters[mint_cluster.get(b["mint"])] >= 2 and top[1] / len(ml) >= 0.5
    b["n_launch"] = len(ml); b["n_creators"] = len(clusters)
    b["d"] = b["glued"]
    np_ = w.get("n_prior"); obt = w.get("oldest_bt")
    b["n_prior"] = np_
    b["age_s"] = (b["create_bt"] - obt) if (obt and b["create_bt"]) else None
    b["e"] = None  # set after born() is defined
    b["traced"] = u in W
# history retention: the RPC's address index starts near this slot; older wallets look "born" here (truncated)
RET = min((x.get("oldest_slot") for x in W.values() if x.get("oldest_slot")), default=0)
def born(w):
    x = W.get(w) or {}
    if x.get("n_prior") == 0:
        return None
    if not x.get("oldest_slot") or x["oldest_slot"] <= RET + 2000 or x.get("n_prior", 0) >= 1000:
        return None
    # the oldest visible tx must be the wallet's funding (else it was funded before the ledger retention -> old wallet)
    if not any(f[3] == x.get("oldest_bt") for f in x.get("fund") or []):
        return None
    return x.get("oldest_bt")
for b in B:
    b["born"] = born(b["user"])
    np_ = b["n_prior"]
    b["e"] = (np_ is not None and np_ <= FRESH_N and (np_ == 0 or (b["born"] is not None and b["create_bt"] - b["born"] <= FRESH_S)))
    b["c_strong"] = b["c"] and (b["d"] or b["b"] or b["jito_bundle"] or b["off"] <= 30)
    b["c_late"] = b["c"] and not b["c_strong"]
print(f"address-history retention starts ~slot {RET}; wallets with truncated history: {sum(1 for w in W if W[w].get('oldest_slot') and W[w]['oldest_slot'] <= RET + 2000)}")
# propagate inside a mint from seeds (a/b/c_strong/Jito/glued): shared non-hub funder, funded-by/funded a seed, or born
# within 120 s of a seed wallet or of the creator (cohort, non-truncated histories only)
for it in range(2):
    for m, bs in by_mint.items():
        linked = [x for x in bs if x["a"] or x["b"] or x["c_strong"] or x["jito_bundle"] or x["d"]]
        lw = {x["user"] for x in linked}
        lf = set()
        for x in linked:
            lf |= funders(x["user"]) - HUB
        cb = born(bs[0]["creator"])
        seeds_born = [x["born"] for x in linked if x["born"]] + ([cb] if cb else [])
        for x in bs:
            if x["user"] in lw and x not in linked:
                pass
            if not x["b"]:
                fx = funders(x["user"]) - HUB
                if (fx & lf) or (fx & lw) or any(x["user"] in funders(y) for y in lw):
                    x["b"] = True; x["b_prop"] = True
            if x["born"] and not x.get("f") and any(abs(x["born"] - sb) <= 120 for sb in seeds_born if sb is not None) and \
                    not (x["d"] and len(seeds_born) == 1 and x["born"] == seeds_born[0]):
                x["f"] = True

for b in B:
    b.setdefault("f", False)
    strong = b["a"] or b["b"] or b["c_strong"] or b["jito_bundle"]
    if strong:
        b["cls"] = "BUNDLE"
    elif b["d"] and (b["e"] or b["same_tip_as_create"] or b["f"]):
        b["cls"] = "BUNDLE_likely"
    elif b["f"]:
        b["cls"] = "BUNDLE_likely"      # same-birth cohort as the bundle / creator wallets, landed later
    elif b["d"]:
        b["cls"] = "GLUED_unlinked"
    elif b["c_late"]:
        b["cls"] = "AMBIG_reuse"        # bought >=2 launches of this creator cluster, but late and unlinked: team or dev-tracker
    elif b["e"]:
        b["cls"] = "INDEP_fresh"
    else:
        b["cls"] = "INDEP"
    b["is_bundle"] = b["cls"] in ("BUNDLE", "BUNDLE_likely", "GLUED_unlinked")
    if b["ours"]:
        b["cls"] = "OURS"; b["is_bundle"] = False

with open("/root/indep/buyers.jsonl", "w") as f:
    for b in B:
        f.write(json.dumps(b) + "\n")


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs: return None
    k = (len(xs) - 1) * p; lo = math.floor(k); hi = math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] * (hi - k) + xs[hi] * (k - lo)


def med(xs):
    return pct(xs, 0.5)


def f3(x, fmt="{:.3f}"):
    return "-" if x is None else fmt.format(x)


# ---------- sample
CM = {c["mint"]: c for c in CREATES}
rand = [c for c in CREATES if "rand" in c["src"]]
multi = [c for c in CREATES if c["n_same"] >= 2]
print(f"\n=== SAMPLE ===\ncreates: {len(CREATES)}; with >=1 same-slot buyer: {sum(1 for c in CREATES if c['n_same']>=1)}; with >=2 same-slot buyers: {len(multi)}"
      f" (rand-only: {sum(1 for c in rand if c['n_same']>=2)} of {len(rand)}); with any buyer in S or S+1: {sum(1 for c in CREATES if c['n_same']+c['n_next']>0)}")
print("create-slot leader clients (all creates):", dict(collections.Counter(grp(c["client"]) for c in CREATES)))
print("create tx sender (all creates):", collections.Counter(c["create_sender"] for c in CREATES).most_common(12))
print("create in a Jito bundle (only checked for creates with a buyer glued at +1/+2 or a buy inside the create tx):",
      collections.Counter(str(c["in_jito_bundle"]) for c in CREATES))
traced = sum(1 for b in B if b["traced"])
print(f"buyer events with wallet history traced: {traced}/{len(B)}")

# ---------- signals
print("\n=== SIGNAL CONTRIBUTIONS (buyer events in S/S+1; MULTI = creates with >=2 same-slot buyers) ===")
for name, pop in [("ALL", B), ("MULTI", [b for b in B if CM[b['mint']]['n_same'] >= 2]), ("front rank0-2", [b for b in B if b["rank"] <= 2])]:
    n = len(pop)
    print(f"[{name}] n={n}")
    for s, desc in [("a", "(a) buy inside create tx / creator wallet itself"), ("b", "(b) funding link to creator/creator-funder/linked co-buyer"),
                    ("c", "(c) wallet reused on >=2 launches of same creator cluster"), ("c_strong", "(c+) ... and glued/linked/offset<=30"),
                    ("f", "(f) same-birth cohort (<=120 s) as a bundle wallet / creator"), ("jito_bundle", "(d*) same Jito bundle as create (explorer API)"),
                    ("d", "(d) glued: contiguous buy run right after create"), ("same_tip_as_create", "(d') same tip sender as create tx"),
                    ("e", f"(e) fresh wallet (<= {FRESH_N} prior txs, first seen <= {FRESH_S//60} min before)")]:
        k = sum(1 for b in pop if b.get(s))
        only = sum(1 for b in pop if b.get(s) and sum(1 for t in ("a", "b", "c", "d", "e", "f", "jito_bundle") if b.get(t)) == 1)
        print(f"   {desc:70s} {k:5d} ({100*k/max(1,n):4.1f}%)  only-this-signal {only}")
    cc = collections.Counter(b["cls"] for b in pop)
    print("   classes:", {k: f"{v} ({100*v/max(1,n):.1f}%)" for k, v in cc.most_common()})

# ---------- verdict tables
print("\n=== FRONT POSITIONS: share creator-bundle vs independent ===")
def frontrow(lbl, pop):
    n = len(pop)
    if not n:
        print(f"  {lbl:40s} n=0"); return
    cb = sum(1 for b in pop if b["cls"] == "BUNDLE"); bl = sum(1 for b in pop if b["cls"] == "BUNDLE_likely")
    gu = sum(1 for b in pop if b["cls"] == "GLUED_unlinked"); ind = sum(1 for b in pop if b["cls"] in ("INDEP", "INDEP_fresh")); amb = sum(1 for b in pop if b["cls"] == "AMBIG_reuse")
    fr = sum(1 for b in pop if b["cls"] == "INDEP_fresh"); ours = sum(1 for b in pop if b["cls"] == "OURS")
    print(f"  {lbl:40s} n={n:5d}  bundle {100*cb/n:5.1f}%  likely {100*bl/n:5.1f}%  glued-unlinked {100*gu/n:5.1f}%  | ambig-reuse {100*amb/n:4.1f}% | indep {100*ind/n:5.1f}% (fresh-unlinked {100*fr/n:4.1f}%) ours {ours}")
for k in range(3):
    frontrow(f"rank {k} (all creates)", [b for b in B if b["rank"] == k])
frontrow("rank 0-2 (all creates)", [b for b in B if b["rank"] <= 2])
frontrow("rank 0-2 (MULTI creates)", [b for b in B if b["rank"] <= 2 and CM[b['mint']]['n_same'] >= 2])
frontrow("rank 0-2 (rand creates only)", [b for b in B if b["rank"] <= 2 and "rand" in b["src"]])
frontrow("rank 0-2 (fill-launches, dev>=0.5 sample)", [b for b in B if b["rank"] <= 2 and any("fill" in s for s in b["src"])])
frontrow("all buyers fill<=1.10x", [b for b in B if b["fill"] is not None and b["fill"] <= 1.10])
frontrow("all buyers fill<=1.05x", [b for b in B if b["fill"] is not None and b["fill"] <= 1.05])
frontrow("all buyers fill<=1.10x (rand)", [b for b in B if b["fill"] is not None and b["fill"] <= 1.10 and "rand" in b["src"]])
frontrow("same slot (sd0) all", [b for b in B if b["sd"] == 0])
frontrow("next block (sd1) all", [b for b in B if b["sd"] == 1])

# ---------- earlier finding: co_rank0 in the fill launches
print("\n=== RE-CHECK of the earlier 'co_rank0 = 1.036x, Lunar dominant' (fill-launch sample, rank 0) ===")
fl0 = [b for b in B if b["rank"] == 0 and any("fill" in s for s in b["src"])]
print(f"  n={len(fl0)} fill p50={f3(med([b['fill'] for b in fl0]))}")
for cls in ("BUNDLE", "BUNDLE_likely", "GLUED_unlinked", "AMBIG_reuse", "INDEP", "INDEP_fresh", "OURS"):
    xs = [b for b in fl0 if b["cls"] == cls]
    if xs:
        print(f"   {cls:15s} n={len(xs):4d} ({100*len(xs)/len(fl0):4.1f}%) fill p10={f3(pct([b['fill'] for b in xs],.1))} p50={f3(med([b['fill'] for b in xs]))} "
              f"senders={collections.Counter(b['sender'] for b in xs).most_common(5)}")
lun = [b for b in B if b["sender"] == "lunar"]
print(f"  ALL lunar-tipped buyer events: n={len(lun)}; classes {collections.Counter(b['cls'] for b in lun).most_common()}")
lunc = [c for c in CREATES if c["create_sender"] == "lunar"]
print(f"  creates whose CREATE tx tips Lunar: {len(lunc)}; of them with a glued buy run: {sum(1 for c in lunc if c['run']>0)}")

# ---------- independent sniper tables
IND = [b for b in B if b["cls"] in ("INDEP", "INDEP_fresh")]
first_ind = {}
for m, bs in by_mint.items():
    ii = [b for b in sorted(bs, key=lambda b: b["rank"]) if b["cls"] in ("INDEP", "INDEP_fresh")]
    for j, b in enumerate(ii):
        b["rank_ind"] = j
    if ii:
        first_ind[m] = ii[0]
for b in B:
    if b["cls"] == "OURS":
        ii = [x for x in sorted(by_mint[b["mint"]], key=lambda x: x["rank"]) if x["cls"] in ("INDEP", "INDEP_fresh") and x["rank"] < b["rank"]]
        b["rank_ind"] = len(ii)


def table(title, pop, key):
    print(f"\n=== {title} ===")
    print(f"{'sender':34s} {'n':>5s} {'%S':>4s} {'medOff':>6s} {'medRkI':>6s} {'SOLahead':>8s} {'fill p10':>8s} {'p50':>6s} {'%1stInd':>7s} {'%<=1.10':>7s} {'medCUprice':>10s} {'%noCU':>5s} {'medTipSOL':>9s} {'fail':>4s} {'tiny50':>6s} {'prioSOL':>8s} {'uL/CU':>8s}")
    g = collections.defaultdict(list)
    for b in pop:
        g[key(b)].append(b)
    rows = sorted(g.items(), key=lambda kv: -len(kv[1]))
    for k, bs in rows:
        if len(bs) < 3: continue
        n = len(bs)
        nf = sum(1 for f in FAILS if f["sender"] == k) if key is sender_key else 0
        print(f"{str(k)[:34]:34s} {n:5d} {100*sum(1 for b in bs if b['sd']==0)/n:4.0f} {f3(med([b['off'] for b in bs]),'{:.0f}'):>6s} "
              f"{f3(med([b.get('rank_ind') for b in bs]),'{:.0f}'):>6s} {f3(med([b['sol_ahead']/1e9 for b in bs]),'{:.2f}'):>8s} "
              f"{f3(pct([b['fill'] for b in bs],.1)):>8s} {f3(med([b['fill'] for b in bs])):>6s} "
              f"{100*sum(1 for b in bs if first_ind.get(b['mint']) is b)/n:7.0f} {100*sum(1 for b in bs if b['fill'] and b['fill']<=1.10)/n:7.0f} "
              f"{f3(med([b['cu_price'] for b in bs]),'{:.0f}'):>10s} {100*sum(1 for b in bs if not b['cu_price'])/n:5.0f} "
              f"{f3(med([b['tip']/1e9 for b in bs if b['tip']>0]),'{:.6f}'):>9s} {nf:4d} {f3(med([b['tiny'] for b in bs])):>6s} {f3(med([b['prio']/1e9 for b in bs]),'{:.5f}'):>8s} {f3(med([b['prio']*1e6/b['cuu'] for b in bs if b.get('cuu')]),'{:.0f}'):>8s}")


def sender_key(b):
    return b["sender"]


table("INDEPENDENT buyers by sender (S + next block)", IND, sender_key)
table("INDEPENDENT buyers by sender, MULTI creates only", [b for b in IND if CM[b['mint']]['n_same'] >= 2], sender_key)
table("INDEPENDENT buyers by sender, SAME SLOT only", [b for b in IND if b["sd"] == 0], sender_key)
table("INDEPENDENT buyers by landing-slot leader client", IND, lambda b: grp(b["client"]))
for cg in ("BAM", "Harmonic", "JitoSolana", "Firedancer", "Agave", "other"):
    pop = [b for b in IND if grp(b["client"]) == cg]
    if len(pop) >= 10:
        table(f"INDEPENDENT by sender | landing leader client = {cg}", pop, sender_key)

print("\n=== FIRST INDEPENDENT BUYER per create: sender share and fill ===")
fi = list(first_ind.values())
print(f"  creates with >=1 independent buyer in S/S+1: {len(fi)}; landed same slot: {100*sum(1 for b in fi if b['sd']==0)/max(1,len(fi)):.0f}%")
print(f"  first-indep fill: p10={f3(pct([b['fill'] for b in fi],.1))} p25={f3(pct([b['fill'] for b in fi],.25))} p50={f3(med([b['fill'] for b in fi]))} p75={f3(pct([b['fill'] for b in fi],.75))}")
print(f"  first-indep median offset {f3(med([b['off'] for b in fi]),'{:.0f}')} txs; median SOL ahead {f3(med([b['sol_ahead']/1e9 for b in fi]),'{:.2f}')}; median dev {f3(med([b['dev']/1e9 for b in fi]),'{:.2f}')} SOL")
fi_nb = [b for b in fi if not any(x["is_bundle"] for x in by_mint[b["mint"]])]
fi_b = [b for b in fi if any(x["is_bundle"] for x in by_mint[b["mint"]])]
print(f"  first-indep fill when NO bundle ahead: n={len(fi_nb)} p10={f3(pct([b['fill'] for b in fi_nb],.1))} p50={f3(med([b['fill'] for b in fi_nb]))}")
print(f"  first-indep fill when a bundle is ahead: n={len(fi_b)} p10={f3(pct([b['fill'] for b in fi_b],.1))} p50={f3(med([b['fill'] for b in fi_b]))}")
for lo, hi, lbl in [(0, 0.5e9, "dev<0.5"), (0.5e9, 2e9, "dev 0.5-2"), (2e9, 8e9, "dev 2-8"), (8e9, 1e15, "dev>=8")]:
    xs = [b for b in fi if lo <= b["dev"] < hi]
    if xs:
        print(f"   {lbl:10s} n={len(xs):4d} first-indep fill p10={f3(pct([b['fill'] for b in xs],.1))} p50={f3(med([b['fill'] for b in xs]))} sameslot={100*sum(1 for b in xs if b['sd']==0)/len(xs):.0f}%")
print("  first-indep sender share:", [(k, v, f"{100*v/len(fi):.0f}%") for k, v in collections.Counter(b["sender"] for b in fi).most_common(14)])
print("  first-indep by create leader client:")
for cg in ("BAM", "Harmonic", "JitoSolana", "Firedancer", "Agave", "other"):
    xs = [b for b in fi if grp(b["cclient"]) == cg]
    if xs:
        print(f"   {cg:11s} n={len(xs):4d} fill p50={f3(med([b['fill'] for b in xs]))} sameslot={100*sum(1 for b in xs if b['sd']==0)/len(xs):.0f}% top senders={collections.Counter(b['sender'] for b in xs).most_common(4)}")

print("\n=== BUNDLE-class buyers: where/how ===")
BB = [b for b in B if b["is_bundle"]]
print(f"  n={len(BB)} median offset {f3(med([b['off'] for b in BB]),'{:.0f}')} fill p50 {f3(med([b['fill'] for b in BB]))}; sd0 {100*sum(1 for b in BB if b['sd']==0)/max(1,len(BB)):.0f}%")
print("  senders:", collections.Counter(b["sender"] for b in BB).most_common(10))
print("  create-tx sender of bundled launches:", collections.Counter(CM[b["mint"]]["create_sender"] for b in BB if b["rank"] == 0).most_common(10))

print("\n=== OUR wallet (FRZh..) buys ===")
OB = [b for b in B if b["cls"] == "OURS"]
print(f"  n={len(OB)}")
print(f"  {'mint':10s} {'via':12s} {'sd':>2s} {'off':>5s} {'rank':>4s} {'rkInd':>5s} {'SOLahead':>8s} {'fill':>6s} {'client':10s}")
viamap = {}
for c in R:
    if c.get("ours"):
        viamap[c["ours"]["sig"]] = c["ours"].get("via")
for b in sorted(OB, key=lambda b: b["cslot"]):
    print(f"  {b['mint'][:10]:10s} {str(viamap.get(b['sig'],'?')):12s} {b['sd']:2d} {b['off']:5d} {b['rank']:4d} {b.get('rank_ind',-1):5d} {b['sol_ahead']/1e9:8.2f} {f3(b['fill']):>6s} {grp(b['client']):10s} sender={b['sender']}")
for via in sorted({viamap.get(b["sig"]) for b in OB}, key=str):
    xs = [b for b in OB if viamap.get(b["sig"]) == via]
    print(f"  via {via}: n={len(xs)} med off={f3(med([b['off'] for b in xs]),'{:.0f}')} med rank={f3(med([b['rank'] for b in xs]),'{:.0f}')} med rankInd={f3(med([b.get('rank_ind') for b in xs]),'{:.0f}')} fill p50={f3(med([b['fill'] for b in xs]))} sd: {collections.Counter(b['sd'] for b in xs)}")

print("\n=== GLUED creates (buy run right behind the create): Jito-bundle confirmation by create-slot client / create sender ===")
gl = [c for c in CREATES if c["run"] > 0]
print(f"  creates with a glued run: {len(gl)} of {len(CREATES)}; run length median {med([c['run'] for c in gl])}, p90 {pct([c['run'] for c in gl], .9)}")
for cg in ("BAM", "Harmonic", "JitoSolana", "Firedancer", "Agave", "other"):
    xs = [c for c in gl if grp(c["client"]) == cg]
    if xs:
        print(f"   {cg:11s} glued creates {len(xs):4d}  in Jito bundle: {collections.Counter(str(c['in_jito_bundle']) for c in xs)}  create senders {collections.Counter(c['create_sender'] for c in xs).most_common(4)}")
for snd in collections.Counter(c["create_sender"] for c in gl):
    xs = [c for c in gl if c["create_sender"] == snd]
    if len(xs) >= 3:
        print(f"   create sender {snd:24s} n={len(xs):4d} in Jito bundle: {collections.Counter(str(c['in_jito_bundle']) for c in xs)}")
print(f"  share of ALL creates that have a glued creator bundle: {100*len(gl)/len(CREATES):.1f}%  (rand only: {100*sum(1 for c in gl if 'rand' in c['src'])/max(1,sum(1 for c in CREATES if 'rand' in c['src'])):.1f}%)")
print(f"  share of creates with >=1 S/S+1 buyer that have a glued bundle: {100*len(gl)/max(1,sum(1 for c in CREATES if c['n_same']+c['n_next']>0)):.1f}%")

print("\n=== FAILED buy attempts (txs touching the mint that errored, S after create + next block) by sender ===")
fc = collections.Counter(f["sender"] for f in FAILS)
sc = collections.Counter(b["sender"] for b in IND)
for k, v in fc.most_common(14):
    print(f"   {k:34s} failed {v:5d}  indep successes {sc.get(k,0):5d}")

print("\n=== TOP INDEPENDENT WALLETS (by # buys in S/S+1) — who are the real snipers and how they send ===")
uw = collections.defaultdict(list)
for b in IND:
    uw[b["user"]].append(b)
print(f"{'wallet':12s} {'n':>4s} {'#1stInd':>7s} {'%S':>4s} {'medOff':>6s} {'fill p50':>8s} {'SOLahead':>8s} {'medCU':>9s} {'medTip':>7s}  senders")
for w, bs in sorted(uw.items(), key=lambda kv: -len(kv[1]))[:20]:
    n = len(bs)
    print(f"{w[:12]:12s} {n:4d} {sum(1 for b in bs if first_ind.get(b['mint']) is b):7d} {100*sum(1 for b in bs if b['sd']==0)/n:4.0f} {f3(med([b['off'] for b in bs]),'{:.0f}'):>6s} "
          f"{f3(med([b['fill'] for b in bs])):>8s} {f3(med([b['sol_ahead']/1e9 for b in bs]),'{:.2f}'):>8s} {f3(med([b['cu_price'] for b in bs]),'{:.0f}'):>9s} "
          f"{f3(med([b['tip']/1e9 for b in bs]),'{:.4f}'):>7s}  {collections.Counter(b['sender'] for b in bs).most_common(3)}")
print("  most frequent FIRST independent buyers:", [(w[:10], k) for w, k in collections.Counter(b["user"] for b in fi).most_common(10)])
T4 = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
t4 = [b for b in B if b["user"] == T4]
if t4:
    print(f"  4yFAz (clone target) in sample: n={len(t4)} classes {collections.Counter(b['cls'] for b in t4)} sd0 {sum(1 for b in t4 if b['sd']==0)} "
          f"med off {f3(med([b['off'] for b in t4]),'{:.0f}')} fill p50 {f3(med([b['fill'] for b in t4]))} rankInd p50 {f3(med([b.get('rank_ind') for b in t4]),'{:.0f}')} "
          f"first-indep {sum(1 for b in t4 if first_ind.get(b['mint']) is b)} senders {collections.Counter(b['sender'] for b in t4).most_common(4)} cu p50 {f3(med([b['cu_price'] for b in t4]),'{:.0f}')}")

print("\n=== TINY-BUY FILL by independent rank (fill a ~0-size buy like ours would get at that queue position) ===")
for bundled in (False, True):
    for k in range(4):
        xs = [b for b in IND if b.get("rank_ind") == k and any(x["is_bundle"] for x in by_mint[b["mint"]]) == bundled]
        if xs:
            print(f"  bundle-ahead={str(bundled):5s} indep-rank {k}: n={len(xs):4d} tiny-fill p10={f3(pct([b['tiny'] for b in xs],.1))} p25={f3(pct([b['tiny'] for b in xs],.25))} p50={f3(med([b['tiny'] for b in xs]))} p75={f3(pct([b['tiny'] for b in xs],.75))}  same-slot {100*sum(1 for b in xs if b['sd']==0)/len(xs):.0f}%")
xs = [b for b in IND if b.get("rank_ind") == 0]
print(f"  ALL first-independent: n={len(xs)} tiny-fill p10={f3(pct([b['tiny'] for b in xs],.1))} p50={f3(med([b['tiny'] for b in xs]))} p75={f3(pct([b['tiny'] for b in xs],.75))}; share <=1.05: {100*sum(1 for b in xs if b['tiny']<=1.05)/len(xs):.0f}%  <=1.10: {100*sum(1 for b in xs if b['tiny']<=1.10)/len(xs):.0f}%")
print(f"  bundle-ahead share among creates with an independent buyer: {100*sum(1 for b in xs if any(x['is_bundle'] for x in by_mint[b['mint']]))/len(xs):.0f}%")
print(f"  median SOL in the creator bundle ahead (creates with bundle): {f3(med([sum(x['sol'] for x in by_mint[m] if x['is_bundle'])/1e9 for m in by_mint if any(x['is_bundle'] for x in by_mint[m])]),'{:.2f}')} SOL")

print("\n=== HEAD-TO-HEAD (independents in the SAME create): row sender landed before column sender, % of pairs (n pairs) ===")
MAIN = ["helius_sender", "none", "nozomi", "astralane", "jito", "0slot", "flashblock"]
win = collections.Counter(); tot = collections.Counter()
for m, bs in by_mint.items():
    ii = [b for b in bs if b["cls"] in ("INDEP", "INDEP_fresh")]
    # one entry per wallet per create (its first buy)
    seenw = {}
    for b in sorted(ii, key=lambda b: b["rank"]):
        seenw.setdefault(b["user"], b)
    ii = list(seenw.values())
    for i in range(len(ii)):
        for j in range(len(ii)):
            a, c = ii[i], ii[j]
            if i == j or a["sender"] == c["sender"]: continue
            tot[(a["sender"], c["sender"])] += 1
            if a["rank"] < c["rank"]:
                win[(a["sender"], c["sender"])] += 1
print(f"{'':16s}" + "".join(f"{c[:10]:>14s}" for c in MAIN))
for a in MAIN:
    row = f"{a[:16]:16s}"
    for c in MAIN:
        t = tot[(a, c)]
        row += f"{(f'{100*win[(a,c)]/t:.0f}% ({t})' if t >= 5 else '-'):>14s}"
    print(row)

print("\n=== WITHIN-WALLET sender comparison (same bot, different send path; wallets with >=2 buys on each of >=2 senders) ===")
for w, bs in uw.items():
    bysnd = collections.defaultdict(list)
    for b in bs:
        bysnd[b["sender"]].append(b)
    good = {k: v for k, v in bysnd.items() if len(v) >= 2}
    if len(good) >= 2:
        print(f"  {w[:10]}: " + " | ".join(f"{k} n={len(v)} sameslot={100*sum(1 for b in v if b['sd']==0)/len(v):.0f}% medOff={med([b['off'] for b in v]):.0f} 1stInd={sum(1 for b in v if first_ind.get(b['mint']) is b)}/{len(v)}" for k, v in sorted(good.items(), key=lambda kv: -len(kv[1]))))

print("\n=== 'none' (no tip) independents split by compute-unit price ===")
nn = [b for b in IND if b["sender"] == "none"]
for lbl, f in [("no cu_price", lambda b: not b["cu_price"]), ("cu_price<1M", lambda b: b["cu_price"] and b["cu_price"] < 1e6), ("cu_price>=1M", lambda b: b["cu_price"] and b["cu_price"] >= 1e6)]:
    xs = [b for b in nn if f(b)]
    if xs:
        print(f"  {lbl:13s} n={len(xs):4d} sameslot={100*sum(1 for b in xs if b['sd']==0)/len(xs):.0f}% medOff={f3(med([b['off'] for b in xs]),'{:.0f}')} 1stInd={100*sum(1 for b in xs if first_ind.get(b['mint']) is b)/len(xs):.0f}% fill p50={f3(med([b['fill'] for b in xs]))}")

print("\n=== SPRAY RACES: same bot (fee payer), same create, txs via DIFFERENT senders (landed ok OR failed) -> which path landed first ===")
att = collections.defaultdict(list)   # (payer, mint) -> [(slot, idx, sender, ok, client)]
bundle_payers = {b["payer"] for b in B if b["is_bundle"]}
for b in B:
    if b["cls"] in ("INDEP", "INDEP_fresh", "AMBIG_reuse"):
        att[(b["payer"], b["mint"])].append((b["slot"], b["off"], b["sender"], True, b["client"]))
for f in FAILS:
    if f["payer"] not in bundle_payers:
        att[(f["payer"], f["mint"])].append((f["slot"], f["off"], f["sender"], False, f["client"]))
races = []
for k, ent in att.items():
    if len({e[2] for e in ent}) >= 2:
        ent = sorted(set(ent), key=lambda e: e[1])
        races.append((k, ent))
print(f"  races (bot x create with >=2 distinct senders landing): {len(races)}; bots: {len({k[0] for k, _ in races})}")
def race_tables(rs, label):
    firstc = collections.Counter(); present = collections.Counter(); pw = collections.Counter(); pt = collections.Counter()
    for k, ent in rs:
        snds = []
        for e in ent:
            if e[2] not in snds:
                snds.append(e[2])
        firstc[snds[0]] += 1
        for x in snds:
            present[x] += 1
        for a_ in range(len(snds)):
            for c_ in range(a_ + 1, len(snds)):
                pw[(snds[a_], snds[c_])] += 1
                pt[(snds[a_], snds[c_])] += 1; pt[(snds[c_], snds[a_])] += 1
    print(f"  [{label}] races={len(rs)}")
    print(f"  {'sender':34s} {'in races':>8s} {'landed 1st':>10s} {'%1st':>5s}")
    for k2, v in present.most_common(14):
        if v >= 3:
            print(f"  {k2[:34]:34s} {v:8d} {firstc[k2]:10d} {100*firstc[k2]/v:5.0f}")
    RS = [k2 for k2, v in present.most_common(9) if not k2.startswith("multi")][:7]
    print("  pairwise: row landed before column (% of races with both, n):")
    print(f"  {'':16s}" + "".join(f"{c[:11]:>13s}" for c in RS))
    for a in RS:
        row = f"  {a[:16]:16s}"
        for c in RS:
            t = pt[(a, c)]
            row += f"{(f'{100*pw[(a,c)]/t:.0f}% ({t})' if (t >= 4 and a != c) else '-'):>13s}"
        print(row)
race_tables(races, "all bots")
print("  bots in races:", collections.Counter(k[0][:10] for k, _ in races).most_common(12))
race_tables([r for r in races if r[0][0] == T4], "4yFAz only")
for cg in ("BAM", "Harmonic", "JitoSolana", "Firedancer"):
    rr = [r for r in races if grp(r[1][0][4]) == cg]
    if len(rr) >= 15:
        race_tables(rr, f"first-landing leader client = {cg}")

print("\n=== FAILED-tx senders by bot (top fee payers of failed attempts) ===")
fp_c = collections.Counter(f["payer"] for f in FAILS)
succ_by_payer = collections.Counter(b["payer"] for b in B)
for p_, n_ in fp_c.most_common(12):
    fs = [f for f in FAILS if f["payer"] == p_]
    print(f"  {p_[:10]} fails {n_:5d} successes {succ_by_payer.get(p_,0):4d} senders {collections.Counter(f['sender'] for f in fs).most_common(4)} sd0 {100*sum(1 for f in fs if f['sd']==0)/len(fs):.0f}% medOff {med([f['off'] for f in fs]):.0f}")
T4f = [f for f in FAILS if f["payer"] == T4]
if T4f:
    print(f"  4yFAz failed attempts: {len(T4f)} senders {collections.Counter(f['sender'] for f in T4f).most_common(8)}")

print("\n=== WHAT ORDERS INDEPENDENTS INSIDE A CREATE? concordance (1.0 = higher value always earlier, 0.5 = no effect) ===")
def conc(key, pop_by_mint):
    c = d = 0
    for m, bs in pop_by_mint.items():
        gg = [b for b in bs if b.get(key) is not None]
        for i in range(len(gg)):
            for j in range(i + 1, len(gg)):
                a, b2 = gg[i], gg[j]
                if a[key] == b2[key] or a["slot"] != b2["slot"]: continue
                earlier = a if a["rank"] < b2["rank"] else b2
                higher = a if a[key] > b2[key] else b2
                if earlier is higher: c += 1
                else: d += 1
    return c, d
ibm = collections.defaultdict(list)
for b in IND:
    b["prio_per_cu"] = b["prio"] * 1e6 / b["cuu"] if b.get("cuu") else None
    b["prio_sol"] = b["prio"]
    ibm[b["mint"]].append(b)
for key in ("prio_per_cu", "prio_sol", "tip", "sol"):
    c, d = conc(key, ibm)
    print(f"  same-slot pairs, {key:12s}: concordance {c/max(1,c+d):.3f} (pairs {c+d})")
print("  prio fee per CU used (microlamports/CU) tiers -> independents:")
def tier(v):
    if v is None: return "?"
    return "<1k" if v < 1e3 else "1k-100k" if v < 1e5 else "100k-1M" if v < 1e6 else "1M-10M" if v < 1e7 else "10M-100M" if v < 1e8 else ">=100M"
tg = collections.defaultdict(list)
for b in IND:
    tg[tier(b["prio_per_cu"])].append(b)
for t in ("<1k", "1k-100k", "100k-1M", "1M-10M", "10M-100M", ">=100M", "?"):
    xs = tg.get(t)
    if xs:
        print(f"   {t:9s} n={len(xs):4d} sameslot={100*sum(1 for b in xs if b['sd']==0)/len(xs):3.0f}% medOff={f3(med([b['off'] for b in xs]),'{:.0f}'):>4s} 1stInd={100*sum(1 for b in xs if first_ind.get(b['mint']) is b)/len(xs):3.0f}% medPrio={f3(med([b['prio']/1e9 for b in xs]),'{:.5f}')} SOL fill p50={f3(med([b['fill'] for b in xs]))}")
OBp = [b for b in B if b["cls"] == "OURS"]
if OBp:
    print(f"  OURS: prio per CU median {f3(med([b['prio']*1e6/b['cuu'] for b in OBp if b.get('cuu')]),'{:.0f}')} uL/CU, prio {f3(med([b['prio']/1e9 for b in OBp]),'{:.5f}')} SOL, cu_price {f3(med([b['cu_price'] for b in OBp]),'{:.0f}')}")

print("\n=== HELIUS SENDER split by tip size (<0.0002 SOL ~ SWQoS-only mode; >=0.0002 ~ default dual-route Jito+SWQoS) ===")
for lbl, f in [("tip<0.0002", lambda b: b["tip"] < 200_000), ("tip>=0.0002", lambda b: b["tip"] >= 200_000), ("tip>=0.001", lambda b: b["tip"] >= 1_000_000)]:
    xs = [b for b in IND if b["sender"] == "helius_sender" and f(b)]
    if xs:
        print(f"  {lbl:12s} n={len(xs):4d} wallets={len({b['user'] for b in xs}):3d} sameslot={100*sum(1 for b in xs if b['sd']==0)/len(xs):.0f}% medOff={f3(med([b['off'] for b in xs]),'{:.0f}')} "
              f"1stInd={100*sum(1 for b in xs if first_ind.get(b['mint']) is b)/len(xs):.0f}% fill p50={f3(med([b['fill'] for b in xs]))} medPrio={f3(med([b['prio']/1e9 for b in xs]),'{:.5f}')}")

print("\n=== WITHIN-WALLET pairwise summary: for bots that used both senders (>=2 buys each), which had the lower median offset ===")
PAIRS = [("helius_sender", "nozomi"), ("helius_sender", "astralane"), ("helius_sender", "jito"), ("helius_sender", "none"), ("nozomi", "astralane"),
         ("nozomi", "jito"), ("nozomi", "none"), ("astralane", "jito"), ("jito", "0slot"), ("none", "jito")]
for a, c in PAIRS:
    wa = wc = 0; da = []
    for w, bs in uw.items():
        A = [b for b in bs if b["sender"] == a]; C = [b for b in bs if b["sender"] == c]
        if len(A) >= 2 and len(C) >= 2:
            ma, mc = med([b["off"] for b in A]), med([b["off"] for b in C])
            if ma < mc: wa += 1
            elif mc < ma: wc += 1
            da.append(mc - ma)
    if wa + wc:
        print(f"  {a:14s} vs {c:10s}: bots={wa+wc:3d}  {a} faster in {wa}, {c} faster in {wc}; median (off_{c} - off_{a}) = {med(da):.0f} txs")

print("\n=== SENDER x LANDING-LEADER CLIENT (independents; helius split by tip mode): %first-indep / median offset / %same-slot (n) ===")
def snd2(b):
    if b["sender"] == "helius_sender":
        return "helius_dual(tip>=.0002)" if b["tip"] >= 200_000 else "helius_swqos(tip<.0002)"
    return b["sender"]
CL = ["BAM", "Harmonic", "JitoSolana", "Firedancer"]
print(f"{'sender':26s}" + "".join(f"{c:>24s}" for c in CL) + f"{'ALL':>24s}")
for sn in ["helius_dual(tip>=.0002)", "helius_swqos(tip<.0002)", "none", "nozomi", "jito", "astralane", "0slot", "flashblock", "speedlanding", "landx"]:
    row = f"{sn:26s}"
    for c in CL + ["ALL"]:
        xs = [b for b in IND if snd2(b) == sn and (c == "ALL" or grp(b["client"]) == c)]
        if len(xs) >= 8:
            row += f"{f'{100*sum(1 for b in xs if first_ind.get(b[chr(109)+chr(105)+chr(110)+chr(116)]) is b)/len(xs):.0f}% / {med([b[chr(111)+chr(102)+chr(102)] for b in xs]):.0f} / {100*sum(1 for b in xs if b[chr(115)+chr(100)]==0)/len(xs):.0f}% ({len(xs)})':>24s}"
        else:
            row += f"{'-':>24s}"
    print(row)
