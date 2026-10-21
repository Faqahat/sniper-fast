# READ-ONLY (host): one joined table for FILTERS2.md (non-bundle create-time signals). Rows = the 932 priced watched
# launches of FILTERS.md (groups A/B/C, filters_rows.json) + today's paper launches after C (group D, paper_rows.py),
# joined with (a) the engine's RACE seen fields (creator, name, sym, uri, cu_limit, nsig, dev_sized/dev_cap, tip...),
# (b) block time of the create slot (rec files), (c) the create-slot leader identity, (d) the activity regime from the
# engine's DETECT lines (all creates seen / base-filter passes in the 10 min before the create), (e) creator history
# from creator_hist.py (on-chain, only signatures BEFORE the create slot are used), (f) in-log creator history (the same
# creator's earlier WATCHED launches in any log, with their modelled PnL; only launches strictly before this one).
import os, re, json, glob, bisect, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.environ.get("F2_WORK", "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad")
FILT = os.path.join(SP, "filt"); F2 = os.path.join(SP, "f2"); PAP = os.path.join(F2, "paper")
REC_DIRS = ["/home/moiz/sniper-data/research/rec", os.path.join(PAP, "rec")]
LOGS = {"cov": "dry_cov.log", "alt": "dry_alt.log", "cad": "dry_cad.log", "edge1": "live_edge1.log", "latest": "dry_latest.log",
        "edge2": "live_edge2.log", "dry1h": "dry_1h.log", "run1": "prod_p1.log", "edge3": "live_edge3.log", "edge5": "live_edge5.log",
        "night": "dry_run1.prev-20261021.log", "morning": "dry_run1.log"}
WIN = 10 * 60 * 1000 / 216.5                                    # 10 min in slots


def regime_index():
    """per log: sorted slots of every create the engine saw first (DETECT first=1) and of base-filter passes"""
    idx = {}
    paths = {l: os.path.join(FILT, "logs", f) for l, f in LOGS.items()}
    paths["today"] = os.path.join(PAP, "paper.log")
    for l, p in paths.items():
        allc, base = [], []
        for line in open(p, errors="replace"):
            if "DETECT" not in line or " first=1 " not in line: continue
            m = re.search(r" slot=(\d+)", line)
            if not m: continue
            s = int(m.group(1)); allc.append(s)
            if "verdict=pass" in line: base.append(s)
        allc.sort(); base.sort()
        idx[l] = (allc, base, allc[0] if allc else None)
    return idx


OURS6 = ("FRZh63", "2g7rYv")


def market(rec):
    """the launch's own market response in S..S+2 (an OUTCOME: used only as the creator's reputation for LATER launches)
    mkt2 = price at the end of S+2 / price right after the creator's glued bundle; out2 = outside buy SOL in S..S+2
    (not the creator / bundle wallets / us); nb2 = distinct outside buyers; dump2 = creator+bundle sells in S..S+2 (SOL)"""
    S, tr, ge = rec["S"], rec["trades"], rec["glued_end"]
    if not tr: return {}
    mem = set(rec.get("bundle_members") or []) | {rec.get("creator")}
    gl = [t for t in tr if t["slot"] == S and t["idx"] is not None and t["idx"] < ge]
    t0 = gl[-1] if gl else tr[0]
    pb = t0["vsol"] / t0["vtok"]
    last = [t for t in tr if t["slot"] <= S + 2]
    p2 = last[-1]["vsol"] / last[-1]["vtok"] if last else pb
    out = [t for t in tr if t["slot"] <= S + 2 and t["buy"] and not (t["slot"] == S and t["idx"] is not None and t["idx"] < ge)
           and t["user"] not in mem and not t["user"].startswith(OURS6)]
    dump = [t for t in tr if t["slot"] <= S + 2 and not t["buy"] and t["user"] in mem]
    return dict(mkt2=p2 / pb, out2=sum(t["sol"] for t in out) / 1e9, nb2=len({t["user"] for t in out}), dump2=sum(t["sol"] for t in dump) / 1e9)


def load(with_creators=True):
    R = json.load(open(os.path.join(HERE, "filters_rows.json")))
    rows, hours = R["rows"], dict(R["hours"])
    P = json.load(open(os.path.join(PAP, "paper_rows.json")))
    rows += P["rows"]; hours.update(P["hours"])
    L = {(x["S"], x["mint"]): x for x in json.load(open(os.path.join(FILT, "launches2.json")))["launches"]}
    L.update({(x["S"], x["mint"]): x for x in json.load(open(os.path.join(PAP, "launches_ready.json")))["launches"]})
    LD = json.load(open(os.path.join(FILT, "leaders2.json"))); LD.update(json.load(open(os.path.join(PAP, "leaders.json"))))
    reg = regime_index()
    for r in rows:
        x = L[(r["S"], r["mint"])]
        for f in ("creator", "name", "sym", "uri", "cu_limit", "nsig", "dev_sized", "dev_cap", "tip", "tip_to"):
            r[f] = x.get(f)
        r["host_raw"] = x.get("host")
        r["leader"] = (LD.get(str(r["S"])) or [None])[0]
        rec = None
        for d in REC_DIRS:
            p = os.path.join(d, r["mint"] + ".json")
            if os.path.exists(p):
                rr = json.load(open(p))
                if rr["S"] == r["S"]: rec = rr; break
        r["bt"] = rec.get("block_time") if rec else None
        r.update(market(rec) if rec else {})
        allc, base, first = reg[r["log"] if r["log"] in reg else "today"]
        lo = r["S"] - WIN
        cov = min(WIN, r["S"] - first) if first else 0           # slots of the window the log actually covers
        if cov >= WIN / 5:
            na = bisect.bisect_left(allc, r["S"]) - bisect.bisect_left(allc, lo)
            nb = bisect.bisect_left(base, r["S"]) - bisect.bisect_left(base, lo)
            mins = cov * 216.5 / 60000
            r["act_all"] = na / mins; r["act_base"] = nb / mins
        else:
            r["act_all"] = r["act_base"] = None
    # in-log creator history: earlier WATCHED launches by the same creator (any log), with their modelled S+2 PnL
    by_c = collections.defaultdict(list); bym = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: r["S"]):
        h = by_c[r["creator"]]
        r["c_prev_n"] = len(h); r["c_prev_p2"] = sum(p for _, p in h); r["c_prev_win"] = sum(1 for _, p in h if p > 0)
        r["c_prev_gap"] = (r["S"] - h[-1][0]) if h else None
        r["c_last_p2"] = h[-1][1] if h else None
        hm = bym[r["creator"]]
        r["c_prev_mkt_last"] = hm[-1][0] if hm else None; r["c_prev_mkt_max"] = max(m for m, _ in hm) if hm else None
        r["c_prev_out_max"] = max(o for _, o in hm) if hm else None
        h.append((r["S"], r["p2"])); hm.append((r.get("mkt2", 1.0), r.get("out2", 0.0)))
    CJ = os.environ.get("F2_CREATORS", os.path.join(F2, "creators.json"))
    if with_creators and os.path.exists(CJ):
        C = json.load(open(CJ))
        for r in rows:
            c = C.get(r["creator"])
            r["rpc"] = c is not None and c.get("ok")
            if not r["rpc"]: continue
            prior = [s for s in c["sigs"] if s[0] < r["S"]]
            r["w_prior"] = len(prior); r["w_complete"] = bool(c["complete"])
            r["w_age_s"] = (r["bt"] - prior[-1][1]) if (c["complete"] and prior and r["bt"] and prior[-1][1]) else None
            r["w_last_s"] = (r["bt"] - prior[0][1]) if (prior and r["bt"] and prior[0][1]) else None
            f = c.get("first") or {}
            r["funder"] = f.get("funder") or f.get("payer")
            r["funded_sol"] = (f.get("funded_lam") or 0) / 1e9 if f else None
            lr = c["launch"].get(str(r["S"])) or {}
            r["v_n"] = lr.get("vn"); r["v_complete"] = lr.get("vcomplete")
            r["v_first_s"] = (r["bt"] - lr["vfirst_bt"]) if (lr.get("vfirst_bt") and r["bt"]) else None
            r["v_last_s"] = (r["bt"] - lr["vlast_bt"]) if (lr.get("vlast_bt") and r["bt"]) else None
            vb = lr.get("vbt") or []
            r["v_1h"] = sum(1 for t in vb if t and r["bt"] and r["bt"] - t <= 3600) if r["bt"] else None
        # funder reputation: earlier watched launches (any creator) whose creator wallet had the same first funder
        by_f = collections.defaultdict(list)
        for r in sorted(rows, key=lambda r: r["S"]):
            f = r.get("funder")
            h = by_f[f] if f else []
            r["f_prev_n"] = len(h); r["f_prev_p2"] = sum(p for _, p in h)
            r["f_prev_other"] = sum(1 for c, _ in h if c != r["creator"])
            if f: h.append((r["creator"], r["p2"]))
    return rows, hours
