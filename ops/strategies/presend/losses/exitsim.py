"""Exit-rule replay on the live hold tapes (presend_live_tape, engine arrival clock).
A rule returns the arrival time t_dec at which it would decide to sell (or None). The new sell lands at the first
other-wallet trade position p with t(p) >= t_dec + LAT and (strict) slot(p) >= slot(trigger trade)+1; it executes
on the curve state just before p. If p is not before our real sell, nothing changes. Proceeds scale from the real sell
by the curve value ratio (fees/tip unchanged: one sell tx either way). Multi-round positions are left unchanged."""
def f(vs, vt, T): return vs * T / (vt + T)
def replay(r, rule, lat_ms=59.0, strict=True):
    if len(r["sells"]) != 1 or r["nbuys"] != 1 or not r["exit"]["t"]: return 0.0, None
    fl, s1, T = r["fill"], r["sells"][0], r["tokens"]
    tp = r["tape"]
    oth = [x for x in tp if not x["ours"] and (x["slot"], x["idx"]) > (fl["slot"], fl["idx"])]
    hit = rule(r, oth)
    if hit is None: return 0.0, None
    t_dec, s_trig = hit
    if t_dec >= r["exit"]["t"]: return 0.0, None
    cand = [x for x in oth if x["t"] >= t_dec + lat_ms * 1e6 and (not strict or x["slot"] >= s_trig + 1)]
    if not cand: return 0.0, None
    p = cand[0]
    if (p["slot"], p["idx"]) >= (s1["slot"], s1["idx"]): return 0.0, None
    allb = [x for x in tp if not (x["ours"] and not x["buy"]) and (x["slot"], x["idx"]) < (p["slot"], p["idx"])]
    allr = [x for x in tp if not (x["ours"] and not x["buy"]) and (x["slot"], x["idx"]) < (s1["slot"], s1["idx"])]
    if not allb or not allr: return 0.0, None
    sb, sr = allb[-1], allr[-1]
    new = s1["sol"] * f(sb["vsol"], sb["vtok"], T) / f(sr["vsol"], sr["vtok"], T)
    return (new - s1["sol"]) / 1e9, p
