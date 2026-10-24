#!/usr/bin/env python3
# BOT PLAYBOOK, bait responders (read-only): after a quiet-token buy (the F7 trigger: buy on a token quiet >= 20 slots,
# age >= 150 slots, curve <= 45 SOL before the buy, buyer not creator/insider), which ID'd bots buy in the same token
# within 1 slot? Per bot: P(responds | bait) on R2 and R3, delay (slots / tx index), size; by bait size band: P(any follower
# buy within 1 slot) and follower SOL. -> patterns/playbook_bait.json
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
PO = "/home/moiz/sniper-data/strategies/patterns"
BANDS = [(0.1, 0.35), (0.35, 0.75), (0.75, 1.2), (1.2, 2.1), (2.1, 3.0)]
def bait_mask(d, lo, hi):
    F = d["F"]; FI = d["FI"]
    return ((d["buy"] == 1) & (d["sol"] >= lo * 1e9) & (d["sol"] < hi * 1e9) & (F[:, FI["quiet"]] >= 20) & (F[:, FI["age"]] >= 150)
            & (F[:, FI["curve"]] - d["sol"] / 1e9 <= 45) & ~np.isin(d["wt"], [1, 2]))
def responders(d, idx):
    s = d["s"]; tend = d["tend"]; out = []
    for k in idx:
        k = int(k); j = k + 1; e = int(tend[k]); resp = []
        while j < e and s[j] <= s[k] + 1:
            if d["buy"][j] and d["uid"][j] != d["uid"][k]: resp.append((int(d["bid"][j]), int(s[j] - s[k]), int(d["i"][j] - d["i"][k]) if s[j] == s[k] else -1, float(d["sol"][j] / 1e9)))
            j += 1
        out.append(resp)
    return out
if __name__ == "__main__":
    E.load(["R2", "R3"])
    BOT = json.load(open(f"{PO}/botids.json")); inv = {v[0]: (u, v[1]) for u, v in BOT.items()}
    res = {"bands": {}, "bots": {}}
    per_bot = {}
    for run in ("R2", "R3"):
        d = E.DAYS[run]
        for lo, hi in BANDS:
            idx = np.flatnonzero(bait_mask(d, lo, hi)); R = responders(d, idx)
            anyr = [len(r) > 0 for r in R]; sol = [sum(x[3] for x in r) for r in R]
            res["bands"].setdefault(f"{lo}-{hi}", {})[run] = dict(n=len(idx), p_any=round(float(np.mean(anyr)), 3) if R else None,
                                                                   follow_sol_mean=round(float(np.mean(sol)), 3) if R else None)
        idx = np.flatnonzero(bait_mask(d, 0.75, 3.0)); R = responders(d, idx)
        cnt = collections.Counter(); dl = collections.defaultdict(list); sz = collections.defaultdict(list)
        for r in R:
            seen = set()
            for b, ds, di, so in r:
                if b and b not in seen: seen.add(b); cnt[b] += 1; dl[b].append((ds, di)); sz[b].append(so)
        for b, c in cnt.items():
            pb = per_bot.setdefault(b, {})
            pb[run] = dict(p=round(c / len(R), 4), n=c, same_slot=round(float(np.mean([x[0] == 0 for x in dl[b]])), 2),
                           idx_delay_med=int(np.median([x[1] for x in dl[b] if x[0] == 0])) if any(x[0] == 0 for x in dl[b]) else None,
                           size_med=round(float(np.median(sz[b])), 3))
        res[f"n_baits_{run}"] = len(R)
    top = sorted(per_bot.items(), key=lambda kv: -(kv[1].get("R2", {}).get("p", 0)))[:25]
    res["bots"] = [dict(bot=f"B{b}", wallet=inv.get(b, ("?", "?"))[0], family=inv.get(b, ("?", "?"))[1], **{r: v.get(r) for r in ("R2", "R3")}) for b, v in top]
    json.dump(res, open(f"{PO}/playbook_bait.json", "w"), indent=1)
    print("P(any follower buy within 1 slot | quiet-token buy), by bait size:")
    for k, v in res["bands"].items(): print(f"  {k:>9} SOL: R2 n {v['R2']['n']:5d} p {v['R2']['p_any']} follow SOL {v['R2']['follow_sol_mean']} | R3 n {v['R3']['n']:5d} p {v['R3']['p_any']} follow SOL {v['R3']['follow_sol_mean']}")
    print(f"top responders to 0.75-3 SOL baits (R2 baits {res['n_baits_R2']}, R3 baits {res['n_baits_R3']}):")
    for o in res["bots"][:20]:
        print(f"  {o['bot']:>5}({o['family']}) {o['wallet'][:8]}  R2 {o['R2']}  | R3 {o['R3']}")
