#!/usr/bin/env python3
# RACE-GATE patch part 2 (2026-10-18): --race-track-rejects (PAPER only): launches the gate rejects are still price-tracked
# as SHADOW positions (path dumped with "fired": false, log "PAPER shadow-done", NOT in the PAPER report), so fired and
# rejected launches of the same forward window can be compared on identical data. Default off.
import sys

p = sys.argv[1]
e = open(p).read()
assert "track_rejects" not in e


def rep(old, new, cnt=1):
    global e
    assert e.count(old) == cnt, (e.count(old), old[:100])
    e = e.replace(old, new)


rep("""    /// count outside buyers in the window (true when --race-window-ms > 0)
    count_out: bool,""", """    /// count outside buyers in the window (true when --race-window-ms > 0)
    count_out: bool,
    /// --race-track-rejects (paper only): also price-track rejected launches as shadow positions
    track_rejects: bool,""")
rep("""            count_out: window_cfg > 0.0,""", """            count_out: window_cfg > 0.0,
            track_rejects: has("--race-track-rejects"),""")
rep("""struct RaceWatch { cfg: RaceCfg, pend: std::collections::HashMap<Pk, RacePend> }""",
    """struct RaceWatch { cfg: RaceCfg, pend: std::collections::HashMap<Pk, RacePend>, shadow: Vec<(Launch, u64)> }""")
rep("""    fn new(cfg: RaceCfg) -> Self { RaceWatch { cfg, pend: Default::default() } }""",
    """    fn new(cfg: RaceCfg) -> Self { RaceWatch { cfg, pend: Default::default(), shadow: Vec::new() } }""")
rep("""        if self.cfg.gate && !static_ok { eprintln!("  RACE reject-static slot={slot} mint={}", b58(&launch.mint)); }""",
    """        if self.cfg.gate && !static_ok {
            eprintln!("  RACE reject-static slot={slot} mint={}", b58(&launch.mint));
            if self.cfg.track_rejects { self.shadow.push((launch.clone(), slot)); }
        }""")
rep("""                if p.pass { ready.push((p.launch.clone(), p.slot)); }""",
    """                if p.pass { ready.push((p.launch.clone(), p.slot)); }
                else if self.cfg.track_rejects { self.shadow.push((p.launch.clone(), p.slot)); }""")
# paper loop: fired + shadow
rep("""        if race.cfg.active() { ready.extend(race.due()); }
        for (launch, create_slot) in ready.drain(..) {
        detected += 1;
        let vanilla = launch.is_vanilla();
        eprintln!("  PAPER launch #{detected} slot={create_slot} mint={} dev_buy={} vanilla={vanilla} — tracking price path", b58(&launch.mint), launch.dev_buy_lamports);
""", """        if race.cfg.active() { ready.extend(race.due()); }
        let shadows: Vec<(Launch, u64)> = race.shadow.drain(..).collect();
        let batch: Vec<(Launch, u64, bool)> = ready.drain(..).map(|(l, s)| (l, s, true)).chain(shadows.into_iter().map(|(l, s)| (l, s, false))).collect();
        for (launch, create_slot, fired) in batch {
        let vanilla = launch.is_vanilla();
        if fired {
            detected += 1;
            eprintln!("  PAPER launch #{detected} slot={create_slot} mint={} dev_buy={} vanilla={vanilla} — tracking price path", b58(&launch.mint), launch.dev_buy_lamports);
        } else {
            eprintln!("  PAPER shadow-launch slot={create_slot} mint={} dev_buy={} (race gate rejected; tracked for comparison only)", b58(&launch.mint), launch.dev_buy_lamports);
        }
""")
rep("""                let obj = serde_json::json!({ "mint": b58(&launch.mint), "dev": launch.dev_buy_lamports as f64 / 1e9,
                    "vanilla": vanilla, "peak": peak_path, "path": path });""", """                let obj = serde_json::json!({ "mint": b58(&launch.mint), "dev": launch.dev_buy_lamports as f64 / 1e9,
                    "vanilla": vanilla, "peak": peak_path, "path": path, "fired": fired, "slot": create_slot });""")
rep("""            eprintln!("  PAPER done mint={} entry={:.3e} fill={:.3}x peak_r={:.3} legs={} pnl_R={:+.4} pnl_NET{}{}",
                rec.mint, rec.entry, rec.fill, rec.peak_r, rec.legs, rec.pnl_r, net_str, scale_str);
            sink2.lock().unwrap().push(rec);
        });
        } // ready.drain""", """            if !fired {
                eprintln!("  PAPER shadow-done mint={} fill={:.3}x peak_r={:.3} pnl_NET{}", rec.mint, rec.fill, rec.peak_r, net_str);
                return;
            }
            eprintln!("  PAPER done mint={} entry={:.3e} fill={:.3}x peak_r={:.3} legs={} pnl_R={:+.4} pnl_NET{}{}",
                rec.mint, rec.entry, rec.fill, rec.peak_r, rec.legs, rec.pnl_r, net_str, scale_str);
            sink2.lock().unwrap().push(rec);
        });
        } // batch""")
# live loop: never fire shadows (they are only collected in paper); drop any that accumulate
rep("""        if race.cfg.active() { ready.extend(race.due()); }
        for (launch, create_slot) in ready.drain(..) {
        // reserve a concurrency slot (never block the detector) and budget""", """        if race.cfg.active() { ready.extend(race.due()); race.shadow.clear(); } // shadows are paper-only: never fired live
        for (launch, create_slot) in ready.drain(..) {
        // reserve a concurrency slot (never block the detector) and budget""")
# document the flag in the header comment
rep("""//   --race-obs-ms O         keep observing to O ms for the log (default max(W, 200))""",
    """//   --race-obs-ms O         keep observing to O ms for the log (default max(W, 200))
//   --race-track-rejects    PAPER only: price-track rejected launches too, as shadow positions (dump "fired":false,
//                           log "PAPER shadow-done", excluded from the PAPER report). Ignored by the live loop.""")
open(p, "w").write(e)
print("patch2 OK")
