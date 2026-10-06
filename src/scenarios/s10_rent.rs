//! S10 (PLAN WP-09's table, after WP-06): rent neutrality. A non-held mid mint gets create and close; a held one gets
//! neither. On real USDC/SOL pools with a dry-run executor (its would-sends signed and checked from the signed bytes):
//! the token account the route trades through is created (idempotent) before the route and closed to the payer after
//! it, in the same transaction, when the wallet holds none; never when it holds one. Whether it holds one is the
//! store's view where the state stream follows the wallet (PLAN-ADDENDUM: "held-set changes during a run ... derived from
//! journaled inputs"): an account that appears mid-run (the owner's wallet prep, a held-set addition landing) stops the
//! create and close from the next decision on, and the replay builds the same bundles. The PumpSwap user volume
//! accumulator is read the same way (`uva_missing`)
use super::*;
use crate::exec::Mode;

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
/// about the bundles, not the ≥1M class's throttle (S11)
const NO_BAND_THROTTLE: [(&str, &str); 1] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0")];

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve by `label` at `slot`, resolved by quiescence; returns the time after
fn usdc_sale(r: &mut Rig, m: &PoolMeta, frac: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    let s = r.sig(label);
    for (k, d) in w { r.write(k, d, slot, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    t + 5 * MS
}

/// (creates_ata, closes_ata, the dry run's checks all passed, the route's mint) of every attempt
fn bundles(r: &Rig) -> Vec<(bool, bool, bool, String)> {
    r.attempts().iter().map(|a| (a["tx"]["creates_ata"].as_bool().unwrap(), a["tx"]["closes_ata"].as_bool().unwrap(), a["dry_run"]["checks_ok"].as_bool().unwrap(),
        a["route"]["mint"].as_str().unwrap().to_string())).collect()
}

/// a few USDC sales on the AMM v4 pool (each opens a gap to the other pools), a slot and the blockhash ring's head first
fn trade(r: &mut Rig, labels: &[&str], slot: u64, t: u64) -> u64 { trade_on(r, "usdc.ammv4", labels, slot, t) }

fn trade_on(r: &mut Rig, pool: &str, labels: &[&str], slot: u64, mut t: u64) -> u64 {
    let a = r.meta(pool);
    r.tick(slot, t);
    r.blockhash(slot, t + 200 * US);
    t += MS;
    for l in labels { t = usdc_sale(r, &a, 300, l, slot, t + 5 * MS); }
    t
}

fn rig(name: &'static str, hold_tokens: bool, wallet: Option<WalletSetup<'static>>) -> Rig {
    let mut r = Rig::new(name, Setup { pools: &POOLS3, config: &NO_BAND_THROTTLE, exec: Some(ExecSetup { mode: Mode::DryRun, hold_tokens, ..Default::default() }),
        wallet, ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    r
}

/// The boot read (the state stream does not follow the wallet here): a token the wallet holds no account for gets the
/// create and the close in every bundle through it, a held one neither; every signed bundle passes the dry run's checks
/// (the order, the create's account, the close to the payer, the rent back in the same transaction)
#[test]
fn s10_a_non_held_mid_mint_gets_create_and_close_a_held_one_neither() {
    for (hold, want) in [(false, (true, true)), (true, (false, false))] {
        let mut r = rig(if hold { "s10-held" } else { "s10-not-held" }, hold, None);
        let s2 = r.s0 + 2;
        trade(&mut r, &["S10-a", "S10-b", "S10-c"], s2, T0 + 10 * MS);
        let b = bundles(&r);
        assert!(!b.is_empty(), "the sales open gaps the dry run builds");
        for (creates, closes, ok, _) in &b { assert_eq!(((*creates, *closes), *ok), (want, true), "held {hold}: {b:?}"); }
        // decisions 1.2: every route says whether the DLMM window bound its size (a bool when priced, null when not)
        let routes: Vec<serde_json::Value> = r.evaluations().iter().flat_map(|d| d["routes"].as_array().cloned().unwrap_or_default()).collect();
        assert!(!routes.is_empty() && routes.iter().all(|x| x.get("dlmm_cap_bound").is_some_and(|c| c.is_boolean() == x["size"].is_u64())), "{routes:?}");
        let done = r.finish_and_replay();
        assert_eq!(done.replay["executor"]["replayed"].as_bool(), Some(true));
        // review WP-06 #8: a what-if tip model reaches the replayed executor (its tips, min_profit and bands), not only the
        // engine's fee
        if !hold {
            let out = done.dir.join("tips-what-if");
            let sets = vec!["tips.shares=[0.35,0.35,0.35,0.35,0.35]".parse().unwrap()];
            crate::replay::replay(&done.dir, &crate::replay::Opts { compare: true, sets, out: Some(out.clone()), ..Default::default() }).unwrap();
            let (run, what_if) = (rec::read_jsonl(&done.dir, "attempts").unwrap(), rec::read_jsonl(&out, "attempts").unwrap());
            assert!(!what_if.is_empty() && run.iter().all(|a| a["tip"]["share"].as_f64() == Some(0.7)), "{run:?}");
            assert!(what_if.iter().all(|a| a["tip"]["share"].as_f64() == Some(0.35)), "{what_if:?}");
        }
    }
}

/// The store's view (the state stream follows the wallet, `[state] watch_wallet`): the wallet holds no USDC account at
/// boot, so the first bundles create and close it; then the account appears on the stream (the owner's wallet prep) and
/// the next bundles name it as it is, creating and closing nothing. The replay rebuilds the same bundles from the same
/// journaled records. With the accumulator absent, the PumpSwap buys are refused `uva_missing`
#[test]
fn s10_the_held_view_follows_the_wallet_on_the_stream_and_replays() {
    let mut r = rig("s10-wallet", false, Some(WalletSetup { holds: &[], uva: true, lamports: 3 * SOL }));
    let payer = crate::tx::pk(&r.cfg.wallet);
    let s2 = r.s0 + 2;
    let t = trade(&mut r, &["S10-w1", "S10-w2"], s2, T0 + 10 * MS);
    let before = bundles(&r);
    assert!(!before.is_empty() && before.iter().all(|b| b.0 && b.1 && b.2), "not held at boot: create and close: {before:?}");
    // the bankroll the WP-07 cap will read: the wallet's lamports and WSOL from the store
    let bk = r.e.bankroll(&payer);
    assert_eq!((bk.native, bk.wsol), (Some(3 * SOL), Some(5 * SOL)));
    // the USDC account appears
    let usdc = { let m = r.meta("usdc.ammv4"); if m.t0 == *crate::venues::WSOL { (m.t1, m.t1_prog) } else { (m.t0, m.t0_prog) } };
    let ata = crate::build::ata_of(&payer, &usdc.0, &usdc.1);
    let s3 = s2 + 1;
    r.write(ata, token_account(&usdc.0, &payer, 0), s3, None, t + MS);
    trade(&mut r, &["S10-w3", "S10-w4"], s3, t + 2 * MS);
    let after = bundles(&r)[before.len()..].to_vec();
    assert!(!after.is_empty() && after.iter().all(|b| !b.0 && !b.1 && b.2), "held now: neither: {after:?}");
    let done = r.finish_and_replay();
    assert_eq!(done.replay["executor"]["replayed"].as_bool(), Some(true));

    // the accumulator absent: USDC sold into the PumpSwap pool makes it cheap there, and no PumpSwap buy is built
    // (`uva_missing` behind the closed gate); the wallet holds its USDC account
    let mut r = rig("s10-no-uva", false, Some(WalletSetup { holds: &["usdc.pump"], uva: false, lamports: SOL }));
    let s2 = r.s0 + 2;
    trade_on(&mut r, "usdc.pump", &["S10-u1", "S10-u2", "S10-u3"], s2, T0 + 10 * MS);
    let pump = b58(&r.meta("usdc.pump").pool);
    let opps = r.opportunities();
    assert!(r.attempts().iter().all(|a| a["route"]["buy_pool"] != pump), "no attempt buys on PumpSwap");
    let refused = opps.iter().filter(|d| d["reason_ungated"] == "uva_missing").count();
    assert!(refused > 0, "the PumpSwap buys are refused: {:?}", opps.iter().map(|d| (d["reason"].clone(), d["reason_ungated"].clone())).collect::<Vec<_>>());
    r.finish_and_replay();
}
