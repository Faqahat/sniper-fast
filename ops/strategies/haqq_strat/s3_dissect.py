#!/usr/bin/env python3
"""HAQQ_STRAT step 3 (read-only): dissect haqq's last 24 h (10-26 23:15 -> 10-27 23:15 PKT) from the chain tape.
Positions = trips (zero balance -> zero), typed by the context of the FIRST buy (hs_lib.etype); adds are their own lots.
P&L = sell proceeds net of pump fees - gross buy cost - landed tx fees and tips (buys + sells) - failed tx fees (spread per buy).
Open lots at the tape end are marked at the last price x 0.9875. ATA rent is left out (reclaimed in batches).
Out: haqq_strat/s3.txt + s3.json + lots24.pkl (per-lot rows reused later)."""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_strat")
from hs_lib import *

out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    Z = load_pos(); B = Z["buys"]; LOTS = Z["lots"]; SELLS = Z["sells"]
    # sell tx cost allocation
    scost = {(s["mint"], s["slot"], s["idx"]): (s["cost"][0] / 1e9 if s["cost"] else None) for s in SELLS}
    touch = collections.Counter()
    for L in LOTS:
        for (sl, fr, px) in L["sells"]: touch[(L["mint"], sl)] += 1
    sc_by_ms = collections.defaultdict(list)
    for s in SELLS: sc_by_ms[(s["mint"], s["slot"])].append(scost[(s["mint"], s["slot"], s["idx"])])
    # failed txs (haqq) in window
    fail = []; n_land = 0
    for l in open(f"{D}/haqq_raw.jsonl"):
        d = json.loads(l)
        if not (W0 <= d["bt"] < W1): continue
        if d["err"] is not None: fail.append(d)
        else: n_land += 1
    fail_fee = sum(d["fee"] for d in fail) / 1e9
    H = [b for b in B if b["w"] == "haqq" and W0 <= b["bt"] < W1 and b["size"] > 0.05]
    probes = [b for b in B if b["w"] == "haqq" and W0 <= b["bt"] < W1 and b["size"] <= 0.05]
    nbuy_all = len(H) + len(probes)
    ff_per_buy = fail_fee / max(nbuy_all, 1)
    P(f"# haqq last 24 h: {pkt(W0)} -> {pkt(W1)} PKT")
    P(f"landed haqq txs {n_land:,}, failed {len(fail):,} ({100 * len(fail) / (n_land + len(fail)):.1f}%), failed fees {fail_fee:.3f} SOL")
    P(f"buys > 0.05 SOL: {len(H):,}; probes (0.01): {len(probes):,}")
    rows = []
    for b in H + probes:
        L = LOTS[b["lot_ix"]]
        if L["close_slot"] is None and L.get("mark") is None: continue
        sx = 0.0; ok = L["txc"] is not None
        for (sl, fr, px) in L["sells"]:
            cs_ = [c for c in sc_by_ms[(L["mint"], sl)] if c is not None]
            if cs_: sx += sum(cs_) / max(touch[(L["mint"], sl)], 1)
            else: ok = False
        gross = L["out"] + L.get("mark", 0.0) * (L["left"] / L["tok"] if L["tok"] else 0) - L["cost"]
        txc = (L["txc"] or 0.0) + sx + ff_per_buy
        hold_ms = (L["close_cc"] - b["cc"]) if L.get("close_cc") else None
        d_hold = (L["close_slot"] - b["d_slot"]) if (L["close_slot"] and b.get("d_slot")) else None
        r = dict(b=b, t=etype(b), size=b["size"], gross=gross, txc=txc, net=gross - txc, hold_ms=hold_ms, d_hold=d_hold,
                 hold_slots=(L["close_slot"] - b["slot"]) if L["close_slot"] else None, nsell=L["nsell"], open=L["close_slot"] is None,
                 ret=gross / b["size"], cost_ok=ok, probe=b["size"] <= 0.05, client=client_of(b["slot"]))
        rows.append(r)
    pickle.dump([{k: v for k, v in r.items()} for r in rows], open(f"{D}/lots24.pkl", "wb"))
    R = [r for r in rows if not r["probe"]]
    tot_net = sum(r["net"] for r in rows); tot_g = sum(r["gross"] for r in rows)
    P(f"lots {len(rows):,} (probes {sum(r['probe'] for r in rows)}), gross {tot_g:+.2f} SOL, tx costs {sum(r['txc'] for r in rows):.2f}, NET {tot_net:+.2f} SOL/24h")
    P(f"cost coverage: {100 * np.mean([r['cost_ok'] for r in rows]):.1f}% of lots have every tx cost from the raw recording")
    P(f"open at tape end (marked): {sum(r['open'] for r in rows)}")
    # ---------------- by type
    P("\n## 1. Strategy types (lots; type from the context of each buy; MEASURED)")
    P("| type | lots/day | SOL in | gross | tx costs | net SOL/day | net per SOL | win | median size | hold p10/p50/p90 s | holds > 60 s |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    T = collections.defaultdict(list)
    for r in R: T[r["t"]].append(r)
    T["probe 0.01"] = [r for r in rows if r["probe"]]
    J = {}
    for t in ("DIP", "DIP_LATE", "LAUNCH", "MOMO", "DEAD", "OTHER", "ADD", "probe 0.01"):
        v = T.get(t, [])
        if not v: continue
        sol = sum(r["size"] for r in v); g = sum(r["gross"] for r in v); c = sum(r["txc"] for r in v); n = sum(r["net"] for r in v)
        lo, hi = boot([r["net"] for r in v])
        hs = [r["hold_ms"] / 1000 for r in v if r["hold_ms"] is not None]
        P(f"| {t} | {len(v):,} | {sol:.0f} | {g:+.2f} | {c:.2f} | **{n:+.2f}** [{lo:+.1f}..{hi:+.1f}] | {100 * n / sol:+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% | "
          f"{np.median([r['size'] for r in v]):.2f} | {pct(hs)} | {100 * np.mean([h > 60 for h in hs]):.0f}% |")
        J[t] = dict(n=len(v), sol=sol, gross=g, txc=c, net=n, lo=lo, hi=hi)
    # DIP split by age / drop / seller / curve
    dips = T["DIP"] + T["ADD"]
    dd = [r for r in R if r["t"] in ("DIP",)]
    P("\n### DIP lots by token age at the buy (MEASURED)")
    P("| age | lots | net SOL | per SOL | win |"); P("|---|---|---|---|---|")
    for lo_, hi_, nm in ((0, 10, "< 2 s"), (10, 25, "2-5 s"), (25, 150, "5-30 s"), (150, 1500, "30 s - 5 min"), (1500, 10 ** 9, "> 5 min")):
        v = [r for r in dd if lo_ <= (r["b"]["age"] or 0) < hi_]
        if v: P(f"| {nm} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% |")
    P("\n### DIP lots by dump size (single-sell price drop)")
    P("| drop | lots | net SOL | per SOL | win | median ms after dump |"); P("|---|---|---|---|---|---|")
    for lo_, hi_ in ((0.05, 0.08), (0.08, 0.12), (0.12, 0.2), (0.2, 0.35), (0.35, 1)):
        v = [r for r in dd if lo_ <= r["b"]["d_drop"] < hi_]
        if v: P(f"| {int(lo_ * 100)}-{int(hi_ * 100)}% | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% | {np.median([r['b']['d_ms'] for r in v]):.0f} |")
    P("\n### DIP lots by dumper type")
    P("| dumper | lots | net SOL | per SOL | win |"); P("|---|---|---|---|---|")
    for st in ("dev", "bundler", "early", "fbot", "other", "us/haqq"):
        v = [r for r in dd if r["b"]["d_type"] == st]
        if v: P(f"| {st} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% |")
    P("\n### DIP lots by curve SOL before the buy")
    P("| curve SOL | lots | net SOL | per SOL | win |"); P("|---|---|---|---|---|")
    for lo_, hi_ in ((30.52, 35), (35, 45), (45, 60), (60, 90), (90, 1e9)):
        v = [r for r in dd if lo_ < r["b"]["vsol_pre"] <= hi_]
        if v: P(f"| {lo_:.0f}-{hi_:.0f} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% |")
    P("\n### DIP lots: first buyer after the dump vs not; dump in the same slot vs later")
    for nm, f in (("first after dump", lambda r: r["b"]["d_first"]), ("1+ buyers ahead", lambda r: not r["b"]["d_first"]),
                  ("same slot", lambda r: r["b"]["d_slots"] == 0), ("1 slot later", lambda r: r["b"]["d_slots"] == 1), ("2 slots later", lambda r: r["b"]["d_slots"] == 2)):
        v = [r for r in dd if f(r)]
        if v: P(f"- {nm}: {len(v)} lots, net {sum(r['net'] for r in v):+.2f}, per SOL {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}%, win {100 * np.mean([r['net'] > 0 for r in v]):.0f}%")
    # ---------------- holds / exits
    P("\n## 2. Exits (MEASURED)")
    P("| hold | lots | net SOL | per SOL | win | main types |"); P("|---|---|---|---|---|---|")
    for lo_, hi_, nm in ((0, 2, "< 2 s"), (2, 5, "2-5 s"), (5, 15, "5-15 s"), (15, 60, "15-60 s"), (60, 300, "1-5 min"), (300, 1e9, "> 5 min")):
        v = [r for r in R if r["hold_ms"] is not None and lo_ <= r["hold_ms"] / 1000 < hi_]
        if v:
            mt = collections.Counter(r["t"] for r in v).most_common(3)
            P(f"| {nm} | {len(v)} | {sum(r['net'] for r in v):+.2f} | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% | {100 * np.mean([r['net'] > 0 for r in v]):.0f}% | {', '.join(f'{a} {b}' for a, b in mt)} |")
    P("\nHold (s) by size tier, p10/p50/p90 (MEASURED):")
    for tier in (0.25, 0.4, 0.5, 1.0, 1.25):
        v = [r for r in R if abs(r["size"] - tier) < 0.03 and r["hold_ms"] is not None]
        if v: P(f"- {tier:.2f} SOL: {len(v)} lots, hold {pct([r['hold_ms'] / 1000 for r in v])} s, slots from dump {pct([r['d_hold'] for r in v])}, net {sum(r['net'] for r in v):+.2f}, dead-curve share {100 * np.mean([r['b']['vsol_pre'] <= DEAD_V for r in v]):.0f}%")
    # timer menu check
    menu = {10, 12, 15, 20, 25, 30, 40, 50, 60, 65}
    v = [r for r in R if r["d_hold"] is not None and r["t"] in ("DIP", "ADD")]
    hit = np.mean([(r["d_hold"] in menu or r["d_hold"] - 1 in menu) for r in v]) if v else 0
    P(f"\nDIP/ADD lots whose sell slot - dump slot is on the old timer menu (10..65, or +1): {100 * hit:.0f}% of {len(v)}")
    dh = collections.Counter(r["d_hold"] for r in v if r["d_hold"] is not None and r["d_hold"] <= 80)
    P("most common sell slot after the dump: " + ", ".join(f"{k}:{c}" for k, c in dh.most_common(15)))
    # do longer holds hold winners?
    P("\nDoes he hold winners longer? lot return by hold (DIP lots):")
    for lo_, hi_, nm in ((0, 5, "< 5 s"), (5, 15, "5-15 s"), (15, 60, "15-60 s"), (60, 1e9, "> 60 s")):
        vv = [r for r in dd if r["hold_ms"] is not None and lo_ <= r["hold_ms"] / 1000 < hi_]
        if vv: P(f"- {nm}: {len(vv)} lots, mean return {100 * np.mean([r['ret'] for r in vv]):+.2f}%, median {100 * np.median([r['ret'] for r in vv]):+.2f}%, net {sum(r['net'] for r in vv):+.2f}")
    # partial sells, adds
    P(f"\nLots sold in more than one piece: {100 * np.mean([r['nsell'] > 1 for r in R]):.1f}%")
    trips = collections.Counter((r["b"]["trip_ix"]) for r in R)
    P(f"Buys per position (trip): mean {np.mean(list(trips.values())):.2f}; positions with adds {100 * np.mean([c > 1 for c in trips.values()]):.0f}%")
    # sell context
    S24 = [s for s in SELLS if s["w"] == "haqq" and W0 <= s["bt"] < W1]
    P(f"\nSell context ({len(S24):,} sells): an outside buy >= 1 SOL in the last 2 slots {100 * np.mean([s['big_buy2'] >= 1 for s in S24]):.0f}%, "
      f"an outside sell >= 1 SOL in the last 2 slots {100 * np.mean([s['big_sell2'] >= 1 for s in S24]):.0f}%, last outside trade a buy {100 * np.mean([bool(s['last_buy']) for s in S24]):.0f}%, "
      f"ms since the last outside trade p50 {np.median([s['last_ms'] for s in S24 if s['last_ms'] is not None]):.0f}")
    # concurrency
    ev = []
    for r in R:
        if r["hold_ms"] is None: continue
        ev.append((r["b"]["cc"], 1)); ev.append((r["b"]["cc"] + r["hold_ms"], -1))
    ev.sort(); cur = 0; mx = 0; acc = []; last = None
    for t, dlt in ev:
        if last is not None: acc.append((cur, t - last))
        cur += dlt; mx = max(mx, cur); last = t
    w = np.array([a[1] for a in acc]); c = np.array([a[0] for a in acc])
    P(f"\nConcurrency (open lots, time-weighted): mean {np.sum(c * w) / np.sum(w):.1f}, p90 {np.percentile(np.repeat(c, np.maximum((w / 1000).astype(int), 1)), 90):.0f}, max {mx}")
    evd = [(r["b"]["cc"], r["b"]["cc"] + r["hold_ms"]) for r in R if r["hold_ms"] is not None and r["hold_ms"] < 15000]
    P(f"Short lots (< 15 s) only: {len(evd)} lots; lots per hour {len(evd) / 24:.0f}")
    # ---------------- latency (his side)
    P("\n## 3. Latency, his reactive first buys (chain clock = slot x 212 ms + index / block size x 212 ms; MEASURED)")
    P("| event | n | slots after p10/50/90 | same slot | index gap (same slot) p10/50/90 | ms after p10/50/90 | wallets between p10/50/90 | first buyer |")
    P("|---|---|---|---|---|---|---|---|")
    LAT = {}
    for t, key in (("DIP", "d"), ("LAUNCH", "c"), ("MOMO", "w")):
        v = [r["b"] for r in R if r["t"] == t]
        if key == "d":
            sls = [b["d_slots"] for b in v]; ms = [b["d_ms"] for b in v]; ig = [b["d_idx"] for b in v if b["d_idx"] is not None]; nw = [b["d_nw"] for b in v]; fst = np.mean([b["d_first"] for b in v])
        elif key == "c":
            sls = [b["age"] for b in v]; ms = [b["age_ms"] for b in v]; ig = []; nw = [b["n_prev"] for b in v]; fst = float("nan")
        else:
            sls = [b["wb_slots"] for b in v]; ms = [b["wb_ms"] for b in v]; ig = []; nw = [b["wb_nw"] for b in v]; fst = float("nan")
        P(f"| {t} | {len(v)} | {pct(sls)} | {100 * np.mean([s == 0 for s in sls]):.0f}% | {pct(ig)} | {pct(ms)} | {pct(nw)} | {100 * fst:.0f}% |")
        LAT[t] = dict(n=len(v), ms=[float(x) for x in np.percentile([m for m in ms if m is not None], (10, 50, 90))])
    P("\nDIP buys by leader client:")
    P("| client | n | ms p10/50/90 | same slot | first buyer | net per SOL |"); P("|---|---|---|---|---|---|")
    for cl in ("jito", "bam", "harmonic", "fd", "agave", "other", "?"):
        v = [r for r in R if r["t"] == "DIP" and r["client"] == cl]
        if v: P(f"| {cl} | {len(v)} | {pct([r['b']['d_ms'] for r in v])} | {100 * np.mean([r['b']['d_slots'] == 0 for r in v]):.0f}% | {100 * np.mean([r['b']['d_first'] for r in v]):.0f}% | {100 * sum(r['net'] for r in v) / sum(r['size'] for r in v):+.2f}% |")
    json.dump(dict(types=J, lat=LAT, fail_fee=fail_fee, n_fail=len(fail), n_land=n_land, net=tot_net), open(f"{D}/s3.json", "w"), indent=1)
    open(f"{D}/s3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
