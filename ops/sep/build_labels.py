import re, json

LOG = "/root/arbx-fast/paper_urihost.log"
BAND_LO, BAND_HI = 800_000_000, 3_000_000_000

launches = {}   # mint -> dict(slot, dev, order)
done = {}       # mint -> dict(peak, floor, pnlR, legs, entry)
order = 0
for ln in open(LOG):
    m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+) dev_buy=(\d+)", ln)
    if m:
        order += 1
        mint = m.group(2)
        launches[mint] = {"slot": int(m.group(1)), "dev": int(m.group(3)), "order": order}
        continue
    m = re.search(r"PAPER done mint=(\w+) entry=([0-9.e\-]+) fill=[0-9.]+x peak_r=([0-9.]+) legs=(\d+) pnl_R=([+\-0-9.]+) pnl_NET @1\.00=([+\-0-9.]+)", ln)
    if m:
        mint = m.group(1)
        done[mint] = {
            "entry": float(m.group(2)),
            "peak": float(m.group(3)),
            "legs": int(m.group(4)),
            "pnlR": float(m.group(5)),
            "floor": float(m.group(6)),
        }

rows = []
for mint, L in launches.items():
    if not (BAND_LO <= L["dev"] <= BAND_HI):
        continue
    if mint not in done:
        continue  # no outcome
    D = done[mint]
    peak, floor = D["peak"], D["floor"]
    if peak >= 1.5 or floor > 0.15:
        label = "WIN"
    elif peak < 1.3 and floor <= 0.05:
        label = "LOSE"
    else:
        label = "MID"
    rows.append({
        "mint": mint, "slot": L["slot"], "order": L["order"],
        "dev": L["dev"], "dev_sol": L["dev"]/1e9,
        "peak": peak, "floor": floor, "pnlR": D["pnlR"],
        "legs": D["legs"], "entry": D["entry"], "label": label,
    })

rows.sort(key=lambda r: r["slot"])
json.dump(rows, open("/root/sep/labels.json", "w"), indent=0)

from collections import Counter
c = Counter(r["label"] for r in rows)
print(f"IN-BAND (0.8-3.0 SOL) with outcome: {len(rows)}  ->  {dict(c)}")
print(f"{'mint':<10} {'slot':>10} {'dev':>5} {'peak':>5} {'floor':>7} {'legs':>4}  label")
for r in rows:
    print(f"{r['mint'][:9]:<10} {r['slot']:>10} {r['dev_sol']:>5.2f} {r['peak']:>5.2f} {r['floor']:>+7.3f} {r['legs']:>4}  {r['label']}")

# also dump mints missing outcome and out-of-band for transparency
no_done = [m for m, L in launches.items() if BAND_LO <= L["dev"] <= BAND_HI and m not in done]
print(f"\nin-band but NO done-line (excluded): {len(no_done)} -> {no_done}")
