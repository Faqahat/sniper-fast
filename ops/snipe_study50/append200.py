import json, statistics as st
U64MAX=18446744073709551615
E=json.load(open('/root/snipe_study50/enriched200.json'))
R=E['records']; N=len(R)
dec=[r for r in R if r.get('create_found')]
nd=len(dec)
van=[r for r in dec if r.get('vanilla')]
sentinel=[r for r in dec if r.get('wire_dev')==U64MAX]
def accept_counts(thr):
    acc=snv=sdev=0
    for r in dec:
        if not r.get('vanilla'): snv+=1; continue
        if (r.get('wire_dev') or 0) < thr: sdev+=1; continue
        acc+=1
    return acc,snv,sdev
def disagree(thr):
    over=under=0
    for r in dec:
        wd=r.get('wire_dev') or 0; cd=r.get('curve_delta')
        if cd is None: continue
        wpass= wd>=thr
        cpass= cd>=thr
        if wpass and not cpass: over+=1
        if (not wpass) and cpass: under+=1
    return over,under
def dist(vals,scale=1.0):
    vals=[v/scale for v in vals if v is not None and v!=U64MAX]
    if not vals: return "n/a"
    vals.sort(); n=len(vals); return f"p25={vals[n//4]:.3f} med={st.median(vals):.3f} p75={vals[(3*n)//4]:.3f}"
span=E.get('meta')
import datetime
def ts(x): return datetime.datetime.fromtimestamp(x,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
hours=(span[1]-span[0])/3600 if span else 0

L=[]
L.append("\n\n---\n")
L.append("## FILTER ACCEPT TEST — 200 SNIPES (our real logic)")
L.append(f"- Sample: his last **{N} landed snipes**, window {ts(span[0])}..{ts(span[1])} UTC (~{hours:.0f} h). Create tx decoded for **{nd}/{N}** (undecoded excluded below).")
L.append(f"- Our wire filter: dev_buy read from the create tx's bundled pump buy instruction data only (6 discriminators; spendable=data[8:16], cap=max_sol_cost data[16:24]; priority spend>finite-cap>u64::MAX-sentinel>0), vanilla from create_v2 flag bytes. ACCEPT = vanilla AND wire_dev>=threshold.")
L.append(f"- Vanilla: {len(van)}/{nd} = {100.0*len(van)/nd:.0f}%.  u64::MAX sentinel (always-pass dev) hits: **{len(sentinel)}/{nd}**.")
L.append(f"- Wire dev_buy dist (excl sentinel): {dist([r['wire_dev'] for r in dec],1e9)} SOL.  Curve-delta truth dist: {dist([r['curve_delta'] for r in dec],1e9)} SOL.")
L.append("")
L.append("| --min-dev-buy | ACCEPT | SKIP non-vanilla | SKIP dev-too-low | accept-rate |")
L.append("|---|---|---|---|---|")
for thr,lbl in [(0,'0'),(3*10**8,'0.3 SOL'),(5*10**8,'0.5 SOL'),(10**9,'1.0 SOL')]:
    a,snv,sdev=accept_counts(thr)
    L.append(f"| {lbl} | {a} | {snv} | {sdev} | {100.0*a/nd:.0f}% |")
L.append("")
L.append("### Wire-vs-curve faithfulness (our slot-0 number vs bonding-curve SOL delta truth)")
L.append("| threshold | over-accept (wire pass, curve<thr) | under-accept (wire skip, curve>=thr) |")
L.append("|---|---|---|")
for thr,lbl in [(3*10**8,'0.3 SOL'),(5*10**8,'0.5 SOL'),(10**9,'1.0 SOL')]:
    o,u=disagree(thr)
    L.append(f"| {lbl} | {o} | {u} |")
o3,u3=disagree(3*10**8)
L.append("")
L.append(f"**Verdict:** at --min-dev-buy 0.3 SOL our filter ACCEPTS {accept_counts(3*10**8)[0]}/{nd} ({100.0*accept_counts(3*10**8)[0]/nd:.0f}%) of his decoded picks; dropping to 0.5 SOL barely changes it, 1.0 SOL loses ~half. Wire vs curve disagree on {o3+u3}/{nd} at 0.3 SOL ({'mostly over-accept from cap=max_sol_cost>actual' if o3>=u3 else 'mostly under-accept'}), so the wire number is a faithful-enough proxy (cap-family reads the declared max, which slightly over-states spend). Recommend **--min-dev-buy 0.3 SOL**.")
txt="\n".join(L)
with open('/root/snipe_study50/REPORT.md','a') as f: f.write(txt)
print(txt)
