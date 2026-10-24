#!/usr/bin/env python3
# Haiku REFINEMENT round for sssssDdM (train day R2 only). Feeds the code-measured mismatches of round 1 back to Haiku:
#  ENTRY: the measured selection-model bands + the best round-1 rules with their measured precision / recall, and cards of
#         MISSED attempts (it tried, the rule did not flag) and FALSE ALARMS (the rule flagged, it did not try).
#  EXIT:  the measured exit hazard table + the best round-1 exit rules with hit / premature / late and P&L, and cards of
#         PREMATURE firings (state where the rule fired, the path after it, where it really sold) and LATE / MISSED exits
#         (state at its real sell). Sibling sells are shown but rules must NOT need them (we cannot rely on them).
#   python3 ss15_refine.py prep <tag> <prev_tag> | submit <tag> | status <tag> | fetch <tag>
import sys, os, json, zlib, random
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
import llm as L
from ss7_cards import KNOWN, SYS_ENTRY, SYS_EXIT, entry_taken, entry_tried, entry_skipped, state_line, fmt, who, P, first_idx, WK, MAXTOK
from ss11_rules import day_ctx
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")

def hazard_text():
    return open(f"{OUT}/hazard_R2.log").read()

def bands_text():
    sel = json.load(open(f"{OUT}/select.json"))
    lines = ["MEASURED attempt rate by band of the feature at the trigger trade (R2; base rate ~0.7% of all trades on busy tokens):"]
    for f, rows in sel["bands_R2"].items():
        lines.append(f"  {f}: " + "; ".join(f"[{lo:g},{hi:g}] {rate:.2%}" for lo, hi, n, rate in rows))
    lines.append("A gradient-boosted model on these features reaches AUC 0.94 on a held-out day; top gains: bsol3 0.21, bsol1 0.17, nwal 0.05, maxb1 0.04, nb1 0.04, curve 0.03.")
    return "\n".join(lines)

def prep(tag, prev, n_entry=10, n_exit=10):
    os.makedirs(WK, exist_ok=True)
    E.load(["R2"]); d = E.DAYS["R2"]; d["sibs"] = S.sib_last_sell(d); M = d["M"]; rng = random.Random(21)
    rr = json.load(open(f"{WK}/rules_{prev}.json"))
    def f1(v): return 2 * v["precision"] * v["recall"] / max(1e-9, v["precision"] + v["recall"])
    best_e = sorted(rr["entry"].items(), key=lambda kv: -f1(kv[1]["R2"]))[:4]
    best_x = sorted(rr["exit"].items(), key=lambda kv: -kv[1]["R2"]["hit"])[:4]
    ctx = day_ctx("R2")
    # entry mismatches for the single best rule
    R = E.compile_rule(dict(best_e[0][1]["rule"], size=0.5, exit={"max_slots": 30}), M["feats"], M["themes"], M["xl"])
    flag = np.zeros(len(d["s"]), bool); flag[E.triggers(d, R)] = True; flag &= ctx["base"]
    fn = list(np.flatnonzero(ctx["lab"] & ctx["base"] & ~flag)); fp = list(np.flatnonzero(flag & ~ctx["lab"])); rng.shuffle(fn); rng.shuffle(fp)
    att = {a["j"]: a for a in json.load(open(f"{OUT}/att_R2.json"))}
    T = {t["k0"]: t for t in json.load(open(f"{OUT}/trips_R2.json")) if t["closed"]}
    def miss_card(j):
        a = att.get(int(j)); s0 = int(d["s"][j]); a0 = float(d["arr"][j]); lo = first_idx(d, j)
        res = "landed" if a and a["ok"] else "failed on slippage"
        return (f"MISSED (it tried, {res}; the rule did not flag): token {M['meta'][int(d['tok'][j])]['m'][:6]} | state at the trigger: {state_line(d, j)} "
                f"bsol1={d['F'][j, d['FI']['bsol1']]:.3g} bsol3={d['F'][j, d['FI']['bsol3']]:.3g} nb1={d['F'][j, d['FI']['nb1']]:.3g} sol={d['sol'][j] / 1e9:.2f} move={d['F'][j, d['FI']['move']]:+.1f}\n"
                f"  tape (slot / ms vs trigger): " + " ; ".join(fmt(d, x, s0, a0) for x in range(max(lo, j - 7), j + 1)))
    def fa_card(j):
        s0 = int(d["s"][j]); a0 = float(d["arr"][j]); lo = first_idx(d, j); e = int(d["tend"][j]); z = j
        while z + 1 < e and d["s"][z + 1] <= s0 + 30: z += 1
        return (f"FALSE ALARM (the rule flagged, it did NOT try): token {M['meta'][int(d['tok'][j])]['m'][:6]} | state: {state_line(d, j)} "
                f"bsol1={d['F'][j, d['FI']['bsol1']]:.3g} bsol3={d['F'][j, d['FI']['bsol3']]:.3g} nb1={d['F'][j, d['FI']['nb1']]:.3g} sol={d['sol'][j] / 1e9:.2f} move={d['F'][j, d['FI']['move']]:+.1f}\n"
                f"  tape (slot / ms vs this trade): " + " ; ".join(fmt(d, x, s0, a0) for x in range(max(lo, j - 7), j + 1)) + f"\n  price 30 slots later: {(P(d, z) / P(d, j) - 1) * 100:+.1f}%")
    head_e = (bands_text() + "\n\nROUND-1 RULES MEASURED IN CODE on the train day (precision = share of flagged moments it tried; recall = share of its tries flagged):\n" +
              "\n".join(f"  {json.dumps(v['rule'].get('when'))} event={v['rule'].get('event')} -> precision {v['R2']['precision']:.1%}, recall {v['R2']['recall']:.1%}" for k, v in best_e) +
              "\nA good rule should reach precision >= 20% at recall >= 20%. Improve the FIRST rule using the mismatch cards below.")
    reqs = []
    sys_e = SYS_ENTRY.replace("{KNOWN}", KNOWN); sys_x = SYS_EXIT.replace("{KNOWN}", KNOWN)
    for r in range(n_entry):
        cards = [miss_card(j) for j in fn[r * 16:(r + 1) * 16]] + [fa_card(j) for j in fp[r * 16:(r + 1) * 16]]
        rng.shuffle(cards)
        reqs.append({"custom_id": f"{tag}_entry_{r:03d}", "params": {"model": L.MODEL, "max_tokens": MAXTOK, "system": sys_e,
                     "messages": [{"role": "user", "content": head_e + "\n\nMISMATCH CARDS (train day):\n\n" + "\n\n".join(cards)}]}})
    # exit mismatches for the best non-sibling exit rule
    nonsib = [(k, v) for k, v in sorted(rr["exit"].items(), key=lambda kv: -kv[1]["R2"]["hit"]) if "sib_sold" not in json.dumps(v["rule"])][:4]
    rule = S.norm_exit(nonsib[0][1]["rule"]); FI = d["FI"]
    prem = []; late = []
    trips = [t for t in T.values() if t["sells"]]; rng.shuffle(trips)
    for t in trips[:3000]:
        k0 = t["k0"]; st = dict(j=k0 + 1, V=float(d["vsol"][k0]), T=float(d["vtok"][k0]), q=t["buys"][0]["tok"], p_in=t["p_in"], B=t["cost"], fr=float(d["fr"][k0]),
                                land_slot=int(d["s"][k0]), end=int(d["tend"][k0]))
        x = S.walk(d, st, rule, 0.0, UID, d["sibs"], FI)
        if x["jf"] is not None and x["hold"] < t["hold"] - 2: prem.append((t, x))
        elif x["jf"] is None or x["hold"] > t["hold"] + 2: late.append((t, x))
    def path_lines(t, lo_k, hi_k, max_rows=14):
        s0 = int(d["s"][t["k0"]]); p_in = t["p_in"]; rows = []; pk = 1.0
        for q in range(t["k0"] + 1, hi_k):
            if d["uid"][q] == UID: continue
            m = P(d, q) / p_in; pk = max(pk, m)
            if q >= lo_k: rows.append(f"{int(d['s'][q] - s0):+d} {'B' if d['buy'][q] else 'S'} {d['sol'][q] / 1e9:.2f} {who(d, q)} {d['F'][q, FI['move']]:+.1f}% ret1 {d['F'][q, FI['ret1']]:+.1f} m{m:.3f} dd{1 - m / pk:.3f}")
        return rows[:max_rows // 2] + (["..."] if len(rows) > max_rows else []) + rows[-max_rows // 2:] if len(rows) > max_rows else rows
    def prem_card(t, x):
        jf = x["jf"]; ks = t["sells"][-1]["k"]
        return (f"PREMATURE: token {t['mint'][:6]} its buy at curve {t['buys'][0]['vsol'] / 1e9:.1f}; the rule fired at +{int(d['s'][jf] - t['slot'])} slots on:\n  " +
                "\n  ".join(path_lines(t, max(t['k0'] + 1, jf - 4), jf + 1)) + f"\n  ...but it kept holding; it really sold at +{t['hold']} slots (exit {t['exit_mult']:.3f}x, peak {t['peak_mult']:.2f}x, result {t['pnl_curve']:+.3f}). Trades right before its real sell:\n  " +
                "\n  ".join(path_lines(t, max(t['k0'] + 1, ks - 6), ks)))
    def late_card(t, x):
        ks = t["sells"][-1]["k"]
        return (f"MISSED EXIT: token {t['mint'][:6]} its buy at curve {t['buys'][0]['vsol'] / 1e9:.1f}; it sold at +{t['hold']} slots (exit {t['exit_mult']:.3f}x, peak {t['peak_mult']:.2f}x, result {t['pnl_curve']:+.3f}); "
                f"the rule {'fired only at +' + str(x['hold']) if x['jf'] is not None else 'never fired'}. Trades right before its sell:\n  " + "\n  ".join(path_lines(t, max(t['k0'] + 1, ks - 8), ks)))
    head_x = ("MEASURED EXIT HAZARD (probability that a trade is the one right before its sell, by band):\n" + hazard_text() +
              "\n\nROUND-1 EXIT RULES MEASURED IN CODE on its own trips (train day; hit = fires within +-2 slots of its real sell):\n" +
              "\n".join(f"  {json.dumps(v['rule'].get('any_of'))} -> hit {v['R2']['hit']:.0%}, premature {v['R2']['premature']:.0%}, late {v['R2']['late']:.0%}; its trips' P&L with this exit {v['R2']['pnl_rule']:+.1f} SOL vs its real {v['R2']['pnl_real']:+.1f}" for k, v in nonsib) +
              "\nPremature exits are costly: 1% of its trips (2-4x runners held 400-700 slots) make most of its profit. Your rule must NOT use sib_sold. Improve the first rule using the mismatch cards.")
    for r in range(n_exit):
        cards = [prem_card(t, x) for t, x in prem[r * 8:(r + 1) * 8]] + [late_card(t, x) for t, x in late[r * 6:(r + 1) * 6]]
        rng.shuffle(cards)
        reqs.append({"custom_id": f"{tag}_exit_{r:03d}", "params": {"model": L.MODEL, "max_tokens": MAXTOK, "system": sys_x,
                     "messages": [{"role": "user", "content": head_x + "\n\nMISMATCH CARDS (train day; ret1 = % price change since the end of the previous slot):\n\n" + "\n\n".join(cards)}]}})
    with open(f"{WK}/req_{tag}.jsonl", "w") as f:
        for q in reqs: f.write(json.dumps(q) + "\n")
    print(f"{tag}: {len(reqs)} requests; worst case ${L.worst_case(reqs):.3f}; spend so far ${L.ledger()['usd']:.3f}; entry FN {len(fn)} FP {len(fp)}; exit premature {len(prem)} late {len(late)}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "prep": prep(a[1], a[2])
    elif a[0] == "submit": L.submit(a[1], [json.loads(l) for l in open(f"{WK}/req_{a[1]}.jsonl")])
    elif a[0] == "status": print(L.status(a[1]))
    elif a[0] == "fetch": L.fetch(a[1])
