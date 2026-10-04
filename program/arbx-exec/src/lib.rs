//! arbx-exec: the arbx on-chain route executor. It runs an atomic, self-funded round trip of 1..=8 legs, and the
//! whole transaction reverts unless the route ends with at least `min_profit` more than it started with.
//!
//! This is a NEW program with its own program id. It started as a copy of nexus-arb-v2 (8K8uyQDt…, kept untouched
//! in `program/nexus-arb-v2` as the reference). The plan is `docs/research/redesign-final.md` §3.9, plus
//! `docs-review-synthesis.md` §4.
//!
//! Two instruction layouts, chosen by byte 0 (`README.md` has the byte tables):
//!   * **v2** (byte 0 = 2): nexus-arb-v2's layout, byte for byte and PARSED identically (a property test compares
//!     the parser with a verbatim copy of nexus-arb-v2's). That includes the optional 8-byte payer-guard trailer and
//!     the NATIVE flags in the top bits of the n_accounts byte. EXECUTION is not byte-identical to nexus-arb-v2
//!     (REVIEW.md #8); an engine switching only the program id must know these differences:
//!       - three account-structure mistakes get the new code ERR_BAD_ACCOUNTS (0x4E580009) instead of nexus's
//!         answer: a last leg that does not deliver into the quote account (nexus: ERR_PROFIT after running every
//!         leg), a native route with a read-only authority (nexus: the runtime's PrivilegeEscalation), and a token
//!         leg whose output account is its input account;
//!       - the NATIVE_OUT output-slot check runs before the foreign-signer scan (the codes are unchanged);
//!       - every route also logs one AXS1 summary record at the guard (about 130 log bytes and ~200 CU), after the
//!         unchanged NXV2LEG / NXV2OUT markers.
//!   * **v3** (byte 0 = 3): a flags byte, a MANDATORY payer-guard field, an optional CPI-tip block, and a 5-byte leg
//!     descriptor with its own leg_flags byte. A full u8 n_accounts (1..=255) fixes the v2 bug where a leg with 64 or
//!     more accounts collided with the NATIVE flag bits. Rules the parser enforces (each is ERR_BAD_DATA):
//!       - PAYER_GUARD must be set: every venue sees the trading wallet as a signer (REVIEW.md #2);
//!       - CPI_TIP requires COUNT_LAMPORTS: the tip is paid in lamports, so lamports lost inside the legs must
//!         count against the gain it is computed from (REVIEW.md #4);
//!       - a native leg requires COUNT_LAMPORTS; one leg cannot be both NATIVE_IN and NATIVE_OUT (REVIEW.md #6);
//!         LEG_AUTH_RO cannot be combined with a native flag;
//!       - SELF_SIZE, BASKET and NOOP_ON_MISS are reserved (ERR_UNSUPPORTED); bits 6-7 must be 0;
//!       - the instruction needs at most 255 accounts (the runtime's per-instruction limit).
//!     At run time a v3 route also requires the quote account and every token output account to be owned (token
//!     owner field) by the authority (REVIEW.md #7), and a CPI tip must leave the authority rent-exempt (#5).
//!
//! What every route gets, in both layouts:
//!   * Balance chaining: each leg spends exactly what the previous leg delivered, measured from the output
//!     account's real balance (leg 0 spends `amount_in`).
//!   * A compiled-in venue allowlist. Keys are compared as raw bytes.
//!   * Signer and aliasing checks. The authority signs. The last leg delivers into the quote account (or into the
//!     authority's lamports for a NATIVE_OUT leg). A token leg never delivers into the account it spends from.
//!   * An end-of-route guard computed in i128:
//!         g = (quote_after − quote_before) + (COUNT_LAMPORTS ? authority lamport delta : 0)
//!     With CPI_TIP the route needs g − tip ≥ min_profit, otherwise g ≥ min_profit. Anything less reverts the
//!     whole transaction with ERR_PROFIT.
//!   * Structured logs (`LOGS.md`): one record per leg and one summary record per route. The summary is logged
//!     even when the guard fails, so a miss says by how much it missed. The summary is the guard's verdict, not the
//!     transaction's outcome: a CPI tip or the runtime's rent check can still fail the transaction after it.
//!   * No PDAs and no funds held. Every swap is signed by the trading wallet itself.
//!
//! Venue min-out stays 0 or 1 in every leg. The end-of-route guard is the protection.
//!
//! Syscalls: the program may only use syscalls that mainnet registers unconditionally or behind an ACTIVE feature.
//! `tests/litesvm.rs::review_01_elf_uses_only_syscalls_mainnet_registers` audits the built ELF against the runtime's
//! registry under LiteSVM's mainnet feature set. (`sol_remaining_compute_units` is NOT active on mainnet; calling it
//! aborted every route at the guard: REVIEW.md #1.)

#![allow(clippy::too_many_arguments)]

pub mod logic {
    //! Pure route accounting with no Solana runtime, so it is unit-testable on the host. The on-chain entrypoint is
    //! a thin shell around these functions.

    // ============================================================================================================
    // Layouts
    // ============================================================================================================

    pub const V2: u8 = 0x02;
    pub const V3: u8 = 0x03;
    /// nexus-arb-v2's name for the v2 version byte. Kept for engine code that uses it.
    pub const VERSION: u8 = V2;
    pub const MAX_LEGS: usize = 8;

    // ---- v2 (byte for byte nexus-arb-v2) -------------------------------------------------------------------------
    /// version u8, n_legs u8, amount_in u64, min_profit u64
    pub const HEADER_LEN: usize = 18;
    /// per leg: n_accounts u8 (top 2 bits = NATIVE flags), amount_offset u8, data_len u16
    pub const LEG_META_LEN: usize = 4;
    /// v2 native-SOL flags, in the top bits of the leg's n_accounts byte. The low 6 bits are the account count.
    /// A v2 leg therefore cannot carry 64 or more accounts. v3 fixes this.
    pub const NATIVE_IN: u8 = 0x80;
    pub const NATIVE_OUT: u8 = 0x40;
    pub const N_ACCOUNTS_MASK: u8 = 0x3F;
    /// Optional v2 trailer `max_payer_lamport_drop` u64 LE. Its presence is decided by the exact total length.
    pub const GUARD_TRAILER_LEN: usize = 8;

    // ---- v3 ------------------------------------------------------------------------------------------------------
    /// version u8 (3), flags u8, n_legs u8, amount_in u64, min_profit u64
    pub const V3_HEADER_LEN: usize = 19;
    /// max_payer_lamport_drop u64. Present iff PAYER_GUARD.
    pub const V3_GUARD_LEN: usize = 8;
    /// tip_bps u16, tip_floor u64, tip_cap u64, tip_acct_ix u8. Present iff CPI_TIP.
    pub const V3_TIP_LEN: usize = 19;
    /// per leg: n_accounts u8 (1..=255), leg_flags u8, amount_offset u8, data_len u16
    pub const V3_LEG_META_LEN: usize = 5;

    /// v3 flags, byte 1.
    /// Mandatory in v3: the payer guard (authority owner, data length and lamports; the authority's token accounts
    /// in every leg; no foreign signer). A v3 route without it is ERR_BAD_DATA.
    pub const PAYER_GUARD: u8 = 0x01;
    /// Pay `clamp(g × bps)` to a Jito tip account by CPI once the guard passes. Requires COUNT_LAMPORTS.
    pub const CPI_TIP: u8 = 0x02;
    pub const COUNT_LAMPORTS: u8 = 0x04;
    /// Reserved for Stage 2B: on-chain sizing. Rejected with ERR_UNSUPPORTED for now.
    pub const SELF_SIZE: u8 = 0x08;
    /// Reserved for Stage 2B: a basket of candidate pairs. Rejected with ERR_UNSUPPORTED for now.
    pub const BASKET: u8 = 0x10;
    /// Reserved for the order-flow track: no-op instead of a revert. Rejected with ERR_UNSUPPORTED for now.
    pub const NOOP_ON_MISS: u8 = 0x20;
    pub const RESERVED_FEATURES: u8 = SELF_SIZE | BASKET | NOOP_ON_MISS;
    /// Bits 6 and 7 must be 0. Setting them is ERR_BAD_DATA.
    pub const INVALID_FLAGS: u8 = 0xC0;

    /// v3 leg_flags. These normalized bits are also what the AXL1 log record carries for both layouts.
    /// At most one of NATIVE_IN / NATIVE_OUT per leg.
    pub const LEG_NATIVE_IN: u8 = 0x01;
    pub const LEG_NATIVE_OUT: u8 = 0x02;
    /// The venue gets the authority as a READ-ONLY signer (REVIEW.md #14): the runtime then refuses any lamport debit
    /// or System assign of the wallet inside this leg, whatever the venue's code does. For venues whose swap takes the
    /// user as a plain `Signer` (DLMM swap2, CPMM, DAMM v2, AMM v4, Whirlpool, CLMM); a venue that marks the user
    /// `mut` (PumpSwap) fails with PrivilegeEscalation. Not allowed on a native leg (those move authority lamports).
    pub const LEG_AUTH_RO: u8 = 0x04;
    pub const LEG_FLAGS_KNOWN: u8 = LEG_NATIVE_IN | LEG_NATIVE_OUT | LEG_AUTH_RO;

    pub const MAX_TIP_BPS: u16 = 10_000;
    pub const BPS_DENOMINATOR: i128 = 10_000;
    /// The largest top-level instruction the runtime serializes (agave MAX_ACCOUNTS_PER_INSTRUCTION; 256 metas fail
    /// with MaxAccountsExceeded before the program runs). The v3 parser accepts n_accounts up to 255 per leg, and
    /// also requires the instruction as a whole (2 + Σ(2 + n_i) [+ 2]) to fit.
    pub const MAX_IX_ACCOUNTS: usize = 255;

    // ============================================================================================================
    // Compiled-in keys. These are the single source of truth: the on-chain module decodes them at compile time.
    // ============================================================================================================

    /// The only programs a leg may invoke. The venue id in the AXL1 log is the index into this list. The list is
    /// APPEND-ONLY: never reorder it, or the ids in old logs change meaning. Same 12 venues as nexus-arb-v2.
    pub const ALLOWLIST_B58: [&str; 12] = [
        "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", // 0  Meteora DLMM
        "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", // 1  Orca Whirlpool
        "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", // 2  Raydium CLMM
        "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", // 3  PumpSwap
        "HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq", // 4  Raydium-CLMM fork (PancakeSwap v3)
        "REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2", // 5  Raydium-CLMM fork (Byreal)
        "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", // 6  Raydium CPMM
        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", // 7  Raydium AMM v4 (amount_in at data offset 1)
        "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", // 8  Meteora DAMM v2
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", // 9  pump.fun bonding curve (native SOL legs)
        "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", // 10 Meteora Dynamic Bonding Curve
        "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", // 11 Raydium LaunchLab
    ];
    pub const ALLOWLIST_NAMES: [&str; 12] = [
        "meteora-dlmm", "orca-whirlpool", "raydium-clmm", "pumpswap", "pancake-clmm", "byreal-clmm",
        "raydium-cpmm", "raydium-amm-v4", "meteora-damm-v2", "pumpfun", "meteora-dbc", "raydium-launchlab",
    ];

    /// The 8 Jito tip accounts (data/sender-tip-accounts.json, `jito.tip_accounts`, same order). A CPI tip can only
    /// go to `JITO_TIP_ACCOUNTS_B58[tip_acct_ix]`.
    pub const JITO_TIP_ACCOUNTS_B58: [&str; 8] = [
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
        "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
        "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    ];

    /// Lamports are only ever added to wrapped SOL. COUNT_LAMPORTS and CPI_TIP need a wSOL quote account (v3 only).
    pub const WSOL_MINT_B58: &str = "So11111111111111111111111111111111111111112";
    pub const SYSTEM_PROGRAM_B58: &str = "11111111111111111111111111111111";
    pub const TOKEN_PROGRAM_B58: &str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
    pub const TOKEN_2022_PROGRAM_B58: &str = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";

    // ============================================================================================================
    // Error codes (Custom(u32)). They are stable, because the off-chain recorder decodes them, and they sit in their
    // own range: SPL token codes are < 32, Anchor 100-5999 and venue codes 6000+.
    // ============================================================================================================

    pub const ERR_BASE: u32 = 0x4E58_0000; // "NX"
    pub const ERR_BAD_DATA: u32 = ERR_BASE + 1;
    pub const ERR_PROFIT: u32 = ERR_BASE + 2;
    pub const ERR_NOT_ALLOWLISTED: u32 = ERR_BASE + 3;
    pub const ERR_NOT_TOKEN_ACCOUNT: u32 = ERR_BASE + 4;
    pub const ERR_PAYER_GUARD: u32 = ERR_BASE + 5;
    pub const ERR_TOKEN_GUARD: u32 = ERR_BASE + 6;
    pub const ERR_FOREIGN_SIGNER: u32 = ERR_BASE + 7;
    /// v3: a reserved feature flag is set (SELF_SIZE, BASKET or NOOP_ON_MISS). The data is well formed, but this
    /// build does not implement the feature.
    pub const ERR_UNSUPPORTED: u32 = ERR_BASE + 8;
    /// The account list is badly structured: the last leg does not deliver into the quote account, a token leg
    /// delivers into its own input account, a NATIVE_OUT slot (v3) is not the authority, the authority is not
    /// writable when lamports move, or (v3) the quote account or a leg's token output account is not owned by the
    /// authority.
    pub const ERR_BAD_ACCOUNTS: u32 = ERR_BASE + 9;
    /// CPI_TIP: the tip account is not `JITO_TIP_ACCOUNTS[tip_acct_ix]` or is not writable, or the System program
    /// slot does not hold the System program.
    pub const ERR_TIP_ACCOUNT: u32 = ERR_BASE + 10;
    /// CPI_TIP: paying the tip would leave the authority below its rent-exempt minimum (or the tip exceeds its
    /// lamports). The runtime would otherwise fail the transaction with InsufficientFundsForRent after a passing AXS1.
    pub const ERR_TIP_FUNDS: u32 = ERR_BASE + 11;
    /// v3: COUNT_LAMPORTS or CPI_TIP is set but the quote account is not wSOL, so lamports and quote units would mix.
    pub const ERR_QUOTE_NOT_WSOL: u32 = ERR_BASE + 12;
    /// `LEG_ERR_BASE + i` means leg `i` (0-based) delivered nothing or its output balance went down.
    pub const LEG_ERR_BASE: u32 = ERR_BASE + 0x100;

    // ============================================================================================================
    // Structured logs (sol_log_data, one field each; see LOGS.md)
    // ============================================================================================================

    /// v2 routes only: logged just before leg i runs (nexus-arb-v2 compatible).
    pub const LEG_MARKER: [u8; 7] = *b"NXV2LEG";
    /// v2 routes only: logged after leg i delivers (nexus-arb-v2 compatible).
    pub const DELIVERED_MARKER: [u8; 7] = *b"NXV2OUT";
    /// v3 routes: one AXL1 record per completed leg.
    pub const LEG_LOG_MAGIC: [u8; 4] = *b"AXL1";
    pub const LEG_LOG_LEN: usize = 24;
    /// Both layouts: one AXS1 summary per route, at the guard, whether it passes or not.
    pub const SUMMARY_MAGIC: [u8; 4] = *b"AXS1";
    pub const SUMMARY_LEN: usize = 92;

    /// The 8 bytes logged before leg `i` of a v2 route.
    pub fn leg_marker(i: usize) -> [u8; 8] {
        let mut m = [0u8; 8];
        m[..7].copy_from_slice(&LEG_MARKER);
        m[7] = i as u8; // i < MAX_LEGS
        m
    }

    /// The 16 bytes logged after leg `i` of a v2 route delivered `amount`.
    pub fn delivered_log(i: usize, amount: u64) -> [u8; 16] {
        let mut m = [0u8; 16];
        m[..7].copy_from_slice(&DELIVERED_MARKER);
        m[7] = i as u8; // i < MAX_LEGS
        m[8..].copy_from_slice(&amount.to_le_bytes());
        m
    }

    /// One completed leg of a v3 route.
    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct LegLog {
        pub leg: u8,
        /// index into ALLOWLIST_B58
        pub venue: u8,
        /// LEG_NATIVE_IN / LEG_NATIVE_OUT
        pub flags: u8,
        /// the amount patched into the venue instruction
        pub input: u64,
        /// what the leg's output account (or the authority, for NATIVE_OUT) gained
        pub delivered: u64,
    }

    /// AXL1 record: magic[4] leg u8 venue u8 flags u8 reserved u8 input u64 delivered u64 (24 bytes, LE)
    pub fn leg_log(l: &LegLog) -> [u8; LEG_LOG_LEN] {
        let mut m = [0u8; LEG_LOG_LEN];
        m[..4].copy_from_slice(&LEG_LOG_MAGIC);
        m[4] = l.leg;
        m[5] = l.venue;
        m[6] = l.flags;
        m[8..16].copy_from_slice(&l.input.to_le_bytes());
        m[16..24].copy_from_slice(&l.delivered.to_le_bytes());
        m
    }

    pub fn decode_leg_log(b: &[u8]) -> Option<LegLog> {
        if b.len() != LEG_LOG_LEN || b[..4] != LEG_LOG_MAGIC { return None; }
        Some(LegLog { leg: b[4], venue: b[5], flags: b[6], input: u64_at(b, 8), delivered: u64_at(b, 16) })
    }

    /// The route at the guard.
    #[derive(Debug, PartialEq, Eq, Clone, Copy, Default)]
    pub struct Summary {
        /// 2 or 3
        pub layout: u8,
        /// v3 flags byte. For v2 it is synthesized: PAYER_GUARD if the trailer is present, COUNT_LAMPORTS if any
        /// leg is native.
        pub flags: u8,
        pub n_legs: u8,
        /// 0 = guard passed (the tip, if any, is paid next). Otherwise the 0x4E58xxxx code the instruction fails
        /// with right after this record.
        pub result: u32,
        pub amount_in: u64,
        pub min_profit: u64,
        /// The CPI tip computed from `gain`. It is paid only when result == 0. Always 0 without CPI_TIP.
        pub tip: u64,
        /// The g the guard compared: quote_delta + (COUNT_LAMPORTS ? lamport_delta : 0).
        pub gain: i128,
        /// quote balance after the last leg minus before the first.
        pub quote_delta: i128,
        /// authority lamports after the last leg minus at entry, before any tip. Reported even when not counted.
        pub lamport_delta: i128,
        /// Reserved, always 0 ("unknown"). It was meant to carry sol_remaining_compute_units() at the guard, but that
        /// syscall is not active on mainnet (feature 5TuppMut…; calling it aborted every route, REVIEW.md #1). The
        /// runtime's "Program … consumed N of M compute units" line gives the instruction's total.
        pub cu_remaining: u64,
    }

    /// AXS1 record (92 bytes, LE):
    /// magic[4] layout u8 flags u8 n_legs u8 reserved u8 result u32 amount_in u64 min_profit u64 tip u64
    /// gain i128 quote_delta i128 lamport_delta i128 cu_remaining u64
    pub fn summary_log(s: &Summary) -> [u8; SUMMARY_LEN] {
        let mut m = [0u8; SUMMARY_LEN];
        m[..4].copy_from_slice(&SUMMARY_MAGIC);
        m[4] = s.layout;
        m[5] = s.flags;
        m[6] = s.n_legs;
        m[8..12].copy_from_slice(&s.result.to_le_bytes());
        m[12..20].copy_from_slice(&s.amount_in.to_le_bytes());
        m[20..28].copy_from_slice(&s.min_profit.to_le_bytes());
        m[28..36].copy_from_slice(&s.tip.to_le_bytes());
        m[36..52].copy_from_slice(&s.gain.to_le_bytes());
        m[52..68].copy_from_slice(&s.quote_delta.to_le_bytes());
        m[68..84].copy_from_slice(&s.lamport_delta.to_le_bytes());
        m[84..92].copy_from_slice(&s.cu_remaining.to_le_bytes());
        m
    }

    pub fn decode_summary(b: &[u8]) -> Option<Summary> {
        if b.len() != SUMMARY_LEN || b[..4] != SUMMARY_MAGIC { return None; }
        let i128_at = |o: usize| { let mut x = [0u8; 16]; x.copy_from_slice(&b[o..o + 16]); i128::from_le_bytes(x) };
        Some(Summary {
            layout: b[4], flags: b[5], n_legs: b[6],
            result: u32::from_le_bytes([b[8], b[9], b[10], b[11]]),
            amount_in: u64_at(b, 12), min_profit: u64_at(b, 20), tip: u64_at(b, 28),
            gain: i128_at(36), quote_delta: i128_at(52), lamport_delta: i128_at(68), cu_remaining: u64_at(b, 84),
        })
    }

    // ============================================================================================================
    // Parsed route
    // ============================================================================================================

    #[derive(Debug, PartialEq, Eq)]
    pub enum ArbError {
        // ---- data (ERR_BAD_DATA unless noted) ----
        DataTooShort,
        BadVersion(u8),
        BadLegCount(usize),
        ZeroMinProfit,
        AmountOffsetOutOfRange { leg: usize },
        DataLengthMismatch { declared: usize, actual: usize },
        /// a NATIVE_IN leg that follows a token leg, or a NATIVE_OUT leg followed by a token leg
        BadNativeChain { leg: usize },
        /// v3: bits 6-7 of the flags byte
        InvalidFlags(u8),
        /// v3: SELF_SIZE / BASKET / NOOP_ON_MISS -> ERR_UNSUPPORTED
        UnsupportedFlags(u8),
        /// v3: unknown leg_flags bits, NATIVE_IN together with NATIVE_OUT, or LEG_AUTH_RO on a native leg
        BadLegFlags { leg: usize, flags: u8 },
        /// v3: n_accounts == 0
        ZeroAccounts { leg: usize },
        /// v3: tip_bps > 10_000, tip_cap < tip_floor, or tip_acct_ix > 7
        BadTipParams,
        /// v3: a native leg moves lamports the guard would ignore without COUNT_LAMPORTS
        NativeNeedsCountLamports { leg: usize },
        /// v3: PAYER_GUARD is mandatory
        PayerGuardRequired,
        /// v3: CPI_TIP pays lamports, so the gain it is computed from must count lamports (COUNT_LAMPORTS)
        TipNeedsCountLamports,
        /// v3: the instruction would need more than MAX_IX_ACCOUNTS accounts
        TooManyAccounts { needed: usize },
        // ---- accounts ----
        NotAllowlisted { leg: usize },
        NotTokenAccount,
        /// ERR_BAD_ACCOUNTS
        LastLegNotIntoQuote,
        /// ERR_BAD_ACCOUNTS
        OutputIsInput { leg: usize },
        /// ERR_BAD_ACCOUNTS (v3; a v2 route reports ERR_BAD_DATA here, as nexus-arb-v2 did)
        NativeOutNotAuthority { leg: usize },
        /// ERR_BAD_ACCOUNTS
        AuthorityNotWritable,
        /// ERR_BAD_ACCOUNTS (v3): the quote account's token owner is not the authority
        QuoteNotAuthoritys,
        /// ERR_BAD_ACCOUNTS (v3): a token leg's output account's token owner is not the authority
        OutputNotAuthoritys { leg: usize },
        /// ERR_TIP_ACCOUNT
        WrongTipAccount,
        /// ERR_QUOTE_NOT_WSOL
        QuoteNotWsol,
        // ---- execution ----
        LegDeliveredNothing { leg: usize },
        LegBalanceWentDown { leg: usize },
        /// `net` is g − tip (or g without CPI_TIP)
        ProfitBelowMinimum { net: i128, min: u64 },
        PayerLamportsDropped { drop: u64, max: u64 },
        PayerReassigned,
        TokenAccountDrained { leg: usize, drop: u64, allowed: u64 },
        TokenAccountAuthorityChanged { leg: usize },
        ForeignSigner { leg: usize },
        /// ERR_TIP_FUNDS: `lamports − tip` would be below `keep` (the authority's rent-exempt minimum), or negative
        TipExceedsBalance { tip: u64, lamports: u64, keep: u64 },
    }

    /// The Custom code the chain reports for an error.
    pub fn error_code(e: &ArbError) -> u32 {
        use ArbError::*;
        match e {
            LegDeliveredNothing { leg } | LegBalanceWentDown { leg } => LEG_ERR_BASE + *leg as u32,
            ProfitBelowMinimum { .. } => ERR_PROFIT,
            PayerLamportsDropped { .. } | PayerReassigned => ERR_PAYER_GUARD,
            TokenAccountDrained { .. } | TokenAccountAuthorityChanged { .. } => ERR_TOKEN_GUARD,
            ForeignSigner { .. } => ERR_FOREIGN_SIGNER,
            NotAllowlisted { .. } => ERR_NOT_ALLOWLISTED,
            NotTokenAccount => ERR_NOT_TOKEN_ACCOUNT,
            UnsupportedFlags(_) => ERR_UNSUPPORTED,
            LastLegNotIntoQuote | OutputIsInput { .. } | NativeOutNotAuthority { .. } | AuthorityNotWritable
            | QuoteNotAuthoritys | OutputNotAuthoritys { .. } => ERR_BAD_ACCOUNTS,
            WrongTipAccount => ERR_TIP_ACCOUNT,
            TipExceedsBalance { .. } => ERR_TIP_FUNDS,
            QuoteNotWsol => ERR_QUOTE_NOT_WSOL,
            DataTooShort | BadVersion(_) | BadLegCount(_) | ZeroMinProfit | AmountOffsetOutOfRange { .. }
            | DataLengthMismatch { .. } | BadNativeChain { .. } | InvalidFlags(_) | BadLegFlags { .. }
            | ZeroAccounts { .. } | BadTipParams | NativeNeedsCountLamports { .. } | PayerGuardRequired
            | TipNeedsCountLamports | TooManyAccounts { .. } => ERR_BAD_DATA,
        }
    }

    #[derive(Debug, PartialEq, Eq, Clone, Copy, Default)]
    pub struct LegMeta {
        pub n_accounts: usize,
        pub amount_offset: usize,
        /// where this leg's data starts in the instruction data
        pub data_start: usize,
        pub data_len: usize,
        /// the leg spends the authority's lamports (leg 0: `amount_in`; later: the previous NATIVE_OUT leg's output)
        pub native_in: bool,
        /// the leg's output is the authority's lamport gain; its output slot must be the authority
        pub native_out: bool,
        /// v3 LEG_AUTH_RO: the venue gets the authority as a read-only signer. Always false for v2.
        pub auth_ro: bool,
    }

    impl LegMeta {
        /// The normalized leg flags (LEG_NATIVE_IN / LEG_NATIVE_OUT / LEG_AUTH_RO), whichever layout the leg came from.
        pub fn flags(&self) -> u8 {
            (if self.native_in { LEG_NATIVE_IN } else { 0 })
                | (if self.native_out { LEG_NATIVE_OUT } else { 0 })
                | (if self.auth_ro { LEG_AUTH_RO } else { 0 })
        }
    }

    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct TipParams {
        /// share of the gain g, in basis points (0..=10_000)
        pub bps: u16,
        /// the minimum tip in lamports. It is paid even when bps × g is smaller.
        pub floor: u64,
        /// the maximum tip in lamports (>= floor)
        pub cap: u64,
        /// index into JITO_TIP_ACCOUNTS_B58 (0..=7)
        pub account_ix: u8,
    }

    #[derive(Debug, PartialEq, Eq, Clone)]
    pub struct Route {
        /// V2 or V3
        pub layout: u8,
        /// The v3 flags. For v2 they are synthesized: PAYER_GUARD iff the trailer is present, COUNT_LAMPORTS iff any
        /// leg is native. That is exactly nexus-arb-v2's guard behaviour.
        pub flags: u8,
        pub amount_in: u64,
        pub min_profit: u64,
        /// `Some` iff PAYER_GUARD (v3) / the trailer (v2)
        pub max_payer_lamport_drop: Option<u64>,
        /// `Some` iff CPI_TIP (v3 only)
        pub tip: Option<TipParams>,
        pub n_legs: usize,
        /// The first `n_legs` entries are the legs. The rest are `LegMeta::default()`. Parsing allocates nothing.
        pub leg_slots: [LegMeta; MAX_LEGS],
    }

    impl Route {
        pub fn legs(&self) -> &[LegMeta] { &self.leg_slots[..self.n_legs] }
        pub fn count_lamports(&self) -> bool { self.flags & COUNT_LAMPORTS != 0 }
        pub fn has_native(&self) -> bool { self.legs().iter().any(|l| l.native_in || l.native_out) }
        /// Index of the first account after the legs: authority, quote, then per leg (output, program, n accounts).
        /// At most 2 + 8 × 257, so it cannot overflow.
        pub fn legs_end(&self) -> usize { 2 + self.legs().iter().map(|l| 2 + l.n_accounts).sum::<usize>() }
        /// Accounts the instruction must carry: the legs, then with CPI_TIP the System program and the tip account.
        pub fn required_accounts(&self) -> usize { self.legs_end() + if self.tip.is_some() { 2 } else { 0 } }
        pub fn max_leg_accounts(&self) -> usize { self.legs().iter().map(|l| l.n_accounts).max().unwrap_or(0) }
        pub fn max_leg_data(&self) -> usize { self.legs().iter().map(|l| l.data_len).max().unwrap_or(0) }
    }

    /// nexus-arb-v2's free functions, kept for callers that use them.
    pub fn required_accounts(route: &Route) -> usize { route.required_accounts() }
    pub fn has_native(route: &Route) -> bool { route.has_native() }

    pub(crate) fn u64_at(d: &[u8], o: usize) -> u64 {
        let mut b = [0u8; 8];
        b.copy_from_slice(&d[o..o + 8]);
        u64::from_le_bytes(b)
    }

    fn u16_at(d: &[u8], o: usize) -> u16 { u16::from_le_bytes([d[o], d[o + 1]]) }

    /// Parse and fully validate the instruction data before anything is invoked. Byte 0 picks the layout.
    pub fn parse(data: &[u8]) -> Result<Route, ArbError> {
        match data.first() {
            None => Err(ArbError::DataTooShort),
            Some(&V2) => parse_v2(data),
            Some(&V3) => parse_v3(data),
            Some(&v) => Err(ArbError::BadVersion(v)),
        }
    }

    /// Native lamports only chain into native lamports. A token leg can never feed a NATIVE_IN leg, and a
    /// NATIVE_OUT leg is either last or feeds a NATIVE_IN leg.
    fn check_native_chain(legs: &[LegMeta]) -> Result<(), ArbError> {
        let n = legs.len();
        for i in 0..n {
            if legs[i].native_in && i > 0 && !legs[i - 1].native_out { return Err(ArbError::BadNativeChain { leg: i }); }
            if legs[i].native_out && i + 1 < n && !legs[i + 1].native_in { return Err(ArbError::BadNativeChain { leg: i }); }
            if !legs[i].native_in && i > 0 && legs[i - 1].native_out { return Err(ArbError::BadNativeChain { leg: i }); }
        }
        Ok(())
    }

    /// The v2 layout, parsed exactly as nexus-arb-v2 parsed it (a property test compares this with a verbatim copy of
    /// nexus-arb-v2's parser on arbitrary input).
    fn parse_v2(data: &[u8]) -> Result<Route, ArbError> {
        if data.len() < HEADER_LEN { return Err(ArbError::DataTooShort); }
        if data[0] != V2 { return Err(ArbError::BadVersion(data[0])); }
        let n = data[1] as usize;
        if n == 0 || n > MAX_LEGS { return Err(ArbError::BadLegCount(n)); }
        let amount_in = u64_at(data, 2);
        let min_profit = u64_at(data, 10);
        if min_profit == 0 { return Err(ArbError::ZeroMinProfit); }
        let meta_end = HEADER_LEN + n * LEG_META_LEN;
        if data.len() < meta_end { return Err(ArbError::DataTooShort); }
        let mut legs = [LegMeta::default(); MAX_LEGS];
        let mut cursor = meta_end;
        for (i, leg) in legs.iter_mut().enumerate().take(n) {
            let m = &data[HEADER_LEN + i * LEG_META_LEN..HEADER_LEN + (i + 1) * LEG_META_LEN];
            let data_len = u16::from_le_bytes([m[2], m[3]]) as usize;
            let amount_offset = m[1] as usize;
            if amount_offset.checked_add(8).map_or(true, |end| end > data_len) {
                return Err(ArbError::AmountOffsetOutOfRange { leg: i });
            }
            *leg = LegMeta {
                n_accounts: (m[0] & N_ACCOUNTS_MASK) as usize,
                amount_offset,
                data_start: cursor,
                data_len,
                native_in: m[0] & NATIVE_IN != 0,
                native_out: m[0] & NATIVE_OUT != 0,
                auth_ro: false,
            };
            cursor = cursor.checked_add(data_len).ok_or(ArbError::DataTooShort)?;
        }
        check_native_chain(&legs[..n])?;
        let max_payer_lamport_drop = if data.len() == cursor {
            None
        } else if cursor.checked_add(GUARD_TRAILER_LEN) == Some(data.len()) {
            Some(u64_at(data, cursor))
        } else {
            return Err(ArbError::DataLengthMismatch { declared: cursor, actual: data.len() });
        };
        let mut route = Route { layout: V2, flags: 0, amount_in, min_profit, max_payer_lamport_drop, tip: None, n_legs: n, leg_slots: legs };
        if route.max_payer_lamport_drop.is_some() { route.flags |= PAYER_GUARD; }
        if route.has_native() { route.flags |= COUNT_LAMPORTS; }
        Ok(route)
    }

    fn need(data: &[u8], end: usize) -> Result<(), ArbError> {
        if data.len() < end { Err(ArbError::DataTooShort) } else { Ok(()) }
    }

    /// The v3 layout (README.md has the byte-by-byte table).
    fn parse_v3(data: &[u8]) -> Result<Route, ArbError> {
        need(data, V3_HEADER_LEN)?;
        let flags = data[1];
        if flags & INVALID_FLAGS != 0 { return Err(ArbError::InvalidFlags(flags)); }
        if flags & RESERVED_FEATURES != 0 { return Err(ArbError::UnsupportedFlags(flags)); }
        // REVIEW.md #2: every venue gets the wallet as a signer, so the payer guard is not optional
        if flags & PAYER_GUARD == 0 { return Err(ArbError::PayerGuardRequired); }
        // REVIEW.md #4: the tip is paid in lamports, so lamports lost inside the legs must count against the gain
        if flags & CPI_TIP != 0 && flags & COUNT_LAMPORTS == 0 { return Err(ArbError::TipNeedsCountLamports); }
        let n = data[2] as usize;
        if n == 0 || n > MAX_LEGS { return Err(ArbError::BadLegCount(n)); }
        let amount_in = u64_at(data, 3);
        let min_profit = u64_at(data, 11);
        if min_profit == 0 { return Err(ArbError::ZeroMinProfit); }
        let mut c = V3_HEADER_LEN;
        need(data, c + V3_GUARD_LEN)?;
        let max_payer_lamport_drop = Some(u64_at(data, c));
        c += V3_GUARD_LEN;
        let tip = if flags & CPI_TIP != 0 {
            need(data, c + V3_TIP_LEN)?;
            let t = TipParams { bps: u16_at(data, c), floor: u64_at(data, c + 2), cap: u64_at(data, c + 10), account_ix: data[c + 18] };
            c += V3_TIP_LEN;
            if t.bps > MAX_TIP_BPS || t.cap < t.floor || t.account_ix as usize >= JITO_TIP_ACCOUNTS_B58.len() {
                return Err(ArbError::BadTipParams);
            }
            Some(t)
        } else {
            None
        };
        let meta_start = c;
        let meta_end = meta_start + n * V3_LEG_META_LEN; // <= 19 + 8 + 19 + 40: no overflow
        need(data, meta_end)?;
        let mut legs = [LegMeta::default(); MAX_LEGS];
        let mut cursor = meta_end;
        for (i, leg) in legs.iter_mut().enumerate().take(n) {
            let m = &data[meta_start + i * V3_LEG_META_LEN..meta_start + (i + 1) * V3_LEG_META_LEN];
            let n_accounts = m[0] as usize;
            if n_accounts == 0 { return Err(ArbError::ZeroAccounts { leg: i }); }
            let leg_flags = m[1];
            // unknown bits; REVIEW.md #6: one leg both NATIVE_IN and NATIVE_OUT ("delivered" would be the net
            // lamport change); a read-only authority cannot move its lamports, so AUTH_RO excludes the native flags
            let native = leg_flags & (LEG_NATIVE_IN | LEG_NATIVE_OUT);
            if leg_flags & !LEG_FLAGS_KNOWN != 0
                || native == LEG_NATIVE_IN | LEG_NATIVE_OUT
                || (native != 0 && leg_flags & LEG_AUTH_RO != 0)
            {
                return Err(ArbError::BadLegFlags { leg: i, flags: leg_flags });
            }
            let amount_offset = m[2] as usize;
            let data_len = u16::from_le_bytes([m[3], m[4]]) as usize;
            if amount_offset + 8 > data_len { return Err(ArbError::AmountOffsetOutOfRange { leg: i }); }
            *leg = LegMeta {
                n_accounts,
                amount_offset,
                data_start: cursor,
                data_len,
                native_in: leg_flags & LEG_NATIVE_IN != 0,
                native_out: leg_flags & LEG_NATIVE_OUT != 0,
                auth_ro: leg_flags & LEG_AUTH_RO != 0,
            };
            cursor += data_len; // <= 89 + 8 × 65_535: no overflow
        }
        check_native_chain(&legs[..n])?;
        if flags & COUNT_LAMPORTS == 0 {
            if let Some(i) = legs[..n].iter().position(|l| l.native_in || l.native_out) {
                return Err(ArbError::NativeNeedsCountLamports { leg: i });
            }
        }
        if data.len() != cursor { return Err(ArbError::DataLengthMismatch { declared: cursor, actual: data.len() }); }
        let route = Route { layout: V3, flags, amount_in, min_profit, max_payer_lamport_drop, tip, n_legs: n, leg_slots: legs };
        // the runtime refuses a larger instruction before the program runs; an encoder that checks with `parse`
        // learns it here
        let needed = route.required_accounts();
        if needed > MAX_IX_ACCOUNTS { return Err(ArbError::TooManyAccounts { needed }); }
        Ok(route)
    }

    // ============================================================================================================
    // Execution accounting
    // ============================================================================================================

    /// What a leg delivered, from its output account's own balances. No estimate and no haircut.
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

    /// The guard's gain, exact in i128. Each delta lies in ±(2^64 − 1), so |g| < 2^65.
    pub fn gain(quote_before: u64, quote_after: u64, lamports_before: u64, lamports_after: u64, count_lamports: bool) -> i128 {
        let dq = quote_after as i128 - quote_before as i128;
        if count_lamports { dq + (lamports_after as i128 - lamports_before as i128) } else { dq }
    }

    /// tip = min(cap, max(floor, ⌊g × bps / 10_000⌋)). A non-positive g gives the floor (then the cap). With
    /// |g| < 2^65 and bps <= 10^4 the product is < 2^79, so i128 cannot overflow. The result lies in
    /// [min(floor, cap), cap], so it fits in a u64.
    pub fn cpi_tip(g: i128, p: &TipParams) -> u64 {
        let share = if g > 0 { g.saturating_mul(p.bps as i128) / BPS_DENOMINATOR } else { 0 };
        let floored = share.max(p.floor as i128);
        floored.min(p.cap as i128) as u64
    }

    /// The end-of-route guard: g − tip >= min_profit (tip = 0 without CPI_TIP). It is exact in i128 because
    /// g − tip > −2^66.
    pub fn check_guard(g: i128, min_profit: u64, tip: u64) -> Result<(), ArbError> {
        let net = g - tip as i128;
        if net < min_profit as i128 { return Err(ArbError::ProfitBelowMinimum { net, min: min_profit }); }
        Ok(())
    }

    /// CPI_TIP funds (REVIEW.md #5): after paying `tip` out of `lamports` the authority must keep at least `keep`
    /// (its rent-exempt minimum), or the runtime fails the whole transaction with InsufficientFundsForRent after the
    /// program logged a passing summary. A zero tip moves nothing and always passes.
    pub fn check_tip_funds(tip: u64, lamports: u64, keep: u64) -> Result<(), ArbError> {
        if tip == 0 { return Ok(()); }
        match lamports.checked_sub(tip) {
            Some(rest) if rest >= keep => Ok(()),
            _ => Err(ArbError::TipExceedsBalance { tip, lamports, keep }),
        }
    }

    /// Rent-exempt minimum of an account with `data_len` bytes, from the Rent sysvar's raw fields, in integer maths
    /// only (the SBF build carries no soft-float code). Exact for the two thresholds clusters use, 2.0 (legacy,
    /// lamports_per_byte_year 3480) and 1.0 (SIMD-0194, lamports_per_byte 6960): both give 890,880 for 0 bytes. Any
    /// other threshold up to 2.0 is rounded UP to 2.0 (positive IEEE-754 doubles order like their bit patterns), so
    /// the result never under-states the minimum; a threshold above 2.0, a negative one or an overflow gives `None`.
    pub fn rent_exempt_minimum(lamports_per_byte: u64, exemption_threshold_le: [u8; 8], data_len: u64) -> Option<u64> {
        const ONE: u64 = 0x3FF0_0000_0000_0000; // 1.0f64
        const TWO: u64 = 0x4000_0000_0000_0000; // 2.0f64
        let bits = u64::from_le_bytes(exemption_threshold_le);
        let factor = if bits == ONE { 1 } else if bits <= TWO { 2 } else { return None };
        128u64.checked_add(data_len)?.checked_mul(lamports_per_byte)?.checked_mul(factor)
    }

    /// nexus-arb-v2's profit check on the quote account alone. Equal to `check_guard(gain(.., false), min, 0)`.
    pub fn check_profit(before: u64, after: u64, min_profit: u64) -> Result<u64, ArbError> {
        let net = after as i128 - before as i128;
        if net < min_profit as i128 { return Err(ArbError::ProfitBelowMinimum { net, min: min_profit }); }
        Ok(net as u64)
    }

    /// nexus-arb-v2's check for a route with native legs: quote tokens plus authority lamports.
    pub fn check_profit_native(q_before: u64, q_after: u64, l_before: u64, l_after: u64, min_profit: u64) -> Result<u64, ArbError> {
        let net = gain(q_before, q_after, l_before, l_after, true);
        if net < min_profit as i128 { return Err(ArbError::ProfitBelowMinimum { net, min: min_profit }); }
        Ok(net as u64)
    }

    pub fn is_allowlisted(key: &[u8; 32], allow: &[[u8; 32]]) -> bool { allow.iter().any(|a| a == key) }

    // ---- payer guard ---------------------------------------------------------------------------------------------

    /// The authority's native account, as the guard compares it.
    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct PayerState {
        pub lamports: u64,
        pub owner: [u8; 32],
        pub data_len: usize,
    }

    /// The authority at entry against now. It may lose at most `max_drop + tip` lamports (the CPI tip is the
    /// program's own payment), and its owner and data length must not change. A lamport GAIN is always fine.
    pub fn check_payer_guard(before: &PayerState, after: &PayerState, max_drop: u64, tip: u64) -> Result<(), ArbError> {
        if after.owner != before.owner || after.data_len != before.data_len { return Err(ArbError::PayerReassigned); }
        if let Some(drop) = before.lamports.checked_sub(after.lamports) {
            // saturating: when max_drop + tip > u64::MAX every possible drop is allowed anyway
            let allowed = max_drop.saturating_add(tip);
            if drop > allowed { return Err(ArbError::PayerLamportsDropped { drop, max: allowed }); }
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

    /// The token account's owner field (`data[32..64]`) is `authority`. The caller has checked the account belongs
    /// to a token program. REVIEW.md #7: a v3 route's quote and token outputs must be the authority's own.
    pub fn token_owner_is(data: &[u8], authority: &[u8; 32]) -> bool { data.len() >= 72 && data[32..64] == authority[..] }

    #[derive(Debug, PartialEq, Eq, Clone, Copy)]
    pub struct TokenView {
        pub amount: u64,
        pub auth: [u8; AUTH_FIELDS_LEN],
    }

    /// `Some` iff `data` (owned by a token program; the caller checks that) is an initialized token account whose
    /// owner field is `authority`. Mints (82 bytes, or AccountType 1) and multisigs are not token accounts.
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

    /// One authority-owned token account across one leg. `after == None` means it is no longer an authority-owned
    /// token account (closed, reassigned, or its owner changed).
    pub fn check_token_guard(leg: usize, before: &TokenView, after: Option<&TokenView>, allowed_drop: u64) -> Result<(), ArbError> {
        let after = after.ok_or(ArbError::TokenAccountAuthorityChanged { leg })?;
        if after.auth != before.auth { return Err(ArbError::TokenAccountAuthorityChanged { leg }); }
        if let Some(drop) = before.amount.checked_sub(after.amount) {
            if drop > allowed_drop { return Err(ArbError::TokenAccountDrained { leg, drop, allowed: allowed_drop }); }
        }
        Ok(())
    }

    // ============================================================================================================
    // Reference encoders. The engine's builder must produce byte-identical output, and the tests pin fixtures.
    // ============================================================================================================

    /// v2: nexus-arb-v2's encoder. `legs` = (n_accounts byte incl. NATIVE flags, amount_offset, data).
    pub fn encode(amount_in: u64, min_profit: u64, legs: &[(u8, u8, &[u8])]) -> Vec<u8> {
        let mut out = vec![V2, legs.len() as u8];
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

    /// v2 guarded: `encode(..)` followed by the 8-byte trailer.
    pub fn encode_guarded(amount_in: u64, min_profit: u64, legs: &[(u8, u8, &[u8])], max_payer_lamport_drop: u64) -> Vec<u8> {
        let mut out = encode(amount_in, min_profit, legs);
        out.extend_from_slice(&max_payer_lamport_drop.to_le_bytes());
        out
    }

    /// One v3 leg for the encoder.
    #[derive(Debug, Clone, Copy)]
    pub struct LegSpec<'a> {
        pub n_accounts: u8,
        /// LEG_NATIVE_IN / LEG_NATIVE_OUT
        pub flags: u8,
        pub amount_offset: u8,
        pub data: &'a [u8],
    }

    /// v3 encoder. The PAYER_GUARD and CPI_TIP bits come from the two Options. `other_flags` supplies the remaining
    /// bits (COUNT_LAMPORTS, and the reserved bits for negative tests). It encodes what it is given, including routes
    /// the parser refuses (no guard, a tip without COUNT_LAMPORTS, ...), so negative tests can build them; a builder
    /// must run `parse` on its output.
    pub fn encode_v3(other_flags: u8, amount_in: u64, min_profit: u64, max_payer_lamport_drop: Option<u64>, tip: Option<TipParams>, legs: &[LegSpec]) -> Vec<u8> {
        let mut flags = other_flags & !(PAYER_GUARD | CPI_TIP);
        if max_payer_lamport_drop.is_some() { flags |= PAYER_GUARD; }
        if tip.is_some() { flags |= CPI_TIP; }
        let mut out = vec![V3, flags, legs.len() as u8];
        out.extend_from_slice(&amount_in.to_le_bytes());
        out.extend_from_slice(&min_profit.to_le_bytes());
        if let Some(d) = max_payer_lamport_drop { out.extend_from_slice(&d.to_le_bytes()); }
        if let Some(t) = tip {
            out.extend_from_slice(&t.bps.to_le_bytes());
            out.extend_from_slice(&t.floor.to_le_bytes());
            out.extend_from_slice(&t.cap.to_le_bytes());
            out.push(t.account_ix);
        }
        for l in legs {
            out.push(l.n_accounts);
            out.push(l.flags);
            out.push(l.amount_offset);
            out.extend_from_slice(&(l.data.len() as u16).to_le_bytes());
        }
        for l in legs { out.extend_from_slice(l.data); }
        out
    }
}

#[cfg(test)]
mod v2_reference;

#[cfg(test)]
mod tests;

// ---------------------------------------------------------------------------------------------------------------
// On-chain entrypoint, built with `--features onchain`. Everything above it is runtime-free.
// ---------------------------------------------------------------------------------------------------------------
#[cfg(feature = "onchain")]
pub mod onchain {
    use super::logic::*;
    use solana_program::{
        account_info::AccountInfo,
        entrypoint::ProgramResult,
        instruction::{AccountMeta, Instruction},
        log::sol_log_data,
        program::invoke_unchecked,
        program_error::ProgramError,
        pubkey::Pubkey,
    };

    /// Decode a list of base58 keys at compile time. A malformed literal fails the build.
    const fn keys<const N: usize>(b58: [&str; N]) -> [Pubkey; N] {
        let mut out = [Pubkey::new_from_array([0u8; 32]); N];
        let mut i = 0;
        while i < N {
            out[i] = Pubkey::from_str_const(b58[i]);
            i += 1;
        }
        out
    }

    /// Only these venue programs may be invoked. A caller cannot substitute an arbitrary program.
    pub const ALLOWLIST: [Pubkey; 12] = keys(ALLOWLIST_B58);
    pub const JITO_TIP_ACCOUNTS: [Pubkey; 8] = keys(JITO_TIP_ACCOUNTS_B58);
    const TOKEN: Pubkey = Pubkey::from_str_const(TOKEN_PROGRAM_B58);
    const TOKEN_2022: Pubkey = Pubkey::from_str_const(TOKEN_2022_PROGRAM_B58);
    const SYSTEM_PROGRAM: Pubkey = Pubkey::from_str_const(SYSTEM_PROGRAM_B58);
    const WSOL_MINT: Pubkey = Pubkey::from_str_const(WSOL_MINT_B58);
    /// Authority-owned writable token accounts a leg normally carries: 2 (in and out). One allocation is reused
    /// across all legs, because the bump allocator never frees.
    const SNAP_CAPACITY: usize = 8;

    solana_program::entrypoint!(process_instruction);

    fn custom(code: u32) -> ProgramError { ProgramError::Custom(code) }
    fn arb(e: ArbError) -> ProgramError { custom(error_code(&e)) }

    fn venue_id(key: &Pubkey) -> Option<u8> { ALLOWLIST.iter().position(|a| a == key).map(|i| i as u8) }

    /// SPL token account: the amount is a u64 at offset 64. The account must belong to a token program, or a
    /// crafted account could pass the guard without holding real tokens.
    fn token_amount(ai: &AccountInfo) -> Result<u64, ProgramError> {
        if *ai.owner != TOKEN && *ai.owner != TOKEN_2022 { return Err(arb(ArbError::NotTokenAccount)); }
        let d = ai.try_borrow_data()?;
        if d.len() < 72 { return Err(ProgramError::InvalidAccountData); }
        Ok(u64_at(&d, 64))
    }

    /// v3 (REVIEW.md #7): `token_amount` of a token account whose owner field is the authority; `not_ours` otherwise.
    fn owned_token_amount(ai: &AccountInfo, authority: &[u8; 32], not_ours: ArbError) -> Result<u64, ProgramError> {
        if *ai.owner != TOKEN && *ai.owner != TOKEN_2022 { return Err(arb(ArbError::NotTokenAccount)); }
        let d = ai.try_borrow_data()?;
        if d.len() < 72 { return Err(ProgramError::InvalidAccountData); }
        if !token_owner_is(&d, authority) { return Err(arb(not_ours)); }
        Ok(u64_at(&d, 64))
    }

    /// The quote account's mint is wrapped SOL. The caller has already checked that it is a token account.
    fn is_wsol(ai: &AccountInfo) -> Result<bool, ProgramError> {
        let d = ai.try_borrow_data()?;
        Ok(d.len() >= 32 && d[..32] == WSOL_MINT.as_ref()[..])
    }

    fn payer_state(ai: &AccountInfo) -> PayerState {
        PayerState { lamports: ai.lamports(), owner: ai.owner.to_bytes(), data_len: ai.data_len() }
    }

    /// `Some` iff `ai` is now a token-program-owned, initialized token account whose owner field is the authority.
    /// Read after a CPI, `None` means it was closed, reassigned or re-owned.
    fn payer_token(ai: &AccountInfo, authority: &[u8; 32]) -> Result<Option<TokenView>, ProgramError> {
        if *ai.owner != TOKEN && *ai.owner != TOKEN_2022 { return Ok(None); }
        let d = ai.try_borrow_data()?;
        Ok(payer_token_view(&d, authority))
    }

    /// The authority's rent-exempt minimum, from the Rent sysvar. It uses `sol_get_rent_sysvar`, which every cluster
    /// registers unconditionally (`Rent::get()` now goes through `sol_get_sysvar`, which is feature-gated), and reads
    /// the raw 24-byte `Rent` (lamports_per_byte u64, exemption_threshold f64 bits, burn_percent u8, padding) so no
    /// float code is linked. About 100 CU; called only when a CPI tip is about to be paid.
    fn authority_rent_minimum(data_len: usize) -> Result<u64, ProgramError> {
        #[allow(unused_mut)]
        let mut raw = [0u64; 3];
        #[cfg(target_os = "solana")]
        {
            // SAFETY: `raw` is 24 bytes, 8-aligned: exactly one `Rent` value, which the syscall writes.
            #[allow(deprecated)]
            let rc = unsafe { solana_program::syscalls::sol_get_rent_sysvar(raw.as_mut_ptr() as *mut u8) };
            if rc != 0 { return Err(ProgramError::UnsupportedSysvar); }
        }
        #[cfg(not(target_os = "solana"))]
        { raw = [3_480, 2.0f64.to_bits(), 50]; } // host builds only: the legacy mainnet values
        rent_exempt_minimum(raw[0], raw[1].to_le_bytes(), data_len as u64).ok_or(ProgramError::UnsupportedSysvar)
    }

    /// System Program Transfer (instruction 2) by CPI, from the authority, which signed the transaction.
    fn system_transfer<'a>(from: &AccountInfo<'a>, to: &AccountInfo<'a>, lamports: u64) -> ProgramResult {
        let mut data = Vec::with_capacity(12);
        data.extend_from_slice(&2u32.to_le_bytes());
        data.extend_from_slice(&lamports.to_le_bytes());
        let ix = Instruction {
            program_id: SYSTEM_PROGRAM,
            accounts: vec![AccountMeta::new(*from.key, true), AccountMeta::new(*to.key, false)],
            data,
        };
        // no RefCell borrow is held here, so the unchecked variant is safe
        invoke_unchecked(&ix, &[from.clone(), to.clone()])
    }

    pub fn process_instruction(_program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
        let route = parse(data).map_err(arb)?;
        let v3 = route.layout == V3;
        if accounts.len() < route.required_accounts() { return Err(ProgramError::NotEnoughAccountKeys); }

        let authority = &accounts[0];
        if !authority.is_signer { return Err(ProgramError::MissingRequiredSignature); }
        if (route.has_native() || route.tip.is_some()) && !authority.is_writable {
            return Err(arb(ArbError::AuthorityNotWritable));
        }
        let authority_bytes = authority.key.to_bytes();
        let quote = &accounts[1];
        // v3: the profit must land in the authority's own account (REVIEW.md #7)
        let quote_before = if v3 { owned_token_amount(quote, &authority_bytes, ArbError::QuoteNotAuthoritys)? } else { token_amount(quote)? };
        if v3 && route.flags & (COUNT_LAMPORTS | CPI_TIP) != 0 && !is_wsol(quote)? {
            return Err(arb(ArbError::QuoteNotWsol));
        }

        // CPI_TIP accounts are checked before any venue runs, so a wrong tip account costs no venue CU
        let legs_end = route.legs_end();
        let tip_account = match route.tip {
            Some(t) => {
                let system = &accounts[legs_end];
                let tip_acct = &accounts[legs_end + 1];
                if *system.key != SYSTEM_PROGRAM || *tip_acct.key != JITO_TIP_ACCOUNTS[t.account_ix as usize] || !tip_acct.is_writable {
                    return Err(arb(ArbError::WrongTipAccount));
                }
                Some(tip_acct)
            }
            None => None,
        };

        let lamports_before = authority.lamports();
        // always Some for v3 (the parser requires PAYER_GUARD); for v2 iff the trailer is present
        let guard = route.max_payer_lamport_drop;
        let payer_before = guard.map(|_| payer_state(authority));
        // (index into the leg's accounts, view before the leg). Vec::new() does not allocate.
        let mut snaps: Vec<(usize, TokenView)> = if guard.is_some() { Vec::with_capacity(SNAP_CAPACITY) } else { Vec::new() };
        // One CPI instruction is reused for every leg, so its account and data vectors are allocated once. The heap
        // still grows per leg: solana-cpi's invoke clones the instruction into a StableInstruction on every call
        // (measured harmless: 255 metas fit the default 32 KiB heap, REVIEW.md #10).
        let mut ix = Instruction {
            program_id: SYSTEM_PROGRAM,
            accounts: Vec::with_capacity(route.max_leg_accounts()),
            data: Vec::with_capacity(route.max_leg_data()),
        };
        // A v3 leg must not hand a venue any signer but the authority. A v2 leg is checked only when guarded, as in
        // nexus-arb-v2.
        let check_signers = v3 || guard.is_some();

        let n = route.n_legs;
        let mut cursor = 2usize;
        let mut input = route.amount_in;
        // the account each leg spends from: leg 0 the quote account, leg i leg i-1's output account
        let mut input_acct: &AccountInfo = quote;
        for (i, leg) in route.legs().iter().enumerate() {
            // bounded by required_accounts(), which was checked above
            let out_acct = &accounts[cursor];
            let program = &accounts[cursor + 1];
            let leg_end = cursor + 2 + leg.n_accounts;
            let leg_accounts = &accounts[cursor + 2..leg_end];
            cursor = leg_end;

            let venue = venue_id(program.key).ok_or_else(|| arb(ArbError::NotAllowlisted { leg: i }))?;

            // account structure (aliasing)
            if leg.native_out {
                // the output is the authority's lamport gain, so the output slot must name the authority
                if out_acct.key != authority.key {
                    return Err(if v3 { arb(ArbError::NativeOutNotAuthority { leg: i }) } else { custom(ERR_BAD_DATA) });
                }
            } else {
                if i + 1 == n && out_acct.key != quote.key { return Err(arb(ArbError::LastLegNotIntoQuote)); }
                if !leg.native_in && out_acct.key == input_acct.key { return Err(arb(ArbError::OutputIsInput { leg: i })); }
            }

            if check_signers {
                snaps.clear();
                for (j, a) in leg_accounts.iter().enumerate() {
                    // the guard watches only the authority, so a second signer would go unguarded
                    if a.is_signer && a.key != authority.key { return Err(arb(ArbError::ForeignSigner { leg: i })); }
                    // the runtime already stops a venue from changing a read-only account
                    if guard.is_none() || !a.is_writable { continue; }
                    if let Some(v) = payer_token(a, &authority_bytes)? { snaps.push((j, v)); }
                }
            }

            let before = if leg.native_out {
                authority.lamports()
            } else if v3 {
                // v3: every token leg delivers into one of the authority's own accounts (REVIEW.md #7)
                owned_token_amount(out_acct, &authority_bytes, ArbError::OutputNotAuthoritys { leg: i })?
            } else {
                token_amount(out_acct)?
            };
            // v2: name the leg BEFORE invoking it, because a venue error aborts inside the CPI with the venue's own
            // code. v3 needs no marker: the failing leg is the number of AXL1 records logged before the failure.
            if !v3 { sol_log_data(&[&leg_marker(i)]); }
            ix.program_id = *program.key;
            ix.accounts.clear();
            // LEG_AUTH_RO (v3): the venue sees the authority as a read-only signer, so the runtime itself refuses any
            // debit or assign of the wallet inside this leg (REVIEW.md #14)
            let auth_ro = leg.auth_ro;
            ix.accounts.extend(leg_accounts.iter().map(|a| AccountMeta {
                pubkey: *a.key,
                is_signer: a.is_signer,
                is_writable: a.is_writable && !(auth_ro && a.key == authority.key),
            }));
            ix.data.clear();
            ix.data.extend_from_slice(&data[leg.data_start..leg.data_start + leg.data_len]);
            if !patch_amount(&mut ix.data, leg.amount_offset, input) { return Err(custom(ERR_BAD_DATA)); }
            // No RefCell borrow of any account is held across this call (token_amount and payer_token drop theirs),
            // so the unchecked variant is safe. It skips an O(accounts × infos) key scan.
            invoke_unchecked(&ix, leg_accounts)?;
            let after = if leg.native_out { authority.lamports() } else { token_amount(out_acct)? };
            let got = delivered(i, before, after).map_err(arb)?;
            if v3 {
                sol_log_data(&[&leg_log(&LegLog { leg: i as u8, venue, flags: leg.flags(), input, delivered: got })]);
            } else {
                sol_log_data(&[&delivered_log(i, got)]);
            }

            if guard.is_some() {
                for (j, snap) in snaps.iter() {
                    let a = &leg_accounts[*j];
                    // a NATIVE_IN leg spends lamports, so none of our token accounts may drop in it
                    let allowed = if a.key == input_acct.key && !leg.native_in { input } else { 0 };
                    let now = payer_token(a, &authority_bytes)?;
                    check_token_guard(i, snap, now.as_ref(), allowed).map_err(arb)?;
                }
            }

            input = got;
            input_acct = out_acct;
        }

        // ---- the guard ----
        let lamports_after = authority.lamports();
        let quote_after = token_amount(quote)?;
        let quote_delta = quote_after as i128 - quote_before as i128;
        let lamport_delta = lamports_after as i128 - lamports_before as i128;
        let g = gain(quote_before, quote_after, lamports_before, lamports_after, route.count_lamports());
        let tip = route.tip.map_or(0, |p| cpi_tip(g, &p));
        // nexus-arb-v2 order: the payer guard first, then profit. The payer is checked here BEFORE the tip, against
        // max_drop alone. The tip below is a System transfer of exactly `tip` out of the authority (owner and data
        // length cannot change), so "L0 − L_end <= max_drop + tip" then holds by construction and is not re-checked.
        let mut verdict = match (guard, payer_before.as_ref()) {
            (Some(max_drop), Some(before)) => check_payer_guard(before, &payer_state(authority), max_drop, 0),
            _ => Ok(()),
        };
        if verdict.is_ok() { verdict = check_guard(g, route.min_profit, tip); }
        // the tip must leave the authority rent-exempt, or the runtime fails the transaction after AXS1 said "0"
        if verdict.is_ok() && tip > 0 { verdict = check_tip_funds(tip, lamports_after, authority_rent_minimum(authority.data_len())?); }
        sol_log_data(&[&summary_log(&Summary {
            layout: route.layout,
            flags: route.flags,
            n_legs: n as u8,
            result: verdict.as_ref().err().map_or(0, error_code),
            amount_in: route.amount_in,
            min_profit: route.min_profit,
            tip,
            gain: g,
            quote_delta,
            lamport_delta,
            // reserved: sol_remaining_compute_units is not active on mainnet (REVIEW.md #1)
            cu_remaining: 0,
        })]);
        verdict.map_err(arb)?;

        // ---- the conditional CPI tip: paid only once the guard has passed ----
        if let (Some(tip_acct), true) = (tip_account, tip > 0) {
            system_transfer(authority, tip_acct, tip)?;
        }
        Ok(())
    }
}
