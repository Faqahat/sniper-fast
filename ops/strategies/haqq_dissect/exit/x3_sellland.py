#!/usr/bin/env python3
"""EXIT step 3 (read-only): OUR measured sell landing, from the live records (ours_pos.pkl) joined with the tape (MEASURED).
Per live position: our buy rows and sell rows on the tape (wallet, slot, idx), chain clock of each.
 * reactive exits (take-profit / stop-loss): the trigger = the first outside trade after our buy at which the engine's value
   crosses the threshold (pre-send: SOL out x (1 - fee) / spend; regular: (SOL out x (1 - fee) - 0.0008) / (spend + 0.0008)),
   recomputed on the tape; delay = chain clock of our first sell landing - chain clock of the trigger (ms) and rows between.
 * time-limit exits: decision slot D (exit.slot); first sell landing slot - D, and ms after the start of slot D.
 * both: local rx delay = sell rx time - exit decision time (engine clock, ms).
Out: haqq_dissect/exit/sellland.pkl (per position rows), x3.txt"""
import pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
import dv8lib as L
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def q(v, ps=(10, 25, 50, 75, 90)):
    v = np.array([x for x in v if x is not None and x == x], float)
    return " / ".join(f"{np.percentile(v, p):.0f}" for p in ps) + f" (n={len(v)})" if len(v) else "-"


def main():
    R, MI, span, CC = X.tape()
    wid = {"FRA": MI["who"]["FRA"], "AMS": MI["who"]["AMS"]}
    ids, idm = L.ids_map()
    POS = pickle.load(open(f"{X.OUT}/ours_pos.pkl", "rb"))
    rows = []
    for p in POS:
        m = idm.get(p["mint"])
        if m is None or m not in span: continue
        M = X.Mint(m); w = wid[p["srv"]]
        mine = M.us == w
        key = M.sl * 100000 + M.ix
        def find(s, i):
            k = np.flatnonzero((key == s * 100000 + i) & mine)
            return int(k[0]) if len(k) else None
        bk = [find(b[0], b[1]) for b in p["buys"]]
        # sells = our wallet's sell rows after our last buy and before our next buy on the mint (<= 400 slots); the record's sell
        # list can hold a later position's sells on the same mint
        bkk = [k for k in (find(b[0], b[1]) for b in p["buys"]) if k is not None]
        sk = []
        if bkk:
            lb = max(bkk); nxt = np.flatnonzero(mine & M.bu & (np.arange(M.n) > lb))
            hi = int(nxt[0]) if len(nxt) else M.n
            sk = [int(k) for k in np.flatnonzero(mine & ~M.bu) if lb < k < hi and M.sl[k] <= M.sl[lb] + 400]
        r = dict(kind=p["kind"], run=p["run"], srv=p["srv"], mint=m, why=p["exit"][0], dslot=p["exit"][1], t_dec=p["exit"][2], val=p["exit"][3],
                 bk=bk, sk=sk, spend=p["spend"], hold=p["hold"], tp=p["tp"], sl=p["sl"], buys=p["buys"], sells=p["sells"], curve_pnl=p["curve_pnl"])
        if any(k is None for k in bk) or not bk:
            r["miss"] = "buy"; rows.append(r); continue
        b0 = min(bk); r["b_cc"] = float(M.cc[b0]); r["b_slot"] = int(M.sl[b0]); r["bt"] = int(M.bt[b0]); r["day"] = X.day_of(int(M.bt[b0]))
        tok = sum(float(M.tk[k]) for k in bk); r["tok"] = tok; r["cost"] = sum(float(M.so[k] * (1 + M.fee[k])) for k in bk)
        if not sk or any(k is None for k in sk):
            r["miss"] = "sell"; rows.append(r); continue
        s0 = min(sk); r["s_cc"] = float(M.cc[s0]); r["s_slot"] = int(M.sl[s0]); r["s_k"] = s0
        r["got"] = sum(float(M.so[k] * (1 - M.fee[k])) for k in sk)
        r["realized"] = r["got"] - r["cost"]
        if p["sells"][0][2] and r["t_dec"]: r["rx_ms"] = (p["sells"][0][2] - r["t_dec"]) / 1e6
        if r["why"] in ("take-profit", "stop-loss"):
            last_b = max(bk); spend = p["spend"] * 1e9 if p["spend"] else None
            trig = None
            for j in range(last_b + 1, s0):
                if M.us[j] == w: continue
                so = X.sell_value(M.vs[j], M.vt[j], tok, M.fee[j])
                if p["kind"] == "ps": v = so / p["spend"]
                else: v = (so - 0.0008) / (p["spend"] + 0.0008)
                if (p["tp"] and p["tp"] < 9 and v >= 1 + p["tp"]) or (p["sl"] and v <= 1 - p["sl"]):
                    trig = j; break
            if trig is not None:
                r["trig_k"] = trig; r["trig_slot_ok"] = int(M.sl[trig]) == r["dslot"]
                r["react_ms"] = float(M.cc[s0] - M.cc[trig]); r["react_rows"] = int(s0 - trig - 1)
                r["react_slots"] = int(M.sl[s0] - M.sl[trig])
        else:
            r["timer_slots"] = int(M.sl[s0] - r["dslot"]) if r["dslot"] else None
            r["timer_ms"] = float(M.cc[s0] - r["dslot"] * X.SMS) if r["dslot"] else None
            r["held_slots"] = int(M.sl[s0] - r["b_slot"])
            r["idx_frac"] = float((M.cc[s0] - M.sl[s0] * X.SMS) / X.SMS)
        rows.append(r)
    pickle.dump(rows, open(f"{X.OUT}/sellland.pkl", "wb"))
    P("# Our live sells: decision -> landing (MEASURED, all live runs AMS r9-r33 + FRA r1-r26)")
    P(f"positions {len(rows)}; missing buy on tape {sum(r.get('miss') == 'buy' for r in rows)}, missing sell {sum(r.get('miss') == 'sell' for r in rows)}")
    for kind in ("ps", "reg"):
        v = [r for r in rows if r["kind"] == kind and "react_ms" in r]
        P(f"\n## {kind}: reactive exits (TP / SL), trigger trade found on tape: {len(v)} of {sum(r['kind'] == kind and r['why'] in ('take-profit', 'stop-loss') for r in rows)}; trigger slot = exit-event slot {sum(r['trig_slot_ok'] for r in v)}")
        if v:
            P(f"- chain-clock ms trigger -> our first sell landing p10/25/50/75/90: {q([r['react_ms'] for r in v])}")
            P(f"- outside trades between trigger and our sell p10/25/50/75/90: {q([r['react_rows'] for r in v])}")
            P(f"- slots trigger -> sell: " + ", ".join(f"{k}: {c}" for k, c in sorted(collections.Counter(min(r['react_slots'], 4) for r in v).items())))
            P(f"- local rx ms decision -> sell seen: {q([r.get('rx_ms') for r in v])}")
        v = [r for r in rows if r["kind"] == kind and "timer_ms" in r and r["timer_ms"] is not None]
        P(f"\n## {kind}: time-limit exits on tape: {len(v)}; hold configs {dict(collections.Counter(r['hold'] for r in v))}")
        if v:
            P(f"- sell slot - decision slot: " + ", ".join(f"{k}: {c}" for k, c in sorted(collections.Counter(min(r['timer_slots'], 4) for r in v).items())))
            P(f"- sell slot - buy slot: " + ", ".join(f"{k}: {c}" for k, c in sorted(collections.Counter(min(r['held_slots'], 25) for r in v).items())))
            P(f"- ms after the decision slot's start p10/25/50/75/90: {q([r['timer_ms'] for r in v])}")
            P(f"- position in the landing slot (idx / block size) p10/25/50/75/90 (x100): {q([100 * r['idx_frac'] for r in v])}")
            P(f"- local rx ms decision -> sell seen: {q([r.get('rx_ms') for r in v])}")
    open(f"{X.OUT}/x3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
