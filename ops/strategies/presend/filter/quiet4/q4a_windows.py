#!/usr/bin/env python3
"""QUIET4 step 4a [MEASURED, read-only]: the 24 earlier live runs (QUIET3's set; AMS r36 now from the COMPLETE local copy) -> one row per
live pre-send ARM (signals if logged, landed failed tries, fill, realized P&L) and per censored QUIET skip. Same as quiet3/w1_windows.py
plus: failed tries counted per window from presend_attempt_land (unique signatures; 6042 / deadline / ata_exists / 6005 = landed
failed, 5120 lamports each), the v2 annotation when logged, the run's session spans (hours).
Out: /home/moiz/sniper-data/presend_quiet4/windows24.json"""
import json, collections, re
L = '/home/moiz/sniper-data/runs'; V = '/home/moiz/sniper-data/presend_losses/verify/raw'
OUT = '/home/moiz/sniper-data/presend_quiet4/windows24.json'
runs = [('FRA', f'r{n}', f'{L}/fra/runs/dip_r{n}.jsonl') for n in (21, 22, 23, 24, 26, 27, 28)]
runs += [('AMS', f'r{n}', f'{L}/ams/runs/dip_ams_r{n}.jsonl') for n in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36)]
runs += [('AMS', f'r{n}', f'{V}/dip_ams_r{n}.jsonl') for n in (28, 29, 30, 31, 32, 33)]
FAILRES = None  # any landed result but ok / unseen


def main():
    W = []; SK = []; meta = {}
    for reg, r, p in runs:
        seg = 0; win = {}; qcfg = None; nsk = collections.Counter(); att = {}; land = {}; spans = []; seg_t0 = None; last_t = None; lcfg = None
        for line in open(p, errors='ignore'):
            if '"ev":"' not in line: continue
            if not ('presend_live' in line or '"run_start"' in line or 'presend_attempt' in line): continue
            try: d = json.loads(line)
            except Exception: continue
            ev = d.get('ev'); t = d.get('t')
            if isinstance(t, (int, float)) and t > 1e18:
                if ev == 'run_start':
                    if seg_t0 is not None and last_t is not None: spans.append((seg_t0, last_t))
                    seg_t0 = t
                last_t = t if last_t is None else max(last_t, t)
            if ev == 'run_start':
                seg += 1; lcfg = d.get('presend_live') or lcfg
                q = json.dumps(d)
                if '"quiet"' in q and qcfg is None:
                    m = re.search(r'"quiet":\s*(\{[^{}]*\})', q); qcfg = json.loads(m.group(1)) if m else True
                continue
            k = (seg, d.get('w'))
            if ev == 'presend_live_arm':
                tg = d['trig']
                win[k] = dict(reg=reg, run=r, seg=seg, w=d['w'], mint=tg['mint'], whale=tg['wallet'], t=tg['t'], slot=tg['slot'], idx=tg['idx'], j=tg.get('j', 0),
                              age=tg.get('age_slots'), pct=tg.get('pct'), wsol=tg['sol'] / 1e9, size=d['spend'] / 1e9, q=d.get('quiet'), v2=d.get('v2'), att=0, filled=False,
                              pnl=None, fill_off=None, why=None, en_slot=d.get('en_slot'), sigs=[])
            elif ev == 'presend_attempt':
                if d['sig'] not in att: att[d['sig']] = (seg, d.get('w'))
            elif ev == 'presend_attempt_land':
                o = land.get(d['sig'])
                if o is None or (o == 'unseen' and d.get('res') != 'unseen'): land[d['sig']] = d.get('res')
            elif ev == 'presend_live_fill' and k in win:
                x = win[k]
                if not x['filled']: x['filled'] = True; x['fill_off'] = d.get('slots_after_trigger'); x['fill_slot'] = d.get('slot'); x['fill_idx'] = d.get('idx')
            elif ev == 'presend_live_realized' and k in win:
                x = win[k]; x['pnl'] = (x['pnl'] or 0) + d['pnl'] / 1e9
            elif ev == 'presend_live_disarm' and k in win:
                x = win[k]; x['att'] = d.get('attempts', 0); x['why'] = d.get('why'); x['dis_slot'] = d.get('slot'); x['dis_t'] = d.get('t')
            elif ev == 'presend_live_skip':
                nsk[d.get('why')] += 1
                if d.get('why') in ('quiet', 'young_age'):
                    tg = d['trig']
                    SK.append(dict(reg=reg, run=r, seg=seg, why=d['why'], mint=tg['mint'], whale=tg['wallet'], t=tg['t'], slot=tg['slot'], idx=tg['idx'], j=tg.get('j', 0),
                                   age=tg.get('age_slots'), q=d.get('quiet'), v2=d.get('v2')))
        if seg_t0 is not None and last_t is not None: spans.append((seg_t0, last_t))
        nf = collections.Counter()
        for sig, kk in att.items():
            res = land.get(sig)
            if res is not None and res not in ('unseen', 'ok'): nf[kk] += 1
        for kk, x in win.items(): x['n_fail'] = nf.get(kk, 0)
        W += list(win.values())
        hours = sum((b - a) for a, b in spans) / 3.6e12
        meta[r + reg] = dict(qcfg=qcfg, skips=dict(nsk), arms=len(win), segs=seg, hours=hours, t0=spans[0][0] if spans else None, t1=spans[-1][1] if spans else None,
                             stop=(qcfg or {}).get('stop') if isinstance(qcfg, dict) else None, min_age=(lcfg or {}).get('min_age_slots'))
        fills = [x for x in win.values() if x['pnl'] is not None]
        print(reg, r, f"{hours:.2f} h", 'arms', len(win), 'fills', len(fills), 'pnl %+.3f' % sum(x['pnl'] for x in fills), 'failed tries', sum(nf.values()),
              'quiet' if qcfg else '-', dict(nsk), flush=True)
    json.dump(dict(windows=W, skips=SK, meta=meta), open(OUT, 'w'))


if __name__ == '__main__':
    main()
