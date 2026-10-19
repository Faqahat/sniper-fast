import json
F = [f for f in json.load(open("/root/sizing/feat.json")) if "dev" in f]
F.sort(key=lambda f: f["sol"])
print("gross  prog   off pos   dev  gsol gl  realpre flmult outahead nout cu(M) tip  pnl  args")
for f in F:
    d = f["dec"]; a = d.get("args")
    extra = [round(x / 1e9, 3) for x in a] if a else (round(d.get("min_out", 0) / 1e12, 1) if d.get("min_out") else "")
    print(f"{f['sol']*1.0125/1e9:6.3f} {d['prog']:7} {f['slot_off']:2} {str(f.get('pos')):5} {f['dev']/1e9:5.2f} {f['gsol']/1e9:5.2f} {f['glued']:2} "
          f"{f['real_pre']/1e9:6.2f} {f['floor_mult']:5.2f} {f.get('out_buy_sol_ahead',0)/1e9:6.2f} {f.get('n_out_buys_ahead',0):3} "
          f"{(f['cu'] or 0)/1e6:6.0f} {f['tip_sum']/1e9:.4f} {f['pnl_pct']:+.2f}", extra, f.get("client_b"), f.get("lh"))
