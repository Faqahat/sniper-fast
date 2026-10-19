import json
rows=json.load(open("rows.json"))
res=json.load(open("results.json"))
def f(x): return f"{x:.4e}"
L=[]
L.append("# Sniper Fill-Quality Probe — 5 Live Buys\n")
L.append("Wallet/payer `FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS`. RPC = constantk staked (Frankfurt). Buys are v0; creates v1.\n")
L.append("## Method\n")
L.append("- **Floor** = marginal pool price *immediately after the dev buy* (first trade in the create slot), `virtual_sol/virtual_token`.\n")
L.append("- **Reserves**: pump constant-product, verified empirically on-chain. SOL offset 30e9, token offset 73e12, k = 30e9*(1e15+73e12). Predicted dev-buy SOL matched measured curve lamport delta to <0.2% on every probe.\n")
L.append("- **Our fill** = SOL actually added to the bonding curve by our buy (curve lamport delta, net of the 1% pump fee / ATA rent / priority — pure pool price) / base tokens we received. Apples-to-apples vs floor (also a pool price).\n")
L.append("- **Ordering** taken from `getBlock` (authoritative block index), across the create slot + next 2 slots.\n")
L.append("- All prices in **lamports per base token** (6-decimal units).\n")
L.append("\n## Per-probe results\n")
L.append("| # | mint | dev SOL | create→land | floor | our fill | **fill ratio** | buys before us (✓) | rank in our landed slot | distinct buyers in create slot |")
L.append("|---|------|---------|-------------|-------|----------|----------------|--------------------|-------------------------|-------------------------------|")
for x,r in zip(rows,res):
    L.append(f"| {x['n']} | {x['mint']} | {x['dev']} | c+{x['land']} | {f(x['floor'])} | {f(x['fill'])} | **{x['ratio']:.3f}** | {x['buys_before']} | {x['inslot_rank']} | {r['buyers_by_slot'].get(str(x['create']),'')} |")
L.append("")
L.append("## Aggregate\n")
L.append("- **Fill ratio: median 1.33, mean 1.34, range 1.05–1.78.**")
L.append("- Marginal price at our execution vs floor: median 1.32x.")
L.append("- Successful buyers landing *before us*: 4,4,5,7,5 (median **5**). We are never 1st (that's the dev) or 2nd on any probe.")
L.append("- Rank within our own landed slot: 1,3,6,3,5 (median **3**) — we are usually not even first among same-slot public buyers.")
L.append("- Create→land: 4 of 5 at create+1; probe 3 landed in the create slot itself but still 6th.")
L.append("")
L.append("## What the ordering shows (per probe)\n")
for r in res:
    p=r["probe"]
    L.append(f"**Probe {p['n']} ({p['mint'][:8]}, dev {p['dev']} SOL, create {p['create']}, land create+{p['buy_slot']-p['create']}):**")
    for s in r["seq"]:
        tag="CREATE+DEVBUY" if s["is_create"] else "buy"
        me=" **<- US**" if s["ours"] else ""
        L.append(f"  - seq{s['i']} slot {s['slot']} blk-idx {s['idx']:>5} {tag} `{s['payer'][:6]}` tokens {s['tokens']:,} solIn {s['sol_in']:,} margPost {s['marg_post']:.4e}{me}")
    L.append("")
L.append("## Verdict — is the intra-slot race winnable with our current warm path?\n")
L.append("**No, not with the current path.** Median fill ratio **1.33** sits far above the ~1.0–1.1 \"winnable\" band and far above the value study's +EV bound (fill within ~0.6 slot of the floor). We pay a median ~33% premium to the floor because a median of 5 buyers fill ahead of us on every mint.\n")
L.append("**Where the winners sit:** the fastest co-snipers occupy the *create slot itself*, in block indices immediately adjacent to the create instruction — e.g. probe 1 create at idx 1168, co-snipers at idx 1169/1170/1171; probe 3 create at idx 18, co-snipers at idx 19/20/21. That back-to-back adjacency = they are **bundled with the create** (same Jito bundle / same-leader pipeline), landing at ~0 slot gap and ~$0 extra. They are not outbidding us — they are structurally ahead. This matches the run48e finding exactly.\n")
L.append("**What our warm send path actually buys us:** it wins the race *among the public (non-bundled) traffic* — in probe 1 we are idx 225, first of the public wave in create+1, beating ~12 submissions that failed on slippage. But first-of-public is still a full slot + a bundle behind the floor. And it is not even reliable: in 4 of 5 probes we were 3rd–6th within our own landed slot (only probe 1 we were 1st in-slot).\n")
L.append("**Why ratios vary — competition, not our latency.** Probe 5 (ratio 1.05, best): only the dev bought in the create slot and followers were tiny → we land near floor. Probe 4 (ratio 1.78, worst): a 6.5-SOL whale plus 6 buyers front-ran inside the create slot, pumping the price +76% before create+1. Our fill quality is dominated by how many bundled/same-slot buyers a given mint attracts — which send latency does not control.\n")
L.append("**Implication / lever:** to be +EV we must land *inside the create slot adjacent to the create* (co-located in the creator's bundle or in-shred insertion), not merely submit fast on the public path. Tips/size are not the lever (winners pay ~$0); same-slot placement is.\n")
open("REPORT.md","w").write("\n".join(L))
print("wrote REPORT.md", len("\n".join(L)), "bytes")
