#!/usr/bin/env python3
"""dip46 PROBE / FILTER A/B check (offline; reads a run's dip log, never writes it).

(1) PROBES: every presend_live_probe_land of the run. A probe is the try a live filter blocked, signed so it can never fill; where it
    LANDED (slot, idx) is measured. Would the real try have filled there? -> the curve just before that position:
      * engine: the record's own `pre` (the executed feed's last trade of the mint before the landing) and `would_fill`
      * --tape (default when the chain tape covers the run): the collector's chain tape (harness/hlib.tape_df, read-only), recomputed
    The real try fills iff pump's tokens out at that state >= the try's real min_out (`would_min_out`, the 0.88x limit's tokens).
    Per window only its FIRST would-fill landing counts (a real window disarms on its fill). That fill is priced with the r82 exit:
    ms timer 2350 ms (+ 40 ms the engine sees the fill late + the measured ms-exit lag), TP / SL +-20% on the exact-curve value at every
    outside trade (+ the measured reaction lag), exact curve math with pump's 1.25% fee, sell fixed cost 1,805,000 lamports, buy cost =
    the probe's own landed fee + the tip the real try would have paid. The one-position rule and our own impact on followers are NOT
    modelled (a would-fill may have overlapped a real position).
(2) FILTER A/B: per A/B'd filter, the windows of each arm (presend_live_arm "ab46") and their REAL realized P&L (presend_live_realized
    joined on w); the bypass arm's windows the filter would have blocked are listed apart (their P&L = what the filter costs or saves).

usage: probe_check.py DIP_LOG.jsonl [--no-tape] [--size SOL]    (SOL: scale the P&L to this size per fill; default the run's)
"""
import sys, os, json, bisect, collections, math

K = 30_000_000_000 * 1_073_000_000_000_000      # pump curve V*T (virtual reserves)
FR = 0.0125
SMS = 214.0                                     # ms per slot of the block-position clock (harness convention)
EXIT_MS, TP, SL = 2350.0, 0.20, 0.20            # r82's exit
SEE_MS = 40.0                                   # the engine sees its fill ~40 ms late (its ms timer starts then)
MS_LAG, REACT_LAG = 73.8, 66.2                  # measured medians (exit study lags.pkl: ms-timer exits, TP/SL exits)
SELL_FIX = 1_805_000
HARN = "/home/it/sniper-studies/sniper-plan1110/harness"


def buy_tokens(T, spend, fr=FR):
    V = K / T
    x = spend / (1.0 + fr)
    return T * x / (V + x)


def proceeds(T, tok):
    """sell proceeds (after the pump fee) of tok tokens at CLEAN reserve T (the curve as if we never bought: ours put back)"""
    if T - tok <= 0:
        return 0.0
    return K * tok / ((T - tok) * T) * (1.0 - FR)


def load(path):
    R = collections.defaultdict(list)
    keep = ("presend_live_probe", "presend_live_filter_ab", "presend_live_arm", "presend_live_fill", "presend_live_realized", "presend_live_dip46", "run_start")
    with open(path) as f:
        for line in f:
            if '"presend_live_' not in line and '"run_start"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ev = r.get("ev", "")
            if ev.startswith(keep):
                R[ev].append(r)
    return R


class Tape:
    """per mint: [(s, i, vtok)] from the chain tape (hlib, read-only), sorted; maxi per slot for the block clock"""
    def __init__(self, t0, t1, mints):
        sys.path.insert(0, HARN)
        import hlib                                       # noqa: E402
        df = hlib.tape_df(t0, t1)
        df = df[df["mint"].isin(mints)]
        self.m = collections.defaultdict(list)
        self.maxi = collections.defaultdict(int)
        for s, i, mint, vtok in zip(df["s"].values, df["i"].values, df["mint"].values, df["vtok"].values):
            if vtok > 0:
                self.m[mint].append((int(s), int(i), float(vtok)))
            self.maxi[int(s)] = max(self.maxi[int(s)], int(i))
        for v in self.m.values():
            v.sort()
        self.ok = len(df) > 0

    def tau(self, s, i):
        return s * SMS + (i + 0.5) / (self.maxi.get(s, 600) + 1.0) * SMS

    def pre(self, mint, s, i):
        v = self.m.get(mint) or []
        k = bisect.bisect_left(v, (s, i, -1.0))
        return v[k - 1] if k > 0 else None

    def after(self, mint, s, i):
        v = self.m.get(mint) or []
        k = bisect.bisect_right(v, (s, i, float("inf")))
        return v[k:]


def price_exit(tp, mint, s, i, T0, tok, spend):
    """the r82 exit on a would-fill at (s, i), entry reserve T0 -> (sell proceeds lamports, why)"""
    f_tau = tp.tau(s, i)
    due = f_tau + SEE_MS + EXIT_MS
    path = tp.after(mint, s, i)
    taus = [tp.tau(a, b) for a, b, _ in path]
    for (a, b, T), t in zip(path, taus):
        if t >= due:
            break
        v = proceeds(T, tok) / spend
        if v >= 1 + TP or v <= 1 - SL:
            ts = t + REACT_LAG
            k = bisect.bisect_left(taus, ts)
            Tx = path[k - 1][2] if k > 0 else T0
            return proceeds(Tx, tok), "take-profit" if v >= 1 + TP else "stop-loss"
    ts = due + MS_LAG
    k = bisect.bisect_left(taus, ts)
    Tx = path[k - 1][2] if k > 0 else T0
    return proceeds(Tx, tok), "time-ms"


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    use_tape = "--no-tape" not in sys.argv
    size = float(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else None
    R = load(path)
    sends = {r["sig"]: r for r in R["presend_live_probe"]}
    lands = R["presend_live_probe_land"]
    print(f"probe sends {len(sends)}, landings {len(lands)} ({sum(1 for l in lands if l['res'] == 'unseen')} unseen), probe windows {len(R['presend_live_probe_arm'])}")
    fees = sum(l.get("fee", 0) for l in lands)
    print(f"probe fees {fees / 1e9:.6f} SOL")
    tp = None
    landed = [l for l in lands if l["res"] != "unseen" and l.get("idx") is not None]
    if use_tape and landed:
        ts = [l["t"] / 1e9 for l in landed if l.get("t")]
        try:
            tp = Tape(min(ts) - 60, max(ts) + 600, {l["mint"] for l in landed})
            if not tp.ok:
                tp = None
        except Exception as e:                            # no tape here: the engine's own pre-state only
            print("chain tape not available:", e)
            tp = None
    print("would-fill source:", "chain tape (hlib) + exit priced" if tp else "engine record only (no exit pricing)")

    # ---- (1) probes: per window its first would-fill landing --------------------------------------------------------------
    by_w = collections.defaultdict(list)
    for l in landed:
        by_w[(l["w"], l["filter"])].append(l)
    rows = collections.defaultdict(lambda: {"probes": 0, "windows": 0, "would": 0, "eng_would": 0, "agree": 0, "win": 0, "lose": 0, "net": 0.0, "net1": 0.0, "why": collections.Counter()})
    for l in lands:
        rows[l["filter"]]["probes"] += 1
    detail = []
    for (w, flt), L in by_w.items():
        L.sort(key=lambda x: (x["slot"], x["idx"]))
        row = rows[flt]
        row["windows"] += 1
        first = None
        for l in L:
            eng = bool(l.get("would_fill"))
            if tp:
                pre = tp.pre(l["mint"], l["slot"], l["idx"])
                T0 = pre[2] if pre else float(l["pre"]["vtok"]) if l.get("pre") else None
                if T0 is None:
                    continue
                tok = buy_tokens(T0, l["spend"])
                would = tok >= l["would_min_out"]
                row["agree"] += int(would == eng)
            else:
                would, T0, tok = eng, (float(l["pre"]["vtok"]) if l.get("pre") else None), float(l.get("would_tokens") or 0)
            row["eng_would"] += int(eng)
            if would and first is None:
                first = (l, T0, tok)
        if first is None:
            continue
        row["would"] += 1
        l, T0, tok = first
        if not tp:
            continue
        spend = l["spend"]
        tip = (sends.get(l["sig"]) or {}).get("tip", 0)
        out, why = price_exit(tp, l["mint"], l["slot"], l["idx"], T0, tok, spend)
        pnl = (out - spend - l.get("fee", 0) - tip - SELL_FIX) / 1e9
        scale = (size * 1e9 / spend) if size else 1.0
        row["net"] += pnl
        row["net1"] += pnl * (1e9 / spend)
        row["win" if pnl > 0 else "lose"] += 1
        row["why"][why] += 1
        detail.append((flt, w, l["mint"][:8], l["slot"], l["idx"], round(pnl * scale, 4), why))
    print("\n== (1) PROBES per filter: windows probed, windows whose real try WOULD HAVE FILLED (first landing), priced with the r82 exit")
    hdr = f"{'filter':22s} {'probes':>6s} {'windows':>7s} {'would':>6s} {'eng-agree':>9s} {'win':>4s} {'lose':>4s} {'net SOL':>9s} {'net@1SOL':>9s}  exits"
    print(hdr)
    for flt, r in sorted(rows.items()):
        print(f"{flt:22s} {r['probes']:6d} {r['windows']:7d} {r['would']:6d} {r['agree']:9d} {r['win']:4d} {r['lose']:4d} {r['net']:+9.4f} {r['net1']:+9.4f}  {dict(r['why'])}")
    if detail:
        print("\nworst / best would-fills:")
        detail.sort(key=lambda x: x[5])
        for d in (detail if len(detail) <= 10 else detail[:5] + detail[-5:]):
            print("  ", d)

    # ---- (2) the filter A/B: real realized P&L by arm ---------------------------------------------------------------------
    arms = {}
    for r in R["presend_live_arm"]:
        if "ab46" in r:
            arms[r["w"]] = r["ab46"]
    for r in R["presend_live_fill"]:
        if "ab46" in r:
            a = arms.setdefault(r["w"], {"arms": {}, "would": []})
            a["arms"].update(r["ab46"].get("arms", {}))
            a["would"] = sorted(set(a.get("would", [])) | set(r["ab46"].get("would", [])))
    pnl = collections.defaultdict(float)
    for r in R["presend_live_realized"]:
        if r.get("pnl") is not None:
            pnl[r["w"]] += r["pnl"] / 1e9
    if not arms:
        print("\n== (2) FILTER A/B: no ab46-tagged window in this log")
        return
    filters = sorted({f for a in arms.values() for f in a.get("arms", {})})
    print("\n== (2) FILTER A/B: real realized P&L per arm (windows armed / with a fill / P&L SOL); bypass-would = windows the filter would have blocked")
    print(f"{'filter':16s} {'live arm':>28s} {'bypass arm':>28s} {'bypass-would':>28s}")
    rej = collections.Counter(r["filter"] + ":" + r["arm"] for r in R["presend_live_filter_ab"])
    for f in filters:
        cell = {}
        for arm in ("live", "bypass", "bwould"):
            ws = [w for w, a in arms.items() if (a["arms"].get(f) == arm if arm != "bwould" else (a["arms"].get(f) == "bypass" and f in a.get("would", [])))]
            filled = [w for w in ws if w in pnl]
            cell[arm] = f"{len(ws):5d} {len(filled):5d} {sum(pnl[w] for w in filled):+9.4f}"
        print(f"{f:16s} {cell['live']:>28s} {cell['bypass']:>28s} {cell['bwould']:>28s}")
    print("presend_live_filter_ab records:", dict(rej))


if __name__ == "__main__":
    main()
