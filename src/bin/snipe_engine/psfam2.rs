// =====================================================================================================================
// dip42 FAM2: the "2NUM family present" annotation on the pre-send windows (owner 11-06: LOG ONLY, built LOCAL, default OFF).
// Research (/home/it/sniper-studies/sniper-w2num3 ex10.py `fam_arm`; memory wallet-2num.md): on our real trips that passed the bot gate, the trips where
// a wallet of the 2NUM family (2NUMEzNh + its siblings 7anesLRr / 5UipEgoi / 4MUFHfy6: one timer-scalper engine) had traded the token in the
// 300 slots BEFORE the dump made +21.1 mSOL/trip vs +10.0 without it, on all 9 days; it is known before the dump.
//   --presend-live-fam2 on|off              (default off)
//   --presend-live-fam2-wallets W1,W2,...   (default the 4 above; 1..16 base58 wallets)
//   --presend-live-fam2-slots N             (default 300; 1..2000)
// On every pre-send live ARM / SKIP record (T2, re-arm, wide, qf2), every FILL and every REALIZED record:
//   "fam2": {"n": DISTINCT family wallets that traded the mint (buy or sell, any size) in the last N slots = slots >= the record's slot - N,
//                 only trades the executed feed delivered BEFORE the record (no look-ahead),
//            "last": slots since the latest such trade (null: none), "who": [the wallets' first 8 characters]}
//   arm / skip: at the trigger's slot (re-arm: the arm's / the skip's slot).
//   fill: at the fill's slot, plus the research's own cut: "pre" = the distinct family wallets that traded in [ref - N, ref) (STRICTLY before
//         slot "ref"), "ref" = the DUMP's slot = the newest sell >= 0.3 SOL by another wallet on the window's tape in the 3 slots up to our
//         fill and seen before it (ex10.py: `dm`, `ds`; "dump": true), else the fill's slot ("dump": false). "pre" > 0 = "family present".
//   realized: the position's FILL object again with "at": "fill" (so its P&L splits without a join).
// HOW: one hash lookup per executed-feed trade (4 wallets); a family trade keeps its slot (the newest F2_KEEP distinct slots per wallet and
// mint, so a count at a slot a few slots back is exact). Nothing is read by the sender; no decision, no send, no other record changes.
// Records only with the flag on: a startup presend_live_fam2_config, "fam2" on the records above, run_end presend_live.fam2, the status
// line's part. Off: nothing of it runs; every record and decision dip41's.
// =====================================================================================================================
use super::*;

/// the family (wallet-2num.md): 2NUM and its three siblings
pub const F2_DEFAULT: [&str; 4] = ["2NUMEzNh4mFjZpzMwBqyyzoQLimbPZvpo3ksrJLM2rk3", "7anesLRrxNBYrNgYtxiixSwp4yiz286wXviWeWzxzpZx",
    "5UipEgoiVht6jydSVbtBhDHgCWbtZMYPiif8LvwJZnvH", "4MUFHfy6adSDv7wqJam8BPVAxZedQRzYDnXS3FrxfkD1"];
/// --presend-live-fam2-wallets: at most this many; --presend-live-fam2-slots: at most this
pub const F2_MAX_WALLETS: usize = 16;
pub const F2_SLOTS_MAX: u64 = 2000;
pub const F2_SLOTS: u64 = 300;
/// the newest distinct trade slots kept per (mint, wallet)
pub const F2_KEEP: usize = 8;
/// the fill's dump: a sell >= this (lamports) by another wallet in the F2_DUMP_SLOTS slots up to our fill (ex10.py: 3e8, bs - 3)
pub const F2_DUMP_SOL: u64 = 300_000_000;
pub const F2_DUMP_SLOTS: u64 = 3;
/// the book's prune (slots); the fills kept for their realized records at most
const F2_PRUNE_SLOTS: u64 = 25;
const F2_FILLS_CAP: usize = 4096;

/// --presend-live-fam2-wallets W1,W2,... -> the wallets (1..=16 distinct base58 keys)
pub fn wallets_parse(s: &str) -> Result<Vec<Pk>> {
    let mut v: Vec<Pk> = Vec::new();
    for x in s.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        let pk = bs58::decode(x).into_vec().ok().and_then(|b| <[u8; 32]>::try_from(b).ok()).with_context(|| format!("--presend-live-fam2-wallets: '{x}' is not a base58 wallet"))?;
        if !v.contains(&pk) { v.push(pk); }
    }
    if v.is_empty() || v.len() > F2_MAX_WALLETS { bail!("--presend-live-fam2-wallets W1,W2,...: 1..{F2_MAX_WALLETS} wallets; got {}", v.len()); }
    Ok(v)
}
pub fn default_wallets() -> Vec<Pk> { F2_DEFAULT.iter().map(|w| <[u8; 32]>::try_from(bs58::decode(w).into_vec().expect("b58")).expect("32")).collect() }

/// the flags' values
#[derive(Clone, Debug, PartialEq)]
pub struct F2Cfg { pub wallets: Vec<Pk>, pub slots: u64 }
impl F2Cfg {
    pub fn json(&self) -> serde_json::Value { serde_json::json!({"wallets": self.wallets.iter().map(b58).collect::<Vec<_>>(), "slots": self.slots}) }
}

/// one family wallet on one mint: its newest distinct trade slots, newest first
#[derive(Clone, Copy, Debug, Default)]
struct F2Tr { w: u8, n: u8, s: [u64; F2_KEEP] }
impl F2Tr {
    fn add(&mut self, slot: u64) {
        let n = self.n as usize;
        if self.s[..n].contains(&slot) { return; }
        // keep the newest F2_KEEP, newest first (the feed is in slot order: this is nearly always a push to the front)
        let pos = self.s[..n].iter().position(|&x| x < slot).unwrap_or(n);
        if pos >= F2_KEEP { return; }
        let end = (n + 1).min(F2_KEEP);
        self.s.copy_within(pos..end - 1, pos + 1);
        self.s[pos] = slot;
        self.n = end as u8;
    }
    fn slots(&self) -> &[u64] { &self.s[..self.n as usize] }
}

/// a count: the distinct family wallets, the newest counted trade's slot, who (indices into the wallet list, in list order)
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct F2V { pub n: u32, pub newest: Option<u64>, pub who: Vec<u8> }

/// per mint: the family wallets that traded it
#[derive(Debug, Default)]
pub struct F2Book { m: FxHashMap<Pk, Vec<F2Tr>> }
impl F2Book {
    pub fn add(&mut self, mint: Pk, w: u8, slot: u64) {
        let v = self.m.entry(mint).or_default();
        match v.iter_mut().find(|e| e.w == w) { Some(e) => e.add(slot), None => { let mut e = F2Tr { w, ..Default::default() }; e.add(slot); v.push(e); } }
    }
    /// the wallets with a kept trade in slots [slot - span, hi]: `strict` false: hi = any slot seen (the record's own slot included);
    /// `strict` true: hi = slot - 1 (STRICTLY before `slot`: the research's [ds - 300, ds))
    pub fn view(&self, mint: &Pk, slot: u64, span: u64, strict: bool) -> F2V {
        let mut o = F2V::default();
        let Some(v) = self.m.get(mint) else { return o };
        let lo = slot.saturating_sub(span);
        for e in v {
            let hit = e.slots().iter().copied().filter(|&x| x >= lo && (!strict || x < slot)).max();
            if let Some(x) = hit { o.n += 1; o.newest = Some(o.newest.map_or(x, |y| y.max(x))); o.who.push(e.w); }
        }
        o.who.sort_unstable();
        o
    }
    /// trades older than `span` (+ the dump look-back) before `slot_now` can never count again
    pub fn prune(&mut self, slot_now: u64, span: u64) {
        let lo = slot_now.saturating_sub(span + F2_DUMP_SLOTS + 2);
        self.m.retain(|_, v| { v.retain(|e| e.s[0] >= lo); !v.is_empty() });
    }
    pub fn mints(&self) -> usize { self.m.len() }
}

/// the probe's side
#[derive(Debug)]
pub struct Fam2 {
    pub cfg: F2Cfg,
    idx: FxHashMap<Pk, u8>,
    pub book: F2Book,
    pruned: u64,
    /// window id -> its fill's object (for the position's realized record)
    fills: FxHashMap<u64, serde_json::Value>,
    /// counts [records, with the family present]: arms, skips, fills (present = "pre" > 0); the family's trades seen
    pub arms: [u64; 2], pub skips: [u64; 2], pub fills_n: [u64; 2], pub trades: u64,
}

impl Fam2 {
    pub fn new(cfg: F2Cfg) -> Fam2 {
        let idx = cfg.wallets.iter().enumerate().map(|(i, w)| (*w, i as u8)).collect();
        Fam2 { cfg, idx, book: F2Book::default(), pruned: 0, fills: FxHashMap::default(), arms: [0; 2], skips: [0; 2], fills_n: [0; 2], trades: 0 }
    }
    /// one executed-feed trade (feed order): kept when a family wallet's
    #[inline]
    pub fn trade(&mut self, mint: &Pk, user: &Pk, slot: u64) {
        let Some(&i) = self.idx.get(user) else { return };
        self.trades += 1;
        self.book.add(*mint, i, slot);
    }
    fn who(&self, v: &F2V) -> Vec<String> { v.who.iter().map(|&i| b58(&self.cfg.wallets[i as usize])[..8].to_string()).collect() }
    /// {"n", "last", "who"} at `slot` (every trade seen so far)
    pub fn json(&self, mint: &Pk, slot: u64) -> (serde_json::Value, bool) {
        let v = self.book.view(mint, slot, self.cfg.slots, false);
        (serde_json::json!({"n": v.n, "last": v.newest.map(|x| slot.saturating_sub(x)), "who": self.who(&v)}), v.n > 0)
    }
    /// the fill's object: the above at the fill's slot + "pre" / "ref" / "dump" (`dump`: the dump's slot when the tape has one)
    pub fn fill_json(&self, mint: &Pk, slot: u64, dump: Option<u64>) -> (serde_json::Value, bool) {
        let (mut j, _) = self.json(mint, slot);
        let r = dump.unwrap_or(slot);
        let p = self.book.view(mint, r, self.cfg.slots, true);
        j["pre"] = p.n.into();
        j["pre_who"] = self.who(&p).into();
        j["ref"] = r.into();
        j["dump"] = dump.is_some().into();
        (j, p.n > 0)
    }
    pub fn prune(&mut self, slot_now: u64) {
        if slot_now < self.pruned + F2_PRUNE_SLOTS { return; }
        self.pruned = slot_now;
        self.book.prune(slot_now, self.cfg.slots);
        if self.fills.len() > F2_FILLS_CAP {
            let mut ids: Vec<u64> = self.fills.keys().copied().collect();
            ids.sort_unstable();
            let cut = ids[ids.len() - F2_FILLS_CAP / 2];
            self.fills.retain(|k, _| *k >= cut);
        }
    }
}

/// the fill's dump on the window's tape (trades seen before our fill, newest last): the newest sell >= F2_DUMP_SOL by another wallet in
/// slots [fill - F2_DUMP_SLOTS, fill] -> its slot
pub fn dump_slot<'a>(tape: impl DoubleEndedIterator<Item = &'a pl::Trade>, user: &Pk, fill_slot: u64) -> Option<u64> {
    let lo = fill_slot.saturating_sub(F2_DUMP_SLOTS);
    tape.rev().take_while(|t| t.s >= lo).find(|t| !t.buy && t.sol >= F2_DUMP_SOL && t.user != *user && t.s <= fill_slot).map(|t| t.s)
}

impl PsLive {
    /// the executed feed's trade (nothing with the flag off)
    #[inline]
    pub(super) fn f2_trade(&mut self, mint: &Pk, user: &Pk, slot: u64) { if let Some(f) = self.f2.as_mut() { f.trade(mint, user, slot); } }
    /// an arm (`skip` false) / skip record's "fam2" at `slot` (None: the flag off)
    pub(super) fn f2_json(&mut self, skip: bool, mint: &Pk, slot: u64) -> Option<serde_json::Value> {
        let f = self.f2.as_mut()?;
        let (j, present) = f.json(mint, slot);
        let c = if skip { &mut f.skips } else { &mut f.arms };
        c[0] += 1; c[1] += present as u64;
        Some(j)
    }
    /// a fill record's "fam2" (window `w`; kept for its realized record; None: the flag off). Called before the fill's own trade reaches
    /// the tape: the tape holds only what was seen before our fill
    pub(super) fn f2_fill_json(&mut self, w: u64, t: &pl::Trade) -> Option<serde_json::Value> {
        self.f2.as_ref()?;
        let dump = self.tapes.get(&t.mint).and_then(|(tp, _)| dump_slot(tp.iter(), &self.user, t.s));
        let f = self.f2.as_mut()?;
        let (j, present) = f.fill_json(&t.mint, t.s, dump);
        f.fills_n[0] += 1; f.fills_n[1] += present as u64;
        f.fills.insert(w, j.clone());
        Some(j)
    }
    /// the realized record's "fam2": the position's fill object, "at": "fill" (None: the flag off / no fill kept)
    pub(super) fn f2_realized(&mut self, w: u64) -> Option<serde_json::Value> {
        let mut j = self.f2.as_mut()?.fills.remove(&w)?;
        j["at"] = "fill".into();
        Some(j)
    }
    pub(super) fn f2_tick(&mut self, slot_now: u64) { if let Some(f) = self.f2.as_mut() { f.prune(slot_now); } }
    /// the start's record (nothing with the flag off)
    pub(super) fn f2_start(&mut self) {
        let Some(f) = self.f2.as_ref() else { return };
        let mut r = f.cfg.json();
        r["ev"] = "presend_live_fam2_config".into();
        r["mode"] = "log".into();
        r["keep"] = F2_KEEP.into();
        r["dump"] = serde_json::json!({"sol": F2_DUMP_SOL as f64 / 1e9, "slots": F2_DUMP_SLOTS});
        r["t"] = arbx::feeds::clock::now_ns().into();
        self.rec(r);
    }
    /// the status line's part ("" with the flag off)
    pub(super) fn f2_status(&self) -> String {
        let Some(f) = self.f2.as_ref() else { return String::new() };
        format!(" | FAM2 LOG ({} wallets, {} slots): family present on arms {}/{}, skips {}/{}, fills {}/{} (family trades seen {})", f.cfg.wallets.len(), f.cfg.slots,
            f.arms[1], f.arms[0], f.skips[1], f.skips[0], f.fills_n[1], f.fills_n[0], f.trades)
    }
    /// run_end's part (None with the flag off)
    pub(super) fn f2_finish(&self) -> Option<serde_json::Value> {
        let f = self.f2.as_ref()?;
        let c = |x: &[u64; 2]| serde_json::json!({"n": x[0], "present": x[1]});
        Some(serde_json::json!({"mode": "log", "wallets": f.cfg.wallets.len(), "slots": f.cfg.slots, "arms": c(&f.arms), "skips": c(&f.skips), "fills": c(&f.fills_n),
            "trades": f.trades, "mints": f.book.mints()}))
    }
}
