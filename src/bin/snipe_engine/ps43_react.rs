// =====================================================================================================================
// dip43 A12 REACT-PROBE RECORDER (coordinator 11-10; reactive agent REA-1, ~/sniper-studies/sniper-plan1110/reactive/REPORT.md §8). LOG ONLY.
//   --react-watch FILE (off without it): FILE = a JSON list of wallets (base58; also {"wallets": [...]}), re-read every ~60 s (a bad file keeps
//   the last good list). Every arrival on ANY feed whose fee payer is a watched wallet goes (one hash lookup + one bounded try_send on the event
//   loop; the clone only for a watched payer) to this module's own thread, which per signature collects every feed's arrival for 3 s and writes
//   one `react_watch` record: wallet, mint, buy, sol, curve state (executed feed), slot, idx, the first feed and every feed's arrival, the CU
//   price (its last 3 digits = haqq's bot code), whether our pre-send probe had the mint armed / held at the first sighting (overlap), and
//   t_signed_copy_ready_ns = the first sighting + the MEASURED time to build and sign a 0.01 SOL copy buy on the pre-send attempt builder
//   (pl::attempt_ixs + compile_v0 + sign with a THROWAWAY key, never sent: no send, no RPC). Bounded: 4,096 pending signatures, a full channel
//   drops (counted).
// =====================================================================================================================
use super::*;

/// one sighting from the event loop
pub struct Seen { pub feed: u16, pub t_rx: u64, pub slot: u64, pub executed: Option<bool>, pub tx: arbx::tx::Tx, pub exec: Option<Arc<arbx::feeds::ExecInfo>>,
    pub armed: bool, pub held: bool }

/// the event loop's handle
pub struct ReactTap { pub set: Arc<std::sync::RwLock<FxHashSet<Pk>>>, tx: crossbeam_channel::Sender<Seen>, pub dropped: Arc<AtomicU64> }

pub const PENDING_MAX: usize = 4_096;
const HOLD_NS: u64 = 3_000_000_000;
const COPY_SPEND: u64 = 10_000_000;

/// the list file: ["W", ...] or {"wallets": ["W", ...]}
pub fn list_parse(b: &[u8]) -> std::result::Result<FxHashSet<Pk>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    let a = v.as_array().or_else(|| v["wallets"].as_array()).ok_or("not a list (or {\"wallets\": [...]})")?;
    let mut s = FxHashSet::default();
    for x in a {
        let w = x.as_str().ok_or("a wallet is not a string")?;
        let pk: Pk = bs58::decode(w).into_vec().ok().and_then(|v| v.try_into().ok()).ok_or_else(|| format!("bad wallet {w}"))?;
        s.insert(pk);
    }
    Ok(s)
}

/// the tx's CU price (micro-lamports; ComputeBudget SetComputeUnitPrice)
pub fn cu_price(tx: &arbx::tx::Tx) -> Option<u64> {
    const CB: &str = "ComputeBudget111111111111111111111111111111";
    let cb = arbx::tx::pk(CB);
    tx.ixs.iter().find(|ix| tx.keys.get(ix.program as usize) == Some(&cb) && ix.data.first() == Some(&3) && ix.data.len() >= 9)
        .map(|ix| u64::from_le_bytes(ix.data[1..9].try_into().unwrap()))
}

/// the mint of a pump instruction in a tx (accounts[2] of a pump.fun ix: buy / sell), when the feed gives no event
fn pump_mint(tx: &arbx::tx::Tx) -> Option<Pk> {
    let pump = *arbx::snipe::PUMP;
    tx.ixs.iter().find(|ix| tx.keys.get(ix.program as usize) == Some(&pump)).and_then(|ix| ix.accounts.get(2)).and_then(|i| tx.keys.get(*i as usize)).copied()
}

/// build + sign a 0.01 SOL copy buy of `mint` on the pre-send attempt builder (throwaway key; never sent) -> ns taken
pub fn copy_build_ns(mint: &Pk, key: &SigningKey) -> u64 {
    let t0 = arbx::fast::mono_ns();
    let user = key.verifying_key().to_bytes();
    let l = snipe_build::launch_from_target(*mint, *mint);
    let guard = build::cu_limit_ix(120_000);
    let (ixs, _) = pl::attempt_ixs(user, &l, COPY_SPEND, 1, 120_000, 1_000, guard, None);
    let bh = (*BLOCKHASH_CACHE.lock().unwrap()).map(|x| x.0).unwrap_or([7u8; 32]);
    if let Ok(m) = build::compile_v0(user, &ixs, bh, &[], &[]) { let _ = std::hint::black_box(build::sign(&m, key)); }
    arbx::fast::mono_ns().saturating_sub(t0)
}

struct Pend { first: (u16, u64, Option<bool>), feeds: Vec<(u16, u64, Option<bool>)>, payer: Pk, slot: u64, idx: Option<u64>, mint: Option<Pk>, ev: Option<arbx::dip::TradeEvent>,
    cu: Option<u64>, armed: bool, held: bool, copy_ns: u64, mono0: u64 }

impl ReactTap {
    /// the thread and its list (a bad / missing file: refused at the start)
    pub fn start(path: String, names: Vec<String>, log: Arc<DipLog>) -> Result<ReactTap> {
        let set0 = list_parse(&std::fs::read(&path).with_context(|| format!("--react-watch {path}"))?).map_err(|e| anyhow::anyhow!("--react-watch {path}: {e}"))?;
        eprintln!("DIP43 A12 REACT-WATCH (LOG ONLY): {} wallets from {path} (re-read every ~60 s); one react_watch record per watched tx (every feed's arrival, \
                   the measured 0.01 SOL copy build + sign: never sent)", set0.len());
        let set = Arc::new(std::sync::RwLock::new(set0));
        let (tx, rx) = crossbeam_channel::bounded::<Seen>(4_096);
        let dropped = Arc::new(AtomicU64::new(0));
        let s2 = set.clone();
        std::thread::Builder::new().name("react-watch".into()).spawn(move || run(rx, s2, path, names, log)).context("react-watch thread")?;
        Ok(ReactTap { set, tx, dropped })
    }
    /// the event loop's side: a watched payer's arrival (nothing else costs more than one lookup)
    #[inline]
    pub fn note(&self, a: &arbx::feeds::Arrival, armed: impl Fn(&Pk) -> (bool, bool)) {
        let Some(p) = a.tx.keys.first() else { return };
        if !self.set.read().unwrap().contains(p) { return; }
        let m = a.exec.as_ref().and_then(|x| x.trades.first().map(|t| t.mint)).or_else(|| pump_mint(&a.tx));
        let (armed, held) = m.map_or((false, false), |m| armed(&m));
        if self.tx.try_send(Seen { feed: a.feed, t_rx: a.t_rx, slot: a.slot, executed: a.executed, tx: a.tx.clone(), exec: a.exec.clone(), armed, held }).is_err() {
            self.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }
}

fn run(rx: crossbeam_channel::Receiver<Seen>, set: Arc<std::sync::RwLock<FxHashSet<Pk>>>, path: String, names: Vec<String>, log: Arc<DipLog>) {
    let key = SigningKey::from_bytes(&[0x43u8; 32]);
    let mut pend: FxHashMap<[u8; 64], Pend> = FxHashMap::default();
    let mut last_read = Instant::now();
    let mut mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
    let name = |f: u16| names.get(f as usize).cloned().unwrap_or_else(|| f.to_string());
    loop {
        let got = rx.recv_timeout(Duration::from_millis(250));
        let now = arbx::fast::mono_ns();
        match got {
            Ok(s) => {
                let ev = s.exec.as_ref().and_then(|x| x.trades.iter().find(|t| Some(&t.user) == s.tx.keys.first()).cloned());
                let idx = s.exec.as_ref().map(|x| x.index);
                let room = pend.len() < PENDING_MAX;
                match pend.get_mut(&s.tx.sig) {
                    Some(p) => {
                        p.feeds.push((s.feed, s.t_rx, s.executed));
                        if p.ev.is_none() && ev.is_some() { p.ev = ev; p.mint = p.ev.as_ref().map(|e| e.mint).or(p.mint); }
                        if p.idx.is_none() { p.idx = idx; }
                    }
                    None if room => {
                        let mint = ev.as_ref().map(|e| e.mint).or_else(|| pump_mint(&s.tx));
                        let copy_ns = mint.map_or(0, |m| copy_build_ns(&m, &key));
                        pend.insert(s.tx.sig, Pend { first: (s.feed, s.t_rx, s.executed), feeds: vec![(s.feed, s.t_rx, s.executed)], payer: s.tx.keys[0], slot: s.slot, idx, mint, ev,
                            cu: cu_price(&s.tx), armed: s.armed, held: s.held, copy_ns, mono0: now });
                    }
                    None => {}
                }
            }
            Err(crossbeam_channel::RecvTimeoutError::Disconnected) => break,
            Err(_) => {}
        }
        let due: Vec<[u8; 64]> = pend.iter().filter(|(_, p)| now.saturating_sub(p.mono0) >= HOLD_NS).map(|(k, _)| *k).collect();
        for k in due {
            let p = pend.remove(&k).unwrap();
            log.w(serde_json::json!({"ev": "react_watch", "wallet": b58(&p.payer), "sig": bs58::encode(&k).into_string(), "mint": p.mint.map(|m| b58(&m)),
                "buy": p.ev.as_ref().map(|e| e.buy), "sol": p.ev.as_ref().map(|e| e.sol), "tok": p.ev.as_ref().map(|e| e.tok), "vsol": p.ev.as_ref().map(|e| e.vsol), "vtok": p.ev.as_ref().map(|e| e.vtok),
                "slot": p.slot, "idx": p.idx, "first_feed": name(p.first.0), "t_seen_ns": p.first.1, "first_executed": p.first.2,
                "feeds": p.feeds.iter().map(|f| serde_json::json!({"feed": name(f.0), "t": f.1, "dt_ms": (f.1 as i64 - p.first.1 as i64) as f64 / 1e6, "executed": f.2})).collect::<Vec<_>>(),
                "cu_price": p.cu, "cu_last3": p.cu.map(|c| c % 1000), "presend_armed": p.armed, "presend_held": p.held,
                "copy_build_sign_ns": p.copy_ns, "t_signed_copy_ready_ns": (p.copy_ns > 0).then(|| p.first.1 + p.copy_ns)}));
        }
        if last_read.elapsed() >= Duration::from_secs(60) {
            last_read = Instant::now();
            let m = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
            if m != mt {
                mt = m;
                match std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| list_parse(&b)) {
                    Ok(s) => { eprintln!("  REACT-WATCH list re-read: {} wallets", s.len()); *set.write().unwrap() = s; }
                    Err(e) => eprintln!("  REACT-WATCH list {path} NOT re-read ({e}): the last good list stays"),
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dip43_react_list_cu_copy() {
        let s = list_parse(br#"["haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq"]"#).unwrap();
        assert_eq!(s.len(), 1);
        assert_eq!(list_parse(br#"{"wallets": ["haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq", "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"]}"#).unwrap().len(), 2);
        assert!(list_parse(br#"["nope"]"#).is_err() && list_parse(b"{}").is_err());
        let root = env!("CARGO_MANIFEST_DIR");
        let f = list_parse(&std::fs::read(format!("{root}/ops/prod/react_watch.json")).unwrap()).unwrap();
        assert_eq!(f.len(), 17, "the initial list (14 + 3 added 11-10)");
        // the CU price of a tx and its last 3 digits
        let cb = arbx::tx::pk("ComputeBudget111111111111111111111111111111");
        let mut d = vec![3u8]; d.extend_from_slice(&1_234_567u64.to_le_bytes());
        let tx = arbx::tx::Tx { keys: vec![[1u8; 32], cb], ixs: vec![arbx::tx::Ix { program: 1, accounts: vec![], data: d }], ..Default::default() };
        assert_eq!(cu_price(&tx), Some(1_234_567));
        // the copy build + sign is measured (never sent)
        assert!(copy_build_ns(&[9u8; 32], &SigningKey::from_bytes(&[1u8; 32])) > 0);
    }
}
