# READ-ONLY offline. Task 5: simulate our entry at several landing positions / sizes on the real trade tapes,
# replaying every later trade on the curve with our buy inserted (others' buy SOL and sell tokens held fixed).
# Output: /root/comp/sim_<SET>.json  (per launch x scenario x size x exit -> pnl SOL)
import sys, json, math, collections
sys.path.insert(0, "/root/comp")
from lib import *

SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
SIZES = [0.25, 0.5, 1.0, 2.0, 3.0]
SELL_FEE = 0.002          # sell-side priority/landing, SOL (assumption)
SLOTS_PER_S = 1 / SLOT_S  # 2.5


def exits_def():
    E = {}
    for T in (1, 2, 3, 5, 10, 20, 30):
        E[f"T{T}"] = ("time", T)
    for X in (1.2, 1.5, 2.0):
        for T in (10, 30):
            E[f"TP{X}/T{T}"] = ("tp", X, T)
    for Y in (0.15, 0.25, 0.35):
        E[f"TR{int(Y*100)}/T30"] = ("trail", Y, 30)
        E[f"TPA1.2+TR{int(Y*100)}/T30"] = ("trail_act", 1.2, Y, 30)
    for Z in (0.5, 1.0, 2.0):
        E[f"BIGSELL{Z}/T30"] = ("bigsell", Z, 30)
    E["BUNDLEDUMP/T30"] = ("bundledump", 30)
    E["BUNDLEDUMP|BIGSELL1/T30"] = ("bd_or_big", 1.0, 30)
    E["HALF@1.5+TR25/T30"] = ("partial", 1.5, 0.25, 30)
    E["HALF@1.3+TR20/T20"] = ("partial", 1.3, 0.20, 20)
    return E


EXITS = exits_def()


def replay(ev, k0, x_sol, fee_rate, eslot):
    """insert our buy of x_sol (into curve) before ev[k0]; return per-slot path after entry.
    path: list of (slot, V_end, T_end, maxbig_other_sell_sol, bundle_sell_sol) for each slot from entry slot to end."""
    if k0 < len(ev):
        V, T = pre_state(ev[k0])
    else:
        V, T = ev[-1]["vsol"], ev[-1]["vtok"]
    x = x_sol * 1e9
    q = T * x / (V + x)
    V += x; T -= q
    fill = x / q
    path = collections.OrderedDict()
    path[eslot] = [V, T, 0.0, 0.0]
    for e in ev[k0:]:
        if e["buy"]:
            dt = T * e["sol"] / (V + e["sol"]); V += e["sol"]; T -= dt
        else:
            so = V * e["tok"] / (T + e["tok"]); V -= so; T += e["tok"]
        s = e["slot"]
        if s not in path:
            path[s] = [V, T, 0.0, 0.0]
        p = path[s]
        p[0], p[1] = V, T
        if not e["buy"]:
            if e["_bundle"]:
                p[3] += e["sol"] / 1e9
            else:
                p[2] = max(p[2], e["sol"] / 1e9)
    return q, fill, path


def sell_value(V, T, q, fee_rate):
    return V * q / (T + q) * (1 - fee_rate) / 1e9


def run_exits(eslot, q, fill, path, fee_rate, last_slot):
    """returns dict exit -> (gross SOL proceeds, hold slots)"""
    slots = list(path.keys())
    st = {s: path[s] for s in slots}
    # precompute per-slot carried states from eslot..last_slot
    carried = {}
    cur = None; it = iter(slots); nxt = next(it, None)
    for s in range(eslot, last_slot + 1):
        while nxt is not None and nxt <= s:
            cur = st[nxt]; nxt = next(it, None)
        carried[s] = cur
    def exec_at(dec_slot):  # sell lands at end of dec_slot+1
        s = min(dec_slot + 1, last_slot)
        V, T = carried[s][0], carried[s][1]
        return V, T
    out = {}
    for name, d in EXITS.items():
        kind = d[0]
        Tstop = d[-1]
        stop_slot = min(eslot + max(1, math.ceil(Tstop * SLOTS_PER_S)) - 1, last_slot - 1)
        sold = None
        if kind == "time":
            sold = [(1.0, stop_slot)]
        elif kind in ("tp", "trail", "trail_act", "bigsell", "bundledump", "bd_or_big"):
            peak = 0; armed = kind != "trail_act"
            for s in range(eslot, stop_slot + 1):
                c = carried[s]
                if c is None: continue
                px = c[0] / c[1]; r = px / fill
                peak = max(peak, px)
                hit = False
                if kind == "tp": hit = r >= d[1]
                elif kind == "trail": hit = px <= peak * (1 - d[1])
                elif kind == "trail_act":
                    if r >= d[1]: armed = True
                    hit = armed and px <= peak * (1 - d[2])
                elif kind == "bigsell": hit = s in st and st[s][2] >= d[1]
                elif kind == "bundledump": hit = s in st and st[s][3] >= 0.05
                elif kind == "bd_or_big": hit = s in st and (st[s][3] >= 0.05 or st[s][2] >= d[1])
                if hit:
                    sold = [(1.0, s)]; break
            if sold is None: sold = [(1.0, stop_slot)]
        elif kind == "partial":
            X, Y = d[1], d[2]
            peak = 0; half = None; rest = None
            for s in range(eslot, stop_slot + 1):
                c = carried[s]
                if c is None: continue
                px = c[0] / c[1]; r = px / fill; peak = max(peak, px)
                if half is None and r >= X: half = s
                if half is not None and s > half and px <= peak * (1 - Y): rest = s; break
            if half is None: sold = [(1.0, stop_slot)]
            else: sold = [(0.5, half), (0.5, rest if rest is not None else stop_slot)]
        # execute sequentially (the first partial sell moves the curve for the second)
        proc = 0.0; qq = q; extra = (0.0, 0.0); nsell = 0; hold = 0
        for frac, ds in sold:
            V, T = exec_at(ds)
            V -= extra[0]; T += extra[1]   # our earlier partial sell still in the curve
            qs = q * frac
            so = V * qs / (T + qs)
            proc += so * (1 - fee_rate) / 1e9
            extra = (extra[0] + so, extra[1] + qs)
            nsell += 1; hold = ds + 1 - eslot
        out[name] = (proc, hold, nsell)
    return out


def main():
    res = []
    nl = 0
    for r in load(f"/root/comp/tapes_{SET}.jsonl"):
        ev, fb = order_launch(r)
        if len(ev) < 3: continue
        S = r["slot"]; bw = bundle_set(r)
        for e in ev: e["_bundle"] = e["user"] in bw
        fr = [(e["fbps"] + e["cbps"]) / 1e4 for e in ev if e["fbps"] is not None]
        fee_rate = sorted(fr)[len(fr) // 2] if fr else 0.0125
        last_slot = S + 300 if not r.get("capped") else max(t["slot"] for t in r["txs"])
        # entry indices
        sc = {}
        def idx_before_d(D):
            k = 0
            while k < len(ev) and ev[k]["slot"] == S and (ev[k]["d"] is not None and ev[k]["d"] < D):
                k += 1
            # skip S events with unknown d? (they are rare) keep k
            return k
        sc["d8"] = idx_before_d(8)
        sc["d25"] = idx_before_d(25)
        sc["d100"] = idx_before_d(100)
        k = 0
        while k < len(ev) and ev[k]["slot"] == S: k += 1
        sc["s1"] = k
        fo = next((i for i, e in enumerate(ev) if e["buy"] and not e["_bundle"]), len(ev))
        sc["firstout"] = fo
        es = {"d8": S, "d25": S, "d100": S, "s1": S + 1, "firstout": ev[fo]["slot"] if fo < len(ev) else S}
        fo_d = ev[fo]["d"] if fo < len(ev) and ev[fo]["slot"] == S else None
        fo_slot = ev[fo]["slot"] - S if fo < len(ev) else None
        gv, gt = post_bundle_state(r)
        row = dict(mint=r["mint"], S=S, bt=r["bt"], dev=r["dev"] / 1e9, gsol=r["gsol"] / 1e9, fee_rate=fee_rate, fo_d=fo_d, fo_slot=fo_slot,
                   nev=len(ev), r={})
        # reference price path (no our trade): peak multiple vs post-bundle within 60 s
        pb = gv / gt
        pk = max([e["vsol"] / e["vtok"] for e in ev if e["slot"] - S <= 150] or [pb])
        row["peak60_vs_pb"] = pk / pb
        for sname, k0 in sc.items():
            for x in SIZES:
                xs = x / (1 + fee_rate)  # SOL into curve so that the total buy spend = x
                eslot = es[sname]
                q, fill, path = replay(ev, k0, xs, fee_rate, eslot)
                ex = run_exits(eslot, q, fill, path, fee_rate, last_slot)
                pre_px = (pre_state(ev[k0])[0] / pre_state(ev[k0])[1]) if k0 < len(ev) else ev[-1]["vsol"] / ev[-1]["vtok"]
                row["r"][f"{sname}|{x}"] = dict(entry_vs_pb=pre_px / pb, fill_vs_pb=fill / pb, ex={n: [round(v[0], 6), v[1], v[2]] for n, v in ex.items()})
        res.append(row); nl += 1
    json.dump(res, open(f"/root/comp/sim_{SET}.json", "w"))
    print("launches", nl)


if __name__ == "__main__":
    main()
