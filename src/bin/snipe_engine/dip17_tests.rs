// ===================================================================================================================
// dip17 tests (10-25 PKT): the QUIC landing lanes (kind soyas / solami, send/quic_lane.rs). Nothing changes without a
// [[send]] entry of those kinds:
//  * golden: every tx shape the engine builds is still dip15's / dip16's bytes (DIP15_GOLDEN), the FAST path's kind map of every
//    older kind is dip16's, a dip16 probe config parses, checks and serializes exactly as before (no new keys)
//  * the lanes: config parse (defaults, refusals), tip accounts and minimums, a path built with no lane listening (not fatal,
//    no junk bytes ever written to a lane, probe skipped)
// ===================================================================================================================
use super::*;
use arbx::config::SendKind;

#[test]
fn dip17_golden_no_quic_lane_equals_dip16() {
    let (d, n) = super::dip16_tests::golden_digest();
    assert_eq!(d, super::dip16_tests::DIP15_GOLDEN, "the tx bytes must be dip15's / dip16's ({n} shapes)");
    // the FAST path's kind map of every pre-dip17 kind (dip16's json_kind / bin_kind); the lanes take the async send
    let json = [SendKind::Helius, SendKind::Shyft, SendKind::Rpc, SendKind::Nozomi, SendKind::ZeroSlot, SendKind::Falcon, SendKind::Everstake, SendKind::JupiterTx,
        SendKind::HarmonicBundle];
    let bin = [SendKind::Haan, SendKind::Bolt, SendKind::Iris, SendKind::Lunar, SendKind::NodeOne, SendKind::BlockRazor, SendKind::Landx, SendKind::Glaive];
    let other = [SendKind::JitoBundle, SendKind::JitoTx, SendKind::Rpcfast, SendKind::Tpu, SendKind::SpeedLanding, SendKind::FlashBlock, SendKind::NextBlock,
        SendKind::Bloxroute, SendKind::Soyas, SendKind::Solami];
    for k in json { assert!(fastfire::json_kind(k) && !fastfire::bin_kind(k), "{k:?}"); }
    for k in bin { assert!(fastfire::bin_kind(k) && !fastfire::json_kind(k), "{k:?}"); }
    for k in other { assert!(!fastfire::bin_kind(k) && !fastfire::json_kind(k), "{k:?}"); }
    // only the two new kinds are QUIC lanes, and only they take the lane keys
    for k in json.iter().chain(&bin).chain(&other) { assert_eq!(k.is_quic_lane(), matches!(k, SendKind::Soyas | SendKind::Solami), "{k:?}"); }
}

/// the repo's dip probe configs (the shapes the run scripts use) parse as dip16 read them, pass the dip17 check, and serialize
/// their [[send]] entries with no dip17 key (meta / run records unchanged)
#[test]
fn dip17_dip16_configs_unchanged() {
    for f in ["ops/fix2/final2_landing.toml", "ops/lat/lat_landing.toml", "ops/lat/final_landing.toml"] {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(f);
        let probe: Probe = toml::from_str(&std::fs::read_to_string(&p).unwrap()).unwrap_or_else(|e| panic!("{f}: {e}"));
        assert!(!probe.sends.is_empty(), "{f}");
        for s in &probe.sends {
            s.quic_check().unwrap_or_else(|e| panic!("{f} {}: {e:#}", s.name));
            assert!(!s.kind.is_quic_lane());
            let j = serde_json::to_value(s).unwrap();
            for k in ["sni", "alpn", "identity_env", "keepalive_ms", "idle_ms"] { assert!(j.get(k).is_none(), "{f} {}: {k} serialized", s.name); }
        }
    }
}

fn send_of(toml_text: &str) -> config::SendPath { toml::from_str(toml_text).unwrap() }

/// the side-file entries for FRA and AMS parse (as Probe's [[send]]), with the kind's defaults; the minimum tips and the tip lists
#[test]
fn dip17_lane_entries_parse() {
    let side = r#"
[[send]]
name         = "soyas-fra"
kind         = "soyas"
url          = "quic://fra.landing.soyas.xyz:9000"
tip_lamports = 1000000
max_per_sec  = 10
enabled      = false
[[send]]
name         = "solami-fra"
kind         = "solami"
url          = "quic://fra.beam.solami.dev:11000"
tip_lamports = 100000
max_per_sec  = 10
enabled      = false
"#;
    #[derive(serde::Deserialize)]
    struct Side { send: Vec<config::SendPath> }
    let s: Side = toml::from_str(side).unwrap();
    let (soy, sol) = (&s.send[0], &s.send[1]);
    let (l, env) = soy.quic_settings().unwrap();
    assert_eq!((l.host.as_str(), l.port, l.sni.as_str(), l.alpn.as_str(), l.keepalive_ms, l.idle_ms, env.as_str()),
        ("fra.landing.soyas.xyz", 9000, "soyas-landing", "solana-tpu", 25_000, 30_000, "SOYAS_KEYPAIR"));
    let (l, env) = sol.quic_settings().unwrap();
    assert_eq!((l.host.as_str(), l.port, l.sni.as_str(), env.as_str()), ("fra.beam.solami.dev", 11000, "solami-beam", "SOLAMI_KEYPAIR"));
    assert_eq!((SendKind::Soyas.min_tip(), SendKind::Solami.min_tip()), (1_000_000, 100_000));
    let (st, lt) = (send::known_tip_accounts(SendKind::Soyas), send::known_tip_accounts(SendKind::Solami));
    assert_eq!((st.len(), lt.len()), (10, 10));
    assert!(st.iter().all(|a| a.starts_with("soyas")) && lt.iter().all(|a| a.ends_with("beam")));
    // the tips are named in recordings (chain studies): the code's own names now
    let names = send::code_tip_names();
    assert!(st.iter().all(|a| names.get(&pk(a)).map(String::as_str) == Some("soyas")) && lt.iter().all(|a| names.get(&pk(a)).map(String::as_str) == Some("solami")));
    // overrides; refusals: a non-quic url, no port, keep-alive at / over idle, a token_env, the lane keys on another kind
    let e = |t: &str| format!("{:#}", send_of(t).quic_check().unwrap_err());
    let o = send_of("name = \"x\"\nkind = \"soyas\"\nurl = \"quic://ams.landing.soyas.xyz:9000\"\nsni = \"s\"\nalpn = \"a\"\nidentity_env = \"K\"\nkeepalive_ms = 5000\nidle_ms = 20000\n");
    assert_eq!(o.quic_settings().unwrap(), (arbx::send::quic_lane::LaneCfg { host: "ams.landing.soyas.xyz".into(), port: 9000, sni: "s".into(), alpn: "a".into(),
        keepalive_ms: 5_000, idle_ms: 20_000 }, "K".to_string()));
    assert!(e("name = \"x\"\nkind = \"soyas\"\nurl = \"https://fra.landing.soyas.xyz\"\n").contains("quic://"));
    assert!(e("name = \"x\"\nkind = \"solami\"\nurl = \"quic://fra.beam.solami.dev\"\n").contains("port"));
    assert!(e("name = \"x\"\nkind = \"soyas\"\nurl = \"quic://h:1\"\nkeepalive_ms = 30000\n").contains("below idle_ms"));
    assert!(e("name = \"x\"\nkind = \"soyas\"\nurl = \"quic://h:1\"\ntoken_env = \"T\"\n").contains("identity_env"));
    assert!(e("name = \"x\"\nkind = \"helius\"\nurl = \"https://h\"\nsni = \"s\"\n").contains("for QUIC lanes"));
    // a copy must pay the lane's tip: at the minimum to one of its accounts (else refused before it leaves)
    let key = SigningKey::from_bytes(&[5; 32]);
    let user: Pk = key.verifying_key().to_bytes();
    for (k, accts, min) in [(SendKind::Soyas, st, 1_000_000u64), (SendKind::Solami, lt, 100_000)] {
        let tips: Vec<Pk> = accts.iter().map(|a| pk(a)).collect();
        for (t, ok) in [(min, true), (min - 1, false)] {
            let ixs = vec![build::transfer_ix(user, tips[3], t), build::transfer_ix(user, pk("11111111111111111111111111111112"), 5)];
            let raw = build::sign(&build::compile_v0(user, &ixs, [9u8; 32], &[], &[]).unwrap(), &key);
            assert_eq!(send::verify_copy(&raw, k, &tips, "lane").is_ok(), ok, "{k:?} {t}");
        }
    }
}

/// a lane path built while nothing listens: Paths::new keeps it (lenient, as snipe_engine builds them), the keypair must not be
/// the payer's, probe / ack_probe never write to it (junk mode writes nothing to a lane), a send fails fast (one reconnect)
#[tokio::test(flavor = "multi_thread")]
async fn dip17_lane_path_without_a_listener() {
    let port = std::net::UdpSocket::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let lane_key = SigningKey::from_bytes(&[31; 32]);
    let mut kp = [31u8; 32].to_vec();
    kp.extend_from_slice(&lane_key.verifying_key().to_bytes());
    std::env::set_var("ARB_TEST_DIP17_KP", bs58::encode(&kp).into_string());
    let c = send_of(&format!("name = \"soyas-test\"\nkind = \"soyas\"\nurl = \"quic://127.0.0.1:{port}\"\ntip_lamports = 1000000\nidentity_env = \"ARB_TEST_DIP17_KP\"\n"));
    // the payer's keypair as the lane key: refused
    let payer: Pk = lane_key.verifying_key().to_bytes();
    let r = send::Paths::new(std::slice::from_ref(&c), send::PathsOpts { queue_ms: 0, payer: Some(payer) }, arbx::rec::Rec::off(), false).await;
    assert!(r.map(|_| ()).unwrap_err().to_string().contains("payer"));
    let (paths, notes) = send::Paths::new(std::slice::from_ref(&c), send::PathsOpts { queue_ms: 0, payer: Some([1; 32]) }, arbx::rec::Rec::off(), true).await.unwrap();
    assert_eq!((paths.list.len(), notes.len()), (1, 0), "{notes:?}");
    let p = &paths.list[0];
    assert!(p.quic.is_some() && p.describe().starts_with("Soyas 127.0.0.1"));
    assert!(p.probe().await.contains("skipped"));
    let (_, answered, msg) = p.ack_probe().await;
    assert!(!answered && msg.contains("skipped"));
    assert_eq!(p.quic.as_ref().unwrap().sent.load(std::sync::atomic::Ordering::Relaxed), 0, "nothing written");
    let t = Instant::now();
    let tips: Vec<Pk> = send::known_tip_accounts(SendKind::Soyas).iter().map(|a| pk(a)).collect();
    let key = SigningKey::from_bytes(&[6; 32]);
    let user: Pk = key.verifying_key().to_bytes();
    let raw = build::sign(&build::compile_v0(user, &[build::transfer_ix(user, tips[0], 1_000_000)], [9u8; 32], &[], &[]).unwrap(), &key);
    let e = p.send(&raw, send::Prio::default(), None).await.unwrap_err();
    assert!(!e.answered && t.elapsed() < Duration::from_secs(1), "{e} {:?}", t.elapsed());
    // a key that is not set: the path is left out (lenient) with the reason, the value never printed
    let c2 = send_of(&format!("name = \"solami-test\"\nkind = \"solami\"\nurl = \"quic://127.0.0.1:{port}\"\ntip_lamports = 100000\nidentity_env = \"ARB_TEST_DIP17_NONE\"\n"));
    let (paths, notes) = send::Paths::new(&[c2], send::PathsOpts::default(), arbx::rec::Rec::off(), true).await.unwrap();
    assert!(paths.list.is_empty() && notes[0].contains("ARB_TEST_DIP17_NONE"), "{notes:?}");
}
