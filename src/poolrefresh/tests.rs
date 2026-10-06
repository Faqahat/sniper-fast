//! poolrefresh.rs tests (WP-22): the list, the records, the sources' parsing, the plan's rules (verification, the group
//! rule, priority, the cap, idle and dead pools), its determinism and fail-safe, and an end-to-end refresh on recorded
//! fixtures (GeckoTerminal and DexScreener answers, chain accounts: testdata/poolrefresh), with no network
use super::*;
use crate::pda;

fn k(n: u8) -> Pk { let mut x = [n; 32]; x[0] = 0xa0; x }
fn tok(n: u8) -> Pk { let mut x = [n; 32]; x[0] = 0xb0; x }

/// a policy for the plan tests: WSOL only, 2 SOL on the quote side, idle after 2 segments
fn pol() -> PoolRefreshCfg { PoolRefreshCfg { enabled: true, cap: 100, max_adds: 50, idle_segments: 2, ..Default::default() } }

/// synthetic chain accounts the engine's decoders read (`pools::meta_of`): PumpSwap and DLMM pools, token accounts, mints
struct World { accts: BTreeMap<String, Option<SavedAcct>> }
impl World {
    fn new() -> World { World { accts: BTreeMap::new() } }
    fn put(&mut self, key: Pk, a: Option<Account>) { self.accts.insert(b58(&key), a.as_ref().map(SavedAcct::of)); }
    fn mint(&mut self, m: Pk) { self.put(m, Some(Account { owner: *pda::TOKEN_PROGRAM, lamports: 1, data: vec![0u8; 82] })); }
    fn vault(&mut self, v: Pk, mint: Pk, amount: u64) {
        let mut d = vec![0u8; 165];
        d[..32].copy_from_slice(&mint);
        d[64..72].copy_from_slice(&amount.to_le_bytes());
        self.put(v, Some(Account { owner: *pda::TOKEN_PROGRAM, lamports: 2_039_280, data: d }));
    }
    /// a PumpSwap pool `pool` on `token` / WSOL holding `sol` lamports (vaults and mints too)
    fn pump(&mut self, pool: Pk, token: Pk, sol: u64) {
        let (vb, vq) = (vault_of(pool, 1), vault_of(pool, 2));
        let mut d = vec![0u8; 301];
        d[43..75].copy_from_slice(&token);
        d[75..107].copy_from_slice(&WSOL[..]);
        d[139..171].copy_from_slice(&vb);
        d[171..203].copy_from_slice(&vq);
        self.put(pool, Some(Account { owner: Venue::PumpSwap.program(), lamports: 1, data: d }));
        self.vault(vb, token, 1_000_000);
        self.vault(vq, *WSOL, sol);
        self.mint(token);
        self.mint(*WSOL);
    }
    /// a DLMM pool on x / y holding `y_amount` of y
    fn dlmm(&mut self, pool: Pk, x: Pk, y: Pk, y_amount: u64) {
        let (rx, ry) = (vault_of(pool, 1), vault_of(pool, 2));
        let mut d = vec![0u8; 904];
        d[88..120].copy_from_slice(&x);
        d[120..152].copy_from_slice(&y);
        d[152..184].copy_from_slice(&rx);
        d[184..216].copy_from_slice(&ry);
        self.put(pool, Some(Account { owner: Venue::Dlmm.program(), lamports: 1, data: d }));
        self.vault(rx, x, 1_000_000);
        self.vault(ry, y, y_amount);
        self.mint(x);
        self.mint(y);
    }
}
fn vault_of(pool: Pk, side: u8) -> Pk { let mut v = pool; v[0] = 0xc0 + side; v }

fn cand(pool: Pk, src: Src, base: Option<Pk>, score: f64) -> Cand {
    Cand { pool: b58(&pool), venue: "DLMM".into(), src, base: base.map(|b| b58(&b)), quote: base.map(|_| b58(&WSOL)), score, symbol: None, via: "test".into() }
}
fn row(v: Venue, p: Pk) -> Row { Row { venue: v, pool: p, source: "seed".into() } }
/// a full 30-minute segment (its triggers cover all of it)
fn seg(name: &str, listed: &[Pk], active: &[Pk], ok: bool) -> SegAct {
    SegAct { name: name.into(), started_ns: 0, complete: true, ok, listed: Some(listed.iter().map(b58).collect()),
        pools: active.iter().map(|p| (b58(p), Counts { triggers: 1, ..Default::default() })).collect(), covered_min: 30, planned_min: Some(30.0), ..Default::default() }
}
fn inputs(rows: &[Row], segs: Vec<SegAct>, cands: Vec<Cand>, w: &World) -> Inputs {
    let mut i = Inputs { segments: segs, cands: merge(cands), accounts: w.accts.clone(), ..Default::default() };
    i.set_rows(rows);
    i
}
fn why_rejected(r: &Value, pool: Pk) -> Option<String> {
    r["rejected"].as_array().unwrap().iter().find(|x| x["pool"] == b58(&pool)).and_then(|x| x["why"].as_str().map(String::from))
}
fn pools_of(rows: &[Row]) -> Vec<Pk> { rows.iter().map(|r| r.pool).collect() }
fn tmp(tag: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("arbx-wp22-{tag}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

/// The seed list: `venue` and `pool` columns found by name (other columns ignored, `source` kept), a repeated pool once,
/// unreadable rows counted; written back as `venue,pool,source`; `check_list` refuses a file whose hash is not the
/// report's, or that has no rows
#[test]
fn the_list_reads_and_writes() {
    let text = format!("source,venue,pool,mint_a\nmriya,DLMM,{},x\nbad,Orca,{},x\n,PumpSwap,{},y\nagain,DLMM,{},x\nx,DLMM,not-a-key,x\n", b58(&k(1)), b58(&k(2)), b58(&k(3)), b58(&k(1)));
    let (rows, bad) = parse_list(&text).unwrap();
    assert_eq!((rows.len(), bad), (2, 2));
    assert_eq!((rows[0].venue, rows[0].pool, rows[0].source.as_str()), (Venue::Dlmm, k(1), "mriya"));
    assert_eq!((rows[1].venue, rows[1].source.as_str()), (Venue::PumpSwap, ""));
    let csv = list_csv(&[Row { venue: Venue::DammV2, pool: k(4), source: "wp22:gt:c-p2".into() }, Row { venue: Venue::RayCpmm, pool: k(5), source: "a,b".into() }]);
    assert_eq!(csv, format!("venue,pool,source\nDAMMv2,{},wp22:gt:c-p2\nRayCPMM,{},a;b\n", b58(&k(4)), b58(&k(5))));
    assert_eq!(parse_list(&csv).unwrap().0.len(), 2);
    let d = tmp("list");
    let f = d.join("l.csv");
    std::fs::write(&f, &csv).unwrap();
    let h = crate::provenance::sha256_hex(csv.as_bytes());
    assert_eq!(check_list(&f, Some(&h)).unwrap(), (2, h.clone()));
    assert!(check_list(&f, Some("00")).unwrap_err().to_string().contains("is not the report's"));
    std::fs::write(&f, "venue,pool,source\n").unwrap();
    assert!(check_list(&f, None).unwrap_err().to_string().contains("no rows"));
    let _ = std::fs::remove_dir_all(&d);
}

/// The pool account of a swap on each of our venues, at the engine decoders' positions; anything else is no swap; an
/// exec line's swaps, top-level and inner (an aggregator's), when it landed
#[test]
fn swap_pools_are_read_where_the_decoders_read_them() {
    let d = |h: &str| { let mut v = hex8(h).to_vec(); v.extend([0u8; 16]); v };
    assert_eq!(swap_pool_index(Venue::PumpSwap, &d("33e685a4017f83ad"), 20), Some(0));
    assert_eq!(swap_pool_index(Venue::PumpSwap, &d("66063d1201daebea"), 20), Some(0));
    assert_eq!(swap_pool_index(Venue::PumpSwap, &d("0000000000000000"), 20), None, "not a swap (a create, a deposit)");
    assert_eq!(swap_pool_index(Venue::RayCpmm, &d("8fbe5adac41e33de"), 13), Some(3));
    assert_eq!(swap_pool_index(Venue::RayAmmV4, &[9u8; 17], 18), Some(1));
    assert_eq!(swap_pool_index(Venue::RayAmmV4, &[16u8; 17], 8), Some(1));
    assert_eq!(swap_pool_index(Venue::RayAmmV4, &[3u8; 17], 18), None);
    assert_eq!(swap_pool_index(Venue::Dlmm, &d("2bd7f784893cf351"), 15), Some(0));
    assert_eq!(swap_pool_index(Venue::Dlmm, &d("414b3f4ceb5b5b88"), 5), None, "too few accounts");
    assert_eq!(swap_pool_index(Venue::DammV2, &d("f8c69e91e17587c8"), 12), Some(1));
    let b64 = |h: &str| base64::engine::general_purpose::STANDARD.encode(d(h));
    let line = json!({ "arb_like": { "is": true, "why": "venues" }, "ok": true, "keys": [b58(&k(9)), b58(&k(1)), b58(&k(2)), b58(&Venue::Dlmm.program()), b58(&Venue::PumpSwap.program())],
        "ixs": [{ "p": 4, "a": [2, 0, 0, 0, 0], "d": b64("33e685a4017f83ad") }],
        "inner": [{ "ix": 0, "list": [{ "p": 3, "a": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "d": b64("414b3f4ceb5b5b88"), "h": 2 }] }] }).to_string();
    assert_eq!(exec_pools(line.as_bytes()), vec![(Venue::PumpSwap, b58(&k(2))), (Venue::Dlmm, b58(&k(1)))]);
    assert!(exec_pools(line.replace("\"ok\":true", "\"ok\":false").as_bytes()).is_empty());
}

/// A segment's records: each listed pool's triggers, decisions (the trigger's pool), opportunities (both pools) and
/// rival rows; the exec records' landed rival arbitrage on pools the segment did not list; zstd files with a frame still
/// being written (left out) read like plain ones; a segment without its rivals is not `ok`; a campaign directory's
/// segments, oldest first
#[test]
fn a_segments_records() {
    let d = tmp("seg");
    let (a, b, c, u) = (b58(&k(1)), b58(&k(2)), b58(&k(3)), b58(&k(4)));
    std::fs::write(d.join("meta.json"), json!({ "run": { "segment": "c-p3", "started_ns": 42, "argv": ["arbx", "run", "--minutes", "30", "--canary"] } }).to_string()).unwrap();
    std::fs::write(d.join("pools.json"), json!([{ "pool": a }, { "pool": b }, { "pool": c }]).to_string()).unwrap();
    let hdr = |s: &str| json!({ "schema": s, "file_seq": 0 }).to_string();
    // triggers in two rotation files, zstd: the second ends with an incomplete frame (a write in progress)
    let t1 = format!("{}\n{}\n", hdr("arbx.triggers/2.0"), json!({ "pool": a, "sig": "x", "st": { "rx": 1_800_000_000_000_000_000u64, "decoded": 1 } }));
    std::fs::write(d.join("triggers.000.jsonl.zst"), zstd::bulk::compress(t1.as_bytes(), 3).unwrap()).unwrap();
    let mut z = zstd::bulk::compress(format!("{}\n", json!({ "pool": a, "st": { "rx": 1_800_000_061_000_000_000u64 } })).as_bytes(), 3).unwrap();
    let partial = zstd::bulk::compress(format!("{}\n", json!({ "pool": b })).as_bytes(), 3).unwrap();
    z.extend(&partial[..partial.len() - 3]);
    std::fs::write(d.join("triggers.001.jsonl.zst"), z).unwrap();
    std::fs::write(d.join("opportunities.jsonl"), format!("{}\n{}\n", hdr("arbx.opportunities/1.2"), json!({ "buy_pool": a, "sell_pool": c, "trigger_pool": c }))).unwrap();
    std::fs::write(d.join("decisions.jsonl"), format!("{}\n{{\"decision\":1,\"kind\":\"commit\",\"trigger\":{{\"txn\":\"t\",\"pool\":\"{c}\",\"group\":1}},\"routes\":[{{\"buy\":\"{a}\"}}]}}\n{{\"decision\":1,\"torn_suspect\":true}}\n",
        hdr("arbx.decisions/1.2"))).unwrap();
    std::fs::write(d.join("rivals.jsonl"), format!("{}\n{}\n", hdr("arbx.rivals/1.2"), json!({ "pools": [b, c], "why": "pools" }))).unwrap();
    let b64 = base64::engine::general_purpose::STANDARD.encode([hex8("414b3f4ceb5b5b88").to_vec(), vec![0u8; 16]].concat());
    let ex = |ok: bool, arb: bool, pool: &str| json!({ "alts": [], "arb_like": { "is": arb, "why": null }, "ok": ok, "keys": [b58(&k(9)), pool, b58(&Venue::Dlmm.program())],
        "ixs": [{ "p": 2, "a": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "d": b64 }], "inner": null }).to_string();
    std::fs::write(d.join("exec.jsonl"), format!("{}\n{}\n{}\n{}\n{}\n{}\n", hdr("arbx.exec/2.2"), ex(true, true, &u), ex(true, true, &u), ex(false, true, &u), ex(true, false, &u), ex(true, true, &a))).unwrap();
    let far = Instant::now() + Duration::from_secs(60);
    let s = read_segment(&d, true, far);
    assert_eq!((s.name.as_str(), s.started_ns, s.complete, s.ok), ("c-p3", 42, false, true));
    assert_eq!(s.listed.as_ref().map(|l| l.len()), Some(3));
    assert_eq!(s.pools[&a], Counts { triggers: 2, decisions: 0, opps: 1, rivals: 0 }, "the partial frame's trigger is left out");
    assert_eq!(s.pools[&b], Counts { rivals: 1, ..Default::default() });
    assert_eq!(s.pools[&c], Counts { decisions: 1, opps: 1, rivals: 1, ..Default::default() });
    assert_eq!(s.unlisted.len(), 1, "a listed pool's arbitrage is the rivals' count");
    assert_eq!(s.unlisted[&u], Seen { venue: "DLMM".into(), txs: 2 }, "landed rival arbitrage only");
    assert_eq!(s.streams["triggers"]["files"], 2);
    // review #3a: the minutes its triggers cover (their receive times), and the minutes it was started for
    assert_eq!((s.covered_min, s.planned_min), (2, Some(30.0)));
    // without exec, nothing unlisted; without rivals, the segment is not ok (it cannot count toward an idle streak)
    assert!(read_segment(&d, false, far).unlisted.is_empty());
    std::fs::remove_file(d.join("rivals.jsonl")).unwrap();
    assert!(!read_segment(&d, false, far).ok);
    // a segment that recorded no trigger at all (its state stream was down) is not ok either
    let e = tmp("seg-empty");
    std::fs::write(e.join("triggers.jsonl"), format!("{}\n", hdr("arbx.triggers/2.0"))).unwrap();
    std::fs::write(e.join("rivals.jsonl"), format!("{}\n", hdr("arbx.rivals/1.2"))).unwrap();
    assert!(!read_segment(&e, false, far).ok);
    std::fs::write(e.join("triggers.jsonl"), format!("{}\n{}\n", hdr("arbx.triggers/2.0"), json!({ "pool": a }))).unwrap();
    assert!(read_segment(&e, false, far).ok);
    let _ = std::fs::remove_dir_all(&e);
    // a campaign directory: its segments, oldest first
    let camp = d.join("camp");
    for (n, t) in [("c-p2", 20), ("c-p1", 10)] {
        std::fs::create_dir_all(camp.join(n)).unwrap();
        std::fs::write(camp.join(n).join("meta.json"), json!({ "run": { "started_ns": t } }).to_string()).unwrap();
    }
    std::fs::create_dir_all(camp.join("not-a-segment")).unwrap();
    assert_eq!(segment_dirs(&[camp.clone()]).iter().map(|p| p.file_name().unwrap().to_string_lossy().into_owned()).collect::<Vec<_>>(), ["c-p1", "c-p2"]);
    assert_eq!(segment_dirs(&[camp.join("c-p2"), camp.clone()]).len(), 2);
    let _ = std::fs::remove_dir_all(&d);
}

/// The sources' answers (recorded: testdata/poolrefresh/api): GeckoTerminal's pools on our venues by dex id (an Orca pool
/// is only a token), the base tokens for DexScreener; DexScreener's pools of a token on our venues with a quote we take
/// and at least half the minimum on the quote side; merged by pool, records over GeckoTerminal over DexScreener
#[test]
fn the_sources_answers() {
    let api = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh/api");
    let (c, t) = parse_gt(&std::fs::read_to_string(api.join("gt-trending_1h.json")).unwrap(), "gt:trending_1h").unwrap();
    assert_eq!(c.iter().map(|x| (x.venue.as_str(), &x.pool[..8])).collect::<Vec<_>>(), [("DAMMv2", "CHQ5CAEG"), ("DLMM", "zxTpi4Bt"), ("RayAMMv4", "EP2ib6dY")]);
    assert_eq!(c[0].base.as_deref(), Some("BQxzR4pLkDw46gzbrkRjFuUSsgvN5BhTWHh6EXUwf3F"));
    assert_eq!(c[0].symbol.as_deref(), Some("BINDER"));
    assert!(c.iter().all(|x| x.src == Src::Gt && x.quote.as_deref() == Some("So11111111111111111111111111111111111111112")));
    assert_eq!(t.len(), 3, "{t:?}");
    let (c5, t5) = parse_gt(&std::fs::read_to_string(api.join("gt-trending_5m.json")).unwrap(), "gt:trending_5m").unwrap();
    assert_eq!((c5.len(), t5.len()), (1, 2), "the Orca WETH pool is no candidate, its token is");
    assert!(parse_gt("{\"errors\":[]}", "x").is_err() && parse_gt("<html>", "x").is_err());
    let wsol = [*WSOL];
    let min = |_: &Pk| 2.0;
    let ds = parse_ds(&std::fs::read_to_string(api.join("ds-BQxzR4pLkDw46gzbrkRjFuUSsgvN5BhTWHh6EXUwf3F.json")).unwrap(), "ds:BINDER", &wsol, &min).unwrap();
    assert_eq!(ds.iter().map(|x| (x.venue.as_str(), &x.pool[..8])).collect::<Vec<_>>(), [("DAMMv2", "CHQ5CAEG"), ("DLMM", "67mcDJDV"), ("DLMM", "D4ghcnAb")],
        "dust, USDC and USDT pools and the DBC curve left out");
    let wif = parse_ds(&std::fs::read_to_string(api.join("ds-EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm.json")).unwrap(), "ds:WIF", &wsol, &min).unwrap();
    assert!(wif.iter().any(|x| x.venue == "RayAMMv4") && wif.iter().any(|x| x.venue == "RayCPMM") && wif.iter().all(|x| x.venue != "DAMMv2"), "DYN (DAMM v1) is not ours");
    assert_eq!(gt_venue("raydium-clmm"), None);
    assert_eq!(ds_venue("raydium", &["CLMM".into()]), None);
    let m = merge(vec![cand(k(1), Src::Ds, Some(tok(1)), 5.0), cand(k(1), Src::Records, None, 2.0), cand(k(2), Src::Ds, None, 1.0), cand(k(2), Src::Gt, Some(tok(2)), 3.0)]);
    assert_eq!(m.iter().map(|c| (c.src, c.score, c.base.is_some())).collect::<Vec<_>>(), [(Src::Records, 5.0, true), (Src::Gt, 3.0, true)]);
}

/// Verification (every pool added: on chain, the engine's own decoders, the boot's Token-2022 refusals) and the group
/// rule (2+ verified pools of one quote on our venues, the listed ones counted): each refusal is named
#[test]
fn every_added_pool_is_verified_and_tokens_enter_in_groups() {
    let mut w = World::new();
    let (ta, tb, tc, td) = (tok(1), tok(2), tok(3), tok(4));
    w.pump(k(1), ta, 50_000_000_000); // listed, token A
    w.dlmm(k(2), tb, *WSOL, 10_000_000_000); // listed, token B
    w.dlmm(k(10), ta, *WSOL, 9_000_000_000); // A's second pool: enters (one listed)
    w.pump(k(11), tc, 30_000_000_000); // C: two new pools enter together
    w.dlmm(k(12), tc, *WSOL, 3_000_000_000);
    w.dlmm(k(13), td, *WSOL, 3_000_000_000); // D: alone
    w.put(k(14), None); // gone
    w.put(k(15), Some(Account { owner: [7; 32], lamports: 1, data: vec![0; 904] })); // not a venue's
    w.put(k(16), Some(Account { owner: Venue::Dlmm.program(), lamports: 1, data: vec![0; 100] })); // a layout no decoder reads
    w.dlmm(k(17), tok(5), *WSOL, 3_000_000_000); // claimed as another token's
    w.dlmm(k(18), tok(6), *USDC, 9_000_000_000); // a USDC pool (quotes: WSOL)
    w.dlmm(k(19), ta, *WSOL, 1_000_000_000); // 1 SOL < 2
    // Token-2022 with a transfer fee: refused as at boot
    w.dlmm(k(20), tok(7), *WSOL, 5_000_000_000);
    w.dlmm(k(21), tok(7), *WSOL, 5_000_000_000);
    let mut fee = vec![0u8; 166];
    fee[165] = 1;
    let mut ext = vec![0u8; 108];
    ext[88..90].copy_from_slice(&300u16.to_le_bytes());
    fee.extend(1u16.to_le_bytes());
    fee.extend((ext.len() as u16).to_le_bytes());
    fee.extend(ext);
    w.put(tok(7), Some(Account { owner: *pda::TOKEN_2022, lamports: 1, data: fee }));
    // a "vault" that is not the quote mint's token account
    w.dlmm(k(22), ta, *WSOL, 9_000_000_000);
    w.vault(vault_of(k(22), 2), tok(9), 9_000_000_000);
    let rows = vec![row(Venue::PumpSwap, k(1)), row(Venue::Dlmm, k(2))];
    let s = vec![seg("p1", &[k(1), k(2)], &[k(1)], true)];
    let cands = vec![cand(k(10), Src::Gt, Some(ta), 10.0), cand(k(11), Src::Ds, Some(tc), 5.0), cand(k(12), Src::Ds, Some(tc), 4.0), cand(k(13), Src::Ds, Some(td), 9.0),
        cand(k(14), Src::Gt, None, 1.0), cand(k(15), Src::Gt, None, 1.0), cand(k(16), Src::Gt, None, 1.0), cand(k(17), Src::Gt, Some(tok(8)), 1.0),
        cand(k(18), Src::Gt, None, 1.0), cand(k(19), Src::Gt, Some(ta), 1.0), cand(k(20), Src::Ds, Some(tok(7)), 1.0), cand(k(21), Src::Ds, Some(tok(7)), 1.0),
        cand(k(22), Src::Gt, Some(ta), 1.0), cand(k(1), Src::Gt, Some(ta), 99.0)];
    let out = plan(&pol(), &inputs(&rows, s, cands, &w), "c-p2").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(2), k(10), k(11), k(12)], "listed first, then the new ones by source and score");
    assert_eq!(out.rows[2].source, "wp22:gt:c-p2");
    assert_eq!(out.rows[3].source, "wp22:ds:c-p2");
    let r = &out.report;
    for (p, why) in [(13, "group"), (14, "missing"), (15, "venue"), (16, "layout"), (17, "mints"), (18, "quote"), (19, "liquidity"), (20, "transfer_fee"), (21, "transfer_fee"), (22, "vault")] {
        assert_eq!(why_rejected(r, k(p)).as_deref(), Some(why), "pool {p}");
    }
    assert!(why_rejected(r, k(1)).is_none(), "a listed pool is no candidate");
    assert_eq!((r["counts"]["added"].as_u64(), r["counts"]["kept_active"].as_u64(), r["counts"]["kept_idle"].as_u64()), (Some(3), Some(1), Some(1)));
    assert_eq!(r["added"][0]["quote_liquidity"].as_u64(), Some(9_000_000_000));
    assert_eq!(r["top_tokens"][0]["token"].as_str(), Some(b58(&tc).as_str()), "C: two pools");
    // USDC allowed: the USDC pool is verified, and alone it is refused by the group rule
    let mut p = pol();
    p.quotes = vec!["WSOL".into(), "USDC".into()];
    let rows2 = vec![row(Venue::PumpSwap, k(1))];
    let out = plan(&p, &inputs(&rows2, vec![], vec![cand(k(18), Src::Gt, None, 1.0)], &w), "c-p2").unwrap();
    assert_eq!(why_rejected(&out.report, k(18)).as_deref(), Some("group"));
    // a registry pool on the pair counts toward the group (when alive on chain), and is itself no candidate
    w.dlmm(k(30), td, *WSOL, 3_000_000_000);
    let mut i = inputs(&rows2, vec![], vec![cand(k(13), Src::Ds, Some(td), 9.0), cand(k(30), Src::Ds, Some(td), 1.0)], &w);
    i.registry = vec![RegPool { venue: "DLMM".into(), pool: b58(&k(30)), t0: b58(&td), t1: b58(&WSOL) }];
    let out = plan(&pol(), &i, "c-p2").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(13)]);
    assert_eq!(why_rejected(&out.report, k(30)).as_deref(), Some("in_registry"));
}

/// Priority and the cap: active listed pools, new pools from our records, then from the trending lists, then idle listed
/// pools; `max_adds` bounds what one refresh adds; a cut that would leave an added token with one pool removes its
/// additions (`cap_group`) and gives the room back
#[test]
fn priority_and_the_cap() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=5 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    w.dlmm(k(10), t, *WSOL, 5_000_000_000); // records
    w.dlmm(k(11), t, *WSOL, 5_000_000_000); // GeckoTerminal
    w.dlmm(k(12), t, *WSOL, 5_000_000_000); // DexScreener
    let rows: Vec<Row> = (1..=5).map(|n| row(Venue::Dlmm, k(n))).collect();
    // 1..3 active, 4 and 5 idle (one segment: no idle drop)
    let s = vec![seg("p1", &(1..=5).map(k).collect::<Vec<_>>(), &[k(1), k(2), k(3)], true)];
    let cands = vec![cand(k(12), Src::Ds, None, 1e6), cand(k(11), Src::Gt, None, 1.0), cand(k(10), Src::Records, None, 1.0)];
    let mut p = pol();
    p.cap = 6;
    let out = plan(&p, &inputs(&rows, s.clone(), cands.clone(), &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(2), k(3), k(10), k(11), k(12)], "the idle pools make room");
    let dropped: Vec<(String, String)> = out.report["dropped"].as_array().unwrap().iter().map(|d| (d["pool"].as_str().unwrap().to_string(), d["why"].as_str().unwrap().to_string())).collect();
    assert_eq!(dropped, vec![(b58(&k(4)), "cap".to_string()), (b58(&k(5)), "cap".to_string())]);
    p.cap = 5;
    let out = plan(&p, &inputs(&rows, s.clone(), cands.clone(), &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(2), k(3), k(10), k(11)]);
    assert_eq!(why_rejected(&out.report, k(12)).as_deref(), Some("cap"));
    p.cap = 100;
    p.max_adds = 1;
    let out = plan(&p, &inputs(&rows, s.clone(), cands.clone(), &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(2), k(3), k(4), k(5), k(10)], "records first");
    assert_eq!((why_rejected(&out.report, k(11)).as_deref(), why_rejected(&out.report, k(12)).as_deref()), (Some("max_adds"), Some("max_adds")));
    // a group the cap breaks: token U's only listed pool is idle (k 6); its new pool (k 20) needs it
    let u = tok(2);
    w.dlmm(k(6), u, *WSOL, 5_000_000_000);
    w.dlmm(k(20), u, *WSOL, 5_000_000_000);
    let rows: Vec<Row> = [1, 2, 6].iter().map(|n| row(Venue::Dlmm, k(*n))).collect();
    let s = vec![seg("p1", &[k(1), k(2), k(6)], &[k(1), k(2)], true)];
    let mut p = pol();
    p.cap = 3;
    let out = plan(&p, &inputs(&rows, s, vec![cand(k(20), Src::Gt, Some(u), 1.0)], &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), vec![k(1), k(2), k(6)], "the addition goes, the room goes back to the idle pool");
    assert_eq!(why_rejected(&out.report, k(20)).as_deref(), Some("cap_group"));
}

/// Listed pools: dead ones (no account, another owner, a layout no decoder reads) that the last boot had dropped too (no
/// pools.json lists them) are dropped; so are pools idle in `idle_segments` consecutive full segments they were listed
/// in. A segment that did not list the pool, or whose records were not read whole, ends the streak; 0 never drops
#[test]
fn dead_and_idle_listed_pools() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=5 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    w.put(k(6), None);
    w.put(k(7), Some(Account { owner: Venue::PumpSwap.program(), lamports: 1, data: vec![0; 904] }));
    w.put(k(8), Some(Account { owner: Venue::Dlmm.program(), lamports: 1, data: vec![0; 20] }));
    // 32 busy pools keep the shrink guard's floor out of the way (8 of the 40 rows may go)
    for n in 100..132 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    let busy: Vec<Pk> = (100..132).map(k).collect();
    let rows: Vec<Row> = (1..=8).chain(100..132).map(|n| row(Venue::Dlmm, k(n))).collect();
    // the boot dropped the dead ones: no segment lists them
    let all: Vec<Pk> = (1..=5).map(k).chain(busy.iter().copied()).collect();
    let no4: Vec<Pk> = all.iter().copied().filter(|p| *p != k(4)).collect();
    let act = |x: &[Pk]| -> Vec<Pk> { x.iter().copied().chain(busy.iter().copied()).collect() };
    // k1 active in p3; k2 active in p1 only; k3 and k5 never; k4 not listed in p2; the busy pools in every segment
    let segs = vec![seg("p1", &all, &act(&[k(2)]), true), seg("p2", &no4, &act(&[]), true), seg("p3", &all, &act(&[k(1)]), true), seg("p4", &all, &act(&[]), true)];
    let out = plan(&pol(), &inputs(&rows, segs.clone(), vec![], &w), "x").unwrap();
    let why: BTreeMap<String, String> = out.report["dropped"].as_array().unwrap().iter().map(|d| (d["pool"].as_str().unwrap().to_string(), d["why"].as_str().unwrap().to_string())).collect();
    assert_eq!(why.get(&b58(&k(6))).map(|s| s.as_str()), Some("dead:missing"));
    assert_eq!(why.get(&b58(&k(7))).map(|s| s.as_str()), Some("dead:owner"));
    assert_eq!(why.get(&b58(&k(8))).map(|s| s.as_str()), Some("dead:layout"));
    for n in [2, 3, 4, 5] { assert_eq!(why.get(&b58(&k(n))).map(|s| s.as_str()), Some("idle"), "k{n}: idle in the last 2 segments it was listed in"); }
    assert_eq!(pools_of(&out.rows), [vec![k(1)], busy.clone()].concat(), "k1: active in p3, idle in p4 only");
    let mut p = pol();
    p.idle_segments = 3;
    let out = plan(&p, &inputs(&rows, segs.clone(), vec![], &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), [vec![k(1), k(4)], busy.clone()].concat(), "k4: p2 did not list it, its streak is 2");
    // a segment whose records were not read whole ends every streak
    let mut segs2 = segs.clone();
    segs2[2].ok = false;
    let out = plan(&p, &inputs(&rows, segs2, vec![], &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), [(1..=5).map(k).collect::<Vec<_>>(), busy.clone()].concat());
    p.idle_segments = 0;
    assert_eq!(plan(&p, &inputs(&rows, segs, vec![], &w), "x").unwrap().rows.len(), 37, "0: never idle-dropped");
}

/// Review #2: a listed pool that one verification answer calls dead, but that the last boot found alive (its pools.json
/// lists it) or that the last segment saw active, is kept (`unconfirmed_dead`): the next boot re-checks it on its own
/// provider. Once a boot has dropped it and it shows no activity, it goes
#[test]
fn a_pool_the_last_boot_found_alive_is_never_dropped_on_one_answer() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=3 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    w.put(k(4), None);
    w.put(k(5), Some(Account { owner: Venue::PumpSwap.program(), lamports: 1, data: vec![0; 904] }));
    w.put(k(6), None);
    let rows: Vec<Row> = (1..=6).map(|n| row(Venue::Dlmm, k(n))).collect();
    // k4: booted alive, the answer says missing; k5: not booted but active in the last segment (50 triggers, as the
    // review's demo), the answer says another owner; k6: the boot dropped it, no activity
    let mut last = seg("p1", &[k(1), k(2), k(3), k(4)], &[k(1)], true);
    last.pools.insert(b58(&k(5)), Counts { triggers: 50, decisions: 5, opps: 3, rivals: 0 });
    let out = plan(&pol(), &inputs(&rows, vec![last], vec![], &w), "x").unwrap();
    assert_eq!(pools_of(&out.rows), (1..=5).map(k).collect::<Vec<_>>());
    let kept: BTreeMap<String, (String, Value)> = out.report["kept"].as_array().unwrap().iter()
        .map(|x| (x["pool"].as_str().unwrap().to_string(), (x["why"].as_str().unwrap().to_string(), x["rpc"].clone()))).collect();
    assert_eq!(kept[&b58(&k(4))], ("unconfirmed_dead".to_string(), json!("dead:missing")));
    assert_eq!(kept[&b58(&k(5))], ("unconfirmed_dead".to_string(), json!("dead:owner")));
    assert_eq!(out.report["dropped"].as_array().unwrap().iter().map(|d| (d["pool"].as_str().unwrap().to_string(), d["why"].as_str().unwrap().to_string())).collect::<Vec<_>>(),
        [(b58(&k(6)), "dead:missing".to_string())]);
    assert_eq!(out.report["counts"]["kept_unconfirmed"].as_u64(), Some(2));
}

/// Review #3a: a segment counts toward an idle streak only when its triggers cover 80% of a segment's minutes (the
/// campaign's `--segment-min`, else its own `--minutes`): a short, crashed or degraded segment ends the streak
#[test]
fn short_segments_do_not_count_toward_idleness() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=40 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    let rows: Vec<Row> = (1..=40).map(|n| row(Venue::Dlmm, k(n))).collect();
    let all: Vec<Pk> = (1..=40).map(k).collect();
    let busy: Vec<Pk> = (2..=40).map(k).collect();
    let full = |n: &str| seg(n, &all, &busy, true);
    let has_k1 = |i: &Inputs| pools_of(&plan(&pol(), i, "x").unwrap().rows).contains(&k(1));
    assert!(!has_k1(&inputs(&rows, vec![full("p1"), full("p2")], vec![], &w)), "two full segments: k1 is idle");
    let mut short = full("p2");
    short.covered_min = 23;
    assert!(has_k1(&inputs(&rows, vec![full("p1"), short.clone()], vec![], &w)), "23 of 30 minutes (under 24): the streak ends");
    let mut i = inputs(&rows, vec![full("p1"), short], vec![], &w);
    i.segment_min = Some(25.0);
    assert!(!has_k1(&i), "the campaign's segment length decides: 23 of 25 minutes counts");
    let mut unknown = full("p2");
    unknown.planned_min = None;
    assert!(has_k1(&inputs(&rows, vec![full("p1"), unknown], vec![], &w)), "no length known: it does not count");
    let r = plan(&pol(), &inputs(&rows, vec![full("p1"), full("p2")], vec![], &w), "x").unwrap().report;
    assert_eq!(r["segments_counted_for_idle"][0], json!({ "segment": "p1", "counts": true, "covered_min": 30, "minutes": 30.0 }));
}

/// Review #3b: one refresh drops at most max(25, a tenth of the list) idle pools, the longest idle first, and never so
/// many that the list falls under 80% of its rows; the others stay (idle, last in priority) and the report says so
#[test]
fn the_shrink_guard_bounds_idle_drops() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=200u8 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    let rows: Vec<Row> = (1..=200u8).map(|n| row(Venue::Dlmm, k(n))).collect();
    let all: Vec<Pk> = (1..=200u8).map(k).collect();
    let mut p = pol();
    p.idle_segments = 4;
    p.cap = 1_000;
    // the review's case: four full segments, one pool active: 199 idle, 25 go (max(25, 200 / 10))
    let segs: Vec<SegAct> = (1..=4).map(|i| seg(&format!("p{i}"), &all, &[k(1)], true)).collect();
    let out = plan(&p, &inputs(&rows, segs, vec![], &w), "x").unwrap();
    assert_eq!(out.rows.len(), 175);
    assert_eq!(out.report["shrink_guard"], json!({ "idle_candidates": 199, "idle_dropped": 25, "idle_held": 174, "idle_bound": 25, "floor_rows": 160, "applied": true }));
    assert_eq!(out.report["counts"]["idle_held"].as_u64(), Some(174));
    // the longest idle first: k2..k31 were active in p2 (idle 4 segments), the rest never (idle 6): k32..k56 go
    let mut segs: Vec<SegAct> = (1..=6).map(|i| seg(&format!("p{i}"), &all, &[k(1)], true)).collect();
    for n in 2..=31u8 { segs[1].pools.insert(b58(&k(n)), Counts { triggers: 1, ..Default::default() }); }
    let out = plan(&p, &inputs(&rows, segs, vec![], &w), "x").unwrap();
    let gone: Vec<Pk> = out.report["dropped"].as_array().unwrap().iter().map(|d| pk_opt(d["pool"].as_str().unwrap()).unwrap()).collect();
    assert_eq!(gone, (32..=56u8).map(k).collect::<Vec<_>>());
    // never under 80% of the rows: 40 rows, 30 idle: 8 go
    let rows40 = &rows[..40];
    let segs: Vec<SegAct> = (1..=4).map(|i| seg(&format!("p{i}"), &all[..40], &all[..10], true)).collect();
    let out = plan(&p, &inputs(rows40, segs, vec![], &w), "x").unwrap();
    assert_eq!((out.rows.len(), out.report["shrink_guard"]["idle_dropped"].as_u64()), (32, Some(8)));
}

/// Review #10: a refresh adds pools only on the five venues the engine trades at FT-008 (`ADD_VENUES`), whatever
/// `Venue` knows: a candidate owned by Raydium CLMM or Orca Whirlpool (a DexScreener "raydium" pair with no labels, say)
/// is refused (`venue`), and the sources' dex ids map only into the five
#[test]
fn only_our_five_venues_are_added() {
    assert_eq!(ADD_VENUES, [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2]);
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=4 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); }
    for (n, prog) in [(3, "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"), (4, "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc")] {
        if let Some(Some(a)) = w.accts.get_mut(&b58(&k(n))) { a.owner = prog.to_string(); }
    }
    let rows = vec![row(Venue::Dlmm, k(1)), row(Venue::Dlmm, k(2))];
    let out = plan(&pol(), &inputs(&rows, vec![], vec![cand(k(3), Src::Ds, Some(t), 1.0), cand(k(4), Src::Gt, Some(t), 1.0)], &w), "x").unwrap();
    assert_eq!((why_rejected(&out.report, k(3)).as_deref(), why_rejected(&out.report, k(4)).as_deref()), (Some("venue"), Some("venue")));
    assert_eq!(out.rows.len(), 2);
    for dex in ["pumpswap", "meteora", "meteora-damm-v2", "raydium", "raydium-cp", "raydium-clmm", "orca", "whirlpool"] {
        if let Some(v) = gt_venue(dex) { assert!(ADD_VENUES.contains(&v), "{dex}"); }
        for labels in [vec![], vec!["CLMM".to_string()], vec!["DLMM".to_string()], vec!["DYN2".to_string()], vec!["CPMM".to_string()]] {
            if let Some(v) = ds_venue(dex, &labels) { assert!(ADD_VENUES.contains(&v), "{dex} {labels:?}"); }
        }
    }
    assert_eq!(ds_venue("raydium", &["CLMM".to_string()]), None, "a labelled CLMM pair is not a candidate at all");
}

/// Review #8: the refresh's environment holds only what its verification endpoints name (never a HAAN variable); the
/// config check refuses Haan by name, by host in any case, or by the variables Haan's endpoints read; the run-time check
/// refuses a url_env that resolves to Haan; and the endpoint's limiter is the policy's rate with a burst of 1 (review #4)
#[test]
fn the_refresh_never_holds_or_uses_haan() {
    let base = "config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n\
        [[rpc.endpoint]]\nname = \"haan\"\nurl = \"https://rpc.haandigital.eu/\"\nbearer_env = \"HAAN_API_KEY\"\n\
        [[rpc.endpoint]]\nname = \"alt1\"\nurl = \"https://RPC.HaanDigital.EU/x\"\nenabled = false\n\
        [[rpc.endpoint]]\nname = \"alt2\"\nurl = \"https://x.example/\"\nbearer_env = \"HAAN_API_KEY\"\nenabled = false\n\
        [[rpc.endpoint]]\nname = \"alt3\"\nurl_env = \"MY_HAAN_URL\"\nenabled = false\n\
        [[rpc.endpoint]]\nname = \"good\"\nurl = \"https://api.example/?k=${WP22_T_KEY}\"\nbearer_env = \"WP22_T_BEARER\"\nenabled = false\n\
        [[rpc.endpoint]]\nname = \"wp22-t-url\"\nurl_env = \"WP22_T_URL_3\"\nenabled = false\n\
        [[rpc.endpoint]]\nname = \"wp22-t-limit\"\nurl = \"https://example.invalid/\"\nenabled = false\n\
        [state]\nurl = \"http://localhost\"\n[pool_refresh]\nenabled = true\nrpc = [\"good\"]\n";
    let mut cfg = Config::parse(base).unwrap();
    for n in ["haan", "alt1", "alt2", "alt3"] {
        cfg.pool_refresh.rpc = vec![n.into()];
        assert!(cfg.pool_refresh.check(&cfg.rpc).unwrap_err().contains("never Haan"), "{n}");
    }
    cfg.pool_refresh.rpc = vec!["good".into()];
    cfg.pool_refresh.check(&cfg.rpc).unwrap();
    assert_eq!(cfg.pool_refresh.env_names(&cfg.rpc), ["WP22_T_BEARER", "WP22_T_KEY"]);
    let pairs = vec![("WP22_T_KEY".to_string(), "k".to_string()), ("WP22_T_BEARER".into(), "b".into()), ("WP22_T_OTHER".into(), "o".into()), ("HAAN_API_KEY".into(), "secret".into())];
    let (set, remove) = env_plan(pairs, &["WP22_T_KEY".to_string(), "WP22_T_BEARER".to_string(), "HAAN_API_KEY".to_string()],
        vec!["PATH".into(), "HAAN_X_TOKEN".into(), "haan_api_key".into()]);
    assert_eq!(set, [("WP22_T_KEY".to_string(), "k".to_string()), ("WP22_T_BEARER".into(), "b".into())], "only what the endpoints name, never a HAAN variable");
    assert_eq!(remove, ["HAAN_X_TOKEN", "haan_api_key"]);
    // a url_env resolving to Haan (any case) is refused when the refresh starts
    std::env::set_var("WP22_T_URL_3", "https://Rpc.HAANDIGITAL.eu/abc");
    cfg.pool_refresh.rpc = vec!["wp22-t-url".into()];
    cfg.pool_refresh.check(&cfg.rpc).unwrap();
    assert!(format!("{:#}", RpcChain::new(&cfg).err().unwrap()).contains("never Haan"));
    assert!(is_haan_url("https://RPC.HaanDigital.eu/") && !is_haan_url("https://api.mainnet-beta.solana.com"));
    // the limiter: the policy's rate, a burst of 1, on the endpoint's name
    cfg.pool_refresh.rpc = vec!["wp22-t-limit".into()];
    cfg.pool_refresh.rpc_max_rps = 1.5;
    let _chain = RpcChain::new(&cfg).unwrap();
    assert_eq!(crate::rpc::Registry::global().limits_json()["wp22-t-limit"], json!({ "max_rps": 1.5, "burst": 1.0 }));
}

/// Review #9: registry pools count toward a token's group only when the boot loads them (`[pools] registry_all`)
#[test]
fn registry_pools_count_only_with_registry_all() {
    let d = tmp("reg");
    let f = d.join("registry.json");
    std::fs::write(&f, json!([{ "venue": "DLMM", "pool": b58(&k(1)), "t0": b58(&tok(1)), "t1": b58(&WSOL) }, { "venue": "Orca", "pool": b58(&k(2)), "t0": "x", "t1": "y" }]).to_string()).unwrap();
    let cfg = |all: bool| Config::parse(&format!("config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\nregistry_json = \"{}\"\nregistry_all = {all}\n\
        [rpc]\n[state]\nurl = \"http://localhost\"\n", f.display())).unwrap();
    assert_eq!(registry_for(&cfg(true)).iter().map(|r| r.pool.clone()).collect::<Vec<_>>(), [b58(&k(1))], "our venues only");
    assert!(registry_for(&cfg(false)).is_empty());
    let _ = std::fs::remove_dir_all(&d);
}

/// Review #12: the refresh runs below the segment for the CPU (nice +10) and the disk (I/O class idle); in a thread of
/// its own here (both are per thread on Linux, and threads made later inherit them)
#[test]
fn the_refresh_runs_below_the_segment() {
    let (before, v, io) = std::thread::spawn(|| {
        let before = unsafe { libc::getpriority(libc::PRIO_PROCESS, 0) };
        let v = lower_priority();
        (before, v, unsafe { libc::syscall(libc::SYS_ioprio_get, 1, 0) })
    }).join().unwrap();
    assert_eq!(v["io_class"], "idle", "{v}");
    assert_eq!(io, 3 << 13, "IOPRIO_CLASS_IDLE");
    assert_eq!(v["nice"].as_i64(), Some((before + 10).min(19) as i64), "{v}");
}

/// Fail-safe: more listed pools dead in one refresh than max(25, a twentieth of the list), among those the last segment's
/// boot found alive, is the RPC's or a decoder's fault, not the pools': the plan refuses (the refresh keeps the previous
/// list, with the reason). Pools the boot had already dropped go whatever their number
#[test]
fn many_dead_listed_pools_keep_the_previous_list() {
    let mut w = World::new();
    let t = tok(1);
    for n in 1..=40 { if n <= 14 { w.dlmm(k(n), t, *WSOL, 5_000_000_000); } else { w.put(k(n), None); } }
    let rows: Vec<Row> = (1..=40).map(|n| row(Venue::Dlmm, k(n))).collect();
    let e = plan(&pol(), &inputs(&rows, vec![], vec![], &w), "x").unwrap_err();
    assert!(e.contains("26 of the 40 listed pools came back dead (more than 25 in one refresh)"), "{e}");
    // the last segment's boot found them all alive: as suspect
    let all: Vec<Pk> = (1..=40).map(k).collect();
    let e = plan(&pol(), &inputs(&rows, vec![seg("p1", &all, &[k(1)], true)], vec![], &w), "x").unwrap_err();
    assert!(e.contains("all alive at the last segment's boot"), "{e}");
    // its boot had already dropped them (a stale list): they go, whatever their number
    let alive: Vec<Pk> = (1..=14).map(k).collect();
    let out = plan(&pol(), &inputs(&rows, vec![seg("p1", &all, &[], true), seg("p2", &alive, &alive, true)], vec![], &w), "x").unwrap();
    assert_eq!((out.rows.len(), out.report["counts"]["dropped_by"]["dead:missing"].as_u64()), (14, Some(26)));
    // 25 dead: the bound itself passes (pools die)
    w.dlmm(k(15), t, *WSOL, 5_000_000_000);
    let out = plan(&pol(), &inputs(&rows, vec![], vec![], &w), "x").unwrap();
    assert_eq!((out.rows.len(), out.report["counts"]["dropped_by"]["dead:missing"].as_u64()), (15, Some(25)));
}

/// The plan is a function of its inputs: the same inputs (in any order of candidates) give the same list and report;
/// an account the plan needs that was not fetched is an error (the refresh then keeps the previous list)
#[test]
fn the_plan_is_deterministic_and_refuses_incomplete_inputs() {
    let mut w = World::new();
    let (ta, tc) = (tok(1), tok(3));
    w.pump(k(1), ta, 50_000_000_000);
    w.dlmm(k(10), ta, *WSOL, 9_000_000_000);
    w.pump(k(11), tc, 30_000_000_000);
    w.dlmm(k(12), tc, *WSOL, 3_000_000_000);
    let rows = vec![row(Venue::PumpSwap, k(1))];
    let c = vec![cand(k(10), Src::Gt, Some(ta), 10.0), cand(k(11), Src::Ds, Some(tc), 5.0), cand(k(12), Src::Ds, Some(tc), 5.0)];
    let mut rc = c.clone();
    rc.reverse();
    let a = plan(&pol(), &inputs(&rows, vec![], c.clone(), &w), "x").unwrap();
    let b = plan(&pol(), &inputs(&rows, vec![], rc, &w), "x").unwrap();
    assert_eq!(list_csv(&a.rows), list_csv(&b.rows));
    assert_eq!(a.report, b.report);
    assert_eq!(a.rows.len(), 4);
    let mut i = inputs(&rows, vec![], c.clone(), &w);
    i.accounts.remove(&b58(&vault_of(k(12), 2)));
    assert!(plan(&pol(), &i, "x").unwrap_err().contains("was not fetched"));
    let mut i = inputs(&rows, vec![], c, &w);
    i.accounts.remove(&b58(&k(1)));
    assert!(plan(&pol(), &i, "x").is_err(), "a listed pool's account too");
}

/// recorded chain accounts (the e2e fixture): an account not recorded is none on chain
struct Recorded { accts: HashMap<Pk, Account>, calls: usize, fail: bool }
impl Chain for Recorded {
    fn accounts(&mut self, keys: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> {
        self.calls += 1;
        if self.fail { return Err("HTTP 429 Too Many Requests (test)".into()); }
        Ok(keys.iter().map(|k| self.accts.get(k).cloned()).collect())
    }
    fn name(&self) -> String { "recorded".into() }
}
fn recorded(fail: bool) -> Recorded {
    let f = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh/accounts.json");
    let m: BTreeMap<String, Option<SavedAcct>> = serde_json::from_slice(&std::fs::read(f).unwrap()).unwrap();
    Recorded { accts: m.into_iter().filter_map(|(k, a)| Some((pk_opt(&k)?, a?.account()?))).collect(), calls: 0, fail }
}

/// the e2e fixture's records: one segment (fx-p1) in a campaign directory `fx` under `root`, from
/// testdata/poolrefresh/fx-p1-records.json (record streams are *.jsonl, which .gitignore keeps out of git)
fn fixture_runs(root: &Path) -> PathBuf {
    let f = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh/fx-p1-records.json");
    let v: Value = serde_json::from_slice(&std::fs::read(f).unwrap()).unwrap();
    let d = root.join("fx").join("fx-p1");
    std::fs::create_dir_all(&d).unwrap();
    for (name, body) in v["files"].as_object().unwrap() { std::fs::write(d.join(name), body.as_str().unwrap()).unwrap(); }
    root.join("fx")
}

/// the e2e fixture's config: the recorded current list, the verification endpoint (never called: recorded)
pub(crate) fn fixture_cfg() -> Config {
    let t = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh");
    Config::parse(&format!("config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"{}\"\n[rpc]\n[[rpc.endpoint]]\nname = \"public\"\n\
        url = \"https://api.mainnet-beta.solana.com\"\nenabled = false\n[state]\nurl = \"http://localhost\"\n[pool_refresh]\nenabled = true\n", t.join("current.csv").display())).unwrap()
}

/// End to end on recorded fixtures (testdata/poolrefresh: GeckoTerminal's lists and DexScreener's token pairs as they
/// answered on 2026-10-06, the chain accounts as the public RPC answered, a segment's records naming the listed STONK
/// pools and a rival arbitrage through BINDER's DLMM pool): BINDER enters with its verified pools (one from our
/// records, one from the trending lists), the dead pool goes, the rest is kept; the list, the report and the inputs file
/// are written, and the inputs file replays to the same list byte for byte
#[test]
fn a_refresh_end_to_end_on_recorded_fixtures() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh");
    let out_dir = tmp("e2e");
    let cfg = fixture_cfg();
    // the output directory does not exist yet (a pre-flight's): the list, the report and the inputs file all land in it
    let o = Opts { runs: vec![fixture_runs(&out_dir)], out: out_dir.join("preflight/pools-fx-p2.csv"), segment: "fx-p2".into(), ..Default::default() };
    let mut web = DirWeb { dir: base.join("api"), asked: vec![] };
    let mut chain = recorded(false);
    let r = refresh(&cfg, &o, &mut web, &mut chain).unwrap();
    assert_eq!(r["status"], "ok", "{r:#}");
    assert_eq!(r["inputs_file"].as_str(), Some(out_dir.join("preflight/pools-fx-p2.csv.inputs.json").display().to_string().as_str()));
    assert_eq!(r["inputs_sha256"].as_str(), Some(crate::provenance::sha256_hex(&std::fs::read(out_dir.join("preflight/pools-fx-p2.csv.inputs.json")).unwrap()).as_str()));
    assert!(r["inputs_error"].is_null(), "{}", r["inputs_error"]);
    assert!(out_dir.join("preflight/pools-fx-p2.csv.report.json").is_file());
    let added: Vec<(String, String)> = r["added"].as_array().unwrap().iter().map(|a| (a["pool"].as_str().unwrap()[..8].to_string(), a["src"].as_str().unwrap().to_string())).collect();
    assert_eq!(added[..2], [("67mcDJDV".to_string(), "records".to_string()), ("CHQ5CAEG".to_string(), "gt".to_string())], "BINDER first: our records, then the trending list");
    assert_eq!(r["counts"]["added"].as_u64(), Some(14), "{}", r["counts"]);
    assert_eq!(r["counts"]["added_by_source"], json!({ "records": 1, "gt": 2, "ds": 11 }));
    assert_eq!(r["counts"]["rejected_by"], json!({ "liquidity": 4 }), "BINDER's 1-SOL DLMM pool and the other thin ones");
    let binder = r["top_tokens"].as_array().unwrap().iter().find(|t| t["token"] == "BQxzR4pLkDw46gzbrkRjFuUSsgvN5BhTWHh6EXUwf3F").unwrap();
    assert_eq!(binder["pools"].as_u64(), Some(2), "{binder}");
    assert_eq!(r["dropped"].as_array().unwrap().iter().map(|d| d["why"].as_str().unwrap()).collect::<Vec<_>>(), ["dead:missing"]);
    assert_eq!((r["counts"]["kept"].as_u64(), r["counts"]["kept_active"].as_u64()), (Some(6), Some(3)), "the three STONK pools active, three idle");
    assert_eq!(r["current"]["unreadable_rows"].as_u64(), Some(1));
    assert_eq!(r["sources"]["geckoterminal"]["status"], "ok");
    assert_eq!(r["sources"]["dexscreener"]["requests"].as_u64(), Some(4), "{}", r["sources"]);
    assert_eq!(r["sources"]["records"]["status"], "ok");
    assert_eq!(web.asked.len(), 8, "4 GeckoTerminal lists, 4 tokens");
    assert_eq!(chain.calls as u64, r["rpc"]["calls"].as_u64().unwrap());
    let body = std::fs::read(&o.out).unwrap();
    assert_eq!(r["out"]["sha256"].as_str(), Some(crate::provenance::sha256_hex(&body).as_str()));
    let (rows, _) = parse_list(std::str::from_utf8(&body).unwrap()).unwrap();
    assert_eq!(rows.len(), 20);
    assert!(rows.iter().filter(|x| x.source.starts_with("wp22:")).all(|x| x.source.ends_with(":fx-p2")));
    // every pool added was verified on chain: its account recorded, a venue's, decoding with the engine's decoder
    for a in r["added"].as_array().unwrap() {
        let p = pk_opt(a["pool"].as_str().unwrap()).unwrap();
        let acct = chain.accts.get(&p).expect("verified on chain");
        let v = Venue::of_program(&acct.owner).unwrap();
        assert_eq!(venue_name(v), a["venue"].as_str().unwrap());
        assert!(pools::meta_of(v, &p, &acct.data).is_some());
        assert!(a["quote_liquidity"].as_u64().unwrap() >= 2_000_000_000);
    }
    // the inputs file replays to the same list, with no web and no chain
    let o2 = Opts { inputs: Some(PathBuf::from(r["inputs_file"].as_str().unwrap())), out: out_dir.join("replayed.csv"), segment: "fx-p2".into(), ..Default::default() };
    struct No;
    impl Web for No { fn get(&mut self, _: &str) -> std::result::Result<String, String> { panic!("no web in a replay") } }
    impl Chain for No { fn accounts(&mut self, _: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> { panic!("no chain in a replay") } fn name(&self) -> String { "none".into() } }
    let r2 = refresh(&cfg, &o2, &mut No, &mut No).unwrap();
    assert_eq!(std::fs::read(&o2.out).unwrap(), body, "the same inputs, the same list");
    assert_eq!(r2["added"], r["added"]);
    // review #7: the inputs carry the policy, the segment and the current list's hash: a replay refuses another policy
    // or another current list
    let saved = load_inputs(Path::new(r["inputs_file"].as_str().unwrap())).unwrap();
    assert_eq!((saved.policy.as_ref(), saved.segment.as_deref(), saved.failure.as_deref()), (Some(&cfg.pool_refresh), Some("fx-p2"), None));
    let mut other = fixture_cfg();
    other.pool_refresh.max_adds = 7;
    assert!(format!("{:#}", refresh(&other, &o2, &mut No, &mut No).unwrap_err()).contains("another [pool_refresh] policy"));
    let o3 = Opts { current: Some(o.out.clone()), ..o2.clone() };
    assert!(format!("{:#}", refresh(&cfg, &o3, &mut No, &mut No).unwrap_err()).contains("is not the current list the refresh read"));
    let _ = std::fs::remove_dir_all(&out_dir);
}

/// Fail-safe: a verification that cannot complete (the RPC refuses, the deadline passes) writes the previous list byte
/// for byte, with `status` kept_previous and the reason; sources that fail (no web) only add nothing
#[test]
fn a_failed_verification_keeps_the_previous_list() {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/poolrefresh");
    let out_dir = tmp("fail");
    let cfg = fixture_cfg();
    let o = Opts { runs: vec![fixture_runs(&out_dir)], out: out_dir.join("next.csv"), segment: "fx-p2".into(), ..Default::default() };
    let mut web = DirWeb { dir: base.join("api"), asked: vec![] };
    let r = refresh(&cfg, &o, &mut web, &mut recorded(true)).unwrap();
    assert_eq!(r["status"], "kept_previous");
    assert!(r["reason"].as_str().unwrap().contains("429"), "{}", r["reason"]);
    assert_eq!(std::fs::read(&o.out).unwrap(), std::fs::read(base.join("current.csv")).unwrap(), "the previous list, unchanged");
    assert_eq!(r["out"]["sha256"], r["current"]["sha256"]);
    assert!(summary_line(&r).starts_with("kept the previous list"), "{}", summary_line(&r));
    // review #7: the failure is in the inputs file, so its replay keeps the previous list too, for the same reason
    struct Off;
    impl Web for Off { fn get(&mut self, _: &str) -> std::result::Result<String, String> { panic!("no web in a replay") } }
    impl Chain for Off { fn accounts(&mut self, _: &[Pk]) -> std::result::Result<Vec<Option<Account>>, String> { panic!("no chain in a replay") } fn name(&self) -> String { "none".into() } }
    let o2 = Opts { inputs: Some(PathBuf::from(r["inputs_file"].as_str().unwrap())), out: out_dir.join("replayed.csv"), segment: "fx-p2".into(), ..Default::default() };
    let r2 = refresh(&cfg, &o2, &mut Off, &mut Off).unwrap();
    assert_eq!((r2["status"].as_str(), &r2["reason"]), (Some("kept_previous"), &r["reason"]));
    assert_eq!(std::fs::read(&o2.out).unwrap(), std::fs::read(&o.out).unwrap());
    // no web at all: our records still propose (BINDER's DLMM pool has no second pool without the trending lists: refused)
    struct Down;
    impl Web for Down { fn get(&mut self, _: &str) -> std::result::Result<String, String> { Err("timeout".into()) } }
    let r = refresh(&cfg, &Opts { out: out_dir.join("n2.csv"), ..o.clone() }, &mut Down, &mut recorded(false)).unwrap();
    assert_eq!(r["status"], "ok");
    assert_eq!((r["sources"]["geckoterminal"]["status"].as_str(), r["sources"]["dexscreener"]["status"].as_str()), (Some("failed"), Some("none")));
    assert_eq!(r["counts"]["added"].as_u64(), Some(0));
    assert_eq!(r["counts"]["rejected_by"]["group"].as_u64(), Some(1), "{}", r["counts"]);
    // a deadline already past: nothing verified, the previous list
    let r = refresh(&cfg, &Opts { out: out_dir.join("n3.csv"), deadline_s: Some(0), ..o.clone() }, &mut DirWeb { dir: base.join("api"), asked: vec![] }, &mut recorded(false)).unwrap();
    assert_eq!(r["status"], "kept_previous");
    assert!(r["reason"].as_str().unwrap().contains("deadline"), "{}", r["reason"]);
    let _ = std::fs::remove_dir_all(&out_dir);
}

/// `[pool_refresh]`: off by default and not serialized while off (a config without it hashes as before); checked when
/// on (never Haan, a named endpoint, the lead above the timeout); `arbx check`'s line
#[test]
fn the_policy_keys() {
    let min = "config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[[rpc.endpoint]]\nname = \"haan\"\nurl = \"https://rpc.haandigital.eu/\"\n\
        [[rpc.endpoint]]\nname = \"public\"\nurl = \"https://api.mainnet-beta.solana.com\"\nenabled = false\n[[rpc.endpoint]]\nname = \"h2\"\nurl = \"https://x.haandigital.eu/\"\n\
        [state]\nurl = \"http://localhost\"\n";
    let off = Config::parse(min).unwrap();
    assert_eq!(off.pool_refresh, PoolRefreshCfg::default());
    assert!(!off.pool_refresh.enabled && off.pool_refresh.cap == 1500 && off.pool_refresh.rpc == ["public"]);
    assert!(serde_json::to_value(&off).unwrap().get("pool_refresh").is_none(), "off: not serialized");
    let with_off = Config::parse(&format!("{min}[pool_refresh]\nenabled = false\ncap = 900\n")).unwrap();
    assert_eq!(with_off.normalized_sha256(), off.normalized_sha256(), "an off section hashes as no section");
    let on = |extra: &str| Config::parse(&format!("{min}[pool_refresh]\nenabled = true\n{extra}\n")).map_err(|e| format!("{e:#}"));
    let c = on("").unwrap();
    assert_ne!(c.normalized_sha256(), off.normalized_sha256(), "on: part of the hash");
    assert_eq!(serde_json::to_value(&c).unwrap()["pool_refresh"]["lead_s"], 300);
    assert!(c.pool_refresh.describe().starts_with("pool refresh (WP-22): on: a refresh 300 s before each segment ends"));
    assert!(off.pool_refresh.describe().contains("off"));
    assert!(on("rpc = [\"haan\"]").unwrap_err().contains("never Haan"));
    assert!(on("rpc = [\"h2\"]").unwrap_err().contains("never Haan"), "by its host too");
    assert!(on("rpc = [\"nope\"]").unwrap_err().contains("no [[rpc.endpoint]] of that name"));
    assert!(on("lead_s = 200\ntimeout_s = 240").unwrap_err().contains("must be above timeout_s"));
    assert!(on("quotes = [\"USDT\"]").unwrap_err().contains("quotes"));
    assert!(on("max_adds = 2000").unwrap_err().contains("above cap"));
    assert!(on("geckoterminal_per_min = 100").unwrap_err().contains("geckoterminal_per_min"));
    assert!(on("min_liquidity_sol = -1").unwrap_err().contains("min_liquidity_sol"));
    assert!(on("sources = 1").unwrap_err().contains("unknown field `sources`"));
    assert!(on("quotes = [\"WSOL\", \"USDC\"]\nmin_liquidity_sol = 0.5\nrpc_max_rps = 1").is_ok());
}

/// Replay: a segment's input is its own list. `arbx replay` takes the registry from the segment's pools.json (what the
/// segment booted from its own list, `--pools-csv`, recorded in meta.json `overrides.pools_csv`), never from the
/// config's `[pools] seed_csv` (here a list that does not exist)
#[test]
fn replay_reads_the_segments_own_list() {
    let d = tmp("replay");
    let m = |n: u8| PoolMeta { venue: Venue::Dlmm, pool: k(n), t0: tok(1), t1: *WSOL, vault0: vault_of(k(n), 1), vault1: vault_of(k(n), 2), t0_prog: *pda::TOKEN_PROGRAM,
        t1_prog: *pda::TOKEN_PROGRAM, extra: vec![], flag: false };
    let rows = vec![row(Venue::Dlmm, k(1)), Row { venue: Venue::Dlmm, pool: k(2), source: "wp22:gt:c-p2".into() }];
    let list = d.join("pools-c-p2.csv");
    std::fs::write(&list, list_csv(&rows)).unwrap();
    let mut reg = pools::Registry { pools: vec![m(1), m(2)], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
    for (i, p) in [k(1), k(2)].iter().enumerate() { reg.by_pool.insert(*p, i); reg.seeds.insert(*p); }
    reg.pairs.insert(pair_key(&tok(1), &WSOL), vec![0, 1]);
    let roles = crate::rec::accounts::Roles::new(reg.watch_roles());
    crate::replay::write_pools_json(&d, &reg, &reg.static_accounts(), &roles).unwrap();
    std::fs::write(d.join("config.toml"), "config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"/nonexistent/seed-pools.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n").unwrap();
    std::fs::write(d.join("meta.json"), json!({ "overrides": { "pools_csv": { "path": list.display().to_string(), "sha256": crate::provenance::sha256_hex(&std::fs::read(&list).unwrap()) } } }).to_string()).unwrap();
    for f in ["journal.000.bin", "accounts.000.bin"] { std::fs::write(d.join(f), b"").unwrap(); }
    let i = crate::replay::inputs(&d, None, None).unwrap();
    assert_eq!(i.pools_path, d.join("pools.json"));
    assert_eq!(i.reg.pools.iter().map(|m| m.pool).collect::<Vec<_>>(), pools_of(&rows), "the segment's own list");
    assert!(rows.iter().all(|r| i.reg.seeds.contains(&r.pool)));
    assert_eq!(i.cfg.pools.seed_csv, "/nonexistent/seed-pools.csv", "the config's list is never read");
    assert_eq!(i.meta.as_ref().unwrap()["overrides"]["pools_csv"]["path"].as_str(), Some(list.display().to_string().as_str()));
    let _ = std::fs::remove_dir_all(&d);
}
