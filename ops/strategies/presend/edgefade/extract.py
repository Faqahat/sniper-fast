# Stream a run jsonl; write compact records for analysis. Read-only on input.
import json, sys
src, dst = sys.argv[1], sys.argv[2]
KEEP = ('"ev":"presend_attempt_land"', '"ev":"presend_arm"', '"ev":"presend_fill"', '"ev":"presend_exit"',
        '"ev":"presend_disarm"', '"ev":"dump"', '"ev":"run_start"', '"ev":"run_end"', '"ev":"presend_skip"')
def tr(x):
    return [x.get('user'), x.get('buy'), x.get('sol'), x.get('slot'), x.get('p_rel'), x.get('t')]
out = open(dst, 'w')
with open(src, 'rb') as f:
    for raw in f:
        l = raw.decode('utf-8', 'replace')
        hit = None
        for k in KEEP:
            if k in l:
                hit = k; break
        if not hit: continue
        d = json.loads(l)
        ev = d.get('ev')
        if ev == 'presend_attempt_land':
            o = {k: d.get(k) for k in ('t','t_send','mint','res','err','kind','ms_send_to_rx','ms_after_d_rx','n_between','slots_after_send','path','client','sig','slot','send_slot','n','lim','p_sign')}
            dd = d.get('d') or {}
            o['d'] = {k: dd.get(k) for k in ('drop_pct','sol','user','slot','t','buy')}
            o['between'] = [tr(x) for x in (d.get('between') or [])]
            o['after'] = [tr(x) for x in (d.get('after') or [])]
            o['ev'] = ev
        elif ev == 'dump':
            o = {k: d.get(k) for k in ('ev','t','mint','drop_pct','sell','age','launch_ok','pass','vsol','slot')}
        elif ev in ('presend_fill',):
            o = {k: d.get(k) for k in ('ev','mint','row','drop_pct','n_ahead','slots_after_trigger','p_m','p_x','ref','lim','s_in','w','seller_is_whale','d_ms','ft')}
            e = d.get('entry') or {}
            o['entry'] = {k: e.get(k) for k in ('p_avg','p_before','sol_in')}
            o['t'] = (d.get('m') or {}).get('t')
        else:
            o = d
        out.write(json.dumps(o, separators=(',',':')) + '\n')
out.close()
