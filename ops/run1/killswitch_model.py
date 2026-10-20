# Kill-switch / --lock-tiers model: OLD logic (commit 0d628e0, snipe_engine.rs 2232-2269 + 2384) vs NEW logic (audit fixes
# C1 + M7, sniper/main after the fix commit: Acct/Pos/ks_eval in src/bin/snipe_engine.rs).
# OLD: pnl = (balance + open) - start, open += spend at FIRE, -= at task END; poll 8 s; tiers armed/tripped on any poll.
# NEW: open += actual cost when the buy is SEEN landed with tokens, -= when a CONFIRMED read shows the token account 0
#      (sold); poll 2 s; kill if pnl < -cap on 2 consecutive evaluated polls (re-audit N2: always, not only while a buy is
#      pending; a poll that raced a position change is not evaluated); realized < -cap kills at once; lock tiers arm/trip
#      only with NO position in flight (fire .. exit done), and the trip needs 2 consecutive polls below the floor.
# Tiers "0.3:0,0.6:0.3", loss cap 0.5 SOL, size 1.5 SOL. Times in seconds.
SOL = 1e9
start = int(5 * SOL); spend = int(1.5 * SOL); loss_cap = int(0.5 * SOL)
tiers = [(int(0.3 * SOL), 0), (int(0.6 * SOL), int(0.3 * SOL))]


def run_old(events, horizon=120):
    """events: (t, d_balance, d_open)"""
    bal, opn, floor, log = start, 0, None, []
    ev = sorted(events)
    for t in range(8, horizon + 1, 8):
        while ev and ev[0][0] <= t:
            _, db, do = ev.pop(0); bal += db; opn += do
        pnl = (bal + opn) - start
        log.append(f"t={t:5.1f}s bal={bal/SOL:.4f} open={opn/SOL:.2f} pnl={pnl/SOL:+.4f}")
        if pnl < -loss_cap: return log, f"KILL-SWITCH at t={t}"
        for a, f in tiers:
            if pnl >= a and (floor is None or f > floor): floor = f; log.append(f"        PROFIT-LOCK armed -> floor {f/SOL}")
        if floor is not None and pnl < floor: return log, f"PROFIT-LOCK STOP at t={t} (pnl {pnl/SOL:+.4f} < floor {floor/SOL})"
    return log, "no stop"


def ks_eval(st, pnl, realized, pending, inflight):
    """same decision as ks_eval() in snipe_engine.rs (re-audit N2: KILL and LOCK need 2 consecutive evaluated polls)"""
    below = pnl < -loss_cap
    kill = below and st["prev_below"]
    note = "  (below cap: confirm next poll)" if below and not kill else ""
    st["prev_below"] = below
    if kill: return "KILL", note
    if realized < -loss_cap: return "KILL-REALIZED", note
    if inflight > 0:
        st["prev_lock"] = False
        return "GO", note + ("  (lock deferred: position in flight)" if tiers else "")
    for a, f in tiers:
        if pnl >= a and (st["floor"] is None or f > st["floor"]): st["floor"] = f; note += f"  PROFIT-LOCK armed -> floor {f/SOL}"
    under = st["floor"] is not None and pnl < st["floor"]
    lock = under and st["prev_lock"]
    if under and not lock: note += "  (below floor: confirm next poll)"
    st["prev_lock"] = under
    if lock: return "LOCK", note
    return "GO", note


def run_new(events, horizon=120, poll0=2.0):
    """events: (t, d_balance, d_open, d_pending, d_inflight, d_realized)"""
    bal, opn, pend, infl, real = start, 0, 0, 0, 0
    st = {"floor": None, "prev_below": False, "prev_lock": False}
    ev = sorted(events); log = []
    t = poll0
    while t <= horizon + 1e-9:
        while ev and ev[0][0] <= t:
            _, db, do, dp, di, dr = ev.pop(0); bal += db; opn += do; pend += dp; infl += di; real += dr
        pnl = (bal + opn) - start
        v, note = ks_eval(st, pnl, real, pend, infl)
        log.append(f"t={t:5.1f}s bal={bal/SOL:.4f} open={opn/SOL:.3f} pending={pend} inflight={infl} pnl={pnl/SOL:+.4f} realized={real/SOL:+.4f}{note}")
        if v != "GO": return log, f"{v} at t={t:.1f}"
        t += 2.0
    return log, "no stop"


def show(name, old, new, **kw):
    print("=" * 110); print(name)
    lo, wo = run_old(old, **{k: v for k, v in kw.items() if k == "horizon"})
    print("  OLD:", wo); [print("     ", l) for l in lo[:8]]
    ln, wn = run_new(new, **kw)
    print("  NEW:", wn); [print("     ", l) for l in ln[:12]]
    return wo, wn


fee = int(0.0255 * SOL); rent = 2_074_080; cost = spend + fee + rent
# blockhash validity ~150 blocks x 217 ms ~ 33 s: a never-landing buy is resolved (not landed) at fire + 3 s land timeout
# (land_check every 100 ms) .. at most fire + ~36 s (late-land watch ends when the blockhash is dead)
res = {}
res["A"] = show("Scenario A: one buy that never lands (old: guard held 15 s + 45 s late-land)",
     [(1, 0, +spend), (61, 0, -spend)],
     [(1, 0, 0, +1, +1, 0), (37, 0, 0, -1, -1, 0)])
res["B"] = show("Scenario B: a WINNING trade (+0.05 SOL); a poll falls between fire (t=7.6) and the buy landing (t=8.4)",
     [(7.6, 0, +spend), (8.4, -spend - int(0.025*SOL), 0), (9.5, spend + int(0.075*SOL), 0), (9.6, 0, -spend)],
     # fire 7.6; lands 8.4 (balance -cost), SEEN 8.55 -> open +cost, pending -1; sell lands 9.5 (+proceeds incl. rent back),
     # token account 0 seen 9.65 -> open -cost; exit done 9.65; realized (+0.05 - fees) from getTransaction at ~12
     [(7.6, 0, 0, +1, +1, 0), (8.4, -cost, 0, 0, 0, 0), (8.55, 0, +cost, -1, 0, 0),
      (9.5, cost + int(0.05*SOL), 0, 0, 0, 0), (9.65, 0, -cost, 0, -1, 0), (12, 0, 0, 0, 0, int(0.05*SOL))], poll0=8.0)
res["B2"] = show("Scenario B': the same winning trade, worst case: a poll lands INSIDE the landing->seen gap (t=8.45)",
     [(7.6, 0, +spend), (8.4, -spend - int(0.025*SOL), 0), (9.5, spend + int(0.075*SOL), 0), (9.6, 0, -spend)],
     [(7.6, 0, 0, +1, +1, 0), (8.4, -cost, 0, 0, 0, 0), (8.55, 0, +cost, -1, 0, 0),
      (9.5, cost + int(0.05*SOL), 0, 0, 0, 0), (9.65, 0, -cost, 0, -1, 0), (12, 0, 0, 0, 0, int(0.05*SOL))], poll0=8.45)
res["C"] = show("Scenario C: run PnL already -0.45; two trades lose 0.15 each (t=5, t=12) while a third buy never lands",
     [(1, -int(0.45*SOL), 0), (2, 0, +spend), (5, -int(0.15*SOL), 0), (12, -int(0.15*SOL), 0), (62, 0, -spend)],
     [(1, -int(0.45*SOL), 0, 0, 0, -int(0.45*SOL)), (2, 0, 0, +1, +1, 0), (5, -int(0.15*SOL), 0, 0, 0, 0), (12, -int(0.15*SOL), 0, 0, 0, 0),
      (38, 0, 0, -1, -1, 0)], horizon=80)
res["D"] = show("Scenario D (re-audit N2): a +0.05 sale; one poll reads a lagging balance (proceeds missing) after the engine saw it sold",
     [(1, 0, +spend), (1.5, -cost, 0), (3.0, cost + int(0.05*SOL), 0), (3.2, 0, -spend)],
     [(1, 0, 0, +1, +1, 0), (1.5, -cost, 0, 0, 0, 0), (1.6, 0, +cost, -1, 0, 0), (3.0, cost + int(0.05*SOL), 0, 0, 0, 0), (3.2, 0, -cost, 0, -1, 0),
      # the 4.0 poll's node lags: the balance still lacks the proceeds (modelled as a -proceeds blip undone at 4.1)
      (4.0, 0, 0, 0, 0, 0), (3.9, -(cost + int(0.05*SOL)), 0, 0, 0, 0), (4.1, cost + int(0.05*SOL), 0, 0, 0, 0)], horizon=30)
print("=" * 110)
print("SUMMARY (expected: A no stop, B no stop, B' no stop, C KILL soon after real PnL < -0.5 at t=5, D no stop)")
for k, (o, n) in res.items(): print(f"  {k:3} OLD: {o:45} NEW: {n}")
