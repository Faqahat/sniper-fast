#!/usr/bin/env python3
import json, re
from collections import Counter
R=[json.loads(l) for l in open('/root/meta400/his_meta.jsonl')]
N=len(R)
print("N his =",N)

def dist(key,fn=None,top=12):
    c=Counter()
    for r in R:
        v=fn(r) if fn else r.get(key)
        c[v]+=1
    print(f"\n=== {key} === (distinct={len(c)})")
    for val,cnt in c.most_common(top):
        print(f"  {cnt:4d} {100*cnt/N:5.1f}%  {repr(val)[:80]}")
    return c

def host(u):
    if not u: return None
    m=re.match(r'https?://([^/]+)',u)
    return m.group(1) if m else u[:30]

dist('mint_program')
dist('decimals')
dist('supply')
dist('mint_authority', lambda r: 'RENOUNCED(null)' if r.get('mint_authority') is None else 'SET')
dist('freeze_authority', lambda r: 'NONE(null)' if r.get('freeze_authority') is None else 'SET')
dist('update_authority', lambda r: 'null' if r.get('update_authority') is None else r.get('update_authority'))
dist('extensions', lambda r: tuple(r.get('extensions')) if r.get('extensions') else None)
dist('is_v2')
dist('suffix')
dist('uri_fetch_ok', lambda r: r.get('uri_fetch_status','').startswith('ok'))
dist('uri_host', lambda r: host(r.get('uri')))
dist('uri_createdOn')
dist('uri_showName')
dist('has_twitter', lambda r: bool(r.get('uri_twitter')))
dist('has_telegram', lambda r: bool(r.get('uri_telegram')))
dist('has_website', lambda r: bool(r.get('uri_website')))
dist('has_discord', lambda r: bool(r.get('uri_discord')))
dist('uri_has_social')
dist('has_image', lambda r: bool(r.get('uri_image')))
dist('has_description', lambda r: bool(r.get('uri_description') not in (None,'')))

# uri_keys signature (sorted key tuple)
dist('uri_keys_sig', lambda r: tuple(r.get('uri_keys')) if r.get('uri_keys') else None, top=15)

# creator reuse
cc=Counter(r['creator'] for r in R)
print(f"\n=== creator reuse === distinct creators={len(cc)}; max launches by one creator={cc.most_common(1)}")
print("  creators with >1 his-launch:",sum(1 for k,v in cc.items() if v>1))

# social domains
def domains(key):
    c=Counter()
    for r in R:
        v=r.get(key)
        if v: c[host(v)]+=1
    return c
print("\n=== twitter hosts ===", domains('uri_twitter').most_common(6))
print("=== website hosts top ===", domains('uri_website').most_common(10))

# dev_buy stats
import statistics as st
dv=[r['dev_buy'] for r in R if r.get('dev_buy')]
print(f"\n=== dev_buy === n={len(dv)} min={min(dv):.3f} med={st.median(dv):.3f} max={max(dv):.3f}")
jt=[r.get('jito_tip_create') for r in R if r.get('jito_tip_create') is not None]
print(f"=== jito_tip_create === nonzero={sum(1 for x in jt if x)} / {len(jt)}")
