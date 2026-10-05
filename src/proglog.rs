//! The route program's logs and error codes, in one place (PLAN WP-05 item 10, F11): what an error code means in
//! words ([`meaning`], moved from exec.rs), what each leg delivered ([`delivered_from_logs`], moved from build.rs), and
//! the program's events ([`events`]: `NXV2LEG` before each leg, `NXV2OUT` after it). WP-08 extends only this file.
//!
//! nexus-arb-v2 logs with `sol_log_data`, so each record is a `Program data: <base64> ...` line:
//! - `NXV2LEG` + leg index (8 bytes), right before the leg runs: a venue failure aborts inside the CPI with the venue's
//!   own code, and the last marker names the leg;
//! - `NXV2OUT` + leg index + delivered u64 LE (16 bytes), right after the leg delivered (program/nexus-arb-v2 `logic`).
use crate::build;
use serde_json::Value;

/// what a nexus-v2 or venue error code means, in words
pub fn meaning(code: Option<u32>, err: &Option<Value>) -> &'static str {
    match (code, err) {
        (_, None) => "ok",
        (Some(build::ERR_PROFIT), _) => "profit check: every leg ran, the round trip did not pay",
        (Some(0x4e58_0001), _) => "nexus: bad instruction data",
        (Some(0x4e58_0003), _) => "nexus: a leg program is not allowlisted",
        (Some(0x4e58_0004), _) => "nexus: an output or quote account is not a token account",
        (Some(0x4e58_0005), _) => "nexus: payer guard",
        (Some(0x4e58_0006), _) => "nexus: token guard",
        (Some(0x4e58_0007), _) => "nexus: a leg named a foreign signer",
        // arbx-exec only (program/arbx-exec REVIEW.md #8): its v2 path can return 0x4e580009 where nexus-arb-v2 gave
        // ERR_PROFIT or PrivilegeEscalation; the others come from its v3 layout
        (Some(build::arbx_v3::ERR_UNSUPPORTED), _) => "arbx-exec: a reserved v3 feature flag is set",
        (Some(build::arbx_v3::ERR_BAD_ACCOUNTS), _) => "arbx-exec: account structure (last leg not into the quote, output = input, NATIVE_OUT slot, read-only authority, or a quote/output not owned by the authority)",
        (Some(build::arbx_v3::ERR_TIP_ACCOUNT), _) => "arbx-exec: CPI tip account or System program slot wrong",
        (Some(build::arbx_v3::ERR_TIP_FUNDS), _) => "arbx-exec: the CPI tip would leave the authority below rent exemption",
        (Some(build::arbx_v3::ERR_QUOTE_NOT_WSOL), _) => "arbx-exec: COUNT_LAMPORTS or CPI_TIP needs a wSOL quote account",
        (Some(c), _) if (0x4e58_0100..0x4e58_0108).contains(&c) => "nexus: a leg delivered nothing",
        (Some(3005), _) => "anchor: not enough accounts (bin/tick arrays)",
        (Some(1), _) => "token: insufficient funds",
        (Some(_), _) => "a venue's own error (see code)",
        (None, Some(_)) => "not a program error (see err)",
    }
}

/// the 7-byte markers (program/nexus-arb-v2 `LEG_MARKER`, `DELIVERED_MARKER`)
pub const LEG_MARKER: &[u8; 7] = b"NXV2LEG";
pub const DELIVERED_MARKER: &[u8; 7] = b"NXV2OUT";

/// One decoded program event (outcomes.jsonl `prog_events`: `{kind, leg, amount, code}`)
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub struct ProgEvent {
    /// `leg` (a leg is about to run), `out` (a leg delivered `amount`)
    pub kind: &'static str,
    pub leg: u8,
    pub amount: Option<u64>,
    /// set by later decoders (WP-08) for failure events; null here
    pub code: Option<String>,
}

/// every `Program data:` record's decoded bytes, in log order
fn data_records(logs: &[String]) -> Vec<Vec<u8>> {
    use base64::Engine as _;
    let mut out = Vec::new();
    for l in logs {
        let Some(rest) = l.strip_prefix("Program data: ") else { continue };
        for part in rest.split_whitespace() {
            if let Ok(b) = base64::engine::general_purpose::STANDARD.decode(part) { out.push(b); }
        }
    }
    out
}

/// What `NXV2OUT` logs say each leg delivered: (leg index, amount). Logged as "Program data: <base64>" of
/// `NXV2OUT` + leg u8 + u64 LE (16 bytes).
pub fn delivered_from_logs(logs: &[String]) -> Vec<(u8, u64)> {
    data_records(logs).into_iter().filter(|b| b.len() == 16 && &b[..7] == DELIVERED_MARKER).map(|b| (b[7], u64::from_le_bytes(b[8..16].try_into().unwrap()))).collect()
}

/// The route program's events in log order: `leg` for each `NXV2LEG` marker (8 bytes), `out` for each `NXV2OUT` record
/// (16 bytes). Other `Program data:` records (a venue's own events) are left out
pub fn events(logs: &[String]) -> Vec<ProgEvent> {
    data_records(logs).into_iter().filter_map(|b| match b.len() {
        8 if &b[..7] == LEG_MARKER => Some(ProgEvent { kind: "leg", leg: b[7], amount: None, code: None }),
        16 if &b[..7] == DELIVERED_MARKER => Some(ProgEvent { kind: "out", leg: b[7], amount: Some(u64::from_le_bytes(b[8..16].try_into().unwrap())), code: None }),
        _ => None,
    }).collect()
}

/// the last leg whose `NXV2LEG` marker was logged (a venue's failure aborts inside that leg's CPI)
pub fn failing_leg(logs: &[String]) -> Option<u8> { events(logs).iter().rev().find(|e| e.kind == "leg").map(|e| e.leg) }

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine as _;

    fn data(b: &[u8]) -> String { format!("Program data: {}", base64::engine::general_purpose::STANDARD.encode(b)) }

    /// arbx-exec REVIEW.md #8: every arbx-exec code has its own meaning, none falls through to "a venue's own error"
    #[test]
    fn meaning_knows_the_arbx_exec_codes() {
        let e = Some(serde_json::json!("x"));
        for c in 0x4e58_0001u32..=0x4e58_000c {
            assert_ne!(meaning(Some(c), &e), "a venue's own error (see code)", "{c:#x}");
        }
        assert_eq!(meaning(Some(0x4e58_0009), &e).split(':').next(), Some("arbx-exec"));
        assert_eq!(meaning(Some(0x4e58_0107), &e), "nexus: a leg delivered nothing");
        assert_eq!(meaning(None, &None), "ok");
    }

    /// moved from build.rs unchanged: only the 16-byte NXV2OUT records count
    #[test]
    fn delivered_reads_the_out_records() {
        let mut ev = b"NXV2OUT".to_vec(); ev.push(1); ev.extend(123u64.to_le_bytes());
        let logs = vec!["Program log: x".to_string(), data(&ev), data(b"NXV2LEG\x01")];
        assert_eq!(delivered_from_logs(&logs), vec![(1, 123)]);
    }

    /// PLAN WP-05 item 10: the route program's events as the program logs them (program/nexus-arb-v2 `leg_marker`,
    /// `delivered_log`): the marker before each leg, the delivered amount after it; other records are left out
    #[test]
    fn events_decode_the_markers_in_order() {
        let out = |i: u8, a: u64| { let mut m = b"NXV2OUT".to_vec(); m.push(i); m.extend(a.to_le_bytes()); m };
        let logs = vec![
            "Program 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg invoke [1]".to_string(),
            data(b"NXV2LEG\x00"), "Program log: Instruction: Swap".into(), data(&out(0, 1_000)),
            data(b"NXV2LEG\x01"), data(&[9u8; 16]), data(&out(1, 1_000_200)),
            // two records on one line (sol_log_data with two fields)
            format!("Program data: {} {}", base64::engine::general_purpose::STANDARD.encode(b"NXV2LEG\x02"), base64::engine::general_purpose::STANDARD.encode(out(2, 7))),
        ];
        let ev = events(&logs);
        let kinds: Vec<(&str, u8, Option<u64>)> = ev.iter().map(|e| (e.kind, e.leg, e.amount)).collect();
        assert_eq!(kinds, vec![("leg", 0, None), ("out", 0, Some(1_000)), ("leg", 1, None), ("out", 1, Some(1_000_200)), ("leg", 2, None), ("out", 2, Some(7))]);
        assert_eq!(failing_leg(&logs), Some(2));
        assert_eq!(failing_leg(&logs[..3]), Some(0));
        assert!(events(&["Program data: !!notbase64".to_string()]).is_empty());
    }
}
