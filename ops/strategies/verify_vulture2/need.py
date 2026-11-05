# VERIFY VULTURE-2: reproduce score2 headline, then re-score the frozen picks on OUR block-position clock with measured
# FRA reactive landing distributions, with/without 8yYMhu kept on the tape, cost + follower stresses.
# Read-only on /home/moiz/sniper-vulture2 (imports its sim/ev/gbm with bytecode writing disabled).
# usage: python3 -B rescore.py  > /home/moiz/sniper-data/verify_vulture2/rescore.txt
import sys; sys.dont_write_bytecode = True
import pickle, json, hashlib, bisect, collections, numpy as np, datetime as Dt
V = '/home/moiz/sniper-vulture2/'; OUT = '/home/moiz/sniper-data/verify_vulture2/'
sys.path.insert(0, V); import sim, ev, gbm
LAT_RAW = np.load('/home/moiz/sniper-data/ld247/fra_lat.npy')   # 963 measured FRA reactive landings, slots, block clock (as sniper-m2v4/sim.py)
def m2pen(S): return max(13.62 * S + 10.38 * S * S, -4.4 + 28.1 * S) / 1e3   # copy of sniper-m2v4/sim.py pen()
K = sim.K; FEE = sim.FEE; smax = sim.smax; MAXI = sim.S; W = sim.W

assert hashlib.sha256(open(V + 'VULTURE_v2.json', 'rb').read()).hexdigest() == 'b8d8c8311a5698dc9de081c623e6665a13046ccfc9c97fd878e471604a1492b0'
cfg = json.load(open(V + 'VULTURE_v2.json'))
assert hashlib.sha256(open(V + cfg['model_file'], 'rb').read()).hexdigest() == cfg['model_sha256']
m2 = pickle.load(open(V + cfg['model_file'], 'rb'))
LATS = [30, 50, 66, 80, 93, 123]; REAL = [16, 27, 35, 43, 50, 66]
Call = pickle.load(open(V + 'data/cands.pkl', 'rb')); Pall = pickle.load(open(V + 'data/paths_30_50_66_80_93_123.pkl', 'rb'))
TEND = max(c['slot'] for c in Call)
ok = [i for i, c in enumerate(Call) if cfg['splits']['fresh_from_slot'] <= c['slot'] <= TEND - 10]
C = [Call[i] for i in ok]; P = [Pall[i] for i in ok]; del Call, Pall
o = np.argsort([c['slot'] * 10**6 + c['idx'] for c in C], kind='stable'); C = [C[i] for i in o]; P = [P[i] for i in o]
sl = np.array([c['slot'] for c in C]); Dd = (sl.max() - sl.min()) * 0.2144 / 86400
X = np.array([[float(c[f]) if c[f] is not None else -1 for f in m2['F']] for c in C]); B = np.column_stack([np.searchsorted(m2['E'][j], X[:, j]) for j in range(X.shape[1])])
f2 = np.full(len(C), m2['init'])
for t in m2['T']: f2 += 0.05 * gbm.pred(t, B)
sol = np.array([c['sol'] for c in C]); drop = np.array([c['drop'] for c in C])
I = np.where((sol >= 0.3) & (drop >= 3) & (f2 >= cfg['select']['score_thr']))[0]
E = cfg['size']['edges']; Z = np.array([cfg['size']['sizes'][int(np.searchsorted(E, f2[i]))] for i in I])
EX = dict(tp=cfg['exit']['tp'], hold=cfg['exit']['hold_slots'])
pr = lambda *a: print(*a, flush=True)
pr(f'# FRESH {Dd:.3f} d ({Dd*24:.1f} h), {len(C)} cand rows, v2 picks {len(I)}; size mix', collections.Counter(Z.tolist()))

# ---------- 3. own path builder on the block clock ----------
TS0, KEY0 = sim.TS, sim.KEYS                       # their tape (8yYMhu removed)
mints = {C[i]['m'] for i in I}
T_all = pickle.load(open(V + 'data/tape_all.pkl', 'rb'))[0]
TSW = {m: sorted(T_all[m], key=lambda r: (r[0], r[1])) for m in mints}; KEYW = {m: [(r[0], r[1]) for r in l] for m, l in TSW.items()}
del T_all
CAP = 7
def mkpath(TS, KEY, m, s, six, frac, spill='block', inslot_cut=False):
    """entry at dump clock + frac (slots) on the block-position clock; returns ev-style path or None (spill)"""
    n = MAXI.get(s, smax[s]) + 1
    lix = six + frac * n
    if spill == 'block' and lix > n - 1: return None
    if spill == 'theirs' and lix > smax[s]: return None
    l = TS[m]; KY = KEY[m]
    k0 = bisect.bisect_left(KY, (s, six + 1)); vpost = K / (l[k0-1][6] if k0 > 0 else 1073e12)
    k = bisect.bisect_left(KY, (s, lix)); vt = l[k-1][6] if k > 0 else 1073e12; vs = K / vt
    so = []; ix = []; cp = []; cn = []; Pp = Nn = 0.0; j = k
    while j < len(l) and len(so) < 300:
        r = l[j]
        if r[0] > s + CAP: break
        prev = l[j-1][6] if j > 0 else 1073e12; d = K / r[6] - K / prev
        if d > 0:
            if not (inslot_cut and r[0] == s): Pp += d
        else: Nn += d
        so.append(r[0]); ix.append(r[1]); cp.append(Pp); cn.append(Nn); j += 1
    return (vs / vpost, vt, np.array(so, np.int64) - s, np.array(ix, np.float32), np.array(cp, np.float32), np.array(cn, np.float32), None)

def trip1(i, z, frac, fol=1.0, tape='theirs', inslot_cut=False, spill='block'):
    c = C[i]; s = c['slot']
    TS, KEY = (TS0, KEY0) if tape == 'theirs' else (TSW, KEYW)
    p = mkpath(TS, KEY, c['m'], s, c['idx'], frac, spill, inslot_cut)
    lat_eq = frac * (MAXI.get(s, smax[s]) + 1) * 400 / max(smax[s], 600)   # their ms2idx-equivalent for the exit leg
    r, _ = ev.trip(p, s, lat_eq, z, fol, **EX)
    if p is not None and r != -ev.FAIL:   # recover gross (uncalibrated) for cost variants
        g = (r + ev.PF + ev.C2) / ev.CAL
        return True, g
    return False, 0.0

def score(fracs, w=None, **kw):
    """expected per-pick (fill prob, gross-if-fill-weighted) over latency samples"""
    w = np.ones(len(fracs)) / len(fracs) if w is None else w
    F = np.zeros(len(I)); G = np.zeros(len(I))
    for q, i in enumerate(I):
        for fr, ww in zip(fracs, w):
            f, g = trip1(i, Z[q], fr, **kw)
            if f: F[q] += ww; G[q] += ww * g
    return F, G

def net(F, G, cal='sym', pf=0.003 + 0.0002, fail=0.0004, pen=0.0):
    if cal == 'sym': g = G * ev.CAL
    else: g = np.where(G > 0, G * ev.CAL, G)      # haircut only the wins
    return g - (pf + pen) * F - fail * (1 - F)

def summ(F, G, lab, **kw):
    a = net(F, G, **kw)
    t = collections.defaultdict(float)
    for q, i in enumerate(I): t[C[i]['m']] += a[q]
    top5 = sum(sorted(t.values())[-5:])
    s = np.sort(a)
    return f'| {lab} | {a.sum()/Dd:+.1f} | {(a.sum()-top5)/Dd:+.1f} | {s[:int(len(s)*0.95)].sum()/Dd:+.1f} | {F.sum()/Dd:.0f} | {100-100*F.mean():.0f} |'

HDR = '| scenario | SOL/day | w/o top5 tokens | w/o top5% trades | fills/day | fail% |\n|---|---|---|---|---|---|'
FRA = np.asarray(LAT_RAW, float)             # slots, 963 measured FRA reactive landings (block clock)
fra12 = np.quantile(FRA, (np.arange(12) + 0.5) / 12)
r29 = []
for l in open('/home/moiz/sniper-data/runs/fra_r29/dip_r29.jsonl'):
    if '"timing"' not in l: continue
    d = json.loads(l); c2 = d.get('clock2') or {}
    if c2.get('land_ms_pos') is not None: r29.append(c2['land_ms_pos'] / d.get('slot_ms', 214.477))
r29 = np.array(r29)
pr('## needed speed: FRA-shaped distribution rescaled to a target median (block clock), their tape')
pr(HDR)
for med in (25, 35, 45, 52, 61):
    fr = fra12 * (med / (np.median(FRA) * 212.07))
    F, G = score(fr); pr(summ(F, G, f'FRA shape, median {med} ms'))
    pr(summ(F, G, f'FRA shape, median {med} ms, cal wins only + 4.9/0.78 mSOL', cal='win', pf=0.0049, fail=0.00078))
    F8, G8 = score(fr, fol=0.8); pr(summ(F8, G8, f'FRA shape, median {med} ms, followers -20%'))
pr('DONE')
