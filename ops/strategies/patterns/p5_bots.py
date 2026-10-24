#!/usr/bin/env python3
# BOT BEHAVIOR VERIFIER (read-only). Every behavior Haiku described ("bot B<id> does <action> within N slots after <trigger>")
# is measured in code on each day:
#   trig_on   = trigger trades by OTHER wallets while the bot is online (it traded anywhere within +-15 min)
#   hit       = P(bot does <action> in the same token within N slots after the trigger | trigger, online)
#   base      = same probability after a random other-wallet trade while online (same tokens' activity) -> lift = hit / base
#   timing    = slot delay p25/p50/p75, share in the trigger's own slot, tx-index delay when same slot
# Behaviors with no trigger ("acts on its own") get an activity profile instead (actions/day, size, token age/curve).
# Reliable (chosen on R2 ONLY): trig_on >= 50, hit >= 0.10, lift >= 5. R3 numbers = out-of-sample stability.
# -> patterns/bots_verified.json
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
PO = "/home/moiz/sniper-data/strategies/patterns"
ONLINE_MS = 900_000

def prep(d):
    bid = d["bid"]; o = np.argsort(bid, kind="stable"); bs = bid[o]
    u, st = np.unique(bs, return_index=True); en = np.append(st[1:], len(bs))
    d["bot_idx"] = {int(b): np.sort(o[a:e]) for b, a, e in zip(u, st, en) if b}
    rng = np.random.default_rng(5); d["sample"] = np.sort(rng.choice(len(bid), size=min(300_000, len(bid)), replace=False))

def verify(d, beh, R):
    B = beh["bid"]; act_buy = beh["action"] == "buy"; N = beh["N"]
    lo, hi = beh["size"]
    allb = d["bot_idx"].get(B)
    if allb is None or not len(allb): return dict(bot_trades=0)
    acts = allb[(d["buy"][allb] == (1 if act_buy else 0)) & (d["sol"][allb] >= lo * 0.5e9) & (d["sol"][allb] <= hi * 2e9)]
    times = np.sort(d["arr"][allb])
    def online(idx):
        t = d["arr"][idx]; p = np.searchsorted(times, t)
        left = np.abs(t - times[np.maximum(p - 1, 0)]); right = np.abs(times[np.minimum(p, len(times) - 1)] - t)
        return np.minimum(left, right) <= ONLINE_MS
    def hits(idx):
        if not len(acts) or not len(idx): return np.zeros(len(idx), bool), np.zeros(len(idx), np.int64), np.zeros(len(idx), np.int64)
        p = np.searchsorted(acts, idx, side="right"); ok = p < len(acts); a = acts[np.minimum(p, len(acts) - 1)]
        h = ok & (d["tok"][a] == d["tok"][idx]) & (d["s"][a] - d["s"][idx] <= N)
        return h, d["s"][a] - d["s"][idx], d["i"][a].astype(np.int64) - d["i"][idx]
    out = dict(bot_trades=int(len(allb)), actions=int(len(acts)), act_size_med=round(float(np.median(d["sol"][acts]) / 1e9), 3) if len(acts) else None)
    if beh["self"]:
        if len(acts):
            out["age_med"] = float(np.median(d["F"][acts, d["FI"]["age"]])); out["curve_med"] = round(float(np.median(d["F"][acts, d["FI"]["curve"]])), 1)
        return out
    tr = E.triggers(d, R); tr = tr[d["bid"][tr] != B]
    if not len(tr): out.update(trig=0); return out
    on = online(tr); tro = tr[on]
    h, ds, di = hits(tro)
    smp = d["sample"]; smp = smp[d["bid"][smp] != B]; smp = smp[online(smp)]
    hb, _, _ = hits(smp)
    hit = float(h.mean()) if len(h) else 0.0; base = float(hb.mean()) if len(hb) else 0.0
    out.update(trig=int(len(tr)), trig_on=int(len(tro)), hit=round(hit, 3), base=round(base, 4), lift=round(hit / base, 1) if base > 0 else None)
    if h.any():
        dd = ds[h]; out["delay_slots"] = [int(np.percentile(dd, q)) for q in (25, 50, 75)]
        out["same_slot"] = round(float((dd == 0).mean()), 3)
        same = di[h][dd == 0]; out["idx_delay_same_slot_med"] = int(np.median(same)) if len(same) else None
        out["hit_tokens"] = int(len(set(d["tok"][tro[h]].tolist())))
    return out

def norm(b, feats, themes, xl):
    bot = str(b.get("bot", "")).strip().lstrip("B").split("(")[0]
    if not bot.isdigit(): raise ValueError("bot id")
    tg = b.get("trigger") or {}
    ev = str(tg.get("event", "any")).lower()
    if ev not in ("buy", "sell", "any"): ev = "any"
    when = tg.get("when") or []
    act = str(b.get("action", "buy")).lower()
    if act not in ("buy", "sell"): raise ValueError("action")
    N = int(b.get("within_slots") or 0); N = max(0, min(N, 300))
    sz = b.get("size") or [0, 100]
    try: lo, hi = float(sz[0]), float(sz[1])
    except Exception: lo, hi = 0.0, 100.0
    R = E.compile_rule({"event": ev, "when": when}, feats, themes, xl)
    selfinit = ev == "any" and not when
    return dict(bid=int(bot), action=act, N=max(N, 1), size=(lo, hi), self=selfinit, R=R,
                key=json.dumps([int(bot), act, max(N, 1) if not selfinit else 0, R["sig"] if not selfinit else ""]))

if __name__ == "__main__":
    files = sys.argv[1:] or [f"{PO}/llm/bots_r1.jsonl"]
    days = ("R2", "R3")
    E.load(days); M = E.DAYS["R2"]["M"]
    for r in days: prep(E.DAYS[r])
    raw = [json.loads(l) for f in files for l in open(f)]
    uniq = {}; bad = 0
    for b in raw:
        try: nb = norm(b, M["feats"], M["themes"], M["xl"])
        except Exception: bad += 1; continue
        if nb["key"] in uniq: uniq[nb["key"]]["n_described"] += 1; continue
        nb["desc"] = {k: b.get(k) for k in ("bot", "trigger", "action", "within_slots", "size", "notes", "exploit", "exploit_idea", "src")}
        nb["n_described"] = 1; uniq[nb["key"]] = nb
    print(f"behaviors: {len(raw)} described, {bad} not compilable, {len(uniq)} unique")
    BOT = json.load(open(f"{PO}/botids.json")); inv = {v[0]: (u, v[1]) for u, v in BOT.items()}
    res = []
    for key, nb in uniq.items():
        o = dict(key=key, bot=f"B{nb['bid']}", wallet=inv.get(nb["bid"], ("?", "?"))[0], family=inv.get(nb["bid"], ("?", "?"))[1], action=nb["action"], N=nb["N"],
                 self=nb["self"], conds=nb["R"]["conds"], event=nb["R"]["event"], size=nb["size"], n_described=nb["n_described"], desc=nb["desc"])
        for r in days: o[r] = verify(E.DAYS[r], nb, nb["R"])
        a2 = o["R2"]
        o["reliable_r2"] = (not nb["self"]) and a2.get("trig_on", 0) >= 50 and a2.get("hit", 0) >= 0.10 and (a2.get("lift") or 0) >= 5
        a3 = o["R3"]
        o["holds_r3"] = o["reliable_r2"] and a3.get("trig_on", 0) >= 50 and a3.get("hit", 0) >= 0.10 and (a3.get("lift") or 0) >= 5
        res.append(o)
    res.sort(key=lambda o: (-o["reliable_r2"], -(o["R2"].get("hit") or 0) * min(1, (o["R2"].get("trig_on") or 0) / 200)))
    json.dump(res, open(f"{PO}/bots_verified.json", "w"))
    rel = [o for o in res if o["reliable_r2"]]
    print(f"reliable on R2: {len(rel)}; of those also on R3: {sum(1 for o in rel if o['holds_r3'])}; self-initiated (activity only): {sum(1 for o in res if o['self'])}")
    for o in rel[:40]:
        a2, a3 = o["R2"], o["R3"]
        print(f"  {o['bot']:>5}({o['family']}) {o['wallet'][:8]} {o['action']:<4} <= {o['N']:>3} slots after {o['event']} {o['conds']} | R2 hit {a2.get('hit')} n {a2.get('trig_on')} lift {a2.get('lift')} delay {a2.get('delay_slots')} same {a2.get('same_slot')} idx {a2.get('idx_delay_same_slot_med')} | R3 hit {a3.get('hit')} n {a3.get('trig_on')} lift {a3.get('lift')}")
