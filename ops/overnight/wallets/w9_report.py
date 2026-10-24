#!/usr/bin/env python3
# Build PROFITABLE_WALLETS.md + wallets.json from the w2/w5/w6 outputs (read-only).
# usage: python3 -I w9_report.py <w2 out dir> <deliverable dir>
import sys, os, json, re
OUTD, DEL = sys.argv[1], sys.argv[2]
R = json.load(open(os.path.join(OUTD, "wallets_all.json"))); NUL = json.load(open(os.path.join(OUTD, "null.json")))
FOL = json.load(open(os.path.join(OUTD, "follow.json")))["summary"]
FOCUS = ["9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"]
BAD = re.compile("nigg|nigr|fagg|retard|kike|chink|tranny|cunt|fuck|shit|bitch|whore|slut|hitler|nazi|negro|neeg|rape|porn|pussy|dick|cock|jew|sex", re.I)
mask = lambda s: BAD.sub("[masked]", s or "")
def cls(s):
    L = s["land"]
    if L["ahead_med"] == 0: return "first"
    if (L["fs_med"] or 0) >= 2: return "later"
    return "like-us"
def fol(w, c, run="all", cost=0.015):
    x = FOL.get(w, {}).get(f"{c}|{cost}|{run}")
    return dict(n=x[0], mean=x[1], median=x[2], win=x[3], sol_at_0_5=x[4]) if x else None
def behind(s): return round(sum(v["pnl"] for k, v in s["by_ahead"].items() if k != "0"), 3)
def short(w): return mask(w[:6]) + "…" + mask(w[-4:])
def gm(w): return f"[{short(w)}](https://gmgn.ai/sol/address/{w})"
def ex_links(s, k=1):
    out = []
    for e in s["examples"][:k]:
        out.append(f"[{mask(e['name'])[:18] or e['m'][:6]}](https://gmgn.ai/sol/token/{e['m']}) {e['pnl']:+.2f} ([buy tx](https://solscan.io/tx/{e['fsig']}))")
    return "; ".join(out)
def sel_txt(s):
    t = s["sel"]; bits = []
    if t["serial3"] >= 0.5: bits.append(f"serial devs ({int(t['serial3']*100)}% of picks; dev's launches in run med {t['signer_launches_med']:g})")
    else: bits.append(f"mostly one-off devs ({int((1-t['serial3'])*100)}%)")
    bits.append(f"dev buy med {t['dev_buy_med']:.2f} SOL")
    bits.append(f"bundled {int(t['bundled']*100)}% (glued med {t['glued_sol_med']:.2f} SOL)")
    bits.append(f"X link {int(t['tw']*100)}% / site {int(t['web']*100)}%")
    if t["grad"] >= 0.2: bits.append(f"{int(t['grad']*100)}% graduated")
    bits.append(f"top dev share {int((t['top_creator_share'] or 0)*100)}% of {t['distinct_creators']} devs")
    bits.append("busiest UTC hours " + ",".join(str(h) for h, _ in t["hours_top"][:3]))
    return "; ".join(bits)

ps = sorted((s for s in R.values() if s.get("pass")), key=lambda s: -s["all"]["pnl"])
for s in ps: s["class"] = cls(s)
rows = []
for k, s in enumerate(ps, 1):
    L = s["land"]; a = s["all"]; nu = NUL.get(s["w"], {})
    ms = f"{L['ms_med']:.0f}" if L["ms_med"] is not None else "–"
    rows.append(f"| {k} | {gm(s['w'])} | {s['class']} | {s['n']} | {a['pnl']:+.2f} | {s['R1']['pnl']:+.2f}/{s['R1']['n']} · {s['R2']['pnl']:+.2f}/{s['R2']['n']} | {a['pnl_ex_top2']:+.2f} | {a['roi']*100:+.1f}% | {nu.get('p_mean_le0', '–')} | "
                f"{L['fs_med']:g} / {L['ahead_med']:g} / {ms} | {behind(s):+.2f} | {s['size']['first_buy_med']:.2f} | {s['exit']['hold_s_med']:g}s·{s['exit']['nsells_med']:g} | {L['feetip_pct_med']:.2f}% |")
like = [s for s in ps if s["class"] == "like-us"]; later = [s for s in ps if s["class"] == "later"]; first = [s for s in ps if s["class"] == "first"]
def card(s):
    L = s["land"]; a = s["all"]; nu = NUL.get(s["w"], {}); w = s["w"]
    p1 = fol(w, "P1_mirror"); p2 = fol(w, "P2_mirror"); p2h = fol(w, "P2_h15"); f1 = fol(w, "F1_mirror")
    p1r1 = fol(w, "P1_mirror", "R1"); p1r2 = fol(w, "P1_mirror", "R2")
    ba = " · ".join(f"{k} ahead: {v['n']} tok {v['pnl']:+.2f}" for k, v in s["by_ahead"].items())
    bm = " · ".join(f"{k}: {v['n']} tok {v['pnl']:+.2f}" for k, v in s["by_ms"].items()) or "no engine timeline overlap"
    lines = [f"**{gm(w)}** — {s['class']}, {s['n']} snipes, **{a['pnl']:+.2f} SOL** (R1 {s['R1']['pnl']:+.2f} / R2 {s['R2']['pnl']:+.2f}), without best 2 {a['pnl_ex_top2']:+.2f}, "
             f"ROI {a['roi']*100:+.1f}%, win {int(a['win']*100)}%, median token {a['med']:+.3f} SOL, bootstrap P(mean≤0) {nu.get('p_mean_le0','–')}" + (f", in CANDIDATES.md #{s['known']}" if s.get("known") else ""),
             f"- Landing (MEASURED): median slot +{L['fs_med']:g} ({int(L['create_slot']*100)}% in the create slot), outside buys ahead median {L['ahead_med']:g} (p25–p75 {L['ahead_p25']}–{L['ahead_p75']}), "
             f"arrival in our feed median {L['ms_med'] if L['ms_med'] is None else round(L['ms_med'])} ms (n={L['ms_n']}), entry price ×{(L['mult_med'] or 0):.2f} of the post-bundle price, fee+tip {L['feetip_pct_med']:.2f}% of the buy, tips {L['tips_services'][:3] if L['tips_services'] else '–'}",
             f"- PnL by place: {ba}",
             f"- PnL by arrival ms (R2 17:10+): {bm}",
             f"- Size {s['size']['first_buy_med']:.2f} SOL (tiers {', '.join(str(t[0]) for t in s['size']['tiers'][:3])}); hold median {s['exit']['hold_s_med']} s (p25–p75 {s['exit']['hold_s_p25']}–{s['exit']['hold_s_p75']}), sells median {s['exit']['nsells_med']}, sold everything {int(s['exit']['sold_all']*100)}%; failed attempts on unfilled launches {s['n_fail_only']}",
             f"- Picks (MEASURED): {sel_txt(s)}",
             f"- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: "
             + (f"{p1['mean']*100:+.1f}%/trade, {p1['sol_at_0_5']:+.2f} SOL (R1 {p1r1['mean']*100 if p1r1 else 0:+.1f}%, R2 {p1r2['mean']*100 if p1r2 else 0:+.1f}%)" if p1 else "–")
             + (f"; behind 2: {p2['mean']*100:+.1f}%" if p2 else "") + (f"; behind 2 + hold 3 s: {p2h['mean']*100:+.1f}%" if p2h else "")
             + (f"; reactive follow (buy after its buy +1 trade, sell after its sell): {f1['mean']*100:+.1f}%/trade" if f1 else ""),
             f"- Example: {ex_links(s, 2)}"]
    if s.get("n_unres"):
        lines.insert(1, f"- Includes {s['all']['unrealized']:+.2f} SOL of tokens still held at the end; {s['n_unres']} of them graduated while held (AMM price unknown, valued at the last curve price). Without those: {s['ex_unres']['pnl']:+.2f} SOL")
    return "\n".join(lines)
focus_lines = []
for w in FOCUS:
    s = R.get(w)
    if not s or not s.get("n"): focus_lines.append(f"- {gm(w)}: no snipes in these windows"); continue
    focus_lines.append(f"- {gm(w)}: {s['n']} snipes, **{s['all']['pnl']:+.2f} SOL** (R1 {s['R1']['pnl']:+.2f}/{s['R1']['n']}, R2 {s['R2']['pnl']:+.2f}/{s['R2']['n']}), without best 2 {s['all']['pnl_ex_top2']:+.2f}, "
                       f"ROI {s['all']['roi']*100:+.1f}%, failed-attempt fees {s['fail_cost']:.3f} SOL, landing slot +{s['land']['fs_med']:g} / ahead {s['land']['ahead_med']:g} / {round(s['land']['ms_med'] or 0)} ms, size {s['size']['first_buy_med']:.2f} SOL, hold {s['exit']['hold_s_med']} s, sells {s['exit']['nsells_med']}")
md = open(os.path.join(DEL, "PROFITABLE_WALLETS.template.md")).read()
md = md.replace("{{TABLE}}", "\n".join(rows)).replace("{{LIKE}}", "\n\n".join(card(s) for s in like)).replace("{{LATER}}", "\n\n".join(card(s) for s in later))
md = md.replace("{{FIRST}}", "\n\n".join(card(s) for s in first)).replace("{{FOCUS}}", "\n".join(focus_lines))
md = md.replace("{{NPASS}}", str(len(ps))).replace("{{NLIKE}}", str(len(like))).replace("{{NLATER}}", str(len(later))).replace("{{NFIRST}}", str(len(first)))
open(os.path.join(DEL, "PROFITABLE_WALLETS.md"), "w").write(md)
out = {}
for s in ps + [R[w] for w in FOCUS if w in R]:
    w = s["w"]; d = dict(s); d["class"] = cls(s) if s.get("n") else None; d["gmgn"] = f"https://gmgn.ai/sol/address/{w}"
    d["null"] = NUL.get(w); d["copy_test"] = {c: fol(w, c, run) for c in ("P1_mirror", "P2_mirror", "P2_h15", "P1_h25", "F1_mirror", "F1_h15") for run in ("all",)}
    d["copy_test_by_run"] = {f"{c}|{run}": fol(w, c, run) for c in ("P1_mirror", "P2_mirror", "F1_mirror") for run in ("R1", "R2")}
    for e in d.get("examples", []):
        e["token_link"] = f"https://gmgn.ai/sol/token/{e['m']}"; e["buy_tx"] = f"https://solscan.io/tx/{e['fsig']}"; e["name"] = mask(e.get("name"))
    d["sel"]["names"] = [mask(x) for x in d["sel"].get("names", [])]
    d["focus_wallet"] = w in FOCUS
    out[mask(w)] = d
json.dump(out, open(os.path.join(DEL, "wallets.json"), "w"), indent=1)
print("wrote", len(ps), "passing +", len(FOCUS), "focus wallets")
