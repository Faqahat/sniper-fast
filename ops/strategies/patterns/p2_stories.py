#!/usr/bin/env python3
# Tape stories for the LLM (read-only): ~2,000 tokens per day, stratified (dumps, quiet spells, big buys, creator activity,
# near graduation, random). Each story is a compact time-bucketed account of the token's bonding-curve trading
# (<= ~1.5k tokens): per bucket price change %, curve SOL, buys/sells n and SOL, distinct wallets, and notable trades
# (>= 0.5 SOL, or by an ID'd bot) with slot offset, size, price impact and wallet type: creator / insider (create slot) /
# new (first seen < 10 min) / B<id>(<family>) for the 500 stable bot IDs / F# or bot (R2-only lists) / w (other).
# Header: launch label (theme, X link, effort, fun), create time PKT, creator buy, insiders, life summary.
# -> patterns/stories_{R2,R3}.jsonl  {id, m, strata, focus_bot, text}
import sys, json, random, collections, time
import numpy as np
PO = "/home/moiz/sniper-data/strategies/patterns"
WTN = {0: "w", 1: "creator", 2: "insider", 3: "new", 4: "bot", **{10 + k: f"F{k}" for k in range(1, 11)}}
BOT = {v[0]: v[1] for v in json.load(open(f"{PO}/botids.json")).values()}
EDGES = [0, 1, 5, 15, 30, 60, 120, 180, 240, 300, 420, 600, 900, 1200, 1800, 2700, 4200, 6000, 9000, 14000, 20000, 10 ** 9]

def load(run):
    z = np.load(f"{PO}/day_{run}.npz"); M = json.load(open(f"{PO}/day_{run}_meta.json"))
    return z, M

def who(wt, bid):
    if bid: return f"B{bid}({BOT.get(int(bid), 'bot')})"
    return WTN.get(int(wt), "w")

def story(run, ti, z, M, F, FI, off, cnt, sid, strata):
    me = M["meta"][ti]; a, b = off[ti], off[ti] + cnt[ti]
    S0 = me["S0"]; s = z["s"][a:b]; buy = z["buy"][a:b]; sol = z["sol"][a:b] / 1e9; V = z["vsol"][a:b] / 1e9; T = z["vtok"][a:b]
    wt = z["wt"][a:b]; bid = z["bid"][a:b]; move = F[a:b, FI["move"]]; age = s - S0
    p = z["vsol"][a:b] / T
    th = M["themes"][int(F[a, FI["theme"]])] if F[a, FI["theme"]] >= 0 else "?"
    xl = M["xl"][int(F[a, FI["x"]])] if F[a, FI["x"]] >= 0 else "?"
    eff = int(F[a, FI["eff"]]); fun = int(F[a, FI["fun"]])
    cre_buy = sol[(wt == 1) & (buy == 1) & (age == 0)].sum(); ins = (wt == 2) & (buy == 1) & (age == 0)
    created = time.strftime("%m-%d %H:%M", time.gmtime((me["cbt"] or 0) + 5 * 3600))
    users_n = int(F[b - 1, FI["nwal"]])
    hdr = (f"T{sid} [{','.join(strata)}] theme={th} x={xl} effort={eff} fun={fun} | created {created} PKT | creator buy {cre_buy:.2f} SOL, "
           f"create-slot insiders {int(ins.sum())} ({sol[ins].sum():.2f} SOL) | life {b - a} trades, {users_n} wallets, {int(age[-1])} slots, peak curve {V.max():.0f} SOL{', GRADUATED' if V.max() >= 113 else ''}")
    lines = [hdr, "age_slots | price% | curve | buys n/SOL | sells n/SOL | new wallets | notable (@slot side SOL who price-impact%)"]
    p_prev = p[0] / (1 + move[0] / 100) if move[0] > -99 else p[0]
    last_s = None; nnote = 0; rows = 0
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        k = np.flatnonzero((age >= lo) & (age < hi))
        if not len(k): continue
        if last_s is not None and age[k[0]] - last_s >= 50:
            lines.append(f"  ... quiet {age[k[0]] - last_s} slots ({(age[k[0]] - last_s) * 0.212:.0f} s) ...")
        pe = p[k[-1]]
        nb = int(buy[k].sum()); ns = len(k) - nb
        sel = [q for q in k if sol[q] >= 0.5 or bid[q]]
        if len(sel) > 7: sel = sorted(sorted(sel, key=lambda q: -sol[q] - (0.3 if bid[q] else 0))[:7])
        notes = " ".join(f"@{age[q]} {'B' if buy[q] else 'S'}{sol[q]:.2f} {who(wt[q], bid[q])}{move[q]:+.0f}%" for q in sel)
        nnote += len(sel); rows += 1
        lines.append(f"{lo}-{hi if hi < 10 ** 9 else 'end'} | {(pe / p_prev - 1) * 100:+.0f}% | {V[k[-1]]:.0f} | {nb}/{sol[k][buy[k] == 1].sum():.2f} | {ns}/{sol[k][buy[k] == 0].sum():.2f} | "
                     f"{int(F[a + k[-1], FI['nwal']] - (F[a + k[0] - 1, FI['nwal']] if k[0] > 0 else 0))} | {notes}")
        p_prev = pe; last_s = age[k[-1]]
        if rows >= 26 or nnote >= 110: lines.append("  ... (truncated)"); break
    return "\n".join(lines)

def build(run, n_per=330, n_rand=300, seed=11):
    z, M = load(run); F = z["F"]; FI = {k: i for i, k in enumerate(M["feats"])}
    tok = z["tok"]; nt = len(M["meta"])
    cnt = np.bincount(tok, minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    S = z["s"]; buy = z["buy"]; sol = z["sol"] / 1e9; wt = z["wt"]; move = F[:, FI["move"]]; quiet = F[:, FI["quiet"]]; V = z["vsol"] / 1e9
    age = F[:, FI["age"]]
    def anyt(mask):
        r = np.zeros(nt, bool); r[np.unique(tok[mask])] = True; return r
    act = cnt >= 10
    strata = {
        "dump": anyt((buy == 0) & (sol >= 1.0) & (move <= -8)) & act,
        "quiet_then_buy": anyt((buy == 1) & (sol >= 0.5) & (quiet >= 50) & (age >= 150)) & act,
        "big_buy": anyt((buy == 1) & (sol >= 2.0)) & act,
        "creator_sells": anyt((wt == 1) & (buy == 0) & (age <= 300)) & act,
        "near_grad": anyt(V >= 90) & act}
    rnd = random.Random(seed); chosen = collections.OrderedDict()
    for name, m in strata.items():
        idx = [int(i) for i in np.flatnonzero(m)]; rnd.shuffle(idx)
        for i in idx[:n_per]: chosen.setdefault(i, []).append(name)
    pool = [int(i) for i in np.flatnonzero(cnt >= 5) if int(i) not in chosen]; rnd.shuffle(pool)
    for i in pool[:n_rand]: chosen.setdefault(i, []).append("random")
    # tag all strata a chosen token belongs to
    for i in chosen:
        for name, m in strata.items():
            if m[i] and name not in chosen[i]: chosen[i].append(name)
    out = []
    bidall = z["bid"]
    for sid, (ti, st) in enumerate(chosen.items()):
        a, b = off[ti], off[ti] + cnt[ti]
        bc = collections.Counter(int(x) for x in bidall[a:b] if x)
        focus = bc.most_common(1)[0][0] if bc else 0
        out.append(dict(id=f"{run}-{sid}", m=M["meta"][ti]["m"], ti=int(ti), strata=st, focus_bot=focus, bots=sorted(bc),
                        text=story(run, ti, z, M, F, FI, off, cnt, f"{run[1]}{sid}", st)))
    with open(f"{PO}/stories_{run}.jsonl", "w") as f:
        for o in out: f.write(json.dumps(o) + "\n")
    L = [len(o["text"]) for o in out]
    print(f"{run}: {len(out)} stories; strata {collections.Counter(s for o in out for s in o['strata'])}; chars p50 {sorted(L)[len(L) // 2]} p90 {sorted(L)[int(len(L) * .9)]} max {max(L)}")

if __name__ == "__main__":
    for run in sys.argv[1:] or ["R2", "R3"]: build(run)
