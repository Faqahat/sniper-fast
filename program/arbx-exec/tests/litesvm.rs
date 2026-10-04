//! SVM tests of the BUILT program (target/deploy/arbx_exec.so, `cargo-build-sbf --features onchain`) under LiteSVM's
//! MAINNET feature set, against tests/mock-amm loaded at allowlisted venue addresses (and at one unlisted address),
//! side by side with the deployed nexus-arb-v2 ELF (md5 809315be) for the v2 layout.
//!
//! Promoted from the review harness (REVIEW.md #3, `review/tests/adversarial.rs`). Every `finding_*` proof there is a
//! `review_NN_*` regression here that asserts the FIX. Real-venue snapshot tests are in tests/venues.rs.
//!
//! Run: cargo-build-sbf --features onchain && cargo test --release -- --nocapture
mod common;

use arbx_exec::logic::*;
use common::*;
use litesvm::LiteSVM;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::AccountMeta;
use solana_instruction_error::InstructionError;
use solana_keypair::Keypair;
use solana_message::AddressLookupTableAccount;
use solana_signer::Signer;
use solana_transaction_error::TransactionError;

const DLMM: usize = 0;
const PANCAKE: usize = 4;
const CPMM: usize = 6;
const PUMPFUN: usize = 9;
const UNLISTED: Address = Address::new_from_array([0x55; 32]);

#[derive(Clone)]
struct Pool { program: Address, pda: Address, bump: u8, v_sol: Address, v_x: Address, native_pool: Address }

struct Env {
    svm: LiteSVM,
    payer: Keypair,
    x_mint: Address,
    quote: Address,
    w2: Address,
    user_x: Address,
    spare_x: Address,
    a: Pool,    // X cheap   (mock at DLMM)
    b: Pool,    // X dear    (mock at CPMM)
    evil: Pool, // X cheap   (mock at the PancakeSwap Raydium-CLMM fork: a third-party upgradeable venue)
    pump_cheap: Pool,
    pump_dear: Pool,
    attacker: Address,
}

fn make_pool(svm: &mut LiteSVM, program: Address, x_mint: Address, sol: u64, x: u64) -> Pool {
    let (pda, bump) = Address::find_program_address(&[b"auth"], &program);
    let (v_sol, v_x) = (fresh(), fresh());
    set_token(svm, v_sol, WSOL, pda, sol, true);
    set_token(svm, v_x, x_mint, pda, x, false);
    // a native-SOL pool account for the BUY_NATIVE / SELL_NATIVE ops: data = virtual SOL reserve
    let native_pool = fresh();
    let rent8 = svm.minimum_balance_for_rent_exemption(8);
    svm.set_account(native_pool, Account { lamports: rent8 + sol, data: sol.to_le_bytes().to_vec(), owner: program, executable: false, rent_epoch: 0 }).unwrap();
    Pool { program, pda, bump, v_sol, v_x, native_pool }
}

impl Env {
    /// LiteSVM's mainnet features, nothing added (REVIEW.md #1, #3).
    fn new() -> Env {
        let mut svm = mainnet_svm();
        let mock = mock_so();
        for p in [venue(DLMM), venue(CPMM), venue(PANCAKE), venue(PUMPFUN), UNLISTED] { svm.add_program(p, &mock).unwrap(); }
        let payer = Keypair::new();
        svm.airdrop(&payer.pubkey(), 100 * SOL).unwrap();
        let x_mint = fresh();
        set_mint(&mut svm, x_mint, 6);
        set_mint(&mut svm, WSOL, 9);
        let (quote, w2, user_x, spare_x) = (fresh(), fresh(), fresh(), fresh());
        let me = payer.pubkey();
        set_token(&mut svm, quote, WSOL, me, 10 * SOL, true);
        set_token(&mut svm, w2, WSOL, me, 0, true);
        set_token(&mut svm, user_x, x_mint, me, 0, false);
        set_token(&mut svm, spare_x, x_mint, me, 5_000_000_000, false);
        let a = make_pool(&mut svm, venue(DLMM), x_mint, 1_000 * SOL, 1_000_000_000_000);
        let b = make_pool(&mut svm, venue(CPMM), x_mint, 1_100 * SOL, 1_000_000_000_000);
        let evil = make_pool(&mut svm, venue(PANCAKE), x_mint, 1_000 * SOL, 1_000_000_000_000);
        let pump_cheap = make_pool(&mut svm, venue(PUMPFUN), x_mint, 1_000 * SOL, 1_000_000_000_000);
        let pump_dear = make_pool(&mut svm, venue(PUMPFUN), x_mint, 1_100 * SOL, 1_000_000_000_000);
        let attacker = fresh();
        svm.airdrop(&attacker, SOL).unwrap();
        for i in 0..8 { svm.airdrop(&jito(i), SOL).unwrap(); }
        Env { svm, payer, x_mint, quote, w2, user_x, spare_x, a, b, evil, pump_cheap, pump_dear, attacker }
    }
    fn me(&self) -> Address { self.payer.pubkey() }

    /// mock SWAP-family leg (ops 0, 3, 5, 6, 7). buy = wSOL -> X.
    fn swap(&self, p: &Pool, src: Address, dst: Address, buy: bool, op: u8, arg: u64, extra: &[AccountMeta]) -> Leg {
        let (vin, vout) = if buy { (p.v_sol, p.v_x) } else { (p.v_x, p.v_sol) };
        let mut data = vec![0u8; 32];
        data[0] = op;
        data[1] = p.bump;
        data[24..32].copy_from_slice(&arg.to_le_bytes());
        let mut metas = vec![
            AccountMeta::new(self.me(), true), AccountMeta::new(src, false), AccountMeta::new(dst, false),
            AccountMeta::new(vin, false), AccountMeta::new(vout, false),
            AccountMeta::new_readonly(p.pda, false), AccountMeta::new_readonly(TOKEN, false),
        ];
        metas.extend_from_slice(extra);
        Leg { out: dst, program: p.program, metas, data, flags: 0, amount_offset: 8 }
    }
    /// mock BUY_NATIVE: lamports -> X (NATIVE_IN)
    fn buy_native(&self, p: &Pool, dst: Address) -> Leg {
        let mut data = vec![0u8; 32];
        data[0] = 1;
        data[1] = p.bump;
        Leg { out: dst, program: p.program, data, flags: LEG_NATIVE_IN, amount_offset: 8, metas: vec![
            AccountMeta::new(self.me(), true), AccountMeta::new(p.native_pool, false), AccountMeta::new(dst, false),
            AccountMeta::new(p.v_x, false), AccountMeta::new_readonly(p.pda, false), AccountMeta::new_readonly(TOKEN, false),
            AccountMeta::new_readonly(SYSTEM, false)] }
    }
    /// mock SELL_NATIVE: X -> lamports (NATIVE_OUT); the output slot is the authority
    fn sell_native(&self, p: &Pool, src: Address) -> Leg {
        let mut data = vec![0u8; 32];
        data[0] = 2;
        data[1] = p.bump;
        Leg { out: self.me(), program: p.program, data, flags: LEG_NATIVE_OUT, amount_offset: 8, metas: vec![
            AccountMeta::new(self.me(), true), AccountMeta::new(p.native_pool, false), AccountMeta::new(src, false),
            AccountMeta::new(p.v_x, false), AccountMeta::new_readonly(TOKEN, false)] }
    }
    /// the profitable 2-leg round trip quote -> X (A, cheap) -> quote (B, dear)
    fn round_trip(&self) -> Vec<Leg> {
        vec![self.swap(&self.a, self.quote, self.user_x, true, 0, 0, &[]), self.swap(&self.b, self.user_x, self.quote, false, 0, 0, &[])]
    }
    /// leg 0 through the hostile venue (op, arg, extra accounts), leg 1 back through B
    fn hostile(&self, op: u8, arg: u64, extra: &[AccountMeta]) -> Vec<Leg> {
        vec![self.swap(&self.evil, self.quote, self.user_x, true, op, arg, extra), self.swap(&self.b, self.user_x, self.quote, false, 0, 0, &[])]
    }
    fn v3(&self, legs: &[Leg], min_profit: u64, o: &V3) -> solana_instruction::Instruction { v3_ix(ARBX, self.me(), self.quote, SOL, min_profit, legs, o) }
    fn v2(&self, program: Address, legs: &[Leg], guard: Option<u64>) -> solana_instruction::Instruction { v2_ix(program, self.me(), self.quote, SOL, 1, legs, guard) }
    fn send(&mut self, ixs: &[solana_instruction::Instruction], extra: &[&Keypair], heap: Option<u32>) -> Outcome { send(&mut self.svm, &self.payer, ixs, extra, heap) }
    /// a second authority (not the fee payer) with `lamports_`, a wSOL quote of 10 SOL and an empty X account
    fn second_authority(&mut self, lamports_: u64) -> (Keypair, Address, Address) {
        let auth = Keypair::new();
        let a = auth.pubkey();
        self.svm.airdrop(&a, lamports_).unwrap();
        let (q, x) = (fresh(), fresh());
        set_token(&mut self.svm, q, WSOL, a, 10 * SOL, true);
        set_token(&mut self.svm, x, self.x_mint, a, 0, false);
        (auth, q, x)
    }
}

fn as_authority(mut l: Leg, a: Address, writable: bool) -> Leg {
    l.metas[0] = if writable { AccountMeta::new(a, true) } else { AccountMeta::new_readonly(a, true) };
    l
}
fn with_flags(mut l: Leg, flags: u8) -> Leg { l.flags |= flags; l }
fn pad(n: usize) -> Vec<AccountMeta> { (0..n).map(|_| AccountMeta::new_readonly(TOKEN, false)).collect() }
fn hex(c: Option<u32>) -> String { c.map_or("-".into(), |c| format!("{c:#x}")) }
/// the route failed before any venue program ran
fn no_venue_ran(o: &Outcome) -> bool { [DLMM, PANCAKE, CPMM, PUMPFUN].iter().all(|v| o.invoked(&venue(*v)) == 0) }

// =====================================================================================================================
// REVIEW #1 (blocker): no syscall that mainnet lacks; every route completes under mainnet features
// =====================================================================================================================

/// The CI check REVIEW.md #1 asks for: every static syscall the built ELF calls must be registered by the runtime
/// under LiteSVM's mainnet feature set AND under "every known feature active" (so a scheduled feature that removes a
/// syscall, like disable_fees_sysvar, is caught too). The registry is agave's own (solana-syscalls 4.3), built for
/// deployment (reject_broken_elfs = true).
#[test]
fn review_01_elf_uses_only_syscalls_mainnet_registers() {
    use solana_program_runtime::execution_budget::SVMTransactionExecutionBudget;
    let budget = SVMTransactionExecutionBudget::new_with_defaults(false);
    let env = |fs: &agave_feature_set::FeatureSet| solana_syscalls::create_program_runtime_environment(&fs.runtime_features(), &budget, true, false).unwrap();
    let mainnet = env(&LiteSVM::mainnet_feature_set());
    let every = env(&agave_feature_set::FeatureSet::all_enabled());
    let rcu = solana_sbpf::ebpf::hash_symbol_name(b"sol_remaining_compute_units");
    // the audit would have caught the blocker: the syscall is absent from the mainnet registry
    assert!(mainnet.get_function_registry().lookup_by_key(rcu).is_none(), "sol_remaining_compute_units is registered on mainnet now");
    assert!(!svm_feature_active(&REMAINING_CU_FEATURE));
    for (label, elf) in [("arbx_exec.so", arbx_so()), ("nexus_arb_v2.so (deployed)", nexus_so()), ("mock_amm.so", mock_so())] {
        let calls = elf_static_syscalls(&elf);
        assert!(calls.len() >= 4, "{label}: the scanner found too few syscalls: {calls:?}");
        let mut names = Vec::new();
        for h in &calls {
            let name = mainnet.get_function_registry().lookup_by_key(*h).map(|(n, _)| String::from_utf8_lossy(n).into_owned());
            assert!(name.is_some(), "{label}: static syscall {h:#010x} is NOT registered under mainnet features");
            assert!(every.get_function_registry().lookup_by_key(*h).is_some(), "{label}: {name:?} disappears once every known feature is active");
            names.push(name.unwrap());
        }
        assert!(!calls.contains(&rcu), "{label} calls sol_remaining_compute_units");
        eprintln!("{label}: {} syscalls, all registered on mainnet: {}", calls.len(), names.join(", "));
    }
}

/// Every layout and flag combination completes under mainnet features (the old binary aborted all of them at the
/// guard with "unsupported BPF instruction"), and AXS1 is logged with cu_remaining = 0 (reserved).
#[test]
fn review_01_every_route_completes_under_mainnet_features() {
    let cases: Vec<(&str, Box<dyn Fn(&Env) -> solana_instruction::Instruction>)> = vec![
        ("v2", Box::new(|e: &Env| e.v2(ARBX, &e.round_trip(), None))),
        ("v2 + guard trailer", Box::new(|e: &Env| e.v2(ARBX, &e.round_trip(), Some(0)))),
        ("v3 PG", Box::new(|e: &Env| e.v3(&e.round_trip(), 1, &GUARDED))),
        ("v3 PG|CL", Box::new(|e: &Env| e.v3(&e.round_trip(), 1, &V3 { flags: COUNT_LAMPORTS, ..GUARDED }))),
        ("v3 PG|CL|TIP", Box::new(|e: &Env| e.v3(&e.round_trip(), 1, &V3 { flags: COUNT_LAMPORTS, tip: Some(TipParams { bps: 1_000, floor: 1_000, cap: SOL, account_ix: 3 }), ..GUARDED }))),
    ];
    for (name, ix) in cases {
        let mut e = Env::new();
        let ix = ix(&e);
        let q0 = amount(&e.svm, &e.quote);
        let o = e.send(&[ix], &[], None);
        assert!(o.ok(), "{name}: {}", o.dump());
        assert!(!o.logs.iter().any(|l| l.contains("unsupported BPF instruction")));
        let s = o.summary();
        assert_eq!((s.result, s.cu_remaining, s.n_legs), (0, 0, 2), "{name}");
        assert_eq!(s.quote_delta, amount(&e.svm, &e.quote) as i128 - q0 as i128, "{name}");
        assert!(s.gain >= 1, "{name}");
    }
}

// =====================================================================================================================
// CU budgets (REVIEW #3: "add CU budgets as assertions") and v2 parity with the deployed nexus-arb-v2 binary
// =====================================================================================================================

/// The 2-leg mock round trip on the same pools in every row. Budgets are the measured values (2026-10-04, this
/// build) plus ~3%; a change that costs more fails here and must update the budget deliberately.
#[test]
fn cu_budgets_and_v2_parity_with_nexus_v2() {
    let tip = Some(TipParams { bps: 1_000, floor: 1_000, cap: SOL, account_ix: 3 });
    type Case = (&'static str, u64, Box<dyn Fn(&Env) -> solana_instruction::Instruction>);
    let cases: Vec<Case> = vec![
        ("nexus-arb-v2 .so, v2", 20_500, Box::new(|e: &Env| e.v2(NEXUS, &e.round_trip(), None))),
        ("arbx-exec, v2", 20_700, Box::new(|e: &Env| e.v2(ARBX, &e.round_trip(), None))),
        ("nexus-arb-v2 .so, v2+guard", 22_900, Box::new(|e: &Env| e.v2(NEXUS, &e.round_trip(), Some(0)))),
        ("arbx-exec, v2+guard", 23_100, Box::new(|e: &Env| e.v2(ARBX, &e.round_trip(), Some(0)))),
        ("arbx-exec, v3 PG", 22_900, Box::new(|e: &Env| e.v3(&e.round_trip(), 1, &GUARDED))),
        ("arbx-exec, v3 PG|CL", 22_900, Box::new(|e: &Env| e.v3(&e.round_trip(), 1, &V3 { flags: COUNT_LAMPORTS, ..GUARDED }))),
        ("arbx-exec, v3 PG|CL|TIP", 25_400, Box::new(move |e: &Env| e.v3(&e.round_trip(), 1, &V3 { flags: COUNT_LAMPORTS, tip, ..GUARDED }))),
        ("arbx-exec, v3 PG, both legs AUTH_RO", 22_900, Box::new(|e: &Env| {
            let l = e.round_trip().into_iter().map(|l| with_flags(l, LEG_AUTH_RO)).collect::<Vec<_>>();
            e.v3(&l, 1, &GUARDED)
        })),
        ("arbx-exec, v3 native in (lamports->X->wSOL)", 22_400, Box::new(|e: &Env| {
            e.v3(&[e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])], 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..GUARDED })
        })),
        ("arbx-exec, v3 native out (wSOL->X->lamports)", 19_900, Box::new(|e: &Env| {
            e.v3(&[e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.sell_native(&e.pump_dear, e.user_x)], 1, &V3 { flags: COUNT_LAMPORTS, ..GUARDED })
        })),
    ];
    let mut rows = Vec::new();
    let mut deltas = Vec::new();
    for (name, budget, ix) in &cases {
        let mut e = Env::new();
        let ix = ix(&e);
        let q0 = amount(&e.svm, &e.quote);
        let o = e.send(&[ix], &[], None);
        assert!(o.ok(), "{name}: {}", o.dump());
        let cu = o.cu.unwrap();
        let dq = amount(&e.svm, &e.quote) as i128 - q0 as i128;
        rows.push(format!("{name:<46} cu={cu:>6} (budget {budget:>6})  quote_delta={dq}"));
        deltas.push(dq);
        assert!(cu <= *budget, "{name}: {cu} CU exceeds its budget {budget}");
    }
    eprintln!("\n== 2-leg mock round trip, same pools, mainnet features ==\n{}", rows.join("\n"));
    // the v2 bytes move exactly the same tokens on both binaries, with and without the trailer
    assert_eq!(deltas[0], deltas[1]);
    assert_eq!(deltas[2], deltas[3]);
    assert_eq!(deltas[1], deltas[4], "v3 and v2 run the same legs");
}

// =====================================================================================================================
// REVIEW #2 (major): PAYER_GUARD is mandatory in v3, and it stops the hostile venue
// =====================================================================================================================

#[test]
fn review_02_v3_without_payer_guard_is_refused_before_any_venue_runs() {
    for flags in [0u8, COUNT_LAMPORTS] {
        let mut e = Env::new();
        let me = e.me();
        // the very route that bricked the wallet before the fix: the venue assigns the authority to itself
        let legs = e.hostile(6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]);
        let o = e.send(&[e.v3(&legs, 1, &V3 { flags, guard: None, ..GUARDED })], &[], None);
        assert_eq!(o.code(), Some(ERR_BAD_DATA), "{}", o.dump());
        assert!(no_venue_ran(&o));
        assert_eq!(owner_of(&e.svm, &me), SYSTEM);
    }
}

#[test]
fn review_02_hostile_venue_reverts_on_every_v3_flag_combination() {
    let tip = Some(TipParams { bps: 1_000, floor: 0, cap: SOL, account_ix: 0 });
    for (label, o3) in [("PG", GUARDED), ("PG|CL", V3 { flags: COUNT_LAMPORTS, ..GUARDED }), ("PG|CL|TIP", V3 { flags: COUNT_LAMPORTS, tip, ..GUARDED })] {
        // (a) System assign of the authority to the venue program inside leg 0
        let mut e = Env::new();
        let me = e.me();
        let legs = e.hostile(6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]);
        let o = e.send(&[e.v3(&legs, 1, &o3)], &[], None);
        assert_eq!(o.code(), Some(ERR_PAYER_GUARD), "{label} assign: {}", o.dump());
        assert_eq!(owner_of(&e.svm, &me), SYSTEM, "{label}: the wallet still belongs to the System program");
        // (b) lamport theft: 0.5 SOL to the attacker
        let mut e = Env::new();
        let att = e.attacker;
        let a0 = lamports(&e.svm, &att);
        let legs = e.hostile(3, SOL / 2, &[AccountMeta::new(att, false), AccountMeta::new_readonly(SYSTEM, false)]);
        let o = e.send(&[e.v3(&legs, 1, &o3)], &[], None);
        assert_eq!(o.code(), Some(ERR_PAYER_GUARD), "{label} lamports: {}", o.dump());
        assert_eq!(lamports(&e.svm, &att), a0, "{label}: the attacker is not paid");
        // (c) token theft from a second authority-owned token account passed writable
        let mut e = Env::new();
        let att_x = fresh();
        let xm = e.x_mint;
        set_token(&mut e.svm, att_x, xm, att, 0, false);
        let legs = e.hostile(5, 4_000_000_000, &[AccountMeta::new(e.spare_x, false), AccountMeta::new(att_x, false)]);
        let o = e.send(&[e.v3(&legs, 1, &o3)], &[], None);
        assert_eq!(o.code(), Some(ERR_TOKEN_GUARD), "{label} tokens: {}", o.dump());
        assert_eq!(amount(&e.svm, &att_x), 0);
    }
}

/// max_payer_lamport_drop is honoured exactly: a venue may take up to max_drop of the authority's lamports (e.g. an
/// init_if_needed rent it charges), one lamport more reverts.
#[test]
fn review_02_payer_guard_max_drop_is_exact() {
    for (max_drop, ok) in [(10_000u64, true), (9_999, false)] {
        let mut e = Env::new();
        let att = e.attacker;
        let legs = e.hostile(3, 10_000, &[AccountMeta::new(att, false), AccountMeta::new_readonly(SYSTEM, false)]);
        let o = e.send(&[e.v3(&legs, 1, &V3 { guard: Some(max_drop), ..GUARDED })], &[], None);
        assert_eq!(o.ok(), ok, "max_drop {max_drop}: {}", o.dump());
        if !ok { assert_eq!(o.code(), Some(ERR_PAYER_GUARD)); }
    }
}

// =====================================================================================================================
// REVIEW #4 (major): CPI_TIP requires COUNT_LAMPORTS
// =====================================================================================================================

#[test]
fn review_04_cpi_tip_without_count_lamports_is_refused() {
    // the reviewer's losing route: ~0.092 SOL gained in wSOL, 0.1 SOL of lamports taken by leg 1's venue
    let t = TipParams { bps: 5_000, floor: 0, cap: SOL, account_ix: 1 };
    let mut e = Env::new();
    let fee_acct = e.attacker;
    let legs = |e: &Env| vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]),
        e.swap(&e.b, e.user_x, e.quote, false, 3, SOL / 10, &[AccountMeta::new(fee_acct, false), AccountMeta::new_readonly(SYSTEM, false)])];
    let j0 = lamports(&e.svm, &jito(1));
    let l = legs(&e);
    let o = e.send(&[e.v3(&l, 1, &V3 { flags: 0, guard: Some(SOL), tip: Some(t), tip_acct: None })], &[], None);
    assert_eq!(o.code(), Some(ERR_BAD_DATA), "{}", o.dump());
    assert!(no_venue_ran(&o));
    assert_eq!(lamports(&e.svm, &jito(1)), j0);
    // with COUNT_LAMPORTS (the only accepted form) the loss is seen: ERR_PROFIT, AXS1 says by how much, no tip moves
    let mut e = Env::new();
    let l = legs(&e);
    let o = e.send(&[e.v3(&l, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), tip: Some(t), tip_acct: None })], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    let s = o.summary();
    assert_eq!(s.result, ERR_PROFIT);
    assert_eq!(s.gain, s.quote_delta + s.lamport_delta);
    assert!(s.gain < 0 && s.lamport_delta == -((SOL / 10) as i128), "{s:?}");
    assert_eq!(lamports(&e.svm, &jito(1)), j0, "no tip on a losing transaction");
}

// =====================================================================================================================
// CPI tip
// =====================================================================================================================

#[test]
fn cpi_tip_is_paid_exactly_and_only_when_the_guard_passes() {
    let t = TipParams { bps: 3_000, floor: 1_000, cap: 50 * SOL, account_ix: 5 };
    let o3 = V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(t), tip_acct: None };
    let mut e = Env::new();
    let me = e.me();
    let legs = e.round_trip();
    let (q0, l0, j0) = (amount(&e.svm, &e.quote), lamports(&e.svm, &me), lamports(&e.svm, &jito(5)));
    let o = e.send(&[e.v3(&legs, 1, &o3)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summary();
    let (dq, dl, dj) = (amount(&e.svm, &e.quote) as i128 - q0 as i128, lamports(&e.svm, &me) as i128 - l0 as i128, lamports(&e.svm, &jito(5)) as i128 - j0 as i128);
    assert_eq!(s.result, 0);
    assert_eq!(dj, s.tip as i128, "the tip account gets exactly the logged tip");
    assert_eq!(s.tip as i128, s.gain * 3_000 / 10_000);
    assert_eq!(s.quote_delta, dq);
    assert_eq!(dl, -(s.tip as i128) - SIG_FEE as i128, "the authority pays tip + the signature fee");
    // a miss: same route, min_profit above the gain -> ERR_PROFIT, and no tip moves
    let mut e = Env::new();
    let legs = e.round_trip();
    let j0 = lamports(&e.svm, &jito(5));
    let o = e.send(&[e.v3(&legs, s.gain as u64, &o3)], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    assert_eq!(o.summary().result, ERR_PROFIT, "the miss is logged with its code");
    assert_eq!(lamports(&e.svm, &jito(5)), j0, "no tip on a miss");
}

#[test]
fn cpi_tip_account_and_system_slot_are_validated() {
    let t = TipParams { bps: 1_000, floor: 1_000, cap: SOL, account_ix: 2 };
    let cases: Vec<(&str, Option<(Address, Address, bool)>)> = vec![
        ("a non-Jito tip account", Some((SYSTEM, Address::new_from_array([9; 32]), true))),
        ("another Jito account than tip_acct_ix", Some((SYSTEM, jito(3), true))),
        ("the right Jito account, read-only", Some((SYSTEM, jito(2), false))),
        ("System slot holds the token program", Some((TOKEN, jito(2), true))),
    ];
    for (name, acct) in cases {
        let mut e = Env::new();
        let legs = e.round_trip();
        let o = e.send(&[e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(t), tip_acct: acct })], &[], None);
        assert_eq!(o.code(), Some(ERR_TIP_ACCOUNT), "{name}: {}", o.dump());
        assert!(no_venue_ran(&o), "{name}: a venue ran");
    }
}

#[test]
fn cpi_tip_larger_than_the_authoritys_lamports_is_err_tip_funds() {
    // a separate fee payer, and an authority holding just 0.01 SOL; tip floor 0.02 SOL
    let mut e = Env::new();
    let (auth, q, x) = e.second_authority(SOL / 100);
    let a = auth.pubkey();
    let legs = vec![as_authority(e.swap(&e.a, q, x, true, 0, 0, &[]), a, true), as_authority(e.swap(&e.b, x, q, false, 0, 0, &[]), a, true)];
    let t = TipParams { bps: 0, floor: SOL / 50, cap: SOL / 50, account_ix: 0 };
    let o = e.send(&[v3_ix(ARBX, a, q, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(t), tip_acct: None })], &[&auth], None);
    assert_eq!(o.code(), Some(ERR_TIP_FUNDS), "{}", o.dump());
    assert_eq!(o.summary().result, ERR_TIP_FUNDS);
}

// =====================================================================================================================
// REVIEW #5 (minor): the tip must leave the authority rent-exempt
// =====================================================================================================================

#[test]
fn review_05_tip_that_would_break_rent_exemption_is_err_tip_funds() {
    let rent0 = Env::new().svm.minimum_balance_for_rent_exemption(0);
    assert_eq!(rent0, 890_880);
    // (authority lamports, tip, passes): the reviewer's 1,000,000 / 500,000 case, then the exact boundary
    for (bal, tip, ok) in [(1_000_000u64, 500_000u64, false), (1_000_000, 1_000_000 - rent0, true), (1_000_000, 1_000_000 - rent0 + 1, false)] {
        let mut e = Env::new();
        let (auth, q, x) = e.second_authority(bal);
        let a = auth.pubkey();
        let legs = vec![as_authority(e.swap(&e.a, q, x, true, 0, 0, &[]), a, true), as_authority(e.swap(&e.b, x, q, false, 0, 0, &[]), a, true)];
        let t = TipParams { bps: 0, floor: tip, cap: tip, account_ix: 0 };
        let j0 = lamports(&e.svm, &jito(0));
        let o = e.send(&[v3_ix(ARBX, a, q, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(t), tip_acct: None })], &[&auth], None);
        assert_eq!(o.ok(), ok, "balance {bal} tip {tip}: {}", o.dump());
        let s = o.summary();
        if ok {
            assert_eq!((s.result, lamports(&e.svm, &a)), (0, rent0), "exactly rent-exempt afterwards");
            assert_eq!(lamports(&e.svm, &jito(0)) - j0, tip);
        } else {
            // the program refuses, with its own code in both the error and the AXS1 record; before the fix it was a
            // runtime InsufficientFundsForRent after an AXS1 that said "0"
            assert_eq!(o.code(), Some(ERR_TIP_FUNDS), "{}", o.dump());
            assert_eq!(s.result, ERR_TIP_FUNDS);
            assert!(!matches!(o.err, Some(TransactionError::InsufficientFundsForRent { .. })));
            assert_eq!(lamports(&e.svm, &jito(0)), j0);
        }
    }
}

// =====================================================================================================================
// REVIEW #6, #7 (minor): leg flags and account ownership
// =====================================================================================================================

#[test]
fn review_06_one_leg_with_both_native_flags_is_refused_on_chain() {
    let mut e = Env::new();
    let mut weird = e.buy_native(&e.pump_cheap, e.user_x);
    weird.flags = LEG_NATIVE_IN | LEG_NATIVE_OUT;
    weird.out = e.me();
    let legs = vec![weird, e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..GUARDED })], &[], None);
    assert_eq!(o.code(), Some(ERR_BAD_DATA), "{}", o.dump());
    assert!(no_venue_ran(&o));
}

/// The quote account and every token output must be the authority's own (token owner field). Before the fix a native
/// route that delivered into a stranger's wSOL account passed the guard while our wallet only paid.
#[test]
fn review_07_quote_and_token_outputs_must_belong_to_the_authority() {
    // (a) a foreign quote account
    let mut e = Env::new();
    let me = e.me();
    let foreign = fresh();
    set_token(&mut e.svm, foreign, WSOL, e.attacker, 0, true);
    let legs = vec![e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, foreign, false, 0, 0, &[])];
    let l0 = lamports(&e.svm, &me);
    let o = e.send(&[v3_ix(ARBX, me, foreign, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..GUARDED })], &[], None);
    assert_eq!(o.code(), Some(ERR_BAD_ACCOUNTS), "{}", o.dump());
    assert!(no_venue_ran(&o));
    assert_eq!(lamports(&e.svm, &me), l0 - SIG_FEE, "only the fee");
    assert_eq!(amount(&e.svm, &foreign), 0);
    // (b) an intermediate output owned by someone else (leg 0 would deliver X to the attacker)
    let mut e = Env::new();
    let att_x = fresh();
    let (xm, att) = (e.x_mint, e.attacker);
    set_token(&mut e.svm, att_x, xm, att, 0, false);
    let legs = vec![e.swap(&e.a, e.quote, att_x, true, 0, 0, &[]), e.swap(&e.b, att_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert_eq!(o.code(), Some(ERR_BAD_ACCOUNTS), "{}", o.dump());
    assert!(no_venue_ran(&o));
    // (c) v2 is unchanged (nexus-arb-v2 compatibility): the same foreign-quote route still passes on BOTH binaries.
    // This is why the engine's v2 builder derives the quote ATA itself, and why new routes should be v3.
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let me = e.me();
        let foreign = fresh();
        set_token(&mut e.svm, foreign, WSOL, e.attacker, 0, true);
        let legs = vec![e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, foreign, false, 0, 0, &[])];
        let o = e.send(&[v2_ix(prog, me, foreign, SOL, 1, &legs, Some(SOL))], &[], None);
        assert!(o.ok(), "v2 on {prog}: {}", o.dump());
    }
}

// =====================================================================================================================
// REVIEW #14 (hardening): LEG_AUTH_RO
// =====================================================================================================================

#[test]
fn review_14_auth_ro_leg_cannot_debit_or_assign_the_wallet() {
    // an honest swap takes the user only as a signer: works with the authority read-only
    let mut e = Env::new();
    let legs: Vec<Leg> = e.round_trip().into_iter().map(|l| with_flags(l, LEG_AUTH_RO)).collect();
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(o.leg_logs().iter().map(|l| l.flags).collect::<Vec<_>>(), vec![LEG_AUTH_RO, LEG_AUTH_RO], "AXL1 carries the flag");
    // a hostile venue: the runtime refuses the assign and the lamport debit inside the CPI itself
    for (op, arg, extra) in [(6u8, 0u64, vec![AccountMeta::new_readonly(SYSTEM, false)]),
                             (3, SOL / 2, vec![AccountMeta::new(fresh(), false), AccountMeta::new_readonly(SYSTEM, false)])] {
        let mut e = Env::new();
        let me = e.me();
        let mut legs = e.hostile(op, arg, &extra);
        legs[0].flags = LEG_AUTH_RO;
        let l0 = lamports(&e.svm, &me);
        let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
        assert_eq!(o.ix_err(), Some(&InstructionError::PrivilegeEscalation), "op {op}: {}", o.dump());
        assert_eq!((owner_of(&e.svm, &me), lamports(&e.svm, &me)), (SYSTEM, l0 - SIG_FEE));
    }
    // AUTH_RO cannot be put on a native leg
    let mut e = Env::new();
    let legs = vec![with_flags(e.buy_native(&e.pump_cheap, e.user_x), LEG_AUTH_RO), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..GUARDED })], &[], None);
    assert_eq!(o.code(), Some(ERR_BAD_DATA), "{}", o.dump());
}

// =====================================================================================================================
// Other guards, preserved from the review harness
// =====================================================================================================================

#[test]
fn v3_foreign_signer_skim_unlisted_venue_and_empty_leg() {
    // a second signer handed to a venue: refused
    let mut e = Env::new();
    let other = Keypair::new();
    e.svm.airdrop(&other.pubkey(), SOL).unwrap();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[AccountMeta::new(other.pubkey(), true)]), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[&other], None);
    assert_eq!(o.code(), Some(ERR_FOREIGN_SIGNER), "{}", o.dump());
    // a skimming venue: ERR_PROFIT, and the AXS1 record says by how much
    let mut e = Env::new();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.swap(&e.b, e.user_x, e.quote, false, 7, 9_000, &[])];
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    assert!(o.summary().gain < 0);
    // an unlisted program
    let mut e = Env::new();
    let mut legs = e.round_trip();
    legs[1].program = UNLISTED;
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert_eq!(o.code(), Some(ERR_NOT_ALLOWLISTED), "{}", o.dump());
    // a leg that delivers nothing names itself; leg 0's AXL1 was logged first
    let mut e = Env::new();
    let mut legs = e.round_trip();
    legs[1].data[0] = 4;
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert_eq!(o.code(), Some(LEG_ERR_BASE + 1), "{}", o.dump());
    assert_eq!(o.leg_logs().len(), 1);
}

#[test]
fn native_legs_work_and_count_lamports() {
    // lamports -> X on the (mock) pump.fun curve, X -> wSOL quote on B
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let (q0, l0) = (amount(&e.svm, &e.quote), lamports(&e.svm, &me));
    let o = e.send(&[e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..GUARDED })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summary();
    assert_eq!(s.quote_delta, amount(&e.svm, &e.quote) as i128 - q0 as i128);
    assert_eq!(s.lamport_delta, lamports(&e.svm, &me) as i128 - l0 as i128 + SIG_FEE as i128);
    assert_eq!(s.gain, s.quote_delta + s.lamport_delta);
    // wSOL -> X on A, X -> lamports on the dear curve (NATIVE_OUT last leg)
    let mut e = Env::new();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.sell_native(&e.pump_dear, e.user_x)];
    let o = e.send(&[e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, ..GUARDED })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(o.leg_logs()[1].flags, LEG_NATIVE_OUT);
}

// =====================================================================================================================
// Heap, wide legs, the 255-account limit, and transaction size (REVIEW #3, #10, #11)
// =====================================================================================================================

#[test]
fn wide_legs_and_long_routes_fit_the_heap_up_to_the_runtime_account_limit() {
    let mut rows = Vec::new();
    // 2-leg route, leg 0 padded to n accounts (the mock ignores accounts 7..): 2 + (2 + n) + (2 + 7) metas
    for n in [7usize, 63, 64, 128, 200, 242, 243] {
        let mut e = Env::new();
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &pad(n - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
        let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
        let metas = 2 + (2 + n) + (2 + 7);
        rows.push(format!("2 legs, leg0 {n:>3} accts ({metas:>3} metas): {:?} cu={:?}", o.err, o.cu));
        if metas <= MAX_IX_ACCOUNTS {
            assert!(o.ok(), "{metas} metas at the default 32 KiB heap: {}", o.dump());
        } else {
            assert_eq!(o.ix_err(), Some(&InstructionError::MaxAccountsExceeded), "{}", o.dump());
        }
    }
    // 8-leg routes A/B alternating through w2, each leg padded to p accounts: 2 + 8 × (2 + p) metas
    for p in [7usize, 16, 24, 29, 30] {
        let mut e = Env::new();
        let mut legs = Vec::new();
        for i in 0..8 {
            let src = if i == 0 { e.quote } else if i % 2 == 1 { e.user_x } else { e.w2 };
            let dst = if i == 7 { e.quote } else if i % 2 == 0 { e.user_x } else { e.w2 };
            let (pool, buy) = if i % 2 == 0 { (&e.a, true) } else { (&e.b, false) };
            legs.push(e.swap(pool, src, dst, buy, 0, 0, &pad(p - 7)));
        }
        let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
        let metas = 2 + 8 * (2 + p);
        rows.push(format!("8 legs x {p:>2} accts       ({metas:>3} metas): {:?} cu={:?}", o.err, o.cu));
        if metas <= MAX_IX_ACCOUNTS {
            assert!(o.ok(), "{metas} metas: {}", o.dump());
            assert_eq!(o.leg_logs().len(), 8);
        } else {
            assert_eq!(o.ix_err(), Some(&InstructionError::MaxAccountsExceeded), "{}", o.dump());
        }
    }
    eprintln!("\n== wide legs / long routes (v3, PAYER_GUARD, default heap) ==\n{}", rows.join("\n"));
}

/// The widest route the engine builds today, as a v0 transaction with lookup tables: CU limit, CU price, loaded-data
/// limit, then a v3 route with PAYER_GUARD | COUNT_LAMPORTS | CPI_TIP whose legs have the account counts of a
/// PumpSwap buy (26 accounts: build.rs pump_leg with the volume accumulators, fee config/program, pool-v2 and the
/// buyback pair) and a DLMM swap2 over 5 bin arrays (21 accounts). The mock ignores the padding accounts, so the
/// route really executes; the leg data is the mock's 32 bytes (real legs carry 24 and 28).
#[test]
fn transaction_size_widest_engine_route_fits_1232_bytes_with_lookup_tables() {
    let mut e = Env::new();
    let me = e.me();
    let fill = |n: usize| -> Vec<AccountMeta> { (0..n).map(|i| if i % 2 == 0 { AccountMeta::new(fresh(), false) } else { AccountMeta::new_readonly(fresh(), false) }).collect() };
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &fill(26 - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &fill(21 - 7))];
    let tip = TipParams { bps: 5_000, floor: 1_000, cap: SOL, account_ix: 4 };
    let route = e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(tip), tip_acct: None });
    assert_eq!(route.accounts.len(), 2 + (2 + 26) + (2 + 21) + 2);
    let ixs = vec![cu_limit(200_000), cu_price(1), loaded_data_limit(256 * 1024), route];
    // every key except the payer and the top-level programs goes into two tables (the engine's AltIndex picks <= 4)
    let mut keys: Vec<Address> = Vec::new();
    for m in ixs.iter().flat_map(|i| i.accounts.iter()) { if m.pubkey != me && !keys.contains(&m.pubkey) { keys.push(m.pubkey); } }
    let (t1, t2) = (fresh(), fresh());
    let half = keys.len() / 2;
    set_alt(&mut e.svm, t1, &keys[..half]);
    set_alt(&mut e.svm, t2, &keys[half..]);
    let tables = [AddressLookupTableAccount { key: t1, addresses: keys[..half].to_vec() }, AddressLookupTableAccount { key: t2, addresses: keys[half..].to_vec() }];
    let (_, without, _) = v0_message(&e.svm, &me, &ixs, &[]);
    let o = send_v0(&mut e.svm, &e.payer, &ixs, &tables, &ARBX);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(o.summary().result, 0);
    eprintln!("widest engine route: {} unique keys, {} bytes with 2 lookup tables (limit 1,232; {} bytes without tables), cu={:?}",
        keys.len() + 1, o.tx_bytes, without, o.cu);
    assert!(o.tx_bytes <= 1_232, "{} bytes", o.tx_bytes);
    // regression budget on the size: today's measurement plus a little room for header growth
    assert!(o.tx_bytes <= 560, "the widest route grew to {} bytes", o.tx_bytes);
    assert!(without > 1_232, "without lookup tables it cannot fit: the engine must keep using them");
}

// =====================================================================================================================
// v2 compatibility (REVIEW #8, #9): how arbx-exec's v2 path differs from the deployed nexus-arb-v2 binary
// =====================================================================================================================

#[test]
fn review_08_v2_account_structure_differences_from_nexus_are_the_documented_ones() {
    let mut rows = Vec::new();
    // (1) the last leg delivers into w2, not into the quote account: nexus ERR_PROFIT, arbx ERR_BAD_ACCOUNTS
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.swap(&e.b, e.user_x, e.w2, false, 0, 0, &[])];
        let o = e.send(&[e.v2(prog, &legs, None)], &[], None);
        rows.push(format!("v2 last leg not into quote on {:<5}: {}", if prog == NEXUS { "nexus" } else { "arbx" }, hex(o.code())));
        assert_eq!(o.code(), Some(if prog == NEXUS { ERR_PROFIT } else { ERR_BAD_ACCOUNTS }));
    }
    // (2) a NATIVE_OUT leg whose output slot is not the authority: v2 ERR_BAD_DATA (as nexus), v3 ERR_BAD_ACCOUNTS
    for (name, v3) in [("v2", false), ("v3", true)] {
        let mut e = Env::new();
        let mut sell = e.sell_native(&e.pump_dear, e.user_x);
        sell.out = e.w2;
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), sell];
        let ix = if v3 { e.v3(&legs, 1, &V3 { flags: COUNT_LAMPORTS, ..GUARDED }) } else { e.v2(ARBX, &legs, None) };
        let o = e.send(&[ix], &[], None);
        rows.push(format!("{name} NATIVE_OUT slot != authority (arbx): {}", hex(o.code())));
        assert_eq!(o.code(), Some(if v3 { ERR_BAD_ACCOUNTS } else { ERR_BAD_DATA }));
    }
    // (3) COUNT_LAMPORTS with a non-wSOL quote account
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.b, e.spare_x, e.w2, false, 0, 0, &[]), e.swap(&e.a, e.w2, e.spare_x, true, 0, 0, &[])];
    let o = e.send(&[v3_ix(ARBX, me, e.spare_x, 1_000_000, 1, &legs, &V3 { flags: COUNT_LAMPORTS, ..GUARDED })], &[], None);
    rows.push(format!("v3 COUNT_LAMPORTS, X-mint quote: {}", hex(o.code())));
    assert_eq!(o.code(), Some(ERR_QUOTE_NOT_WSOL));
    // (4) a native route with a read-only authority: nexus PrivilegeEscalation, arbx ERR_BAD_ACCOUNTS
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let (auth, q, x) = e.second_authority(SOL);
        let a = auth.pubkey();
        let legs = vec![as_authority(e.buy_native(&e.pump_cheap, x), a, false), as_authority(e.swap(&e.b, x, q, false, 0, 0, &[]), a, false)];
        let mut ix = v2_ix(prog, a, q, SOL, 1, &legs, None);
        ix.accounts[0] = AccountMeta::new_readonly(a, true);
        let o = e.send(&[ix], &[&auth], None);
        rows.push(format!("v2 native leg, read-only authority on {:<5}: {:?}", if prog == NEXUS { "nexus" } else { "arbx" }, o.err));
        if prog == ARBX { assert_eq!(o.code(), Some(ERR_BAD_ACCOUNTS)); } else { assert!(!o.ok()); }
    }
    // (5) the logs: same NXV2LEG / NXV2OUT markers on both, plus one AXS1 record on arbx-exec
    let mut counts = Vec::new();
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let legs = e.round_trip();
        let o = e.send(&[e.v2(prog, &legs, None)], &[], None);
        assert!(o.ok());
        counts.push((o.logs.iter().filter(|l| l.starts_with("Program data: ")).count(), o.summaries().len()));
    }
    assert_eq!(counts, vec![(4, 0), (5, 1)], "2 legs × (NXV2LEG + NXV2OUT), and arbx adds exactly one AXS1");
    eprintln!("\n== account structure ==\n{}", rows.join("\n"));
}

/// REVIEW #9 (engine): a v2 leg with 64+ accounts is re-read on chain as a NATIVE leg by BOTH binaries, so the
/// engine's v2 builder must refuse it (src/build.rs route_ix now does, `> 63`). Both binaries fail it safely.
#[test]
fn review_09_v2_leg_with_64_accounts_is_misread_by_both_binaries() {
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &pad(64 - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
        let o = e.send(&[e.v2(prog, &legs, None)], &[], None);
        assert_eq!(o.code(), Some(ERR_BAD_DATA), "{}", o.dump());
    }
    // the same 64-account leg in v3 is read as 64 accounts and runs
    let mut e = Env::new();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &pad(64 - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[e.v3(&legs, 1, &GUARDED)], &[], None);
    assert!(o.ok(), "{}", o.dump());
}
