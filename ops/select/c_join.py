#!/usr/bin/env python3
# PHASE C (read-only, offline): join phase-B launch rows with enrich.jsonl and add LEAK-FREE history features.
# History uses only earlier launches whose 10-minute outcome window had already ended at this launch's create time.
# Every feature carries an availability tier in FEATURE_TIERS (what a sniper could know before buying):
#   T0 create tx | T0b create slot (bundle) | T1 RPC lookups on the creator (fast, cacheable) | T2 metadata fetch (~0.5 s)
#   | F1/F5/F15 early flow after 1/5/15 s (delayed entries only)
# usage: python3 c_join.py <phaseB dir> <run dir> <out table.jsonl.gz>
import sys, os, json, gzip, glob, re, collections, statistics, urllib.parse
B, RUN, OUT = sys.argv[1:4]
rows = []
for bdir in B.split(","):
    for f in sorted(glob.glob(os.path.join(bdir, "*.jsonl.gz"))):
        for l in gzip.open(f, "rt"): rows.append(json.loads(l))
E = {}
for run in RUN.split(","):
    for l in open(os.path.join(run, "enrich.jsonl")):
        try: r = json.loads(l)
        except Exception: continue
        E[r["mint"]] = r
# launches with NO trade at all after the create (no dev buy, no buyers): a buy there only pays the round trip
have = {r["mint"] for r in rows}; RT = (1 - 0.0125) / (1 + 0.0125) - 1; added = 0
for l in (x for run in RUN.split(",") for x in open(os.path.join(run, "launches.jsonl"))):
    try: c = json.loads(l)
    except Exception: continue
    if c["mint"] in have or c.get("err"): continue
    have.add(c["mint"]); added += 1
    r = dict(mint=c["mint"], S=c["slot"], bt=c.get("bt"), creator=c.get("creator") or c.get("user"), payer=c.get("payer"), name=c.get("name"), symbol=c.get("symbol"),
             uri=c.get("uri"), create_idx=c.get("idx"), create_fee=c.get("fee"), create_ixn=(c.get("ixn") or [])[:3], mayhem=int("InitializeMayhemState" in (c.get("ixn") or [])),
             n_trades=0, quote_sol=1, max_vsol=30.0, dev_buy=0.0, glued_n=0, glued_wallets=0, glued_sol=0.0, glued_same_payer=0, glued_payer_is_creator=0,
             slot_buys=0, slot_buy_sol=0.0, slot_sells=0, slot_buyers=0, peak_px=1.0, peak_10m=1.0, peak_slot=0, vol_sol=0.0, holders_proxy=0, migrated=0, no_trades=1,
             early_buyers=[], bundle_wallets=[], graduated=0)
    for ck in ("slot", "1s", "5s", "15s"):
        for k in ("nb", "ns", "bsol", "ssol", "net", "ub", "maxb", "dev_sold", "bundle_sold", "cup_med", "tips", "via_router"): r[f"f{ck}_{k}"] = 0
        r[f"f{ck}_px"] = 1.0
    for h in ("2s", "5s", "15s", "30s", "60s", "2m", "5m", "10m"): r[f"px_{h}"] = 1.0
    for en, dl in (("E_bundle", -1), ("E_k1", -1), ("E_k2", -1), ("E_k3", -1), ("E_slot", 0), ("E_s1", 1), ("E_1s", 5), ("E_5s", 25), ("E_15s", 75)):
        r[f"{en}_entry_px"] = 1.0
        for h, v in (("2s", 10), ("3s", 15), ("5s", 25), ("10s", 50), ("15s", 75), ("30s", 150), ("60s", 300), ("2m", 600), ("5m", 1500), ("10m", 2860)):
            if dl < v: r[f"{en}_h{h}"] = RT
        for x in ("trail30_20_s30_10m", "trail50_25_s30_10m", "trail100_40_s40_10m", "trail20_10_s15_2m", "sk1_10s", "sk2_10s", "sk3_10s", "sk5_30s", "sv1_10s", "sv2_10s", "sv5_30s", "fsell_30s"): r[f"{en}_{x}"] = RT; r[f"{en}_{x}_eos"] = RT
        r[f"L{en}_best"] = RT; r[f"L{en}_best_d"] = 0; r[f"L{en}_dd"] = RT
        for x, cap in (("tp25_sl25_60s", 300), ("tp50_sl30_5m", 1500), ("tp100_sl40_10m", 2860), ("tp20_sl10_30s", 150), ("tp30_none_2m", 600), ("tp200_sl50_10m", 2860)):
            if dl < cap: r[f"{en}_{x}"] = RT
    rows.append(r)
print("added never-traded launches:", added)
rows = [r for r in rows if not (r.get("n_trades", 0) == 0 and r.get("no_trades") is None)]
rows.sort(key=lambda r: (r["bt"] or 0, r["S"]))
def host(u):
    try: return urllib.parse.urlparse(u if "://" in u else "https://" + u).hostname or ""
    except Exception: return ""
WIN = lambda r: (r.get("peak_10m") if r.get("peak_10m") is not None else (r.get("peak_px") if r.get("no_trades") else 0) or 0) >= 2.0
hist_creator = collections.defaultdict(list); hist_funder = collections.defaultdict(list); hist_wallet = collections.defaultdict(lambda: [0, 0])
hist_name = collections.defaultdict(list); hist_bundle = collections.defaultdict(lambda: [0, 0]); pending = collections.deque()
out = []
recent = collections.deque()                   # (bt, name, symbol, creator, funder) of earlier creates, last 60 min
resolved_recent = collections.deque()          # (resolve time, win) last 60 min
cr_seen = collections.defaultdict(list); fd_creators = collections.defaultdict(set)
def norm(x): return re.sub(r"[^a-z0-9]", "", (x or "").lower())
for r in rows:
    t = r["bt"] or 0
    while recent and recent[0][0] < t - 3600: recent.popleft()
    while resolved_recent and resolved_recent[0][0] < t - 3600: resolved_recent.popleft()
    while pending and pending[0][0] <= t:                      # resolve launches whose 10-min window has ended
        tp_, p = pending.popleft(); w = WIN(p); resolved_recent.append((tp_, w))
        hist_creator[p["creator"]].append(w); hist_name[(p.get("name") or "").strip().lower()].append(w)
        if p.get("_funder"): hist_funder[p["_funder"]].append(w)
        for b in p.get("bundle_wallets") or []: hist_bundle[b][0] += 1; hist_bundle[b][1] += w
        for eb in (p.get("early_buyers") or [])[:20]: hist_wallet[eb[0]][0] += 1; hist_wallet[eb[0]][1] += w
    e = E.get(r["mint"], {}); m = (e.get("meta") or {}); j = m.get("json") if isinstance(m.get("json"), dict) else {}
    x = dict(r)
    # T0: names
    nm = r.get("name") or ""; sy = r.get("symbol") or ""
    x.update(name_len=len(nm), sym_len=len(sy), name_upper=int(nm.isupper()), name_digits=int(bool(re.search(r"\d", nm))), name_nonascii=int(any(ord(c) > 127 for c in nm + sy)),
             sym_eq_name=int(sy.lower() == nm.lower()), uri_host=host(r.get("uri") or ""), payer_is_creator=int(r.get("payer") == r.get("creator")),
             create_variant=(r.get("create_ixn") or ["?"])[0])
    # T1: creator wallet
    ps = e.get("creator_prior_sigs") or []
    x["cr_prior_n"] = e.get("creator_prior_n"); x["cr_prior_fail"] = sum(1 for s in ps if s[3])
    x["cr_age_s"] = (t - ps[-1][2]) if ps and ps[-1][2] else None
    x["cr_last_tx_s"] = (t - ps[0][2]) if ps and ps[0][2] else None
    fd = e.get("funder") or {}; x["funder"] = fd.get("from_"); x["fund_amt"] = (fd.get("amount") or 0) / 1e9 if fd else None
    x["fund_age_s"] = None
    rc = e.get("creator_recent_creates") or []; x["cr_recent_creates"] = len(rc)
    x["cr_same_name_before"] = int(any((c.get("name") or "").lower() == nm.lower() for c in rc))
    # T2: metadata
    x["meta_ok"] = int(bool(j)); desc = j.get("description") or ""
    tw = j.get("twitter") or ""; tg = j.get("telegram") or ""; ws = j.get("website") or ""
    x.update(desc_len=len(desc) if isinstance(desc, str) else 0, has_tw=int(bool(tw)), has_tg=int(bool(tg)), has_web=int(bool(ws)),
             tw_status=int("/status/" in tw) if isinstance(tw, str) else 0, tw_community=int("/communities/" in tw or "/i/" in tw) if isinstance(tw, str) else 0,
             web_host=host(ws) if isinstance(ws, str) and ws else "", img_host=host(j.get("image") or "") if isinstance(j.get("image"), str) else "",
             created_on=str(j.get("createdOn") or "")[:40], show_name=j.get("showName"), meta_keys=len(j))
    x["web_same_as_tw"] = int(bool(ws) and bool(tw) and ws == tw)
    # history (leak-free)
    hc = hist_creator.get(r["creator"], []); x.update(h_cr_n=len(hc), h_cr_wins=sum(hc), h_cr_last_win=int(hc[-1]) if hc else -1)
    hf = hist_funder.get(x["funder"], []) if x["funder"] else []; x.update(h_fd_n=len(hf), h_fd_wins=sum(hf))
    hn = hist_name.get(nm.strip().lower(), []); x.update(h_name_n=len(hn), h_name_wins=sum(hn))
    bw = [hist_bundle[b] for b in r.get("bundle_wallets") or [] if b in hist_bundle]
    x.update(h_bund_seen=len(bw), h_bund_launches=sum(v[0] for v in bw), h_bund_wins=sum(v[1] for v in bw))
    # early-buyer identity at 1 s / 5 s (delayed entries): how many early buyers have a winning record so far
    for lab, dl in (("1s", 5), ("5s", 25)):
        eb = [b for b in (r.get("early_buyers") or []) if b[1] <= dl]
        rec = [hist_wallet[b[0]] for b in eb if b[0] in hist_wallet]
        x[f"eb{lab}_n"] = len(eb); x[f"eb{lab}_known"] = len(rec)
        x[f"eb{lab}_known_wins"] = sum(v[1] for v in rec); x[f"eb{lab}_good"] = sum(1 for v in rec if v[0] >= 3 and v[1] / v[0] >= 0.3)
        x[f"eb{lab}_bad"] = sum(1 for v in rec if v[0] >= 3 and v[1] == 0)
    # early-buyer fee levels at 1 s
    eb1 = [b for b in (r.get("early_buyers") or []) if b[1] <= 5]
    x["eb1s_cup_max"] = max((b[3] or 0 for b in eb1), default=0); x["eb1s_tips_sum"] = sum(b[4] for b in eb1); x["eb1s_router"] = sum(1 for b in eb1 if b[5])
    # ---- round-2 context ----
    nn, ns_ = norm(nm), norm(sy); fdr = x.get("funder")
    x["hour_utc"] = int((t % 86400) // 3600)
    x["heat_launches_10m"] = sum(1 for q in recent if q[0] >= t - 600)
    rr = [w for tq, w in resolved_recent]; x["heat_win_rate_60m"] = (sum(rr) / len(rr)) if len(rr) >= 20 else None
    x["wave_name_10m"] = sum(1 for q in recent if q[0] >= t - 600 and q[1] == nn and nn)
    x["wave_name_60m"] = sum(1 for q in recent if q[1] == nn and nn); x["wave_sym_60m"] = sum(1 for q in recent if q[2] == ns_ and ns_)
    cs = cr_seen[r["creator"]]; x["cr_creates_window"] = len(cs); x["cr_min_since_prev_create"] = (t - cs[-1]) / 60 if cs else None
    x["fd_creators_so_far"] = len(fd_creators[fdr]) if fdr else None
    x["fd_is_creator"] = int(bool(fdr) and fdr == r["creator"])
    db = r.get("dev_buy") or 0; gs = r.get("glued_sol") or 0
    x["dev_share"] = db / (db + gs) if (db + gs) > 0 else None; x["bundle_avg"] = gs / r["glued_wallets"] if r.get("glued_wallets") else 0
    x["fp"] = f"{r.get('create_cup')}|{r.get('create_cul')}|{int((r.get('create_tips') or 0) > 0)}"
    recent.append((t, nn, ns_, r["creator"], fdr)); cs.append(t)
    if fdr: fd_creators[fdr].add(r["creator"])
    x.pop("early_buyers", None); x.pop("bundle_wallets", None)
    out.append(x)
    r["_funder"] = x["funder"]; pending.append((t + 600, r))
with gzip.open(OUT, "wt") as f:
    for x in out: f.write(json.dumps(x, separators=(",", ":")) + "\n")
print("rows", len(out), "with enrich", sum(1 for r in rows if r["mint"] in E))
