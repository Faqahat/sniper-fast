//! SVM tests of the BUILT program (program/snipe-guard/release/snipe_guard.so, or $SNIPE_GUARD_SO) under LiteSVM's MAINNET feature
//! set: AUTH runs first (compiled wallets, not signing, other signers), the allowlist PDA (init by the upgrade authority, add /
//! remove / rotate by the admin, look-alikes refused, a pre-funded PDA), every check's opaque code decoded back, the echo, the
//! compute units, the ELF's syscalls (all registered on mainnet) and the strings scan.
//! Run: bash program/snipe-guard/test_svm.sh
use litesvm::LiteSVM;
use snipe_guard::client::{decode, Guard};
use snipe_guard::logic::*;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_instruction_error::InstructionError;
use solana_keypair::Keypair;
use solana_message::Message;
use solana_signer::Signer;
use solana_transaction::Transaction;
use solana_transaction_error::TransactionError;

const CB: Address = Address::from_str_const("ComputeBudget111111111111111111111111111111");
const PROG: Address = Address::new_from_array([0x5A; 32]);
const LOADER: Address = Address::new_from_array(LOADER_V3);
const M: u64 = 1_000_000 * UNIT; // one million tokens (0.1% of supply)

fn so_path() -> String {
    std::env::var("SNIPE_GUARD_SO").unwrap_or_else(|_| concat!(env!("CARGO_MANIFEST_DIR"), "/../snipe-guard/release/snipe_guard.so").to_string())
}
fn so() -> Vec<u8> { let p = so_path(); std::fs::read(&p).unwrap_or_else(|e| panic!("{p}: {e}")) }
fn ams() -> Address { Address::new_from_array(COMPILED[0]) }
fn cu_limit(u: u32) -> Instruction { let mut d = vec![2u8]; d.extend(u.to_le_bytes()); Instruction { program_id: CB, accounts: vec![], data: d } }
fn a(k: &Address) -> [u8; 32] { k.to_bytes() }

struct Env { svm: LiteSVM, ua: Keypair }
#[derive(Debug)]
struct Out { err: Option<TransactionError>, cu: u64, logs: Vec<String>, ret: Vec<u8> }
impl Out {
    fn custom(&self) -> Option<(u8, u32)> { match &self.err { Some(TransactionError::InstructionError(i, InstructionError::Custom(c))) => Some((*i, *c)), _ => None } }
    /// the decoded failure at instruction `ix`
    fn fail(&self, ix: u8) -> Option<Fail> { self.custom().filter(|(i, _)| *i == ix).and_then(|(_, c)| decode(c)) }
}

impl Env {
    /// sigverify OFF: our compiled wallets can "sign" without their keys (a signer = the message header's flag; nothing else is
    /// checked by the program). The upgrade authority `ua` is written into the programdata account.
    fn new() -> Env {
        let mut svm = LiteSVM::new().with_sigverify(false);
        svm.add_program(PROG, &so()).unwrap();
        let ua = Keypair::new();
        let (pd, _) = Address::find_program_address(&[PROG.as_ref()], &LOADER);
        let mut acc = svm.get_account(&pd).unwrap();
        acc.data[12] = 1;
        acc.data[13..45].copy_from_slice(&ua.pubkey().to_bytes());
        svm.set_account(pd, acc).unwrap();
        for w in COMPILED { svm.airdrop(&Address::new_from_array(w), 10_000_000_000).unwrap(); }
        svm.airdrop(&ua.pubkey(), 10_000_000_000).unwrap();
        svm.warp_to_slot(1_000);
        Env { svm, ua }
    }
    fn funded(&mut self) -> Keypair { let k = Keypair::new(); self.svm.airdrop(&k.pubkey(), 10_000_000_000).unwrap(); k }
    /// a Token-2022 account (170 bytes) holding `amount`
    fn token(&mut self, amount: u64, program: [u8; 32]) -> Address {
        let k = Keypair::new().pubkey();
        let mut d = vec![0u8; 170];
        d[64..72].copy_from_slice(&amount.to_le_bytes());
        d[108] = 1; d[165] = 2;
        let rent = self.svm.minimum_balance_for_rent_exemption(d.len());
        self.svm.set_account(k, Account { lamports: rent, data: d, owner: Address::new_from_array(program), executable: false, rent_epoch: 0 }).unwrap();
        k
    }
    fn gix(&self, g: &Guard, wallet: Address, list: Option<Address>) -> Instruction {
        Instruction { program_id: PROG, data: g.data(), accounts: g.accounts(a(&wallet), list.map(|l| a(&l))).into_iter()
            .map(|(k, s, w)| AccountMeta { pubkey: Address::new_from_array(k), is_signer: s, is_writable: w }).collect() }
    }
    /// a tx paid by `payer` (unsigned: sigverify is off), the CU-limit instruction first
    fn send(&mut self, payer: &Address, ixs: &[Instruction]) -> Out {
        let mut all = vec![cu_limit(200_000)];
        all.extend_from_slice(ixs);
        let mut tx = Transaction::new_unsigned(Message::new(&all, Some(payer)));
        tx.message.recent_blockhash = self.svm.latest_blockhash();
        let r = self.svm.send_transaction(tx);
        self.svm.expire_blockhash();
        let pfx = format!("Program {PROG} consumed ");
        let (err, logs, ret) = match r { Ok(m) => (None, m.logs, m.return_data.data), Err(f) => (Some(f.err), f.meta.logs, vec![]) };
        let cu = logs.iter().find_map(|l| l.strip_prefix(&pfx).and_then(|r| r.split(' ').next()).and_then(|n| n.parse().ok())).unwrap_or(0);
        Out { err, cu, logs, ret }
    }
    /// ASSERT signed (header flag) by our AMS wallet, which pays
    fn run(&mut self, g: &Guard) -> Out { let ix = self.gix(g, ams(), None); self.send(&ams(), &[ix]) }
    fn list_addr(&self) -> (Address, u8) { Address::find_program_address(&[&AL_SEED], &PROG) }
    fn init_ix(&self, payer: &Address, admin: &Address, bump: u8, pd: Address, ua: &Address) -> Instruction {
        let (l, _) = self.list_addr();
        let lamports = self.svm.minimum_balance_for_rent_exemption(AL_LEN);
        Instruction { program_id: PROG, data: snipe_guard::client::al_init_data(bump, a(admin), lamports), accounts: vec![
            AccountMeta::new(*payer, true), AccountMeta::new(l, false), AccountMeta::new_readonly(*ua, true), AccountMeta::new_readonly(pd, false),
            AccountMeta::new_readonly(Address::new_from_array(SYSTEM), false)] }
    }
    fn edit_ix(&self, op: u8, admin: &Address, key: &Address, list: Address) -> Instruction {
        Instruction { program_id: PROG, data: snipe_guard::client::al_edit_data(op, a(key)), accounts: vec![AccountMeta::new_readonly(*admin, true), AccountMeta::new(list, false)] }
    }
    fn programdata(&self) -> Address { Address::find_program_address(&[PROG.as_ref()], &LOADER).0 }
}

fn dl(slot: u64) -> Guard { Guard { deadline: Some(slot), ..Default::default() } }

#[test]
fn auth_first_compiled_wallets_only() {
    let mut e = Env::new();
    for w in COMPILED {
        let w = Address::new_from_array(w);
        let ix = e.gix(&dl(5_000), w, None);
        let o = e.send(&w, &[ix]);
        assert!(o.err.is_none(), "{w}: {:?}\n{}", o.err, o.logs.join("\n"));
    }
    // the same call by any other signer: refused at AUTH with its own code, before the (late!) deadline is looked at
    let x = e.funded();
    let ix = e.gix(&dl(1), x.pubkey(), None);
    let o = e.send(&x.pubkey(), &[ix]);
    assert_eq!(o.fail(1), Some(Fail::new(K_AUTH, A_NO_LIST)), "{o:?}");
    // our wallet present but NOT signing (someone else pays): refused before any other check
    let mut ix = e.gix(&dl(1), ams(), None);
    ix.accounts[0].is_signer = false;
    let o = e.send(&x.pubkey(), &[ix]);
    assert_eq!(o.fail(1), Some(Fail::new(K_AUTH, A_NOT_SIGNER)), "{o:?}");
    // no accounts at all
    let ix = Instruction { program_id: PROG, data: dl(5_000).data(), accounts: vec![] };
    assert_eq!(e.send(&x.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_NO_ACCOUNTS)));
    // another signer that passes some random account as "the list": refused (not ours)
    let fake = e.token(5, TOKEN_2022);
    let ix = e.gix(&dl(5_000), x.pubkey(), Some(fake));
    assert_eq!(e.send(&x.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_LIST_OWNER)));
    // an unknown op is refused too (no state anywhere)
    let ix = Instruction { program_id: PROG, data: vec![0x00, 1], accounts: vec![AccountMeta::new_readonly(ams(), true)] };
    assert_eq!(e.send(&ams(), &[ix]).fail(1), Some(Fail::new(K_DATA, D_OP)));
}

#[test]
fn checks_and_their_codes() {
    let mut e = Env::new();
    let curve = e.token(900 * M, TOKEN_2022);
    let hs: Vec<Address> = [40u64, 30, 20, 15, 12, 10].iter().map(|x| e.token(x * M, TOKEN_2022)).collect();
    let classic = e.token(20 * M, TOKEN);
    let closed = Keypair::new().pubkey(); // never created = closed: system-owned, no data
    // deadline (Clock.slot = 1000)
    assert!(e.run(&dl(1_000)).err.is_none());
    assert_eq!(e.run(&dl(999)).fail(1), Some(Fail { kind: K_DEADLINE, idx: 0, cnt: 0, gap: 1 }));
    assert_eq!(e.run(&dl(990)).fail(1), Some(Fail { kind: K_DEADLINE, idx: 0, cnt: 0, gap: 5 }), "10 late -> 9-16");
    // curve band
    let band = |lo, hi| Guard { curve: Some((a(&curve), lo, hi)), ..Default::default() };
    assert!(e.run(&band(850 * M, 950 * M)).err.is_none());
    assert_eq!(e.run(&band(901 * M, 950 * M)).fail(1).map(|f| f.kind), Some(K_CURVE_HIGH));
    assert_eq!(e.run(&band(850 * M, 899 * M)).fail(1).map(|f| f.kind), Some(K_CURVE_DEEP));
    // floors G-A 6:0.9:1 (abort when MORE THAN 1 is below)
    let fl = |v: &[(Address, u64)], mv| Guard { deadline: Some(5_000), floors: v.iter().map(|(k, f)| (a(k), (*f * 9 / 10) as u32)).collect(), max_viol: mv, ..Default::default() };
    let signed: Vec<(Address, u64)> = hs.iter().zip([40u64, 30, 20, 15, 12, 10]).map(|(k, x)| (*k, x * 1_000_000)).collect();
    assert!(e.run(&fl(&signed, 1)).err.is_none());
    let mut one_left = signed.clone(); one_left[0].0 = closed;
    assert!(e.run(&fl(&one_left, 1)).err.is_none(), "one leaver (closed account) tolerated");
    let mut two_left = one_left.clone(); two_left[2].0 = classic; two_left[2].1 = 40_000_000; // classic Token holds 20M < 36M
    assert_eq!(e.run(&fl(&two_left, 1)).fail(1), Some(Fail { kind: K_FLOORS, idx: 0, cnt: 2, gap: 0 }), "2 below: abort, worst = the closed one");
    let mut half = signed.clone(); half[3].1 = 33_000_000; half[5].1 = 12_000_000; // 15/29.7 = 50%, 10/10.8 = 92%
    assert_eq!(e.run(&fl(&half, 1)).fail(1), Some(Fail { kind: K_FLOORS, idx: 3, cnt: 2, gap: 3 }));
    // malformed: a floor account missing
    let mut ix = e.gix(&fl(&signed, 1), ams(), None);
    ix.accounts.pop();
    assert_eq!(e.send(&ams(), &[ix]).fail(1), Some(Fail::new(K_ACCTS, X_COUNT)));
    let bad = Instruction { program_id: PROG, accounts: vec![AccountMeta::new_readonly(ams(), true)], data: vec![OP_ASSERT, 0x40] };
    assert_eq!(e.send(&ams(), &[bad]).fail(1), Some(Fail::new(K_DATA, D_FLAGS)));
    // echo: [flags, n | viol << 4, margin bucket]
    let mut g = fl(&one_left, 1); g.echo = true;
    let o = e.run(&g);
    assert!(o.err.is_none());
    assert_eq!(o.ret, vec![F_DEADLINE | F_FLOORS, 6 | 1 << 4, 2]);
}

#[test]
fn allowlist_pda_init_add_remove_rotate() {
    let mut e = Env::new();
    let (list, bump) = e.list_addr();
    let pd = e.programdata();
    let payer = e.funded();
    let admin = e.funded();
    let ua = e.ua.pubkey();
    // griefing: somebody pre-funds the PDA address; init must still work
    let griefer = e.funded();
    let t = solana_instruction::Instruction { program_id: Address::new_from_array(SYSTEM), accounts: vec![AccountMeta::new(griefer.pubkey(), true), AccountMeta::new(list, false)],
        data: { let mut d = vec![2u8, 0, 0, 0]; d.extend(1_000_000u64.to_le_bytes()); d } };
    assert!(e.send(&griefer.pubkey(), &[t]).err.is_none());
    // not the upgrade authority: refused
    let ix = e.init_ix(&payer.pubkey(), &admin.pubkey(), bump, pd, &admin.pubkey());
    assert_eq!(e.send(&payer.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_NOT_AUTHORITY)));
    // a programdata account that is not this program's (a look-alike with our authority inside)
    let fake_pd = Keypair::new().pubkey();
    let pda = e.svm.get_account(&pd).unwrap();
    e.svm.set_account(fake_pd, pda.clone()).unwrap();
    let ix = e.init_ix(&payer.pubkey(), &admin.pubkey(), bump, fake_pd, &ua);
    assert_eq!(e.send(&payer.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_PROGDATA)));
    // the wrong bump (address mismatch)
    let ix = e.init_ix(&payer.pubkey(), &admin.pubkey(), bump.wrapping_sub(1), pd, &ua);
    assert_eq!(e.send(&payer.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_LIST_ADDR)));
    // the real init
    let ix = e.init_ix(&payer.pubkey(), &admin.pubkey(), bump, pd, &ua);
    let o = e.send(&payer.pubkey(), &[ix.clone()]);
    assert!(o.err.is_none(), "{o:?}");
    let acc = e.svm.get_account(&list).unwrap();
    assert_eq!((acc.owner, acc.data.len()), (PROG, AL_LEN));
    assert!(acc.lamports >= e.svm.minimum_balance_for_rent_exemption(AL_LEN));
    println!("INIT CU: {}", o.cu);
    assert_eq!(e.send(&payer.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_LIST_STATE)), "init twice");

    // a wallet not compiled in: refused without the list, refused when not listed
    let w = e.funded();
    let g = dl(5_000);
    let ix = e.gix(&g, w.pubkey(), None);
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_NO_LIST)));
    let ix = e.gix(&g, w.pubkey(), Some(list));
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_NOT_LISTED)));
    // non-admin cannot edit (the upgrade authority neither)
    for who in [&w, &e.ua.insecure_clone()] {
        let ix = e.edit_ix(OP_AL_ADD, &who.pubkey(), &w.pubkey(), list);
        assert_eq!(e.send(&who.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_NOT_ADMIN)));
    }
    // admin adds: the listed wallet passes WITH the list
    let ix = e.edit_ix(OP_AL_ADD, &admin.pubkey(), &w.pubkey(), list);
    assert!(e.send(&admin.pubkey(), &[ix]).err.is_none());
    let ix = e.gix(&g, w.pubkey(), Some(list));
    let o = e.send(&w.pubkey(), &[ix]);
    assert!(o.err.is_none(), "{o:?}");
    let cu_listed = o.cu;
    // the compiled wallet passes WITHOUT the list (and pays nothing for it)
    let cu_compiled = e.run(&g).cu;
    println!("AUTH CU: deadline-only compiled wallet {cu_compiled}, listed wallet via the PDA {cu_listed}");
    // look-alikes: the same bytes in an account owned by another program; owned by us at another address
    let data = e.svm.get_account(&list).unwrap().data;
    let other_owner = Keypair::new().pubkey();
    e.svm.set_account(other_owner, Account { lamports: 10_000_000, data: data.clone(), owner: Address::new_from_array(TOKEN), executable: false, rent_epoch: 0 }).unwrap();
    let ix = e.gix(&g, w.pubkey(), Some(other_owner));
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_LIST_OWNER)));
    let other_addr = Keypair::new().pubkey();
    e.svm.set_account(other_addr, Account { lamports: 10_000_000, data: data.clone(), owner: PROG, executable: false, rent_epoch: 0 }).unwrap();
    let ix = e.gix(&g, w.pubkey(), Some(other_addr));
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_LIST_ADDR)), "wrong seeds / address");
    let mut short = data.clone(); short.pop();
    e.svm.set_account(other_addr, Account { lamports: 10_000_000, data: short, owner: PROG, executable: false, rent_epoch: 0 }).unwrap();
    let ix = e.gix(&g, w.pubkey(), Some(other_addr));
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_LIST_LEN)));
    // editing a look-alike: refused
    let ix = e.edit_ix(OP_AL_ADD, &admin.pubkey(), &w.pubkey(), other_owner);
    assert_eq!(e.send(&admin.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_LIST_STATE)));
    // remove: the wallet fails again
    let ix = e.edit_ix(OP_AL_REMOVE, &admin.pubkey(), &w.pubkey(), list);
    assert!(e.send(&admin.pubkey(), &[ix]).err.is_none());
    let ix = e.gix(&g, w.pubkey(), Some(list));
    assert_eq!(e.send(&w.pubkey(), &[ix]).fail(1), Some(Fail::new(K_AUTH, A_NOT_LISTED)));
    // rotate the admin: the old admin is out
    let admin2 = e.funded();
    let ix = e.edit_ix(OP_AL_ADMIN, &admin.pubkey(), &admin2.pubkey(), list);
    assert!(e.send(&admin.pubkey(), &[ix]).err.is_none());
    let ix = e.edit_ix(OP_AL_ADD, &admin.pubkey(), &w.pubkey(), list);
    assert_eq!(e.send(&admin.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_NOT_ADMIN)));
    let ix = e.edit_ix(OP_AL_ADD, &admin2.pubkey(), &w.pubkey(), list);
    assert!(e.send(&admin2.pubkey(), &[ix]).err.is_none());
    let (adm, _, ws) = snipe_guard::client::al_read(&e.svm.get_account(&list).unwrap().data).unwrap();
    assert_eq!((adm, ws), (a(&admin2.pubkey()), vec![a(&w.pubkey())]));
    // the admin must sign
    let mut ix = e.edit_ix(OP_AL_REMOVE, &admin2.pubkey(), &w.pubkey(), list);
    ix.accounts[0].is_signer = false;
    assert_eq!(e.send(&payer.pubkey(), &[ix]).fail(1), Some(Fail::new(K_ADMIN, M_SIGNER)));
}

/// the CU of each shape (pass path), the fail paths, and the budget the try's CU limit must hold: dip42 buys used max 102.2k CU
/// incl. Lighthouse's ~400 (onchain REPORT, 425 fills); the 120,000 limit must still hold with the guard's worst shape
#[test]
fn compute_units_table() {
    let mut e = Env::new();
    let curve = e.token(900 * M, TOKEN_2022);
    let hs: Vec<Address> = (0..12).map(|i| e.token((40 - i) * M, TOKEN_2022)).collect();
    let fl = |n: usize| -> Vec<([u8; 32], u32)> { hs[..n].iter().map(|k| (a(k), 1_000_000)).collect() };
    let cv = Some((a(&curve), 850 * M, 950 * M));
    let rows: Vec<(&str, Guard)> = vec![
        ("deadline", dl(5_000)),
        ("deadline + echo", Guard { echo: true, ..dl(5_000) }),
        ("deadline + curve", Guard { curve: cv, ..dl(5_000) }),
        ("deadline + 4 floors", Guard { floors: fl(4), max_viol: 1, ..dl(5_000) }),
        ("deadline + 6 floors (G-A)", Guard { floors: fl(6), max_viol: 1, ..dl(5_000) }),
        ("deadline + 8 floors", Guard { floors: fl(8), max_viol: 1, ..dl(5_000) }),
        ("deadline + curve + 12 floors (max)", Guard { curve: cv, floors: fl(12), max_viol: 1, ..dl(5_000) }),
    ];
    println!("{:<44} {:>6} {:>5} {:>6}", "shape (pass path, compiled wallet)", "CU", "data", "accts");
    let mut worst = 0;
    for (name, g) in rows {
        let o = e.run(&g);
        assert!(o.err.is_none(), "{name}: {:?}\n{}", o.err, o.logs.join("\n"));
        println!("{:<44} {:>6} {:>5} {:>6}", name, o.cu, g.data().len(), g.accounts(COMPILED[0], None).len());
        worst = worst.max(o.cu);
    }
    let o = e.run(&dl(999));
    println!("{:<44} {:>6}", "deadline, late (fail)", o.cu);
    let o = e.run(&Guard { floors: hs[..6].iter().map(|k| (a(k), 50_000_000)).collect(), max_viol: 1, ..dl(5_000) });
    assert_eq!(o.fail(1).map(|f| f.kind), Some(K_FLOORS));
    println!("{:<44} {:>6}", "deadline + 6 floors, all below (fail)", o.cu);
    let x = e.funded();
    let ix = e.gix(&dl(5_000), x.pubkey(), None);
    println!("{:<44} {:>6}", "other signer (AUTH fail)", e.send(&x.pubkey(), &[ix]).cu);
    // budget: the measured buy max (102.2k incl. Lighthouse) - Lighthouse + this guard's worst shape < 120k
    const BUY_MAX_CU: u64 = 102_200;
    assert!(worst < 3_000, "the guard's worst pass shape costs {worst} CU");
    assert!(BUY_MAX_CU + worst < 120_000, "{} CU", BUY_MAX_CU + worst);
    println!("program size: {} bytes", so().len());
}

fn elf_static_syscalls(elf: &[u8]) -> std::collections::BTreeSet<u32> {
    let u16_at = |o: usize| u16::from_le_bytes(elf[o..o + 2].try_into().unwrap()) as usize;
    let u32_at = |o: usize| u32::from_le_bytes(elf[o..o + 4].try_into().unwrap());
    let u64_at = |o: usize| u64::from_le_bytes(elf[o..o + 8].try_into().unwrap()) as usize;
    assert_eq!(&elf[..4], b"\x7fELF");
    assert_eq!(u32_at(48), 3, "SBPF v3 (static syscalls) expected");
    let (phoff, phentsize, phnum) = (u64_at(32), u16_at(54), u16_at(56));
    let mut out = std::collections::BTreeSet::new();
    for i in 0..phnum {
        let o = phoff + i * phentsize;
        let (p_type, p_flags, p_offset, p_filesz) = (u32_at(o), u32_at(o + 4), u64_at(o + 8), u64_at(o + 32));
        if p_type != 1 || p_flags & 1 == 0 { continue; }
        for insn in elf[p_offset..p_offset + p_filesz].chunks_exact(8) {
            if insn[0] == 0x85 && insn[1] >> 4 == 0 { out.insert(u32::from_le_bytes(insn[4..8].try_into().unwrap())); }
        }
    }
    out
}

/// every static syscall of the ELF is registered under mainnet features (and stays so with every known feature on); SBPF v3
/// deployment is active in LiteSVM's mainnet feature list (the ops tool re-checks the feature account on the target cluster)
#[test]
fn elf_syscalls_registered_on_mainnet() {
    use solana_program_runtime::execution_budget::SVMTransactionExecutionBudget;
    let budget = SVMTransactionExecutionBudget::new_with_defaults(false);
    let env = |fs: &agave_feature_set::FeatureSet| solana_syscalls::create_program_runtime_environment(&fs.runtime_features(), &budget, true, false).unwrap();
    let mainnet = env(&LiteSVM::mainnet_feature_set());
    let every = env(&agave_feature_set::FeatureSet::all_enabled());
    assert!(LiteSVM::mainnet_feature_set().is_active(&agave_feature_set::enable_sbpf_v3_deployment_and_execution::id()), "SBPF v3 not active on mainnet");
    let calls = elf_static_syscalls(&so());
    let mut names = Vec::new();
    for h in &calls {
        let name = mainnet.get_function_registry().lookup_by_key(*h).map(|(n, _)| String::from_utf8_lossy(n).into_owned());
        assert!(name.is_some(), "static syscall {h:#010x} is NOT registered under mainnet features");
        assert!(every.get_function_registry().lookup_by_key(*h).is_some());
        names.push(name.unwrap());
    }
    println!("syscalls ({}): {}", names.len(), names.join(", "));
    for n in &names {
        assert!(["abort", "sol_get_clock_sysvar", "sol_set_return_data", "sol_create_program_address", "sol_try_find_program_address", "sol_invoke_signed_c",
            "sol_memcpy_", "sol_memset_", "sol_memcmp_", "sol_memmove_"].contains(&n.as_str()), "unexpected syscall {n}");
    }
}

/// the ELF carries no revealing text: no printable run contains any of these words (case-insensitive)
#[test]
fn strings_scan_no_revealing_words() {
    let elf = so();
    let mut runs: Vec<String> = Vec::new();
    let mut cur = String::new();
    for &b in &elf {
        if (0x20..0x7f).contains(&b) { cur.push(b as char); } else { if cur.len() >= 3 { runs.push(cur.clone()); } cur.clear(); }
    }
    if cur.len() >= 3 { runs.push(cur); }
    const WORDS: [&str; 27] = ["guard", "holder", "floor", "slot", "deadline", "curve", "abort", "allow", "admin", "auth", "snipe", "pump", "error",
        "fail", "panic", "sniper", "lamport", "token", "wallet", "signer", "list", "src/", ".rs", "assert", "leaver", "check", "band"];
    let hits: Vec<&String> = runs.iter().filter(|r| { let l = r.to_ascii_lowercase(); WORDS.iter().any(|w| l.contains(w)) }).collect();
    let long: Vec<&String> = runs.iter().filter(|r| r.len() >= 4).collect();
    println!("printable runs >= 4 bytes: {long:?}");
    assert!(hits.is_empty(), "revealing text in the ELF: {hits:?}");
    // only the section names are real text
    for r in &long { assert!([".text", ".rodata", ".shstrtab", ".dynsym", ".dynstr", ".dynamic"].iter().any(|s| r.contains(s)) || r.len() <= 6, "text in the ELF: {r:?}"); }
}
