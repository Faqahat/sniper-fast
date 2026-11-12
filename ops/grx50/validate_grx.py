#!/usr/bin/env python3
"""dip50 GRX offline validation: recompute the engine's rule (psgrx50.rs eval()) from the run logs and compare with the research flags.

Mirror of the Rust rule, on the logged presend_live_fill record of the FIRST fill of each window:
  candidates = ann.holders[] (the engine's holder_clocks: >= 2% of supply, ours out, top 12 by holding, at the fill slot)
  member     = h.w != trigger whale and h.risk >= 5 and h.hz3 >= 0.3 and h.age <= since
  since      = fill.slots_after_trigger (= fill slot - the window's trig_slot, the engine's own number; cross-checked against
               fill.slot - arm.trig.slot, the research's derivation)
  ent_pct    = sum of the members' pct in the logged order; would_exit = kind == t2 and ent_pct >= 2.245
Research: /home/it/sniper-data/grouprisk2/feat2.pkl column Ln_g (m5_entrants.py), rule "Ln_g >= 2.245" on T2 fills.
"""
import json, os, sys, collections, pickle
THR = 2.245
RUNS = range(65, 91)
def path(r):
    return {89: '/home/it/sniper-data/runs/ams_r89/r89_now.jsonl', 90: '/home/it/sniper-data/runs/ams_r90/r90_now.jsonl'}.get(r, f'/home/it/sniper-data/runs/ams_r{r}/dip_ams_r{r}.jsonl')

def rule(holders, whale, since):
    """psgrx50::eval"""
    ent = 0.0; mem = []; old = 0.0; whale_member = False
    for h in holders:
        if not (h['risk'] >= 5 and h['hz3'] >= 0.3): continue
        if h['w'] == whale: whale_member = True; continue
        if h['age'] <= since: ent += h['pct']; mem.append(h)
        else: old += h['pct']
    return ent, mem, old, whale_member

def load(r):
    f = path(r)
    if not os.path.exists(f): return []
    F = {}; R = collections.defaultdict(float); A = {}; X = {}
    for l in open(f, errors='ignore'):
        if '"presend_live_fill"' in l:
            x = json.loads(l)
            if x.get('ev') == 'presend_live_fill' and x['w'] not in F: F[x['w']] = x
        elif '"presend_live_realized"' in l:
            x = json.loads(l); R[x['w']] += x['pnl'] / 1e9
        elif '"ev":"presend_live_arm"' in l:
            x = json.loads(l); A[x['w']] = x
        elif '"ev":"presend_live_exit"' in l:
            x = json.loads(l); X.setdefault(x['w'], x)
    out = []
    for w, x in F.items():
        a = x.get('ann') or {}; ar = A.get(w) or {}
        kind = x.get('kind') or ar.get('kind') or 't2'
        tr = ar.get('trig') or {}; du = ar.get('dump') or {}
        whale = tr.get('wallet') or du.get('seller')
        trig_slot = tr.get('slot') or du.get('slot')
        hl = a.get('holders')
        since = x.get('slots_after_trigger')
        since_arm = (x['slot'] - trig_slot) if trig_slot else None
        o = dict(run=r, w=w, kind=kind, mint=x['mint'], slot=x['slot'], whale=whale, since=since, since_arm=since_arm, has_ann=hl is not None, pnl=R.get(w), realized=w in R,
                 exit=(X.get(w) or {}).get('why'), held=(X.get(w) or {}).get('slots_held'), sol=(x.get('sol_in') or 0) / 1e9)
        if hl is not None and whale is not None and since is not None:
            ent, mem, old, wm = rule(hl, whale, since)
            o.update(ent_pct=ent, ent_n=len(mem), old_pct=old, whale_member=wm, would_exit=(kind == 't2' and ent >= THR), over=ent >= THR,
                     members=[(h['w'][:8], round(h['pct'], 2), h['age'], h['risk'], round(h['hz3'], 2)) for h in mem])
            if since_arm is not None and since_arm != since:
                o['ent_pct_arm'] = rule(hl, whale, since_arm)[0]
        out.append(o)
    return out

rows = []
for r in RUNS: rows += load(r)
print(f'fills (first per window) r65-r90: {len(rows)}; with ann.holders + trigger: {sum(1 for o in rows if "ent_pct" in o)}')
mis = [o for o in rows if o['since'] is not None and o['since_arm'] is not None and o['since'] != o['since_arm']]
print(f'since: fill.slots_after_trigger != fill.slot - arm.trig.slot on {len(mis)} fills ({collections.Counter(o["kind"] for o in mis)})')
for o in mis[:8]: print('   ', o['run'], o['w'], o['kind'], 'since', o['since'], 'arm-derived', o['since_arm'], 'ent', round(o.get('ent_pct', -1), 3), 'ent(arm)', round(o.get('ent_pct_arm', -1), 3))

# ---- agreement with the research (r65-r84) -----------------------------------------------------------------------------------
try:
    import pandas as pd
    D = pd.read_pickle('/home/it/sniper-data/grouprisk2/feat2.pkl')
    res = {(int(x.run), int(x.w)): x for x in D.itertuples()}
    for lab, lo, hi in [('r65-r84', 65, 84), ('r85-r90', 85, 90)]:
        n = agree = both = only_me = only_res = 0; missing = 0; maxd = 0.0; bad = []
        for o in rows:
            if not (lo <= o['run'] <= hi) or o['kind'] != 't2' or 'ent_pct' not in o: continue
            x = res.get((o['run'], o['w']))
            if x is None or x.Ln_g != x.Ln_g: missing += 1; continue
            n += 1; a = o['ent_pct'] >= THR; b = x.Ln_g >= THR
            maxd = max(maxd, abs(o['ent_pct'] - x.Ln_g))
            agree += a == b; both += a and b; only_me += a and not b; only_res += b and not a
            if a != b or abs(o['ent_pct'] - x.Ln_g) > 1e-9: bad.append((o['run'], o['w'], o['ent_pct'], x.Ln_g, o['since'], o['since_arm']))
        print(f'AGREEMENT {lab} T2 fills with holders: {agree}/{n} = {agree / max(n, 1):.4%} | flagged by both {both}, only this script {only_me}, only research {only_res} | max |ent_pct - Ln_g| {maxd:.3g} | not in research table {missing}')
        for b in bad[:10]: print('    differs:', b)
    # the research's scored set (T2, non-A, grp logged): the flagged count it reported
    T = D[(D.kind == 't2') & (~D.A) & D.grp.notna() & (D.run <= 84)]
    mine = {(o['run'], o['w']) for o in rows if o.get('would_exit')}
    f_res = {(int(x.run), int(x.w)) for x in T.itertuples() if x.Ln_g >= THR}
    f_me = {(int(x.run), int(x.w)) for x in T.itertuples() if (int(x.run), int(x.w)) in mine}
    print(f'research scored set r65-r84 (T2 non-A, grp logged): {len(T)} fills, research flags {len(f_res)}, this script flags {len(f_me)}, same set: {f_res == f_me}')
    try:
        E = pd.read_pickle('/home/it/sniper-data/grouprisk2/feat_exit.pkl')
        L = E[(E.kind == 't2') & (~E.A)]
        b = L[[(int(x.run), int(x.w)) in mine for x in L.itertuples()]]
        print(f'exit-sim set (tape): {len(L)} T2 non-A fills, flagged here {len(b)}: sim x1 - base {((b.x1 - b.base).sum()):+.3f}, x1 - x4 {((b.x1 - b.x4).sum()):+.3f}, x1 - x6 {((b.x1 - b.x6).sum()):+.3f} SOL')
    except Exception as e: print('feat_exit.pkl:', e)
except Exception as e:
    print('research table not compared:', repr(e))

# ---- r85-r90: the T2 fills the rule flags, with their real P&L ---------------------------------------------------------------------
print('\nr85-r90 T2 fills: flagged (would_exit) with real P&L')
tot = collections.defaultdict(lambda: [0, 0.0, 0, 0.0])
for o in rows:
    if o['run'] < 85 or o['kind'] != 't2' or 'ent_pct' not in o: continue
    t = tot[o['run']]; p = o['pnl'] or 0.0
    t[2] += 1; t[3] += p
    if o['would_exit']:
        t[0] += 1; t[1] += p
        print(f"  r{o['run']} w{o['w']} {o['mint']} since {o['since']} ent {o['ent_pct']:.2f}% n{o['ent_n']} old {o['old_pct']:.1f}% pnl {('%+.4f' % o['pnl']) if o['realized'] else 'n/a'} SOL (in {o['sol']:.2f}) exit {o['exit']} held {o['held']} | {o['members']}")
for r in sorted(tot):
    t = tot[r]; print(f'  r{r}: flagged {t[0]}/{t[2]} T2 fills, flagged P&L {t[1]:+.4f} SOL, all T2 P&L {t[3]:+.4f} SOL')
a = [sum(t[i] for t in tot.values()) for i in range(4)]
print(f'  r85-r90 total: flagged {a[0]}/{a[2]} T2 fills, flagged real P&L {a[1]:+.4f} SOL, unflagged {a[3] - a[1]:+.4f} SOL')
ra = [o for o in rows if o['run'] >= 85 and o['kind'] == 'rearm' and 'ent_pct' in o]
print(f"  re-arm r85-r90 (log only, never acts): {len(ra)} fills, over the threshold {sum(1 for o in ra if o['over'])}, their P&L {sum((o['pnl'] or 0) for o in ra if o['over']):+.4f} SOL")
json.dump([{k: v for k, v in o.items()} for o in rows], open('/home/it/sniper-data/dip50/validate_grx_rows.json', 'w'))
