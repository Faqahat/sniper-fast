# READ-ONLY (host): which CREATE-TIME filters give more qualifying launches per hour than rule #2 and stay profitable,
# on the realistic landing model (sim_land.py's run(), unchanged economics):
#   our 1.5 SOL buy lands T ms (feed time) after the create, T by the create-slot leader's client: BAM 20, Jito-client 35,
#   Harmonic 32, other 35 (pessimistic column +20 ms); it goes after every outside buy our feed saw before T (RACE obs
#   outs, matched to the block by wallet prefix) and after the creator's glued bundle; created late in the slot
#   (create_ms + T > slot) = after the whole create slot. Price cap: refused if our tokens < 85% of the post-bundle quote
#   (refused = priority fee 0.011 lost). Filled: + tips by class (BAM route 0.015, Jito-client 0.004, Harmonic 0.001,
#   other 0.004), pump fee per side, sell tx 0.0007; sell ALL at the end of slot S+2 (S+1 also shown).
# Launch universe = every launch the engine WATCHED (base filter + close leader -> RACE seen + RACE obs) in the logs.
# usage: python3 filters.py <launches.json> <rec dir> <leaders.json> <tipmap.json> <out prefix> [--yday-map rec_dir_with_leader_client]
import sys, os, re, json, glob, statistics, collections

LJ, REC, LEAD, TIPMAP, OUTP = sys.argv[1:6]
YDAY = sys.argv[sys.argv.index("--yday-map") + 1] if "--yday-map" in sys.argv else None
SIZE, PRIO, CAP, SELL_FEE, PESS = 1.5, 0.011, 1500, 0.0007, 20.0
T_BY = {"bam": 20.0, "jito": 35.0, "harmonic": 32.0, "other": 35.0}
TIP_BY = {"bam": 0.015, "jito": 0.004, "harmonic": 0.001, "other": 0.004}
OURS6 = ("FRZh63", "2g7rYv")
GROUPS = {"A": ["dry1h", "run1"], "B": ["cov", "alt", "cad", "edge1", "latest", "edge2", "edge3", "edge5", "night"], "C": ["morning"]}
GNAME = {"A": "A in-sample: evening (1 h dry 19:50-20:50 + Run 1 21:54-22:26, 10-20)",
         "B": "B out-of-sample: older + overnight (10-20 12:40-19:24, 23:30-00:18, 01:16-01:56)",
         "C": "C out-of-sample: current paper log (10-21 morning)"}

D = json.load(open(LJ)); spans = D["spans"]
LD = json.load(open(LEAD)); TM = json.load(open(TIPMAP))
HOURS = {g: sum(spans[l]["hours"] for l in ls if l in spans) for g, ls in GROUPS.items()}

# leader client as the engine saw it at the time: FAST-FIRE lines (fired launches) > yesterday's map (the recorder's
# /root/fix2/leader_rtt_new.json clients, 10-20 evening; many "AgaveBam" leaders read "JitoLabs" in gossip on 10-21) >
# current gossip (getClusterNodes now; used as-is for the 10-21 morning log)
ymap = {}
if YDAY:
    for f in glob.glob(os.path.join(YDAY, "*.json")):
        if f.endswith("_index.json"): continue
        x = json.load(open(f))
        if x.get("leader") and x.get("leader_client"): ymap[x["leader"]] = x["leader_client"]
ff8 = {}
for r in D["launches"]:
    f = r.get("fastfire")
    if f: ff8[f["leader"]] = f["client"]


def cls(c):
    c = c or ""
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if c.startswith("Harmonic"): return "harmonic"
    if c == "JitoLabs": return "jito"
    return "other"


def client_of(r):
    if r.get("fastfire"): return r["fastfire"]["client"], "fastfire"
    leader, cur = LD.get(str(r["S"]), [None, None])
    if r["log"] != "morning":
        if leader in ymap: return ymap[leader], "yday-map"
        if leader and leader[:8] in ff8: return ff8[leader[:8]], "fastfire-leader"
    return cur, "gossip-now"


def pre(t):
    return (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])


def clean(r):
    """live runs: drop OUR real buys/sells and replay the curve without them (others' SOL in / tokens out fixed)"""
    tr = r["trades"]
    if not any(t["user"].startswith(OURS6) for t in tr): return r
    V, Tk = pre(tr[0]); new = []
    for t in tr:
        if t["user"].startswith(OURS6): continue
        t = dict(t)
        if t["buy"]: d = Tk * t["sol"] / (V + t["sol"]); V += t["sol"]; Tk -= d; t["tok"] = d
        else: so = V * t["tok"] / (Tk + t["tok"]); V -= so; Tk += t["tok"]; t["sol"] = so
        t["vsol"], t["vtok"] = V, Tk; new.append(t)
    r = dict(r); r["trades"] = new; r["cleaned"] = True
    return r


def run(r, outs, T, tips, loose=True):
    """sim_land.py run() with per-launch tips; loose=True also matches a feed anchor by wallet alone (the feed's SOL for
    cap-family buys is an estimate that ignores the bundle, so the +-2% size match drops real anchors)"""
    S, tr = r["S"], r["trades"]
    if not tr: return None
    fee = ((tr[0].get("fbps") or 0) + (tr[0].get("cbps") or 0)) / 1e4 or 0.0125
    ge = r["glued_end"]
    gl = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] < ge]
    pbV, pbT = (gl[-1]["vsol"], gl[-1]["vtok"]) if gl else pre(tr[0])
    key = lambda t: (t["slot"], t["idx"] if t["idx"] is not None else 10 ** 9)
    E = (S, ge - 1); n_anchor = 0; n_miss = 0
    cm = r.get("create_ms")
    late = cm is not None and cm + T > r.get("slot_ms", 217.4)
    if late:
        E = max(E, (S, max([t["idx"] for t in tr if t["slot"] == S and t["idx"] is not None] or [ge - 1])))
    for ms, sol, flag, w6 in outs:
        if ms > T or flag != "1" or w6.startswith(OURS6): continue
        mine = [t for t in tr if t["slot"] in (S, S + 1) and t["idx"] is not None and t["buy"] and (t["user"].startswith(w6) or t.get("payer", "").startswith(w6))]
        cand = [t for t in mine if abs(t["sol"] / 1e9 - sol) <= max(0.02, 0.02 * sol)]
        if not cand and loose: cand = mine
        if cand: E = max(E, min(key(c) for c in cand)); n_anchor += 1
        else: n_miss += 1
    before = [t for t in tr if key(t) <= E]
    seq = [t for t in tr if key(t) > E]
    V, Tk = (before[-1]["vsol"], before[-1]["vtok"]) if before else (pbV, pbT)
    x = SIZE * 1e9 / (1 + fee)
    q_pb = pbT * x / (pbV + x)
    q = Tk * x / (V + x)
    at_px = (V / Tk) / (pbV / pbT)
    n_ahead = sum(1 for t in before if t["buy"] and not (t["slot"] == S and t["idx"] < ge))
    if q < q_pb * (1 - CAP / 1e4):
        return dict(refused=True, at_px=at_px, pnl={1: -PRIO, 2: -PRIO}, late=late, n_anchor=n_anchor, n_miss=n_miss, n_ahead=n_ahead)
    V += x; Tk -= q
    after_buy = (V, Tk); endst = {}
    for t in seq:
        if t["buy"]: d = Tk * t["sol"] / (V + t["sol"]); V += t["sol"]; Tk -= d
        else: so = V * t["tok"] / (Tk + t["tok"]); V -= so; Tk += t["tok"]
        endst[t["slot"]] = (V, Tk)
    res = {}
    for k in (1, 2):
        st = None
        for s in range(S + k, S - 1, -1):
            if s in endst: st = endst[s]; break
        Vk, Tkk = st if st else after_buy
        res[k] = Vk * q / (Tkk + q) * (1 - fee) / 1e9 - SIZE - PRIO - tips - SELL_FEE
    return dict(refused=False, at_px=at_px, pnl=res, late=late, n_anchor=n_anchor, n_miss=n_miss, n_ahead=n_ahead)


def tipclass(r, rec):
    dst = rec.get("largest_to") or ""
    if not dst and (r.get("tip_to") or "-") != "-": dst = r["tip_to"]
    if not dst or not rec.get("largest_lam"): return "none"
    if dst.startswith("moon"): return "lunar"
    if dst.startswith("noz"): return "nozomi"          # Temporal Nozomi's vanity tip accounts (noz...), not all in the tip map
    lab = TM.get(dst)
    if lab in ("jito", "nozomi"): return lab
    if lab: return "other tip svc"
    return "fee/other addr"                             # mostly launch-platform fees: uxento uxto..., j7tracker dev..., KfHbT...


def host_of(r):
    h = r.get("host") or "-"
    if "j7tracker" in h: return "j7tracker"
    if h == "ipfs.io": return "ipfs.io"
    if "uxento" in h: return "uxento"
    if "pinata" in h: return "pinata"
    return "other"


rows = []; miss = collections.Counter()
for r in D["launches"]:
    p = os.path.join(REC, f"{r['mint']}.json")
    if not os.path.exists(p): miss["no record"] += 1; continue
    rec = json.load(open(p))
    if rec["S"] != r["S"]: miss["slot mismatch"] += 1; continue
    obs = r.get("obs")
    if not obs: miss["no RACE obs"] += 1; continue
    rec["create_ms"] = r.get("create_ms"); rec["slot_ms"] = r.get("slot_ms", 217.0)
    rec = clean(rec)
    client, csrc = client_of(r); c = cls(client)
    o = run(rec, obs["outs"], T_BY[c], TIP_BY[c]); op = run(rec, obs["outs"], T_BY[c] + PESS, TIP_BY[c])
    os_ = run(rec, obs["outs"], T_BY[c], TIP_BY[c], loose=False)
    if not o: miss["no trades"] += 1; continue
    dev = (r.get("dev") or 0) / 1e9
    g = next(k for k, ls in GROUPS.items() if r["log"] in ls)
    rows.append(dict(log=r["log"], grp=g, S=r["S"], mint=r["mint"], fired=bool(r.get("fire")), client=client, csrc=csrc, cls=c, T=T_BY[c],
                     create_ms=r.get("create_ms"), dev=dev, gsol=rec["gsol"], glued=rec["glued"], legs=rec.get("glued_legs", rec["glued"]),
                     bwal=rec.get("bundle_wallets"), eng_bsol=(r.get("decide") or {}).get("bundle_sol"), eng_pass=(r.get("decide") or {}).get("passed"),
                     static_ok=r.get("static_ok") == "true", tipc=tipclass(r, rec), tip_lam=rec.get("largest_lam") or 0, host=host_of(r), host_raw=r.get("host"),
                     cu_price=r.get("cu_price"), luts=r.get("luts"), v1=r.get("v1"), t22=r.get("t22"), kind=r.get("kind"), nkeys=r.get("nkeys"), nix=r.get("nix"),
                     name_len=r.get("name_len"), n_outs_100=obs.get("n100"), cleaned=rec.get("cleaned", False),
                     refused=o["refused"], at_px=o["at_px"], late=o["late"], n_ahead=o["n_ahead"], anchors=o["n_anchor"], anchor_miss=o["n_miss"],
                     p2=o["pnl"][2], p1=o["pnl"][1], pp2=op["pnl"][2], pp1=op["pnl"][1], pref=op["refused"], s2=os_["pnl"][2]))
json.dump(dict(rows=rows, hours=HOURS, groups=GROUPS, missing=dict(miss)), open(OUTP + "_rows.json", "w"))
print(f"rows {len(rows)}; missing {dict(miss)}; hours {({g: round(h, 2) for g, h in HOURS.items()})}")
print("client source:", collections.Counter(r["csrc"] for r in rows).most_common(), " class:", collections.Counter(r["cls"] for r in rows).most_common())
