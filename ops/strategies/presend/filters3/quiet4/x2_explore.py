#!/usr/bin/env python3
"""QUIET4 step 2 [MEASURED]: signing-time candidate features on every baseline-kept live position (DEV shown first; VAL/HOLD only
for the frozen picks later). Features are built ONLINE in time order from what the engine could know before the trigger:
  wl_*   whale ledger: OUR earlier positions whose trigger whale (T2) / dumper (re-arm) was this wallet, known (closed) before t0
  ws_*   whale shadow: the shadow's earlier T2 triggers by this wallet (any run, t < t0; row c paper result known ~5 s after)
  bait   whale's T2 trigger count in the last 24 h (shadow arms) and trig SOL == 2.962962962 (template buy)
  hl_*   holder ledger: wallets that SOLD into our hold on earlier positions, charged that position's P&L; checked against the
         arm-time holders (re-arm: arm holders; T2: fill-time holders whose hold age >= fill slot - trigger slot, i.e. held at the
         trigger [proxy: engine would need its holder map at the arm]) + creator + whale
  rg_*   regime: our last N positions' follow rate, the shadow's last N row-c results (market-wide)
Writes feats.pkl (one dict per kept position)."""
import sys, pickle, collections, bisect
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/quiet4")
import q4lib as L

P = L.baseline(L.all_positions())
H = L.spans(P)
SH = []
for r in L.RUNS:
    for s in L.load(r)["sh"]: SH.append(s)
SH.sort(key=lambda s: s["t"])
sh_by_w = collections.defaultdict(list)
for s in SH: sh_by_w[s["whale"]].append(s)
sh_t = [s["t"] for s in SH]
KNOW = 6e9                      # a shadow trigger's row-c result is known ~6 s after the trigger (window 10 slots + 2-slot exit)

# events: positions become known at p["known"]
known_q = sorted(P, key=lambda p: p["known"])
wl = collections.defaultdict(list); hl = collections.defaultdict(list); recent = collections.deque(maxlen=200)
F = []; k = 0
for p in P:
    t0 = p["t0"]
    while k < len(known_q) and known_q[k]["known"] < t0:
        q = known_q[k]; k += 1
        if q["whale"]: wl[q["whale"]].append(q)
        for u, sol in q["hold_sellers"].items():
            if sol >= 0.3 and u not in L.OURS: hl[u].append(q)
        recent.append(q)
    f = {"id": p["id"]}
    h = wl.get(p["whale"], [])
    f["wl_n"] = len(h); f["wl_sum"] = sum(q["pnl"] for q in h); f["wl_unf"] = sum(not q["followed"] for q in h)
    h3 = h[-3:]; f["wl_last3_unf"] = len(h3) > 0 and all(not q["followed"] for q in h3)
    h24 = [q for q in h if q["known"] >= t0 - 24 * 3.6e12]; f["wl24_n"] = len(h24); f["wl24_sum"] = sum(q["pnl"] for q in h24)
    f["wl24_unf"] = sum(not q["followed"] for q in h24)
    # whale shadow
    s = [x for x in sh_by_w.get(p["whale"], []) if x["t"] < t0 - KNOW]
    s24 = [x for x in s if x["t"] >= t0 - 24 * 3.6e12]
    f["ws24_n"] = len(s24); c = [x["c"] for x in s24 if x["c"] is not None]
    f["ws24_fills"] = len(c); f["ws24_mean"] = sum(c) / len(c) if c else None; f["ws24_sum"] = sum(c)
    s1 = [x for x in s if x["t"] >= t0 - 3.6e12]; f["ws1_n"] = len(s1)
    f["ws24_mean_k"] = len(c)
    for hh in (3, 6):
        cc = [x["c"] for x in s if x["t"] >= t0 - hh * 3.6e12 and x["c"] is not None]
        f[f"ws{hh}_mean"] = sum(cc) / len(cc) if cc else None; f[f"ws{hh}_mean_k"] = len(cc)
    f["ws24_creators"] = None
    f["tmpl"] = p["trig_sol"] == 2962962962
    # holders at arm
    hold = {}
    if p["kind"] != "T2":
        for x in p["arm_holders"] or []: hold[x["w"]] = x["pct"]
    elif p["fill_holders"] is not None and p["fill_slot"] and p["trig_slot"]:
        lag = p["fill_slot"] - p["trig_slot"]
        for x in p["fill_holders"]:
            if (x.get("age") or 0) >= lag and x["w"] != p["whale"]: hold[x["w"]] = x["pct"]
    if p["creator"] and p["cr_pct"]: hold[p["creator"]] = max(hold.get(p["creator"], 0), p["cr_pct"])
    f["hold_known"] = p["fill_holders"] is not None or p["kind"] != "T2"
    best = None
    for u, pct in hold.items():
        hh = hl.get(u, [])
        if not hh: continue
        e = (sum(q["pnl"] for q in hh), len(hh), pct, u)
        if best is None or e[0] < best[0]: best = e
    f["hl_sum"], f["hl_n"], f["hl_pct"], f["hl_w"] = best if best else (0.0, 0, 0.0, None)
    # also: the whale itself as a past hold-seller
    hw = hl.get(p["whale"], []); f["hlw_n"] = len(hw); f["hlw_sum"] = sum(q["pnl"] for q in hw)
    # regime
    r = list(recent)
    for n in (20, 50):
        rr = r[-n:]; f[f"rg_fol{n}"] = sum(q["followed"] for q in rr) / len(rr) if rr else None
        f[f"rg_pnl{n}"] = sum(q["pnl"] for q in rr) / len(rr) if rr else None
    j = bisect.bisect_left(sh_t, t0 - KNOW)
    cc = [x["c"] for x in SH[max(0, j - 400):j] if x["c"] is not None][-60:]
    f["rg_sh60"] = sum(cc) / len(cc) if cc else None
    j0 = bisect.bisect_left(sh_t, t0 - 3 * 3.6e12)
    c3 = [x["c"] for x in SH[j0:j] if x["c"] is not None]
    f["rg_sh3h"] = sum(c3) / len(c3) if len(c3) >= 20 else None
    c200 = [x["c"] for x in SH[max(0, j - 1500):j] if x["c"] is not None][-200:]
    f["rg_sh200"] = sum(c200) / len(c200) if len(c200) >= 50 else None
    F.append(f)
pickle.dump({"P": P, "F": F, "H": dict(H)}, open(f"{L.D}/feats.pkl", "wb"))
print("kept positions", len(P), "spans h", {k: round(v, 1) for k, v in H.items()})
