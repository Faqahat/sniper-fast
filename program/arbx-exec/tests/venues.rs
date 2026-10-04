//! Real-venue SVM tests (REVIEW.md #3; plan §3.9 "SVM integration tests for each venue, on captured mainnet account
//! snapshots"). The MAINNET venue programs (DLMM, PumpSwap + its fee program, DAMM v2, Raydium CPMM, Raydium AMM v4)
//! run from their programdata ELFs, on account snapshots captured by tests/fixtures/fetch_venues.py, under LiteSVM's
//! mainnet feature set, with the built arbx-exec in front of them.
//!
//! The legs are built exactly as the engine builds them (src/build.rs `leg`, `pump_leg`, `dlmm_leg`, ported below
//! account for account), so these tests also pin the engine's account layouts against the real programs.
//!
//! Refresh the snapshots: python3 tests/fixtures/fetch_venues.py   (public read-only RPC)
mod common;

use arbx_exec::logic::*;
use base64::Engine as _;
use common::*;
use litesvm::LiteSVM;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_keypair::Keypair;
use solana_message::AddressLookupTableAccount;
use solana_signer::Signer;
use std::collections::HashMap;

const ATA_PROGRAM: Address = Address::from_str_const("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL");
const MEMO: Address = Address::from_str_const("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr");
const PUMP_FEE_PROGRAM: Address = Address::from_str_const("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ");
const PUMP_GLOBAL_CONFIG: Address = Address::from_str_const("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw");
const PUMP_EVENT_AUTHORITY: Address = Address::from_str_const("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR");
const PUMP_GVA: Address = Address::from_str_const("C2aFPdENg4A2HQsmrd5rTw5TaYBX5Ku887cWjbFKtZpw");
const PUMP_FEE_CONFIG: Address = Address::from_str_const("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx");
const RAYCPMM_AUTHORITY: Address = Address::from_str_const("GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL");
const DAMMV2_POOL_AUTHORITY: Address = Address::from_str_const("HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC");
const DAMMV2_EVENT_AUTHORITY: Address = Address::from_str_const("3rmHSu74h1ZcmAisVcWerTCiRDQbUrBKmcwptYGjHfet");

const DAMMV2_SWAP: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];
const PUMP_SELL: [u8; 8] = [0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
const PUMP_BUY_EXACT_QUOTE_IN: [u8; 8] = [0xc6, 0x2e, 0x15, 0x52, 0xb4, 0xd9, 0xe8, 0x70];
const CPMM_SWAP_BASE_INPUT: [u8; 8] = [0x8f, 0xbe, 0x5a, 0xda, 0xc4, 0x1e, 0x33, 0xde];
const DLMM_SWAP2: [u8; 8] = [0x41, 0x4b, 0x3f, 0x4c, 0xeb, 0x5b, 0x5b, 0x88];
const AMMV4_SWAP_BASE_IN_V2: u8 = 16;

// ---------------------------------------------------------------------------------------------------------------------
// fixtures
// ---------------------------------------------------------------------------------------------------------------------

struct Fixture {
    name: String,
    venue: String,
    pool: Address,
    program: Address,
    slot: u64,
    unix_timestamp: i64,
    roles: HashMap<String, Address>,
    accounts: HashMap<Address, Account>,
}

fn addr(s: &str) -> Address { Address::from_str_const(s) }

fn load(name: &str) -> Fixture {
    let j: serde_json::Value = serde_json::from_slice(&read(&format!("tests/fixtures/venues/{name}.json"))).unwrap();
    let s = |k: &str| j[k].as_str().unwrap().to_string();
    let roles = j["roles"].as_object().unwrap().iter().map(|(r, v)| (r.clone(), addr(v.as_str().unwrap()))).collect();
    let accounts = j["accounts"].as_object().unwrap().iter().map(|(key, a)| {
        let data = base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap();
        (addr(key), Account { lamports: a["lamports"].as_u64().unwrap(), data, owner: addr(a["owner"].as_str().unwrap()),
            executable: a["executable"].as_bool().unwrap(), rent_epoch: a["rent_epoch"].as_u64().unwrap() })
    }).collect();
    Fixture { name: s("name"), venue: s("venue"), pool: addr(&s("pool")), program: addr(&s("program")), slot: j["slot"].as_u64().unwrap(),
        unix_timestamp: j["unix_timestamp"].as_i64().unwrap(), roles, accounts }
}

impl Fixture {
    fn role(&self, r: &str) -> Address { *self.roles.get(r).unwrap_or_else(|| panic!("{}: no role {r}", self.name)) }
    fn data(&self, k: &Address) -> &[u8] { &self.accounts.get(k).unwrap_or_else(|| panic!("{}: account {k} not in the snapshot", self.name)).data }
    fn pool_data(&self) -> &[u8] { self.data(&self.pool) }
    fn has(&self, k: &Address) -> bool { self.accounts.contains_key(k) }
    fn mints(&self) -> (Address, Address) { (self.role("mint0"), self.role("mint1")) }
    fn token_program(&self, mint: &Address) -> Address { self.accounts[mint].owner }
}

fn pk_at(d: &[u8], o: usize) -> Address { Address::new_from_array(d[o..o + 32].try_into().unwrap()) }
fn ata(owner: &Address, mint: &Address, prog: &Address) -> Address {
    Address::find_program_address(&[owner.as_ref(), prog.as_ref(), mint.as_ref()], &ATA_PROGRAM).0
}

/// LiteSVM (mainnet features) with arbx-exec, the venue programs of `fixtures` from their mainnet ELFs, every
/// snapshot account, and the clock at the snapshot's slot and time.
fn world(fixtures: &[&Fixture]) -> (LiteSVM, Keypair) {
    let mut svm = mainnet_svm();
    let mut progs: Vec<Address> = fixtures.iter().map(|f| f.program).collect();
    if fixtures.iter().any(|f| f.venue == "pumpswap") { progs.push(PUMP_FEE_PROGRAM); }
    progs.dedup();
    for p in progs { svm.add_program(p, &read(&format!("tests/fixtures/programs/{p}.so"))).unwrap(); }
    for f in fixtures {
        for (k, a) in &f.accounts { svm.set_account(*k, a.clone()).unwrap(); }
    }
    let slot = fixtures.iter().map(|f| f.slot).max().unwrap();
    let ts = fixtures.iter().map(|f| f.unix_timestamp).max().unwrap();
    svm.warp_to_slot(slot);
    let epoch = slot / 432_000;
    svm.set_sysvar(&solana_clock::Clock { slot, epoch_start_timestamp: ts, epoch, leader_schedule_epoch: epoch + 1, unix_timestamp: ts });
    // a fixed test key: venues derive PDAs from the payer (PumpSwap's volume accumulator), and every extra bump
    // search costs 1,500 CU, so a random key would make the CU numbers drift between runs
    let payer = Keypair::new_from_array([0x42; 32]);
    svm.airdrop(&payer.pubkey(), 100 * SOL).unwrap();
    (svm, payer)
}

/// Our wSOL ATA (10 SOL) and an empty ATA for every other mint of `fixtures`.
fn user_accounts(svm: &mut LiteSVM, payer: &Address, fixtures: &[&Fixture]) -> Address {
    let quote = ata(payer, &WSOL, &TOKEN);
    set_token(svm, quote, WSOL, *payer, 10 * SOL, true);
    for f in fixtures {
        let (m0, m1) = f.mints();
        for m in [m0, m1] {
            if m == WSOL { continue; }
            let prog = f.token_program(&m);
            assert_eq!(prog, TOKEN, "{}: Token-2022 user accounts are not built by this harness", f.name);
            set_token_with(svm, ata(payer, &m, &prog), m, *payer, 0, false, prog);
        }
    }
    quote
}

// ---------------------------------------------------------------------------------------------------------------------
// the engine's leg builders (src/build.rs), account for account
// ---------------------------------------------------------------------------------------------------------------------

fn w(k: Address) -> AccountMeta { AccountMeta::new(k, false) }
fn r(k: Address) -> AccountMeta { AccountMeta::new_readonly(k, false) }
fn s(k: Address) -> AccountMeta { AccountMeta::new(k, true) }

/// One leg tin -> tout on the fixture's pool, spending `amount` (patched on chain anyway), as build.rs `leg` builds it.
fn engine_leg(f: &Fixture, tin: Address, tout: Address, payer: Address, amount: u64) -> Leg {
    let (t0, t1) = f.mints();
    assert!((tin == t0 && tout == t1) || (tin == t1 && tout == t0), "{}: mints not of this pool", f.name);
    let prog_of = |m: &Address| f.token_program(m);
    let user = |m: &Address| ata(&payer, m, &prog_of(m));
    let zfo = tin == t0;
    let out = user(&tout);
    let pid = f.program;
    let (v0, v1) = (f.role("vault0"), f.role("vault1"));
    let mut tail = amount.to_le_bytes().to_vec();
    tail.extend(1u64.to_le_bytes());
    let d = f.pool_data();
    let (metas, data, amount_offset) = match f.venue.as_str() {
        "ammv4" => {
            // swap_base_in_v2 (tag 16): every account from the pool; spl-token only
            let metas = vec![r(TOKEN), w(f.pool), r(f.role("authority")), w(v0), w(v1), w(user(&tin)), w(out), s(payer)];
            let mut data = vec![AMMV4_SWAP_BASE_IN_V2];
            data.extend(&tail);
            (metas, data, 1u8)
        }
        "cpmm" => {
            let (cfg, obs) = (pk_at(d, 8), pk_at(d, 296));
            assert_eq!((cfg, obs), (f.role("config"), f.role("observation")));
            let (vin, vout) = if zfo { (v0, v1) } else { (v1, v0) };
            let metas = vec![s(payer), r(RAYCPMM_AUTHORITY), r(cfg), w(f.pool), w(user(&tin)), w(out), w(vin), w(vout),
                r(prog_of(&tin)), r(prog_of(&tout)), r(tin), r(tout), w(obs)];
            let mut data = CPMM_SWAP_BASE_INPUT.to_vec();
            data.extend(&tail);
            (metas, data, 8)
        }
        "dammv2" => {
            // vaults and mints in the POOL's order whatever the direction; referral None = the program id
            let metas = vec![r(DAMMV2_POOL_AUTHORITY), w(f.pool), w(user(&tin)), w(out), w(v0), w(v1), r(t0), r(t1),
                s(payer), r(prog_of(&t0)), r(prog_of(&t1)), r(pid), r(DAMMV2_EVENT_AUTHORITY), r(pid)];
            let mut data = DAMMV2_SWAP.to_vec();
            data.extend(&tail);
            (metas, data, 8)
        }
        "dlmm" => {
            // bin arrays: the active one, then onward in the direction of travel (one buffer array), only if held
            let oracle = pk_at(d, 552);
            let active = i32::from_le_bytes(d[76..80].try_into().unwrap());
            let c = (active as i64).div_euclid(70);
            let array = |i: i64| Address::find_program_address(&[b"bin_array", f.pool.as_ref(), &i.to_le_bytes()], &pid).0;
            assert!(f.has(&array(c)), "{}: active bin array not in the snapshot", f.name);
            let step: i64 = if zfo { -1 } else { 1 };
            let mut picks = vec![c];
            let mut i = c;
            while picks.len() < 5 {
                i += step;
                if !f.has(&array(i)) { break; }
                picks.push(i);
                if (i - c) * step >= 1 { break; }
            }
            let ext = f.role("bitmap_ext");
            let ext = if f.has(&ext) { w(ext) } else { r(pid) };
            let mut metas = vec![w(f.pool), ext, w(v0), w(v1), w(user(&tin)), w(out), r(t0), r(t1), w(oracle), r(pid), s(payer),
                r(prog_of(&t0)), r(prog_of(&t1)), r(MEMO), r(f.role("event_authority")), r(pid)];
            metas.extend(picks.iter().map(|p| w(array(*p))));
            let mut data = DLMM_SWAP2.to_vec();
            data.extend(&tail);
            data.extend(0u32.to_le_bytes()); // remaining_accounts_info: no transfer-hook slices
            (metas, data, 8)
        }
        "pumpswap" => {
            let g = f.data(&PUMP_GLOBAL_CONFIG);
            let keys = |at: usize, n: usize| -> Vec<Address> { (0..n).map(|i| pk_at(g, at + 32 * i)).filter(|k| *k != Address::default()).collect() };
            let (protocol, mut reserved, buyback) = (keys(57, 8), keys(385, 1), keys(643, 8));
            reserved.extend(keys(418, 7));
            let sell = tin == t0;
            assert_eq!(g[56] & if sell { 1 << 4 } else { 1 << 3 }, 0, "pump {} disabled", if sell { "sell" } else { "buy" });
            let creator = pk_at(d, 211);
            let (mayhem, cashback) = (d.get(243) == Some(&1), d.get(244) == Some(&1));
            let fees = if mayhem { &reserved } else { &protocol };
            let (base_prog, quote_prog, quote) = (prog_of(&t0), prog_of(&t1), t1);
            let pick = f.pool.as_ref()[0] as usize;
            let (fee_recipient, bb) = (fees[pick % fees.len()], buyback[pick % buyback.len()]);
            let creator_auth = Address::find_program_address(&[b"creator_vault", creator.as_ref()], &pid).0;
            let uva = Address::find_program_address(&[b"user_volume_accumulator", payer.as_ref()], &pid).0;
            let quote_ata = |owner: &Address| ata(owner, &quote, &quote_prog);
            let mut metas = vec![w(f.pool), s(payer), r(PUMP_GLOBAL_CONFIG), r(t0), r(t1), w(ata(&payer, &t0, &base_prog)),
                w(ata(&payer, &t1, &quote_prog)), w(v0), w(v1), r(fee_recipient), w(quote_ata(&fee_recipient)), r(base_prog),
                r(quote_prog), r(SYSTEM), r(ATA_PROGRAM), r(PUMP_EVENT_AUTHORITY), r(pid), w(quote_ata(&creator_auth)), r(creator_auth)];
            if !sell { metas.push(r(PUMP_GVA)); metas.push(w(uva)); }
            metas.push(r(PUMP_FEE_CONFIG));
            metas.push(r(PUMP_FEE_PROGRAM));
            let has_v2 = creator != Address::default();
            if cashback && !has_v2 { metas.push(w(quote_ata(&uva))); if sell { metas.push(w(uva)); } }
            if has_v2 { metas.push(r(Address::find_program_address(&[b"pool-v2", t0.as_ref()], &pid).0)); }
            metas.push(r(bb));
            metas.push(w(quote_ata(&bb)));
            let mut data = if sell { PUMP_SELL.to_vec() } else { PUMP_BUY_EXACT_QUOTE_IN.to_vec() };
            data.extend(&tail);
            (metas, data, 8)
        }
        v => panic!("venue {v}"),
    };
    Leg { out, program: pid, metas, data, flags: 0, amount_offset }
}

/// The non-wSOL mint of a SOL pool
fn other_mint(f: &Fixture) -> Address { let (a, b) = f.mints(); if a == WSOL { b } else { a } }

/// "Program <venue> consumed N of M compute units" of the venue's own invocations at depth 2 (arbx-exec's CPIs), in
/// order: one per leg. The venue's self-CPIs (Anchor event emission) at depth 3 are inside these.
fn venue_cus(o: &Outcome, venue: &Address) -> Vec<u64> {
    let (consumed, invoke) = (format!("Program {venue} consumed "), format!("Program {venue} invoke ["));
    let mut stack: Vec<bool> = Vec::new(); // per open invocation: is it the venue at depth 2
    let mut out = Vec::new();
    for l in &o.logs {
        if let Some(rest) = l.strip_prefix("Program ") {
            if rest.contains(" invoke [") { stack.push(l.starts_with(&invoke) && rest.ends_with(" invoke [2]")); continue; }
            if rest.ends_with(" success") || rest.contains(" failed: ") { stack.pop(); continue; }
        }
        if let Some(n) = l.strip_prefix(&consumed).and_then(|r| r.split(' ').next()).and_then(|n| n.parse().ok()) {
            if stack.last() == Some(&true) { out.push(n); }
        }
    }
    out
}

// (fixture, amount_in in lamports, max_payer_lamport_drop, arbx-exec CU budget for the 2-leg route: the route's CU
// minus the two venue invocations', i.e. what the program itself adds; measured 2026-10-04 plus ~5%)
const VENUES: [(&str, u64, u64, u64); 6] = [
    ("dlmm_sol_usdc", SOL / 10, 0, 15_400),
    ("ammv4_sol_usdc", SOL / 10, 0, 11_100),
    ("dammv2_sol_usdc", SOL / 10, 0, 13_100),
    ("cpmm_sol_token", SOL / 100, 0, 13_100),
    // the first PumpSwap buy creates the payer's user volume accumulator (rent from the payer): max_drop covers it
    ("pumpswap_sol_usdc", SOL / 10, 5_000_000, 18_800),
    ("pumpswap_pump_token", SOL / 100, 5_000_000, 19_200),
];

fn venue_index(program: &Address) -> u8 { ALLOWLIST_B58.iter().position(|k| addr(k) == *program).unwrap() as u8 }

// =====================================================================================================================
// tests
// =====================================================================================================================

/// Every venue, through arbx-exec v3 (PAYER_GUARD | COUNT_LAMPORTS): wSOL -> X -> wSOL on the same real pool. A round
/// trip on one pool loses both fees, so the route must run BOTH legs (two AXL1 records, leg 1 spending exactly what
/// leg 0 delivered) and then fail the guard with ERR_PROFIT, with AXS1 reporting the loss.
#[test]
fn every_venue_runs_both_legs_through_arbx_exec_on_mainnet_snapshots() {
    let mut rows = Vec::new();
    for (name, amount_in, max_drop, budget) in VENUES {
        let f = load(name);
        let (mut svm, payer) = world(&[&f]);
        let me = payer.pubkey();
        let quote = user_accounts(&mut svm, &me, &[&f]);
        let x = other_mint(&f);
        let legs = vec![engine_leg(&f, WSOL, x, me, amount_in), engine_leg(&f, x, WSOL, me, 0)];
        let o = send(&mut svm, &payer, &[v3_ix(ARBX, me, quote, amount_in, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(max_drop), ..GUARDED })], &[], None);
        assert_eq!(o.code(), Some(ERR_PROFIT), "{name}: {}", o.dump());
        let l = o.leg_logs();
        assert_eq!(l.len(), 2, "{name}: both legs delivered\n{}", o.dump());
        let v = venue_index(&f.program);
        assert_eq!((l[0].leg, l[0].venue, l[0].input), (0, v, amount_in), "{name}");
        assert_eq!((l[1].leg, l[1].venue, l[1].input), (1, v, l[0].delivered), "{name}: leg 1 spends exactly what leg 0 delivered");
        let s = o.summary();
        assert_eq!(s.result, ERR_PROFIT);
        assert_eq!(s.quote_delta, l[1].delivered as i128 - amount_in as i128, "{name}");
        assert_eq!(s.gain, s.quote_delta + s.lamport_delta);
        let loss_bps = -s.quote_delta * 10_000 / amount_in as i128;
        assert!(loss_bps > 0 && loss_bps < 500, "{name}: a same-pool round trip loses the fees, here {loss_bps} bps");
        let cus = venue_cus(&o, &f.program);
        assert_eq!(cus.len(), 2, "{name}");
        let overhead = o.cu.unwrap() - cus.iter().sum::<u64>();
        rows.push(format!("{name:<20} slot {} out0 {:>14} back {:>12} loss {:>4} bps lamport_delta {:>9} venue CU {:?} route CU {:?} arbx-exec {overhead} (budget {budget})",
            f.slot, l[0].delivered, l[1].delivered, loss_bps, s.lamport_delta, cus, o.cu));
        assert!(overhead <= budget, "{name}: arbx-exec adds {overhead} CU, budget {budget}");
    }
    eprintln!("\n== real venues, same-pool round trip via arbx-exec (expect ERR_PROFIT after both legs) ==\n{}", rows.join("\n"));
}

/// LEG_AUTH_RO probe (REVIEW #14): which real venues accept the wallet as a READ-ONLY signer. The engine may set the
/// flag only on these. Measured on the snapshots and pinned here.
#[test]
fn which_venues_accept_a_read_only_authority() {
    let mut rows = Vec::new();
    for (name, amount_in, max_drop, _) in VENUES {
        let f = load(name);
        let (mut svm, payer) = world(&[&f]);
        let me = payer.pubkey();
        let quote = user_accounts(&mut svm, &me, &[&f]);
        let x = other_mint(&f);
        let legs: Vec<Leg> = [engine_leg(&f, WSOL, x, me, amount_in), engine_leg(&f, x, WSOL, me, 0)].into_iter().map(|mut l| { l.flags = LEG_AUTH_RO; l }).collect();
        let o = send(&mut svm, &payer, &[v3_ix(ARBX, me, quote, amount_in, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(max_drop), ..GUARDED })], &[], None);
        let accepts = o.code() == Some(ERR_PROFIT) && o.leg_logs().len() == 2;
        rows.push(format!("{name:<20} AUTH_RO: {}", if accepts { "accepted (both legs ran)".to_string() } else { format!("refused: {:?}", o.err) }));
        let expected = f.venue != "pumpswap"; // PumpSwap marks the user `mut` (it pays the accounts it creates)
        assert_eq!(accepts, expected, "{name}: {}", o.dump());
    }
    eprintln!("\n== LEG_AUTH_RO on real venues ==\n{}", rows.join("\n"));
}

/// The happy path on real programs: wSOL -> USDC on DLMM, USDC -> wSOL on Raydium AMM v4 whose SOL vault was raised by
/// 2% in the snapshot (a price gap). The route passes the guard, pays the CPI tip, and the wallet's real balances
/// match AXS1. Then the same route with min_profit above the gain reverts with nothing moved.
#[test]
fn cross_venue_route_with_a_gap_passes_and_pays_the_cpi_tip() {
    let (fd, fa) = (load("dlmm_sol_usdc"), load("ammv4_sol_usdc"));
    let usdc = other_mint(&fd);
    assert_eq!(usdc, other_mint(&fa));
    let run = |min_profit: u64| -> (Outcome, i128, i128, u64) {
        let (mut svm, payer) = world(&[&fd, &fa]);
        let me = payer.pubkey();
        let quote = user_accounts(&mut svm, &me, &[&fd, &fa]);
        // the gap: AMM v4's coin (SOL) vault holds 2% more
        let v = fa.role("vault0");
        let mut acc = svm.get_account(&v).unwrap();
        let amt = u64::from_le_bytes(acc.data[64..72].try_into().unwrap());
        let extra = amt / 50;
        acc.data[64..72].copy_from_slice(&(amt + extra).to_le_bytes());
        acc.lamports += extra;
        svm.set_account(v, acc).unwrap();
        let amount_in = SOL;
        let legs = vec![engine_leg(&fd, WSOL, usdc, me, amount_in), engine_leg(&fa, usdc, WSOL, me, 0)];
        let tip = TipParams { bps: 3_000, floor: 10_000, cap: SOL, account_ix: 6 };
        svm.airdrop(&jito(6), SOL).unwrap();
        let (q0, l0, j0) = (amount(&svm, &quote), lamports(&svm, &me), lamports(&svm, &jito(6)));
        let o = send(&mut svm, &payer, &[v3_ix(ARBX, me, quote, amount_in, min_profit, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(tip), tip_acct: None })], &[], None);
        let (dq, dl) = (amount(&svm, &quote) as i128 - q0 as i128, lamports(&svm, &me) as i128 - l0 as i128);
        (o, dq, dl, lamports(&svm, &jito(6)) - j0)
    };
    let (o, dq, dl, paid) = run(10_000);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summary();
    assert_eq!(s.result, 0);
    assert!(s.gain > 0 && s.tip > 0);
    assert_eq!(s.quote_delta, dq);
    assert_eq!(paid, s.tip, "the Jito account got exactly the logged tip");
    assert_eq!(dl, -(s.tip as i128) - SIG_FEE as i128, "the wallet paid the tip and the fee, nothing else");
    assert_eq!(s.tip as i128, (s.gain * 3_000 / 10_000).max(10_000));
    assert_eq!(o.leg_logs().iter().map(|l| l.venue).collect::<Vec<_>>(), vec![0, 7], "DLMM then AMM v4");
    eprintln!("cross-venue DLMM -> AMM v4 (+2% gap): gain {} tip {} wallet net {} route CU {:?} (DLMM {:?}, AMM v4 {:?})",
        s.gain, s.tip, dq + dl, o.cu, venue_cus(&o, &fd.program), venue_cus(&o, &fa.program));
    // min_profit just above what the route can clear after the tip: ERR_PROFIT, nothing moves but the fee
    let (o, dq, dl, paid) = run((s.gain - s.tip as i128) as u64 + 1);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    assert_eq!((dq, dl, paid), (0, -(SIG_FEE as i128), 0));
}

/// Transaction size (REVIEW #3, plan "regression tests for transaction size"): the widest real route the engine builds
/// today, a PumpSwap buy and a PumpSwap sell on a canonical pump-token pool (creator vault, pool-v2, buyback, volume
/// accumulators), as a v0 transaction with CU limit, CU price, loaded-data limit, PAYER_GUARD | COUNT_LAMPORTS |
/// CPI_TIP, and the route's accounts in two lookup tables. It executes (ERR_PROFIT: a same-pool round trip) and its
/// serialized size must stay within 1,232 bytes.
#[test]
fn widest_real_route_fits_1232_bytes_with_lookup_tables() {
    let f = load("pumpswap_pump_token");
    let (mut svm, payer) = world(&[&f]);
    let me = payer.pubkey();
    let quote = user_accounts(&mut svm, &me, &[&f]);
    let x = other_mint(&f);
    let legs = vec![engine_leg(&f, WSOL, x, me, SOL / 100), engine_leg(&f, x, WSOL, me, 0)];
    let tip = TipParams { bps: 5_000, floor: 1_000, cap: SOL, account_ix: 2 };
    let route = v3_ix(ARBX, me, quote, SOL / 100, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(5_000_000), tip: Some(tip), tip_acct: None });
    let metas = route.accounts.len();
    let ixs: Vec<Instruction> = vec![cu_limit(400_000), cu_price(1), loaded_data_limit(4 * 1024 * 1024), route];
    let mut keys: Vec<Address> = Vec::new();
    for m in ixs.iter().flat_map(|i| i.accounts.iter()) { if m.pubkey != me && !keys.contains(&m.pubkey) { keys.push(m.pubkey); } }
    let (t1, t2) = (fresh(), fresh());
    let half = keys.len() / 2;
    set_alt(&mut svm, t1, &keys[..half]);
    set_alt(&mut svm, t2, &keys[half..]);
    let tables = [AddressLookupTableAccount { key: t1, addresses: keys[..half].to_vec() }, AddressLookupTableAccount { key: t2, addresses: keys[half..].to_vec() }];
    let o = send_v0(&mut svm, &payer, &ixs, &tables, &ARBX);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    assert_eq!(o.leg_logs().len(), 2);
    eprintln!("widest real route (PumpSwap buy + sell, CPI tip): {metas} metas, {} unique keys, {} bytes (limit 1,232), route CU {:?}",
        keys.len() + 1, o.tx_bytes, o.cu);
    assert!(o.tx_bytes <= 1_232);
    assert!(o.tx_bytes <= 600, "the widest real route grew to {} bytes", o.tx_bytes);
}
