// dip36 FP-NOBOT unit tests (src/fpnb.rs): the frozen models (sha256, parse), the PARITY with the study's fixture (scores from the given
// inputs; the chain inputs rebuilt from the raw chain when /home/it/sniper-data/flatperfect/engine_fixture_r55.bin exists), missing
// data, the bot list's shapes.
use super::*;

/// a pubkey from a chain id (the u64 prefix; the rest zero)
fn p64(v: u64) -> Pk { let mut k = [0u8; 32]; k[..8].copy_from_slice(&v.to_be_bytes()); k }

/// the numbers of a JSON array, parsed exactly (Rust's f64 parser; null = NaN)
fn arr_exact(line: &str, key: &str) -> Vec<f64> {
    let i = line.find(&format!("\"{key}\": [")).unwrap_or_else(|| panic!("no {key}")) + key.len() + 5;
    let j = i + line[i..].find(']').unwrap();
    line[i..j].split(',').map(|s| { let s = s.trim(); if s == "null" { f64::NAN } else { s.parse::<f64>().unwrap() } }).collect()
}

fn fixture() -> Vec<String> {
    let z = std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/fpnb/parity_r55.jsonl.zst")).unwrap();
    String::from_utf8(zstd::decode_all(&z[..]).unwrap()).unwrap().lines().map(|s| s.to_string()).collect()
}

#[test]
fn fpnb_models_frozen() {
    let m = Models::frozen().expect("sha256 + parse");
    for t in m.t2.iter().chain(m.rearm.iter()) { assert_eq!(t.trees.len(), 200); }
    // the input order is the fixture's
    let l = fixture();
    let meta: serde_json::Value = serde_json::from_str(&l[0]).unwrap();
    let f: Vec<&str> = meta["meta"]["features"].as_array().unwrap().iter().map(|x| x.as_str().unwrap()).collect();
    assert_eq!(f, FEATS.to_vec());
    assert!(l[0].contains(&format!("\"T2\": {THR_T2}")) && l[0].contains(&format!("\"rearm\": {THR_REARM}")), "the frozen thresholds");
    for (i, k) in SEND_IX.iter().enumerate() { assert!(FEATS[*k].starts_with("pf_") || FEATS[*k].ends_with("_20s"), "{i} {}", FEATS[*k]); }
    assert_eq!(FEATS.iter().filter(|f| f.starts_with("pf_")).count() + 2, SEND_IX.len());
}

/// PARITY (1): the fixture's 1,048 per-send input vectors -> our tree walker -> the seeds' and the mean score, and the block
#[test]
fn fpnb_parity_scores() {
    let m = Models::frozen().unwrap();
    let l = fixture();
    let (mut n, mut maxe, mut blocks, mut t2n, mut ran) = (0, 0.0f64, 0, 0, 0);
    for line in &l[1..] {
        let v: serde_json::Value = serde_json::from_str(line).unwrap();
        let x = X(arr_exact(line, "x").try_into().unwrap());
        let t2 = v["kind"] == "T2";
        let s = m.score(t2, &x);
        let want = v["score"].as_f64().unwrap();
        for (k, ws) in v["seed_scores"].as_array().unwrap().iter().enumerate() { maxe = maxe.max((s.seeds[k] - ws.as_f64().unwrap()).abs()); }
        maxe = maxe.max((s.score - want).abs());
        assert_eq!(s.score >= s.thr, v["block"].as_bool().unwrap(), "{line}");
        assert!((s.thr - v["thr"].as_f64().unwrap()).abs() < 1e-15);
        if v["block"] == true { blocks += 1; }
        if t2 { t2n += 1; } else { ran += 1; }
        n += 1;
    }
    eprintln!("fpnb parity: {n} vectors ({t2n} T2, {ran} re-arm), {blocks} blocks, max |score error| {maxe:.3e}");
    assert_eq!(n, 1048);
    assert!(t2n > 0 && ran > 0);
    assert!(maxe < 1e-9, "max error {maxe}");
}

/// missing data: NaN goes left / right per each split's missing type; "None" splits treat NaN as 0.0
#[test]
fn fpnb_missing_data() {
    let t = Model::parse("objective=binary sigmoid:1\nmax_feature_idx=152\n\nTree=0\nnum_leaves=3\nnum_cat=0\nsplit_feature=5 7\nthreshold=1.5 -0.5\n\
        decision_type=8 2\nleft_child=1 -1\nright_child=-3 -2\nleaf_value=0.1 0.2 0.3\n\n\nend of trees\n").unwrap();
    // node 0: feature 5, NaN type, default right (dt 8 = missing NaN, default_left false); node 1: feature 7, type None, default left
    let mut x = X::default();
    x.0[5] = f64::NAN;
    assert_eq!(t.raw(&x.0), 0.3, "NaN on a NaN-type split: the default side (right)");
    x.0[5] = 1.0; x.0[7] = f64::NAN;
    assert_eq!(t.raw(&x.0), 0.2, "NaN on a None-type split = 0.0 > -0.5: right");
    x.0[7] = -1.0;
    assert_eq!(t.raw(&x.0), 0.1);
    // default_left on a NaN split (dt 10)
    let t2 = Model::parse("objective=binary sigmoid:1\nmax_feature_idx=152\n\nTree=0\nnum_leaves=2\nnum_cat=0\nsplit_feature=0\nthreshold=1\ndecision_type=10\n\
        left_child=-1\nright_child=-2\nleaf_value=1 2\n\nend of trees").unwrap();
    assert_eq!(t2.raw(&[f64::NAN; N_FEAT]), 1.0);
    assert_eq!(t2.raw(&[5.0; N_FEAT]), 2.0);
    // the frozen models score an all-missing vector (warm-up, no data) without panicking, in (0, 1)
    let m = Models::frozen().unwrap();
    for t2 in [true, false] { let s = m.score(t2, &X::default()); assert!(s.score > 0.0 && s.score < 1.0); }
    // a store that saw nothing: the arm is not covered, the regime / whale inputs missing
    let st = Store::new(ours());
    let bots = BotList::parse(br#"["haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq"]"#, &ours()).unwrap();
    let mut x = X::default();
    let c = st.arm_chain(&ArmIn { t2: true, mint: [1; 32], s: 100, i: 3, whale: [2; 32] }, &bots, &mut x);
    assert_eq!(c.nc, Some("mint_not_seen"));
    assert!(x.get("g_nd_30m").is_nan() && x.get("wh_n").is_nan() && !c.wh_ok && !c.warm);
    st.send(&c, 101, &bots, &mut x);
    assert!(x.get("pf_n").is_nan() && x.get("pf_slots") == 2.0);
    // own results: fewer than 5 known -> NaN; the 15-min sums 0
    let mut b = Book::default();
    for k in 0..3 { b.add_own(OwnPos { k: 1_000 + k, pnl: -0.01, fol: 1.0, mint: [9; 32], whale: None, creator: None }); }
    b.feats(1_000_000, &[9; 32], None, None, &mut x);
    assert!(x.get("o_mean5").is_nan() && x.get("o_n_15m") == 3.0 && x.get("o_flat_15m") == 1.0 && x.get("o_tok_n") == 3.0 && x.get("o_wh_sum").is_nan() && x.get("s_mean10").is_nan());
}

#[test]
fn fpnb_bot_list_shapes() {
    let ours = ours();
    let h1 = "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq";
    let x = "3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr";
    let new = "4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f";
    // v0
    let l = BotList::parse(format!(r#"{{"cohort": ["{x}"], "named": ["{h1}", "{}"]}}"#, OURS_B58[0]).as_bytes(), &ours).unwrap();
    assert!(l.n == 2 && l.is_core(&pk(h1).unwrap()) && !l.is_core(&pk(x).unwrap()) && !l.is_f(&pk(OURS_B58[0]).unwrap()), "ours never");
    // registry engine view with operators (a new haqq wallet joins CORE), an inactive one left out
    let l = BotList::parse(format!(r#"{{"version": 7, "engine_view": [{{"wallet": "{new}", "operator": "haqq"}}, {{"address": "{x}", "op": "3qvu", "active": false}}]}}"#).as_bytes(), &ours).unwrap();
    assert!(l.n == 1 && l.is_core(&pk(new).unwrap()) && l.ver == "7" && l.sha8.len() == 8);
    let l = BotList::parse(format!(r#"{{"engine view": {{"wallets": ["{x}"]}}}}"#).as_bytes(), &ours).unwrap();
    assert!(l.n == 1 && l.ops[&pk(x).unwrap()] == "3qvu", "seed operator");
    for bad in ["{}", "[]", r#"{"engine_view": ["notakey!"]}"#, "{nope"] { assert!(BotList::parse(bad.as_bytes(), &ours).is_err(), "{bad}"); }
    // the real v0 file, when present
    if let Ok(b) = std::fs::read("/home/it/sniper-data/flatperfect/cohort_full_b58.json") {
        let l = BotList::parse(&b, &ours).unwrap();
        assert_eq!((l.n, l.core.len()), (111, 5));
    }
}

/// the store: dedupe, order, the trigger row, prior rows, holdings, send inputs, the gap -> not covered; membership at query time
#[test]
fn fpnb_store_basics() {
    let ours = ours();
    let mut st = Store::new(ours.clone());
    let (mint, wh, a, bot) = ([1u8; 32], [2u8; 32], [3u8; 32], pk("3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr").unwrap());
    let row = |s: u64, i: u32, user: Pk, buy: bool, tok: u64, vsol: u64| Row { s, i, j: 0, buy, user, sol: 1_000_000_000, tok, vsol };
    st.create(mint, 100);
    st.trade(mint, row(100, 1, a, true, 50_000_000_000_000, 31_000_000_000));
    st.trade(mint, row(102, 4, bot, true, 10_000_000_000_000, 32_000_000_000));
    st.trade(mint, row(102, 4, bot, true, 10_000_000_000_000, 32_000_000_000));
    assert_eq!(st.st.dup_rows, 1);
    st.trade(mint, row(101, 2, a, false, 20_000_000_000_000, 30_000_000_000)); // out of order
    st.trade(mint, row(103, 9, wh, true, 70_000_000_000_000, 40_000_000_000)); // the trigger
    st.trade(mint, row(104, 1, bot, true, 1, 41_000_000_000));
    assert!(st.fail(104, 0, bot, true, &[[7u8; 32], mint]));
    assert!(!st.fail(104, 1, bot, true, &[[7u8; 32]]), "no tracked mint: dropped");
    let empty = BotList::parse(br#"["haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq"]"#, &ours).unwrap();
    let with = BotList::parse(br#"["3qvuM3U5UZPVagL1spxmgVgUvzT3h49gyJZyagxRtqKr"]"#, &ours).unwrap();
    let mut x = X::default();
    let c = st.arm_chain(&ArmIn { t2: true, mint, s: 103, i: 9, whale: wh }, &empty, &mut x);
    assert!(c.nc.is_none(), "{:?}", c.nc);
    assert_eq!((x.get("n_prior"), x.get("buyers"), x.get("sellers"), x.get("age"), x.get("age_cens")), (3.0, 2.0, 1.0, 3.0, 1.0), "first row within 2 slots of the feed start");
    assert!((x.get("top1") - 3.0).abs() < 1e-12 && (x.get("trig_pct") - 7.0).abs() < 1e-12 && x.get("bot_tr_n") == 0.0);
    let mut x2 = X::default();
    st.arm_chain(&ArmIn { t2: true, mint, s: 103, i: 9, whale: wh }, &with, &mut x2);
    assert_eq!((x2.get("bot_tr_n"), x2.get("bot_hold_n"), x2.get("bot_last_age")), (1.0, 1.0, 1.0), "membership at query time");
    st.send(&c, 105, &with, &mut x2);
    assert_eq!((x2.get("pf_n"), x2.get("pf_bot_buys"), x2.get("pf_bfail"), x2.get("pf_fail_all"), x2.get("pf_slots"), x2.get("pf_last_gap")), (1.0, 1.0, 1.0, 1.0, 3.0, 0.0));
    st.send(&c, 104, &with, &mut x2);
    assert_eq!((x2.get("pf_n"), x2.get("pf_bfail"), x2.get("pf_vmax")), (0.0, 0.0, 1.0), "data <= t - 1 only");
    // a feed gap: not covered any more
    st.trade([5u8; 32], row(104 + GAP_SLOTS + 10, 0, a, true, 1, 1));
    assert_eq!(st.covered(&c), Some("feed_gap"));
}

/// PARITY (2): the chain inputs rebuilt by the store from the raw chain rows (the fixture of fp_engine_fixture.py), and the own /
/// shadow / arm-record inputs from the run's records, against the parity file's x, then the score
#[test]
fn fpnb_parity_chain_inputs() {
    let Ok(b) = std::fs::read("/home/it/sniper-data/flatperfect/engine_fixture_r55.bin") else {
        eprintln!("fpnb_parity_chain_inputs: no engine_fixture_r55.bin (run ops/strategies/presend/flatperfect/fp_engine_fixture.py): skipped");
        return;
    };
    let nl = b.iter().position(|c| *c == b'\n').unwrap();
    let h: serde_json::Value = serde_json::from_slice(&b[..nl]).unwrap();
    let (nr, nf, nw) = (h["rows"].as_u64().unwrap() as usize, h["fails"].as_u64().unwrap() as usize, h["wh"].as_u64().unwrap() as usize);
    let body = &b[nl + 1..];
    assert_eq!(body.len(), nr * 57 + nf * 29 + nw * 21);
    let u64a = |c: &[u8], o: usize| u64::from_le_bytes(c[o..o + 8].try_into().unwrap());
    let u32a = |c: &[u8], o: usize| u32::from_le_bytes(c[o..o + 4].try_into().unwrap());
    let ours: Vec<Pk> = h["ours"].as_array().unwrap().iter().map(|v| p64(v.as_u64().unwrap())).collect();
    let mut bots = BotList::default();
    for v in h["bots"].as_array().unwrap() { let k = p64(v.as_u64().unwrap()); if !ours.contains(&k) { bots.set.insert(k); } }
    for v in h["core"].as_array().unwrap() { bots.core.insert(p64(v.as_u64().unwrap())); }
    bots.n = bots.set.len();
    let mut st = Store::new(ours);
    st.gap_slots = u64::MAX / 4;
    st.sweep_slots = u64::MAX / 4;
    let feed_lo = h["feed_lo"].as_u64().unwrap();
    st.wh_lookback = u64::MAX / 4;
    st.wh_need = 0;
    let wh: Vec<(Pk, WRow)> = body[nr * 57 + nf * 29..].chunks_exact(21).map(|c| (p64(u64a(c, 0)), WRow { m: u64a(c, 8), s: u32a(c, 16), f: c[20] })).collect();
    st.preload_wh(wh, PreSpan { from: 1, to: feed_lo - 1 });
    // every event in slot order (rows before fails within a slot); every mint created at its first event (all are tracked)
    enum Ev { R(Pk, Row), F(u64, u32, Pk, bool, Pk) }
    let mut evs: Vec<(u64, u8, Ev)> = Vec::with_capacity(nr + nf);
    for c in body[..nr * 57].chunks_exact(57) {
        let r = Row { s: u64a(c, 0), i: u32a(c, 8), j: u32a(c, 12) as i32, buy: c[32] == 1, user: p64(u64a(c, 24)), sol: u64a(c, 33), tok: u64a(c, 41), vsol: u64a(c, 49) };
        evs.push((r.s, 0, Ev::R(p64(u64a(c, 16)), r)));
    }
    for c in body[nr * 57..nr * 57 + nf * 29].chunks_exact(29) { evs.push((u64a(c, 0), 1, Ev::F(u64a(c, 0), u32a(c, 8), p64(u64a(c, 12)), c[28] == 1, p64(u64a(c, 20))))); }
    evs.sort_by_key(|e| (e.0, e.1));
    for (s, _, e) in evs {
        match e {
            Ev::R(m, r) => { if !st.tracked(&m) { st.create(m, s); } st.trade(m, r); }
            Ev::F(s, i, p, buy, m) => { if !st.tracked(&m) { st.create(m, s); } st.fail(s, i, p, buy, &[m]); }
        }
    }
    st.start = h["span_lo"].as_u64().unwrap();
    // own results / shadow
    let mut book = Book::default();
    for o in h["own"].as_array().unwrap() {
        book.add_own(OwnPos { k: o["k"].as_u64().unwrap_or_else(|| o["k"].as_f64().unwrap() as u64), pnl: o["pnl"].as_f64().unwrap(), fol: o["fol"].as_f64().unwrap(), mint: pk(o["mint"].as_str().unwrap()).unwrap(),
            whale: o["whale"].as_str().and_then(pk), creator: o["creator"].as_str().and_then(pk) });
    }
    for z in h["shadow"].as_array().unwrap() { book.add_sh(z[0].as_f64().unwrap() as u64, z[1].as_f64().unwrap()); }
    for z in h["shadow_arms"].as_array().unwrap() { book.add_sh_arm(z.as_f64().unwrap() as u64); }
    let models = Models::frozen().unwrap();
    let l = fixture();
    let mut lines: FxHashMap<String, Vec<String>> = FxHashMap::default();
    for line in &l[1..] { let v: serde_json::Value = serde_json::from_str(line).unwrap(); lines.entry(v["key"].as_str().unwrap().to_string()).or_default().push(line.clone()); }
    let (mut n, mut bad, mut maxe, mut kinds, mut stale) = (0, Vec::new(), 0.0f64, FxHashSet::default(), 0);
    for p in h["positions"].as_array().unwrap() {
        let t2 = p["kind"] == "T2";
        kinds.insert(t2);
        let a = ArmIn { t2, mint: p64(p["mint64"].as_u64().unwrap()), s: p["trig_slot"].as_u64().unwrap(), i: p["trig_idx"].as_u64().unwrap() as u32, whale: p64(p["whale64"].as_u64().unwrap()) };
        let mut x0 = X::default();
        let c = st.arm_chain(&a, &bots, &mut x0);
        assert!(c.nc.is_none(), "{p}: {:?}", c.nc);
        arm_fields(&p["arm"], t2, &mut x0);
        let t0 = p["t0"].as_u64().unwrap_or_else(|| p["t0"].as_f64().unwrap() as u64);
        book.feats(t0, &pk(p["mint"].as_str().unwrap()).unwrap(), pk(p["whale"].as_str().unwrap()).as_ref(), p["creator"].as_str().and_then(pk).as_ref(), &mut x0);
        for line in &lines[p["key"].as_str().unwrap()] {
            let v: serde_json::Value = serde_json::from_str(line).unwrap();
            let want = arr_exact(line, "x");
            let mut x = x0.clone();
            st.send(&c, v["send_slot"].as_u64().unwrap(), &bots, &mut x);
            for (k, f) in FEATS.iter().enumerate() {
                let (g, w) = (x.0[k], want[k]);
                // ex_r55.pkl (the own / shadow source) was rebuilt from a later log copy after the parity file (19:24 vs 19:16 PKT): its o_* / s_*
                // times moved by < 1 ms and one shadow arm more is in a 5-min window; the chain inputs are exact
                let tol = if f.starts_with("s_arms") { 1.0 } else if f.starts_with("o_") { 1e-6 * w.abs().max(1.0) } else { 1e-9 * w.abs().max(1.0) };
                let ok = (g.is_nan() && w.is_nan()) || (g - w).abs() <= tol;
                if ok && (g - w).abs() > 1e-9 * w.abs().max(1.0) { stale += 1; }
                if !ok { bad.push(format!("{} t={} {f}: got {g} want {w}", p["key"], v["send_slot"])); }
            }
            let s = models.score(t2, &x);
            maxe = maxe.max((s.score - v["score"].as_f64().unwrap()).abs());
            n += 1;
        }
    }
    eprintln!("fpnb chain parity: {n} vectors, {} input mismatches, {stale} own / shadow inputs within the stale-fixture tolerance, max score error {maxe:.3e}", bad.len());
    for b in bad.iter().take(40) { eprintln!("  {b}"); }
    assert!(kinds.len() == 2, "both kinds");
    assert!(bad.is_empty(), "{} mismatches", bad.len());
    assert!(maxe < 1e-9);
}

/// a real preload file (fp_preload.py), when FPNB_PRELOAD names one: parsed, every row's wallet in range, the span ~24 h
#[test]
fn fpnb_preload_real_file() {
    let Ok(p) = std::env::var("FPNB_PRELOAD") else { return };
    let b = std::fs::read(&p).unwrap();
    let pre = preload_parse(&b).unwrap();
    eprintln!("fpnb preload {p}: {} rows, span {}..{} ({:.1} h), {} own, {} shadow", pre.wh.len(), pre.span.from, pre.span.to,
        (pre.span.to - pre.span.from) as f64 * SLOT_S / 3600.0, pre.own.len(), pre.sh.len());
    assert!(!pre.wh.is_empty() && pre.wh.iter().all(|(_, r)| (r.s as u64) >= pre.span.from && (r.s as u64) <= pre.span.to));
    let mut st = Store::new(ours());
    st.preload_wh(pre.wh, pre.span);
    assert!(st.stats().wh_rows > 0);
}

/// SKIP-2 PARITY: the 200 r55 rows (s2_engine_fixture.py: the parity row + its presend_live_arm record): the score from x_filled to 1e-9,
/// would_skip; the arm-record inputs 1-34 rebuilt from the real arm record and the arm clock; the 17 send inputs are FP-NOBOT's names
#[test]
fn skip2_parity_persend() {
    let m = S2Model::frozen().unwrap();
    let z = std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/fpnb/skip2_parity_r55.jsonl.zst")).unwrap();
    let txt = String::from_utf8(zstd::decode_all(&z[..]).unwrap()).unwrap();
    for f in &m.feats[S2_ARM_N..] { let _ = feat_ix(f); }
    let (mut n, mut maxe, mut bad, mut skips, mut kinds) = (0, 0.0f64, Vec::new(), 0, FxHashSet::default());
    for line in txt.lines() {
        let v: serde_json::Value = serde_json::from_str(line).unwrap();
        let t2 = v["kind"] == "T2";
        kinds.insert(t2);
        let xf = arr_exact(line, "x_filled");
        let s = m.score(&xf);
        maxe = maxe.max((s - v["score"].as_f64().unwrap()).abs());
        assert_eq!(s < m.thr(t2), v["would_skip"].as_bool().unwrap(), "{}", v["key"]);
        if s < m.thr(t2) { skips += 1; }
        // the arm-record inputs from the record itself
        let clk = v["arm_clock_ns"].as_u64().unwrap();
        let a = s2_arm_fields(&v["arm"], clk);
        for (k, g) in a.iter().enumerate() {
            let w = v["x_raw"][&m.feats[k]].as_f64().unwrap_or(f64::NAN);
            let ok = (g.is_nan() && w.is_nan()) || (g - w).abs() <= 1e-9 * w.abs().max(1.0);
            if !ok { bad.push(format!("{} {}: got {g} want {w}", v["key"], m.feats[k])); }
        }
        // the median fill of the raw inputs gives x_filled
        let raw: Vec<f64> = m.feats.iter().map(|f| v["x_raw"][f].as_f64().unwrap_or(f64::NAN)).collect();
        maxe = maxe.max((m.score(&raw) - v["score"].as_f64().unwrap()).abs());
        n += 1;
    }
    eprintln!("skip2 parity: {n} rows, {skips} would-skip, max |score error| {maxe:.3e}, {} arm-input mismatches", bad.len());
    for b in bad.iter().take(20) { eprintln!("  {b}"); }
    assert!(n == 200 && kinds.len() == 2);
    assert!(maxe < 1e-9, "{maxe}");
    assert!(bad.is_empty());
}

/// SKIP-2 history: own results / activity / ledgers in record order (s2_table.py), the seed, missing values
#[test]
fn skip2_history_and_ledgers() {
    let mut h = S2Hist::default();
    let min = 60_000_000_000u64;
    let t0 = 1_000 * min;
    let f = h.feats(t0, "M1", "W1", Some("C1"));
    assert_eq!(f.len(), 21);
    assert!(f[0] == 0.0 && f[2].is_nan() && f[3].is_nan() && f[5].is_nan() && f[10].is_nan() && f[11] == 0.0 && f[14] == 0.0 && f[17].is_nan(), "{f:?}");
    assert!(h.feats(t0, "M1", "W1", None)[11].is_nan(), "no creator: NaN");
    h.on_arm(t0, "M1", 1, "W1", Some("C1"));
    h.on_skip(t0 + min);
    h.on_disarm("M1", 1, true);
    h.on_real(t0 + 2 * min, "M1", Some(1), 0.03);
    h.on_arm(t0 + 3 * min, "M2", 2, "W1", None);
    h.on_disarm("M2", 2, false);
    h.on_real(t0 + 4 * min, "M2", Some(2), -0.01);
    let f = h.feats(t0 + 70 * min, "M1", "W1", Some("C1"));
    // own_n60 counts realized in [now - 60 min, now): both are 66..68 min old -> 0
    assert_eq!((f[0], f[1]), (0.0, 0.0));
    assert!((f[2] - 0.02).abs() < 1e-12 && f[3] == 0.5 && f[4] == 0.5 && (f[5] - 66.0).abs() < 1e-9, "{f:?}");
    assert_eq!((f[6], f[7], f[8], f[9], f[10]), (0.0, 0.0, 0.0, 0.0, 0.5));
    assert_eq!((f[11], f[12], f[13]), (1.0, 0.03, 1.0), "creator C1: 1 position +0.03, 1 arm");
    assert!(f[14] == 2.0 && (f[15] - 0.02).abs() < 1e-12 && f[16] == 2.0 && f[17] == 0.5, "whale W1: {f:?}");
    assert_eq!((f[18], f[19], f[20]), (1.0, 1.0, 0.03), "mint M1");
    let f = h.feats(t0 + 5 * min, "M9", "W9", Some("C1"));
    assert_eq!((f[0], f[6], f[7], f[8]), (2.0, 2.0, 2.0, 1.0));
    // the seed: ledgers only
    let mut h = S2Hist::default();
    assert_eq!(h.seed(br#"{"cre": {"C1": [3, 0.5, 9]}, "wh": {"W1": [2, -0.1, 7, 4, 1]}, "mint": {"M1": [1, 0.02, 2]}}"#).unwrap(), 3);
    let f = h.feats(t0, "M1", "W1", Some("C1"));
    assert_eq!((f[11], f[12], f[13], f[14], f[15], f[16], f[17], f[18], f[19], f[20]), (3.0, 0.5, 9.0, 2.0, -0.1, 7.0, 0.25, 2.0, 1.0, 0.02));
    assert!(h.seed(b"{}").is_err());
    // the 4 failed-tx inputs missing: the "nf" score = the median filled ones
    let m = S2Model::frozen().unwrap();
    let mut x = vec![f64::NAN; S2_N];
    for i in S2_FAIL_IX { x[i] = 50.0; }
    assert!((m.score_nf(&x) - m.score(&vec![f64::NAN; S2_N])).abs() < 1e-12 && m.score(&x) != m.score_nf(&x));
}
