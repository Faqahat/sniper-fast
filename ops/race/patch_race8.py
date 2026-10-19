#!/usr/bin/env python3
# RACE-GATE patch part 8 (2026-10-18 night): creator-bundle SOL bounds and a create-tx tip-destination prefix.
#   --race-min-bundle-sol F / --race-max-bundle-sol F   creator bundle SOL (sum of bundle buys within --race-bundle-ms)
#   --race-create-tip-prefix P                           the create tx's largest SOL transfer goes to an account whose
#                                                        base58 starts with P (e.g. "moon" = Lunar Lander tip accounts)
import sys
ep = sys.argv[1]
e = open(ep).read()
def rep(old, new, cnt=1):
    global e
    assert e.count(old) == cnt, (e.count(old), old[:90])
    e = e.replace(old, new)
rep("""    /// --race-max-name-len L: token name <= L chars (0 = off)
    max_name_len: usize,""", """    /// --race-max-name-len L: token name <= L chars (0 = off)
    max_name_len: usize,
    /// --race-min-bundle-sol / --race-max-bundle-sol: creator bundle SOL bounds (lamports)
    min_bundle_sol: u64,
    max_bundle_sol: u64,
    /// --race-create-tip-prefix: create tx's largest non-signer SOL transfer goes to an account with this base58 prefix
    create_tip_prefix: Option<String>,""")
rep("""        let min_bundle = arg_u64("--race-min-bundle", 0) as u32;
        let window_ms = if bundle != 0 || min_bundle > 0 { window_cfg.max(bundle_ms) } else { window_cfg };""",
    """        let min_bundle = arg_u64("--race-min-bundle", 0) as u32;
        let bsol_flags = arg("--race-min-bundle-sol").is_some() || arg("--race-max-bundle-sol").is_some();
        let window_ms = if bundle != 0 || min_bundle > 0 || bsol_flags { window_cfg.max(bundle_ms) } else { window_cfg };""")
rep("""            max_name_len: arg_u64("--race-max-name-len", 0) as usize,""", """            max_name_len: arg_u64("--race-max-name-len", 0) as usize,
            min_bundle_sol: (arg_f64("--race-min-bundle-sol", 0.0) * 1e9) as u64,
            max_bundle_sol: (arg_f64("--race-max-bundle-sol", 1e9) * 1e9) as u64,
            create_tip_prefix: arg("--race-create-tip-prefix"),""")
rep("""    bundle_n: u32,
    /// (ms after the create""", """    bundle_n: u32,
    /// creator-bundle buy SOL seen within bundle_ms (sized amount, or cap-family priced on the curve)
    bundle_sol: u64,
    /// (ms after the create""")
rep("""        name_ok && launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev""",
    """        let tip_ok = match &self.cfg.create_tip_prefix {
            None => true,
            Some(pf) => snipe::create_info(tx).tip_to.map(|k| b58(&k).starts_with(pf.as_str())).unwrap_or(false),
        };
        tip_ok && name_ok && launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev""")
rep("""RacePend { launch: launch.clone(), slot, t0: Instant::now(), cset, bundle_n: 0, out: Vec::new(),""",
    """RacePend { launch: launch.clone(), slot, t0: Instant::now(), cset, bundle_n: 0, bundle_sol: 0, out: Vec::new(),""")
rep("""            if signers.iter().any(|s| p.cset.contains(s)) {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }
                continue;
            }
            if ms <= bundle_ms && !is_pro {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }
                p.cset.insert(payer);
                continue;
            }""", """            let bvq = snipe::CURVE_VQ0 + p.launch.dev_buy_lamports + p.bundle_sol;
            let bsol = match touch {
                snipe::MintTouch::Buy(s) => s,
                snipe::MintTouch::BuyCap { tokens, max_sol } => { let est = snipe::curve_cost(bvq, tokens); if max_sol > 0 && max_sol < est { max_sol } else { est } }
                _ => 0,
            };
            if signers.iter().any(|s| p.cset.contains(s)) {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; p.bundle_sol = p.bundle_sol.saturating_add(bsol); }
                continue;
            }
            if ms <= bundle_ms && !is_pro {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; p.bundle_sol = p.bundle_sol.saturating_add(bsol); }
                p.cset.insert(payer);
                continue;
            }""")
rep("""                let bundle_ok = p.bundle_n >= self.cfg.min_bundle""", """                let bundle_ok = p.bundle_n >= self.cfg.min_bundle
                    && p.bundle_sol >= self.cfg.min_bundle_sol && p.bundle_sol <= self.cfg.max_bundle_sol""")
rep("""first_ms={first:.1} bundle_n={} fired={} outs={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.pass,""",
    """first_ms={first:.1} bundle_n={} bundle_sol={:.3} fired={} outs={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.bundle_sol as f64 / 1e9, p.pass,""")
rep("""//   --race-max-name-len L   gate: token name <= L characters (0 = off)""", """//   --race-max-name-len L   gate: token name <= L characters (0 = off)
//   --race-min-bundle-sol F / --race-max-bundle-sol F  gate: creator bundle SOL (sum of its buys within --race-bundle-ms)
//   --race-create-tip-prefix P  gate: the create tx's largest SOL transfer goes to an account starting with P ("moon" = Lunar)""")
open(ep, "w").write(e)
print("patch8 OK")
