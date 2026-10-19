#!/usr/bin/env python3
"""Aggregate all per-wallet tapes into one ranked candidate table + candidates.json."""
import json, glob, os
NAMES={
 "FixmSpsBa7ew26gWdiqpoMAgKRFgbSXFbGAgfMZw67X":"Marcell(web)",
 "G3gZWqrYkNmYFKYCyfRCNtGuxdyuE2wiYKkZpiZn4WSS":"Goyim(web)",
 "BCagckXeMChUKrHEd6fKFA1uiWDtcmCXMsqaheLiUPJd":"dv(web)",
 "4BdKaxN8G6ka4GYtQQWk4G4dZRUTX2vQH9GcXdBREFUk":"Jijo(web)",
 "4sAUSQFdvWRBxR8UoLBYbw8CcXuwXWxnN8pXa4mtm5nU":"Scharo(web)",
 "DAEdBmTPEKM6xkwfzC3d411QUe6coKpkND6UURa4CvHC":"Fox(web)",
 "DjM7Tu7whh6P3pGVBfDzwXAx2zaw51GJWrJE3PwtuN7s":"LUKEY(web)",
 "95TWoKkvv2z85EXBzd2z6NwbxH2f54AvwuCA9x3NoKep":"Killua(web)",
 "4vw54BmAogeRV3vPKWyFet5yf8DTLcREzdSzx4rw9Ud9":"decu(web)",
 "EeXvxkcGqMDZeTaVeawzxm9mbzZwqDUMmfG3bF7uzumH":"milito(web)",
 "BQVz7fQ1WsQmSTMY3umdPEPPTm1sdcBcX9sP7o6kPRmB":"Limfork(web)",
 "FqamE7xrahg7FEWoByrx1o8SeyHt44rpmE6ZQfT7zrve":"EustazZ(web)",
 "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o":"Cented(web)",
 "Bi4rd5FH5bYEN8scZ7wevxNZyNmKHdaBcvewdPFxYdLt":"theo(web)",
 "2fg5QD1eD7rzNNCsvnhmXFm5hqNgwTTG8p7kQ6f3rx6f":"Cupsey(web)",
 "AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg":"cohort1",
 "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK":"cohort2-lead",
 "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw":"cohort3-lead",
 "BXB7FF4m5x74ZoUvVHfPJnVBbqWHpMEU1WNUZAL9W8PL":"cohort4",
 "G8gTguf7EUwqfwdRhiZ3KCBEgPURVB7LXoDzHif4p6oh":"cohort5",
 "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3":"4yFAz(baseline)",
}
rows=[]
for f in glob.glob("/root/copyable/tapes/*.json"):
    d=json.load(open(f))
    s=d["summary"]; w=s["wallet"]
    rows.append(s)
def k(s):
    return -(s.get("tot_realized_pnl_sol") or -999)
rows.sort(key=k)
hdr=f"{'name':<16}{'wallet':<46}{'nTr':>5}{'nCl':>5}{'pnlSOL':>9}{'win':>6}{'medHold':>9}{'medR':>7}{'tpd':>9}"
print(hdr); print("-"*len(hdr))
for s in rows:
    w=s["wallet"]; nm=NAMES.get(w,"?")
    mh=s.get("median_hold_s"); mr=s.get("median_r"); win=s.get("win_rate"); tpd=s.get("trades_per_day")
    print(f"{nm:<16}{w:<46}{s['n_trades']:>5}{s['n_closed']:>5}"
          f"{(s.get('tot_realized_pnl_sol') or 0):>9.2f}"
          f"{(win if win is not None else -1):>6.2f}"
          f"{(str(mh)+'s' if mh is not None else '-'):>9}"
          f"{(mr if mr is not None else -1):>7.3f}"
          f"{(tpd if tpd is not None else -1):>9.1f}")
json.dump([{**s,"name":NAMES.get(s['wallet'],'?')} for s in rows],
          open("/root/copyable/candidates.json","w"),indent=1)
print("\nwrote /root/copyable/candidates.json  (n=%d)"%len(rows))
# finalists for copy-sim: profitable AND median hold >= 20s (potential lag tolerance)
fin=[s['wallet'] for s in rows if (s.get('tot_realized_pnl_sol') or 0)>0 and (s.get('median_hold_s') or 0)>=20 and s['n_closed']>=15]
print("COPYABLE-SHAPED finalists (pnl>0 & medHold>=20s & nClosed>=15):", fin)
