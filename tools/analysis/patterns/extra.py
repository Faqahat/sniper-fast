exec(open('analyze.py').read().split('out = []')[0])
import collections
q2=lambda v,p: q(v,p)
G=[w for w in A if w['gross']>=1e7]
print('gross>=0.01:', len(G), round(sum(w['gross'] for w in G)/1e9,2), 'net', round(sum(w['gain'] for w in G)/1e9,2), 'bid', round(sum(w['bid'] for w in G)/1e9,2))
for svc in ('no tip','jito','other'):
    ws=[w for w in G if (w['svc']==svc if svc!='other' else w['svc'] not in ('no tip','jito'))]
    print(svc, len(ws), 'gross',round(sum(w['gross'] for w in ws)/1e9,2), 'bid share of gross', round(sum(w['bid'] for w in ws)/max(1,sum(w['gross'] for w in ws)),2), 'gap p50', q([w['dt'] for w in ws],.5), 'same-slot', round(sum(1 for w in ws if w['prev_slot']==w['slot'])/max(1,len(ws)),2), '>=150ms', sum(1 for w in ws if (w['dt'] or 0)>=150 and w['n_watched']>=2), round(sum(w['gross'] for w in ws if (w['dt'] or 0)>=150 and w['n_watched']>=2)/1e9,3))
S150=[w for w in G if w['n_watched']>=2 and (w['dt'] or 0)>=150]
print('gross>=0.01 & gap>=150 & 2 legs:', len(S150), 'gross', round(sum(w['gross'] for w in S150)/1e9,3), 'net', round(sum(w['gain'] for w in S150)/1e9,3), 'per h', round(len(S150)/H,1), round(sum(w['gross'] for w in S150)/1e9/H,3))
print(' bots', collections.Counter(w['signer'][:8] for w in S150).most_common(6), 'svc', collections.Counter(w['svc'] for w in S150).most_common(4), 'size p50', q([w['size'] for w in S150],.5))
es=[w for w in A if w['signer'].startswith('ESuvjvsQ')]
print('ESuvjvsQ wins', len(es), 'gross', round(sum(w['gross'] for w in es)/1e9,2), 'gap p50', q([w['dt'] for w in es],.5), 'same slot', sum(1 for w in es if w['prev_slot']==w['slot']), 'vp', collections.Counter(w['vp'] for w in es).most_common(3), 'size', q([w['size'] for w in es],.5))
# small jito wins by gap age and venue
sj=[w for w in A if w['gain']<1e7 and w['svc']=='jito']
for lo,hi in ((0,20),(20,50),(50,150),(150,300),(300,1e9)):
    ws=[w for w in sj if w['dt'] is not None and lo<=w['dt']<hi]
    print('small jito gap',lo,hi,len(ws), round(len(ws)/H), 'SOL', round(sum(w['gain'] for w in ws)/1e9,3), 'tip p50', q([w['tip'] for w in ws],.5), 'tip/gross', round(q([w['tip']/w['gross'] for w in ws if w['gross']>0],.5) or 0,2), 'gain p50', q([w['gain'] for w in ws],.5))
sm=[w for w in A if w['gain']<1e7]
ws=[w for w in sm if (w['dt'] or 0)>=150 and w['n_watched']>=2]
print('small >=150ms 2 legs', len(ws), round(len(ws)/H), 'SOL', round(sum(w['gain'] for w in ws)/1e9,3), round(sum(w['gain'] for w in ws)/1e9/H,3),'/h svc', collections.Counter(w['svc'] for w in ws).most_common(3), 'vp', collections.Counter(w['vp'] for w in ws).most_common(4), 'tok', collections.Counter((w['mints'] or ['?'])[0][:8] for w in ws).most_common(5), 'gain p50', q([w['gain'] for w in ws],.5), 'rivals p50', q([w['rivals'] for w in ws],.5))
# our wins timing/tips
ow=[x for x in OUR if x['verdict']=='WIN']
print('our wins sent_ms p50', q([x['sent_ms'] for x in ow],.5), 'exp p50', q([x['exp'] for x in ow],.5), 'tip/exp p50', q([x['tip']/max(1,x['exp']) for x in ow],.5), 'profit p50', q([x['profit'] for x in ow],.5), 'kinds', collections.Counter(x['kind'] for x in ow), 'arms', collections.Counter(x['arm'] for x in ow))
# our bundle attempts by size: accepted / would-fail
for lo,hi in ((0,.05),(.05,.2),(.2,1),(1,4.3)):
    xs=[x for x in OUR if x['arm']=='bundle' and lo<=x['size']/1e9<hi]
    print('our bundles size',lo,hi,len(xs),'wins',sum(1 for x in xs if x['verdict']=='WIN'), 'rate', round(sum(1 for x in xs if x['verdict']=='WIN')/max(1,len(xs)),4), 'exp p50', q([x['exp'] for x in xs],.5))
# our attempts by pair: win rate
pc=collections.defaultdict(lambda:[0,0])
for x in OUR: pc[x['pair']][0]+=1; pc[x['pair']][1]+= x['verdict']=='WIN'
print('our pairs', sorted(((k,v[0],v[1]) for k,v in pc.items()), key=lambda t:-t[1])[:10])
# mint-level: our attempts vs market small wins on that mint
