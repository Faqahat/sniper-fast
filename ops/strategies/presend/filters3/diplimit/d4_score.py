#!/usr/bin/env python3
"""DIPLIMIT step 4: checks + per-drop table from d3 replay_<TAG>.json.
Money: total = fill P&L (live realized where the live fill is reproduced, else modelled exit) - 5,120 x landed non-filling tries.
w/o top 5 = total minus the 5 best windows' fill P&L. win = share of fills with P&L > 0 (reps weighted).
usage: d4_score.py TAG [TAG ...]"""
import sys, json, statistics, collections
D = "/home/it/sniper-data/filters3/diplimit"
FAIL = 5120e-9


def table(rows, hours, label):
    out = {}
    drops = list(rows[0]["d"].keys())
    for dr in drops:
        for part in ("all", "t2", "rearm"):
            rr = [r for r in rows if part == "all" or r["kind"] == part]
            fills = sum(r["d"][dr]["filled"] for r in rr)
            fp = [r["d"][dr]["fill_pnl"] for r in rr]
            fees = sum(r["d"][dr]["fails"] for r in rr) * FAIL
            tot = sum(fp) - fees
            win = sum(1 for r in rr if r["d"][dr]["filled"] > 0 and r["d"][dr]["fill_pnl"] > 0)
            nf = sum(1 for r in rr if r["d"][dr]["filled"] > 0)
            top = sorted(fp)[-5:] if part == "all" else []
            src = collections.Counter()
            for r in rr:
                for k, v in r["d"][dr]["src"].items(): src[k] += v
            out[(dr, part)] = {"fills": round(fills, 1), "fill_pnl": round(sum(fp), 3), "fees": round(fees, 3), "total": round(tot, 3),
                               "win": round(win / nf, 2) if nf else None, "wo_top5": round(tot - sum(top), 3) if part == "all" else None,
                               "per_day": round(tot / hours * 24, 2), "src": dict(src)}
    print(f"\n== {label}  ({hours:.2f} h, {len(rows)} armed windows)")
    print(" drop  | fills | fill P&L | fees  |  total  | win | w/o top5 | SOL/day || T2 fills/total | re-arm fills/total | fill source")
    for dr in drops:
        a, t, r = out[(dr, "all")], out[(dr, "t2")], out[(dr, "rearm")]
        print(f" {float(dr):.2f}  | {a['fills']:5.1f} | {a['fill_pnl']:+8.3f} | {a['fees']:.3f} | {a['total']:+7.3f} | {a['win'] if a['win'] is not None else 0:.0%} | "
              f"{a['wo_top5']:+8.3f} | {a['per_day']:+7.2f} || {t['fills']:5.1f} {t['total']:+7.3f} | {r['fills']:5.1f} {r['total']:+7.3f} | {a['src']}")
    return {f"{k[0]}|{k[1]}": v for k, v in out.items()}


if __name__ == "__main__":
    allout = {}
    for tag in sys.argv[1:]:
        R = json.load(open(f"{D}/replay_{tag}.json")); rows = R["rows"]
        ts = sorted(r["t"] for r in rows if r["t"])
        hours = (ts[-1] - ts[0]) / 3.6e12
        print(f"##### {tag}: dropped {R['dropped']} | min_out recompute rel err max {R['mo_err']['max']:.2e} (n {R['mo_err']['n']}) | H {R['H']:.0f} ms | "
              f"fixed { {k: round(v / 1e6, 2) for k, v in R['FX'].items()} } mSOL")
        ex = R["exit_check"]
        tk = [abs(e["tok_model"] - e["tok_live"]) / e["tok_live"] for e in ex if e["tok_live"]]
        cs = [abs(e["curve_own_sell"] - e["curve_live"]) / 1e6 for e in ex if e["curve_own_sell"] is not None and e["curve_live"] is not None]
        md = [e["model"] - e["real"] for e in ex]
        print(f"  live fills checked {len(ex)}: tokens model vs live max rel err {max(tk):.2e}; curve P&L at the real sell, tape vs engine: median "
              f"{statistics.median(cs):.3f} mSOL, max {max(cs):.2f}; exit MODEL (median hold) - realized: sum {sum(md):+.3f} SOL, mean {statistics.mean(md) * 1e3:+.1f} mSOL, "
              f"MAE {statistics.mean(abs(x) for x in md) * 1e3:.1f} mSOL")
        # baseline reproduction
        b = "0.12"; bad = []
        for r in rows:
            d = r["d"][b]
            if r["live_filled"] and d["src"] != {"live": 1}: bad.append((r["w"], r["kind"], "live fill not reproduced", d["src"]))
            if not r["live_filled"] and d["filled"] > 0: bad.append((r["w"], r["kind"], "extra fill", d["src"]))
        live_tot = sum(r["pnl_live"] or 0 for r in rows)
        print(f"  BASELINE 0.12: live-filled windows {sum(r['live_filled'] for r in rows)}, mismatches {len(bad)} {bad[:8]}; "
              f"live realized of replayed windows {live_tot:+.4f} SOL vs replay fill P&L {sum(r['d'][b]['fill_pnl'] for r in rows):+.4f}")
        allout[tag] = {"hours": hours, "table": table(rows, hours, tag), "baseline_mismatch": bad, "live_realized": live_tot}
    json.dump(allout, open(f"{D}/score_{'_'.join(sys.argv[1:])}.json", "w"), indent=1, default=str)
