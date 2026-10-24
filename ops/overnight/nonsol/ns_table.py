#!/usr/bin/env python3
# READ-ONLY, offline. One row per NON-SOL-quoted, non-mayhem launch of both runs (windows: R1 10-22 03:07-18:00 PKT,
# R2 10-22 20:43 - 10-23 07:57 PKT): create-time facts, curve path vs the post-bundle price (with / without fast snipers),
# buy flow by wallet class, and the REPLAY of our mechanics on the quote-denominated curve:
#   buy 0.5 SOL-eq right after the dev's glued bundle, only if first (price at our landing <= 1.005 x post-bundle),
#   landing 30/45/75 ms (R2: our engine's arrival timeline, block-order placement; R1 / no timeline: block-position proxy),
#   SOL -> quote at the measured hourly rate minus a swap leg, pump fees of THIS curve (protocol + creator bps from its
#   events), 1.5% pessimistic fill, exits by time (t2..t20 + end of next slot), sell -> quote -> SOL minus a swap leg.
#   variants: base (real path) | strict (every fast-sniper and pro wallet's trades after our entry removed, except sells
#   of wallets that held before our entry) | harsh (only their buys removed, their sells kept - as rp.sim drop_after)
# Output data/table.jsonl (raw quote proceeds kept so costs / swap legs can be re-applied in the analysis).
import sys, os, json, math, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import ns, rp
from multiprocessing import Pool
HERE = "/home/moiz/sniper/ops/overnight/nonsol"; DATA = os.path.join(HERE, "data")
WIN = {"R1": (1792620420, 1792501200 + 0), "R2": (0, 0)}
# PKT windows -> unix: R1 10-22 03:07 PKT = 10-21 22:07 UTC; R1 end 10-22 18:00 PKT = 13:00 UTC; R2 20:43 PKT = 15:43 UTC; R2 end 10-23 07:57 PKT = 02:57 UTC
import calendar
def ut(y, mo, d, h, mi): return calendar.timegm((y, mo, d, h, mi, 0))
WIN = {"R1": (ut(2026, 10, 21, 22, 7), ut(2026, 10, 22, 13, 0)), "R2": (ut(2026, 10, 22, 15, 43), ut(2026, 10, 23, 2, 57))}
SL = rp.SLOT_MS / 1000.0
GRAD_VTOK = 279_900_000_000_000                  # curve complete: real token reserves 0 (vtok - rtok = 279.9e12 on every curve)
LANDS = (30, 45, 75)
EXITS = (0.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0)   # 0.0 = end of the next slot (eos1)
B = 0.5; S0 = 0.003; FILLPEN = 0.015
L, CR, TR, W = ns.load()
R = json.load(open(os.path.join(DATA, "rates.json")))
PRO = {"9Sh2fd": "9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspi": "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipY": "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ",
       "dKMjeG": "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK", "CWiNFA": "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J", "9qz7cW": "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw",
       "FiFawH": "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W", "AHwJSn": "AHwJSnFNUiAU9FfT5ewW2osqMo938WtL7KhfsJyfpaN2", "4yFAz": "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"}
PROW = set(PRO.values())
def rate(qm, bt):
    h = R["hourly"].get(qm, {}).get(str(int(bt // 3600)))
    if h and h["b"] and h["s"] and h["nb"] >= 3 and h["ns"] >= 3: return math.sqrt(h["b"] * h["s"]), "hour"
    s = R["summ"].get(qm)
    if s and s["mid_med"]: return s["mid_med"], "run"
    if R["ref"].get(qm): return R["ref"][qm], "ref"
    return None, None
def clean(tr):
    """drop mis-decoded events: keep trades whose (virtual - real) quote reserves equal the curve's modal offset"""
    if not tr: return []
    off = collections.Counter(t["vsol"] - t["rq"] for t in tr).most_common(1)[0][0]
    return [t for t in tr if t["vsol"] - t["rq"] == off and 0 < t["vsol"] < 2 ** 62 and 0 < t["vtok"] <= 1_073_000_000_000_000 and t["sol"] < 2 ** 62 and t["tok"] < 2 ** 62]
def universe():
    out = []
    for m, cr in CR.items():
        c = L.get(m)
        if not c or cr["quote"] == "SOL" or not c.get("bt"): continue
        a, b = WIN[c["run"]]
        if not (a <= c["bt"] < b): continue
        out.append(m)
    return out
def fee_of(tr):
    f = collections.Counter((t["fbps"], t["cbps"]) for t in tr if t["fbps"] > 0)
    return f.most_common(1)[0][0] if f else (95, 30)
def at(tr, k_slot, p_def):
    p = None
    for t in tr:
        if t["s"] > k_slot: break
        p = t["vsol"] / t["vtok"]
    return p if p is not None else p_def
def rebase(tr, drop, from_k=0):
    """trade list with `drop` wallets' trades (from index from_k on) removed; reserves recomputed after the first removal"""
    out = list(tr[:from_k]); V = T = None
    for t in tr[from_k:]:
        if t["user"] in drop:
            if V is None:
                if out: V, T = out[-1]["vsol"], out[-1]["vtok"]
                else: V, T = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
            continue
        if V is None: out.append(t); continue
        x = dict(t)
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; x["tok"] = d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]; x["sol"] = so
        x["vsol"], x["vtok"] = V, T; out.append(x)
    return out
def place_q(tr, c, st, outs, land_ms, failed, max_slots=6):
    """block-order placement with our arrival timeline (rp.place_bo2 without the SOL-amount check: amounts are quote units)"""
    S = c["slot"]
    succ = [(t["s"], t["i"], k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    fl = [(s, i, None, u) for s, i, u in failed if s - S <= max_slots and u not in st["insiders"]]
    used_s, used_f, seen = set(), set(), {}
    for a, sol, isbuy, w6 in sorted(outs):
        hit = None
        for s, i, k, t in succ:
            if k in used_s or not t["user"].startswith(w6): continue
            if t["buy"] != isbuy and not (sol == 0 and not isbuy): continue
            used_s.add(k); hit = (s, i); break
        if hit is None:
            for s, i, _, u in fl:
                if (s, i) in used_f or not u.startswith(w6): continue
                used_f.add((s, i)); hit = (s, i); break
        if hit is not None: seen[hit] = min(a, seen.get(hit, a))
    anchors = sorted(seen.items()); last = st["g_end"] - 1; n = 0
    for s, i, k, t in succ:
        a = seen.get((s, i))
        if a is None:
            later = [ms for (ss, ii), ms in anchors if (ss, ii) > (s, i)]
            a = min(later) if later else None
            if a is None or a >= land_ms: continue
        elif a >= land_ms: continue
        last = max(last, k); n += 1
    return max(last + 1, st["g_end"]), n
def sim_q(path, idx, S, fr, Qin, drop=None, keep_sells=(), harsh=False):
    """our buy of Qin raw quote units right before path[idx]; -> {exit_s: (quote_out_raw, nbuy_after, grad)}"""
    V, T = path[idx - 1]["vsol"], path[idx - 1]["vtok"]
    X = Qin / (1 + fr); q = T * X / (V + X); V += X; T -= q; q *= (1 - FILLPEN)
    buy_slot = max(S, path[idx - 1]["s"]); res = {}; pend = list(EXITS); k = idx; grad = False; nb = 0
    while pend:
        t = path[k] if k < len(path) else None
        while pend and (t is None or grad or (pend[0] == 0.0 and t["s"] > buy_slot + 1) or (pend[0] > 0 and (t["s"] - buy_slot) * SL >= pend[0])):
            res[pend.pop(0)] = (V * q / (T + q) * (1 - fr), nb, grad)
        if not pend or t is None: break
        k += 1
        if drop and t["user"] in drop:
            if t["buy"] or not harsh:
                if not (not t["buy"] and t["user"] in keep_sells): continue
        if t["buy"]: d = T * t["sol"] / (V + t["sol"]); V += t["sol"]; T -= d; nb += 1
        else: so = V * t["tok"] / (T + t["tok"]); V -= so; T += t["tok"]
        if T <= GRAD_VTOK: grad = True
    return res
FAST = None
def init(fast):
    global FAST, SLIPF
    FAST = fast
def classify(u, ins):
    if u in ins: return "ins"
    if u in PROW: return "pro"
    if u in FAST: return "fast"
    return "gen"
def one(m, O, fa):
    c = L[m]; cr = CR[m]; S = c["slot"]
    row = dict(m=m, run=c["run"], bt=c["bt"], quote=cr["quote"], mayhem=cr["mayhem"], vq0=cr["vq0"], name=c.get("name"), creator=c.get("creator"), signer=c.get("user"),
               payer_is_creator=int(c.get("payer") == c.get("creator")), create_fee=c.get("fee"), cvar=(c.get("ixn") or [""])[0])
    rt, rsrc = rate(cr["quote"], c["bt"]); row["rate"] = rt; row["rate_src"] = rsrc
    tr = clean(TR.get(m, []))
    row["ntr"] = len(tr)
    if cr["mayhem"] or not tr or rt is None: return row
    st = rp.structure(tr, c); ins = st["insiders"]
    row["g_end"] = st["g_end"]; row["dev_k"] = st["dev_k"]; row["n_glued"] = len(st["glued"]); row["glued_w"] = len({t["user"] for t in st["glued"]})
    fb, cb = fee_of(tr); fr = (fb + cb) / 1e4; row["fbps"] = fb; row["cbps"] = cb
    toS = lambda x: x * rt / 1e9
    row["vq0_sol"] = round(toS(cr["vq0"]), 3)
    if st["dev_k"] is not None:
        d = tr[st["dev_k"]]; row["dev_sol"] = round(toS(d["sol"] + d["feeq"] + d["cfeeq"]), 4); row["dev_tok_share"] = round(d["tok"] / 1e15, 5)
    else: row["dev_sol"] = 0.0
    row["glued_sol"] = round(sum(toS(t["sol"]) for t in st["glued"] if t["buy"]), 4)
    w = W.get(c["sig"]); row["create_tips"] = (w or {}).get("tips")
    if st["g_end"] < 1: return row
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; row["pb_mult0"] = round(p_b / (cr["vq0"] / 1.073e15), 4)
    # ---- path vs post-bundle price (all, without fast snipers, without fast + pro), checkpoints after the create
    CK = (1, 2, 5, 10, 30, 60)
    trnf = rebase(tr, FAST - ins, st["g_end"]); trnfp = rebase(tr, (FAST | PROW) - ins, st["g_end"])
    row["px"] = [round(at(tr, S + int(x / SL), p_b) / p_b, 4) for x in CK]
    row["px_nofast"] = [round(at(trnf, S + int(x / SL), p_b) / p_b, 4) for x in CK]
    row["px_nofp"] = [round(at(trnfp, S + int(x / SL), p_b) / p_b, 4) for x in CK]
    row["pk60"] = round(max([t["vsol"] / t["vtok"] for t in tr if t["s"] <= S + int(60 / SL)] + [p_b]) / p_b, 4)
    # ---- flow by class (buys after the bundle): SOL-eq and distinct buyers in [0,2) [2,10) [10,60) s after the create
    fl = {}; buyers = collections.defaultdict(set); first_fast = None
    for t in tr[st["g_end"]:]:
        dt = (t["s"] - S) * SL
        if dt >= 60: break
        win = "w0" if dt < 2 else ("w2" if dt < 10 else "w10")
        cl = classify(t["user"], ins)
        k = f"{cl}_{win}_{'b' if t['buy'] else 's'}"
        fl[k] = fl.get(k, 0.0) + toS(t["sol"])
        if t["buy"]: buyers[f"{cl}_{win}"].add(t["user"])
    row["flow"] = {k: round(v, 4) for k, v in fl.items()}; row["nbuyers"] = {k: len(v) for k, v in buyers.items()}
    row["pro_in"] = sorted({p for p, u in PRO.items() if any(t["user"] == u and t["buy"] for t in tr)})
    row["pro_first_dt"] = {p: round((min(t["s"] for t in tr if t["user"] == u and t["buy"]) - S) * SL, 3) for p, u in PRO.items() if any(t["user"] == u and t["buy"] for t in tr)}
    row["fast_buys_2slot"] = sum(1 for t in tr[st["g_end"]:] if t["buy"] and t["user"] in FAST and t["s"] - S <= 2)
    # ---- replay
    outs = (O.get(m) or {}).get("outs") if c["run"] == "R2" else None
    row["plc"] = "obs" if outs is not None else "proxy"
    Qin = B * (1 - S0) * 1e9 / rt
    rep = {}
    for Lm in LANDS:
        if outs is not None: ib, nah = place_q(tr, c, st, outs, Lm, fa)
        else: ib, nah = rp.place_proxy(tr, c, st, Lm)
        if ib < 1: continue
        pr = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b
        e = dict(ib=ib, nah=nah, pr=round(pr, 5))
        if pr <= 1.005 and tr[ib - 1]["vtok"] > GRAD_VTOK:
            pre = {t["user"] for t in tr[:ib] if t["buy"]}
            for var, kw in (("base", {}), ("strict", dict(drop=(FAST | PROW) - ins, keep_sells=pre)), ("harsh", dict(drop=(FAST | PROW) - ins, harsh=True))):
                r = sim_q(tr, ib, S, fr, Qin, **kw)
                e[var] = {str(x): [round(toS(v[0]), 6), v[1], int(v[2])] for x, v in r.items()}
        rep[str(Lm)] = e
    row["rep"] = rep
    return row
def work(key):
    run, b, ms = key
    fa = rp.read_failed(run, b, set(ms)) if run == "R2" else {}
    O = {}
    if run == "R2":
        global OBS
        O = {m: OBS[m] for m in ms if m in OBS}
    out = []
    for m in ms:
        try: out.append(one(m, O, fa.get(m, [])))
        except Exception as ex: out.append(dict(m=m, err=repr(ex)))
    return out
OBS = None
if __name__ == "__main__":
    U = universe()
    print("non-SOL launches in windows:", len(U), collections.Counter(L[m]["run"] for m in U))
    # fast snipers: SOL side (q9z list, owner's rule on both runs) + the same rule on the non-SOL curves
    fs_sol = set(json.load(open("/home/moiz/sniper/ops/overnight/q9z/fast_snipers.json")))
    fast = collections.Counter(); tot = collections.Counter()
    for m in U:
        cr = CR[m]
        if cr["mayhem"]: continue
        tr = clean(TR.get(m, []))
        if not tr: continue
        c = L[m]; st = rp.structure(tr, c); seen = set()
        for t in tr[st["g_end"]:]:
            if not t["buy"] or t["user"] in st["insiders"] or t["user"] in seen: continue
            seen.add(t["user"]); tot[t["user"]] += 1
            if t["s"] - c["slot"] <= 2: fast[t["user"]] += 1
    fs_ns = {w for w in fast if fast[w] >= 5 and fast[w] / tot[w] >= 0.5}
    FASTS = fs_sol | fs_ns
    json.dump(dict(sol=sorted(fs_sol), nonsol=sorted(fs_ns), nonsol_counts={w: [fast[w], tot[w]] for w in fs_ns}), open(os.path.join(DATA, "fast_snipers.json"), "w"))
    print(f"fast snipers: SOL-side list {len(fs_sol)}, non-SOL rule {len(fs_ns)} (overlap {len(fs_sol & fs_ns)}), union {len(FASTS)}")
    OBS = rp.load_obs()
    byb = collections.defaultdict(list)
    for m in U: byb[(L[m]["run"], rp.bucket(m))].append(m)
    keys = [(r, b, ms) for (r, b), ms in sorted(byb.items())]
    n = 0
    with Pool(6, initializer=init, initargs=(FASTS,)) as p, open(os.path.join(DATA, "table.jsonl.tmp"), "w") as f:
        for rows in p.imap_unordered(work, keys):
            for r in rows: f.write(json.dumps(r, separators=(",", ":")) + "\n")
            n += 1
            if n % 64 == 0: print("buckets", n, "/", len(keys), flush=True)
    os.rename(os.path.join(DATA, "table.jsonl.tmp"), os.path.join(DATA, "table.jsonl"))
    print("DONE")
