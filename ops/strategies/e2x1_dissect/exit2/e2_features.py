#!/usr/bin/env python3
"""exit2 step 2: trips + candidate events + causal features for the EXIT decision.
Trip = his position on a mint from a buy while flat until the sell that empties it (adds while holding join the trip).
Candidate = every OUTSIDE trade (not his) on the mint while the trip is open (from the entry buy up to his first sell).
Label y1 = he sells in this slot or the next (0 <= sell_slot - slot <= 1); y3 = within 3 slots.
All features use the event row and rows before it only (causal). Out: sniper-data/e2x1_dissect/exit2/ev.npz, trips.pkl"""
import json, pickle, time, collections
import numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"
Z = np.load(f"{OUT}/tape_his.npz"); wid = int(Z["wid"]); sid = int(Z["sid"])
slot = Z["slot"].astype(np.int64); idx = Z["idx"].astype(np.int64); mint = Z["mint"]; user = Z["user"]; buy = Z["buy"].astype(bool)
sol = Z["sol"].astype(np.float64) / 1e9; tok = Z["tok"].astype(np.float64); vsol = Z["vsol"].astype(np.float64) / 1e9; vtok = Z["vtok"].astype(np.float64)
rsol = Z["rsol"].astype(np.float64) / 1e9; bt = Z["bt"].astype(np.int64); fee = (Z["fee_bps"].astype(np.float64) + Z["cfee_bps"].astype(np.float64)) / 1e4
N = len(slot)
# wallet activity over the whole tape
nU = int(max(Z["act_user"].max(), user.max())) + 1
act_mints = np.zeros(nU, np.int32); act_mints[Z["act_mint_user"]] = Z["act_mints"]
act_trades = np.zeros(nU, np.int32); act_trades[Z["act_user"]] = Z["act_trades"]
users = json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/users.json")); uid = {u: i for i, u in enumerate(users)}
mints_l = json.load(open("/home/moiz/sniper-data/haqqml/fresh/tape/mints.json"))
COPIERS = """3iawEZGfWF3H7q6HLxHjSfeZHjCvPr8U9xjXpMgtobDN Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL FiYZPbS4wi7CSEBerzvyHEAzQkT7qj1apB2mZob3R3zj
4HgMCR7abFKHDPgYfMrtjvKniPXj4zHwuSNNRVx7QEzQ AZ45pUnDKayDSsqxASohrqTaAWSLRwwfTzTpdNoqAQSx 8VqKttXDgU2t3hxtP1sgcHBNc6jv1iDnbDyVzcBxGHsM
7yY786SNiCsRpMSZS8vKAKHNHeh2bumPsjBCsYRBSwN5 5174QiRmFgQKkQYBp7aKZsYdP1tSXJMi2RY4Yh2eysKn GLsnURrAT7WyuDU6mXX1jW9V1N6o1EoEryet6K5noQJj
EfN6eT3G2XzcHF57LoTiuQxxg24z12KfW9t7MZxPXX1D J7EA3XgCk25LBpoFtRijSuPSTF1DPbikpmYC6zevgc97 4mYySb7Z74EK9c6AzSmRRbsd5NjRKeU2yjMF6nfz8ctD
8T4XXALtGjvJytQ2zvFSBaZYexxqd1fzpC1n8ATSbkWc 2QGfyorLu58GgSPvHrHhdX7WjP9TEt9xdBmpNsYaHBfz EYeidaTQb7M9F9WtihkSiM1JyyTqzTPibWuyFNih3sgj
3qZ3RTQs5rYz8Gqxqt8cE5qBLCXX9hVB7wMeEwEhUffQ 7Vno6MU2BBtBsUU9HtXaVMwSDE5UAmEdVfS8uE9uNsjh B7A4wooms5zAvWs48eTN358iVm2mVsLiepFGiJ22ofaf
BenzBfhB2eMW7yZaTkN5uV7vSYMnt2eoqRRANAVjhuLA""".split()
copier = np.zeros(nU, bool)
for w in COPIERS:
    if w in uid: copier[uid[w]] = True
lead = np.zeros(nU, bool)
for w in json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/s11_leaders.json")).get("leaders", []):
    if w in uid: lead[uid[w]] = True
lead[sid] = False
# creates (age, creator)
CR = json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/creates_all.json"))
# block clock
S = np.load("/home/moiz/sniper-data/haqqml/fresh/tape/slots.npy"); s0 = int(S["slot"].min())
bsz = np.zeros(int(S["slot"].max()) - s0 + 2); bsz[S["slot"].astype(np.int64) - s0] = S["maxi"].astype(np.int64) + 1
def cc(s, i):
    k = s - s0; n = bsz[k] if 0 <= k < len(bsz) else 0.0
    if n <= 0: n = 400.0
    return s * 212.0 + i / max(n, i + 1.0) * 212.0

FEATS = ["bot", "trip_no", "entry_sol", "entry_vsol", "entry_age_s", "is_add_trip", "sib_holds", "sib_entered_before",
         "dslots", "dsec", "age_s", "vsol", "progress", "r", "r_pre", "rpeak", "dd", "rtrough", "imp",
         "ev_buy", "ev_sol", "ev_sol_rel", "ev_tok_share", "ev_sib", "ev_creator", "ev_trig", "ev_copier", "ev_lead", "ev_act_mints", "ev_act_trades",
         "ev_follower", "ev_prebuyer", "ev_frac_sold", "ev_rem_share", "ev_rank", "ev_user_trades_mint", "ev_user_bought_5s", "ev_first_outside_sell",
         "nb_1s", "ns_1s", "in_1s", "out_1s", "ub_1s", "nb_2s", "ns_2s", "in_2s", "out_2s", "ub_2s", "nb_5s", "ns_5s", "in_5s", "out_5s", "ub_5s",
         "net_5s", "since_buy", "since_sell", "nb_hold", "ns_hold", "in_hold", "out_hold", "ub_hold", "holders", "dholders", "holders_entry",
         "sib_sold_slot", "sib_sold_2", "copier_sold_2", "big_sell_5s", "big_buy_5s", "n_sells_run", "sells_pct_since_peak", "fee"]
FI = {f: k for k, f in enumerate(FEATS)}

# spans per mint
um, st = np.unique(mint, return_index=True); en = np.append(st[1:], N)
t0 = time.time()
X = []; META = []; Y1 = []; Y3 = []; TRIPS = []
for mi, (m, a, b) in enumerate(zip(um, st, en)):
    his = [k for k in range(a, b) if user[k] == wid]
    if not his: continue
    cr = CR.get(mints_l[m]) or {}
    cr_slot = int(cr.get("slot") or -1); cr_user = uid.get(cr.get("creator"), -1); cr_bt = int(cr.get("bt") or 0)
    # trips
    trips = []; held = 0.0; cur = None; mx = 0.0
    for k in his:
        if buy[k]:
            if cur is None:
                cur = dict(mint=int(m), entry=k, buys=[k], sells=[], tok=0.0, cost=0.0); mx = 0.0
            else:
                cur["buys"].append(k)
            cur["tok"] += tok[k]; cur["cost"] += sol[k] * (1 + fee[k]); held += tok[k]; mx = max(mx, held)
        else:
            if cur is None: continue
            cur["sells"].append(k); held -= tok[k]
            if held <= 0.005 * mx:
                cur["close"] = k; trips.append(cur); cur = None; held = 0.0
    if cur is not None: cur["close"] = None; trips.append(cur)
    # walk the mint tape once; balances / per-user info
    bal = collections.defaultdict(float); first_buy = {}; ntr = collections.defaultdict(int); last_buy_slot = {}
    holders = 0
    recent = collections.deque()  # outside trades: (slot, buy, sol, user)
    tr_i = 0; T = trips[tr_i] if trips else None
    st_open = None
    for k in range(a, b):
        u = int(user[k]); s = int(slot[k]); i = int(idx[k])
        if T is not None and st_open is None and k == T["entry"]:
            # open trip: snapshot
            sellk = T["sells"][0] if T["sells"] else None
            ss = int(slot[sellk]) if sellk is not None else None; si = int(idx[sellk]) if sellk is not None else None
            pre_out = [q for q in range(a, k) if user[q] != wid]
            trig_u = int(user[pre_out[-1]]) if pre_out else -1
            st_open = dict(v0=vsol[k], peak=vsol[k], trough=vsol[k], ss=ss, si=si, trig=trig_u, holders0=holders + (1 if bal[wid] <= 0 else 0),
                           nb=0, ns=0, inn=0.0, out=0.0, ub=set(), last_buy=s, last_sell=-10 ** 9, sib_sold=[], cop_sold=[], run=0,
                           peak_k=k, sells_since_peak=0.0, age_s0=(bt[k] - cr_bt) if cr_bt else -1, cc0=cc(s, i), bt0=int(bt[k]), s0=s,
                           bot=0 if (cr_bt and bt[k] - cr_bt < 30) else (1 if (cr_bt and bt[k] - cr_bt < 120) else 2),
                           trip_no=tr_i, sib_before=(bal[sid] > 0), is_add=len(T["buys"]) > 1, entry_sol=sol[k], first_out_sell=False)
            T["bot"] = st_open["bot"]; T["age_s"] = st_open["age_s0"]; T["v0"] = vsol[k]; T["s"] = s; T["i"] = i; T["bt"] = int(bt[k]); T["cc0"] = st_open["cc0"]
            T["trig"] = trig_u; T["holders0"] = st_open["holders0"]
        o = st_open
        if u != wid and o is not None and (o["ss"] is None or (s, i) < (o["ss"], o["si"])) and (o["ss"] is not None or s - o["s0"] <= 9000):
            # ---- candidate event (before updating state with this trade) ----
            v_pre = vsol[k - 1] if k > a else vsol[k]; v = vsol[k]
            peak = max(o["peak"], v); trough = min(o["trough"], v)
            bal_u = bal[u]
            while recent and recent[0][0] < s - 24: recent.popleft()
            w1 = [r for r in recent if r[0] >= s - 4]; w2 = [r for r in recent if r[0] >= s - 9]; w5 = recent
            def agg(w):
                nb = sum(1 for r in w if r[1]); ns = len(w) - nb
                return nb, ns, sum(r[2] for r in w if r[1]), sum(r[2] for r in w if not r[1]), len({r[3] for r in w if r[1]})
            a1, a2, a5 = agg(w1), agg(w2), agg(w5)
            big_sell = max([r[2] for r in w5 if not r[1]] + [0.0]); big_buy = max([r[2] for r in w5 if r[1]] + [0.0])
            # holder rank of this user (by balance before the trade)
            rank = sum(1 for q, bq in bal.items() if bq > bal_u and q != wid) if bal_u > 0 else 99
            fx = {
                "bot": o["bot"], "trip_no": o["trip_no"], "entry_sol": o["entry_sol"], "entry_vsol": o["v0"], "entry_age_s": o["age_s0"], "is_add_trip": o["is_add"],
                "sib_holds": bal[sid] > 0, "sib_entered_before": o["sib_before"],
                "dslots": s - o["s0"], "dsec": bt[k] - o["bt0"], "age_s": (bt[k] - cr_bt) if cr_bt else -1, "vsol": v, "progress": rsol[k] / 85.0,
                "r": (v / o["v0"]) ** 2, "r_pre": (v_pre / o["v0"]) ** 2, "rpeak": (peak / o["v0"]) ** 2, "dd": (v / peak) ** 2, "rtrough": (trough / o["v0"]) ** 2,
                "imp": (v / v_pre) ** 2 - 1,
                "ev_buy": buy[k], "ev_sol": sol[k], "ev_sol_rel": sol[k] / v_pre, "ev_tok_share": tok[k] / 1e15, "ev_sib": u == sid, "ev_creator": u == cr_user,
                "ev_trig": u == o["trig"], "ev_copier": copier[u], "ev_lead": lead[u], "ev_act_mints": act_mints[u], "ev_act_trades": act_trades[u],
                "ev_follower": first_buy.get(u, 10 ** 12) > o["s0"] or (first_buy.get(u) == o["s0"]), "ev_prebuyer": first_buy.get(u, 10 ** 12) < o["s0"],
                "ev_frac_sold": (tok[k] / bal_u if (not buy[k] and bal_u > 0) else 0.0), "ev_rem_share": (max(bal_u - tok[k], 0) if not buy[k] else bal_u + tok[k]) / 1e15,
                "ev_rank": rank, "ev_user_trades_mint": ntr[u], "ev_user_bought_5s": last_buy_slot.get(u, -10 ** 9) >= s - 24,
                "ev_first_outside_sell": (not buy[k]) and not o["first_out_sell"],
                "nb_1s": a1[0], "ns_1s": a1[1], "in_1s": a1[2], "out_1s": a1[3], "ub_1s": a1[4],
                "nb_2s": a2[0], "ns_2s": a2[1], "in_2s": a2[2], "out_2s": a2[3], "ub_2s": a2[4],
                "nb_5s": a5[0], "ns_5s": a5[1], "in_5s": a5[2], "out_5s": a5[3], "ub_5s": a5[4],
                "net_5s": a5[2] - a5[3], "since_buy": s - o["last_buy"], "since_sell": s - o["last_sell"],
                "nb_hold": o["nb"], "ns_hold": o["ns"], "in_hold": o["inn"], "out_hold": o["out"], "ub_hold": len(o["ub"]),
                "holders": holders, "dholders": holders - o["holders0"], "holders_entry": o["holders0"],
                "sib_sold_slot": any(q == s for q in o["sib_sold"]), "sib_sold_2": any(q >= s - 2 for q in o["sib_sold"]), "copier_sold_2": any(q >= s - 2 for q in o["cop_sold"]),
                "big_sell_5s": big_sell, "big_buy_5s": big_buy, "n_sells_run": o["run"], "sells_pct_since_peak": o["sells_since_peak"] / max(peak, 1e-9), "fee": fee[k],
            }
            # include the event itself in the "sells since peak" / run counters AFTER snapshot (causal: event known when we decide)
            X.append([float(fx[f]) for f in FEATS])
            y1 = int(o["ss"] is not None and 0 <= o["ss"] - s <= 1); y3 = int(o["ss"] is not None and 0 <= o["ss"] - s <= 3)
            Y1.append(y1); Y3.append(y3); META.append((len(TRIPS) + tr_i, int(m), s, i, k, u, int(bt[k])))
        # ---- update state with this trade ----
        if buy[k]:
            if bal[u] <= 0 and u != wid: holders += 1
            bal[u] += tok[k]; first_buy.setdefault(u, s); last_buy_slot[u] = s
        else:
            bal[u] -= tok[k]
            if bal[u] <= 1e3 and u != wid: holders -= 1; bal[u] = 0.0
        ntr[u] += 1
        if u != wid:
            recent.append((s, bool(buy[k]), sol[k], u))
            if o is not None:
                if buy[k]: o["nb"] += 1; o["inn"] += sol[k]; o["ub"].add(u); o["last_buy"] = s; o["run"] = 0
                else:
                    o["ns"] += 1; o["out"] += sol[k]; o["last_sell"] = s; o["run"] += 1; o["first_out_sell"] = True; o["sells_since_peak"] += sol[k]
                    if u == sid: o["sib_sold"].append(s)
                    if copier[u]: o["cop_sold"].append(s)
                if vsol[k] > o["peak"]: o["peak"] = vsol[k]; o["sells_since_peak"] = 0.0
                o["trough"] = min(o["trough"], vsol[k])
        if T is not None and T["close"] == k:
            tr_i += 1; T = trips[tr_i] if tr_i < len(trips) else None; st_open = None
        elif T is not None and T["close"] is None and T["sells"] and k == T["sells"][0]:
            pass
    TRIPS.extend(trips)
    if mi % 500 == 0: print(mi, len(um), len(X), time.time() - t0, flush=True)
X = np.array(X, np.float32); META = np.array(META, np.int64)
np.savez(f"{OUT}/ev.npz", X=X, y1=np.array(Y1, np.int8), y3=np.array(Y3, np.int8), meta=META, feats=np.array(FEATS))
pickle.dump(TRIPS, open(f"{OUT}/trips.pkl", "wb"))
print("events", len(X), "trips", len(TRIPS), "pos1", sum(Y1), "pos3", sum(Y3), time.time() - t0)
