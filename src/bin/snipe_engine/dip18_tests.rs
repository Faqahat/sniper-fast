// ===================================================================================================================
// dip18 tests (10-25 PKT): the Falcon native UDP lane (kind falcon-udp; docs.corvus-labs.io/falcon/udp, binary frame:
// bytes 0..16 = the API key's raw 16-byte UUID, bytes 16..N = the raw signed tx, 1..1,232 bytes, no reply). Nothing changes
// without a [[send]] entry of that kind:
//  * golden: every tx shape is still dip15's bytes (DIP15_GOLDEN); the FAST kind map of every older kind is dip17's; the
//    repo's dip probe configs parse and check as before
//  * the key prefix from a fake UUID; the datagram = prefix || tx bytes on a local UDP listener (nothing sent anywhere else);
//    the 1,232-byte limit; tips; a LandX UDP path still writes its 12-byte key and 2 datagrams per copy
// ===================================================================================================================
use super::*;
use arbx::config::SendKind;

/// a made-up key (never a real one): its 16 raw bytes, in order
const FAKE_UUID: &str = "8f1e2d3c-4b5a-6978-8695-a4b3c2d1e0ff";
const FAKE_KEY16: [u8; 16] = [0x8f, 0x1e, 0x2d, 0x3c, 0x4b, 0x5a, 0x69, 0x78, 0x86, 0x95, 0xa4, 0xb3, 0xc2, 0xd1, 0xe0, 0xff];

#[test]
fn dip18_golden_no_falcon_udp_equals_dip17() {
    let (d, n) = super::dip16_tests::golden_digest();
    assert_eq!(d, super::dip16_tests::DIP15_GOLDEN, "the tx bytes must be dip15's / dip16's / dip17's ({n} shapes)");
    let json = [SendKind::Helius, SendKind::Shyft, SendKind::Rpc, SendKind::Nozomi, SendKind::ZeroSlot, SendKind::Falcon, SendKind::Everstake, SendKind::JupiterTx,
        SendKind::HarmonicBundle];
    let bin = [SendKind::Haan, SendKind::Bolt, SendKind::Iris, SendKind::Lunar, SendKind::NodeOne, SendKind::BlockRazor, SendKind::Landx, SendKind::Glaive];
    let other = [SendKind::JitoBundle, SendKind::JitoTx, SendKind::Rpcfast, SendKind::Tpu, SendKind::SpeedLanding, SendKind::FlashBlock, SendKind::NextBlock,
        SendKind::Bloxroute, SendKind::Soyas, SendKind::Solami, SendKind::FalconUdp];
    for k in json { assert!(fastfire::json_kind(k) && !fastfire::bin_kind(k), "{k:?}"); }
    for k in bin { assert!(fastfire::bin_kind(k) && !fastfire::json_kind(k), "{k:?}"); }
    // falcon-udp is never an HTTP form: its fast path is the UDP write (Kind::Udp), else the async send
    for k in other { assert!(!fastfire::bin_kind(k) && !fastfire::json_kind(k), "{k:?}"); }
    for k in json.iter().chain(&bin).chain(&other) { assert_eq!(k.is_quic_lane(), matches!(k, SendKind::Soyas | SendKind::Solami), "{k:?}"); }
    // the HTTP falcon kind is untouched (json, JSON-RPC sendTransaction); the minimums of the older kinds as dip17
    assert_eq!((SendKind::Falcon.min_tip(), SendKind::Landx.min_tip(), SendKind::FalconUdp.min_tip()), (1_000_000, 1_000_000, 1_000_000));
    // the repo's dip probe configs: no falcon-udp, the dip18 check passes
    for f in ["ops/fix2/final2_landing.toml", "ops/lat/lat_landing.toml", "ops/lat/final_landing.toml"] {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(f);
        let probe: Probe = toml::from_str(&std::fs::read_to_string(&p).unwrap()).unwrap_or_else(|e| panic!("{f}: {e}"));
        for s in &probe.sends {
            assert_ne!(s.kind, SendKind::FalconUdp, "{f}");
            s.falcon_udp_check().unwrap_or_else(|e| panic!("{f} {}: {e:#}", s.name));
        }
    }
}

/// the prefix: the UUID hex-decoded without dashes, in order (big-endian as written); upper case and the bare 32 hex digits
/// read the same; anything else is refused without echoing the value
#[test]
fn dip18_falcon_key_prefix() {
    assert_eq!(send::falcon_udp_key(FAKE_UUID).unwrap(), FAKE_KEY16);
    assert_eq!(send::falcon_udp_key(&FAKE_UUID.to_uppercase()).unwrap(), FAKE_KEY16);
    assert_eq!(send::falcon_udp_key(&format!("  {FAKE_UUID}\n")).unwrap(), FAKE_KEY16);
    assert_eq!(send::falcon_udp_key(&FAKE_UUID.replace('-', "")).unwrap(), FAKE_KEY16);
    assert_eq!(send::falcon_udp_key("00000000-0000-0000-0000-000000000001").unwrap(), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
    for bad in ["8f1e2d3c4b5a-6978-8695-a4b3c2d1e0ff-", "8f1e2d3c-4b5a-6978-8695-a4b3c2d1e0fg", "8f1e2d3c-4b5a-6978-8695", "", "zz", "8f1e2d3c_4b5a_6978_8695_a4b3c2d1e0ff"] {
        let e = format!("{:#}", send::falcon_udp_key(bad).unwrap_err());
        assert!(e.contains("not a UUID"), "{bad:?}: {e}");
        if bad.len() > 2 { assert!(!e.contains(bad), "the value must never be printed: {e}"); }
    }
    // the datagram: prefix || tx, nothing else
    let mut buf = vec![7u8; 3];
    send::udp_frame_into(&FAKE_KEY16, &[1, 2, 3], &mut buf);
    assert_eq!(buf, [&FAKE_KEY16[..], &[1, 2, 3]].concat());
    assert_eq!(send::FALCON_UDP_MAX_TX, 1_232);
}

/// the FRA / AMS side-file entries parse (as Probe's [[send]]) and pass the check; tips = Falcon's 10, min 0.001 SOL
#[test]
fn dip18_falcon_udp_entries_parse() {
    let side = r#"
[[send]]
name            = "falcon-udp-fra"
kind            = "falcon-udp"
url             = "udp://fra.falcon.wtf:9000"
token_env       = "FALCON_KEY"
no_tls_endpoint = "Falcon native UDP (docs.corvus-labs.io/falcon/udp): UDP 9000, no TLS form; the 16-byte key prefixes each datagram"
tip_lamports    = 1000000
max_per_sec     = 5
enabled         = false
[[send]]
name            = "falcon-udp-ams"
kind            = "falcon-udp"
url             = "udp://ams.falcon.wtf:9000"
token_env       = "FALCON_KEY"
no_tls_endpoint = "Falcon native UDP (docs.corvus-labs.io/falcon/udp): UDP 9000, no TLS form; the 16-byte key prefixes each datagram"
tip_lamports    = 1000000
max_per_sec     = 5
enabled         = false
"#;
    #[derive(serde::Deserialize)]
    struct Side { send: Vec<config::SendPath> }
    let s: Side = toml::from_str(side).unwrap();
    for (x, host) in s.send.iter().zip(["fra", "ams"]) {
        assert_eq!((x.kind, x.url.as_str(), x.tip_lamports, x.max_per_sec), (SendKind::FalconUdp, format!("udp://{host}.falcon.wtf:9000").as_str(), 1_000_000, Some(5)));
        x.quic_check().unwrap();
        x.falcon_udp_check().unwrap();
        assert!(config::cleartext_check(x).unwrap().is_some(), "the recorded no-TLS exception");
    }
    let tips = send::known_tip_accounts(SendKind::FalconUdp);
    assert_eq!(tips, send::known_tip_accounts(SendKind::Falcon));
    assert!(tips.len() == 10 && tips.iter().all(|a| a.starts_with("Fa1con1")));
    let names = send::code_tip_names();
    assert!(tips.iter().all(|a| names.get(&pk(a)).map(String::as_str) == Some("falcon")), "named falcon in recordings, as before");
    // a copy must pay at least 0.001 SOL to one of them (else refused before it leaves)
    let key = SigningKey::from_bytes(&[5; 32]);
    let user: Pk = key.verifying_key().to_bytes();
    let tpk: Vec<Pk> = tips.iter().map(|a| pk(a)).collect();
    for (t, ok) in [(1_000_000u64, true), (999_999, false)] {
        let raw = build::sign(&build::compile_v0(user, &[build::transfer_ix(user, tpk[4], t)], [9u8; 32], &[], &[]).unwrap(), &key);
        assert_eq!(send::verify_copy(&raw, SendKind::FalconUdp, &tpk, "falcon-udp").is_ok(), ok, "{t}");
    }
}

fn send_of(toml_text: &str) -> config::SendPath { toml::from_str(toml_text).unwrap() }

/// read every datagram that arrives within `ms`
fn drain(l: &std::net::UdpSocket, ms: u64) -> Vec<Vec<u8>> {
    l.set_read_timeout(Some(Duration::from_millis(ms))).unwrap();
    let mut out = Vec::new();
    let mut b = [0u8; 2048];
    while let Ok(n) = l.recv(&mut b) { out.push(b[..n].to_vec()); }
    out
}

/// a falcon-udp path to a LOCAL listener (127.0.0.1; nothing goes to Falcon or the chain): every datagram is the 16 raw key
/// bytes then the signed tx, one per copy (FALCON_UDP_COPIES unset), from the async send and the FAST write alike; a tx over
/// 1,232 bytes or one that does not pay the tip is never written; a bad key leaves the path out without printing it; a
/// LandX UDP path still writes its 12-byte key, 2 datagrams per copy
#[tokio::test(flavor = "multi_thread")]
async fn dip18_falcon_udp_datagram_layout() {
    let l = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
    let port = l.local_addr().unwrap().port();
    std::env::set_var("ARB_TEST_DIP18_FALCON", FAKE_UUID);
    let c = send_of(&format!("name = \"falcon-udp-test\"\nkind = \"falcon-udp\"\nurl = \"udp://127.0.0.1:{port}\"\ntoken_env = \"ARB_TEST_DIP18_FALCON\"\n\
        tip_lamports = 1000000\nmax_per_sec = 5\nno_tls_endpoint = \"test listener\"\n"));
    let (paths, notes) = send::Paths::new(std::slice::from_ref(&c), send::PathsOpts { queue_ms: 0, payer: Some([1; 32]) }, arbx::rec::Rec::off(), true).await.unwrap();
    // the one note: the recorded no-TLS exception (the env var's name, never its value)
    assert!(paths.list.len() == 1 && notes.len() == 1 && notes[0].contains("allowed, the provider has no TLS endpoint") && !notes[0].contains(FAKE_UUID), "{notes:?}");
    let p = &paths.list[0];
    assert!(p.describe().starts_with("FalconUdp 127.0.0.1"), "{}", p.describe());
    assert!(p.fast_udp_ok() && p.fast_ping().is_none());
    assert_eq!(p.udp_copies(), 1, "one datagram per tx copy (FALCON_UDP_COPIES unset)");
    assert!(drain(&l, 100).is_empty(), "nothing written at start (no keep-alive)");

    let key = SigningKey::from_bytes(&[6; 32]);
    let user: Pk = key.verifying_key().to_bytes();
    let tips: Vec<Pk> = send::known_tip_accounts(SendKind::FalconUdp).iter().map(|a| pk(a)).collect();
    let raw = build::sign(&build::compile_v0(user, &[build::transfer_ix(user, tips[0], 1_000_000)], [9u8; 32], &[], &[]).unwrap(), &key);
    // the async send
    let r = p.send(&raw, send::Prio::default(), None).await.unwrap();
    assert_eq!((r.status, r.reply.as_str()), (None, "udp sent x1"));
    let got = drain(&l, 300);
    assert_eq!(got.len(), 1);
    assert_eq!(&got[0][..16], &FAKE_KEY16[..], "bytes 0..16 = the raw UUID");
    assert_eq!(&got[0][16..], &raw[..], "bytes 16..N = the signed tx");
    assert_eq!(got[0].len(), 16 + raw.len());
    // the FAST write (the hot thread's): the same datagram
    let mut buf = Vec::new();
    assert!(matches!(p.fast_udp(&raw, &mut buf, 1), Some(Ok(()))));
    assert_eq!(drain(&l, 300), vec![[&FAKE_KEY16[..], &raw[..]].concat()]);
    // the size limit: 1,232 goes (a 1,248-byte datagram, the largest), 1,233 never leaves
    let max = vec![0xabu8; 1_232];
    assert!(matches!(p.fast_udp(&max, &mut buf, 1), Some(Ok(()))));
    let got = drain(&l, 300);
    assert_eq!((got.len(), got[0].len()), (1, 1_248));
    let over = p.fast_udp(&vec![0u8; 1_233], &mut buf, 1).unwrap().unwrap_err();
    assert_eq!(over.kind(), std::io::ErrorKind::InvalidInput);
    assert!(drain(&l, 200).is_empty(), "an oversized tx is never written");
    // a copy that does not pay Falcon's minimum is refused before it leaves
    let low = build::sign(&build::compile_v0(user, &[build::transfer_ix(user, tips[0], 999_999)], [9u8; 32], &[], &[]).unwrap(), &key);
    let e = p.send(&low, send::Prio::default(), None).await.unwrap_err();
    assert_eq!(e.code, Some("bad_tx"));
    assert!(drain(&l, 200).is_empty());

    // a key that is not a UUID: the path is left out (lenient) with the reason; the value never printed
    std::env::set_var("ARB_TEST_DIP18_FALCON_BAD", "not-a-real-key-value-1234567890");
    let c2 = send_of(&format!("name = \"falcon-udp-bad\"\nkind = \"falcon-udp\"\nurl = \"udp://127.0.0.1:{port}\"\ntoken_env = \"ARB_TEST_DIP18_FALCON_BAD\"\n\
        tip_lamports = 1000000\nno_tls_endpoint = \"test listener\"\n"));
    let (paths2, notes) = send::Paths::new(&[c2], send::PathsOpts::default(), arbx::rec::Rec::off(), true).await.unwrap();
    assert!(paths2.list.is_empty() && notes.iter().any(|n| n.contains("not a UUID")), "{notes:?}");
    assert!(notes.iter().all(|n| !n.contains("not-a-real-key-value")), "the key's value must never be printed: {notes:?}");
    // the key in clear text without the recorded exception: refused
    let c3 = send_of(&format!("name = \"falcon-udp-nonote\"\nkind = \"falcon-udp\"\nurl = \"udp://127.0.0.1:{port}\"\ntoken_env = \"ARB_TEST_DIP18_FALCON\"\ntip_lamports = 1000000\n"));
    let e = send::Paths::new(&[c3], send::PathsOpts::default(), arbx::rec::Rec::off(), true).await.map(|_| ()).unwrap_err().to_string();
    assert!(e.contains("plain udp://") && !e.contains(FAKE_UUID), "{e}");

    // LandX UDP unchanged: the 12-byte key, LANDX_UDP_COPIES (default 2) datagrams per copy
    if std::env::var("LANDX_UDP_COPIES").is_err() {
        std::env::set_var("ARB_TEST_DIP18_LANDX", "abcdefghijkl");
        let lx = send_of(&format!("name = \"landx-test\"\nkind = \"landx\"\nurl = \"udp://127.0.0.1:{port}\"\ntoken_env = \"ARB_TEST_DIP18_LANDX\"\n\
            tip_lamports = 1000000\nno_tls_endpoint = \"test listener\"\n"));
        let (pl, notes) = send::Paths::new(&[lx], send::PathsOpts { queue_ms: 0, payer: Some([1; 32]) }, arbx::rec::Rec::off(), true).await.unwrap();
        assert!(pl.list.len() == 1 && notes.iter().all(|n| n.contains("allowed")), "{notes:?}");
        let ltips: Vec<Pk> = send::known_tip_accounts(SendKind::Landx).iter().map(|a| pk(a)).collect();
        let lraw = build::sign(&build::compile_v0(user, &[build::transfer_ix(user, ltips[0], 1_000_000)], [9u8; 32], &[], &[]).unwrap(), &key);
        assert_eq!(pl.list[0].udp_copies(), 2);
        assert_eq!(pl.list[0].send(&lraw, send::Prio::default(), None).await.unwrap().reply, "udp sent x2");
        let want = [&b"abcdefghijkl"[..], &lraw[..]].concat();
        assert_eq!(drain(&l, 300), vec![want.clone(), want]);
    }
}
