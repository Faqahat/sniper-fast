//! Nexus Arb v2 — atomic arbitrage over ANY number of legs, with exact balance chaining.
//!
//! Every leg spends exactly what the previous leg delivered, measured from the output token
//! account's own balance. The whole route reverts unless the quote account ends with at least
//! `min_profit` more than it started with.
//!
//! What changed from v1 (`programs/nexus-arb`), and why:
//!   * Any number of legs (1..=MAX_LEGS) in ONE loop. v1 had copy-pasted 2-leg and 3-leg paths, and
//!     the wallet we studied routes through 3-10 swaps.
//!   * A per-leg amount offset. v1 shared one offset across every leg.
//!   * Allowlist compared as raw 32-byte keys. v1 base58-encoded every key ON CHAIN, burning compute.
//!   * Every failure names its leg. A leg that delivers nothing reverts with
//!     `Custom(LEG_ERR_BASE + leg index)`; a venue error (6003, 6036, 6005..) is attributed by the
//!     `NXV2LEG` marker logged just before that leg ran. v1 wrapped both legs in one instruction and
//!     the chain could never tell us which leg failed — we reconstructed it by hand after every loss.
//!   * Error codes live in their own range (0x4E58_xxxx), so they never collide with the token
//!     program's small codes or a venue's 6000+ codes.
//!   * `min_profit == 0` is rejected, so a break-even round trip can never pass (it still loses the fee).
//!   * Output and quote accounts must be owned by a token program.
//!   * No panics on a short account list.
//!
//! Upgrade 2026-09-15 (programs/nexus-arb-v2/UPGRADE-2026-09-15.md):
//!   * Every leg logs `NXV2OUT` + leg index + delivered amount after it runs, so a profit failure
//!     names the leg that under-delivered. Always on.
//!   * OPTIONAL payer guard, enabled by an 8-byte trailer `max_payer_lamport_drop` after the last
//!     leg's data. `check_profit` only measures the quote account; two allowlisted venues (the
//!     Raydium-CLMM forks) are upgradeable by third parties and receive the payer as signer+writable,
//!     so a malicious upgrade could take native SOL, other token balances, or token account
//!     authority inside a leg while the quote account still shows a profit. With the trailer:
//!       - authority lamports may not drop by more than the trailer across the legs, and its owner and
//!         data length may not change (a system `assign` would hand the whole wallet over without
//!         moving a lamport)                                                    -> ERR_PAYER_GUARD
//!       - per leg, every writable token account whose owner field is the authority may not lose
//!         more than: that leg's input, if it is the leg's input account (leg 0: the quote account,
//!         leg i: leg i-1's output account); zero otherwise. Its delegate, state and close authority
//!         may not change, and it may not stop being an authority-owned token account -> ERR_TOKEN_GUARD
//!       - no leg may receive a signer other than the authority, since the guard only watches the
//!         authority                                                             -> ERR_FOREIGN_SIGNER
//!     Without the trailer the program behaves exactly as before (plus the NXV2OUT log).

#![allow(clippy::too_many_arguments)]

pub mod logic {
    //! Pure route accounting. No Solana runtime; unit-testable on the host.

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

    /// Accounts: authority, quote account, then per leg (output account, program, leg accounts..).
    pub fn required_accounts(route: &Route) -> usize {
        // at most 2 + 8 * (2 + 255): cannot overflow
        2 + route.legs.iter().map(|l| 2 + l.n_accounts).sum::<usize>()
    }

    /// What a leg delivered, from its output account's own balances. No estimate, no haircut.
    pub fn delivered(leg: usize, before: u64, after: u64) -> Result<u64, ArbError> {
        let got = after.checked_sub(before).ok_or(ArbError::LegBalanceWentDown { leg })?;
        if got == 0 { return Err(ArbError::LegDeliveredNothing { leg }); }
        Ok(got)
    }

    /// Overwrite a venue instruction's input amount (encoded off chain as a placeholder).
    pub fn patch_amount(data: &mut [u8], offset: usize, amount: u64) -> bool {
        match offset.checked_add(8) {
            Some(end) if end <= data.len() => { data[offset..end].copy_from_slice(&amount.to_le_bytes()); true }
            _ => false,
        }
    }

    /// The atomic profit condition, on the quote account's real balances. UNCHANGED by the upgrade.
    pub fn check_profit(before: u64, after: u64, min_profit: u64) -> Result<u64, ArbError> {
        let net = after as i128 - before as i128;
        if net < min_profit as i128 { return Err(ArbError::ProfitBelowMinimum { net, min: min_profit }); }
        Ok(net as u64)
    }

    /// A route with native-SOL legs: quote tokens plus the authority's lamports, both across the legs.
    pub fn check_profit_native(q_before: u64, q_after: u64, l_before: u64, l_after: u64, min_profit: u64) -> Result<u64, ArbError> {
        let net = (q_after as i128 - q_before as i128) + (l_after as i128 - l_before as i128);
        if net < min_profit as i128 { return Err(ArbError::ProfitBelowMinimum { net, min: min_profit }); }
        Ok(net as u64)
    }

    /// true when any leg moves native lamports
    pub fn has_native(route: &Route) -> bool { route.legs.iter().any(|l| l.native_in || l.native_out) }

    pub fn is_allowlisted(key: &[u8; 32], allow: &[[u8; 32]]) -> bool { allow.iter().any(|a| a == key) }

    // ---- payer guard (guarded routes only) ------------------------------------------------------

    /// The authority's native account, as the guard compares it.
    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct PayerState {
        pub lamports: u64,
        pub owner: [u8; 32],
        pub data_len: usize,
    }

    /// Authority before the first leg vs after the last leg. A lamport GAIN is always fine.
    pub fn check_payer_guard(before: &PayerState, after: &PayerState, max_drop: u64) -> Result<(), ArbError> {
        if after.owner != before.owner || after.data_len != before.data_len { return Err(ArbError::PayerReassigned); }
        if let Some(drop) = before.lamports.checked_sub(after.lamports) {
            if drop > max_drop { return Err(ArbError::PayerLamportsDropped { drop, max: max_drop }); }
        }
        Ok(())
    }

    /// SPL token account layout (Tokenkeg and the base of Token-2022).
    pub const TOKEN_ACCOUNT_LEN: usize = 165;
    const TOKEN_MULTISIG_LEN: usize = 355;
    /// Token-2022 AccountType byte at offset 165 when extensions are present.
    const TOKEN_2022_ACCOUNT_TYPE_ACCOUNT: u8 = 2;
    /// delegate COption<Pubkey> [72..108] + state [108] + close_authority COption<Pubkey> [129..165]
    pub const AUTH_FIELDS_LEN: usize = 73;

    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct TokenView {
        pub amount: u64,
        pub auth: [u8; AUTH_FIELDS_LEN],
    }

    /// `Some` iff `data` (owned by a token program — the caller checks that) is an initialized token
    /// account whose owner field is `authority`. Mints (82 bytes, or AccountType 1) and multisigs are
    /// not token accounts.
    pub fn payer_token_view(data: &[u8], authority: &[u8; 32]) -> Option<TokenView> {
        let len = data.len();
        let is_account = len == TOKEN_ACCOUNT_LEN
            || (len > TOKEN_ACCOUNT_LEN && len != TOKEN_MULTISIG_LEN && data[TOKEN_ACCOUNT_LEN] == TOKEN_2022_ACCOUNT_TYPE_ACCOUNT);
        if !is_account || data[108] == 0 || data[32..64] != authority[..] { return None; }
        let mut auth = [0u8; AUTH_FIELDS_LEN];
        auth[..37].copy_from_slice(&data[72..109]);
        auth[37..].copy_from_slice(&data[129..165]);
        Some(TokenView { amount: u64_at(data, 64), auth })
    }

    /// One authority-owned token account across one leg. `after == None` means it is no longer an
    /// authority-owned token account (closed, reassigned, owner changed).
    pub fn check_token_guard(leg: usize, before: &TokenView, after: Option<&TokenView>, allowed_drop: u64) -> Result<(), ArbError> {
        let after = after.ok_or(ArbError::TokenAccountAuthorityChanged { leg })?;
        if after.auth != before.auth { return Err(ArbError::TokenAccountAuthorityChanged { leg }); }
        if let Some(drop) = before.amount.checked_sub(after.amount) {
            if drop > allowed_drop { return Err(ArbError::TokenAccountDrained { leg, drop, allowed: allowed_drop }); }
        }
        Ok(())
    }

    /// The Custom code the chain will report for a logic error.
    pub fn error_code(e: &ArbError) -> u32 {
        match e {
            ArbError::LegDeliveredNothing { leg } | ArbError::LegBalanceWentDown { leg } => LEG_ERR_BASE + *leg as u32,
            ArbError::ProfitBelowMinimum { .. } => ERR_PROFIT,
            ArbError::PayerLamportsDropped { .. } | ArbError::PayerReassigned => ERR_PAYER_GUARD,
            ArbError::TokenAccountDrained { .. } | ArbError::TokenAccountAuthorityChanged { .. } => ERR_TOKEN_GUARD,
            ArbError::ForeignSigner { .. } => ERR_FOREIGN_SIGNER,
            _ => ERR_BAD_DATA,
        }
    }

    /// Reference encoder. The TypeScript builder must produce byte-identical output; tests pin it.
    pub fn encode(amount_in: u64, min_profit: u64, legs: &[(u8, u8, &[u8])]) -> Vec<u8> {
        let mut out = vec![VERSION, legs.len() as u8];
        out.extend_from_slice(&amount_in.to_le_bytes());
        out.extend_from_slice(&min_profit.to_le_bytes());
        for (n_acc, off, d) in legs {
            out.push(*n_acc);
            out.push(*off);
            out.extend_from_slice(&(d.len() as u16).to_le_bytes());
        }
        for (_, _, d) in legs { out.extend_from_slice(d); }
        out
    }

    /// Reference encoder for a guarded route: `encode(..)` followed by the 8-byte trailer.
    pub fn encode_guarded(amount_in: u64, min_profit: u64, legs: &[(u8, u8, &[u8])], max_payer_lamport_drop: u64) -> Vec<u8> {
        let mut out = encode(amount_in, min_profit, legs);
        out.extend_from_slice(&max_payer_lamport_drop.to_le_bytes());
        out
    }
}

#[cfg(test)]
mod tests {
    use super::logic::*;

    // ---- native-SOL legs (upgrade 2026-09-30) ---------------------------------------------------

    fn route(legs: &[(u8, u8, &[u8])]) -> Result<Route, ArbError> { parse(&encode(1_000, 10, legs)) }
    const D24: [u8; 24] = [0u8; 24];

    #[test]
    fn native_flags_parse_and_leave_the_account_count_intact() {
        let r = route(&[(NATIVE_IN | 18, 8, &D24), (21, 8, &D24)]).unwrap();
        assert!(r.legs[0].native_in && !r.legs[0].native_out);
        assert_eq!(r.legs[0].n_accounts, 18);
        assert!(!r.legs[1].native_in && !r.legs[1].native_out);
        assert_eq!(r.legs[1].n_accounts, 21);
        assert!(has_native(&r));
        let r = route(&[(21, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).unwrap();
        assert!(r.legs[1].native_out);
        assert_eq!(r.legs[1].n_accounts, 16);
        assert_eq!(required_accounts(&r), 2 + (2 + 21) + (2 + 16));
    }

    #[test]
    fn pre_upgrade_encodings_parse_identically() {
        // every leg the client ever built has fewer than 64 accounts: no flag bit set
        for n in [1u8, 13, 24, 27, 63] {
            let r = route(&[(n, 8, &D24), (n, 8, &D24)]).unwrap();
            assert!(!has_native(&r));
            assert!(r.legs.iter().all(|l| l.n_accounts == n as usize && !l.native_in && !l.native_out));
        }
    }

    #[test]
    fn native_lamports_only_chain_into_native_lamports() {
        // token -> NATIVE_IN: refused
        assert_eq!(route(&[(10, 8, &D24), (NATIVE_IN | 18, 8, &D24)]), Err(ArbError::BadNativeChain { leg: 1 }));
        // NATIVE_OUT -> token: refused
        assert_eq!(route(&[(NATIVE_OUT | 16, 8, &D24), (10, 8, &D24)]), Err(ArbError::BadNativeChain { leg: 0 }));
        // NATIVE_OUT -> NATIVE_IN: fine (curve to curve)
        assert!(route(&[(10, 8, &D24), (NATIVE_OUT | NATIVE_IN | 16, 8, &D24), (NATIVE_IN | 18, 8, &D24), (10, 8, &D24)]).is_err());
        assert!(route(&[(NATIVE_IN | 18, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).is_ok());
        assert!(route(&[(NATIVE_IN | 18, 8, &D24), (10, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).is_ok());
        assert_eq!(error_code(&ArbError::BadNativeChain { leg: 0 }), ERR_BAD_DATA);
    }

    #[test]
    fn native_profit_counts_lamports_and_tokens_together() {
        // buy on the curve with 1.0 SOL of lamports, sell into wSOL for 1.02: +0.02
        assert_eq!(check_profit_native(5_000, 1_020_005_000, 9_000_000_000, 8_000_000_000, 1_000_000), Ok(20_000_000));
        // buy with wSOL, sell on the curve for lamports
        assert_eq!(check_profit_native(2_000_000_000, 1_000_000_000, 100, 1_010_000_100, 1), Ok(10_000_000));
        // the lamports spent are not free: a token gain smaller than the lamports spent fails
        assert_eq!(check_profit_native(0, 999_999_999, 1_000_000_000, 0, 1),
            Err(ArbError::ProfitBelowMinimum { net: -1, min: 1 }));
    }

    fn leg(n: u8, len: usize) -> (u8, u8, Vec<u8>) { (n, 8, vec![0xAB; len]) }

    #[test]
    fn parses_a_five_leg_route_exactly() {
        let ls: Vec<_> = (0..5).map(|i| leg(10 + i, 24 + i as usize)).collect();
        let refs: Vec<(u8, u8, &[u8])> = ls.iter().map(|(n, o, d)| (*n, *o, d.as_slice())).collect();
        let data = encode(201_247_735, 10_000, &refs);
        let r = parse(&data).unwrap();
        assert_eq!(r.amount_in, 201_247_735);
        assert_eq!(r.min_profit, 10_000);
        assert_eq!(r.legs.len(), 5);
        assert_eq!(r.max_payer_lamport_drop, None);
        let mut start = HEADER_LEN + 5 * LEG_META_LEN;
        for (i, l) in r.legs.iter().enumerate() {
            assert_eq!(l.n_accounts, 10 + i);
            assert_eq!(l.data_start, start);
            assert_eq!(l.data_len, 24 + i);
            start += 24 + i;
        }
        assert_eq!(required_accounts(&r), 2 + (0..5).map(|i| 2 + 10 + i).sum::<usize>());
    }

    #[test]
    fn every_leg_spends_exactly_what_the_previous_delivered() {
        // SOL -> A -> B -> C -> SOL with over- and under-delivery. Each input is the prior delta.
        let balances = [(0u64, 970u64), (20, 532), (5, 1_005), (1_000_000, 1_000_120)];
        let mut input = 1_000u64;
        let mut inputs = vec![input];
        for (i, (b, a)) in balances.iter().enumerate() {
            input = delivered(i, *b, *a).unwrap();
            inputs.push(input);
        }
        assert_eq!(inputs, vec![1_000, 970, 512, 1_000, 120]);
    }

    #[test]
    fn a_leg_that_delivers_nothing_names_itself() {
        let e = delivered(3, 500, 500).unwrap_err();
        assert_eq!(e, ArbError::LegDeliveredNothing { leg: 3 });
        assert_eq!(error_code(&e), LEG_ERR_BASE + 3);
        let e = delivered(0, 500, 400).unwrap_err();
        assert_eq!(error_code(&e), LEG_ERR_BASE);
    }

    #[test]
    fn profit_guard_uses_real_balances_and_rejects_break_even() {
        assert_eq!(check_profit(1_000, 1_010, 5).unwrap(), 10);
        assert!(check_profit(1_000, 1_004, 5).is_err());
        assert!(check_profit(1_000, 990, 1).is_err());
        assert_eq!(error_code(&check_profit(1_000, 990, 1).unwrap_err()), ERR_PROFIT);
        // min_profit 0 would let a break-even trade through; parse refuses it
        let data = encode(1_000, 0, &[(4, 8, &[0u8; 16])]);
        assert_eq!(parse(&data), Err(ArbError::ZeroMinProfit));
    }

    #[test]
    fn malformed_data_is_rejected_before_anything_runs() {
        assert_eq!(parse(&[]), Err(ArbError::DataTooShort));
        let mut d = encode(1, 1, &[(4, 8, &[0u8; 16])]);
        d[0] = 0x01;
        assert_eq!(parse(&d), Err(ArbError::BadVersion(0x01)));
        let none = encode(1, 1, &[]);
        assert_eq!(parse(&none), Err(ArbError::BadLegCount(0)));
        let nine: Vec<(u8, u8, &[u8])> = (0..9).map(|_| (4u8, 8u8, &[0u8; 16][..])).collect();
        assert_eq!(parse(&encode(1, 1, &nine)), Err(ArbError::BadLegCount(9)));
        // amount offset past the end of that leg's data
        assert_eq!(parse(&encode(1, 1, &[(4, 12, &[0u8; 16])])), Err(ArbError::AmountOffsetOutOfRange { leg: 0 }));
        // trailing garbage
        let mut t = encode(1, 1, &[(4, 8, &[0u8; 16])]);
        t.push(0);
        assert!(matches!(parse(&t), Err(ArbError::DataLengthMismatch { .. })));
    }

    #[test]
    fn amount_patching_is_bounds_checked() {
        let mut d = vec![0u8; 24];
        assert!(patch_amount(&mut d, 8, 123_456_789));
        assert_eq!(u64::from_le_bytes(d[8..16].try_into().unwrap()), 123_456_789);
        assert!(!patch_amount(&mut d, 20, 1));
        assert!(!patch_amount(&mut d, usize::MAX, 1));
    }

    /// The TypeScript builder asserts this exact hex too (tools/arb-v2/exec/nexus-v2.test.ts).
    const FIXTURE_HEX: &str = concat!(
        "0202", "0807060504030201", "1817161514131211", "03081000", "04081000",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    );
    /// FIXTURE_HEX + max_payer_lamport_drop = 0x2122232425262728. Pinned in the TS test too.
    const GUARDED_FIXTURE_HEX: &str = concat!(
        "0202", "0807060504030201", "1817161514131211", "03081000", "04081000",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "2827262524232221"
    );

    fn hex(d: &[u8]) -> String { d.iter().map(|b| format!("{:02x}", b)).collect() }
    fn unhex(s: &str) -> Vec<u8> { (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect() }

    #[test]
    fn encoding_matches_the_pinned_cross_language_fixture() {
        let data = encode(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &[(3, 8, &[0xAA; 16]), (4, 8, &[0xBB; 16])]);
        assert_eq!(hex(&data), FIXTURE_HEX);
        assert_eq!(parse(&data).unwrap().legs.len(), 2);
    }

    #[test]
    fn old_format_parses_identically_after_the_upgrade() {
        // the exact pre-upgrade bytes: same legs, same offsets, and no guard
        let r = parse(&unhex(FIXTURE_HEX)).unwrap();
        assert_eq!(r, Route {
            amount_in: 0x0102_0304_0506_0708,
            min_profit: 0x1112_1314_1516_1718,
            legs: vec![
                LegMeta { n_accounts: 3, amount_offset: 8, data_start: 26, data_len: 16, native_in: false, native_out: false },
                LegMeta { n_accounts: 4, amount_offset: 8, data_start: 42, data_len: 16, native_in: false, native_out: false },
            ],
            max_payer_lamport_drop: None,
        });
    }

    #[test]
    fn guarded_format_parses_the_trailer_and_nothing_else_changes() {
        let legs: [(u8, u8, &[u8]); 2] = [(3, 8, &[0xAA; 16]), (4, 8, &[0xBB; 16])];
        let data = encode_guarded(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs, 0x2122_2324_2526_2728);
        assert_eq!(hex(&data), GUARDED_FIXTURE_HEX);
        let g = parse(&data).unwrap();
        let old = parse(&encode(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs)).unwrap();
        assert_eq!(g.max_payer_lamport_drop, Some(0x2122_2324_2526_2728));
        assert_eq!((g.amount_in, g.min_profit, &g.legs), (old.amount_in, old.min_profit, &old.legs));
        // zero is a valid (the strictest) guard
        assert_eq!(parse(&encode_guarded(1, 1, &legs, 0)).unwrap().max_payer_lamport_drop, Some(0));
        // any trailer length other than 0 or 8 is refused
        for extra in [1usize, 7, 9, 16] {
            let mut d = encode(1, 1, &legs);
            d.extend(std::iter::repeat(0u8).take(extra));
            assert!(matches!(parse(&d), Err(ArbError::DataLengthMismatch { .. })), "{extra} trailing bytes");
        }
        // a truncated leg is not mistaken for a guard trailer
        let mut short = encode_guarded(1, 1, &legs, 0);
        short.truncate(short.len() - 1);
        assert!(matches!(parse(&short), Err(ArbError::DataLengthMismatch { .. })));
    }

    #[test]
    fn payer_guard_passes_within_the_limit_and_fails_with_its_own_code() {
        let before = PayerState { lamports: 1_000_000, owner: [0u8; 32], data_len: 0 };
        let at = |lamports| PayerState { lamports, ..before };
        assert_eq!(check_payer_guard(&before, &at(1_000_000), 0), Ok(()));
        assert_eq!(check_payer_guard(&before, &at(2_000_000), 0), Ok(()));      // a gain is fine
        assert_eq!(check_payer_guard(&before, &at(995_000), 5_000), Ok(()));    // exactly the limit
        let e = check_payer_guard(&before, &at(994_999), 5_000).unwrap_err();
        assert_eq!(e, ArbError::PayerLamportsDropped { drop: 5_001, max: 5_000 });
        assert_eq!(error_code(&e), ERR_PAYER_GUARD);
        // a drop of the entire balance (1e6) is under a huge limit, so it passes
        assert_eq!(check_payer_guard(&before, &at(0), u64::MAX - 1), Ok(()));
        assert_eq!(check_payer_guard(&before, &at(0), u64::MAX), Ok(()));
        // a system `assign` or `allocate` moves no lamports but hands the wallet away
        let e = check_payer_guard(&before, &PayerState { owner: [9u8; 32], ..before }, u64::MAX).unwrap_err();
        assert_eq!((e == ArbError::PayerReassigned, error_code(&ArbError::PayerReassigned)), (true, ERR_PAYER_GUARD));
        assert_eq!(check_payer_guard(&before, &PayerState { data_len: 10, ..before }, u64::MAX), Err(ArbError::PayerReassigned));
    }

    fn token_account(owner: [u8; 32], amount: u64) -> Vec<u8> {
        let mut d = vec![0u8; TOKEN_ACCOUNT_LEN];
        d[..32].copy_from_slice(&[5u8; 32]);
        d[32..64].copy_from_slice(&owner);
        d[64..72].copy_from_slice(&amount.to_le_bytes());
        d[108] = 1;
        d
    }

    #[test]
    fn token_view_only_sees_initialized_token_accounts_owned_by_the_authority() {
        let me = [7u8; 32];
        let v = payer_token_view(&token_account(me, 42), &me).unwrap();
        assert_eq!(v.amount, 42);
        assert!(payer_token_view(&token_account([8u8; 32], 42), &me).is_none());   // someone else's
        let mut uninit = token_account(me, 42);
        uninit[108] = 0;
        assert!(payer_token_view(&uninit, &me).is_none());
        assert!(payer_token_view(&[0u8; 82], &me).is_none());                      // a mint
        assert!(payer_token_view(&vec![0u8; TOKEN_ACCOUNT_LEN], &me).is_none());   // zeroed (closed)
        // Token-2022 with extensions: AccountType byte decides
        let mut ext = token_account(me, 42);
        ext.extend_from_slice(&[2u8, 0, 0, 0]);
        assert!(payer_token_view(&ext, &me).is_some());
        ext[TOKEN_ACCOUNT_LEN] = 1;                                                 // AccountType::Mint
        assert!(payer_token_view(&ext, &me).is_none());
    }

    #[test]
    fn token_guard_allows_the_input_spend_and_nothing_more() {
        let me = [7u8; 32];
        let before = payer_token_view(&token_account(me, 1_000), &me).unwrap();
        let view = |amount| payer_token_view(&token_account(me, amount), &me).unwrap();
        // the leg's input account may lose up to the leg's input
        assert_eq!(check_token_guard(2, &before, Some(&view(600)), 400), Ok(()));
        assert_eq!(check_token_guard(2, &before, Some(&view(700)), 400), Ok(()));
        assert_eq!(check_token_guard(2, &before, Some(&view(5_000)), 0), Ok(()));  // gains always fine
        let e = check_token_guard(2, &before, Some(&view(599)), 400).unwrap_err();
        assert_eq!(e, ArbError::TokenAccountDrained { leg: 2, drop: 401, allowed: 400 });
        assert_eq!(error_code(&e), ERR_TOKEN_GUARD);
        // any other authority-owned account may not lose a single unit
        assert_eq!(error_code(&check_token_guard(0, &before, Some(&view(999)), 0).unwrap_err()), ERR_TOKEN_GUARD);
        // authority moved away / closed / delegate set / frozen: amount unchanged, still refused
        assert_eq!(check_token_guard(1, &before, None, u64::MAX), Err(ArbError::TokenAccountAuthorityChanged { leg: 1 }));
        let mut delegated = token_account(me, 1_000);
        delegated[72] = 1;
        delegated[76..108].copy_from_slice(&[9u8; 32]);
        let d = payer_token_view(&delegated, &me).unwrap();
        assert_eq!(check_token_guard(1, &before, Some(&d), u64::MAX), Err(ArbError::TokenAccountAuthorityChanged { leg: 1 }));
        let mut frozen = token_account(me, 1_000);
        frozen[108] = 2;
        let f = payer_token_view(&frozen, &me).unwrap();
        assert_eq!(error_code(&check_token_guard(1, &before, Some(&f), u64::MAX).unwrap_err()), ERR_TOKEN_GUARD);
    }

    #[test]
    fn delivered_log_names_leg_and_amount() {
        let m = delivered_log(3, 0x0102_0304_0506_0708);
        assert_eq!(&m[..7], b"NXV2OUT");
        assert_eq!(m[7], 3);
        assert_eq!(u64::from_le_bytes(m[8..16].try_into().unwrap()), 0x0102_0304_0506_0708);
        assert_ne!(m.len(), leg_marker(3).len()); // the TS leg-marker reader keys on 8 bytes
    }

    #[test]
    fn error_codes_cannot_collide_with_token_or_anchor_errors() {
        // SPL token errors are < 32, Anchor framework errors 100-5999, Anchor program errors 6000+.
        let all = [ERR_BAD_DATA, ERR_PROFIT, ERR_NOT_ALLOWLISTED, ERR_NOT_TOKEN_ACCOUNT, ERR_PAYER_GUARD, ERR_TOKEN_GUARD, ERR_FOREIGN_SIGNER, LEG_ERR_BASE, LEG_ERR_BASE + MAX_LEGS as u32];
        for code in all {
            assert!(code > 1_000_000, "code {code} could be mistaken for a venue or token error");
        }
        // the pre-upgrade codes keep their numbers; the new ones are the next free slots
        assert_eq!((ERR_BAD_DATA, ERR_PROFIT, ERR_NOT_ALLOWLISTED, ERR_NOT_TOKEN_ACCOUNT), (0x4E58_0001, 0x4E58_0002, 0x4E58_0003, 0x4E58_0004));
        assert_eq!((ERR_PAYER_GUARD, ERR_TOKEN_GUARD, ERR_FOREIGN_SIGNER), (0x4E58_0005, 0x4E58_0006, 0x4E58_0007));
        for (i, a) in all.iter().enumerate() { for b in &all[i + 1..] { assert_ne!(a, b); } }
    }

    #[test]
    fn leg_marker_names_the_leg() {
        let m = leg_marker(5);
        assert_eq!(&m[..7], b"NXV2LEG");
        assert_eq!(m[7], 5);
    }

    #[test]
    fn allowlist_compares_raw_bytes() {
        let a = [7u8; 32];
        let b = [9u8; 32];
        assert!(is_allowlisted(&a, &[b, a]));
        assert!(!is_allowlisted(&[1u8; 32], &[b, a]));
    }
}

// ---------------------------------------------------------------------------------------------
// On-chain entrypoint. Built with `--features onchain`; everything above is runtime-free.
// ---------------------------------------------------------------------------------------------
#[cfg(feature = "onchain")]
pub mod onchain {
    use super::logic::*;
    use solana_program::{
        account_info::AccountInfo,
        entrypoint,
        entrypoint::ProgramResult,
        instruction::{AccountMeta, Instruction},
        log::sol_log_data,
        program::invoke,
        program_error::ProgramError,
        pubkey,
        pubkey::Pubkey,
    };

    /// Only these venue programs may be invoked. A caller cannot substitute an arbitrary program.
    const ALLOWLIST: [Pubkey; 12] = [
        pubkey!("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"), // Meteora DLMM
        pubkey!("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"), // Orca Whirlpool
        pubkey!("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"), // Raydium CLMM
        pubkey!("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"), // PumpSwap
        pubkey!("HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq"), // Raydium-CLMM fork (PancakeSwap v3)
        pubkey!("REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2"), // Raydium-CLMM fork (Byreal)
        pubkey!("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"), // Raydium CPMM
        // Added 2026-09-15 at the operator's explicit request (Path A): a 750-block census showed these
        // two complete ~1,900 arbs / 4 min whose other legs are already allowlisted.
        pubkey!("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"), // Raydium AMM v4 (amount_in at data offset 1)
        pubkey!("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"), // Meteora DAMM v2
        // Added 2026-09-30 at the owner's request (FINDINGS F-084): launchpad bonding curves, one upgrade for all three.
        pubkey!("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"), // pump.fun bonding curve (native SOL: NATIVE_IN/OUT legs)
        pubkey!("dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"), // Meteora Dynamic Bonding Curve (wSOL token accounts)
        pubkey!("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"), // Raydium LaunchLab (wSOL token accounts)
    ];
    const TOKEN: Pubkey = pubkey!("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
    const TOKEN_2022: Pubkey = pubkey!("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
    /// Authority-owned writable token accounts a leg normally carries: 2 (in and out). One allocation
    /// is reused across all legs; the bump allocator never frees, so do not allocate per leg.
    const SNAP_CAPACITY: usize = 8;

    entrypoint!(process_instruction);

    fn custom(code: u32) -> ProgramError { ProgramError::Custom(code) }
    fn arb(e: ArbError) -> ProgramError { custom(error_code(&e)) }

    /// SPL token account: amount is a u64 at offset 64. The account must belong to a token program,
    /// otherwise a crafted account could satisfy the profit check without holding real tokens.
    fn token_amount(ai: &AccountInfo) -> Result<u64, ProgramError> {
        if *ai.owner != TOKEN && *ai.owner != TOKEN_2022 { return Err(custom(ERR_NOT_TOKEN_ACCOUNT)); }
        let d = ai.try_borrow_data()?;
        if d.len() < 72 { return Err(ProgramError::InvalidAccountData); }
        let mut b = [0u8; 8];
        b.copy_from_slice(&d[64..72]);
        Ok(u64::from_le_bytes(b))
    }

    fn payer_state(ai: &AccountInfo) -> PayerState {
        PayerState { lamports: ai.lamports(), owner: ai.owner.to_bytes(), data_len: ai.data_len() }
    }

    /// `Some` iff `ai` is currently a token-program-owned, initialized token account whose owner field
    /// is the authority. Read after a CPI, `None` means it was closed, reassigned or re-owned.
    fn payer_token(ai: &AccountInfo, authority: &[u8; 32]) -> Result<Option<TokenView>, ProgramError> {
        if *ai.owner != TOKEN && *ai.owner != TOKEN_2022 { return Ok(None); }
        let d = ai.try_borrow_data()?;
        Ok(payer_token_view(&d, authority))
    }

    pub fn process_instruction(_pid: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
        let route = parse(data).map_err(arb)?;
        if accounts.len() < required_accounts(&route) { return Err(ProgramError::NotEnoughAccountKeys); }

        let authority = &accounts[0];
        if !authority.is_signer { return Err(ProgramError::MissingRequiredSignature); }
        let quote = &accounts[1];
        let quote_before = token_amount(quote)?;
        let native = has_native(&route);
        let lamports_before = authority.lamports();

        let guard = route.max_payer_lamport_drop;
        let authority_bytes = authority.key.to_bytes();
        let payer_before = guard.map(|_| payer_state(authority));
        // (index into leg accounts, view before the leg). Vec::new() does not allocate.
        let mut snaps: Vec<(usize, TokenView)> = if guard.is_some() { Vec::with_capacity(SNAP_CAPACITY) } else { Vec::new() };

        let mut cursor = 2usize;
        let mut input = route.amount_in;
        // the account each leg spends from: leg 0 the quote account, leg i leg i-1's output account
        let mut input_acct: &AccountInfo = quote;
        for (i, leg) in route.legs.iter().enumerate() {
            // bounded by required_accounts(), checked above
            let out_acct = &accounts[cursor];
            let program = &accounts[cursor + 1];
            let leg_end = cursor + 2 + leg.n_accounts;
            let leg_accounts = &accounts[cursor + 2..leg_end];
            cursor = leg_end;

            if !ALLOWLIST.contains(program.key) { return Err(custom(ERR_NOT_ALLOWLISTED)); }

            if guard.is_some() {
                snaps.clear();
                for (j, a) in leg_accounts.iter().enumerate() {
                    // the guard watches the authority only; a second signer would be unguarded
                    if a.is_signer && a.key != authority.key { return Err(arb(ArbError::ForeignSigner { leg: i })); }
                    // a read-only account cannot be changed by the venue: the runtime enforces it
                    if !a.is_writable { continue; }
                    if let Some(v) = payer_token(a, &authority_bytes)? { snaps.push((j, v)); }
                }
            }

            // NATIVE_OUT: the output is the authority's lamport gain, and its output slot must name the authority
            if leg.native_out && out_acct.key != authority.key { return Err(custom(ERR_BAD_DATA)); }
            let before = if leg.native_out { authority.lamports() } else { token_amount(out_acct)? };
            // name the leg BEFORE invoking it: a venue error aborts inside the CPI with its own code
            sol_log_data(&[&leg_marker(i)]);
            let mut leg_data = data[leg.data_start..leg.data_start + leg.data_len].to_vec();
            if !patch_amount(&mut leg_data, leg.amount_offset, input) { return Err(custom(ERR_BAD_DATA)); }
            invoke(
                &Instruction {
                    program_id: *program.key,
                    accounts: leg_accounts
                        .iter()
                        .map(|a| AccountMeta { pubkey: *a.key, is_signer: a.is_signer, is_writable: a.is_writable })
                        .collect(),
                    data: leg_data,
                },
                leg_accounts,
            )?;
            let after = if leg.native_out { authority.lamports() } else { token_amount(out_acct)? };
            let got = delivered(i, before, after).map_err(arb)?;
            // name what this leg delivered, so an ERR_PROFIT later can be attributed to a leg
            sol_log_data(&[&delivered_log(i, got)]);

            if guard.is_some() {
                for (j, snap) in snaps.iter() {
                    let a = &leg_accounts[*j];
                    // a NATIVE_IN leg spends lamports: no token account of ours may drop in it
                    let allowed = if a.key == input_acct.key && !leg.native_in { input } else { 0 };
                    let now = payer_token(a, &authority_bytes)?;
                    check_token_guard(i, snap, now.as_ref(), allowed).map_err(arb)?;
                }
            }

            input = got;
            input_acct = out_acct;
        }

        if let (Some(max_drop), Some(before)) = (guard, payer_before.as_ref()) {
            check_payer_guard(before, &payer_state(authority), max_drop).map_err(arb)?;
        }

        let quote_after = token_amount(quote)?;
        if native {
            check_profit_native(quote_before, quote_after, lamports_before, authority.lamports(), route.min_profit).map_err(arb)?;
        } else {
            check_profit(quote_before, quote_after, route.min_profit).map_err(arb)?;
        }
        Ok(())
    }
}
