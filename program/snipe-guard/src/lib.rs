//! snipe-guard v0.2 (dip43, Builder C). PRIVATE: nothing in this comment, the names below or `README.md` reaches the chain; the
//! built ELF carries no text (checked by `program/snipe-guard-svm`: strings scan, syscall audit).
//!
//! ONE assert-only instruction the engine places in a pre-sent pump.fun buy BEFORE the pump instruction of the same transaction
//! (index 2, where the Lighthouse slot deadline sits today). It reads the state the transaction really executes on and fails the
//! whole transaction (pump never runs, the tip transfer reverts; only base + priority fee is paid) unless every requested check
//! passes:
//!
//!   DEADLINE  Clock.slot <= deadline                              (= today's Lighthouse AssertSysvarClock)
//!   CURVE     lo <= curve token balance <= hi                     (price band; optional)
//!   FLOORS    at most `max_viol` of n listed token accounts below their floor (onchain G-A: holders leaving = abort)
//!
//! and, BEFORE any of those, AUTH: account 0 must be a SIGNER whose key is one of our wallets: compiled in (`logic::COMPILED`,
//! zero extra bytes) or listed in the allowlist account (a PDA of this program, passed LAST, read only when the signer is not
//! compiled in). A closed / never-created token account counts as balance 0.
//!
//! Admin ops (allowlist): INIT (the program's upgrade authority signs; creates the PDA by a system-program CPI: the ONLY CPI in
//! the program, never on the assert path), ADD / REMOVE a wallet and ROTATE the admin (the stored admin signs).
//!
//! Errors: ProgramError::Custom(code) where `code = logic::code(Fail { kind, idx, cnt, gap })` is an opaque, invertible 32-bit
//! scramble of a 16-bit packed reason. The table is in `~/sniper/ops/guard/codes.md`; `client::decode` inverts it (host only).
//!
//! Design rules: no allocation, no logging, no panics (every index is checked; the panic handler aborts without a message),
//! no CPI on the assert path, holds no funds (the allowlist PDA holds only its own rent), bounded loops (<= 20 accounts,
//! <= 12 floors, <= 16 listed wallets). Syscalls: sol_get_clock_sysvar, sol_set_return_data (echo only),
//! sol_create_program_address (allowlist only), sol_try_find_program_address + sol_invoke_signed_c (INIT only), abort.
//!
//! Instruction data, little-endian, byte 0 = op:
//!   ASSERT  [OP_ASSERT, flags, (deadline u64)?, (lo u64, hi u64)?, (n u8, max_viol u8, n x floor u32 WHOLE tokens)?]
//!           flags: 0x01 deadline, 0x02 curve, 0x04 floors, 0x80 echo (return data on success); any other bit = refused.
//!           accounts: [wallet (signer)] [curve token account]? [n floor token accounts]? [allowlist PDA]? (the last only when the
//!           wallet is not compiled in)
//!   INIT    [OP_AL_INIT, bump, admin 32, lamports u64]   accounts: payer (s,w), list (w), upgrade authority (s), programdata, system
//!   ADD / REMOVE / ADMIN  [op, key 32]                   accounts: admin (s), list (w)
#![cfg_attr(target_os = "solana", no_std)]

pub mod logic {
    //! Pure checks: no Solana runtime; unit-tested on the host (src/tests.rs). The entrypoint is a thin shell over these.

    pub const OP_ASSERT: u8 = 0x54;
    pub const OP_AL_INIT: u8 = 0x6a;
    pub const OP_AL_ADD: u8 = 0x37;
    pub const OP_AL_REMOVE: u8 = 0x60;
    pub const OP_AL_ADMIN: u8 = 0x3a;

    pub const F_DEADLINE: u8 = 0x01;
    pub const F_CURVE: u8 = 0x02;
    pub const F_FLOORS: u8 = 0x04;
    pub const F_ECHO: u8 = 0x80;
    pub const F_ALL: u8 = F_DEADLINE | F_CURVE | F_FLOORS | F_ECHO;

    /// the most floor accounts one instruction may list (a 1,232-byte try fits about 8 next to the buy)
    pub const MAX_FLOORS: usize = 12;
    /// the most accounts the program parses (wallet + curve + 12 floors + allowlist = 15)
    pub const MAX_ACCOUNTS: usize = 20;
    /// floors are in whole tokens (pump tokens have 6 decimals)
    pub const UNIT: u64 = 1_000_000;

    /// our wallets, raw keys (AMS EgxfYgEb…, FRA 2g7rYv7y…, FRZ FRZh63L6…; pinned by the host test `compiled_allowlist_is_ours`)
    pub const COMPILED: [[u8; 32]; 3] = [
        [0xcb, 0x64, 0x85, 0x91, 0x40, 0xb2, 0x4d, 0x3e, 0x1f, 0xfa, 0xca, 0x5d, 0x10, 0xd4, 0x6f, 0x30, 0x77, 0x13, 0x42, 0x19, 0x8b, 0x25, 0x39, 0x49, 0x53, 0x04, 0x48, 0x7c, 0xb1, 0x3b, 0xf5, 0x4e],
        [0x18, 0xe1, 0x16, 0xb3, 0xab, 0x2d, 0xe3, 0x75, 0x41, 0x7e, 0xb5, 0xf6, 0x60, 0x35, 0xfa, 0xd6, 0xa9, 0xcd, 0x6f, 0x26, 0x35, 0x00, 0xef, 0x8f, 0x12, 0x64, 0xdd, 0xe3, 0x94, 0xfd, 0xe7, 0xdb],
        [0xd6, 0x4e, 0x85, 0x38, 0x65, 0x15, 0xb3, 0xe5, 0xfe, 0x13, 0x5c, 0x0c, 0xdc, 0xbb, 0x39, 0x05, 0xf4, 0x10, 0x64, 0x57, 0x82, 0xd5, 0xd6, 0xc2, 0xa9, 0x36, 0x97, 0x33, 0xbb, 0x79, 0x7e, 0x13],
    ];
    /// the allowlist PDA's seed (raw bytes, no text): address = create_program_address([AL_SEED, [bump]], program id)
    pub const AL_SEED: [u8; 8] = [0xce, 0xb5, 0xc3, 0xbb, 0x6e, 0x5a, 0x49, 0x90];
    /// the allowlist holds at most this many extra wallets
    pub const AL_MAX: usize = 16;
    /// allowlist account data: admin (32) | bump (1) | n (1) | AL_MAX x key (32)
    pub const AL_LEN: usize = 34 + 32 * AL_MAX;

    /// BPFLoaderUpgradeab1e11111111111111111111111
    pub const LOADER_V3: [u8; 32] = [0x02, 0xa8, 0xf6, 0x91, 0x4e, 0x88, 0xa1, 0xb0, 0xe2, 0x10, 0x15, 0x3e, 0xf7, 0x63, 0xae, 0x2b, 0x00, 0xc2, 0xb9, 0x3d, 0x16, 0xc1, 0x24, 0xd2, 0xc0, 0x53, 0x7a, 0x10, 0x04, 0x80, 0x00, 0x00];
    /// TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
    pub const TOKEN: [u8; 32] = [0x06, 0xdd, 0xf6, 0xe1, 0xd7, 0x65, 0xa1, 0x93, 0xd9, 0xcb, 0xe1, 0x46, 0xce, 0xeb, 0x79, 0xac, 0x1c, 0xb4, 0x85, 0xed, 0x5f, 0x5b, 0x37, 0x91, 0x3a, 0x8c, 0xf5, 0x85, 0x7e, 0xff, 0x00, 0xa9];
    /// TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb
    pub const TOKEN_2022: [u8; 32] = [0x06, 0xdd, 0xf6, 0xe1, 0xee, 0x75, 0x8f, 0xde, 0x18, 0x42, 0x5d, 0xbc, 0xe4, 0x6c, 0xcd, 0xda, 0xb6, 0x1a, 0xfc, 0x4d, 0x83, 0xb9, 0x0d, 0x27, 0xfe, 0xbd, 0xf9, 0x28, 0xd8, 0xa1, 0x8b, 0xfc];
    /// 11111111111111111111111111111111
    pub const SYSTEM: [u8; 32] = [0u8; 32];

    // ---- failure kinds (the private table: ops/guard/codes.md) ----
    pub const K_AUTH: u8 = 1;
    pub const K_DATA: u8 = 2;
    pub const K_ACCTS: u8 = 3;
    pub const K_DEADLINE: u8 = 4;
    pub const K_CURVE_HIGH: u8 = 5;
    pub const K_CURVE_DEEP: u8 = 6;
    pub const K_FLOORS: u8 = 7;
    pub const K_ADMIN: u8 = 8;
    // AUTH sub-reasons (idx)
    pub const A_NO_ACCOUNTS: u8 = 1;
    pub const A_NOT_SIGNER: u8 = 2;
    pub const A_NO_LIST: u8 = 3;
    pub const A_LIST_OWNER: u8 = 4;
    pub const A_LIST_LEN: u8 = 5;
    pub const A_LIST_ADDR: u8 = 6;
    pub const A_NOT_LISTED: u8 = 7;
    // DATA sub-reasons
    pub const D_OP: u8 = 1;
    pub const D_FLAGS: u8 = 2;
    pub const D_SHORT: u8 = 3;
    pub const D_N: u8 = 4;
    pub const D_BAND: u8 = 5;
    pub const D_TRAILING: u8 = 6;
    pub const D_VIOL: u8 = 7;
    // ACCTS sub-reasons
    pub const X_COUNT: u8 = 1;
    pub const X_MANY: u8 = 2;
    pub const X_CLOCK: u8 = 3;
    pub const X_DUP: u8 = 4;
    // ADMIN sub-reasons
    pub const M_COUNT: u8 = 1;
    pub const M_SIGNER: u8 = 2;
    pub const M_PROGDATA: u8 = 3;
    pub const M_NOT_AUTHORITY: u8 = 4;
    pub const M_LIST_ADDR: u8 = 5;
    pub const M_LIST_STATE: u8 = 6;
    pub const M_NOT_ADMIN: u8 = 7;
    pub const M_FULL: u8 = 8;
    pub const M_PRESENT: u8 = 9;
    pub const M_ABSENT: u8 = 10;
    pub const M_ZERO: u8 = 11;
    pub const M_CPI: u8 = 12;
    pub const M_DATA: u8 = 13;
    pub const M_SYSTEM: u8 = 14;

    /// why an instruction failed: kind (1..=8), idx (sub-reason, or the failing holder's index), cnt (holders below their floor),
    /// gap (a coarse bucket of how far: slots late, % beyond the band, % of the floor still held)
    #[derive(Clone, Copy, PartialEq, Eq)]
    #[cfg_attr(not(target_os = "solana"), derive(Debug))]
    pub struct Fail { pub kind: u8, pub idx: u8, pub cnt: u8, pub gap: u8 }
    impl Fail {
        #[inline(always)]
        pub const fn new(kind: u8, idx: u8) -> Fail { Fail { kind, idx, cnt: 0, gap: 0 } }
        /// the 16-bit packed reason
        #[inline(always)]
        pub const fn raw(self) -> u32 {
            (self.kind as u32 & 15) | (self.idx as u32 & 15) << 4 | (self.cnt as u32 & 15) << 8 | (self.gap as u32 & 15) << 12
        }
    }
    // the scramble (private): code = ((raw ^ K1) * M + K2) mod 2^32, M odd => invertible
    pub(crate) const K1: u32 = 0x1a42_8a30;
    pub(crate) const M: u32 = 0x6bf2_1113;
    pub(crate) const K2: u32 = 0x3de2_c778;
    /// the custom error code of a failure (never 0: host test `codes_roundtrip`)
    #[inline(always)]
    pub const fn code(f: Fail) -> u32 { (f.raw() ^ K1).wrapping_mul(M).wrapping_add(K2) }

    /// slots late -> bucket 1..=7 (1, 2, 3-4, 5-8, 9-16, 17-64, >64)
    pub fn late_bucket(late: u64) -> u8 {
        match late { 0 => 0, 1 => 1, 2 => 2, 3..=4 => 3, 5..=8 => 4, 9..=16 => 5, 17..=64 => 6, _ => 7 }
    }
    /// how far beyond a band edge, |diff| / base in basis points -> 1..=7 (<0.5%, <1%, <2%, <5%, <10%, <20%, >=20%)
    pub fn bps_bucket(diff: u64, base: u64) -> u8 {
        let b = if base == 0 { u64::MAX } else { diff.saturating_mul(10_000) / base };
        match b { 0..=49 => 1, 50..=99 => 2, 100..=199 => 3, 200..=499 => 4, 500..=999 => 5, 1000..=1999 => 6, _ => 7 }
    }
    /// percent of its floor a holder BELOW it still holds (pct < 100) -> 0 (nothing: sold out / closed), 1 (<25%), 2 (<50%),
    /// 3 (<75%), 4 (<90%), 5 (90..100%)
    pub fn short_bucket(pct: u64) -> u8 {
        match pct { 0 => 0, 1..=24 => 1, 25..=49 => 2, 50..=74 => 3, 75..=89 => 4, _ => 5 }
    }
    /// the tightest margin of the holders AT or above their floor (pct >= 100) -> 1 (<110%), 2 (<125%), 3 (<150%), 4 (<200%), 5
    pub fn margin_bucket(pct: u64) -> u8 {
        match pct { 0..=109 => 1, 110..=124 => 2, 125..=149 => 3, 150..=199 => 4, _ => 5 }
    }

    #[inline(always)]
    pub fn u64_at(d: &[u8], o: usize) -> Option<u64> { Some(u64::from_le_bytes(d.get(o..o.checked_add(8)?)?.try_into().ok()?)) }
    #[inline(always)]
    pub fn u32_at(d: &[u8], o: usize) -> Option<u32> { Some(u32::from_le_bytes(d.get(o..o.checked_add(4)?)?.try_into().ok()?)) }
    #[inline(always)]
    pub fn key_at(d: &[u8], o: usize) -> Option<[u8; 32]> { d.get(o..o.checked_add(32)?)?.try_into().ok() }

    /// An SPL Token / Token-2022 account's amount: u64 at offset 64. `is_token` = owned by one of the two token programs. Anything
    /// else (closed: system-owned, no data; never created; too short; uninitialized state byte 108) is 0.
    #[inline(always)]
    pub fn token_amount(is_token: bool, data: &[u8]) -> u64 {
        if !is_token || data.get(108).copied().unwrap_or(0) == 0 { return 0; }
        u64_at(data, 64).unwrap_or(0)
    }

    #[inline(always)]
    pub fn is_compiled(key: &[u8; 32]) -> bool { COMPILED.iter().any(|k| k == key) }

    /// the allowlist's wallets (n clamped to AL_MAX) contain `key`
    pub fn al_contains(data: &[u8], key: &[u8; 32]) -> bool {
        let n = (data.get(33).copied().unwrap_or(0) as usize).min(AL_MAX);
        (0..n).any(|i| key_at(data, 34 + 32 * i).is_some_and(|k| &k == key))
    }

    /// AUTH, the first check of ASSERT: account 0 signs and is ours. `list` (called only when the signer is not compiled in) reads
    /// the LAST account as the allowlist: Ok(contains) or Err(sub-reason). -> the number of balance accounts (between the wallet
    /// and the allowlist)
    pub fn auth(n_accounts: usize, signer0: bool, key0: &[u8; 32], list: impl FnOnce() -> Result<bool, u8>) -> Result<usize, Fail> {
        if n_accounts == 0 { return Err(Fail::new(K_AUTH, A_NO_ACCOUNTS)); }
        if !signer0 { return Err(Fail::new(K_AUTH, A_NOT_SIGNER)); }
        if is_compiled(key0) { return Ok(n_accounts - 1); }
        if n_accounts < 2 { return Err(Fail::new(K_AUTH, A_NO_LIST)); }
        match list() { Ok(true) => Ok(n_accounts - 2), Ok(false) => Err(Fail::new(K_AUTH, A_NOT_LISTED)), Err(s) => Err(Fail::new(K_AUTH, s)) }
    }

    /// the allowlist account as AUTH reads it: owned by the program, the right size, at the PDA of its stored bump (`addr_ok`)
    pub fn list_check(owner_ok: bool, data: &[u8], addr_ok: impl FnOnce(u8) -> bool, key0: &[u8; 32]) -> Result<bool, u8> {
        if !owner_ok { return Err(A_LIST_OWNER); }
        if data.len() != AL_LEN { return Err(A_LIST_LEN); }
        if !addr_ok(data.get(32).copied().unwrap_or(0)) { return Err(A_LIST_ADDR); }
        Ok(al_contains(data, key0))
    }

    /// The ASSERT checks after AUTH. `data` = the whole instruction data, `slot` = Clock.slot (read only with DEADLINE),
    /// `amount(i)` = the token amount of balance account i (None past the last), `n_bal` = how many balance accounts the
    /// instruction carries. Checks run in flag order and stop at the first failure. -> the echo bytes (return data with F_ECHO):
    /// [flags, n_floors | violators << 4, tightest margin bucket of the holders at or above their floor (0: none)]
    pub fn assert_checks(data: &[u8], slot: impl FnOnce() -> Option<u64>, amount: impl Fn(usize) -> Option<u64>, n_bal: usize) -> Result<[u8; 3], Fail> {
        if data.first() != Some(&OP_ASSERT) { return Err(Fail::new(K_DATA, D_OP)); }
        let flags = *data.get(1).ok_or(Fail::new(K_DATA, D_SHORT))?;
        if flags & !F_ALL != 0 || flags & !F_ECHO == 0 { return Err(Fail::new(K_DATA, D_FLAGS)); }
        let (mut o, mut a) = (2usize, 0usize);
        let mut echo = [flags & !F_ECHO, 0u8, 0u8];
        if flags & F_DEADLINE != 0 {
            let dl = u64_at(data, o).ok_or(Fail::new(K_DATA, D_SHORT))?;
            o += 8;
            let now = slot().ok_or(Fail::new(K_ACCTS, X_CLOCK))?;
            if now > dl { return Err(Fail { kind: K_DEADLINE, idx: 0, cnt: 0, gap: late_bucket(now - dl) }); }
        }
        if flags & F_CURVE != 0 {
            let lo = u64_at(data, o).ok_or(Fail::new(K_DATA, D_SHORT))?;
            let hi = u64_at(data, o + 8).ok_or(Fail::new(K_DATA, D_SHORT))?;
            o += 16;
            if lo > hi { return Err(Fail::new(K_DATA, D_BAND)); }
            let t = amount(a).ok_or(Fail::new(K_ACCTS, X_COUNT))?;
            a += 1;
            if t < lo { return Err(Fail { kind: K_CURVE_HIGH, idx: 0, cnt: 0, gap: bps_bucket(lo - t, lo) }); }
            if t > hi { return Err(Fail { kind: K_CURVE_DEEP, idx: 0, cnt: 0, gap: bps_bucket(t - hi, hi) }); }
        }
        if flags & F_FLOORS != 0 {
            let n = *data.get(o).ok_or(Fail::new(K_DATA, D_SHORT))? as usize;
            let max_viol = *data.get(o + 1).ok_or(Fail::new(K_DATA, D_SHORT))? as usize;
            o += 2;
            if n == 0 || n > MAX_FLOORS { return Err(Fail::new(K_DATA, D_N)); }
            if max_viol >= n { return Err(Fail::new(K_DATA, D_VIOL)); }
            if data.len() < o + 4 * n { return Err(Fail::new(K_DATA, D_SHORT)); }
            let (mut viol, mut worst, mut worst_pct, mut margin) = (0usize, 0usize, u64::MAX, u64::MAX);
            for k in 0..n {
                let floor = (u32_at(data, o + 4 * k).ok_or(Fail::new(K_DATA, D_SHORT))? as u64).saturating_mul(UNIT);
                let amt = amount(a + k).ok_or(Fail::new(K_ACCTS, X_COUNT))?;
                // percent of the floor held (a floor of 0 always holds)
                let pct = if floor == 0 { u64::MAX } else { amt.saturating_mul(100) / floor };
                if amt < floor {
                    viol += 1;
                    if pct < worst_pct { worst_pct = pct; worst = k; }
                } else if pct < margin { margin = pct; }
            }
            o += 4 * n;
            a += n;
            if viol > max_viol {
                return Err(Fail { kind: K_FLOORS, idx: worst as u8, cnt: viol.min(15) as u8, gap: short_bucket(worst_pct) });
            }
            echo[1] = (n as u8 & 15) | ((viol as u8 & 15) << 4);
            echo[2] = if margin == u64::MAX { 0 } else { margin_bucket(margin) };
        }
        if o != data.len() { return Err(Fail::new(K_DATA, D_TRAILING)); }
        if a != n_bal { return Err(Fail::new(K_ACCTS, X_COUNT)); }
        Ok(echo)
    }

    /// INIT's data on a freshly allocated list (all zero): admin, bump, n = 0
    pub fn al_init(list: &mut [u8], admin: &[u8; 32], bump: u8) -> Result<(), u8> {
        if list.len() != AL_LEN || list.iter().any(|b| *b != 0) { return Err(M_LIST_STATE); }
        if admin.iter().all(|b| *b == 0) { return Err(M_ZERO); }
        for (d, s) in list.iter_mut().zip(admin.iter()) { *d = *s; }
        if let Some(b) = list.get_mut(32) { *b = bump; }
        Ok(())
    }
    /// ADD / REMOVE / ADMIN on the list's data, after the entrypoint checked owner, size and address. `signer` = the admin account
    pub fn al_edit(list: &mut [u8], op: u8, signer: &[u8; 32], key: &[u8; 32]) -> Result<(), u8> {
        if list.len() != AL_LEN { return Err(M_LIST_STATE); }
        if key_at(list, 0).as_ref() != Some(signer) { return Err(M_NOT_ADMIN); }
        if key.iter().all(|b| *b == 0) { return Err(M_ZERO); }
        let n = (list.get(33).copied().unwrap_or(0) as usize).min(AL_MAX);
        let pos = (0..n).find(|i| key_at(list, 34 + 32 * i).as_ref() == Some(key));
        match op {
            OP_AL_ADD => {
                if pos.is_some() { return Err(M_PRESENT); }
                if n >= AL_MAX { return Err(M_FULL); }
                let at = 34 + 32 * n;
                for (d, s) in list.iter_mut().skip(at).zip(key.iter()) { *d = *s; }
                if let Some(b) = list.get_mut(33) { *b = (n + 1) as u8; }
            }
            OP_AL_REMOVE => {
                let i = pos.ok_or(M_ABSENT)?;
                // the last one moves into the hole; the last slot is zeroed
                let last = key_at(list, 34 + 32 * (n - 1)).ok_or(M_LIST_STATE)?;
                for (d, s) in list.iter_mut().skip(34 + 32 * i).zip(last.iter()) { *d = *s; }
                for d in list.iter_mut().skip(34 + 32 * (n - 1)).take(32) { *d = 0; }
                if let Some(b) = list.get_mut(33) { *b = (n - 1) as u8; }
            }
            OP_AL_ADMIN => { for (d, s) in list.iter_mut().zip(key.iter()) { *d = *s; } }
            _ => return Err(M_DATA),
        }
        Ok(())
    }
    /// the upgrade authority stored in a loader-v3 ProgramData account's data (tag 3, slot, Some(authority)); None: not one / no authority
    pub fn programdata_authority(d: &[u8]) -> Option<[u8; 32]> {
        if d.get(0..4)? != [3u8, 0, 0, 0] || *d.get(12)? != 1 { return None; }
        key_at(d, 13)
    }
}

/// The engine's / the ops tool's side (HOST ONLY: not compiled into the .so): the instruction encoder and the private decoder.
#[cfg(not(target_os = "solana"))]
pub mod client {
    use super::logic::*;

    /// one guard instruction's checks
    #[derive(Clone, Debug, Default, PartialEq, Eq)]
    pub struct Guard {
        pub deadline: Option<u64>,
        /// (curve token account, tok_min, tok_max)
        pub curve: Option<([u8; 32], u64, u64)>,
        /// (token account, floor in WHOLE tokens); at most `max_viol` may be below
        pub floors: Vec<([u8; 32], u32)>,
        pub max_viol: u8,
        /// return data on success (3 bytes; the try's later ATA create overwrites it: for simulation / the smoke test)
        pub echo: bool,
    }
    /// (key, signer, writable)
    pub type Meta = ([u8; 32], bool, bool);

    impl Guard {
        pub fn flags(&self) -> u8 {
            let mut f = 0u8;
            if self.deadline.is_some() { f |= F_DEADLINE; }
            if self.curve.is_some() { f |= F_CURVE; }
            if !self.floors.is_empty() { f |= F_FLOORS; }
            if self.echo { f |= F_ECHO; }
            f
        }
        pub fn data(&self) -> Vec<u8> {
            let mut d = Vec::with_capacity(2 + 8 + 16 + 2 + 4 * self.floors.len());
            d.push(OP_ASSERT);
            d.push(self.flags());
            if let Some(dl) = self.deadline { d.extend(dl.to_le_bytes()); }
            if let Some((_, lo, hi)) = self.curve { d.extend(lo.to_le_bytes()); d.extend(hi.to_le_bytes()); }
            if !self.floors.is_empty() {
                d.push(self.floors.len() as u8);
                d.push(self.max_viol);
                for (_, f) in &self.floors { d.extend(f.to_le_bytes()); }
            }
            d
        }
        /// the instruction's accounts: the wallet (signer; it is the fee payer of a try, so no new key), the curve's token account,
        /// the floor accounts, and the allowlist PDA only for a wallet that is not compiled in
        pub fn accounts(&self, wallet: [u8; 32], allowlist: Option<[u8; 32]>) -> Vec<Meta> {
            let mut a: Vec<Meta> = vec![(wallet, true, false)];
            if let Some((k, _, _)) = self.curve { a.push((k, false, false)); }
            for (k, _) in &self.floors { a.push((*k, false, false)); }
            if let Some(l) = allowlist { if !is_compiled(&wallet) { a.push((l, false, false)); } }
            a
        }
    }

    /// INIT's data
    pub fn al_init_data(bump: u8, admin: [u8; 32], lamports: u64) -> Vec<u8> {
        let mut d = vec![OP_AL_INIT, bump];
        d.extend(admin);
        d.extend(lamports.to_le_bytes());
        d
    }
    /// ADD / REMOVE / ADMIN data
    pub fn al_edit_data(op: u8, key: [u8; 32]) -> Vec<u8> { let mut d = vec![op]; d.extend(key); d }
    /// the allowlist's (admin, wallets) from its account data
    pub fn al_read(d: &[u8]) -> Option<([u8; 32], u8, Vec<[u8; 32]>)> {
        if d.len() != AL_LEN { return None; }
        let n = (d[33] as usize).min(AL_MAX);
        Some((key_at(d, 0)?, d[32], (0..n).filter_map(|i| key_at(d, 34 + 32 * i)).collect()))
    }

    const fn m_inv() -> u32 {
        // Newton: x <- x (2 - M x) doubles the correct low bits; M is its own inverse mod 8
        let mut x = M;
        let mut i = 0;
        while i < 5 { x = x.wrapping_mul(2u32.wrapping_sub(M.wrapping_mul(x))); i += 1; }
        x
    }
    const M_INV: u32 = m_inv();

    /// the custom error code -> the failure (None: not one of ours: log it raw)
    pub fn decode(code: u32) -> Option<Fail> {
        let raw = code.wrapping_sub(K2).wrapping_mul(M_INV) ^ K1;
        if raw > 0xFFFF { return None; }
        let f = Fail { kind: (raw & 15) as u8, idx: ((raw >> 4) & 15) as u8, cnt: ((raw >> 8) & 15) as u8, gap: ((raw >> 12) & 15) as u8 };
        if !(K_AUTH..=K_ADMIN).contains(&f.kind) { return None; }
        Some(f)
    }

    pub fn kind_name(k: u8) -> &'static str {
        match k { K_AUTH => "auth", K_DATA => "data", K_ACCTS => "accounts", K_DEADLINE => "deadline", K_CURVE_HIGH => "curve_high",
            K_CURVE_DEEP => "curve_deep", K_FLOORS => "floors", K_ADMIN => "admin", _ => "?" }
    }
    /// the sub-reason of auth / data / accounts / admin failures (None for the checks, whose idx is a holder index)
    pub fn sub_name(kind: u8, idx: u8) -> Option<&'static str> {
        Some(match (kind, idx) {
            (K_AUTH, A_NO_ACCOUNTS) => "no_accounts", (K_AUTH, A_NOT_SIGNER) => "not_signer", (K_AUTH, A_NO_LIST) => "not_ours_no_list",
            (K_AUTH, A_LIST_OWNER) => "list_owner", (K_AUTH, A_LIST_LEN) => "list_len", (K_AUTH, A_LIST_ADDR) => "list_addr", (K_AUTH, A_NOT_LISTED) => "not_listed",
            (K_DATA, D_OP) => "op", (K_DATA, D_FLAGS) => "flags", (K_DATA, D_SHORT) => "short", (K_DATA, D_N) => "n", (K_DATA, D_BAND) => "band",
            (K_DATA, D_TRAILING) => "trailing", (K_DATA, D_VIOL) => "max_viol",
            (K_ACCTS, X_COUNT) => "count", (K_ACCTS, X_MANY) => "too_many", (K_ACCTS, X_CLOCK) => "clock", (K_ACCTS, X_DUP) => "dup",
            (K_ADMIN, M_COUNT) => "count", (K_ADMIN, M_SIGNER) => "signer", (K_ADMIN, M_PROGDATA) => "programdata", (K_ADMIN, M_NOT_AUTHORITY) => "not_authority",
            (K_ADMIN, M_LIST_ADDR) => "list_addr", (K_ADMIN, M_LIST_STATE) => "list_state", (K_ADMIN, M_NOT_ADMIN) => "not_admin", (K_ADMIN, M_FULL) => "full",
            (K_ADMIN, M_PRESENT) => "present", (K_ADMIN, M_ABSENT) => "absent", (K_ADMIN, M_ZERO) => "zero_key", (K_ADMIN, M_CPI) => "cpi",
            (K_ADMIN, M_DATA) => "data", (K_ADMIN, M_SYSTEM) => "system",
            _ => return None,
        })
    }
    /// the gap bucket in words
    pub fn gap_text(kind: u8, gap: u8) -> &'static str {
        match kind {
            K_DEADLINE => ["0", "1 slot", "2 slots", "3-4 slots", "5-8 slots", "9-16 slots", "17-64 slots", ">64 slots"].get(gap as usize).copied().unwrap_or("?"),
            K_CURVE_HIGH | K_CURVE_DEEP => ["0", "<0.5%", "0.5-1%", "1-2%", "2-5%", "5-10%", "10-20%", ">=20%"].get(gap as usize).copied().unwrap_or("?"),
            K_FLOORS => ["0% held (sold out / closed)", "<25% of floor", "25-50%", "50-75%", "75-90%", "90-100%"].get(gap as usize).copied().unwrap_or("?"),
            _ => "",
        }
    }
}

#[cfg(test)]
mod tests;

// ---------------------------------------------------------------------------------------------------------------------------------
// The on-chain entrypoint (SBF only): a raw input parser (no solana-program, no AccountInfo / RefCell, no allocation).
// ---------------------------------------------------------------------------------------------------------------------------------
#[cfg(target_os = "solana")]
mod entry {
    use super::logic::*;
    use solana_define_syscall::definitions as sys;

    #[panic_handler]
    fn on_panic(_: &core::panic::PanicInfo) -> ! { unsafe { sys::abort() } }

    /// one account of the serialized input (pointers into the input region)
    #[derive(Clone, Copy)]
    struct Av { key: *const [u8; 32], owner: *const [u8; 32], lamports: *mut u64, len: *const u64, data: *mut u8, re: *const u64, signer: bool, writable: bool, exec: bool }
    const NONE: Av = Av { key: core::ptr::null(), owner: core::ptr::null(), lamports: core::ptr::null_mut(), len: core::ptr::null(), data: core::ptr::null_mut(),
        re: core::ptr::null(), signer: false, writable: false, exec: false };
    impl Av {
        #[inline(always)] fn key(&self) -> &[u8; 32] { unsafe { &*self.key } }
        #[inline(always)] fn owner(&self) -> &[u8; 32] { unsafe { &*self.owner } }
        /// the data length NOW (the runtime rewrites it after a CPI)
        #[inline(always)] fn len(&self) -> usize { unsafe { *self.len as usize } }
        #[inline(always)] fn data(&self) -> &[u8] { unsafe { core::slice::from_raw_parts(self.data, self.len()) } }
        #[inline(always)] fn data_mut(&self) -> &mut [u8] { unsafe { core::slice::from_raw_parts_mut(self.data, self.len()) } }
        #[inline(always)] fn amount(&self) -> u64 { let o = self.owner(); token_amount(*o == TOKEN || *o == TOKEN_2022, self.data()) }
    }

    /// the serialized-input layout (agave aligned serialization, loader v3)
    const MAX_PERMITTED_DATA_INCREASE: usize = 10 * 1024;

    #[no_mangle]
    pub unsafe extern "C" fn entrypoint(input: *mut u8) -> u64 {
        match run(input) { Ok(()) => 0, Err(f) => code(f) as u64 }
    }

    unsafe fn run(input: *mut u8) -> Result<(), Fail> {
        let n = *(input as *const u64) as usize;
        if n > MAX_ACCOUNTS { return Err(Fail::new(K_ACCTS, X_MANY)); }
        let mut av = [NONE; MAX_ACCOUNTS];
        let mut p = 8usize;
        let mut i = 0usize;
        while i < n {
            let dup = *input.add(p) as usize;
            let a = if dup != 0xff {
                // a duplicate of an earlier account
                if dup >= i { return Err(Fail::new(K_ACCTS, X_DUP)); }
                p += 8;
                *av.get(dup).ok_or(Fail::new(K_ACCTS, X_DUP))?
            } else {
                let dl = *(input.add(p + 80) as *const u64) as usize;
                let mut a = Av {
                    signer: *input.add(p + 1) != 0, writable: *input.add(p + 2) != 0, exec: *input.add(p + 3) != 0,
                    key: input.add(p + 8) as *const [u8; 32], owner: input.add(p + 40) as *const [u8; 32], lamports: input.add(p + 72) as *mut u64,
                    len: input.add(p + 80) as *const u64, data: input.add(p + 88), re: core::ptr::null(),
                };
                p = (p + 88 + dl + MAX_PERMITTED_DATA_INCREASE + 7) & !7;
                a.re = input.add(p) as *const u64;
                p += 8;
                a
            };
            *av.get_mut(i).ok_or(Fail::new(K_ACCTS, X_MANY))? = a;
            i += 1;
        }
        let ilen = *(input.add(p) as *const u64) as usize;
        let ix = core::slice::from_raw_parts(input.add(p + 8) as *const u8, ilen);
        let pid = &*(input.add(p + 8 + ilen) as *const [u8; 32]);
        let acc = av.get(..n).ok_or(Fail::new(K_ACCTS, X_MANY))?;
        match ix.first().copied() {
            Some(OP_ASSERT) => assert_ix(acc, ix, pid),
            Some(OP_AL_INIT) => init_ix(acc, ix, pid),
            Some(OP_AL_ADD) | Some(OP_AL_REMOVE) | Some(OP_AL_ADMIN) => edit_ix(acc, ix, pid),
            _ => Err(Fail::new(K_DATA, D_OP)),
        }
    }

    /// create_program_address([seed, [bump]], program) == key
    fn pda_is(key: &[u8; 32], bump: u8, pid: &[u8; 32]) -> bool {
        let b = [bump];
        let seeds: [[u64; 2]; 2] = [[AL_SEED.as_ptr() as u64, AL_SEED.len() as u64], [b.as_ptr() as u64, 1]];
        let mut out = [0u8; 32];
        let rc = unsafe { sys::sol_create_program_address(seeds.as_ptr() as *const u8, 2, pid.as_ptr(), out.as_mut_ptr()) };
        rc == 0 && out == *key
    }

    fn assert_ix(acc: &[Av], ix: &[u8], pid: &[u8; 32]) -> Result<(), Fail> {
        let w = acc.first().copied().unwrap_or(NONE);
        let signer0 = acc.first().is_some_and(|a| a.signer);
        let key0 = if acc.is_empty() { [0u8; 32] } else { *w.key() };
        let n_bal = auth(acc.len(), signer0, &key0, || {
            let l = acc.last().copied().unwrap_or(NONE);
            list_check(l.owner() == pid, l.data(), |bump| pda_is(l.key(), bump, pid), &key0)
        })?;
        let echo = assert_checks(ix, clock_slot, |i| if i < n_bal { acc.get(1 + i).map(|a| a.amount()) } else { None }, n_bal)?;
        if ix.get(1).is_some_and(|f| f & F_ECHO != 0) { unsafe { sys::sol_set_return_data(echo.as_ptr(), echo.len() as u64) }; }
        Ok(())
    }

    /// Clock.slot via sol_get_clock_sysvar (no account needed; the raw Clock is 5 x u64, slot first)
    fn clock_slot() -> Option<u64> {
        let mut raw = [0u64; 5];
        #[allow(deprecated)]
        let rc = unsafe { sys::sol_get_clock_sysvar(raw.as_mut_ptr() as *mut u8) };
        if rc != 0 { return None; }
        Some(raw[0])
    }

    fn adm(s: u8) -> Fail { Fail::new(K_ADMIN, s) }

    // ---- the system-program CPI (INIT only), C ABI ----
    #[repr(C)] struct CMeta { key: *const [u8; 32], w: bool, s: bool }
    #[repr(C)] struct CIx { pid: *const [u8; 32], accts: *const CMeta, n: u64, data: *const u8, dlen: u64 }
    #[repr(C)] struct CInfo { key: *const [u8; 32], lamports: *mut u64, data_len: u64, data: *mut u8, owner: *const [u8; 32], rent_epoch: u64, s: bool, w: bool, exec: bool }
    fn info(a: &Av) -> CInfo {
        CInfo { key: a.key, lamports: a.lamports, data_len: a.len() as u64, data: a.data, owner: a.owner, rent_epoch: unsafe { *a.re }, s: a.signer, w: a.writable, exec: a.exec }
    }
    /// one system instruction (`metas` = (account, writable, signer)), signed by the list PDA when `pda_bump` is given
    fn sys_call(sys_acc: &Av, metas: &[(&Av, bool, bool)], data: &[u8], infos: &[&Av], pda_bump: Option<u8>) -> Result<(), Fail> {
        let mut m: [CMeta; 2] = [CMeta { key: core::ptr::null(), w: false, s: false }, CMeta { key: core::ptr::null(), w: false, s: false }];
        let nm = metas.len().min(2);
        for (d, (a, w, s)) in m.iter_mut().zip(metas.iter()) { *d = CMeta { key: a.key, w: *w, s: *s }; }
        let cix = CIx { pid: sys_acc.key, accts: m.as_ptr(), n: nm as u64, data: data.as_ptr(), dlen: data.len() as u64 };
        let mut ci: [CInfo; 3] = [info(sys_acc), info(sys_acc), info(sys_acc)];
        let ni = infos.len().min(3);
        for (d, a) in ci.iter_mut().zip(infos.iter()) { *d = info(a); }
        let b = [pda_bump.unwrap_or(0)];
        let seed: [[u64; 2]; 2] = [[AL_SEED.as_ptr() as u64, AL_SEED.len() as u64], [b.as_ptr() as u64, 1]];
        let seeds: [[u64; 2]; 1] = [[seed.as_ptr() as u64, 2]];
        let rc = unsafe {
            sys::sol_invoke_signed_c(&cix as *const CIx as *const u8, ci.as_ptr() as *const u8, ni as u64, seeds.as_ptr() as *const u8, if pda_bump.is_some() { 1 } else { 0 })
        };
        if rc != 0 { return Err(adm(M_CPI)); }
        Ok(())
    }

    /// INIT: [op, bump, admin 32, lamports u64]; accounts payer (s,w), list (w), upgrade authority (s), programdata, system program
    fn init_ix(acc: &[Av], ix: &[u8], pid: &[u8; 32]) -> Result<(), Fail> {
        if acc.len() != 5 { return Err(adm(M_COUNT)); }
        if ix.len() != 42 { return Err(adm(M_DATA)); }
        let (payer, list, ua, pd, sy) = match acc { [a, b, c, d, e] => (*a, *b, *c, *d, *e), _ => return Err(adm(M_COUNT)) };
        let bump = *ix.get(1).ok_or(adm(M_DATA))?;
        let admin = key_at(ix, 2).ok_or(adm(M_DATA))?;
        let lamports = u64_at(ix, 34).ok_or(adm(M_DATA))?;
        if !payer.signer || !payer.writable || !ua.signer || !list.writable { return Err(adm(M_SIGNER)); }
        if *sy.key() != SYSTEM { return Err(adm(M_SYSTEM)); }
        if admin.iter().all(|b| *b == 0) { return Err(adm(M_ZERO)); }
        // the programdata account: the loader's PDA of this program, holding the upgrade authority that signed
        if *pd.owner() != LOADER_V3 { return Err(adm(M_PROGDATA)); }
        let mut want = [0u8; 32];
        let mut pb = 0u8;
        let seeds: [[u64; 2]; 1] = [[pid.as_ptr() as u64, 32]];
        let rc = unsafe { sys::sol_try_find_program_address(seeds.as_ptr() as *const u8, 1, LOADER_V3.as_ptr(), want.as_mut_ptr(), &mut pb as *mut u8) };
        if rc != 0 || want != *pd.key() { return Err(adm(M_PROGDATA)); }
        if programdata_authority(pd.data()) != Some(*ua.key()) { return Err(adm(M_NOT_AUTHORITY)); }
        if !pda_is(list.key(), bump, pid) { return Err(adm(M_LIST_ADDR)); }
        if *list.owner() != SYSTEM || list.len() != 0 { return Err(adm(M_LIST_STATE)); }
        // fund (a pre-funded PDA only gets the rest), allocate, assign: the PDA signs the last two
        let have = unsafe { *list.lamports };
        if have < lamports {
            let mut d = [0u8; 12];
            d[0] = 2;
            for (x, y) in d.iter_mut().skip(4).zip((lamports - have).to_le_bytes().iter()) { *x = *y; }
            sys_call(&sy, &[(&payer, true, true), (&list, true, false)], &d, &[&payer, &list, &sy], None)?;
        }
        let mut d = [0u8; 12];
        d[0] = 8;
        for (x, y) in d.iter_mut().skip(4).zip((AL_LEN as u64).to_le_bytes().iter()) { *x = *y; }
        sys_call(&sy, &[(&list, true, true)], &d, &[&list, &sy], Some(bump))?;
        let mut d = [0u8; 36];
        d[0] = 1;
        for (x, y) in d.iter_mut().skip(4).zip(pid.iter()) { *x = *y; }
        sys_call(&sy, &[(&list, true, true)], &d, &[&list, &sy], Some(bump))?;
        if *list.owner() != *pid || list.len() != AL_LEN { return Err(adm(M_CPI)); }
        al_init(list.data_mut(), &admin, bump).map_err(adm)
    }

    /// ADD / REMOVE / ADMIN: [op, key 32]; accounts admin (s), list (w)
    fn edit_ix(acc: &[Av], ix: &[u8], pid: &[u8; 32]) -> Result<(), Fail> {
        let (admin, list) = match acc { [a, b] => (*a, *b), _ => return Err(adm(M_COUNT)) };
        if ix.len() != 33 { return Err(adm(M_DATA)); }
        if !admin.signer { return Err(adm(M_SIGNER)); }
        if *list.owner() != *pid || list.len() != AL_LEN || !list.writable { return Err(adm(M_LIST_STATE)); }
        if !pda_is(list.key(), list.data().get(32).copied().unwrap_or(0), pid) { return Err(adm(M_LIST_ADDR)); }
        let key = key_at(ix, 1).ok_or(adm(M_DATA))?;
        let op = ix.first().copied().unwrap_or(0);
        al_edit(list.data_mut(), op, admin.key(), &key).map_err(adm)
    }
}
