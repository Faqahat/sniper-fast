#!/usr/bin/env python3
"""vs248 step 8 (read-only): example events per difference with GMGN (maker = haqq) and Solscan links. Out: vs248/examples.json"""
import pickle, sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
HQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"


def gm(m): return f"https://gmgn.ai/sol/token/{m}?maker={HQ}"
def ss(s): return f"https://solscan.io/tx/{s}" if s else None


def lot(x):
    return dict(buy_tx=ss(x["sig"]), sell_txs=[ss(s[4]) for s in x["sells"]], size_sol=round(float(x["cost"]), 4), net_msol=round(1e3 * float(x["net"]), 2),
                txc_msol=round(1e3 * float(x["txc"]), 3), buy_pkt=L.pkt(x["bt"]), slot=x["slot"], idx=x["idx"],
                dump_to_buy_ms=round(x["d_ms"], 1) if x.get("d_ms") is not None else None, trades_ahead=x.get("n_ahead"),
                price_vs_postdump=round(x["px_vs_post"], 4) if x.get("px_vs_post") else None, hold_s=round(x["hold_ms"] / 1000, 2) if x["hold_ms"] else None,
                trigger=x["d_cls"], trigger_sell_pct_supply=round(x.get("d_pct", 0), 2), trigger_drop_pct=round(100 * x["d_drop"], 1))


def main():
    Z = pickle.load(open(f"{OUT}/v2.pkl", "rb")); H, O = Z["H"], Z["O"]
    PP = pickle.load(open(f"{OUT}/v3.pkl", "rb"))["P"]
    hk = {(h["slot"], h["idx"]): h for h in H}; ok = {(x["slot"], x["idx"]): x for x in O}
    rng = np.random.default_rng(7)
    E = collections.OrderedDict()
    def pick(v, n=6, key=None):
        v = list(v)
        if key: v.sort(key=key); return v[:n]
        if len(v) <= n: return v
        return [v[i] for i in sorted(rng.choice(len(v), n, replace=False))]
    D = (4, 5)
    # 1 selection
    E["1a_gate_refused_248_bought"] = [dict(mint=h["mint"], gmgn=gm(h["mint"]), bot248=lot(h), ours="no attempt: " + h.get("reason", ""), our_engine_reg=h.get("reg_reason"), our_engine_ps=h.get("ps_reason"))
                                       for h in pick([h for h in H if h["day"] in D and h["bucket"].startswith("REF:gate") and h["net"] > 0.005])]
    E["1a_gate_refused_248_lost"] = [dict(mint=h["mint"], gmgn=gm(h["mint"]), bot248=lot(h), ours="no attempt: " + h.get("reason", ""))
                                     for h in pick([h for h in H if h["day"] in D and h["bucket"].startswith("REF:gate") and h["net"] < -0.005], 3)]
    E["1b_we_bought_248_did_not"] = [dict(mint=x["mint"], gmgn=gm(x["mint"]), ours=lot(x), path=x["path"], bot248=None)
                                     for x in pick([x for x in O if x["day"] in D and x["bucket"] == "OWN"])]
    for nm, f in (("1c_trigger_dev_chunk_refused", lambda h: h["dumpre"] and h["d_cls"] == "dev" and h["d_pct"] < 5 and h["bucket"].startswith("REF")),
                  ("1c_trigger_bundler_refused", lambda h: h["dumpre"] and h["d_cls"] == "bundler" and h["bucket"].startswith("REF")),
                  ("1c_trigger_whale_refused", lambda h: h["dumpre"] and h["d_cls"] == "whale" and h["bucket"].startswith("REF")),
                  ("1d_run_gap_no_engine", lambda h: h["bucket"] == "NOENG"), ("1e_no_dump_type", lambda h: h["bucket"] == "NODUMP")):
        E[nm] = [dict(mint=h["mint"], gmgn=gm(h["mint"]), bot248=lot(h), engine=h["bucket"], reason=h.get("reason")) for h in pick([h for h in H if h["day"] in D and f(h)])]
    # 2 timing, 4 size, 5 exit, 6 costs, 8 h2h: pairs
    PA = [(r, hk[r["h"]], ok[r["o"]]) for r in PP]
    def pair(r, h, x, extra=None):
        d = dict(mint=h["mint"], gmgn=gm(h["mint"]), ours=lot(x), our_path=x["path"], bot248=lot(h), we_landed_first=(x["slot"], x["idx"]) < (h["slot"], h["idx"]),
                 bot248_lands_after_us_ms=round(h["cc"] - x["cc"], 1), bot248_price_over_ours=round(h["px_pre"] / x["px_pre"], 4),
                 ours_net_msol=round(1e3 * r["A"], 2), bot248_net_msol=round(1e3 * r["Hh"], 2),
                 chain_msol=dict(size=round(1e3 * (r["S1"] - r["Ap"]), 2), exit=round(1e3 * (r["S2"] - r["S1"]), 2), entry=round(1e3 * (r["S3"] - r["S2"]), 2),
                                 costs=round(1e3 * (r["S4"] - r["S3"]), 2)),
                 ours_at_248_sell_time_msol=round(1e3 * r["o_at_h"], 2), bot248_at_our_sell_time_msol=round(1e3 * r["h_at_o"], 2))
        return d
    rec = [z for z in PA if z[2]["day"] in D]
    E["2_timing_same_dump_we_first_248_pays_more"] = [pair(*z) for z in pick([z for z in rec if (z[2]["slot"], z[2]["idx"]) < (z[1]["slot"], z[1]["idx"]) and z[1]["px_pre"] > 1.03 * z[2]["px_pre"]])]
    E["2_timing_same_dump_248_first"] = [pair(*z) for z in pick([z for z in rec if (z[2]["slot"], z[2]["idx"]) > (z[1]["slot"], z[1]["idx"])], 5)]
    E["3_limit_we_failed_248_filled"] = [dict(mint=h["mint"], gmgn=gm(h["mint"]), bot248=lot(h), our_failed_txs=[ss(f["sig"]) for f in h["fails"][:4]],
                                              our_failed_codes=sorted(set(f["code"] for f in h["fails"])), our_path=collections.Counter(f["path"] for f in h["fails"]).most_common(1)[0][0])
                                         for h in pick([h for h in H if h["day"] in D and h["bucket"] == "S_FAIL" and h["dumpre"]], 8)]
    E["4_size_biggest_effect"] = [pair(*z) for z in pick(rec, 5, key=lambda z: -abs(z[0]["S1"] - z[0]["Ap"]))]
    E["5_exit_248_time_better_for_our_tokens"] = [pair(*z) for z in pick(rec, 5, key=lambda z: -(z[0]["S2"] - z[0]["S1"]))]
    E["5_exit_248_time_worse_for_our_tokens"] = [pair(*z) for z in pick(rec, 5, key=lambda z: (z[0]["S2"] - z[0]["S1"]))]
    E["6_costs_same_dump"] = [pair(*z) for z in pick(rec, 5)]
    # 7 concurrency: 248 lots opened while another 248 lot was open
    iv = sorted(H, key=lambda h: h["cc"]); conc = []
    opn = []
    for h in iv:
        opn = [o for o in opn if (o["close_cc"] or o["cc"] + 60000) > h["cc"]]
        if opn and h["day"] in D: conc.append((h, opn[-1]))
        opn.append(h)
    E["7_concurrency_248_two_open"] = [dict(new=dict(mint=h["mint"], gmgn=gm(h["mint"]), bot248=lot(h)), already_open=dict(mint=o["mint"], gmgn=gm(o["mint"]), bot248=lot(o)))
                                       for h, o in pick(conc, 5)]
    E["8_head_to_head_random"] = [pair(*z) for z in pick(rec, 8)]
    json.dump(E, open(f"{OUT}/examples.json", "w"), indent=1, default=float)
    print({k: len(v) for k, v in E.items()})
    print(json.dumps(E["2_timing_same_dump_we_first_248_pays_more"][0], indent=1, default=float)[:2500])


if __name__ == "__main__":
    main()
