//! Shared helpers for the SVM tests (tests/litesvm.rs, tests/venues.rs). Every test runs the BUILT programs under
//! LiteSVM's MAINNET feature set (`LiteSVM::new()`), which is what the program meets on mainnet. That is the gap that
//! let REVIEW.md #1 through: the old harness enabled a syscall mainnet does not have.
#![allow(dead_code)]

use arbx_exec::logic::*;
use base64::Engine as _;
use litesvm::LiteSVM;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_instruction_error::InstructionError;
use solana_keypair::Keypair;
use solana_message::{v0, AddressLookupTableAccount, Message, VersionedMessage};
use solana_signer::Signer;
use solana_transaction::{versioned::VersionedTransaction, Transaction};
use solana_transaction_error::TransactionError;

pub const SOL: u64 = 1_000_000_000;
pub const DIR: &str = env!("CARGO_MANIFEST_DIR");
/// The mainnet signature fee our transactions pay (one signature).
pub const SIG_FEE: u64 = 5_000;

pub const TOKEN: Address = Address::from_str_const("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
pub const TOKEN_2022: Address = Address::from_str_const("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
pub const SYSTEM: Address = Address::from_str_const("11111111111111111111111111111111");
pub const WSOL: Address = Address::from_str_const("So11111111111111111111111111111111111111112");
pub const CB: Address = Address::from_str_const("ComputeBudget111111111111111111111111111111");
pub const ALT_PROGRAM: Address = Address::from_str_const("AddressLookupTab1e1111111111111111111111111");
/// The feature gate of `sol_remaining_compute_units`: NOT active on mainnet (REVIEW.md #1).
pub const REMAINING_CU_FEATURE: Address = Address::from_str_const("5TuppMutoyzhUSfuYdhgzD47F92GL1g89KpCZQKqedxP");

/// arbx-exec is loaded at a fixed test address (its real id comes from its deploy keypair).
pub const ARBX: Address = Address::new_from_array([0xA7; 32]);
pub const NEXUS: Address = Address::new_from_array([0x4E; 32]);

pub fn venue(i: usize) -> Address { Address::from_str_const(ALLOWLIST_B58[i]) }
pub fn jito(i: usize) -> Address { Address::from_str_const(JITO_TIP_ACCOUNTS_B58[i]) }
pub fn fresh() -> Address { Keypair::new().pubkey() }

pub fn read(rel: &str) -> Vec<u8> {
    std::fs::read(format!("{DIR}/{rel}")).unwrap_or_else(|e| panic!("{rel}: {e}"))
}

/// The built arbx-exec ELF. It must be newer than the program source, or the tests would pass on a stale binary.
/// `ARBX_EXEC_SO=<path>` runs the suites against another build of the same source (e.g. an LTO experiment).
pub fn arbx_so() -> Vec<u8> {
    if let Ok(p) = std::env::var("ARBX_EXEC_SO") { return std::fs::read(&p).unwrap_or_else(|e| panic!("{p}: {e}")); }
    let so = format!("{DIR}/target/deploy/arbx_exec.so");
    let built = std::fs::metadata(&so).and_then(|m| m.modified())
        .unwrap_or_else(|e| panic!("{so}: {e}. Build it first: cargo-build-sbf --features onchain"));
    let src = std::fs::metadata(format!("{DIR}/src/lib.rs")).and_then(|m| m.modified()).unwrap();
    assert!(built >= src, "target/deploy/arbx_exec.so is older than src/lib.rs: rebuild with cargo-build-sbf --features onchain");
    std::fs::read(so).unwrap()
}
pub fn nexus_so() -> Vec<u8> { read("../nexus-arb-v2/target/deploy/nexus_arb_v2.so") }
pub fn mock_so() -> Vec<u8> { read("tests/mock-amm/target/deploy/mock_amm.so") }

/// LiteSVM with mainnet features (no extra feature, no remaining-CU syscall), arbx-exec at ARBX and the deployed
/// nexus-arb-v2 binary at NEXUS.
pub fn mainnet_svm() -> LiteSVM {
    let mut svm = LiteSVM::new();
    assert!(!svm_feature_active(&REMAINING_CU_FEATURE), "LiteSVM's mainnet set changed: re-check REVIEW.md #1");
    svm.add_program(ARBX, &arbx_so()).unwrap();
    svm.add_program(NEXUS, &nexus_so()).unwrap();
    svm
}
pub fn svm_feature_active(f: &Address) -> bool { LiteSVM::mainnet_feature_set().is_active(f) }

// ---- accounts ---------------------------------------------------------------------------------------------------

pub fn set_token_with(svm: &mut LiteSVM, key: Address, mint: Address, owner: Address, amount: u64, native: bool, program: Address) {
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
    svm.set_account(key, Account { lamports, data: d, owner: program, executable: false, rent_epoch: 0 }).unwrap();
}
pub fn set_token(svm: &mut LiteSVM, key: Address, mint: Address, owner: Address, amount: u64, native: bool) {
    set_token_with(svm, key, mint, owner, amount, native, TOKEN)
}

pub fn set_mint(svm: &mut LiteSVM, key: Address, decimals: u8) {
    let mut d = vec![0u8; 82];
    d[44] = decimals;
    d[45] = 1;
    let lamports = svm.minimum_balance_for_rent_exemption(82);
    svm.set_account(key, Account { lamports, data: d, owner: TOKEN, executable: false, rent_epoch: 0 }).unwrap();
}

pub fn amount(svm: &LiteSVM, key: &Address) -> u64 {
    let a = svm.get_account(key).unwrap();
    u64::from_le_bytes(a.data[64..72].try_into().unwrap())
}
pub fn lamports(svm: &LiteSVM, key: &Address) -> u64 { svm.get_account(key).map_or(0, |a| a.lamports) }
pub fn owner_of(svm: &LiteSVM, key: &Address) -> Address { svm.get_account(key).unwrap().owner }

/// An address lookup table account holding `addresses` (active, never deactivated, extended at slot 0).
pub fn set_alt(svm: &mut LiteSVM, key: Address, addresses: &[Address]) {
    let mut d = Vec::with_capacity(56 + 32 * addresses.len());
    d.extend(1u32.to_le_bytes()); // ProgramState::LookupTable
    d.extend(u64::MAX.to_le_bytes()); // deactivation_slot: active
    d.extend(0u64.to_le_bytes()); // last_extended_slot
    d.push(0); // last_extended_slot_start_index
    d.push(0); // authority: None (frozen)
    d.extend([0u8; 32]);
    d.extend([0u8; 2]); // padding to LOOKUP_TABLE_META_SIZE = 56
    assert_eq!(d.len(), 56);
    for a in addresses { d.extend_from_slice(a.as_ref()); }
    let lamports = svm.minimum_balance_for_rent_exemption(d.len());
    svm.set_account(key, Account { lamports, data: d, owner: ALT_PROGRAM, executable: false, rent_epoch: 0 }).unwrap();
}

// ---- instructions -------------------------------------------------------------------------------------------------

pub fn cu_limit(units: u32) -> Instruction {
    let mut d = vec![2u8];
    d.extend_from_slice(&units.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}
pub fn cu_price(micro_lamports: u64) -> Instruction {
    let mut d = vec![3u8];
    d.extend_from_slice(&micro_lamports.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}
pub fn loaded_data_limit(bytes: u32) -> Instruction {
    let mut d = vec![4u8];
    d.extend_from_slice(&bytes.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}
pub fn heap_frame(bytes: u32) -> Instruction {
    let mut d = vec![1u8];
    d.extend_from_slice(&bytes.to_le_bytes());
    Instruction { program_id: CB, accounts: vec![], data: d }
}

/// One leg: the account it delivers into, the venue program, the venue's own accounts and data (amount at offset
/// `amount_offset`), and its v3 leg flags.
#[derive(Clone, Debug)]
pub struct Leg { pub out: Address, pub program: Address, pub metas: Vec<AccountMeta>, pub data: Vec<u8>, pub flags: u8, pub amount_offset: u8 }

pub fn route_accounts(authority: Address, quote: Address, legs: &[Leg], tip: Option<(Address, Address, bool)>) -> Vec<AccountMeta> {
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

pub fn v2_ix(program: Address, authority: Address, quote: Address, amount_in: u64, min_profit: u64, legs: &[Leg], guard: Option<u64>) -> Instruction {
    let specs: Vec<(u8, u8, &[u8])> = legs.iter().map(|l| {
        let f = (if l.flags & LEG_NATIVE_IN != 0 { NATIVE_IN } else { 0 }) | (if l.flags & LEG_NATIVE_OUT != 0 { NATIVE_OUT } else { 0 });
        (l.metas.len() as u8 | f, l.amount_offset, l.data.as_slice())
    }).collect();
    let data = match guard { Some(g) => encode_guarded(amount_in, min_profit, &specs, g), None => encode(amount_in, min_profit, &specs) };
    Instruction { program_id: program, accounts: route_accounts(authority, quote, legs, None), data }
}

/// v3 options. `guard: None` builds a route the program must refuse (PAYER_GUARD is mandatory).
#[derive(Clone, Copy)]
pub struct V3 { pub flags: u8, pub guard: Option<u64>, pub tip: Option<TipParams>, pub tip_acct: Option<(Address, Address, bool)> }
/// The minimal valid v3 route: payer guard with max_drop 0, nothing else.
pub const GUARDED: V3 = V3 { flags: 0, guard: Some(0), tip: None, tip_acct: None };

pub fn v3_ix(program: Address, authority: Address, quote: Address, amount_in: u64, min_profit: u64, legs: &[Leg], o: &V3) -> Instruction {
    let specs: Vec<LegSpec> = legs.iter().map(|l| LegSpec { n_accounts: l.metas.len() as u8, flags: l.flags, amount_offset: l.amount_offset, data: &l.data }).collect();
    let data = encode_v3(o.flags, amount_in, min_profit, o.guard, o.tip, &specs);
    let tip = o.tip_acct.or_else(|| o.tip.map(|t| (SYSTEM, jito(t.account_ix as usize), true)));
    Instruction { program_id: program, accounts: route_accounts(authority, quote, legs, tip), data }
}

// ---- sending and reading results ----------------------------------------------------------------------------------

#[derive(Debug)]
pub struct Outcome { pub err: Option<TransactionError>, pub logs: Vec<String>, pub cu: Option<u64>, pub tx_bytes: usize }

impl Outcome {
    pub fn ok(&self) -> bool { self.err.is_none() }
    /// the Custom code of an InstructionError
    pub fn code(&self) -> Option<u32> {
        match &self.err { Some(TransactionError::InstructionError(_, InstructionError::Custom(c))) => Some(*c), _ => None }
    }
    pub fn ix_err(&self) -> Option<&InstructionError> {
        match &self.err { Some(TransactionError::InstructionError(_, e)) => Some(e), _ => None }
    }
    fn data_records(&self) -> Vec<Vec<u8>> {
        self.logs.iter().filter_map(|l| l.strip_prefix("Program data: "))
            .flat_map(|b| b.split(' ').filter_map(|p| base64::engine::general_purpose::STANDARD.decode(p.trim()).ok()).collect::<Vec<_>>())
            .collect()
    }
    pub fn summaries(&self) -> Vec<Summary> { self.data_records().iter().filter_map(|d| decode_summary(d)).collect() }
    pub fn summary(&self) -> Summary {
        let s = self.summaries();
        assert_eq!(s.len(), 1, "exactly one AXS1 record expected:\n{}", self.dump());
        s[0]
    }
    pub fn leg_logs(&self) -> Vec<LegLog> { self.data_records().iter().filter_map(|d| decode_leg_log(d)).collect() }
    /// the number of times `program` was invoked (at any depth)
    pub fn invoked(&self, program: &Address) -> usize {
        let p = format!("Program {program} invoke [");
        self.logs.iter().filter(|l| l.starts_with(&p)).count()
    }
    pub fn dump(&self) -> String { format!("err={:?} cu={:?} bytes={}\n  {}", self.err, self.cu, self.tx_bytes, self.logs.join("\n  ")) }
}

/// "Program <id> consumed N of M compute units" of the LAST top-level instruction of `program`
pub fn program_cu(logs: &[String], program: &Address) -> Option<u64> {
    let pfx = format!("Program {} consumed ", program);
    logs.iter().rev().find_map(|l| l.strip_prefix(&pfx).and_then(|r| r.split(' ').next()).and_then(|n| n.parse().ok()))
}

/// Send a legacy transaction: CU limit 1.4M, an optional heap frame, then `ixs`. `cu` is the last instruction's.
pub fn send(svm: &mut LiteSVM, payer: &Keypair, ixs: &[Instruction], extra_signers: &[&Keypair], heap: Option<u32>) -> Outcome {
    let mut all = vec![cu_limit(1_400_000)];
    if let Some(h) = heap { all.push(heap_frame(h)); }
    all.extend_from_slice(ixs);
    let mut signers: Vec<&Keypair> = vec![payer];
    signers.extend_from_slice(extra_signers);
    let msg = Message::new(&all, Some(&payer.pubkey()));
    let tx = Transaction::new(&signers, msg, svm.latest_blockhash());
    let tx_bytes = 1 + 64 * signers.len() + VersionedMessage::Legacy(tx.message.clone()).serialize().len();
    let r = svm.send_transaction(tx);
    finish(svm, r, &ixs.last().unwrap().program_id, tx_bytes)
}

/// Compile `ixs` into a v0 message with `tables`, its serialized transaction size (signatures included).
pub fn v0_message(svm: &LiteSVM, payer: &Address, ixs: &[Instruction], tables: &[AddressLookupTableAccount]) -> (v0::Message, usize, usize) {
    let msg = v0::Message::try_compile(payer, ixs, tables, svm.latest_blockhash()).unwrap();
    let sigs = msg.header.num_required_signatures as usize;
    let bytes = 1 + 64 * sigs + VersionedMessage::V0(msg.clone()).serialize().len();
    (msg, bytes, sigs)
}

/// Send `ixs` (taken as complete, compute-budget instructions included) as a v0 transaction with lookup tables.
pub fn send_v0(svm: &mut LiteSVM, payer: &Keypair, ixs: &[Instruction], tables: &[AddressLookupTableAccount], program: &Address) -> Outcome {
    let (msg, tx_bytes, _) = v0_message(svm, &payer.pubkey(), ixs, tables);
    let tx = VersionedTransaction::try_new(VersionedMessage::V0(msg), &[payer]).unwrap();
    let r = svm.send_transaction(tx);
    finish(svm, r, program, tx_bytes)
}

fn finish(svm: &mut LiteSVM, r: litesvm::types::TransactionResult, program: &Address, tx_bytes: usize) -> Outcome {
    svm.expire_blockhash();
    let (err, logs) = match r { Ok(m) => (None, m.logs), Err(f) => (Some(f.err), f.meta.logs) };
    let cu = program_cu(&logs, program);
    Outcome { err, logs, cu, tx_bytes }
}

// ---- ELF syscall audit (REVIEW.md #1) -----------------------------------------------------------------------------

/// The static-syscall hashes an SBPF v3 ELF calls: every `call imm` (opcode 0x85) with src = 0 in the executable
/// PT_LOAD segment. (src = 1 is an internal, pc-relative call.) Panics on anything but a v3 ELF.
pub fn elf_static_syscalls(elf: &[u8]) -> std::collections::BTreeSet<u32> {
    let u16_at = |o: usize| u16::from_le_bytes(elf[o..o + 2].try_into().unwrap()) as usize;
    let u32_at = |o: usize| u32::from_le_bytes(elf[o..o + 4].try_into().unwrap());
    let u64_at = |o: usize| u64::from_le_bytes(elf[o..o + 8].try_into().unwrap()) as usize;
    assert_eq!(&elf[..4], b"\x7fELF");
    assert_eq!(u32_at(48), 3, "SBPF v3 (static syscalls) expected");
    let (phoff, phentsize, phnum) = (u64_at(32), u16_at(54), u16_at(56));
    let mut out = std::collections::BTreeSet::new();
    let mut text_segments = 0;
    for i in 0..phnum {
        let o = phoff + i * phentsize;
        let (p_type, p_flags, p_offset, p_filesz) = (u32_at(o), u32_at(o + 4), u64_at(o + 8), u64_at(o + 32));
        if p_type != 1 || p_flags & 1 == 0 { continue; } // PT_LOAD with PF_X
        text_segments += 1;
        assert_eq!(p_filesz % 8, 0);
        for insn in elf[p_offset..p_offset + p_filesz].chunks_exact(8) {
            if insn[0] == 0x85 && insn[1] >> 4 == 0 { out.insert(u32::from_le_bytes(insn[4..8].try_into().unwrap())); }
        }
    }
    assert_eq!(text_segments, 1);
    out
}
