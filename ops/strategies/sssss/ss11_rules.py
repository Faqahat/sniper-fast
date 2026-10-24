#!/usr/bin/env python3
# Verify Haiku's sssssDdM rules IN CODE (read-only). Reads sssss/llm/answers_<tag>.jsonl:
#  ENTRY rules (p4_eval DSL) -> on each day: decision points = non-fleet trades on curve 30-113, age >= 5, >= 5 trades, while
#    it is active (+-10 min) and does not hold the token; label = the trade is the trigger of one of its buy attempts (ok or
#    failed, <= 2 slots). precision = share of flagged points it attempted; recall = share of its attempts flagged.
#  EXIT rules (exit DSL, ss8_sim) -> on its closed trips (its own entry fill): first firing trade vs its real sell slot:
#    hit (within +-2 slots), premature, late/never; plus the P&L of its trips under the rule vs its real exits.
# Writes sssss/llm/rules_<tag>.json (scores per rule) and sssss/llm/exits.jsonl (valid exit rules for the replica).
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/sssss")
import p4_eval as E
import ss8_sim as S
from ss4_select import holding_mask
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)

def day_ctx(run):
    d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; isfleet = np.isin(d["uid"], FLEET)
    att = json.load(open(f"{OUT}/att_{run}.json")); n = len(d["s"])
    lab = np.zeros(n, bool); t_att = np.sort(np.array([a["s"] * 212.0 for a in att]))
    for a in att:
        if a["dslot"] <= 2: lab[a["j"]] = True
    p = np.searchsorted(t_att, d["arr"]); l = np.abs(d["arr"] - t_att[np.maximum(p - 1, 0)]); r = np.abs(t_att[np.minimum(p, len(t_att) - 1)] - d["arr"])
    base = (~isfleet) & (~holding_mask(d, UID)) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < 113) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5) & (np.minimum(l, r) <= 600_000)
    return dict(lab=lab, base=base, isfleet=isfleet, npos=int((lab & base).sum()))

def entry_score(d, ctx, R):
    idx = E.triggers(d, R)
    m = np.zeros(len(d["s"]), bool); m[idx] = True; m &= ctx["base"]
    tp = int((m & ctx["lab"]).sum()); fl = int(m.sum())
    return dict(flagged=fl, tp=tp, precision=round(tp / max(1, fl), 4), recall=round(tp / max(1, ctx["npos"]), 4))

def exit_score(d, run, rule, ctx):
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    sibs = d["sibs"]; FI = d["FI"]; hit = early = late = 0; pnl_rule = pnl_real = 0.0
    for t in T:
        k0 = t["k0"]; st = dict(j=k0 + 1, V=float(d["vsol"][k0]), T=float(d["vtok"][k0]), q=t["buys"][0]["tok"], p_in=t["p_in"], B=t["cost"], fr=float(d["fr"][k0]),
                                land_slot=int(d["s"][k0]), end=int(d["tend"][k0]))
        r = S.walk(d, st, rule, 0.0, UID, sibs, FI)
        h = r["hold"]
        if r["why"] in ("timer",) and h >= rule[1]: late += 1
        elif h < t["hold"] - 2: early += 1
        elif h > t["hold"] + 2: late += 1
        else: hit += 1
        pnl_rule += r["pnl"]; pnl_real += t["pnl_curve"]
    n = len(T)
    return dict(hit=round(hit / n, 3), premature=round(early / n, 3), late=round(late / n, 3), pnl_rule=round(pnl_rule, 2), pnl_real=round(pnl_real, 2))

if __name__ == "__main__":
    tag = sys.argv[1]; days = sys.argv[2:] or ["R2", "R3"]
    ans = [json.loads(l) for l in open(f"{OUT}/llm/answers_{tag}.jsonl")]
    E.load(days); M = E.DAYS[days[0]]["M"]
    ctxs = {}
    for run in days:
        E.DAYS[run]["sibs"] = S.sib_last_sell(E.DAYS[run]); ctxs[run] = day_ctx(run)
    ent = []; exi = []
    for a in ans:
        o = a.get("answer") or {}
        for i, r in enumerate(o.get("entry_rules") or []):
            try: R = E.compile_rule(dict(r, size=0.5, exit={"max_slots": 30}), M["feats"], M["themes"], M["xl"]); ent.append((f"{a['id']}#{i}", r, R))
            except (ValueError, TypeError, KeyError) as e: pass
        for i, x in enumerate(o.get("exit_rules") or []):
            try: S.norm_exit(x); exi.append((f"{a['id']}#{i}", x))
            except (ValueError, TypeError, KeyError, AttributeError): pass
    print(f"{tag}: {len(ent)} valid entry rules, {len(exi)} valid exit rules", flush=True)
    res = {"entry": {}, "exit": {}}
    for rid, r, R in ent:
        res["entry"][rid] = dict(rule=r, **{run: entry_score(E.DAYS[run], ctxs[run], R) for run in days})
    for rid, x in exi:
        rule = S.norm_exit(x)
        res["exit"][rid] = dict(rule=x, **{run: exit_score(E.DAYS[run], run, rule, ctxs[run]) for run in days[:2]})
    json.dump(res, open(f"{OUT}/llm/rules_{tag}.json", "w"), indent=1)
    last = days[-1] if len(days) > 1 else days[0]
    print(f"\nENTRY rules (test day {last}; positives {ctxs[last]['npos']}), sorted by F1 on {last}:")
    def f1(v): return 2 * v["precision"] * v["recall"] / max(1e-9, v["precision"] + v["recall"])
    for rid, v in sorted(res["entry"].items(), key=lambda kv: -f1(kv[1][last]))[:25]:
        print(f"  {rid:<22} {last}: prec {v[last]['precision']:.1%} rec {v[last]['recall']:.1%} (flagged {v[last]['flagged']}) | R2 prec {v['R2']['precision']:.1%} rec {v['R2']['recall']:.1%} | {json.dumps(v['rule'].get('when'))[:230]}")
    print(f"\nEXIT rules (hit = fires within +-2 slots of its real sell), sorted by hit on {days[min(1, len(days) - 1)]}:")
    tday = days[min(1, len(days) - 1)]
    for rid, v in sorted(res["exit"].items(), key=lambda kv: -kv[1][tday]["hit"])[:20]:
        print(f"  {rid:<22} {tday}: hit {v[tday]['hit']:.1%} premature {v[tday]['premature']:.1%} late {v[tday]['late']:.1%} | P&L of its trips with this exit {v[tday]['pnl_rule']:+.1f} vs real {v[tday]['pnl_real']:+.1f} | {json.dumps(v['rule'])[:260]}")
    with open(f"{OUT}/llm/exits.jsonl", "a") as f:
        for rid, v in sorted(res["exit"].items(), key=lambda kv: -kv[1][tday]["hit"])[:6]:
            f.write(json.dumps({"name": f"haiku_{rid}", "exit": v["rule"]}) + "\n")
