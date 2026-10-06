//! PLAN-ADDENDUM WP-21 point 6: arbx's own bundles through Raydium CLMM and Orca Whirlpool legs, run on the real programs
//! through the deployed route program. The vectors are what arbx's builder makes (`src/exec/tests.rs
//! clmm_bundle_vectors_for_the_venue_harness` writes ../../testdata/builder/bundle-vectors-clmm.json): routes between the
//! fixture pools that share a mint (Whirlpool FAqh ↔ PumpSwap 9qKx both ways, Raydium CLMM DCAL ↔ Whirlpool 4uny both
//! ways, Raydium CLMM 3ucN → Raydium AMM v4 58oQ, and one whose min_profit the route cannot reach), a price gap opened by
//! byte patches the vectors carry, signed by the test wallet. Each one runs here, as signed (v0, its lookup table), in
//! LiteSVM on the dumped mainnet programs (Orca Whirlpool, Raydium CLMM, PumpSwap and its fee program, Raydium AMM v4, SPL
//! Token, Token-2022, the ATA program) and the deployed nexus-arb-v2 ELF (../../testdata/programs, md5 809315be), under
//! the later snapshot's Clock, and:
//!   - nexus-v2 invokes each venue's `swap_v2` with the account list the builder laid out (Raydium: 13 accounts, the
//!     bitmap extension, the tick arrays in walk order; Orca: 15 accounts, its 3 tick arrays and the oracle), patching the
//!     amount at offset 8: the route lands, and each leg delivers exactly what arbx-sizing quoted (nexus-v2's NXV2OUT
//!     records: the buy leg the quote's mid, the sell leg its back);
//!   - the payer's WSOL account gains exactly the quoted profit, at least min_profit; its native lamports move by the base
//!     fee and the tip only (a created mid account is closed in the same transaction: rent locked = rent reclaimed); a held
//!     one stays, empty;
//!   - the CU: the transaction within the limit the builder asked; each leg within the CU model's allowance for its steps
//!     (`Venue::leg_cu`), the rest of the route within `cu_route`;
//!   - a bundle whose min_profit the route cannot reach fails with nexus-v2's 0x4e580002 and leaves nothing;
//!   - the measurements (each leg's CU and steps, the route program's overhead) go to results/arbx-bundle-clmm-runs.json.
//!
//!   cargo test --release --test arbx_bundle_clmm -- --nocapture
mod common;
use common::bundle::*;
use litesvm::LiteSVM;
use serde_json::{json, Value};
use solana_account::Account;
use solana_address::Address;
use solana_keypair::Keypair;
use solana_signer::Signer;
use solana_transaction::Transaction;
use venue_harness::fixture::{program_elf, Fixtures, PoolFixture};
use venue_harness::harness::{create_ata_idempotent, pump_init_user_volume_accumulator};
use venue_harness::keys::{self, *};

/// the programs the vectors' routes invoke, and nexus-v2
fn programs(fx: &Fixtures) -> LiteSVM {
    let mut svm = LiteSVM::new().with_log_bytes_limit(None).with_transaction_history(0).with_blockhash_check(false);
    for (name, id) in keys::PROGRAMS {
        if ![PUMPSWAP, PUMP_FEE_PROGRAM, RAYCLMM, WHIRLPOOL, RAYAMMV4, TOKEN, TOKEN_2022, ATA_PROGRAM].contains(id) { continue; }
        let e = fx.manifest.get(id).unwrap_or_else(|| panic!("{name} not in fixtures/programs"));
        let elf = program_elf(e).unwrap();
        let r = if keys::parse(&e.loader).unwrap() == BPF_LOADER_UPGRADEABLE { svm.add_program(*id, &elf) } else { svm.add_program_with_loader(*id, &elf, keys::parse(&e.loader).unwrap()) };
        r.unwrap_or_else(|err| panic!("loading {name}: {err:?}"));
    }
    svm.add_program(NEXUS, &nexus_elf()).unwrap();
    svm
}

fn fixture<'a>(fx: &'a Fixtures, file: &str) -> &'a PoolFixture {
    fx.pools.values().find(|p| format!("{}-{}.json", p.venue.name(), p.pool) == file).unwrap_or_else(|| panic!("no fixture {file}"))
}

/// One case's state: both pools' snapshots (in the vector's order: the buy's, then the sell's), the vector's patches, the
/// later snapshot's Clock and Rent, the wallet (native SOL, its WSOL account with 50 SOL, its PumpSwap volume accumulator,
/// the mid token's account when the case holds it), the Jito tip account, the vectors' lookup table
fn state(base: &LiteSVM, fx: &Fixtures, v: &Value, c: &Value, payer: &Keypair) -> LiteSVM {
    let mut svm = base.clone();
    for f in c["fixtures"].as_array().unwrap() {
        for (k, a) in fixture(fx, f.as_str().unwrap()).account_map().unwrap() { svm.set_account(k, a).unwrap(); }
    }
    for p in c["patches"].as_array().unwrap() {
        let (k, o, hex) = (addr(p[0].as_str().unwrap()), p[1].as_u64().unwrap() as usize, p[2].as_str().unwrap());
        let b: Vec<u8> = (0..hex.len() / 2).map(|i| u8::from_str_radix(&hex[2 * i..2 * i + 2], 16).unwrap()).collect();
        let mut a = svm.get_account(&k).unwrap_or_else(|| panic!("patch of {k}: not in the fixtures"));
        a.data[o..o + b.len()].copy_from_slice(&b);
        svm.set_account(k, a).unwrap();
    }
    let later = fixture(fx, c["clock_from"].as_str().unwrap());
    svm.set_sysvar(&later.clock.to_clock());
    if let Some(r) = &later.rent { svm.set_sysvar(&r.to_rent()); }
    let u = payer.pubkey();
    svm.set_account(u, Account { lamports: 100_000_000_000, data: vec![], owner: SYSTEM, executable: false, rent_epoch: u64::MAX }).unwrap();
    let ixs = vec![create_ata_idempotent(&u, &u, &WSOL, &TOKEN), pump_init_user_volume_accumulator(&u)];
    let tx = Transaction::new_signed_with_payer(&ixs, Some(&u), &[payer], svm.latest_blockhash());
    svm.send_transaction(tx).unwrap_or_else(|f| panic!("wallet prep: {:?} {:?}", f.err, f.meta.logs));
    let wsol = keys::ata(&u, &WSOL, &TOKEN);
    let mut a = svm.get_account(&wsol).unwrap();
    a.data[64..72].copy_from_slice(&50_000_000_000u64.to_le_bytes());
    a.lamports += 50_000_000_000;
    svm.set_account(wsol, a).unwrap();
    if c["held"].as_bool().unwrap() {
        let (mint, prog) = (addr(c["mint"].as_str().unwrap()), addr(c["token_program"].as_str().unwrap()));
        let tx = Transaction::new_signed_with_payer(&[create_ata_idempotent(&u, &u, &mint, &prog)], Some(&u), &[payer], svm.latest_blockhash());
        svm.send_transaction(tx).unwrap_or_else(|f| panic!("the held account: {:?}", f.err));
    }
    let tip = addr(c["tip"][0].as_str().unwrap());
    svm.set_account(tip, Account { lamports: 1_000_000_000, data: vec![], owner: SYSTEM, executable: false, rent_epoch: u64::MAX }).unwrap();
    let alt: Vec<Address> = v["alt"]["addrs"].as_array().unwrap().iter().map(|a| addr(a.as_str().unwrap())).collect();
    svm.set_account(addr(v["alt"]["table"].as_str().unwrap()), alt_account(&alt)).unwrap();
    svm
}

#[test]
fn arbx_clmm_bundles_on_the_real_programs() {
    let path = repo("testdata/builder/bundle-vectors-clmm.json");
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))).unwrap();
    assert_eq!(v["schema"], "arbx.bundle-vectors/1");
    assert_eq!(v["program"].as_str(), Some(NEXUS.to_string().as_str()), "the vectors route through the deployed nexus-v2");
    let fx = Fixtures::load_all().unwrap();
    let payer = Keypair::new_from_array([v["payer_seed_byte"].as_u64().unwrap() as u8; 32]);
    assert_eq!(payer.pubkey().to_string(), v["payer"].as_str().unwrap(), "the vectors' payer is the test wallet");
    let base = programs(&fx);
    let u = payer.pubkey();
    let wsol = keys::ata(&u, &WSOL, &TOKEN);
    let (mut runs, mut problems, mut landed) = (Vec::new(), Vec::new(), 0);
    for c in v["cases"].as_array().unwrap() {
        let name = c["name"].as_str().unwrap();
        let mut svm = state(&base, &fx, &v, c, &payer);
        let mid = addr(c["mid_account"].as_str().unwrap());
        assert_eq!(mid, keys::ata(&u, &addr(c["mint"].as_str().unwrap()), &addr(c["token_program"].as_str().unwrap())));
        let (tip_acct, tip) = (addr(c["tip"][0].as_str().unwrap()), c["tip"][1].as_u64().unwrap());
        let pre = (svm.get_account(&u).unwrap().lamports, token_amount(&svm, &wsol).unwrap(), svm.get_account(&tip_acct).unwrap().lamports, svm.get_account(&mid).map(|a| a.lamports));
        let tx = versioned(&b64(c["tx_b64"].as_str().unwrap()));
        let keys_static = tx.message.static_account_keys().to_vec();
        let res = svm.send_transaction(tx);
        let post = (svm.get_account(&u).map_or(0, |a| a.lamports), token_amount(&svm, &wsol).unwrap_or(0), svm.get_account(&tip_acct).unwrap().lamports,
            svm.get_account(&mid).filter(|a| a.lamports > 0).map(|a| a.lamports));
        let native = post.0 as i128 - pre.0 as i128;
        let wsol_delta = post.1 as i128 - pre.1 as i128;
        let legs = c["legs"].as_array().unwrap();
        let leg_prog = |i: usize| addr(legs[i]["program"].as_str().unwrap());
        match (c["expect"].as_str().unwrap(), res) {
            ("ok", Ok(meta)) => {
                landed += 1;
                let fee = 5_000i128;
                let locked = rent_locked(&meta.inner_instructions, &keys_static);
                let reclaimed = (native + fee + tip as i128 + locked as i128) as u64;
                // each leg's CU at depth 2 (under nexus-v2); the route program's own
                let cu_legs: Vec<Option<u64>> = (0..2).map(|i| venue_cu_depth(&meta.logs, &leg_prog(i), 2)).collect();
                let outer = venue_cu_depth(&meta.logs, &NEXUS, 1).unwrap_or(0);
                let delivered = nexus_delivered(&meta.logs);
                let (create, close) = (venue_cu_depth(&meta.logs, &ATA_PROGRAM, 1), venue_cu_depth(&meta.logs, &addr(c["token_program"].as_str().unwrap()), 1));
                println!("{name:<40} ok: WSOL +{wsol_delta} (quoted {}), legs delivered {delivered:?} (quoted {} / {}), native {native} (fee {fee} + tip {tip}), \
                    rent {locked}/{reclaimed}, CU {} of {} (route {outer}: legs {cu_legs:?} allowed [{}, {}] at steps [{}, {}])",
                    c["expected_profit"], c["mid"], c["back"], meta.compute_units_consumed, c["cu_limit"], legs[0]["cu_allowed"], legs[1]["cu_allowed"], legs[0]["steps"], legs[1]["steps"]);
                for (i, l) in legs.iter().enumerate() {
                    if cu_legs[i].is_none() { problems.push(format!("{name}: leg {i} ({}) was not invoked under nexus-v2", l["venue"])); }
                    if cu_legs[i].is_some_and(|x| x > l["cu_allowed"].as_u64().unwrap()) {
                        problems.push(format!("{name}: leg {i} ({}) took {:?} CU at {} steps, the model allows {}", l["venue"], cu_legs[i], l["steps"], l["cu_allowed"]));
                    }
                }
                if delivered != vec![(0, c["mid"].as_u64().unwrap()), (1, c["back"].as_u64().unwrap())] {
                    problems.push(format!("{name}: the legs delivered {delivered:?}, arbx-sizing quoted {} then {}", c["mid"], c["back"]));
                }
                if wsol_delta != c["expected_profit"].as_i64().unwrap() as i128 { problems.push(format!("{name}: WSOL +{wsol_delta}, arbx-sizing quoted {}", c["expected_profit"])); }
                if wsol_delta < c["min_profit"].as_u64().unwrap() as i128 { problems.push(format!("{name}: below min_profit")); }
                if native != -fee - tip as i128 { problems.push(format!("{name}: native moved {native}, not -fee -tip = {}", -fee - tip as i128)); }
                if locked != reclaimed { problems.push(format!("{name}: rent locked {locked} != reclaimed {reclaimed}")); }
                let held = c["held"].as_bool().unwrap();
                if !held && locked == 0 { problems.push(format!("{name}: no rent was locked: no account created")); }
                if held && locked != 0 { problems.push(format!("{name}: a held token's bundle created an account ({locked})")); }
                if post.2 - pre.2 != tip { problems.push(format!("{name}: the tip account got {}", post.2 - pre.2)); }
                match (held, post.3) {
                    (false, Some(l)) => problems.push(format!("{name}: the created account is still there ({l} lamports): rent locked")),
                    (true, None) => problems.push(format!("{name}: the held account was closed")),
                    (true, Some(_)) => if token_amount(&svm, &mid) != Some(0) { problems.push(format!("{name}: the held account kept tokens")); },
                    _ => {}
                }
                if meta.compute_units_consumed > c["cu_limit"].as_u64().unwrap() { problems.push(format!("{name}: CU {} over the limit", meta.compute_units_consumed)); }
                let (a_create, a_close, a_route) = (c["cu_ata"][0].as_u64().unwrap(), c["cu_ata"][1].as_u64().unwrap(), c["cu_route"].as_u64().unwrap());
                if create.is_some_and(|x| x > a_create) { problems.push(format!("{name}: the ATA create took {create:?} CU, allowed {a_create}")); }
                if close.is_some_and(|x| x > a_close) { problems.push(format!("{name}: the close took {close:?} CU, allowed {a_close}")); }
                let rest = meta.compute_units_consumed - create.unwrap_or(0) - close.unwrap_or(0);
                if rest > a_route { problems.push(format!("{name}: the route and the rest took {rest} CU, allowed {a_route}")); }
                runs.push(json!({ "name": name, "ok": true, "cu_tx": meta.compute_units_consumed, "cu_limit": c["cu_limit"], "cu_route_outer": outer,
                    "cu_legs": cu_legs, "legs": legs.iter().map(|l| json!({ "venue": l["venue"], "pool": l["pool"], "n_accounts": l["n_accounts"], "steps": l["steps"],
                        "tick_arrays": l["tick_arrays"], "cu_allowed": l["cu_allowed"] })).collect::<Vec<_>>(),
                    "cu_overhead": outer.saturating_sub(cu_legs.iter().flatten().sum::<u64>()), "cu_ata_create": create, "cu_ata_close": close,
                    "delivered": delivered.iter().map(|d| d.1).collect::<Vec<_>>(), "wsol_delta": wsol_delta as i64, "native_delta": native as i64, "tip": tip,
                    "rent_locked": locked, "bytes": c["bytes"], "loaded_data_limit": c["loaded_data_limit"] }));
            }
            ("profit_fail", Err(f)) => {
                let code = match &f.err { solana_transaction_error::TransactionError::InstructionError(_, solana_instruction_error::InstructionError::Custom(c)) => Some(*c), _ => None };
                // the legs ran (each delivered) before the profit check refused the route
                let delivered = nexus_delivered(&f.meta.logs);
                println!("{name:<40} failed as built to: {:?} after the legs delivered {delivered:?}; native {native}, WSOL {wsol_delta}, account after {:?}", f.err, post.3);
                if code != Some(ERR_PROFIT) { problems.push(format!("{name}: failed with {:?}, not 0x4e580002", f.err)); }
                if delivered.len() != 2 { problems.push(format!("{name}: {} legs delivered before the profit check", delivered.len())); }
                if post.3.is_some() { problems.push(format!("{name}: a failed bundle left the created account")); }
                if wsol_delta != 0 { problems.push(format!("{name}: a failed bundle moved WSOL {wsol_delta}")); }
                if !(native == 0 || native == -5_000) { problems.push(format!("{name}: a failed bundle moved native {native}")); }
                runs.push(json!({ "name": name, "ok": false, "err": format!("{:?}", f.err), "delivered": delivered.iter().map(|d| d.1).collect::<Vec<_>>(),
                    "native_delta": native as i64 }));
            }
            (want, got) => problems.push(format!("{name}: expected {want}, got {:?}", got.map(|m| m.logs).map_err(|f| (f.err, f.meta.logs)))),
        }
    }
    let out = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("arbx-bundle-clmm-runs.json"), serde_json::to_string_pretty(&json!({ "vectors": v["cases"].as_array().unwrap().len(), "runs": runs })).unwrap()).unwrap();
    for p in &problems { println!("PROBLEM {p}"); }
    assert!(problems.is_empty(), "{} problems", problems.len());
    assert!(landed >= 5, "{landed} routes landed");
}
