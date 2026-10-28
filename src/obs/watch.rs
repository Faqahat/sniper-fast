//! OBSERVATORY module 3: the WATCH LIST (--obs-watch FILE: one wallet per line, '#' comment = its name). LOG ONLY.
//!   watch_trade: every executed curve trade by a watched wallet: wallet + name, mint, side, SOL, tokens, slot, idx, j, t (the feed's
//!     arrival), the curve after it (vsol, vtok, price), token age (slots / ms since its create when the observatory saw the create),
//!     the tx's compute-unit price (micro-lamports; v1 txs: the total priority fee) and limit, cu_price mod 1000 (haqq's bot code),
//!     its top-level System transfers named by the sender catalogue (tips: to, lamports, whose), the fee payer when it is not the
//!     trader, the signature, the trader's holding after it, flags. Block time: not carried by the executed feed (slot only).
//!   watch_fail: every FAILED tx of a watched wallet the feed carries (fee payer = the wallet; a pre-sender leaves many reverted
//!     txs): slot, t, signature, CU price / limit, transfers (tips), its first pump instruction (discriminator hex) and the mint guess
//!     (that instruction's account 2: global, fee recipient, MINT ... in pump's buy / sell layouts). The feed keeps no block index or
//!     error for a failed tx. BOUNDED: at most FAIL_PER_MIN failed txs per wallet per minute are written one by one; the rest of that
//!     minute is one watch_fail_agg record (wallet, minute, count, CU price range, mints guessed).
use super::book::{self, Ctx, Tok, Tr};
use super::{Cfg, FailIn, TxIn, M_WATCH};
use crate::tx::Pk;
use rustc_hash::FxHashMap;
use serde_json::{json, Value};

/// failed txs written one by one per wallet per minute (the rest: one aggregate record per wallet-minute)
pub const FAIL_PER_MIN: u32 = 20;

#[derive(Clone, Debug, Default)]
pub struct Stats { pub trades: u64, pub fails: u64, pub fails_agg: u64, pub per_wallet: FxHashMap<Pk, [u64; 3]> }

/// a wallet's failed txs this minute: (minute, written, total, CU price min, max, distinct mint guesses)
#[derive(Default)]
struct FailMin { minute: u64, written: u32, total: u32, cu_min: u64, cu_max: u64, mints: rustc_hash::FxHashSet<Pk> }

pub struct Watch { names: FxHashMap<Pk, String>, tips: FxHashMap<Pk, String>, pub st: Stats, fmin: FxHashMap<Pk, FailMin> }

impl Watch {
    pub fn new(cfg: &Cfg) -> Watch { Watch { names: cfg.watch_names.clone(), tips: crate::send::tip_owner_names(), st: Stats::default(), fmin: FxHashMap::default() } }

    /// a wallet's minute ended: its aggregate record when more failed than were written
    fn flush_min(&mut self, w: &Pk, recs: &mut Vec<(usize, Value)>) {
        let Some(m) = self.fmin.get_mut(w) else { return };
        if m.total > m.written {
            self.st.fails_agg += 1;
            recs.push((M_WATCH, json!({"ev": "watch_fail_agg", "w": book::b58(w), "name": self.names.get(w).filter(|s| !s.is_empty()), "minute_t": m.minute * 60_000_000_000,
                "total": m.total, "written": m.written, "cu_price_min": m.cu_min, "cu_price_max": m.cu_max, "mints": m.mints.len()})));
        }
        *m = FailMin::default();
    }
    fn xf(&self, v: &[(Pk, u64)]) -> Value {
        json!(v.iter().map(|(to, l)| json!({"to": book::short(to), "lamports": l, "whose": self.tips.get(to)})).collect::<Vec<_>>())
    }
    fn name(&self, k: &Pk) -> Value { self.names.get(k).filter(|s| !s.is_empty()).map(|s| json!(s)).unwrap_or(Value::Null) }

    pub fn on_trade(&mut self, tok: &Tok, tr: &Tr, ctx: &Ctx, t: &TxIn, recs: &mut Vec<(usize, Value)>) {
        self.st.trades += 1;
        let c = self.st.per_wallet.entry(tr.user).or_default();
        c[if tr.buy { 0 } else { 1 }] += 1;
        let tips = t.xfers.as_ref().map(|v| self.xf(v));
        recs.push((M_WATCH, json!({"ev": "watch_trade", "w": book::b58(&tr.user), "name": self.name(&tr.user), "mint": book::b58(&tr.mint), "buy": tr.buy, "sol": tr.sol,
            "tok": tr.tok, "slot": tr.s, "idx": tr.i, "j": tr.j, "t": tr.t, "vsol": tr.vsol, "vtok": tr.vtok, "p": tr.p(), "age_slots": tok.age_slots(tr.s), "age_ms": tok.age_ms(tr.t),
            "hist": tok.hist, "mayhem": tok.mayhem, "cu_price": t.cu_price, "cu_mod1000": t.cu_price.map(|p| p % 1000), "cu_limit": t.cu_limit, "v1": t.v1, "tips": tips,
            "payer": (t.payer != tr.user).then(|| book::short(&t.payer)), "pct_after": ctx.bal_after.max(0) as f64 / book::SUPPLY * 100.0, "fl": book::flags_str(ctx.fl),
            "trades_in_tx": t.exec.trades.len(), "sig": bs58::encode(&tr.sig).into_string()})));
    }

    pub fn on_fail(&mut self, f: &FailIn, book: &book::Book, recs: &mut Vec<(usize, Value)>) {
        self.st.fails += 1;
        self.st.per_wallet.entry(f.payer).or_default()[2] += 1;
        let minute = f.t_rx / 60_000_000_000;
        if self.fmin.get(&f.payer).is_some_and(|m| m.minute != minute && m.total > 0) { self.flush_min(&f.payer, recs); }
        let m = self.fmin.entry(f.payer).or_default();
        if m.total == 0 { m.minute = minute; m.cu_min = u64::MAX; }
        m.total += 1;
        let cp = f.cu_price.unwrap_or(0);
        m.cu_min = m.cu_min.min(cp); m.cu_max = m.cu_max.max(cp);
        if let Some(k) = f.pump_ix.and_then(|x| x.1) { if m.mints.len() < 256 { m.mints.insert(k); } }
        if m.written >= FAIL_PER_MIN { return; }
        m.written += 1;
        let mint = f.pump_ix.and_then(|x| x.1);
        let age = mint.and_then(|m| book.get(&m)).map(|tk| (tk.age_slots(f.slot), tk.age_ms(f.t_rx)));
        recs.push((M_WATCH, json!({"ev": "watch_fail", "w": book::b58(&f.payer), "name": self.name(&f.payer), "slot": f.slot, "t": f.t_rx, "sig": bs58::encode(&f.sig).into_string(),
            "cu_price": f.cu_price, "cu_mod1000": f.cu_price.map(|p| p % 1000), "cu_limit": f.cu_limit, "v1": f.v1, "tips": self.xf(&f.xfers),
            "pump_ix": f.pump_ix.map(|x| format!("{:016x}", x.0.swap_bytes())), "mint_guess": mint.map(|m| book::b58(&m)), "age": age.map(|a| json!({"slots": a.0, "ms": a.1}))})));
    }

    /// the run's end: the open minutes' aggregates
    pub fn finish(&mut self, recs: &mut Vec<(usize, Value)>) { let ws: Vec<Pk> = self.fmin.keys().copied().collect(); for w in ws { self.flush_min(&w, recs); } }
    pub fn status(&self) -> Value { json!({"trades": self.st.trades, "fails": self.st.fails, "fail_aggregates": self.st.fails_agg, "wallets_seen": self.st.per_wallet.len()}) }
    pub fn summary(&self) -> Value {
        let mut v: Vec<(&Pk, &[u64; 3])> = self.st.per_wallet.iter().collect();
        v.sort_by(|a, b| (b.1[0] + b.1[1] + b.1[2]).cmp(&(a.1[0] + a.1[1] + a.1[2])));
        json!({"trades": self.st.trades, "fails": self.st.fails, "per_wallet": v.iter().take(60).map(|(k, c)| json!({"w": book::short(k), "name": self.names.get(*k), "buys": c[0], "sells": c[1], "fails": c[2]})).collect::<Vec<_>>()})
    }
}
