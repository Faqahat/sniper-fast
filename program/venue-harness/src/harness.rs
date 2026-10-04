//! The loader: a LiteSVM holding the dumped mainnet programs and one pool's snapshot (accounts + Clock), plus a funded
//! test wallet with token accounts for both of the pool's mints. Every swap runs a REAL venue instruction (built by
//! `venues::build_swap`) in a clone of that base state, so swaps are independent and deterministic.
use crate::fixture::{program_elf, Fixtures, Patch, PoolFixture};
use crate::keys::{self, *};
use crate::venues::{self, build_swap, BuildOpts, Dir, SwapIx, Venue};
use litesvm::LiteSVM;
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_keypair::Keypair;
use solana_signer::Signer;
use solana_transaction::Transaction;
use std::collections::HashMap;

pub const CU_LIMIT: u32 = 1_400_000;
pub const USER_LAMPORTS: u64 = 1_000_000_000_000; // 1,000 SOL for fees and rent of accounts the venue creates

#[derive(Clone, Debug)]
pub struct HarnessOpts {
    /// load mainnet's own SPL Token / Token-2022 / ATA dumps over LiteSVM's bundled copies (CU then matches mainnet)
    pub mainnet_spl: bool,
    /// PumpSwap: create the wallet's user_volume_accumulator up front (pump-amm `init_user_volume_accumulator`), as
    /// the engine's wallet has one. Without it the first buy creates it: +2.9k CU and 1,346,200 lamports of rent.
    pub pump_volume_accumulator: bool,
}
impl Default for HarnessOpts {
    fn default() -> Self {
        HarnessOpts { mainnet_spl: std::env::var("VENUE_HARNESS_LITESVM_SPL").map_or(true, |v| v != "1"), pump_volume_accumulator: true }
    }
}

/// The result of one real swap.
#[derive(Clone, Debug, serde::Serialize)]
pub struct SwapOutcome {
    pub ok: bool,
    pub amount_in: u64,
    /// the user's output token account delta
    pub amount_out: u64,
    /// the user's input token account debit
    pub spent: u64,
    /// CU of the venue's top-level invocation (its own "consumed" log line, CPIs included)
    pub cu_venue: Option<u64>,
    /// CU of the whole transaction (adds the compute-budget instruction)
    pub cu_tx: u64,
    pub err: Option<String>,
    #[serde(skip)]
    pub logs: Vec<String>,
    /// DLMM: the bin arrays passed
    pub dlmm_arrays: Vec<i64>,
    /// Anchor `emit_cpi!` events (inner-instruction data after the 8-byte event-CPI tag: discriminator + fields)
    #[serde(skip)]
    pub events: Vec<Vec<u8>>,
}

/// Anchor's event-CPI instruction tag (sha256("anchor:event")[..8], little-endian of EVENT_IX_TAG)
pub const EVENT_IX_TAG: [u8; 8] = [0xe4, 0x45, 0xa5, 0x2e, 0x51, 0xcb, 0x9a, 0x1d];

impl SwapOutcome {
    /// the first event whose 8-byte discriminator is `disc` (its fields follow)
    pub fn event(&self, disc: &[u8; 8]) -> Option<&[u8]> { self.events.iter().find(|e| e.starts_with(disc)).map(|e| &e[8..]) }
    fn failed(amount_in: u64, err: String) -> Self {
        SwapOutcome { ok: false, amount_in, amount_out: 0, spent: 0, cu_venue: None, cu_tx: 0, err: Some(err), logs: vec![], dlmm_arrays: vec![], events: vec![] }
    }
}

/// sha256("event:<Name>")[..8]
pub fn event_disc(name: &str) -> [u8; 8] {
    use sha2::Digest;
    sha2::Sha256::digest(format!("event:{name}").as_bytes())[..8].try_into().unwrap()
}

fn events_of(inner: &solana_message::inner_instruction::InnerInstructionsList) -> Vec<Vec<u8>> {
    inner.iter().flatten().filter(|i| i.instruction.data.starts_with(&EVENT_IX_TAG)).map(|i| i.instruction.data[8..].to_vec()).collect()
}

impl SwapOutcome {
    /// what the sizing crate calls TooLarge / ZeroOut: the swap fails or delivers nothing
    pub fn failed_or_zero(&self) -> bool { !self.ok || self.amount_out == 0 }
    pub fn venue_error(&self) -> String {
        let tail: Vec<&String> = self.logs.iter().filter(|l| l.contains("Error") || l.contains("failed") || l.contains("error")).take(3).collect();
        format!("{} {:?}", self.err.clone().unwrap_or_default(), tail)
    }
}

pub struct Harness {
    pub fixture: PoolFixture,
    pub venue: Venue,
    pub pool: Address,
    /// the snapshot as an account map (what the builders read)
    pub view: HashMap<Address, Account>,
    pub user: Keypair,
    pub tokens: venues::PoolTokens,
    pub prog0: Address,
    pub prog1: Address,
    pub opts: BuildOpts,
    base: LiteSVM,
}

impl Harness {
    pub fn new(fx: &Fixtures, pool: &Address) -> Result<Self, String> { Self::with_opts(fx, pool, &HarnessOpts::default()) }

    pub fn with_opts(fx: &Fixtures, pool: &Address, ho: &HarnessOpts) -> Result<Self, String> {
        let fixture = fx.pool(pool).ok_or_else(|| format!("no fixture for pool {pool}"))?.clone();
        Self::from_fixture(fx, fixture, ho)
    }

    /// The pool's snapshot with byte patches applied first (state mutation, DESIGN §6.3): the program and anything
    /// that reads `view` / `svm()` see the patched bytes.
    pub fn with_patches(fx: &Fixtures, pool: &Address, patches: &[Patch]) -> Result<Self, String> {
        let mut fixture = fx.pool(pool).ok_or_else(|| format!("no fixture for pool {pool}"))?.clone();
        fixture.apply(patches)?;
        Self::from_fixture(fx, fixture, &HarnessOpts::default())
    }

    pub fn from_fixture(fx: &Fixtures, fixture: PoolFixture, ho: &HarnessOpts) -> Result<Self, String> {
        let pool = &fixture.pool_key();
        let venue = fixture.venue;
        let view = fixture.account_map()?;
        let mut svm = LiteSVM::new().with_log_bytes_limit(None).with_transaction_history(0);
        // programs
        let needed: Vec<Address> = match venue {
            Venue::PumpSwap => vec![PUMPSWAP, PUMP_FEE_PROGRAM],
            v => vec![v.program()],
        };
        for (name, id) in keys::PROGRAMS {
            let spl = [TOKEN, TOKEN_2022, ATA_PROGRAM].contains(id);
            if spl && !ho.mainnet_spl { continue; }
            if !spl && !needed.contains(id) { continue; }
            let Some(e) = fx.manifest.get(id) else {
                if spl { continue; } // LiteSVM's bundled copy
                return Err(format!("program {name} {id} not in fixtures/programs/MANIFEST.json: run `cargo run --bin fetch-fixtures`"));
            };
            let elf = program_elf(e)?;
            let loader = keys::parse(&e.loader)?;
            let r = if loader == BPF_LOADER_UPGRADEABLE { svm.add_program(*id, &elf) } else { svm.add_program_with_loader(*id, &elf, loader) };
            r.map_err(|err| format!("loading {name}: {err:?}"))?;
        }
        // the snapshot
        for (k, a) in &view { svm.set_account(*k, a.clone()).map_err(|e| format!("set_account {k}: {e:?}"))?; }
        svm.set_sysvar(&fixture.clock.to_clock());
        if let Some(r) = &fixture.rent { svm.set_sysvar(&r.to_rent()); }
        // the wallet and its token accounts, created by the real ATA program
        let user = keys::test_user();
        let u = user.pubkey();
        svm.set_account(u, Account { lamports: USER_LAMPORTS, data: vec![], owner: SYSTEM, executable: false, rent_epoch: u64::MAX })
            .map_err(|e| format!("{e:?}"))?;
        let pa = view.get(pool).ok_or("pool account missing from fixture")?;
        let tokens = venues::pool_tokens(venue, &pa.data).ok_or("pool too short")?;
        let (prog0, prog1) = (venues::mint_program(&view, &tokens.t0), venues::mint_program(&view, &tokens.t1));
        let mut ixs: Vec<Instruction> = [(tokens.t0, prog0), (tokens.t1, prog1)].iter()
            .map(|(m, p)| create_ata_idempotent(&u, &u, m, p)).collect();
        if venue == Venue::PumpSwap && ho.pump_volume_accumulator { ixs.push(pump_init_user_volume_accumulator(&u)); }
        let tx = Transaction::new_signed_with_payer(&ixs, Some(&u), &[&user], svm.latest_blockhash());
        svm.send_transaction(tx).map_err(|f| format!("creating the test wallet's token accounts: {:?} {:?}", f.err, f.meta.logs))?;
        Ok(Harness { fixture, venue, pool: *pool, view, user, tokens, prog0, prog1, opts: BuildOpts::default(), base: svm })
    }

    /// the base state (snapshot + wallet), read-only
    pub fn svm(&self) -> &LiteSVM { &self.base }
    pub fn user_key(&self) -> Address { self.user.pubkey() }
    pub fn user_ata(&self, token_index: usize) -> Address {
        let (m, p) = if token_index == 0 { (self.tokens.t0, self.prog0) } else { (self.tokens.t1, self.prog1) };
        ata(&self.user.pubkey(), &m, &p)
    }
    /// the pool's vault amount on the input side of `dir` (a scale for test sizes)
    pub fn input_reserve(&self, dir: Dir) -> u64 {
        let v = if dir.zfo() { self.tokens.vault0 } else { self.tokens.vault1 };
        self.view.get(&v).and_then(|a| venues::token_amount(&a.data)).unwrap_or(0)
    }
    pub fn output_reserve(&self, dir: Dir) -> u64 { self.input_reserve(if dir.zfo() { Dir::OneForZero } else { Dir::ZeroForOne }) }

    /// a fresh copy of the base state; swaps in a session see each other's effects
    pub fn session(&self) -> Session<'_> { Session { h: self, svm: self.base.clone() } }

    /// one real swap from the snapshot state
    pub fn swap(&self, dir: Dir, amount_in: u64) -> SwapOutcome { self.session().swap_opts(dir, amount_in, &self.opts) }
    pub fn swap_opts(&self, dir: Dir, amount_in: u64, o: &BuildOpts) -> SwapOutcome { self.session().swap_opts(dir, amount_in, o) }
    /// mutate the state first (clock, pool bytes, ...), then swap
    pub fn swap_with(&self, dir: Dir, amount_in: u64, o: &BuildOpts, mutate: impl FnOnce(&mut LiteSVM)) -> SwapOutcome {
        let mut s = self.session();
        mutate(&mut s.svm);
        s.swap_opts(dir, amount_in, o)
    }

    pub fn build(&self, dir: Dir, amount_in: u64, o: &BuildOpts) -> Result<SwapIx, String> {
        build_swap(self.venue, &self.pool, &self.view, &self.user.pubkey(), dir, amount_in, o)
    }
}

pub struct Session<'a> { pub h: &'a Harness, pub svm: LiteSVM }

impl Session<'_> {
    pub fn token_amount(&self, k: &Address) -> u64 { self.svm.get_account(k).and_then(|a| venues::token_amount(&a.data)).unwrap_or(0) }

    /// set a user token account's balance (wSOL: lamports follow, as a native account requires)
    pub fn set_balance(&mut self, k: &Address, amount: u64) {
        let mut a = self.svm.get_account(k).expect("user token account exists");
        let native = a.data.len() >= 121 && u32::from_le_bytes(a.data[109..113].try_into().unwrap()) == 1;
        let old = venues::token_amount(&a.data).unwrap();
        a.data[64..72].copy_from_slice(&amount.to_le_bytes());
        if native { a.lamports = a.lamports - old + amount; }
        self.svm.set_account(*k, a).unwrap();
    }

    pub fn swap(&mut self, dir: Dir, amount_in: u64) -> SwapOutcome { let o = self.h.opts.clone(); self.swap_opts(dir, amount_in, &o) }

    pub fn swap_opts(&mut self, dir: Dir, amount_in: u64, o: &BuildOpts) -> SwapOutcome {
        let h = self.h;
        let sw = match h.build(dir, amount_in, o) {
            Ok(s) => s,
            Err(e) => return SwapOutcome::failed(amount_in, format!("build: {e}")),
        };
        // fund the input with twice the amount, so a debit above `amount_in` would show
        let want = amount_in.saturating_mul(2).max(1);
        if self.token_amount(&sw.user_in) < want { self.set_balance(&sw.user_in, want); }
        let (pre_in, pre_out) = (self.token_amount(&sw.user_in), self.token_amount(&sw.user_out));
        let user = &h.user;
        self.svm.expire_blockhash();
        let tx = Transaction::new_signed_with_payer(&[cu_limit(CU_LIMIT), sw.ix.clone()], Some(&user.pubkey()), &[user], self.svm.latest_blockhash());
        match self.svm.send_transaction(tx) {
            Ok(meta) => {
                let (post_in, post_out) = (self.token_amount(&sw.user_in), self.token_amount(&sw.user_out));
                SwapOutcome { ok: true, amount_in, amount_out: post_out.wrapping_sub(pre_out), spent: pre_in.wrapping_sub(post_in),
                    cu_venue: venue_cu(&meta.logs, &sw.ix.program_id), cu_tx: meta.compute_units_consumed, err: None, events: events_of(&meta.inner_instructions), logs: meta.logs, dlmm_arrays: sw.dlmm_arrays }
            }
            Err(f) => SwapOutcome { ok: false, amount_in, amount_out: 0, spent: 0, cu_venue: venue_cu(&f.meta.logs, &sw.ix.program_id),
                cu_tx: f.meta.compute_units_consumed, err: Some(format!("{:?}", f.err)), events: events_of(&f.meta.inner_instructions), logs: f.meta.logs, dlmm_arrays: sw.dlmm_arrays },
        }
    }
}

/// pump-amm `init_user_volume_accumulator` (payer, user, user_volume_accumulator, system, event authority, program)
pub fn pump_init_user_volume_accumulator(user: &Address) -> Instruction {
    use sha2::Digest;
    let uva = pda(&[b"user_volume_accumulator", user.as_ref()], &PUMPSWAP).0;
    Instruction { program_id: PUMPSWAP, data: sha2::Sha256::digest(b"global:init_user_volume_accumulator")[..8].to_vec(), accounts: vec![
        AccountMeta::new(*user, true), AccountMeta::new_readonly(*user, false), AccountMeta::new(uva, false),
        AccountMeta::new_readonly(SYSTEM, false), AccountMeta::new_readonly(PUMP_EVENT_AUTHORITY, false), AccountMeta::new_readonly(PUMPSWAP, false)] }
}

pub fn cu_limit(units: u32) -> Instruction {
    let mut d = vec![2u8];
    d.extend_from_slice(&units.to_le_bytes());
    Instruction { program_id: COMPUTE_BUDGET, accounts: vec![], data: d }
}

pub fn create_ata_idempotent(payer: &Address, owner: &Address, mint: &Address, token_program: &Address) -> Instruction {
    Instruction { program_id: ATA_PROGRAM, data: vec![1], accounts: vec![
        AccountMeta::new(*payer, true), AccountMeta::new(ata(owner, mint, token_program), false), AccountMeta::new_readonly(*owner, false),
        AccountMeta::new_readonly(*mint, false), AccountMeta::new_readonly(SYSTEM, false), AccountMeta::new_readonly(*token_program, false)] }
}

/// CU of `program`'s top-level invocation: its "consumed" line at invoke depth 1 (inner CPIs log their own first)
pub fn venue_cu(logs: &[String], program: &Address) -> Option<u64> {
    let p = program.to_string();
    let mut depth = 0usize;
    let mut found = None;
    for l in logs {
        let Some(rest) = l.strip_prefix("Program ") else { continue };
        let Some((id, tail)) = rest.split_once(' ') else { continue };
        if id.ends_with(':') { continue; } // "Program log:", "Program data:", "Program return:"
        if tail.starts_with("invoke [") { depth += 1; continue; }
        if let Some(x) = rest.strip_prefix(&format!("{p} consumed ")) {
            if depth == 1 { found = x.split(' ').next().and_then(|n| n.parse().ok()); }
            continue;
        }
        if tail == "success" || tail.starts_with("failed") { depth = depth.saturating_sub(1); }
    }
    found
}
