#!/usr/bin/env python3
# Parity export for the engine's pre-send SHADOW (src/presend.rs; agent 10-25 PKT). Read-only on the study data.
# For a few hundred R3 / R4 tokens: ALL their curve trades exactly as the engine receives them (slot, tx index, event index,
# signature, user, side, SOL, tokens, virtual reserves, fee bps), rebuilt from the phase-A rows the day arrays were built from
# (p1_build.stage_a rules) and CHECKED against the day arrays (rows, arrival clock, fee rate, follower slack, insiders); plus the
# STUDY's own T2 events for the chosen config (ps6_select "T2|c": htype 3 = non-creator, non-create-slot-insider wallet whose
# first >= 3% crossing is >= 5% of supply; W 10 slots; y 0.12 trailing; 0.55 SOL; exit c2_tp10_sl20), taken from ps4_<day>.npz
# (windows, first fills per queue row, paths) with ps5_lib.run's per-token arming (one armed window per token; a fill blocks the
# token until our sell + 300 ms) applied per queue row (a) / (b) / (c) over ALL windows of the token (no evaluation-window cut:
# the engine has none).
# -> testdata/presend_parity.json, + (optional) --full DAY: every token of DAY to a file outside the repo (scratch use)
# usage: python3 ps12_parity.py [tokens_per_day] [procs] [--full R4 OUTFILE]
import sys, os, json, gzip, glob, zlib, hashlib, time, collections
import numpy as np
from multiprocessing import Pool
import ps_common as C
import ps5_lib as E
REPO = "/home/moiz/sniper"
PHA = {"R3": ["/home/moiz/sniper-data/collect/phaseA_r3", "/home/moiz/sniper-data/strategies/phaseA_r3tail"],
       "R4": ["/home/moiz/sniper-data/strategies/bukp/phaseA_r4", "/home/moiz/sniper-data/strategies/dipdetect/phaseA_r4b"]}
NBK = {"R3": 40, "R4": 96}                      # buckets read per day (bounded reading of phase A)
MAXTR = 1500
CFG = dict(W=10, y=0.12, size=0.55, ex="c2_tp10_sl20", htype=3, hpct_min=5.0)
ROWS = ("a", "b", "c"); DFIX = {"a": 0.0, "b": 5.0, "c": 10.0}
SMS = 212.0; MARGIN = 300.0
SLACK = sorted(sl for _, sl, _ in json.load(open("/home/moiz/sniper/ops/overnight/verify2/work/a8_slack.json"))["rows"])
def slack(sig):
    h = int(hashlib.sha256(("dip" + sig).encode()).hexdigest()[:8], 16) / 2 ** 32
    return min(SLACK[min(len(SLACK) - 1, int(h * len(SLACK)))], 1e6)

def study_events(day):
    """the study's T2 windows (chosen filter) with per-row arming / fills, keyed by token"""
    z = np.load(f"{C.OUT}/ps4_{day}.npz"); D = {k: z[k] for k in z.files}
    d = C.load(day, cols=("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "wt", "uid"))
    FI = E.FI; f = D["w_f"]
    T2all = np.flatnonzero(D["w_fam"] == 2)
    sel = T2all[(f[T2all, FI["htype"]] == CFG["htype"]) & (f[T2all, FI["hpct"]] >= CFG["hpct_min"])]
    yi = E.YS.index(CFG["y"]); si = E.SIZES.index(CFG["size"]); e = E.EXI[CFG["ex"]]
    nW = len(D["w_fam"]); FR = np.full((len(E.YS), len(E.DMOD), nW), -1, np.int64)
    FR[D["f_y"], D["f_d"], D["f_w"]] = np.arange(len(D["f_w"]))
    arr = d["arr"]; f_time = arr[D["f_x"]] + D["f_D"]
    st = D["w_start"][sel]; en = np.minimum(D["w_end"][sel], st + CFG["W"] * SMS); tok = D["w_tok"][sel]
    rows = {}
    for r in ROWS:
        di = E.DMOD.index(r); fr = FR[yi, di, sel]; has = fr >= 0
        ft = np.where(has, f_time[np.maximum(fr, 0)], np.inf)
        valid = has & (ft < en)
        pid = np.where(has, D["f_pid"][np.maximum(fr, 0)], -1)
        sin = np.where(has, D["p_sin"][np.maximum(pid, 0)], 0)
        off = np.where(has, D["p_off"][np.maximum(pid, 0), si, e], 0).astype(np.int64)
        pn = np.where(has, D["p_pnl"][np.maximum(pid, 0), si, e], 0.0)
        xt = (sin + off) * SMS + 75.0
        # ps5_lib.run: one armed window per token at a time; a fill blocks the token until our sell lands + MARGIN
        o = np.lexsort((st, tok)); armed = np.zeros(len(sel), bool); aend = np.zeros(len(sel))
        last_tok = -1; free_at = -np.inf
        for q in o.tolist():
            t = tok[q]
            if t != last_tok: last_tok = t; free_at = -np.inf
            if st[q] < free_at: continue
            armed[q] = True
            if valid[q]: aend[q] = ft[q]; free_at = xt[q] + MARGIN
            else: aend[q] = en[q]; free_at = en[q]
        slots = np.where(armed, np.maximum(np.ceil(np.maximum(aend - st, 0.0) / SMS), 1.0), 0.0)
        rows[r] = dict(has=has, valid=valid, ft=ft, fx=np.where(has, D["f_x"][np.maximum(fr, 0)], -1), fm=np.where(has, D["f_m"][np.maximum(fr, 0)], -1),
                       sin=sin, off=off, pn=pn, armed=armed, aend=aend, slots=slots, xt=xt)
    by_tok = collections.defaultdict(list)
    for q, w in enumerate(sel.tolist()): by_tok[int(D["w_tok"][w])].append(q)
    # every T2 trigger of htype 3 (any holding %): the near-misses below 5% must NOT arm
    ht3 = T2all[f[T2all, FI["htype"]] == 3]
    ht3_tok = collections.defaultdict(list)
    for w in ht3.tolist(): ht3_tok[int(D["w_tok"][w])].append((int(D["w_j"][w]), float(f[w, FI["hpct"]])))
    return D, d, sel, st, en, rows, by_tok, ht3_tok

def read_bucket(arg):
    day, b, mints = arg
    out = {m: [] for m in mints}; seen = set()
    for dd in PHA[day]:
        for fn in sorted(glob.glob(f"{dd}/b{b:03d}/*.jsonl.gz")):
            try:
                for line in gzip.open(fn, "rt"):
                    if line[2] != "T": continue
                    e_ = line.index('"', 6); m = line[6:e_]
                    if m not in out: continue
                    r = json.loads(line)
                    if r[12] or (r[5], r[13]) in seen: continue
                    seen.add((r[5], r[13]))
                    out[m].append((r[2], r[3], r[13], r[5], r[14], r[15] == 1, r[16], r[17], r[18], r[19], r[22], r[23]))
            except (EOFError, OSError, zlib.error, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t[0], t[1], t[2]))
    return day, b, out

def token_record(day, t, rows_raw, lau, D, d, sel, st, en, R, wins, ht3):
    """one token's export (None + reason when the rebuilt tape does not match the day array)"""
    M = d["meta"][t]; o = int(d["off"][t]); n = int(d["cnt"][t]); mint = M["m"]
    if len(rows_raw) != n: return None, f"rows {len(rows_raw)} vs {n}"
    for q, r in enumerate(rows_raw):
        if (r[0], r[1], int(r[5]), float(r[6]), float(r[7]), float(r[8]), float(r[9]), zlib.crc32(r[4].encode())) != \
           (int(d["s"][o + q]), int(d["i"][o + q]), int(d["buy"][o + q]), float(d["sol"][o + q]), float(d["tokn"][o + q]),
            float(d["vsol"][o + q]), float(d["vtok"][o + q]), int(d["uid"][o + q])):
            return None, f"row {q} differs"
        a = r[0] * SMS + r[1] / max(400, r[1] + 1) * SMS
        if a != float(d["arr"][o + q]): return None, f"arrival clock differs at row {q} (slot-size table?)"
        fr = np.float32(((r[10] or 95) + (r[11] or 30)) / 1e4)
        if fr != d["fr"][o + q]: return None, f"fee rate differs at row {q}"
        sk = np.float32(slack(r[3]) if r[5] else 0.0)
        if sk != d["slack"][o + q]: return None, f"slack differs at row {q}"
    c = lau.get(mint)
    if c is None or c["slot"] != M["S0"]: return None, "launch record missing / slot differs"
    cre = c.get("creator") or c.get("user"); sig_u = c.get("user")
    if (cre or None) != M.get("creator"): return None, "creator differs"
    ins = {r[4] for r in rows_raw if r[0] == M["S0"] and r[5]} - {cre, sig_u}
    for q, r in enumerate(rows_raw):
        want = 1 if r[4] in (cre, sig_u) else (2 if r[4] in ins else None)
        if want is not None and int(d["wt"][o + q]) != want: return None, f"wallet type differs at row {q}"
        if want is None and int(d["wt"][o + q]) in (1, 2): return None, f"wallet type differs at row {q}"
    users = []; uix = {}
    for r in rows_raw:
        if r[4] not in uix: uix[r[4]] = len(users); users.append(r[4])
    trades = [[r[0], r[1], r[2], r[3], uix[r[4]], 1 if r[5] else 0, r[6], r[7], r[8], r[9], r[10], r[11]] for r in rows_raw]
    W = []
    for q in wins:
        w = int(sel[q]); j = int(D["w_j"][w]) - o
        rec = {"j": j, "st": repr(float(st[q])), "en": repr(float(en[q])), "hpct": repr(float(D["w_f"][w, E.FI["hpct"]])), "rows": {}}
        for r in ROWS:
            X = R[r]
            fill = None
            if X["has"][q]:
                x = int(X["fx"][q]) - o; m = int(X["fm"][q]) - o
                fill = {"x": x, "m": m, "a_land": repr(float(d["arr"][o + x]) + DFIX[r]), "ft": repr(float(X["ft"][q])), "valid": bool(X["valid"][q]),
                        "s_in": int(X["sin"][q]), "off": int(X["off"][q]), "pnl": repr(float(X["pn"][q])), "xt": repr(float(X["xt"][q]))}
            rec["rows"][r] = {"armed": bool(X["armed"][q]), "fill": fill, "aend": repr(float(X["aend"][q])), "slots": int(X["slots"][q])}
        W.append(rec)
    near = [{"j": j - o, "hpct": repr(h)} for j, h in ht3 if h < CFG["hpct_min"]]
    return {"mint": mint, "day": day, "launch": {"slot": c["slot"], "idx": c.get("idx"), "creator": c.get("creator"), "user": c.get("user"), "sig": c.get("sig")},
            "users": users, "trades": trades, "windows": W, "ht3_below": near}, None

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = None
    if "--full" in sys.argv:
        k = sys.argv.index("--full"); full = (sys.argv[k + 1], sys.argv[k + 2]); args = [a for a in args if a not in full]
    NTOK = int(args[0]) if args else 150; PROCS = int(args[1]) if len(args) > 1 else 5
    t0 = time.time(); rng = np.random.default_rng(20261025)
    out_tokens = []; stats = collections.Counter(); s_ends = {}
    days = (full[0],) if full else ("R4", "R3")
    for day in days:
        D, d, sel, st, en, R, by_tok, ht3_tok = study_events(day)
        Mt = d["meta"]; s_end = int(d["s"].max()); s_ends[day] = s_end
        lau = {}
        for l in open(f"/home/moiz/sniper-data/collect/{C.RUNDIR[day]}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            if not c.get("err") and c.get("mint"): lau[c["mint"]] = c
        cnt = d["cnt"]; off = d["off"]
        last_s = np.array([int(d["s"][off[t] + cnt[t] - 1]) if cnt[t] else 0 for t in range(len(Mt))])
        if full:
            pick = [t for t in range(len(Mt)) if cnt[t] >= 1]
            print(f"{day}: FULL export of {len(pick)} tokens, {int(cnt[pick].sum())} trades", flush=True)
        else:
            bks = set(rng.choice(256, NBK[day], replace=False).tolist())
            cand = [t for t in range(len(Mt)) if zlib.crc32(Mt[t]["m"].encode()) % 256 in bks and 5 <= cnt[t] <= MAXTR and last_s[t] <= s_end - 400]
            def grp(t):
                ws = by_tok.get(t, [])
                if len(ws) >= 2: return "A_multi"
                if len(ws) == 1:
                    q = ws[0]
                    if any(R[r]["valid"][q] for r in ROWS): return "B_fill"
                    return "C_nofill"
                if any(h < CFG["hpct_min"] for _, h in ht3_tok.get(t, [])): return "D_below5"
                return "E_other"
            G = collections.defaultdict(list)
            for t in cand: G[grp(t)].append(t)
            # rare cases first: rows that arm differently, hits that are late / untradeable, whale-sold windows
            def special(t):
                for q in by_tok.get(t, []):
                    ar = [bool(R[r]["armed"][q]) for r in ROWS]
                    if len(set(ar)) > 1: return True
                    if any(R[r]["has"][q] and not R[r]["valid"][q] for r in ROWS): return True
                return False
            share = {"A_multi": 0.40, "B_fill": 0.28, "C_nofill": 0.10, "D_below5": 0.12, "E_other": 0.10}
            pick = []
            sp = [t for t in cand if special(t)]; rng.shuffle(sp); pick += sp[:max(8, NTOK // 8)]
            for g, sh in share.items():
                L = [t for t in G[g] if t not in pick]; rng.shuffle(L); pick += L[:int(NTOK * sh)]
            pick = sorted(set(pick))
            print(f"{day}: {len(cand)} candidate tokens in {len(bks)} buckets ({ {g: len(v) for g, v in sorted(G.items())} }, special {len(sp)}) -> {len(pick)} tokens, "
                  f"trades {int(cnt[pick].sum())}", flush=True)
        byb = collections.defaultdict(list)
        for t in pick: byb[zlib.crc32(Mt[t]["m"].encode()) % 256].append(Mt[t]["m"])
        tr = {}
        with Pool(PROCS) as p:
            for k, (_, b, o_) in enumerate(p.imap_unordered(read_bucket, [(day, b, ms) for b, ms in byb.items()]), 1):
                tr.update(o_)
                if k % 32 == 0: print(f"  {k}/{len(byb)} buckets read, {time.time() - t0:.0f} s", flush=True)
        for t in pick:
            rec, why = token_record(day, t, tr.get(Mt[t]["m"], []), lau, D, d, sel, st, en, R, by_tok.get(t, []), ht3_tok.get(t, []))
            if rec is None:
                stats[f"{day} skipped: {why.split(' at ')[0].split(' row ')[0]}"] += 1
                if stats[f"{day} skipped printed"] < 5: stats[f"{day} skipped printed"] += 1; print(f"  {day} {Mt[t]['m']}: {why}: skipped", flush=True)
                continue
            out_tokens.append(rec); stats[f"{day} tokens"] += 1; stats[f"{day} windows"] += len(rec["windows"])
            for w in rec["windows"]:
                for r in ROWS:
                    x = w["rows"][r]; stats[f"{day} {r} armed"] += x["armed"]; stats[f"{day} {r} fills"] += bool(x["armed"] and x["fill"] and x["fill"]["valid"])
    # p1_build.slack on some real signatures (the Rust table + hash must give the same float32 values)
    slack_check = [[r[3], repr(float(np.float32(slack(r[3]))))] for x in out_tokens[:40] for r in x["trades"][:5]]
    note = ("s_end: the day's last tape slot (the study opens no window in its last 300 slots). trades: [slot, tx index, event index, sig, user index (users[]), buy 0/1, sol, tok, vsol, vtok, fee bps, creator fee bps] in chain order "
            "(raw TradeEvent fields; 0 bps = absent). windows: the study's T2 windows of the chosen config (ps6 'T2|c' filter) with j = trigger trade index, "
            "st / en (window start / end on the block-position clock, float64 repr), hpct (float32 repr), and per queue row a / b / c: armed (ps5 "
            "per-token rule over all windows), fill (first hit of ps4: x = crossing trade, m = last trade ahead of us, a_land, ft = ps5 fill time, valid "
            "= ft < en, s_in, off = exit offset slots, pnl = gross SOL float32 for 0.55 SOL / c2_tp10_sl20, xt = our sell time), aend, slots "
            "(armed slots charged). ht3_below: htype-3 triggers below 5% of supply (must not arm).")
    res = {"made": time.strftime("%Y-%m-%d %H:%M PKT", time.gmtime(time.time() + 5 * 3600)), "cfg": CFG, "rows": {r: DFIX[r] for r in ROWS}, "note": note,
           "s_end": s_ends, "slack_check": slack_check, "tokens": out_tokens}
    path = full[1] if full else f"{REPO}/testdata/presend_parity.json"
    json.dump(res, open(path, "w"), separators=(",", ":"))
    print(f"parity: {len(out_tokens)} tokens, {sum(len(x['trades']) for x in out_tokens)} trades, {dict(sorted(stats.items()))}, "
          f"{os.path.getsize(path) / 1e6:.1f} MB -> {path}, {time.time() - t0:.0f} s", flush=True)
