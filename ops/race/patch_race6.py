#!/usr/bin/env python3
# RACE-GATE patch part 6 (2026-10-18): zero-wait "gate B" params. --race-min-bundle N (creator bundle of >= N buy txs seen
# within --race-bundle-ms of the create) and --race-max-name-len L (token name <= L chars). bundle_n now counts BUYS only.
import sys
ep = sys.argv[1]
e = open(ep).read()
def rep(old, new):
    global e
    assert e.count(old) == 1, old[:90]
    e = e.replace(old, new)
rep("""    /// --race-track-rejects (paper only): also price-track rejected launches as shadow positions
    track_rejects: bool,""", """    /// --race-track-rejects (paper only): also price-track rejected launches as shadow positions
    track_rejects: bool,
    /// --race-min-bundle N: creator bundle of >= N buy txs within bundle_ms (0 = off)
    min_bundle: u32,
    /// --race-max-name-len L: token name <= L chars (0 = off)
    max_name_len: usize,""")
rep("""        let window_ms = if bundle != 0 { window_cfg.max(bundle_ms) } else { window_cfg };""",
    """        let min_bundle = arg_u64("--race-min-bundle", 0) as u32;
        let window_ms = if bundle != 0 || min_bundle > 0 { window_cfg.max(bundle_ms) } else { window_cfg };""")
rep("""            track_rejects: has("--race-track-rejects"),
            pros,""", """            track_rejects: has("--race-track-rejects"),
            min_bundle,
            max_name_len: arg_u64("--race-max-name-len", 0) as usize,
            pros,""")
rep("""    fn static_ok(&self, launch: &Launch) -> bool {
        launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev""",
    """    fn static_ok(&self, launch: &Launch, tx: &arbx::tx::Tx) -> bool {
        let name_ok = self.cfg.max_name_len == 0
            || snipe::create_strings(tx).map(|(n, _, _)| n.chars().count() <= self.cfg.max_name_len).unwrap_or(false);
        name_ok && launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev""")
rep("""        let static_ok = self.static_ok(launch);""", """        let static_ok = self.static_ok(launch, tx);""")
rep("""            if ms <= bundle_ms && !is_pro {
                p.bundle_n += 1;
                p.cset.insert(payer);
                continue;
            }""", """            if ms <= bundle_ms && !is_pro {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }
                p.cset.insert(payer);
                continue;
            }""")
rep("""                let bundle_ok = match self.cfg.bundle { 1 => p.bundle_n > 0, -1 => p.bundle_n == 0, _ => true };""",
    """                let bundle_ok = p.bundle_n >= self.cfg.min_bundle
                    && match self.cfg.bundle { 1 => p.bundle_n > 0, -1 => p.bundle_n == 0, _ => true };""")
rep("""//   --race-track-rejects    PAPER only:""", """//   --race-min-bundle N     gate: creator bundle of >= N buy txs seen within --race-bundle-ms (0 = off)
//   --race-max-name-len L   gate: token name <= L characters (0 = off)
//   --race-track-rejects    PAPER only:""")
rep("""        format!("race-gate={} log={} dev-from-cap={} dev=[{:.2},{:.2}] SOL window={}ms count_out={} min_out={} min_out_sol={:.2} bundle={} bundle_ms={} obs={}ms pros={}",""",
    """        format!("race-gate={} log={} dev-from-cap={} dev=[{:.2},{:.2}] SOL window={}ms count_out={} min_out={} min_out_sol={:.2} bundle={} bundle_ms={} obs={}ms pros={} min_bundle={} max_name_len={} track_rejects={}",""")
rep("""            self.min_out_sol as f64 / 1e9, self.bundle, self.bundle_ms, self.obs_ms, self.pros.len())""",
    """            self.min_out_sol as f64 / 1e9, self.bundle, self.bundle_ms, self.obs_ms, self.pros.len(), self.min_bundle, self.max_name_len, self.track_rejects)""")
open(ep, "w").write(e)
print("patch6 OK")
