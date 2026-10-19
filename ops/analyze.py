import json
from collections import defaultdict

parsed = json.load(open("/root/parsed_txs.json"))
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"

n_none = sum(1 for v in parsed.values() if v is None)
print("parsed txs:", len(parsed), "unparseable(None):", n_none)

mints = json.load(open("/root/expanded_mints.json"))
mintset = set(mints)

events = defaultdict(list)
for sig, v in parsed.items():
    if v is None:
        continue
    for m, td in v["tokdeltas"].items():
        if td == 0:
            continue
        side = "buy" if td > 0 else "sell"
        events[m].append({"slot": v["slot"], "bt": v["blockTime"], "side": side,
                          "td": td, "ld": v["lamport_delta"], "sig": sig})

roundtrips = []
no_sell = []
no_buy = []
for m in mintset:
    evs = sorted(events.get(m, []), key=lambda e: (e["slot"] or 0, e["bt"] or 0))
    buys = [e for e in evs if e["side"] == "buy"]
    sells = [e for e in evs if e["side"] == "sell"]
    if not buys:
        no_buy.append(m)
        continue
    if not sells:
        no_sell.append(m)
        continue
    first_buy = buys[0]
    total_bought = sum(b["td"] for b in buys)
    total_sold = -sum(s["td"] for s in sells)
    sol_in = -sum(b["ld"] for b in buys) / 1e9
    sol_out = sum(s["ld"] for s in sells) / 1e9
    mult = (sol_out / sol_in) if sol_in > 0 else None
    first_sell = sells[0]
    last_sell = sells[-1]
    hold_s = (first_sell["bt"] - first_buy["bt"]) if (first_sell["bt"] and first_buy["bt"]) else None
    hold_slots = (first_sell["slot"] - first_buy["slot"]) if (first_sell["slot"] and first_buy["slot"]) else None
    full_exit_s = (last_sell["bt"] - first_buy["bt"]) if (last_sell["bt"] and first_buy["bt"]) else None
    legs = [(-s["td"] / total_bought if total_bought else None) for s in sells]
    roundtrips.append({"mint": m, "n_buys": len(buys), "n_sells": len(sells),
                       "total_bought": total_bought, "total_sold": total_sold,
                       "sol_in": sol_in, "sol_out": sol_out, "mult": mult,
                       "hold_s": hold_s, "hold_slots": hold_slots,
                       "full_exit_s": full_exit_s, "legs": legs,
                       "sold_frac": (total_sold / total_bought if total_bought else None),
                       "buy_slot": first_buy["slot"]})

json.dump({"roundtrips": roundtrips, "no_sell": no_sell, "no_buy": no_buy},
          open("/root/roundtrips.json", "w"))
print("pump mints:", len(mintset), "| full roundtrips:", len(roundtrips),
      "| bought_no_sell:", len(no_sell), "| no_buy_tx_seen:", len(no_buy))
