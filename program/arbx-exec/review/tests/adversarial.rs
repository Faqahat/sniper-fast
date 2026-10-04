//! SUPERSEDED (2026-10-04, REVIEW.md "Disposition"): this harness proved the findings against the pre-fix build
//! (arbx_exec.so md5 e66c5615). It is kept as the record of those proofs. Run against the fixed build its finding_*
//! tests FAIL, which is the expected confirmation that each weakness is gone, and its other tests fail where they
//! build v3 routes the fixed program refuses (no PAYER_GUARD, CPI_TIP without COUNT_LAMPORTS). The maintained suites
//! are ../tests/litesvm.rs and ../tests/venues.rs.
//!
//! REVIEW-ONLY adversarial LiteSVM harness for arbx-exec (see ../REVIEW.md). It loads the BUILT programs:
//!   ../target/deploy/arbx_exec.so                      (cargo-build-sbf --features onchain)
//!   ../../nexus-arb-v2/target/deploy/nexus_arb_v2.so   (the deployed reference, md5 809315be)
//!   ../tests/mock-amm/target/deploy/mock_amm.so        (loaded at DLMM, CPMM, PancakeSwap-fork, pump.fun and one
//!                                                       unlisted address)
//! Tests named `finding_*` PASS when the weakness described in REVIEW.md is present (they are proofs, not goals).
//! Run: cargo test --release -- --nocapture --test-threads=1

use arbx_exec::logic::*;
use base64::Engine as _;
use litesvm::LiteSVM;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_instruction_error::InstructionError;
use solana_keypair::Keypair;
use solana_message::Message;
use solana_signer::Signer;
use solana_transaction::Transaction;
use solana_transaction_error::TransactionError;

const SOL: u64 = 1_000_000_000;
const DIR: &str = env!("CARGO_MANIFEST_DIR");

const TOKEN: Address = Address::from_str_const("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
const SYSTEM: Address = Address::from_str_const("11111111111111111111111111111111");
const WSOL: Address = Address::from_str_const("So11111111111111111111111111111111111111112");
const CB: Address = Address::from_str_const("ComputeBudget111111111111111111111111111111");
const DLMM: Address = Address::from_str_const(ALLOWLIST_B58[0]);
const PANCAKE: Address = Address::from_str_const(ALLOWLIST_B58[4]);
const CPMM: Address = Address::from_str_const(ALLOWLIST_B58[6]);
const PUMPFUN: Address = Address::from_str_const(ALLOWLIST_B58[9]);
const ARBX: Address = Address::new_from_array([0xA7; 32]);
const NEXUS: Address = Address::new_from_array([0x4E; 32]);
const UNLISTED: Address = Address::new_from_array([0x55; 32]);

fn so(rel: &str) -> Vec<u8> {
    std::fs::read(format!("{DIR}/{rel}")).unwrap_or_else(|e| panic!("{rel}: {e} (build it with cargo-build-sbf first)"))
}
fn jito(i: usize) -> Address { Address::from_str_const(JITO_TIP_ACCOUNTS_B58[i]) }
fn fresh() -> Address { Keypair::new().pubkey() }

fn set_token(svm: &mut LiteSVM, key: Address, mint: Address, owner: Address, amount: u64, native: bool) {
    let rent = svm.minimum_balance_for_rent_exemption(165);
    let mut d = vec![0u8; 165];
    d[..32].copy_from_slice(mint.as_ref());
    d[32..64].copy_from_slice(owner.as_ref());
    d[64..72].copy_from_slice(&amount.to_le_bytes());
    d[108] = 1; // Initialized
    if native {
        d[109] = 1; // is_native = Some(rent)
        d[113..121].copy_from_slice(&rent.to_le_bytes());
    }
    let lamports = rent + if native { amount } else { 0 };
    svm.set_account(key, Account { lamports, data: d, owner: TOKEN, executable: false, rent_epoch: 0 }).unwrap();
}

fn set_mint(svm: &mut LiteSVM, key: Address, decimals: u8) {
    let mut d = vec![0u8; 82];
    d[44] = decimals;
    d[45] = 1;
    let lamports = svm.minimum_balance_for_rent_exemption(82);
    svm.set_account(key, Account { lamports, data: d, owner: TOKEN, executable: false, rent_epoch: 0 }).unwrap();
}

fn amount(svm: &LiteSVM, key: &Address) -> u64 {
    let a = svm.get_account(key).unwrap();
    u64::from_le_bytes(a.data[64..72].try_into().unwrap())
}
fn lamports(svm: &LiteSVM, key: &Address) -> u64 { svm.get_account(key).map_or(0, |a| a.lamports) }

#[derive(Clone)]
struct Pool { program: Address, pda: Address, bump: u8, v_sol: Address, v_x: Address, native_pool: Address }

#[derive(Clone)]
struct Leg { out: Address, program: Address, metas: Vec<AccountMeta>, data: Vec<u8>, flags: u8 }

struct Env {
    svm: LiteSVM,
    payer: Keypair,
    quote: Address,
    w2: Address,
    user_x: Address,
    spare_x: Address,
    a: Pool,        // X cheap   (mock at DLMM)
    b: Pool,        // X dear    (mock at CPMM)
    evil: Pool,     // X cheap   (mock at the PancakeSwap Raydium-CLMM fork: a third-party upgradeable venue)
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

/// The feature gate of the `sol_remaining_compute_units` syscall. NOT active on mainnet (getAccountInfo returns null
/// on 2026-10-04, slot 453,208,111), and not in LiteSVM 0.17's mainnet feature list.
const REMAINING_CU_FEATURE: Address = Address::from_str_const("5TuppMutoyzhUSfuYdhgzD47F92GL1g89KpCZQKqedxP");

impl Env {
    /// LiteSVM's mainnet feature set PLUS the remaining-CU syscall, so that the rest of the program's logic can be
    /// exercised at all (see finding_00: without it every route dies at the guard).
    fn new() -> Env { Env::build(true) }
    /// LiteSVM's mainnet feature set, exactly (what the program would meet on mainnet today).
    fn mainnet() -> Env { Env::build(false) }
    fn build(remaining_cu_syscall: bool) -> Env {
        let mut svm = LiteSVM::new();
        if remaining_cu_syscall {
            let mut fs = LiteSVM::mainnet_feature_set();
            fs.activate(&REMAINING_CU_FEATURE, 0);
            svm = svm.with_feature_set(fs).with_builtins();
        }
        svm.add_program(ARBX, &so("../target/deploy/arbx_exec.so")).unwrap();
        svm.add_program(NEXUS, &so("../../nexus-arb-v2/target/deploy/nexus_arb_v2.so")).unwrap();
        let mock = so("../tests/mock-amm/target/deploy/mock_amm.so");
        for p in [DLMM, CPMM, PANCAKE, PUMPFUN, UNLISTED] { svm.add_program(p, &mock).unwrap(); }
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
        let a = make_pool(&mut svm, DLMM, x_mint, 1_000 * SOL, 1_000_000_000_000);
        let b = make_pool(&mut svm, CPMM, x_mint, 1_100 * SOL, 1_000_000_000_000);
        let evil = make_pool(&mut svm, PANCAKE, x_mint, 1_000 * SOL, 1_000_000_000_000);
        let pump_cheap = make_pool(&mut svm, PUMPFUN, x_mint, 1_000 * SOL, 1_000_000_000_000);
        let pump_dear = make_pool(&mut svm, PUMPFUN, x_mint, 1_100 * SOL, 1_000_000_000_000);
        let attacker = fresh();
        svm.airdrop(&attacker, SOL).unwrap();
        for i in 0..8 { let j = jito(i); svm.airdrop(&j, SOL).unwrap(); }
        Env { svm, payer, quote, w2, user_x, spare_x, a, b, evil, pump_cheap, pump_dear, attacker }
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
        Leg { out: dst, program: p.program, metas, data, flags: 0 }
    }
    /// mock BUY_NATIVE: lamports -> X (NATIVE_IN)
    fn buy_native(&self, p: &Pool, dst: Address) -> Leg {
        let mut data = vec![0u8; 32];
        data[0] = 1;
        data[1] = p.bump;
        Leg { out: dst, program: p.program, data, flags: LEG_NATIVE_IN, metas: vec![
            AccountMeta::new(self.me(), true), AccountMeta::new(p.native_pool, false), AccountMeta::new(dst, false),
            AccountMeta::new(p.v_x, false), AccountMeta::new_readonly(p.pda, false), AccountMeta::new_readonly(TOKEN, false),
            AccountMeta::new_readonly(SYSTEM, false)] }
    }
    /// mock SELL_NATIVE: X -> lamports (NATIVE_OUT); the output slot is the authority
    fn sell_native(&self, p: &Pool, src: Address) -> Leg {
        let mut data = vec![0u8; 32];
        data[0] = 2;
        data[1] = p.bump;
        Leg { out: self.me(), program: p.program, data, flags: LEG_NATIVE_OUT, metas: vec![
            AccountMeta::new(self.me(), true), AccountMeta::new(p.native_pool, false), AccountMeta::new(src, false),
            AccountMeta::new(p.v_x, false), AccountMeta::new_readonly(TOKEN, false)] }
    }
    /// the profitable 2-leg round trip quote -> X (A, cheap) -> quote (B, dear)
    fn round_trip(&self) -> Vec<Leg> {
        vec![self.swap(&self.a, self.quote, self.user_x, true, 0, 0, &[]), self.swap(&self.b, self.user_x, self.quote, false, 0, 0, &[])]
    }

    fn send(&mut self, ixs: &[Instruction], extra_signers: &[&Keypair], heap: Option<u32>) -> Outcome {
        let mut all = vec![cu_limit(1_400_000)];
        if let Some(h) = heap { all.push(heap_frame(h)); }
        all.extend_from_slice(ixs);
        let mut signers: Vec<&Keypair> = vec![&self.payer];
        signers.extend_from_slice(extra_signers);
        let msg = Message::new(&all, Some(&self.payer.pubkey()));
        let tx = Transaction::new(&signers, msg, self.svm.latest_blockhash());
        let r = self.svm.send_transaction(tx);
        self.svm.expire_blockhash();
        let (err, logs) = match r { Ok(m) => (None, m.logs), Err(f) => (Some(f.err), f.meta.logs) };
        let cu = program_cu(&logs, &ixs.last().unwrap().program_id);
        Outcome { err, logs, cu }
    }
}

#[derive(Debug)]
struct Outcome { err: Option<TransactionError>, logs: Vec<String>, cu: Option<u64> }
impl Outcome {
    fn ok(&self) -> bool { self.err.is_none() }
    fn code(&self) -> Option<u32> {
        match &self.err { Some(TransactionError::InstructionError(_, InstructionError::Custom(c))) => Some(*c), _ => None }
    }
    fn summaries(&self) -> Vec<Summary> {
        self.logs.iter().filter_map(|l| l.strip_prefix("Program data: "))
            .filter_map(|b| base64::engine::general_purpose::STANDARD.decode(b.trim()).ok())
            .filter_map(|d| decode_summary(&d)).collect()
    }
    fn dump(&self) -> String { format!("err={:?} cu={:?}\n  {}", self.err, self.cu, self.logs.join("\n  ")) }
}

/// "Program <id> consumed N of M compute units" for the top-level instruction of `program`
fn program_cu(logs: &[String], program: &Address) -> Option<u64> {
    let pfx = format!("Program {} consumed ", program);
    logs.iter().rev().find_map(|l| l.strip_prefix(&pfx).and_then(|r| r.split(' ').next()).and_then(|n| n.parse().ok()))
}

fn cu_limit(units: u32) -> Instruction {
    let mut d = vec![2u8];
    d.extend_from_slice(&units.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}
fn heap_frame(bytes: u32) -> Instruction {
    let mut d = vec![1u8];
    d.extend_from_slice(&bytes.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}

fn route_accounts(authority: Address, quote: Address, legs: &[Leg], tip: Option<(Address, Address, bool)>) -> Vec<AccountMeta> {
    let mut a = vec![AccountMeta::new(authority, true), AccountMeta::new(quote, false)];
    for l in legs {
        a.push(AccountMeta::new(l.out, false));
        a.push(AccountMeta::new_readonly(l.program, false));
        a.extend(l.metas.iter().cloned());
    }
    if let Some((system, t, writable)) = tip {
        a.push(AccountMeta::new_readonly(system, false));
        a.push(if writable { AccountMeta::new(t, false) } else { AccountMeta::new_readonly(t, false) });
    }
    a
}

fn v2_ix(program: Address, authority: Address, quote: Address, amount_in: u64, min_profit: u64, legs: &[Leg], guard: Option<u64>) -> Instruction {
    let specs: Vec<(u8, u8, &[u8])> = legs.iter().map(|l| {
        let f = (if l.flags & LEG_NATIVE_IN != 0 { NATIVE_IN } else { 0 }) | (if l.flags & LEG_NATIVE_OUT != 0 { NATIVE_OUT } else { 0 });
        (l.metas.len() as u8 | f, 8u8, l.data.as_slice())
    }).collect();
    let data = match guard { Some(g) => encode_guarded(amount_in, min_profit, &specs, g), None => encode(amount_in, min_profit, &specs) };
    Instruction { program_id: program, accounts: route_accounts(authority, quote, legs, None), data }
}

struct V3 { flags: u8, guard: Option<u64>, tip: Option<TipParams>, tip_acct: Option<(Address, Address, bool)> }
const BARE: V3 = V3 { flags: 0, guard: None, tip: None, tip_acct: None };

fn v3_ix(authority: Address, quote: Address, amount_in: u64, min_profit: u64, legs: &[Leg], o: &V3) -> Instruction {
    let specs: Vec<LegSpec> = legs.iter().map(|l| LegSpec { n_accounts: l.metas.len() as u8, flags: l.flags, amount_offset: 8, data: &l.data }).collect();
    let data = encode_v3(o.flags, amount_in, min_profit, o.guard, o.tip, &specs);
    let tip = o.tip_acct.or_else(|| o.tip.map(|t| (SYSTEM, jito(t.account_ix as usize), true)));
    Instruction { program_id: ARBX, accounts: route_accounts(authority, quote, legs, tip), data }
}

// =====================================================================================================================
// FINDING 0 (BLOCKER): sol_remaining_compute_units is not available on mainnet
// =====================================================================================================================

#[test]
fn finding_00_blocker_every_route_dies_at_the_guard_with_mainnet_features() {
    for (name, v3) in [("v2", false), ("v3", true)] {
        let mut e = Env::mainnet();
        let me = e.me();
        let legs = e.round_trip();
        let ix = if v3 { v3_ix(me, e.quote, SOL, 1, &legs, &BARE) } else { v2_ix(ARBX, me, e.quote, SOL, 1, &legs, None) };
        let o = e.send(&[ix], &[], None);
        let last = o.logs.last().cloned().unwrap_or_default();
        eprintln!("mainnet features, arbx-exec {name}: {:?} / {last}", o.err);
        assert_eq!(o.err, Some(TransactionError::InstructionError(1, InstructionError::ProgramFailedToComplete)));
        assert!(last.ends_with("failed: unsupported BPF instruction"), "{last}");
        // both legs ran and delivered: the failure is the guard's syscall, not a venue
        assert!(o.summaries().is_empty(), "the AXS1 record is never emitted");
        // the identical v2 bytes on the deployed nexus-arb-v2 binary succeed
        if !v3 {
            let mut e = Env::mainnet();
            let legs = e.round_trip();
            let o = e.send(&[v2_ix(NEXUS, me_of(&e), e.quote, SOL, 1, &legs, None)], &[], None);
            assert!(o.ok(), "{}", o.dump());
        }
    }
}

// =====================================================================================================================
// Baseline: v2 parity with the deployed nexus-arb-v2 binary, and a CU table
// =====================================================================================================================

#[test]
fn baseline_v2_parity_with_nexus_v2_and_cu_table() {
    let mut rows = Vec::new();
    let mut deltas = Vec::new();
    for (name, which) in [("nexus-arb-v2 .so, v2", 0), ("arbx-exec, v2", 1), ("nexus-arb-v2 .so, v2+guard", 2), ("arbx-exec, v2+guard", 3),
        ("arbx-exec, v3 bare", 4), ("arbx-exec, v3 PG", 5), ("arbx-exec, v3 PG|CL", 6), ("arbx-exec, v3 PG|CL|TIP", 7)]
    {
        let mut e = Env::new();
        let legs = e.round_trip();
        let me = e.me();
        let ix = match which {
            0 => v2_ix(NEXUS, me, e.quote, SOL, 1, &legs, None),
            1 => v2_ix(ARBX, me, e.quote, SOL, 1, &legs, None),
            2 => v2_ix(NEXUS, me, e.quote, SOL, 1, &legs, Some(0)),
            3 => v2_ix(ARBX, me, e.quote, SOL, 1, &legs, Some(0)),
            4 => v3_ix(me, e.quote, SOL, 1, &legs, &BARE),
            5 => v3_ix(me, e.quote, SOL, 1, &legs, &V3 { guard: Some(0), ..BARE }),
            6 => v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), ..BARE }),
            _ => v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0),
                tip: Some(TipParams { bps: 1_000, floor: 1_000, cap: SOL, account_ix: 3 }), tip_acct: None }),
        };
        let q0 = amount(&e.svm, &e.quote);
        let o = e.send(&[ix], &[], None);
        assert!(o.ok(), "{name}: {}", o.dump());
        let dq = amount(&e.svm, &e.quote) as i128 - q0 as i128;
        rows.push(format!("{name:<28} cu={:>6}  quote_delta={dq}", o.cu.unwrap()));
        deltas.push((which, dq));
    }
    eprintln!("\n== 2-leg mock round trip, same pools ==\n{}", rows.join("\n"));
    // v2 bytes on both binaries move exactly the same tokens
    assert_eq!(deltas[0].1, deltas[1].1);
    assert_eq!(deltas[2].1, deltas[3].1);
}

// =====================================================================================================================
// CPI tip
// =====================================================================================================================

#[test]
fn cpi_tip_is_paid_exactly_and_only_when_the_guard_passes() {
    let mut e = Env::new();
    let me = e.me();
    let legs = e.round_trip();
    let t = TipParams { bps: 3_000, floor: 1_000, cap: 50 * SOL, account_ix: 5 };
    let o3 = V3 { flags: COUNT_LAMPORTS, guard: Some(0), tip: Some(t), tip_acct: None };
    let (q0, l0, j0) = (amount(&e.svm, &e.quote), lamports(&e.svm, &me), lamports(&e.svm, &jito(5)));
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &o3)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summaries();
    assert_eq!(s.len(), 1);
    let s = s[0];
    let (dq, dl, dj) = (amount(&e.svm, &e.quote) as i128 - q0 as i128, lamports(&e.svm, &me) as i128 - l0 as i128, lamports(&e.svm, &jito(5)) as i128 - j0 as i128);
    eprintln!("tip run: summary {:?}\n  quote_delta {dq} authority_delta {dl} (incl. fee) jito5_delta {dj}", s);
    assert_eq!(s.result, 0);
    assert_eq!(dj, s.tip as i128, "the tip account gets exactly the logged tip");
    assert_eq!(s.tip as i128, s.gain * 3_000 / 10_000);
    assert_eq!(s.quote_delta, dq);
    assert_eq!(dl, -(s.tip as i128) - 5_000, "the authority pays tip + the 5,000-lamport signature fee");

    // a miss: same route, min_profit above the gain -> ERR_PROFIT, and no tip moves
    let mut e = Env::new();
    let legs = e.round_trip();
    let j0 = lamports(&e.svm, &jito(5));
    let o = e.send(&[v3_ix(me_of(&e), e.quote, SOL, s.gain as u64, &legs, &o3)], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    let ss = o.summaries();
    assert_eq!(ss.len(), 1);
    assert_eq!(ss[0].result, ERR_PROFIT, "the miss is logged with its code");
    assert_eq!(lamports(&e.svm, &jito(5)), j0, "no tip on a miss");
}
fn me_of(e: &Env) -> Address { e.me() }

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
        let me = e.me();
        let legs = e.round_trip();
        let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: None, tip: Some(t), tip_acct: acct })], &[], None);
        assert_eq!(o.code(), Some(ERR_TIP_ACCOUNT), "{name}: {}", o.dump());
        // rejected before any venue ran
        assert!(!o.logs.iter().any(|l| l.contains(&DLMM.to_string())), "{name}: a venue ran");
    }
}

#[test]
fn cpi_tip_larger_than_the_authoritys_lamports_is_err_tip_funds() {
    // a separate fee payer, and an authority holding just 0.01 SOL; tip floor 0.02 SOL
    let mut e = Env::new();
    let auth = Keypair::new();
    let a = auth.pubkey();
    e.svm.airdrop(&a, SOL / 100).unwrap();
    let (q, x) = (fresh(), fresh());
    set_token(&mut e.svm, q, WSOL, a, 10 * SOL, true);
    let xm = Address::new_from_array(e.svm.get_account(&e.user_x).unwrap().data[..32].try_into().unwrap());
    set_token(&mut e.svm, x, xm, a, 0, false);
    let mut legs = vec![e.swap(&e.a, q, x, true, 0, 0, &[]), e.swap(&e.b, x, q, false, 0, 0, &[])];
    for l in legs.iter_mut() { l.metas[0] = AccountMeta::new(a, true); }
    let t = TipParams { bps: 0, floor: SOL / 50, cap: SOL / 50, account_ix: 0 };
    let o = e.send(&[v3_ix(a, q, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: None, tip: Some(t), tip_acct: None })], &[&auth], None);
    assert_eq!(o.code(), Some(ERR_TIP_FUNDS), "{}", o.dump());
}

// =====================================================================================================================
// Malicious venue (the mock loaded at the PancakeSwap Raydium-CLMM fork address, allowlisted id 4)
// =====================================================================================================================

/// FINDING 1 (proof). A v3 route WITHOUT PAYER_GUARD hands the authority (signer + writable) to every venue, and
/// nothing stops a hostile upgrade from assigning the wallet to itself or taking lamports: the route still passes
/// the profit guard. The very same route with PAYER_GUARD reverts.
#[test]
fn finding_01_v3_without_payer_guard_lets_a_hostile_venue_take_the_wallet() {
    // (a) System Assign of the authority to the venue program inside leg 0
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let owner = e.svm.get_account(&me).unwrap().owner;
    eprintln!("v3 bare route + assigning venue: success={} authority owner after = {owner}", o.ok());
    assert_eq!(owner, PANCAKE, "the trading wallet now belongs to the venue program");
    // also with COUNT_LAMPORTS (an assign moves no lamports): still passes
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, ..BARE })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(e.svm.get_account(&e.me()).unwrap().owner, PANCAKE);
    // with CPI_TIP the System transfer of the tip happens to fail (the System program no longer owns the
    // authority): ExternalAccountLamportSpend. An accident, not a guard.
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: None,
        tip: Some(TipParams { bps: 1_000, floor: 0, cap: SOL, account_ix: 0 }), tip_acct: None })], &[], None);
    assert_eq!(o.err, Some(TransactionError::InstructionError(1, InstructionError::ExternalAccountLamportSpend)), "{}", o.dump());

    // (b) the same with PAYER_GUARD: reverted
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 6, 0, &[AccountMeta::new_readonly(SYSTEM, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { guard: Some(0), ..BARE })], &[], None);
    assert_eq!(o.code(), Some(ERR_PAYER_GUARD), "{}", o.dump());

    // (c) lamport theft: 0.5 SOL to the attacker. Bare v3 passes; the attacker is paid.
    let mut e = Env::new();
    let me = e.me();
    let att = e.attacker;
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 3, SOL / 2, &[AccountMeta::new(att, false), AccountMeta::new_readonly(SYSTEM, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let a0 = lamports(&e.svm, &att);
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(lamports(&e.svm, &att) - a0, SOL / 2);
    // (d) token theft from a second authority-owned token account passed writable: bare v3 passes
    let mut e = Env::new();
    let me = e.me();
    let (spare, att_x) = (e.spare_x, fresh());
    let xm = Address::new_from_array(e.svm.get_account(&e.user_x).unwrap().data[..32].try_into().unwrap());
    set_token(&mut e.svm, att_x, xm, att, 0, false);
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 5, 4_000_000_000, &[AccountMeta::new(spare, false), AccountMeta::new(att_x, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert!(o.ok(), "{}", o.dump());
    assert_eq!(amount(&e.svm, &att_x), 4_000_000_000);
    // ... and with PAYER_GUARD: ERR_TOKEN_GUARD
    let mut e = Env::new();
    let me = e.me();
    let xm = Address::new_from_array(e.svm.get_account(&e.user_x).unwrap().data[..32].try_into().unwrap());
    set_token(&mut e.svm, att_x, xm, att, 0, false);
    let legs = vec![e.swap(&e.evil, e.quote, e.user_x, true, 5, 4_000_000_000, &[AccountMeta::new(e.spare_x, false), AccountMeta::new(att_x, false)]),
                    e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { guard: Some(0), ..BARE })], &[], None);
    assert_eq!(o.code(), Some(ERR_TOKEN_GUARD), "{}", o.dump());
}

/// FINDING 3 (proof). CPI_TIP without COUNT_LAMPORTS: lamports the authority loses INSIDE the legs are invisible to
/// the guard and to the tip, so the tip is paid on a transaction that lost money. Stand-in for an honest venue that
/// charges the user SOL (init_if_needed rent, a SOL-denominated fee): op 3 sends 0.09 SOL from the user to a fee
/// account during leg 0.
#[test]
fn finding_03_cpi_tip_without_count_lamports_pays_a_tip_on_a_losing_transaction() {
    let mut e = Env::new();
    let me = e.me();
    let fee_acct = e.attacker;
    // the round trip gains ~0.092 SOL in wSOL; leg 1's venue also takes 0.1 SOL of lamports from the user
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]),
                    e.swap(&e.b, e.user_x, e.quote, false, 3, SOL / 10, &[AccountMeta::new(fee_acct, false), AccountMeta::new_readonly(SYSTEM, false)])];
    let t = TipParams { bps: 5_000, floor: 0, cap: SOL, account_ix: 1 };
    let (q0, l0) = (amount(&e.svm, &e.quote), lamports(&e.svm, &me));
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: 0, guard: None, tip: Some(t), tip_acct: None })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summaries()[0];
    let wallet = (amount(&e.svm, &e.quote) as i128 - q0 as i128) + (lamports(&e.svm, &me) as i128 - l0 as i128) + 5_000;
    eprintln!("CPI_TIP without COUNT_LAMPORTS: gain(g)={} tip={} lamport_delta(ignored)={} wallet net (ex fee)={wallet}", s.gain, s.tip, s.lamport_delta);
    assert!(s.tip > 0 && wallet < 0, "a tip was paid although the wallet lost money");
    // the same route with COUNT_LAMPORTS reverts
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]),
                    e.swap(&e.b, e.user_x, e.quote, false, 3, SOL / 10, &[AccountMeta::new(fee_acct, false), AccountMeta::new_readonly(SYSTEM, false)])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: None, tip: Some(t), tip_acct: None })], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
}

#[test]
fn v3_foreign_signer_skim_and_unlisted_venue() {
    // a second signer handed to a venue: refused in v3 even without PAYER_GUARD
    let mut e = Env::new();
    let me = e.me();
    let other = Keypair::new();
    e.svm.airdrop(&other.pubkey(), SOL).unwrap();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[AccountMeta::new(other.pubkey(), true)]), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &BARE)], &[&other], None);
    assert_eq!(o.code(), Some(ERR_FOREIGN_SIGNER), "{}", o.dump());
    // a skimming venue: ERR_PROFIT, and the AXS1 record says by how much
    let mut e = Env::new();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.swap(&e.b, e.user_x, e.quote, false, 7, 9_000, &[])];
    let o = e.send(&[v3_ix(me_of(&e), e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert_eq!(o.code(), Some(ERR_PROFIT), "{}", o.dump());
    assert!(o.summaries()[0].gain < 0);
    // an unlisted program
    let mut e = Env::new();
    let mut legs = e.round_trip();
    legs[1].program = UNLISTED;
    let o = e.send(&[v3_ix(me_of(&e), e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert_eq!(o.code(), Some(ERR_NOT_ALLOWLISTED), "{}", o.dump());
    // a leg that delivers nothing names itself
    let mut e = Env::new();
    let mut legs = e.round_trip();
    legs[1].data[0] = 4;
    let o = e.send(&[v3_ix(me_of(&e), e.quote, SOL, 1, &legs, &BARE)], &[], None);
    assert_eq!(o.code(), Some(LEG_ERR_BASE + 1), "{}", o.dump());
}

// =====================================================================================================================
// Native legs
// =====================================================================================================================

#[test]
fn native_legs_work_and_count_lamports() {
    // lamports -> X on the (mock) pump.fun curve, X -> wSOL quote on B
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    let (q0, l0) = (amount(&e.svm, &e.quote), lamports(&e.svm, &me));
    let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..BARE })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    let s = o.summaries()[0];
    assert_eq!(s.quote_delta, amount(&e.svm, &e.quote) as i128 - q0 as i128);
    assert_eq!(s.lamport_delta, lamports(&e.svm, &me) as i128 - l0 as i128 + 5_000);
    assert_eq!(s.gain, s.quote_delta + s.lamport_delta);
    eprintln!("NATIVE_IN route cu={:?} {:?}", o.cu, s);
    // wSOL -> X on A, X -> lamports on the dear curve (NATIVE_OUT last leg)
    let mut e = Env::new();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.sell_native(&e.pump_dear, e.user_x)];
    let o = e.send(&[v3_ix(me_of(&e), e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(0), ..BARE })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    eprintln!("NATIVE_OUT route cu={:?} {:?}", o.cu, o.summaries()[0]);
}

/// FINDING 6 (proof). v3 accepts NATIVE_IN|NATIVE_OUT on ONE leg; its "delivered" is then the NET lamport change of
/// the authority (output minus the input it spent), so the chain hands the next leg only the leg's profit.
#[test]
fn finding_06_one_leg_with_both_native_flags_is_accepted() {
    let d = [0u8; 32];
    let r = parse(&encode_v3(COUNT_LAMPORTS, 1, 1, None, None, &[
        LegSpec { n_accounts: 7, flags: LEG_NATIVE_IN | LEG_NATIVE_OUT, amount_offset: 8, data: &d },
        LegSpec { n_accounts: 7, flags: LEG_NATIVE_IN, amount_offset: 8, data: &d },
        LegSpec { n_accounts: 7, flags: 0, amount_offset: 8, data: &d }])).unwrap();
    assert!(r.legs()[0].native_in && r.legs()[0].native_out);
    // and in v2
    let r = parse(&encode(1, 1, &[(NATIVE_IN | NATIVE_OUT | 7, 8, &d), (NATIVE_IN | 7, 8, &d), (7, 8, &d)])).unwrap();
    assert!(r.legs()[0].native_in && r.legs()[0].native_out);
}

/// FINDING 7 (proof). The quote account is not tied to the authority. A native-in route whose last leg delivers into
/// someone else's wSOL account passes the guard (quote +X, lamports -Y, g = X - Y > 0) while our wallet only lost Y.
#[test]
fn finding_07_quote_account_need_not_belong_to_the_authority() {
    let mut e = Env::new();
    let me = e.me();
    let foreign = fresh();
    set_token(&mut e.svm, foreign, WSOL, e.attacker, 0, true);
    let legs = vec![e.buy_native(&e.pump_cheap, e.user_x), e.swap(&e.b, e.user_x, foreign, false, 0, 0, &[])];
    let l0 = lamports(&e.svm, &me);
    let o = e.send(&[v3_ix(me, foreign, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: Some(SOL), ..BARE })], &[], None);
    assert!(o.ok(), "{}", o.dump());
    eprintln!("foreign quote: our lamports {} -> {}, foreign wSOL got {}", l0, lamports(&e.svm, &me), amount(&e.svm, &foreign));
    assert!(lamports(&e.svm, &me) < l0 - SOL + 1);
}

// =====================================================================================================================
// Heap / wide legs / long routes
// =====================================================================================================================

fn pad(n: usize) -> Vec<AccountMeta> { (0..n).map(|_| AccountMeta::new_readonly(TOKEN, false)).collect() }

#[test]
fn wide_legs_and_long_routes_heap_and_cpi_limits() {
    let mut rows = Vec::new();
    // 2-leg route, leg 0 padded to n accounts (the mock ignores accounts 7..)
    for n in [7usize, 32, 63, 64, 100, 127, 128, 129, 160, 200, 230] {
        for heap in [None, Some(256 * 1024)] {
            let mut e = Env::new();
            let me = e.me();
            let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &pad(n - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
            let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { guard: Some(0), ..BARE })], &[], heap);
            let total = 2 + (2 + n) + (2 + 7);
            rows.push(format!("2 legs, leg0 {n:>3} accts (ix metas {total:>3}) heap {:>6}: {}", heap.unwrap_or(32 * 1024),
                if o.ok() { format!("ok cu={}", o.cu.unwrap()) } else { format!("FAIL {:?} {}", o.err, o.logs.iter().rev().take(3).cloned().collect::<Vec<_>>().join(" | ")) }));
        }
    }
    // 8-leg routes A/B alternating through w2, each leg padded to p accounts
    for p in [7usize, 16, 24, 28, 31] {
        for heap in [None, Some(256 * 1024)] {
            let mut e = Env::new();
            let me = e.me();
            let mut legs = Vec::new();
            for i in 0..8 {
                let src = if i == 0 { e.quote } else if i % 2 == 1 { e.user_x } else { e.w2 };
                let dst = if i == 7 { e.quote } else if i % 2 == 0 { e.user_x } else { e.w2 };
                let (pool, buy) = if i % 2 == 0 { (&e.a, true) } else { (&e.b, false) };
                legs.push(e.swap(pool, src, dst, buy, 0, 0, &pad(p - 7)));
            }
            let o = e.send(&[v3_ix(me, e.quote, SOL, 1, &legs, &V3 { guard: Some(0), ..BARE })], &[], heap);
            let total = 2 + 8 * (2 + p);
            rows.push(format!("8 legs x {p:>2} accts       (ix metas {total:>3}) heap {:>6}: {}", heap.unwrap_or(32 * 1024),
                if o.ok() { format!("ok cu={}", o.cu.unwrap()) } else { format!("FAIL {:?} {}", o.err, o.logs.iter().rev().take(3).cloned().collect::<Vec<_>>().join(" | ")) }));
        }
    }
    eprintln!("\n== wide legs / long routes (v3 + PAYER_GUARD) ==\n{}", rows.join("\n"));
}

/// v2 compatibility: the engine's v2 builder (src/build.rs route_ix) accepts legs of up to 255 accounts, but a v2 leg
/// with 64+ accounts is silently re-read as a NATIVE leg with (n & 0x3F) accounts by BOTH binaries.
#[test]
fn finding_v2_leg_with_64_accounts_is_misread_on_chain() {
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &pad(64 - 7)), e.swap(&e.b, e.user_x, e.quote, false, 0, 0, &[])];
    for prog in [NEXUS, ARBX] {
        let o = e.send(&[v2_ix(prog, me, e.quote, SOL, 1, &legs, None)], &[], None);
        eprintln!("v2 64-account leg on {}: {:?} code {:?}", if prog == NEXUS { "nexus-arb-v2" } else { "arbx-exec" }, o.err, o.code().map(|c| format!("{c:#x}")));
        assert!(!o.ok());
    }
}

// =====================================================================================================================
// Account-structure checks, and how arbx-exec's v2 path differs from the deployed nexus-arb-v2 binary
// =====================================================================================================================

/// A second authority (not the fee payer) holding X and a wSOL quote; returns (authority, quote, user_x).
fn second_authority(e: &mut Env, lamports_: u64) -> (Keypair, Address, Address) {
    let auth = Keypair::new();
    let a = auth.pubkey();
    e.svm.airdrop(&a, lamports_).unwrap();
    let (q, x) = (fresh(), fresh());
    set_token(&mut e.svm, q, WSOL, a, 10 * SOL, true);
    let xm = Address::new_from_array(e.svm.get_account(&e.user_x).unwrap().data[..32].try_into().unwrap());
    set_token(&mut e.svm, x, xm, a, 0, false);
    (auth, q, x)
}
fn as_authority(mut l: Leg, a: Address, writable: bool) -> Leg {
    l.metas[0] = if writable { AccountMeta::new(a, true) } else { AccountMeta::new_readonly(a, true) };
    if l.out == Address::default() { l.out = a; }
    l
}

#[test]
fn account_structure_errors_and_v2_differences_from_nexus() {
    let mut rows = Vec::new();
    // (1) the last leg delivers into w2, not into the quote account
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let me = e.me();
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), e.swap(&e.b, e.user_x, e.w2, false, 0, 0, &[])];
        let o = e.send(&[v2_ix(prog, me, e.quote, SOL, 1, &legs, None)], &[], None);
        rows.push(format!("v2 last leg not into quote   on {:<5}: {:?}", if prog == NEXUS { "nexus" } else { "arbx" }, o.code().map(|c| format!("{c:#x}"))));
        assert_eq!(o.code(), Some(if prog == NEXUS { ERR_PROFIT } else { ERR_BAD_ACCOUNTS }));
    }
    // (2) a NATIVE_OUT leg whose output slot is not the authority
    for (name, v3) in [("v2", false), ("v3", true)] {
        let mut e = Env::new();
        let me = e.me();
        let mut sell = e.sell_native(&e.pump_dear, e.user_x);
        sell.out = e.w2;
        let legs = vec![e.swap(&e.a, e.quote, e.user_x, true, 0, 0, &[]), sell];
        let ix = if v3 { v3_ix(me, e.quote, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, ..BARE }) } else { v2_ix(ARBX, me, e.quote, SOL, 1, &legs, None) };
        let o = e.send(&[ix], &[], None);
        rows.push(format!("{name} NATIVE_OUT slot != authority (arbx): {:?}", o.code().map(|c| format!("{c:#x}"))));
        assert_eq!(o.code(), Some(if v3 { ERR_BAD_ACCOUNTS } else { ERR_BAD_DATA }));
    }
    // (3) COUNT_LAMPORTS with a non-wSOL quote account
    let mut e = Env::new();
    let me = e.me();
    let legs = vec![e.swap(&e.b, e.spare_x, e.w2, false, 0, 0, &[]), e.swap(&e.a, e.w2, e.spare_x, true, 0, 0, &[])];
    let o = e.send(&[v3_ix(me, e.spare_x, 1_000_000, 1, &legs, &V3 { flags: COUNT_LAMPORTS, ..BARE })], &[], None);
    rows.push(format!("v3 COUNT_LAMPORTS, X-mint quote: {:?}", o.code().map(|c| format!("{c:#x}"))));
    assert_eq!(o.code(), Some(ERR_QUOTE_NOT_WSOL));
    // (4) a native route with a read-only authority (separate fee payer)
    for prog in [NEXUS, ARBX] {
        let mut e = Env::new();
        let (auth, q, x) = second_authority(&mut e, SOL);
        let a = auth.pubkey();
        let legs = vec![as_authority(e.buy_native(&e.pump_cheap, x), a, false), as_authority(e.swap(&e.b, x, q, false, 0, 0, &[]), a, false)];
        let mut ix = v2_ix(prog, a, q, SOL, 1, &legs, None);
        ix.accounts[0] = AccountMeta::new_readonly(a, true);
        let o = e.send(&[ix], &[&auth], None);
        rows.push(format!("v2 native leg, read-only authority on {:<5}: {:?}", if prog == NEXUS { "nexus" } else { "arbx" }, o.err));
        assert!(!o.ok());
    }
    eprintln!("\n== account structure ==\n{}", rows.join("\n"));
}

/// FINDING 9 (proof). ERR_TIP_FUNDS compares the tip with the authority's whole balance, not with what it can spend
/// and stay rent-exempt. A tip that leaves the authority below the rent-exempt minimum passes the program (AXS1
/// result 0, tip paid) and then the runtime fails the transaction with InsufficientFundsForRent.
#[test]
fn finding_09_tip_that_breaks_rent_exemption_fails_after_a_passing_summary() {
    let mut e = Env::new();
    let (auth, q, x) = second_authority(&mut e, 1_000_000);
    let a = auth.pubkey();
    let legs = vec![as_authority(e.swap(&e.a, q, x, true, 0, 0, &[]), a, true), as_authority(e.swap(&e.b, x, q, false, 0, 0, &[]), a, true)];
    let t = TipParams { bps: 0, floor: 500_000, cap: 500_000, account_ix: 0 };
    let o = e.send(&[v3_ix(a, q, SOL, 1, &legs, &V3 { flags: COUNT_LAMPORTS, guard: None, tip: Some(t), tip_acct: None })], &[&auth], None);
    eprintln!("tip leaves the authority at 500,000 lamports: {:?}; AXS1 = {:?}", o.err, o.summaries().first().map(|s| (s.result, s.tip)));
    assert!(matches!(o.err, Some(TransactionError::InsufficientFundsForRent { .. })), "{}", o.dump());
    assert_eq!(o.summaries()[0].result, 0, "the program's own record says the route passed");
}
