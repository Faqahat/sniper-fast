//! Parser check against REAL mainnet pump.fun transactions (3 legacy + 3 v0 with lookup tables) fetched as wire bytes via
//! getTransaction(base64); expected values come from the RPC's own JSON decode of the same txs (tests/make_fixtures.py).
use base64::Engine;
use shreder_rec::txparse::{decode_pubkey, parse_tx, pump_summary, PUMP_PROGRAM};

#[test]
fn real_mainnet_txs_parse_like_the_rpc() {
    let txt = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/real_txs.json")).unwrap();
    let fx: serde_json::Value = serde_json::from_str(&txt).unwrap();
    let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
    let (mut n_legacy, mut n_v0) = (0, 0);
    for t in fx.as_array().unwrap() {
        let bytes = base64::engine::general_purpose::STANDARD.decode(t["b64"].as_str().unwrap()).unwrap();
        let p = parse_tx(&bytes).expect("parse");
        assert_eq!(p.consumed, bytes.len(), "whole tx consumed");
        let sig = bs58::encode(p.signatures[0]).into_string();
        assert_eq!(sig, t["sig"].as_str().unwrap());
        assert_eq!(p.version as i64, t["version"].as_i64().unwrap());
        if p.version < 0 { n_legacy += 1 } else { n_v0 += 1 }
        let hdr: Vec<u8> = t["header"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as u8).collect();
        assert_eq!(p.header.to_vec(), hdr);
        let keys: Vec<String> = p.keys.iter().map(|k| bs58::encode(k).into_string()).collect();
        let exp_keys: Vec<String> = t["static_keys"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
        assert_eq!(keys, exp_keys);
        assert_eq!(p.n_lookups as u64, t["n_lookups"].as_u64().unwrap());
        let ixs = t["instructions"].as_array().unwrap();
        assert_eq!(p.instructions.len(), ixs.len());
        for (ix, e) in p.instructions.iter().zip(ixs) {
            assert_eq!(keys[ix.program_idx as usize], e["program"].as_str().unwrap());
            let acc: Vec<u8> = e["accounts"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap() as u8).collect();
            assert_eq!(ix.accounts.to_vec(), acc);
            assert_eq!(ix.data.to_vec(), bs58::decode(e["data_b58"].as_str().unwrap()).into_vec().unwrap());
        }
        let s = pump_summary(&p, &pump, None);
        let n_pump_top = ixs.iter().filter(|e| e["program"].as_str().unwrap() == PUMP_PROGRAM).count();
        assert_eq!(s.len(), n_pump_top);
        for x in &s {
            eprintln!("{} v={} kind={} mint={:?} a1={} a2={}", &sig[..8], p.version, x.kind, x.mint.map(|m| bs58::encode(m).into_string()), x.a1, x.a2);
        }
    }
    assert!(n_legacy >= 2 && n_v0 >= 2, "need both legacy and v0 fixtures");
}
