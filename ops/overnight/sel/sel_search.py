#!/usr/bin/env python3
# Selection study, step 2 (local only): search readable configs (AND of feature thresholds known at the dump) on TRAIN hours,
# judge them on later TEST hours. Our trade per pick = guarded replay (buy only if the price when we land <= 1.02 x the
# post-dump price, else a failed attempt -0.0002), exit after H slots. Beam search; objective per mode:
#   imit:W  -> F1 vs wallet W's picks (W8 prefix or ANY)       profit -> train P&L at 35 + 50 ms with win% >= WINMIN
# usage: python3 -I sel_search.py MODE [SEED_CONFIG_JSON]     env: SPLIT (PKT 'MM-DD HH:MM'), H (exit slots, 4), WINMIN, MINPH
import json, gzip, sys, os, time, calendar, itertools
import numpy as np
EV = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/sel/sel_events.jsonl.gz", "rt")]
H = os.environ.get("H", "4"); WINMIN = float(os.environ.get("WINMIN", "0.6")); MINPH = float(os.environ.get("MINPH", "6"))
SPLIT = calendar.timegm(time.strptime("2026-" + os.environ.get("SPLIT", "10-23 06:00"), "%Y-%m-%d %H:%M")) - 18000
FEATS = ["age", "sell", "drop_pct", "vsol", "pb", "dd", "nb", "ns", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "s_frac", "s_pnl", "s_nb",
         "s_entry", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow", "slotpos",
         "prev_sell_ms", "n_tr", "vmax", "since_buy"]
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
X = np.array([[fv(r, k) for k in FEATS] for r in EV], dtype=float)
T = np.array([r["bt"] + r["age"] for r in EV])
def pnl(L):
    out = np.full(len(EV), np.nan); fill = np.zeros(len(EV), bool)
    for i, r in enumerate(EV):
        if str(L) in r["pnl"]:
            f = r["px"][str(L)] <= 1.02; fill[i] = f; out[i] = r["pnl"][str(L)][H] if f else -0.0002
    return np.nan_to_num(out), fill
P = {L: pnl(L) for L in (20, 35, 50, 75)}
LAB = {w: np.array([w in r["lab"] for r in EV]) for w in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX")}
LAB["ANY"] = LAB["HkQ7hMjy"] | LAB["DYXDDrZC"] | LAB["haqqiUUX"]
tr = T < SPLIT; te = ~tr
hours = lambda m: (T[m].max() - T[m].min()) / 3600
HTR, HTE = hours(tr), hours(te)
def mask(cfg):
    m = np.ones(len(EV), bool)
    for k, op, v in cfg:
        j = FEATS.index(k); m &= (X[:, j] >= v) if op == ">=" else (X[:, j] <= v)
    return m
def stats(m, part, hrs):
    mm = m & part; n = int(mm.sum()); o = dict(n=n, ph=n / hrs)
    for L in (35, 50, 75):
        p, f = P[L]; fills = mm & f
        o[f"p{L}"] = float(p[mm].sum()); o[f"f{L}"] = int(fills.sum()); o[f"w{L}"] = float((p[fills] > 0).mean()) if fills.any() else 0.0
    return o
def show(tag, cfg):
    m = mask(cfg)
    for part, hrs, nm in ((tr, HTR, "TRAIN"), (te, HTE, "TEST ")):
        s = stats(m, part, hrs); mm = m & part
        ov = {w: (int((mm & LAB[w]).sum()), int((LAB[w] & part).sum())) for w in LAB}
        print(f"  {nm} {s['n']:5d} picks ({s['ph']:5.1f}/h) | 35 ms {s['p35']:+7.2f} fills {s['f35']} win {s['w35']:.0%} | 50 ms {s['p50']:+7.2f} win {s['w50']:.0%} | 75 ms {s['p75']:+7.2f} win {s['w75']:.0%}"
              f" | theirs among ours: {(ov['ANY'][0] / max(s['n'], 1)):.0%}; of theirs we catch: HkQ7 {ov['HkQ7hMjy'][0] / max(ov['HkQ7hMjy'][1], 1):.0%} DYX {ov['DYXDDrZC'][0] / max(ov['DYXDDrZC'][1], 1):.0%} haq {ov['haqqiUUX'][0] / max(ov['haqqiUUX'][1], 1):.0%}")
def grid(k):
    j = FEATS.index(k); v = X[tr, j]; v = v[v < 1e8]
    return sorted(set(float(np.quantile(v, q)) for q in np.linspace(0.05, 0.95, 19)))
GR = {k: grid(k) for k in FEATS}
def objective(cfg, mode):
    m = mask(cfg) & tr; n = m.sum()
    if n / HTR < MINPH: return -1e9
    if mode.startswith("imit"):
        y = LAB[mode.split(":")[1]] & tr; tp = (m & y).sum()
        return 2 * tp / (n + y.sum())
    p35, f35 = P[35]; p50, _ = P[50]; fills = m & f35
    win = (p35[fills] > 0).mean() if fills.any() else 0
    pen = 0 if win >= WINMIN else (WINMIN - win) * 200
    return float(p35[m].sum() + p50[m].sum()) - pen
def search(mode, seed=(), depth=6, beam=6):
    B = [(objective(list(seed), mode), list(seed))]; best = B[0]
    for d in range(depth):
        cand = []
        for sc, cfg in B:
            used = {(k, op) for k, op, _ in cfg}
            for k in FEATS:
                for op in (">=", "<="):
                    if (k, op) in used: continue
                    for v in GR[k]:
                        c = cfg + [(k, op, v)]; cand.append((objective(c, mode), c))
        cand.sort(key=lambda x: -x[0]); B = []; seen = set()
        for sc, c in cand:
            key = tuple(sorted((k, op) for k, op, _ in c))
            if key in seen: continue
            seen.add(key); B.append((sc, c))
            if len(B) >= beam: break
        if B[0][0] <= best[0] + 1e-6: break
        best = B[0]
        print(f"depth {d + 1}: objective {best[0]:.4f} | " + " AND ".join(f"{k} {op} {v:.4g}" for k, op, v in best[1]), flush=True)
    return best[1]
if __name__ == "__main__":
    mode = sys.argv[1]; seed = [tuple(x) for x in json.loads(sys.argv[2])] if len(sys.argv) > 2 else []
    print(f"train {tr.sum()} dumps / {HTR:.1f} h, test {te.sum()} dumps / {HTE:.1f} h (split {os.environ.get('SPLIT', '10-23 06:00')} PKT), exit {H} slots, mode {mode}")
    for w in LAB:
        print(f"  their picks {w}: train {LAB[w][tr].sum() / HTR:.1f}/h, test {LAB[w][te].sum() / HTE:.1f}/h")
    print("BASE (all dumps):"); show("base", [])
    for w in ("DYXDDrZC", "HkQ7hMjy", "haqqiUUX", "ANY"):
        m = LAB[w]
        for part, hrs, nm in ((tr, HTR, "TRAIN"), (te, HTE, "TEST ")):
            s = stats(m, part, hrs)
            print(f"  [{w} own picks] {nm} {s['n']:5d} ({s['ph']:5.1f}/h) | 35 ms {s['p35']:+7.2f} win {s['w35']:.0%} | 50 ms {s['p50']:+7.2f} win {s['w50']:.0%} | 75 ms {s['p75']:+7.2f} win {s['w75']:.0%}")
    cfg = search(mode, seed)
    print("FINAL:", json.dumps(cfg)); show("final", cfg)
