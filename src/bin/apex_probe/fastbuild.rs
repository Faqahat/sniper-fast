//! v3 FAST BUILD (FRA shadow run 3: build+sign of the first copy p50 306 µs vs ~45 µs in the bench). The lib builder
//! (snipe_build::buy_message_ixs + buy_ix + build::create_ata_idempotent_ix) derives ~8 PDAs PER COPY with dalek's point
//! decompression (creator_vault is derived and not even used by the v3 buy; the wallet's volume accumulator and WSOL
//! account are re-derived every time). Here:
//!  - per run: the wallet's user_volume_accumulator + WSOL ATA, once;
//!  - per launch: the curve's ATA comes from the create tx; the curve's WSOL ATA and our token ATA are derived ONCE for all
//!    lane copies with the dip engine's fast on-curve check (arbx::fast::ata_fast, self-tested against pda::ata at start);
//!  - per copy: the instruction list by hand (no derivation), compile, and a signature with a pre-computed nonce
//!    (arbx::fast::Presigner, the dip engine's --fast-presign; each one verify_strict-ed in the start-up self-test).
//! The bytes are IDENTICAL to logic::buy_ixs (tests: fast == slow on random launches, nonce / tips / guard variants).

use crate::logic::{self, BuyCfg, Copy, GuardEnc, LaneCopy};
use arbx::build::{self, Ix, Meta};
use arbx::snipe::{self, Launch};
use arbx::snipe_build;
use arbx::tx::{pk, Pk};
use arbx::{fast, pda};
use ed25519_dalek::SigningKey;
use std::sync::Arc;

#[inline] fn w(key: Pk) -> Meta { Meta { key, signer: false, writable: true } }
#[inline] fn r(key: Pk) -> Meta { Meta { key, signer: false, writable: false } }
#[inline] fn s(key: Pk) -> Meta { Meta { key, signer: true, writable: true } }

/// the run's constants (the wallet's own PDAs, the program ids)
pub struct FastCtx {
    pub user: Pk,
    uva: Pk,
    wsol_ata: Pk,
    key: SigningKey,
    presign: Option<Arc<fast::Presigner>>,
    sysvar_rb: Pk,
}

/// a launch's mint-dependent keys, derived once for every copy
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LaunchKeys { pub mint: Pk, pub bc: Pk, pub abc: Pk, pub bc_wsol: Pk, pub user_base: Pk, pub buyback: Pk }

impl FastCtx {
    pub fn new(key: &SigningKey, user: Pk, presign: Option<Arc<fast::Presigner>>) -> FastCtx {
        FastCtx { user, uva: snipe_build::user_volume_accumulator(&user), wsol_ata: snipe_build::assoc_quote(&user), key: key.clone(), presign,
            sysvar_rb: pk("SysvarRecentB1ockHashes11111111111111111111") }
    }

    /// the launch's keys: the curve's base ATA from the create tx (create_v2), the rest derived with the fast check
    pub fn keys(&self, l: &Launch) -> LaunchKeys {
        let abc = if l.is_create_v2 && l.assoc_bonding_curve != [0u8; 32] { l.assoc_bonding_curve } else { fast::ata_fast(&l.bonding_curve, &l.mint, &pda::TOKEN_2022) };
        LaunchKeys { mint: l.mint, bc: l.bonding_curve, abc, bc_wsol: fast::ata_fast(&l.bonding_curve, &snipe_build::WSOL, &pda::TOKEN_PROGRAM),
            user_base: fast::ata_fast(&self.user, &l.mint, &pda::TOKEN_2022), buyback: l.buyback_fee_recipient }
    }

    /// == logic::buy_ixs, without one derivation
    #[allow(clippy::too_many_arguments)]
    pub fn buy_ixs(&self, k: &LaunchKeys, spend: u64, min_out: u64, cu_limit: u32, cu_price: u64, nonce: Option<Pk>, tips: &[(Pk, u64)], guard: Option<(GuardEnc, u64)>) -> Vec<Ix> {
        let u = self.user;
        let mut ixs = Vec::with_capacity(9);
        if let Some(n) = nonce { ixs.push(Ix { program: *pda::SYSTEM_PROGRAM, accounts: vec![w(n), r(self.sysvar_rb), s(u)], data: 4u32.to_le_bytes().to_vec() }); }
        for (t, lam) in tips { ixs.push(build::transfer_ix(u, *t, *lam)); }
        let extra = if tips.len() > 2 { 300 * (tips.len() as u32 - 2) } else { 0 };
        ixs.push(build::cu_limit_ix(cu_limit.saturating_add(extra).min(1_400_000)));
        if cu_price > 0 { ixs.push(build::cu_price_ix(cu_price)); }
        ixs.push(Ix { program: *pda::ATA_PROGRAM, accounts: vec![s(u), w(k.user_base), r(u), r(k.mint), r(*pda::SYSTEM_PROGRAM), r(*pda::TOKEN_2022)], data: vec![1] });
        ixs.push(Ix { program: *pda::ATA_PROGRAM, accounts: vec![s(u), w(self.wsol_ata), r(u), r(*snipe_build::WSOL), r(*pda::SYSTEM_PROGRAM), r(*pda::TOKEN_PROGRAM)], data: vec![1] });
        if let Some((g, dl)) = guard { ixs.push(logic::guard_ix(g, dl)); }
        let mut data = Vec::with_capacity(25);
        data.extend_from_slice(&snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC);
        data.extend_from_slice(&spend.to_le_bytes());
        data.extend_from_slice(&min_out.to_le_bytes());
        data.push(0);
        ixs.push(Ix { program: *snipe::PUMP, data, accounts: vec![
            r(*snipe_build::GLOBAL), r(k.mint), r(*snipe_build::WSOL), r(*pda::TOKEN_2022), r(*pda::TOKEN_PROGRAM), w(k.bc), w(k.abc), w(k.bc_wsol), s(u), w(k.user_base),
            w(self.wsol_ata), w(self.uva), r(*snipe_build::FEE_CONFIG), w(k.buyback), r(*pda::SYSTEM_PROGRAM), r(*snipe_build::EVENT_AUTHORITY), r(*snipe::PUMP)] });
        ixs
    }

    /// signed wire bytes (build::sign's layout); a pre-computed nonce when the pool has one
    pub fn sign(&self, msg: &build::Message) -> Vec<u8> {
        use ed25519_dalek::Signer;
        let sig = self.presign.as_ref().and_then(|p| p.sign(&msg.bytes)).unwrap_or_else(|| self.key.sign(&msg.bytes).to_bytes());
        let mut out = Vec::with_capacity(1 + 64 + msg.bytes.len());
        out.push(1);
        out.extend_from_slice(&sig);
        out.extend_from_slice(&msg.bytes);
        out
    }

    /// one lane's durable-nonce copy (== logic::build_lane_copies for that lane)
    pub fn lane_copy(&self, c: &BuyCfg, k: &LaunchKeys, nonce: (Pk, [u8; 32]), ln: &LaneCopy) -> Result<Copy, String> {
        let tips: Vec<(Pk, u64)> = ln.tip.filter(|t| t.1 > 0).into_iter().collect();
        let ixs = self.buy_ixs(k, c.spend, c.min_out, c.cu_limit, logic::cu_price_for(ln.prio, c.cu_limit), Some(nonce.0), &tips, c.guard);
        let msg = build::compile_v0(c.user, &ixs, nonce.1, &[], &[nonce.0, self.sysvar_rb])?;
        let raw = self.sign(&msg);
        if raw.len() > 1232 { return Err(format!("lane variant {} bytes > 1232", raw.len())); }
        let sig = logic::sig_of(&raw);
        Ok(Copy { raw, sig, paths: vec![ln.pi], tip: tips.first().map_or(0, |t| t.1) })
    }
}

/// start-up self-test: the fast on-curve check vs dalek and fast ATAs vs pda::ata (the dip engine's derive_selftest), and
/// `n` presigned signatures verify_strict-ed. Err = do not use the fast path.
pub fn selftest(ctx: &FastCtx, n: usize) -> Result<String, String> {
    let (bad, bad_ata) = fast::derive_selftest(20_000, 500);
    if bad > 0 || bad_ata > 0 { return Err(format!("fast derive disagrees with dalek: {bad} on-curve, {bad_ata} ATAs")); }
    let mut bad_sig = 0;
    if let Some(p) = &ctx.presign {
        let vk = ctx.key.verifying_key();
        for i in 0..n {
            let m: Vec<u8> = (0..900u32).map(|j| (j * 31 + i as u32) as u8).collect();
            match p.sign(&m) { Some(sg) => if vk.verify_strict(&m, &ed25519_dalek::Signature::from_bytes(&sg)).is_err() { bad_sig += 1; }, None => {} }
        }
        if bad_sig > 0 { return Err(format!("presign: {bad_sig} of {n} signatures failed verify_strict")); }
    }
    Ok(format!("FAST-BUILD self-test OK: on-curve 20000/20000 + ATA 500/500 agree with dalek{}", if ctx.presign.is_some() { format!(", {n} presigned signatures verify") } else { String::new() }))
}

// ------------------------------------------------------------------------------------------------------------------
// v3 TEMPLATES (the dip engine's arbx::fast::Template): a lane's durable-nonce copy is compiled ONCE at start from probe
// keys; per launch only the 6 mint-dependent keys, the tip account, the nonce, min_tokens_out and the deadline are
// patched in, then one (presigned) signature. No allocation-heavy compile on the hot path.
// ------------------------------------------------------------------------------------------------------------------

/// a lane's template shape: tip lamports (None = tipless), priority lamports, guard on
pub type TplKey = (Option<u64>, u64, bool);

impl FastCtx {
    /// compile a lane's template (spend + CU limit fixed for the run; the guard's encoding is the verified one)
    pub fn template(&self, spend: u64, cu_limit: u32, tip: Option<u64>, prio: u64, guard: Option<GuardEnc>) -> Result<fast::Template, String> {
        let k = LaunchKeys { mint: fast::probe_var(0), bc: fast::probe_var(1), abc: fast::probe_var(2), bc_wsol: fast::probe_var(3), user_base: fast::probe_var(4), buyback: fast::probe_var(5) };
        let tips: Vec<(Pk, u64)> = tip.filter(|t| *t > 0).map(|l| vec![(fast::probe_tip(0), l)]).unwrap_or_default();
        let ixs = self.buy_ixs(&k, spend, fast::PROBE_MIN_OUT, cu_limit, logic::cu_price_for(prio, cu_limit), Some(fast::probe_nonce()), &tips, guard.map(|g| (g, fast::PROBE_DEADLINE)));
        let msg = build::compile_v0(self.user, &ixs, fast::PROBE_BH, &[], &[fast::probe_nonce(), self.sysvar_rb])?;
        if 1 + 64 + msg.bytes.len() > 1232 { return Err(format!("template {} bytes > 1232", 1 + 64 + msg.bytes.len())); }
        fast::Template::from_probe_msg_nonce(msg.bytes, tips.len(), guard.is_some())
    }

    /// HOT PATH: a lane copy from its template; None = a key collision / shape mismatch (the caller full-builds it)
    pub fn lane_copy_tpl(&self, t: &fast::Template, k: &LaunchKeys, nonce: (Pk, [u8; 32]), ln: &LaneCopy, min_out: u64, deadline: Option<u64>, out: &mut Vec<u8>) -> Option<Copy> {
        let vars: fast::VarKeys = [k.mint, k.bc, k.abc, k.bc_wsol, k.user_base, k.buyback];
        let tip = ln.tip.filter(|t| t.1 > 0);
        let tips: Vec<Pk> = tip.map(|t| vec![t.0]).unwrap_or_default();
        t.patch_nonce(out, &vars, &tips, &nonce.0, &nonce.1, min_out, deadline)?;
        use ed25519_dalek::Signer;
        let sig = self.presign.as_ref().and_then(|p| p.sign(out)).unwrap_or_else(|| self.key.sign(out).to_bytes());
        let mut raw = Vec::with_capacity(1 + 64 + out.len());
        raw.push(1);
        raw.extend_from_slice(&sig);
        raw.extend_from_slice(out);
        if raw.len() > 1232 { return None; }
        Some(Copy { sig, raw, paths: vec![ln.pi], tip: tip.map_or(0, |t| t.1) })
    }
}
