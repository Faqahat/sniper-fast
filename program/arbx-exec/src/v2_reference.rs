//! TEST-ONLY: nexus-arb-v2's parser, copied VERBATIM from program/nexus-arb-v2/src/lib.rs (lines 46-207, the
//! `logic` module up to and including `parse`). The property tests run it side by side with arbx-exec's v2 parser
//! on arbitrary input to prove "the v2 layout is accepted unchanged". Do not edit; re-copy if nexus-arb-v2 changes.
#![allow(dead_code, clippy::all)]
pub const VERSION: u8 = 0x02;
pub const MAX_LEGS: usize = 8;
/// version u8, n_legs u8, amount_in u64, min_profit u64
pub const HEADER_LEN: usize = 18;
/// per leg: n_accounts u8, amount_offset u8, data_len u16
pub const LEG_META_LEN: usize = 4;
/// NATIVE-SOL LEGS (upgrade 2026-09-30, for pump.fun's bonding curve, which pays and receives native lamports,
/// not a token account). Two flags in the top bits of the leg's n_accounts byte; the low 6 bits are the account
/// count (a transaction holds at most 64 accounts, so no real leg ever set these bits: every encoding made before
/// the upgrade parses identically).
///   NATIVE_IN:  the leg spends the authority's LAMPORTS (leg 0: `amount_in`; later: the previous leg's output,
///               which must then be a NATIVE_OUT leg).
///   NATIVE_OUT: the leg's output is measured as the authority's lamport gain (its output-account slot must be
///               the authority); the next leg, if any, must be NATIVE_IN.
/// A route with any native leg checks profit on quote tokens PLUS authority lamports across the legs, so SOL spent
/// or received natively counts exactly like wSOL. Only lamports moved inside this instruction count: the
/// transaction fee, tips and account creations outside it do not.
pub const NATIVE_IN: u8 = 0x80;
pub const NATIVE_OUT: u8 = 0x40;
pub const N_ACCOUNTS_MASK: u8 = 0x3F;
/// Optional trailer after the last leg's data: `max_payer_lamport_drop` u64 LE. Presence is decided
/// by the exact total length, which is unambiguous because every leg declares its data length:
/// total == end of leg data -> no guard (the pre-upgrade format, parsed identically);
/// total == end of leg data + 8 -> guard; anything else -> DataLengthMismatch. No tag byte: RayFork
/// routes already build to 1,223 of the 1,232-byte transaction limit.
pub const GUARD_TRAILER_LEN: usize = 8;

/// Custom error codes the chain reports. Stable: the off-chain recorder decodes these.
/// They live in their own range on purpose. The SPL token program reports small numbers
/// (Custom(1) = insufficient funds, Custom(4) = owner mismatch) and Anchor venues report 6000+.
/// A v1-style `Custom(1)` could not be told apart from a token failure inside a leg.
pub const ERR_BASE: u32 = 0x4E58_0000; // "NX"
pub const ERR_BAD_DATA: u32 = ERR_BASE + 1;
pub const ERR_PROFIT: u32 = ERR_BASE + 2;
pub const ERR_NOT_ALLOWLISTED: u32 = ERR_BASE + 3;
pub const ERR_NOT_TOKEN_ACCOUNT: u32 = ERR_BASE + 4;
/// Guarded routes only: the authority lost more lamports than `max_payer_lamport_drop` across the
/// legs, or its owner / data length changed.
pub const ERR_PAYER_GUARD: u32 = ERR_BASE + 5;
/// Guarded routes only: an authority-owned token account in a leg lost more than allowed, or its
/// owner / delegate / state / close authority changed, or it was closed.
pub const ERR_TOKEN_GUARD: u32 = ERR_BASE + 6;
/// Guarded routes only: a leg was given a signer other than the authority.
pub const ERR_FOREIGN_SIGNER: u32 = ERR_BASE + 7;
/// `LEG_ERR_BASE + i` means leg `i` (0-based) delivered nothing or its balance went down.
pub const LEG_ERR_BASE: u32 = ERR_BASE + 0x100;

/// Logged (sol_log_data) immediately before each leg is invoked, followed by the leg index.
/// A venue failure (DLMM 6003, Whirlpool 6036, CPMM 6005) aborts the whole transaction inside the
/// CPI with the VENUE's error code, so the code alone cannot name the leg. The last marker in the
/// logs does. This is what makes the most common failures attributable.
pub const LEG_MARKER: [u8; 7] = *b"NXV2LEG";

/// Logged (sol_log_data, one 16-byte field) right after each leg delivers:
/// `NXV2OUT` + leg index u8 + delivered u64 LE. With every venue minOut = 1, this is what names
/// the leg that under-delivered when the route then fails ERR_PROFIT.
pub const DELIVERED_MARKER: [u8; 7] = *b"NXV2OUT";

/// The 8 bytes logged before leg `i`.
pub fn leg_marker(i: usize) -> [u8; 8] {
    let mut m = [0u8; 8];
    m[..7].copy_from_slice(&LEG_MARKER);
    m[7] = i as u8; // i < MAX_LEGS
    m
}

/// The 16 bytes logged after leg `i` delivered `amount`.
pub fn delivered_log(i: usize, amount: u64) -> [u8; 16] {
    let mut m = [0u8; 16];
    m[..7].copy_from_slice(&DELIVERED_MARKER);
    m[7] = i as u8; // i < MAX_LEGS
    m[8..].copy_from_slice(&amount.to_le_bytes());
    m
}

#[derive(Debug, PartialEq, Eq)]
pub enum ArbError {
    DataTooShort,
    BadVersion(u8),
    BadLegCount(usize),
    ZeroMinProfit,
    AmountOffsetOutOfRange { leg: usize },
    DataLengthMismatch { declared: usize, actual: usize },
    LegDeliveredNothing { leg: usize },
    LegBalanceWentDown { leg: usize },
    ProfitBelowMinimum { net: i128, min: u64 },
    PayerLamportsDropped { drop: u64, max: u64 },
    PayerReassigned,
    TokenAccountDrained { leg: usize, drop: u64, allowed: u64 },
    TokenAccountAuthorityChanged { leg: usize },
    ForeignSigner { leg: usize },
    /// a NATIVE_IN leg that follows a token leg, or a NATIVE_OUT leg followed by a token leg
    BadNativeChain { leg: usize },
}

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub struct LegMeta {
    pub n_accounts: usize,
    pub amount_offset: usize,
    pub data_start: usize,
    pub data_len: usize,
    pub native_in: bool,
    pub native_out: bool,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Route {
    pub amount_in: u64,
    pub min_profit: u64,
    pub legs: Vec<LegMeta>,
    /// `Some` only when the instruction carries the guard trailer.
    pub max_payer_lamport_drop: Option<u64>,
}

fn u64_at(d: &[u8], o: usize) -> u64 {
    let mut b = [0u8; 8];
    b.copy_from_slice(&d[o..o + 8]);
    u64::from_le_bytes(b)
}

/// Parse and fully validate instruction data before anything is invoked.
pub fn parse(data: &[u8]) -> Result<Route, ArbError> {
    if data.len() < HEADER_LEN { return Err(ArbError::DataTooShort); }
    if data[0] != VERSION { return Err(ArbError::BadVersion(data[0])); }
    let n = data[1] as usize;
    if n == 0 || n > MAX_LEGS { return Err(ArbError::BadLegCount(n)); }
    let amount_in = u64_at(data, 2);
    let min_profit = u64_at(data, 10);
    if min_profit == 0 { return Err(ArbError::ZeroMinProfit); }
    // n <= MAX_LEGS, so this cannot overflow
    let meta_end = HEADER_LEN + n * LEG_META_LEN;
    if data.len() < meta_end { return Err(ArbError::DataTooShort); }
    let mut legs = Vec::with_capacity(n);
    let mut cursor = meta_end;
    for i in 0..n {
        let m = &data[HEADER_LEN + i * LEG_META_LEN..HEADER_LEN + (i + 1) * LEG_META_LEN];
        let data_len = u16::from_le_bytes([m[2], m[3]]) as usize;
        let amount_offset = m[1] as usize;
        if amount_offset.checked_add(8).map_or(true, |end| end > data_len) {
            return Err(ArbError::AmountOffsetOutOfRange { leg: i });
        }
        let native_in = m[0] & NATIVE_IN != 0;
        let native_out = m[0] & NATIVE_OUT != 0;
        legs.push(LegMeta { n_accounts: (m[0] & N_ACCOUNTS_MASK) as usize, amount_offset, data_start: cursor, data_len, native_in, native_out });
        cursor = cursor.checked_add(data_len).ok_or(ArbError::DataTooShort)?;
    }
    // native lamports only chain into native lamports: a token leg can never feed a NATIVE_IN leg, and a
    // NATIVE_OUT leg can only be last or feed a NATIVE_IN leg
    for i in 0..n {
        if legs[i].native_in && i > 0 && !legs[i - 1].native_out { return Err(ArbError::BadNativeChain { leg: i }); }
        if legs[i].native_out && i + 1 < n && !legs[i + 1].native_in { return Err(ArbError::BadNativeChain { leg: i }); }
        if !legs[i].native_in && i > 0 && legs[i - 1].native_out { return Err(ArbError::BadNativeChain { leg: i }); }
    }
    let max_payer_lamport_drop = if data.len() == cursor {
        None
    } else if cursor.checked_add(GUARD_TRAILER_LEN) == Some(data.len()) {
        Some(u64_at(data, cursor))
    } else {
        return Err(ArbError::DataLengthMismatch { declared: cursor, actual: data.len() });
    };
    Ok(Route { amount_in, min_profit, legs, max_payer_lamport_drop })
}
