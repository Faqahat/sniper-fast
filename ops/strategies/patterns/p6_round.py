#!/usr/bin/env python3
# ROUND DRIVER. Compiles every rule proposed so far (rules_r*.jsonl + auto exploitation rules), dedupes them by signature,
# evaluates NEW ones on R2 (train) only, and writes the next round's prompts from TRAIN results (+ R2 bot verification).
# R3 is never shown to the model; the final lockbox (p7_final.py) evaluates everything on R3 (+R1).
#   python3 p6_round.py eval            -> registry.json (+ train results)
#   python3 p6_round.py prompt r2 [n]   -> llm/req_r2.jsonl (submit with p3_llm.py submit r2)
import sys, os, json, glob, random, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
import p3_llm as L3
PO = "/home/moiz/sniper-data/strategies/patterns"; WK = f"{PO}/llm"
REG = f"{PO}/registry.json"

def registry():
    try: return json.load(open(REG))
    except Exception: return {"rules": [], "sigs": {}}

def collect(reg, M):
    added = 0; bad = collections.Counter()
    for f in sorted(glob.glob(f"{WK}/rules_r*.jsonl")) + sorted(glob.glob(f"{PO}/auto_rules*.jsonl")):
        rnd = os.path.basename(f).split("_")[1].split(".")[0] if "rules_r" in f else "auto"
        for l in open(f):
            r = json.loads(l)
            try: R = E.compile_rule(r, M["feats"], M["themes"], M["xl"])
            except Exception as ex: bad[str(ex)[:30]] += 1; continue
            if R["sig"] in reg["sigs"]: reg["rules"][reg["sigs"][R["sig"]]]["dup"] += 1; continue
            R["id"] = len(reg["rules"]); R["round"] = rnd; R["dup"] = 0; R["raw"] = r
            reg["sigs"][R["sig"]] = R["id"]; reg["rules"].append(R); added += 1
    print(f"registry: +{added} new rules ({len(reg['rules'])} total); not compilable: {sum(bad.values())} {bad.most_common(4)}")

def evaluate_new(reg, days=("R2",)):
    todo = [R for R in reg["rules"] if any(f"{d}_35" not in R.get("res", {}) for d in days)]
    if not todo: return
    res = E.evaluate_rules(todo, days, procs=9)
    for i, R in enumerate(todo): R.setdefault("res", {}).update(res[i])

def score(R, day="R2"):
    lat = 35
    r = R.get("res", {}).get(f"{day}_{lat}", {})
    return r

def summary_lines(reg, k_top=18, k_near=10, k_bad=10):
    rows = []
    for R in reg["rules"]:
        r = score(R)
        if r.get("n", 0) >= 20: rows.append((R, r))
    good = sorted([x for x in rows if x[1]["pnl"] > 0 and x[1]["t"] >= 1.5], key=lambda x: -x[1]["t"])[:k_top]
    near = sorted([x for x in rows if x[1]["pnl"] > 0 and x[1]["t"] < 1.5] + [x for x in rows if x[1]["pnl"] <= 0 and x[1]["mean"] > -0.004], key=lambda x: -x[1]["mean"])[:k_near]
    bad = sorted([x for x in rows if x[1]["pnl"] <= 0], key=lambda x: x[1]["mean"])[:k_bad]
    def fmt(R, r):
        return (f"- [{R['id']}] {R['name']} | event={R['event']}{'(' + str(R['idle']) + ')' if R['idle'] else ''} mode={R['mode']} race={R['race']} when={json.dumps(R['raw'].get('when'))} exit={json.dumps(R['raw'].get('exit'))}"
                f"\n    TRAIN day: trades {r['n']} (triggers {r['trig']}), P&L {r['pnl']:+.2f} SOL, mean {r['mean']:+.4f}/trade, win {r['win']:.0%}, t {r['t']}, fails {r['fail']}, hold {r.get('hold_med')} slots, tx ahead of us {r.get('ahead_med')}")
    L = ["TRAIN-DAY RESULTS of rules tested so far (one position at a time, our costs, 35 ms landing; t = mean / standard error):",
         f"Tested {len(reg['rules'])} rules; {sum(1 for _, r in rows if r['pnl'] > 0)} of {len(rows)} with >= 20 trades were positive on the train day.",
         "WINNERS (positive, t >= 1.5):"] + [fmt(*x) for x in good] + ["NEAR MISSES:"] + [fmt(*x) for x in near] + ["CLEAR LOSERS:"] + [fmt(*x) for x in bad]
    return "\n".join(L)

def bot_lines(k=25):
    V = json.load(open(f"{PO}/bots_verified.json"))
    nonself = [o for o in V if not o["self"] and o["R2"].get("trig_on", 0) >= 50]
    top = sorted(nonself, key=lambda o: -(o["R2"].get("hit") or 0) * min(1.0, (o["R2"].get("lift") or 0) / 5))[:k]
    L = ["VERIFIED BOT BEHAVIORS (measured in code on the TRAIN day; hit = P(bot acts within N slots | trigger, bot online); lift = hit / chance):",
         "Note: individual bots are selective - no described behavior had a hit rate above 35%; most were below 10%."]
    for o in top:
        a = o["R2"]
        L.append(f"- {o['bot']}({o['family']}) {o['action']} within {o['N']} slots after {o['event']} {json.dumps(o['conds'])}: hit {a.get('hit')}, lift {a.get('lift')}, triggers {a.get('trig_on')}, delay slots p25/50/75 {a.get('delay_slots')}, same-slot {a.get('same_slot')}, tx-index delay in same slot {a.get('idx_delay_same_slot_med')}")
    return "\n".join(L)

ROUND_TASK = """
NEXT ROUND. Using the train-day results above (and the stories below), propose up to 5 rules in the same DSL:
 - refinements of WINNERS/NEAR MISSES that should be more robust (fewer, cleaner conditions beat many tight ones),
 - genuinely NEW trigger->reaction ideas not yet tested,
 - exploitation rules built on the verified bot behaviors: be_trigger (we create the trigger they react to, then sell into
   their buy: exit on bot_buy:<id>), front_run (we act on the trigger before a slower bot and sell into its buy), or avoid
   (add a holds:<id> == 0 / acted:<id>:<k> == 0 filter to a rule where that bot dumps).
Remember: our buy lands ~65 transactions after a trigger in the same slot (or the next slot); one position at a time;
0.35-0.75 SOL; costs 1.25% per side + 0.0035 SOL. Do not repeat a rule already listed. Also add up to 3 new bot behaviors in
the same "bots" format if you see them. Reply with ONLY {"rules": [...], "bots": [...]}."""

def prompt(rnd, nreq=30, per=10, seed=0):
    reg = registry()
    head = summary_lines(reg) + "\n\n" + bot_lines() + "\n" + ROUND_TASK
    st = [json.loads(l) for l in open(f"{PO}/stories_R2.jsonl")]
    rnd_ = random.Random(seed + len(rnd)); rnd_.shuffle(st)
    reqs = []
    for k in range(nreq):
        ch = st[k * per:(k + 1) * per]
        user = head + "\n\nSTORIES (train day):\n\n" + "\n\n".join(o["text"] for o in ch)
        reqs.append({"custom_id": f"{rnd}_{k:04d}", "params": {"model": L3.S.MODEL, "max_tokens": L3.MAXTOK, "system": L3.SYSTEM,
                     "messages": [{"role": "user", "content": user}]}})
    L3.write(rnd, reqs)
    open(f"{WK}/feedback_{rnd}.txt", "w").write(head)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "eval":
        reg = registry(); E.load(["R2"]); M = E.DAYS["R2"]["M"]
        collect(reg, M); evaluate_new(reg, ("R2",))
        json.dump(reg, open(REG, "w"))
        rows = [(R, score(R)) for R in reg["rules"] if score(R).get("n", 0) >= 20]
        pos = [x for x in rows if x[1]["pnl"] > 0]
        print(f"train-day: {len(rows)} rules with >=20 trades; positive {len(pos)}; t>=2: {sum(1 for x in pos if x[1]['t'] >= 2)}")
        for R, r in sorted(pos, key=lambda x: -x[1]["t"])[:25]:
            print(f"  [{R['id']}] r{R['round']} {R['name'][:50]:<50} n {r['n']:5d} pnl {r['pnl']:+8.2f} mean {r['mean']:+.4f} win {r['win']:.0%} t {r['t']:5.2f} | dip {r.get('dip_overlap')} f7 {r.get('f7_overlap')} | {R['event']} {R['mode']} race={R['race']}")
    elif a[0] == "prompt":
        prompt(a[1], int(a[2]) if len(a) > 2 else 30)
