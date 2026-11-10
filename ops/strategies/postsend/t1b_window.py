"""Task 1b: same-slot rate / send->seen by when in the slot we sent (ms after slot start, estimated feed clock) and by slot-in-leader-window.
MEASURED: t_send, first_rx, slots. ESTIMATED: slot start (idx extrapolation, slotclock.py)."""
import json,pickle,collections
rows=json.load(open('/home/it/sniper-data/postsend/t1_rows.json'))
SC=pickle.load(open('/home/it/sniper-data/postsend/slotclock.pkl','rb'))
runmap={'r49':'ams_r49','r50':'ams_r50','r51':'ams_r51','r52':'ams_r52','r53':'ams_r53','r54':'ams_r54','r55':'ams_r55_snap'}
def q(v,p):
    v=sorted(v); return v[min(len(v)-1,int(p*len(v)))] if v else float('nan')
R=[]
for r in rows:
    if r['reg']!='AMS' or r['run'] not in runmap or r['s2f'] is None or r['sas'] is None: continue
    st=SC[runmap[r['run']]]['start']
    s0=st.get(r['send_slot']); s1=st.get(r['send_slot']+1)
    if s0 is None: continue
    r['into']=(r['t_send']-s0)/1e6
    r['left']=(s1-r['t_send'])/1e6 if s1 else None
    # landing position inside landing slot
    ls=st.get(r['slot'])
    r['land_into']=(r['first_rx']-ls)/1e6 if ls else None
    R.append(r)
print('rows with slot clock',len(R))
CL=['AgaveBam','JitoLabs','HarmonicAgave','HarmonicFiredancer','Firedancer','FireBAM','Agave','Rakurai','Raiku']
def b(x):
    for e in (25,50,75,100,125,150,175,200,250): 
        if x<e: return f'<{e}'
    return '250+'
print('\n## same-slot % (n) by ms-into-slot at send (est. slot start), both paths; rows = leader client')
bk=['<25','<50','<75','<100','<125','<150','<175','<200','<250','250+']
print('| client | '+' | '.join(bk)+' |'); print('|---'*(len(bk)+1)+'|')
for c in CL+['ALL']:
    g=collections.defaultdict(list)
    for r in R:
        if c=='ALL' or r['client']==c: g[b(r['into'])].append(r)
    print(f'| {c} | '+' | '.join(f"{100*sum(1 for r in g[k] if r['sas']==0)/len(g[k]):.0f}% ({len(g[k])})" if g[k] else '-' for k in bk)+' |')
print('\n## send->seen p50 ms for SAME-SLOT landers by ms-into-slot at send (pure transit+scheduling, no slot wait)')
print('| client | '+' | '.join(bk)+' |'); print('|---'*(len(bk)+1)+'|')
for c in CL+['ALL']:
    g=collections.defaultdict(list)
    for r in R:
        if (c=='ALL' or r['client']==c) and r['sas']==0: g[b(r['into'])].append(r['s2f'])
    print(f'| {c} | '+' | '.join(f"{q(g[k],.5):.0f}" if len(g[k])>=20 else '-' for k in bk)+' |')
print('\n## sent in first 75 ms of the slot (no forced spill): per path x client')
print('| path | client | n | same-slot | send->seen p25/p50/p90 | same-slot only p50 | spill only p50 |'); print('|---|---|---|---|---|---|---|')
for p in ('helius-ps','astralane-ps'):
    for c in CL:
        v=[r for r in R if r['path']==p and r['client']==c and r['into']<75]
        if len(v)<50: continue
        s=[r['s2f'] for r in v]; ss=[r['s2f'] for r in v if r['sas']==0]; sp=[r['s2f'] for r in v if r['sas']>0]
        print(f"| {p} | {c} | {len(v)} | {100*len(ss)/len(v):.0f}% | {q(s,.25):.0f}/{q(s,.5):.0f}/{q(s,.9):.0f} | {q(ss,.5):.0f} | {q(sp,.5):.0f} |")
print('\n## slot position in the leader window (send_slot % 4), all clients, sent <75 ms into slot')
print('| client | pos0 | pos1 | pos2 | pos3 |'); print('|---|---|---|---|---|')
for c in CL[:6]+['ALL']:
    cells=[]
    for k in range(4):
        v=[r for r in R if (c=='ALL' or r['client']==c) and r['send_slot']%4==k and r['into']<75]
        cells.append(f"{100*sum(1 for r in v if r['sas']==0)/max(1,len(v)):.0f}% / {q([r['s2f'] for r in v],.5):.0f} ms ({len(v)})")
    print(f'| {c} | '+' | '.join(cells)+' |')
print('\n## where in its landing slot our tx shows up (ms after est. slot start), same-slot landers sent <25 ms into slot')
for c in CL[:6]:
    v=[r['land_into'] for r in R if r['client']==c and r['sas']==0 and r['into']<25 and r['land_into'] is not None]
    print(c, len(v), 'p50', round(q(v,.5),1))
json.dump([{k:r[k] for k in ('run','path','client','into','left','s2f','sas','idx','res','send_slot','land_into')} for r in R],open('/home/it/sniper-data/postsend/t1b_rows.json','w'))
