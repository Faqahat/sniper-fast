// =====================================================================================================================
// dip43 A3 TRUE TOKEN-BALANCE BOOK (verifier 11-10: TRUE balances come from an RPC snapshot at the arm: `snapshot`) (BUILD_DIP43.md Builder A; onchain P2 / DIP43_SPEC A1). The pre-send probe's Detector keeps a NET-TRADE
// balance per wallet (pump buys minus sells): a wallet that received tokens by transfer, or sent them away, is wrong there (the 9Vcvew2M
// shape: a buy that distributes in the same tx). This book keeps the TRUE balance: every executed pump tx's post_token_balances (its token
// accounts' balances after the tx, owner and mint; proto tag 8, decoded on the feed thread only when the book is on: feeds::tbal_on) and,
// when the transfer decoder is on (A4), plain token transfers. Per tracked mint (from its create on the feed), per owner: the sum of its
// token accounts. The curve's own account (owner = the bonding curve) is not a holder.
//   * `true_balance(mint, wallet)`: Some(raw token units) when the wallet's account was seen since the create; None = never seen
//   * `top_holders(mint, n)`: the n largest by true balance (largest first; ties by key), the curve excluded
// No I/O, no RPC; the probe's event loop owns it (pslive.rs PsLive::d43.book). Builder C's guard (ps43_guard.rs) reads it there.
// =====================================================================================================================
use crate::tx::Pk;
use rustc_hash::FxHashMap;

/// one token account's post balance in an executed tx (feeds::TokBal)
pub use crate::feeds::TokBal;

#[derive(Debug, Default)]
struct TTok {
    s0: u64,
    curve: Pk,
    /// owner -> its token accounts (account, raw amount)
    own: FxHashMap<Pk, Vec<(Pk, u64)>>,
    last: u64,
    /// owner -> the slot of its newest update (a post or a snapshot)
    upd: FxHashMap<Pk, u64>,
    /// the newest RPC snapshot: (its slot, when it came: mono ns)
    snap: Option<(u64, u64)>,
}

/// a snapshot's pseudo account (the RPC read gives owner + amount, not the account): replaced by the owner's first real post
pub const SNAP_ACCT: Pk = [0u8; 32];

/// the book
#[derive(Debug, Default)]
pub struct TBook {
    toks: FxHashMap<Pk, TTok>,
    pub posts: u64,
    pub transfers: u64,
    pub untracked: u64,
}

/// a token idle this many slots (no post, no transfer) leaves the book (~16 min)
pub const TB_IDLE_SLOTS: u64 = 4_500;

impl TBook {
    pub fn new() -> TBook { TBook::default() }
    pub fn tokens(&self) -> usize { self.toks.len() }
    pub fn tracked(&self, mint: &Pk) -> bool { self.toks.contains_key(mint) }
    pub fn create_slot(&self, mint: &Pk) -> Option<u64> { self.toks.get(mint).map(|t| t.s0) }

    /// a create on the feed: the mint is tracked from now (its curve is never a holder)
    pub fn create(&mut self, mint: Pk, slot: u64, curve: Pk) {
        self.toks.entry(mint).or_insert_with(|| TTok { s0: slot, curve, own: FxHashMap::default(), last: slot, upd: FxHashMap::default(), snap: None });
    }

    /// a token account's balance after an executed tx (`acct`: the account; Pk::default() when unknown = keyed by the owner)
    pub fn post(&mut self, b: &TokBal, slot: u64) {
        let Some(t) = self.toks.get_mut(&b.mint) else { self.untracked += 1; return };
        self.posts += 1;
        t.last = t.last.max(slot);
        if b.owner == t.curve { return; }
        let v = t.own.entry(b.owner).or_default();
        // the owner's snapshot holding is its (one) real account's: the post replaces it
        if b.acct != SNAP_ACCT { v.retain(|x| x.0 != SNAP_ACCT); }
        match v.iter_mut().find(|x| x.0 == b.acct) { Some(x) => x.1 = b.amount, None => v.push((b.acct, b.amount)) }
        let u = t.upd.entry(b.owner).or_default(); *u = (*u).max(slot);
    }

    /// an RPC snapshot of ALL the mint's token accounts at `slot` ((owner, amount) per account; the verifier 11-10: the pump-filtered feeds never
    /// carry plain transfers, so the TRUE balances come from this read at the arm, merged with the pump txs' post balances): every owner not
    /// updated after `slot` takes the snapshot's holding (0 when absent: its account closed / emptied). An untracked mint is tracked from here
    /// (`curve`: its bonding curve, never a holder). `now_ns`: its arrival (the snapshot's age)
    pub fn snapshot(&mut self, mint: Pk, curve: Pk, hold: &[(Pk, u64)], slot: u64, now_ns: u64) {
        let t = self.toks.entry(mint).or_insert_with(|| TTok { s0: 0, curve, own: FxHashMap::default(), last: slot, upd: FxHashMap::default(), snap: None });
        if t.snap.is_some_and(|s| s.0 > slot) { return; }
        t.snap = Some((slot, now_ns));
        t.last = t.last.max(slot);
        let mut sum: FxHashMap<Pk, u64> = FxHashMap::default();
        for (o, a) in hold { if *o != t.curve { *sum.entry(*o).or_default() += *a; } }
        let stale: Vec<Pk> = t.own.keys().filter(|o| t.upd.get(*o).is_none_or(|u| *u <= slot) && !sum.contains_key(*o)).copied().collect();
        for o in stale { t.own.remove(&o); }
        for (o, a) in sum {
            if t.upd.get(&o).is_some_and(|u| *u > slot) { continue; }
            t.own.insert(o, vec![(SNAP_ACCT, a)]);
            t.upd.insert(o, slot);
        }
    }
    /// the newest snapshot of `mint`: (slot, arrival mono ns)
    pub fn snap(&self, mint: &Pk) -> Option<(u64, u64)> { self.toks.get(mint)?.snap }

    /// a plain transfer of `amount` between two owners' accounts (A4's decoder; a side unknown = None): moved in the book
    pub fn transfer(&mut self, mint: &Pk, from: Option<(Pk, Pk)>, to: Option<(Pk, Pk)>, amount: u64, slot: u64) {
        let Some(t) = self.toks.get_mut(mint) else { return };
        self.transfers += 1;
        t.last = t.last.max(slot);
        if let Some((o, a)) = from {
            if o != t.curve {
                let v = t.own.entry(o).or_default();
                match v.iter_mut().find(|x| x.0 == a) { Some(x) => x.1 = x.1.saturating_sub(amount), None => v.push((a, 0)) }
            }
        }
        if let Some((o, a)) = to {
            if o != t.curve {
                let v = t.own.entry(o).or_default();
                match v.iter_mut().find(|x| x.0 == a) { Some(x) => x.1 = x.1.saturating_add(amount), None => v.push((a, amount)) }
            }
        }
    }

    /// the wallet's true balance of `mint` (its accounts summed); None = not seen since the create (or the mint is not tracked)
    pub fn true_balance(&self, mint: &Pk, wallet: &Pk) -> Option<u64> {
        self.toks.get(mint)?.own.get(wallet).map(|v| v.iter().map(|x| x.1).sum())
    }

    /// the `n` largest holders of `mint` by true balance (> 0; largest first, ties by key), the curve excluded
    pub fn top_holders(&self, mint: &Pk, n: usize) -> Vec<(Pk, u64)> {
        let Some(t) = self.toks.get(mint) else { return Vec::new() };
        let mut v: Vec<(Pk, u64)> = t.own.iter().map(|(w, a)| (*w, a.iter().map(|x| x.1).sum::<u64>())).filter(|x| x.1 > 0).collect();
        v.sort_unstable_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
        v.truncate(n);
        v
    }

    /// tokens idle for TB_IDLE_SLOTS leave (`keep`: the probe's own: armed, held)
    pub fn retire(&mut self, slot: u64, keep: impl Fn(&Pk) -> bool) -> usize {
        let n0 = self.toks.len();
        self.toks.retain(|m, t| t.last + TB_IDLE_SLOTS >= slot || keep(m));
        n0 - self.toks.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pk(b: u8) -> Pk { [b; 32] }
    fn tb(mint: u8, owner: u8, acct: u8, amount: u64) -> TokBal { TokBal { mint: pk(mint), owner: pk(owner), acct: pk(acct), amount } }

    #[test]
    fn dip43_book_true_balance_and_top() {
        let mut b = TBook::new();
        b.post(&tb(1, 2, 3, 5), 10);
        assert_eq!(b.untracked, 1, "untracked mint ignored");
        b.create(pk(1), 10, pk(99));
        // the curve's own account is not a holder
        b.post(&tb(1, 99, 98, 900_000), 10);
        // a buy that distributes in the same tx (9Vcvew2M): the buyer's post balance is 0 though its net trade is a buy
        b.post(&tb(1, 2, 20, 0), 11);
        b.post(&tb(1, 4, 40, 300), 11);
        b.post(&tb(1, 5, 50, 300), 11);
        b.post(&tb(1, 6, 60, 100), 11);
        // a second account of the same owner adds up
        b.post(&tb(1, 6, 61, 250), 12);
        assert_eq!(b.true_balance(&pk(1), &pk(2)), Some(0));
        assert_eq!(b.true_balance(&pk(1), &pk(6)), Some(350));
        assert_eq!(b.true_balance(&pk(1), &pk(7)), None);
        assert_eq!(b.true_balance(&pk(1), &pk(99)), None);
        assert_eq!(b.top_holders(&pk(1), 2), vec![(pk(6), 350), (pk(4), 300)]);
        // a later post replaces the account's balance
        b.post(&tb(1, 4, 40, 10), 13);
        assert_eq!(b.top_holders(&pk(1), 8), vec![(pk(6), 350), (pk(5), 300), (pk(4), 10)]);
        // a transfer moves tokens
        b.transfer(&pk(1), Some((pk(5), pk(50))), Some((pk(8), pk(80))), 120, 14);
        assert_eq!((b.true_balance(&pk(1), &pk(5)), b.true_balance(&pk(1), &pk(8))), (Some(180), Some(120)));
        // an RPC snapshot: owners not updated after it take its holdings (absent = 0); a later post replaces the snapshot's holding
        b.post(&tb(1, 9, 90, 77), 20);
        b.snapshot(pk(1), pk(99), &[(pk(6), 500), (pk(4), 1), (pk(99), 5), (pk(9), 3)], 19, 1);
        assert_eq!(b.true_balance(&pk(1), &pk(6)), Some(500));
        assert_eq!(b.true_balance(&pk(1), &pk(5)), None, "absent from the snapshot: gone");
        assert_eq!(b.true_balance(&pk(1), &pk(9)), Some(77), "updated after the snapshot: kept");
        b.post(&tb(1, 6, 60, 450), 21);
        assert_eq!(b.true_balance(&pk(1), &pk(6)), Some(450), "the post replaces the snapshot's pseudo account");
        assert_eq!(b.snap(&pk(1)), Some((19, 1)));
        // an untracked mint is tracked from its snapshot
        b.snapshot(pk(2), pk(99), &[(pk(3), 10)], 19, 1);
        assert_eq!(b.top_holders(&pk(2), 3), vec![(pk(3), 10)]);
        b.retire(20 + TB_IDLE_SLOTS, |m| *m == pk(1));
        // idle tokens retire unless kept
        assert_eq!(b.retire(21 + TB_IDLE_SLOTS, |_| false), 0);
        assert_eq!(b.retire(22 + TB_IDLE_SLOTS, |m| *m == pk(1)), 0);
        assert_eq!(b.retire(22 + TB_IDLE_SLOTS, |_| false), 1);
        assert!(!b.tracked(&pk(1)));
    }
}
