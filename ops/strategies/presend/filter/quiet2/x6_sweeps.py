#!/usr/bin/env python3
"""QUIET2 step 6: (A) the (d) threshold F and the no-history default and a minimum wh_dumps: tightening = MEASURED on the live fills,
loosening = INFERRED from chain proxies on the live quiet skips (calibrated on the armed windows); (B) the C5 stop N:M sweep
(stricter = MEASURED, looser = INFERRED); (C) the flat study's post-hoc try-time GATE (send a try only after >= M other trades since
the trigger) tested once on these 9 unseen runs (MEASURED, conservative: a gated fill is charged its window's later tries);
(D) hour of day and the owner's AMS r34 flats."""
import sys, json, collections, bisect
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
import q2lib as Q
rng = np.random.default_rng(3)
F = json.load(open(f"{Q.D}/features.json")); W = [r for r in F["windows"] if r["f"].get("chain_ok")]; SK = [s for s in F["skips"] if s["f"].get("chain_ok")]
QW = [r for r in W if r["since_last"] is not None]        # runs with QUIET on
FILL_SPEND = 0.45


def role_rows(rows, role): return [r for r in rows if r["role"] == role]


# ---- proxy calibration on the armed windows (all 9 runs): P(fill | proxy fill), and net vs proxy return for the filled ones
px = [r for r in W if r["f"].get("px_fill")]
pfill = sum(1 for r in px if r["filled"]) / len(px)
cal = [(r["net"], r["spend"] * (r["f"]["px_ret2"] / 100 - 0.033)) for r in px if r["filled"]]
a = np.array(cal); slope = np.polyfit(a[:, 1], a[:, 0], 1)
corr = np.corrcoef(a[:, 0], a[:, 1])[0, 1]
print(f"proxy: P(fill|proxy fill) = {pfill:.2f} (n={len(px)}); filled: corr(net, spend*(ret2-3.3%)) = {corr:.2f}, fit net = {slope[0]:.2f} x + {slope[1]:+.4f}; "
      f"mean net {a[:,0].mean():+.4f} vs proxy mean {a[:,1].mean():+.4f}")
# proxy flat agreement: proxy 0 followers vs chain-flat label on the filled
pf = [(r["f"]["px_fol_buyers"] == 0, r["lab"] == "FLAT") for r in px if r["filled"]]
tp = sum(1 for x, y in pf if x and y); fp = sum(1 for x, y in pf if x and not y); fn = sum(1 for x, y in pf if not x and y)
print(f"proxy '0 follower buyers' vs chain FLAT on filled: hit {tp}, false alarm {fp}, missed {fn}")


def ev_skip(s):
    """expected net of arming a quiet-skipped trigger (INFERRED): P(fill) x calibrated net - a window's failed-try fees"""
    f = s["f"]
    if not f.get("px_fill"): return -0.00016
    return pfill * (slope[0] * (FILL_SPEND * (f["px_ret2"] / 100 - 0.033)) + slope[1]) - 0.00016


# ---- (A) the (d) rule sweep
print("\n## (A) signal (d): skip when (a),(b),(c) hold AND [wh_dumps < MIN  or  (wh_dumps >= MIN and wh_fol < F)]  (no-history default = SKIP when MIN > 0 ... see rows)")
print("   current live = F 2.24, no history -> skip (counts as (d) true). Rows: MEASURED part = live fills newly removed (tighter) ; INFERRED part = live quiet-skips that would now be ARMED (looser), valued by the proxy")
print(f"{'F':>5s} {'no-hist':>8s} {'minD':>4s} | {'train: tighter fills rm (flat/win/loss)':>40s} {'measured gain':>14s} | {'looser skips armed':>18s} {'inferred gain':>14s} || {'TEST tighter':>28s} {'gain':>7s} | {'looser':>8s} {'inferred':>9s}")
rows_out = []
for Fthr in (0.5, 1.0, 1.5, 2.24, 3.0, 4.0, 5.0, 7.0):
    for nohist in ("skip", "arm"):
        for minD in (0, 3, 10):
            def d_new(r):
                if r["wh_dumps"] == 0: return nohist == "skip"
                if r["wh_dumps"] < minD: return nohist == "skip"
                return r["wh_fol"] < Fthr
            line = f"{Fthr:5.2f} {nohist:>8s} {minD:4d} |"
            for role in ("train", "test"):
                tight = [r for r in role_rows(QW, role) if r["q_a"] and r["q_b"] and r["q_c"] and d_new(r) and not r["all4"]]
                fills = [r for r in tight if r["filled"]]
                g_meas = sum(r["fee_fail"] for r in tight) - sum(r["net"] for r in fills)
                loose = [s for s in role_rows(SK, role) if s["q"] and s["q"][0] and s["q"][1] and s["q"][2] and not d_new(s)]
                g_inf = sum(ev_skip(s) for s in loose)
                lab = collections.Counter(r["lab"] for r in fills)
                if role == "train": line += f" {len(fills):3d} ({lab['FLAT']}/{lab['WIN']}/{lab['LOSS']}) {g_meas:+14.3f} | {len(loose):18d} {g_inf:+14.3f} ||"
                else: line += f" {len(fills):3d} ({lab['FLAT']}/{lab['WIN']}/{lab['LOSS']}) {g_meas:+7.3f} | {len(loose):8d} {g_inf:+9.3f}"
            print(line)
# what do the CURRENT quiet skips look like: proxies by (d) reason
print("\n   current quiet skips by (d) reason (all 9 runs): n, proxy would-fill, of those 0-follower, inferred value if armed")
for name, fn in (("no history", lambda s: s["wh_dumps"] == 0), ("wh_fol < 1", lambda s: 0 < s["wh_dumps"] and s["wh_fol"] < 1), ("1 <= wh_fol < 2.24", lambda s: s["wh_dumps"] > 0 and 1 <= s["wh_fol"] < 2.24)):
    g = [s for s in SK if fn(s)]; p = [s for s in g if s["f"].get("px_fill")]
    print(f"   {name:18s} n {len(g):3d} would-fill {len(p):3d} 0-fol {sum(1 for s in p if s['f']['px_fol_buyers']==0):3d} inferred {sum(ev_skip(s) for s in g):+.3f}  (mean px_ret2 of would-fill {np.mean([s['f']['px_ret2'] for s in p] or [0]):+.1f}%)")
# how do the fills with (a)(b)(c) quiet but (d) false (armed because of the whale history) do?
print("\n   fills ARMED only because (d) was false (a,b,c quiet; whale history >= 2.24):")
for role in ("train", "test"):
    g = [r for r in role_rows(QW, role) if r["q_a"] and r["q_b"] and r["q_c"] and not r["q_d"] and r["filled"]]
    print(f"   {role}: {len(g)} fills, flat {sum(1 for r in g if r['lab']=='FLAT')}, win {sum(1 for r in g if r['lab']=='WIN')}, net {sum(r['net'] for r in g):+.3f} ; by wh_fol: " +
          ", ".join(f"[{lo},{hi}) n={sum(1 for r in g if lo<=r['wh_fol']<hi)} net={sum(r['net'] for r in g if lo<=r['wh_fol']<hi):+.3f}" for lo, hi in ((2.24, 3), (3, 4), (4, 6), (6, 99))))

# ---- (B) the C5 stop sweep. engine's view approximated by the chain: others in slots <= trig + N - 1 (decided at slot >= trig + N)
print("\n## (B) C5 stop N:M (live = 6:2). Stricter than live: fills at >= N slots after the trigger with < M other trades before slot N are removed (MEASURED).")
print("   Looser (8:2, 10:2 = off): windows the live stop disarmed 'quiet' at +6 that the proxy says would have filled later (INFERRED).")
stopped = [r for r in W if r["disarm_why"] == "quiet"]
print(f"   live stop disarms: {len(stopped)} windows; proxy says {sum(1 for r in stopped if r['f'].get('px_fill') and r['f'].get('px_dump_slot',0) >= 6)} would have filled at >= +6; inferred value {sum(ev_skip(r) for r in stopped if r['f'].get('px_fill') and r['f'].get('px_dump_slot',0)>=6):+.3f} "
      f"(0-follower {sum(1 for r in stopped if r['f'].get('px_fill') and r['f'].get('px_dump_slot',0)>=6 and r['f']['px_fol_buyers']==0)})")
print(f"{'N:M':>5s} | {'train fills rm (flat/win/loss)':>32s} {'gain':>7s} {'a28':>7s} {'f27':>7s} | {'TEST fills rm':>24s} {'gain':>7s} {'f28':>7s} {'a34':>7s}")
for N in (1, 2, 3, 4, 5, 6, 7, 8):
    for M in (1, 2, 3):
        key = f"after_tr_{N-1}" if N >= 1 else None
        line = f"{N}:{M:<3d} |"
        for role in ("train", "test"):
            g = role_rows(W, role)
            rm = [r for r in g if r["filled"] and r["slots_after_trigger"] >= N and (r["f"].get(key, 0) if N > 1 else 0) < M]
            # the live 6:2 already removed; a stricter rule removes more: count only fills the live rule kept (all live fills)
            gain = -sum(r["net"] for r in rm)      # fees of the later tries are not saved by a stop that fires at the fill's own slot (conservative: 0)
            lab = collections.Counter(r["lab"] for r in rm)
            per = {rr: -sum(r["net"] for r in rm if r["run"] == rr) for rr in ("a28", "f27", "f28", "a34")}
            if role == "train": line += f" {len(rm):3d} ({lab['FLAT']:2d}/{lab['WIN']:2d}/{lab['LOSS']:2d}) {gain:+7.3f} {per['a28']:+7.3f} {per['f27']:+7.3f} |"
            else: line += f" {len(rm):3d} ({lab['FLAT']:2d}/{lab['WIN']:2d}/{lab['LOSS']:2d}) {gain:+7.3f} {per['f28']:+7.3f} {per['a34']:+7.3f}"
        print(line)

# ---- (C) the try-time GATE (flat study's post-hoc lead), engine view: others since the trigger seen when the filling try was signed (its pos)
print("\n## (C) try-time GATE: the filling try is not sent if < M other trades (not the whale, not us) since the trigger were seen at its signing (pos).")
print("   Conservative: a gated fill is removed and the window's later tries are charged. Pre-specified in the flat study (10-27), tested once here.")
C = np.load(f"{Q.D}/chain.npz"); I = json.load(open(f"{Q.D}/ids.json"))
mid = {m: k for k, m in enumerate(I["mint"])}; uid = {u: k for k, u in enumerate(I["user"])}
S, IX, MI, UI, BUY = C["s"].astype(np.int64), C["i"], C["mint"], C["user"], C["buy"]
morder = np.argsort(MI, kind="stable"); msorted = MI[morder]; mstart = np.searchsorted(msorted, np.arange(len(I["mint"]) + 1))
ours = {uid[u] for u in Q.OURS if u in uid}
gate_rows = []
for run, R in Q.RUNS.items():
    Wr, _, _, _ = Q.load(run)
    for (seg, wi), w in Wr.items():
        if not w["fills"]: continue
        fs = w["fills"][0]["sig"]; t = next((t for t in w["tries"] if t["a"]["sig"] == fs), None)
        if not t: continue
        pos = t["a"]["pos"]; mk = mid.get(w["mint"]); wh = uid.get(w["whale"], -1)
        if mk is None: continue
        rows = morder[mstart[mk]:mstart[mk + 1]]
        p = list(zip(S[rows].tolist(), IX[rows].tolist()))
        a = bisect.bisect_right(p, (w["trig_slot"], w["arm"]["trig"]["idx"])); b = bisect.bisect_right(p, (pos[0], pos[1]))
        seg_rows = rows[a:b]; u = UI[seg_rows]
        oth = int(((u != wh) & ~np.isin(u, list(ours))).sum())
        later_fees = sum(Q.try_fee(x) for x in w["tries"] if x["a"]["t"] > t["a"]["t"])
        fw = next((r for r in W if r["run"] == run and r["seg"] == seg and r["w"] == wi), None)
        if fw: gate_rows.append(dict(run=run, role=R["role"], oth=oth, net=fw["net"], lab=fw["lab"], later_fees=later_fees / 1e9, n_tries_after=sum(1 for x in w["tries"] if x["a"]["t"] > t["a"]["t"])))
print(f"   fills with a matched filling try: {len(gate_rows)}")
for M in (1, 2):
    for role in ("train", "test"):
        g = [x for x in gate_rows if x["role"] == role]; rm = [x for x in g if x["oth"] < M]
        gain = -sum(x["net"] for x in rm) - sum(x["later_fees"] for x in rm)
        lab = collections.Counter(x["lab"] for x in rm)
        per = {rr: -sum(x["net"] for x in rm if x["run"] == rr) - sum(x["later_fees"] for x in rm if x["run"] == rr) for rr in Q.RUNS}
        bs = []
        arr = np.array([(-x["net"] - x["later_fees"]) if x["oth"] < M else 0.0 for x in g])
        for _ in range(2000): bs.append(arr[rng.integers(0, len(arr), len(arr))].sum())
        print(f"   M={M} {role:5s}: fills removed {len(rm)}/{len(g)} (flat {lab['FLAT']}/{sum(1 for x in g if x['lab']=='FLAT')}, win {lab['WIN']} {-sum(x['net'] for x in rm if x['lab']=='WIN'):+.3f} = {100*sum(x['net'] for x in rm if x['lab']=='WIN')/max(sum(x['net'] for x in g if x['lab']=='WIN'),1e-9):.0f}% of win P&L, loss {lab['LOSS']} {-sum(x['net'] for x in rm if x['lab']=='LOSS'):+.3f}) "
              f"later-try fees charged {sum(x['later_fees'] for x in rm):.3f} -> gain {gain:+.3f} 90% CI [{np.percentile(bs,5):+.3f},{np.percentile(bs,95):+.3f}] per run " + " ".join(f"{k}:{v:+.3f}" for k, v in per.items() if Q.RUNS[k]['role'] == role))

# ---- (D) hour of day (PKT) and the owner's AMS r34 flats
print("\n## (D) flat share by hour (PKT), all 9 runs (fills)")
byh = collections.defaultdict(list)
for r in W:
    if r["filled"]: byh[r["hour"]].append(r)
for h in sorted(byh):
    g = byh[h]; print(f"   {h:02d}h fills {len(g):3d} flat {sum(1 for r in g if r['lab']=='FLAT'):2d} ({100*sum(1 for r in g if r['lab']=='FLAT')/len(g):4.0f}%) net {sum(r['net'] for r in g):+.3f} per fill {np.mean([r['net'] for r in g]):+.4f}")
print("\n## AMS r34 flats (chain label): signals and attention at arm time, the dump, our place")
for r in W:
    if r["run"] == "a34" and r["lab"] == "FLAT":
        f = r["f"]
        print(f"   {r['pkt'][6:]} {r['net']:+.4f} held {r['slots_held']} {r['exit_why']:10s} q={''.join('1' if x else '0' for x in (r['q_a'],r['q_b'],r['q_c'],r['q_d']))} wh_dumps {r['wh_dumps']:3d} wh_fol {r['wh_fol']:5.2f} | buyers60s {f['n_buyers_60s']:3d} tr/s {f['trades_per_s_60']:.2f} fb_n {r['fb_n']:2d} coh_hold {r['coh_hold']} holders>0.5% {f['holders_gt0_5pct']:2d} | dump {f.get('dump_sol',0):.1f} SOL drop {f.get('dump_drop',0):.0f}% by whale {f.get('dump_by_whale')} hold_buyers {f.get('hold_buyers')} | in line after dump: {f.get('dump_to_fill_others')} | https://gmgn.ai/sol/token/{r['mint']}")
print("\n## AMS r34 WIN fills that look the same at arm time (<= 5 buyers in 60 s) - why a flat filter costs winners")
for r in W:
    if r["run"] == "a34" and r["lab"] == "WIN" and r["f"]["n_buyers_60s"] <= 5:
        f = r["f"]; print(f"   {r['pkt'][6:]} {r['net']:+.4f} buyers60s {f['n_buyers_60s']} fb_n {r['fb_n']} coh_hold {r['coh_hold']} holders>0.5% {f['holders_gt0_5pct']} fol_buyers {f['fol_buyers']} https://gmgn.ai/sol/token/{r['mint']}")
