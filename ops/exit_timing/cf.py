#!/usr/bin/env python3
"""Fair counterfactuals: same r-model baseline (our ~exit) vs looser exits, incl. trailing stop
that RIDES the pump. Series r-multiples relative to given entry. Equal-sizing assumption."""
import json, statistics as st
P=json.load(open("/root/exit_timing/paths.json"))
UNIT=1000.0; FEE=0.012
ORDER=["883Xw2k39itvFRMPBJYXx91MAw3uzc2sKqiRSAQaFb55","3nfCAA4emVMQpbqVCzEHx9XHursYSdtUw9rfcQzepump",
"CenpWbd7YgwRi13DLEgudX1wwDhBFapv8fL4dzeopump","2mczEAedUhHRP5GQ43gP2qTVWCij9NgfidmNJpya4YKU",
"7Cs9KCipGn4s5GSjBEKdeqQ4CJ8aXwvSunY9Lre1fDKE","FXUVymBHRSNaYyuVdkdNhRU8boEP5doyU4ceV6bswrh2",
"BEms6yQdym89E2d71pypdpjdQ8ZyeuKXtBSdaYqWpump","8FYmQHVr33Li3YykhXKpshLvHGjZksHV9MDHdZ9epump"]
def net(mult): return mult*(1-FEE)-1.0

def seq(m):  # list of (slot, r) from entry forward, seeded at (exit_slot baseline) — use full life
    d=P[m]; e=d["entry_lamports_raw"]; xs=d["exit_slot"]
    rs=[(s, px*UNIT/e) for (s,bt,px,ds) in d["series"]]
    return rs, xs

# baseline: our actual-ish = price at last trade <= exit_slot (what we got out at)
def baseline(m):
    rs,xs=seq(m); c=[r for (s,r) in rs if s<=xs]
    return c[-1] if c else rs[0][1]

# trailing stop that RIDES: hold from entry; track running peak; exit when r<=trail*peak OR cap slots OR death(r<=cut)
def trail_sim(m, trail, cut, cap_slots):
    rs,xs=seq(m); d=P[m]; start=d["create_slot"]
    peak=rs[0][1]; 
    for (s,r) in rs:
        if r>peak: peak=r
        if s-start>=cap_slots: return r
        if r<=cut: return r
        if peak>1.05 and r<=trail*peak: return r  # only arm trail once we're up a bit
    return rs[-1][1]

base=[baseline(m) for m in ORDER]
print(f"BASELINE (our ~exit): mean mult={st.mean(base):.3f}  mean net_r={st.mean([net(x) for x in base]):+.4f}")
print(f"  per-trade mult: {[round(x,2) for x in base]}")
print()
for trail,cut,cap in [(0.85,0.80,300),(0.80,0.70,300),(0.70,0.60,300),(0.85,0.90,300),(0.75,0.75,120)]:
    v=[trail_sim(m,trail,cut,cap) for m in ORDER]
    print(f"TRAIL-RIDE trail={trail} cut={cut} cap={cap}: mean mult={st.mean(v):.3f} net_r={st.mean([net(x) for x in v]):+.4f} mults={[round(x,2) for x in v]}")

# express in SOL: actual total -0.021 over 8. Our baseline mean net_r maps to that total.
act_total=-0.021
bmean=st.mean([net(x) for x in base])
# scale factor so baseline model total == actual (calibrate sizing+fee slippage)
scale = act_total/(bmean*8) if bmean!=0 else 1.0
print(f"\ncalibration: baseline model total {bmean*8:+.4f} net_r-units == actual {act_total} SOL  -> 1 net_r-unit ~ {abs(scale):.4f} SOL/trade-share")
print("SOL-equivalent totals (scaled to actual baseline):")
for name,v in [("our exit (baseline)",base)]+[(f"trail {t}/{c}",[trail_sim(m,t,c,300) for m in ORDER]) for (t,c) in [(0.85,0.80),(0.80,0.70),(0.70,0.60)]]:
    tot_netr=sum(net(x) for x in v)
    print(f"  {name:22s}: total net_r {tot_netr:+.4f}  ~ {tot_netr*abs(scale):+.4f} SOL")
