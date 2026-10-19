//! Send paths, one per `[[send]]` entry (ported from arbed's landers, src/providers/sender/*). Each takes signed
//! transaction bytes and delivers them its own way:
//!   jito-bundle  Jito searcher gRPC sendBundle, one-transaction bundle (jito.rs). A losing bundle costs nothing: the
//!                block engine drops a bundle whose transaction would fail, and its result stream says so
//!   jito-tx      Jito JSON-RPC sendTransaction (`x-jito-auth` UUID)
//!   helius       Helius Sender JSON-RPC sendTransaction (`?swqos_only=true`: the 5,000-lamport tier)
//!   shyft        Shyft staked RPC sendTransaction (SWQoS), no tip
//!   rpcfast      RPC Fast Beam JSON-RPC sendTransaction, tip to a Beam Astralane account
//!   haan         Haan Sender: raw bytes, Bearer key + x-jito-auth, plain-text signature reply, no tip
//!   bolt / iris / lunar  raw bytes (Raiden Bolt, Astralane Iris /irisb, Hello Moon Lunar Lander /send-bin)
//! PLAN WP-05: live sends are one-transaction Jito bundles (bundle-only); the other kinds stay compiled for `arbx
//! senders` checks and a future direct experiment. Tips are paid only when the trade succeeds: the tip transfer comes
//! after the on-chain profit check. Before a copy leaves, `Path::check` makes sure it really pays this path's tip to one
//! of this path's accounts (a top-level System transfer), so a builder bug can't burn a send. The jito-bundle path's
//! rate budget is the send queue (`budget.rs`: bands, crowding, EV, `[send_policy] queue_ms`); its auth token is
//! renewed in the background (`Jito::keep_token`) and only read on the send path; its keep-alive round trip is the
//! block engine's RTT (`leaders::note_be_rtt`: attempts carry it). The Jito gate is gone (WP-05).
//! Records (one JSON object per line, ns CLOCK_REALTIME): every copy in copies.jsonl (sent or not, answered or not),
//! every keep-alive in keepalive.jsonl, every bundle result in bundles.jsonl. Errors never carry a URL (keys live in some).
//! PLAN-ADDENDUM I-10: no secret travels in clear text, in the URL or in a header (review WP-05 #5): a path whose URL
//! expands into plain `http://` (or `udp://`) while it carries a `${...}` secret, a `token_env` or a `jito_auth_env` is
//! refused unless the provider has no TLS endpoint (`no_tls_endpoint`), and no provider key may be the payer's keypair
//! (`check_key_material`).
pub mod budget;
pub mod jito;
pub mod tpu;

pub use budget::{Drop, Granted, Prio, TokenBucket};

use crate::config::{SendKind, SendPath};
use crate::feeds::clock::now_ns;
use crate::tx::Pk;
use anyhow::{bail, Context, Result};
use base64::Engine as _;
use budget::Budget;
use reqwest::header::{HeaderMap, HeaderName, HeaderValue, CONTENT_TYPE};
use serde_json::{json, Value};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

/// keep-alive interval (arbed warms every lander every 20 s; Lunar wants one under 60 s, Helius when idle over 5 s)
/// a send still unanswered after this is reported as failed (the trade is long gone)
const SEND_TIMEOUT: Duration = Duration::from_secs(5);
const SYSTEM_PROGRAM: Pk = [0u8; 32];

/// The sender catalogue (`data/sender-tip-accounts.json`, compiled in): every service's tip accounts, the ones WP-08
/// added each with its provider source (`tip_account_sources`). Recordings name tips with it; sends use only
/// [`known_tip_accounts`]
pub const TIP_CATALOGUE: &str = include_str!("../../data/sender-tip-accounts.json");

/// every known sender tip account -> the sender's name (recording: whose tip a rival's transfer is: rivals.jsonl `tips`,
/// exec.jsonl `transfers`): the code's lists first ([`code_tip_names`]), then the catalogue ([`TIP_CATALOGUE`]) for every
/// account they do not name (WP-08, plan addendum: Glaive, Soyas, AllenHark, Solami and the bloXroute and SVS legacy
/// accounts, which cmp2's rivals.jsonl recorded unnamed)
pub fn tip_owner_names() -> rustc_hash::FxHashMap<crate::tx::Pk, String> {
    let mut m = code_tip_names();
    add_tip_catalogue(&mut m, TIP_CATALOGUE);
    m
}

/// Adds the accounts of a catalogue (the `data/sender-tip-accounts.json` layout: `{service: {"sender"?, "tip_accounts":
/// [..]}}`) that `m` does not name yet, each named by its service's `sender`, else by the service's key
pub fn add_tip_catalogue(m: &mut rustc_hash::FxHashMap<crate::tx::Pk, String>, json: &str) {
    let v: Value = serde_json::from_str(json).unwrap_or(Value::Null);
    for (key, s) in v.as_object().into_iter().flatten() {
        let name = s["sender"].as_str().unwrap_or(key);
        for a in s["tip_accounts"].as_array().into_iter().flatten().filter_map(Value::as_str) {
            if let Some(pk) = bs58::decode(a).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) { m.entry(pk).or_insert_with(|| name.to_string()); }
        }
    }
}

/// the code's sender tip accounts -> the sender's name: [`known_tip_accounts`] of every send kind, then
/// [`OTHER_TIP_ACCOUNTS`]
pub fn code_tip_names() -> rustc_hash::FxHashMap<crate::tx::Pk, String> {
    use SendKind::*;
    let mut m = rustc_hash::FxHashMap::default();
    for (k, name) in [(JitoTx, "jito"), (Helius, "helius"), (Rpcfast, "rpcfast"), (Bolt, "bolt"), (Iris, "astralane"), (Lunar, "lunar"),
        (Nozomi, "nozomi"), (ZeroSlot, "0slot"), (NodeOne, "nodeone"), (Falcon, "falcon"), (Everstake, "everstake"), (BlockRazor, "blockrazor"),
        (FlashBlock, "flashblock"), (NextBlock, "nextblock"), (Bloxroute, "bloxroute"), (JupiterTx, "jupiter"), (Landx, "landx"), (SpeedLanding, "speedlanding")] {
        for a in known_tip_accounts(k) {
            if let Some(pk) = bs58::decode(a).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) { m.entry(pk).or_insert_with(|| name.to_string()); }
        }
    }
    for (a, name) in OTHER_TIP_ACCOUNTS {
        if let Some(pk) = bs58::decode(a).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) { m.entry(pk).or_insert_with(|| name.to_string()); }
    }
    m
}

/// Published tip accounts of sending services we don't send through (sender catalogue, data/sender-tip-accounts.json,
/// 2026-10-03): only to name rivals' tips in the recordings. A trailing "?" marks an unverified list.
pub static OTHER_TIP_ACCOUNTS: &[(&str, &str)] = &[
    ("ste11JV3MLMM7x7EJUM2sXcJC1H7F4jBLnP9a9PG8PH", "stellium"),
    ("ste11MWPjXCRfQryCshzi86SGhuXjF4Lv6xMXD2AoSt", "stellium"),
    ("ste11p5x8tJ53H1NbNQsRBg1YNRd4GcVpxtDw8PBpmb", "stellium"),
    ("ste11p7e2KLYou5bwtt35H7BM6uMdo4pvioGjJXKFcN", "stellium"),
    ("ste11TMV68LMi1BguM4RQujtbNCZvf1sjsASpqgAvSX", "stellium"),
    ("ste111J5Lq54fgZtmCYZTM8emu2UbeDeN9qwhs69hqA", "stellium"),
    ("ste113yP33KzDSqBFUErdbZJ3PGRojHToTPSthUkNTq", "stellium"),
    ("ste11681PDwyYiQUUtFNoujLY3tUqThLMY4yKJrxPtj", "stellium"),
    ("ste11eZvF5bebo6EVyGMJHV6LtPtx7e6TzNZtxPfXGy", "stellium"),
    ("svsMoWJBwLcs8JgfN8VaF111tAc199KpYeTKRwxRtip", "svs_lightspeed"),
    ("BPZrtYhdoAhiHWV5EgGLoV7bZFbMamBZurGDq4DmST8v", "p2p_syncro_sender"),
    ("7D5pdbkV75Sr73M1YFNZwXMed6DenwkdfbJwVWrX6drQ", "p2p_syncro_sender"),
    ("ELpn2NryEW4B3psG36eSjF45YcGMQpGGuu9J2AgAccbV", "p2p_syncro_sender"),
    ("FnckAPC9PitnRpGZM2M4WLwb3w9odRLJ7EDRZDngjvd6", "p2p_syncro_sender"),
    ("3ZnDTgvVfwzqwWoqAUmDkgVtXvXqjmeb5t9zxD5pMbmv", "p2p_syncro_sender"),
    ("3SLDFcdCzMbcFNguZhzmV4zqEAUvcPoKY13akpE4Tq1p", "p2p_syncro_sender"),
    ("48tT6LJqrsoFrLpzZSHkjGdGTWtsJ1PvjgWZjh8qF1RK", "p2p_syncro_sender"),
    ("7GM9fpVMHHcrK4cgzfVdzJvjiy1bSyfwSYzhxvgbfVLg", "p2p_syncro_sender"),
    ("CBd8GE3ffMJKf3iCCcNNBEifMxH1WpgtTzRnXPxxbjGE", "p2p_syncro_sender"),
    ("rfBP8KJ6KMqvBhmqaV7EoNHVexXQdn1sX4CJ9aLv5w2", "rpcfast_beam"),
    ("rfBkmha9yK5QS7h562Pn6Bfw6cPjsrgVqgcnnXBoXj7", "rpcfast_beam"),
    ("rfBxDPw4XK2WKBinv7Vbr68inD964H7HTMLMWshe3jT", "rpcfast_beam"),
    ("Eag4Jt2M7tiCV3daC7jCwM9CZZa7C8tZPGn5kURT7qUE", "rpcfast_beam"),
    ("3ZMMzsRp3mCftMgyX9tCeg9kRwFU8siYTvamTxHCdHoC", "rpcfast_beam"),
    ("tJgbQbGhNtUE2h6pSa7LV2NbUuftTq5wrxQkXbLK4mu", "rpcfast_beam"),
    ("AoJAVKY58jmTa3gT9bx29bdeYpKdE4beoXFrjMJk7A5q", "rpcfast_beam"),
    ("9Uq39ZFGW55zGrafsa1D35uKgchNcQEKsWoCq2CjwUW9", "rpcfast_beam"),
    ("F2onQMdej9rLW8wdUF46dodDDRakYynjm1VT9hDysFRK", "rpcfast_beam"),
    ("CCm7t7d8Q2zpqJRDAcKzCbMbuWuJxj71N6o3A3MHeE8J", "rpcfast_beam"),
    ("BhawUhJ9G6W7D3Q4JGjkbXjs1v2GyyTANFodWmCsPJyu", "rpcfast_beam"),
    ("rfCCxFtXuwjjnP9cXAaEgvCzLkrzXwAiWQadJ4uNKmf", "rpcfast_beam"),
    ("rfCTcFU5p63roQ7S8sTwpQ93NHfGxf5ThSsbH1CjQbf", "rpcfast_beam"),
    ("rfC18Jx6rqwhvwjWpkZnX8q7vE45vzxBXtic1jLr32R", "rpcfast_beam"),
    ("rfCmxTvz2LeEzVmFZHvcfLvz4EaT6Rbkkff98RufbdZ", "rpcfast_beam"),
    ("rfCaRhB66prehCypC53XeSPJ83cTjzwa8cHMeNpenQ8", "rpcfast_beam"),
    ("CHJPZWYoHMkTFtDq75Jmy6FLFcHD5kJhGziBgiNSfmLE", "quicknode_fastlane?"),
    ("Jfxpfrmghh7MWRPB8XMVF8QgFqGVEhKWVp24ZpvPAHC", "quicknode_fastlane?"),
    ("EQHMoomkaneVz99A4gdUfnPaNYedAcBzfnVMRe82rEMW", "quicknode_fastlane?"),
    ("FgBDNKreUbZqYJHQFN8199b9zGCpkKqBCPyDjpCgzhx", "quicknode_fastlane?"),
    ("42mWt6QXn167LgSxKM6rtHjEjMztFF6u5Vnb1nA6Vvu6", "quicknode_fastlane?"),
    ("22GKaRXieiGnrpGdBWpCRoW4a3m7zjSUaUxrDbnhpphk", "quicknode_fastlane?"),
    ("F9XUxbNcqGQAfzjT2E9LDcHtw5LWQzaeqoQuCkXXPhvU", "quicknode_fastlane?"),
    ("AkoLzkJuthPh9ZGR4CddsFfzVunYtmtteUPjZJnvMH5c", "quicknode_fastlane?"),
    ("BjqjPHFmwr19YFmkH8CMNJFbj1wzX9k9ngr4am2nQEdq", "rakurai"),
    ("9CNKnAqJgLA4pL6KByzhhdY4mKoQP5wcPdhJgnvvi5Ve", "rakurai"),
    ("5wy4C2VMFhHE4i8PWKNS1K4SV275zjNwhLwfKBwajrro", "rakurai"),
    ("AgMdA97pk2i2Ry4YQ4iVPNrRiFhcH3x3ARUCiQGt3vJG", "rakurai"),
    ("4Qf8JFV5vmpADXNouoJriQ9KiniT5DENrz9JM2mKGH9m", "rakurai"),
    ("AuFAFzbzE9dzMajy4RNdyJZBTskeiuJQqT2wd9xoGSRD", "rakurai"),
    ("8aLaHz8595MAvgxKoBJEyZmDfqQp8CorezFGYnC7CPjy", "rakurai"),
    ("H6hyJo6rpBmwHbvVuWCEHExJ2bE4rcn1hTPeiBtypus4", "rakurai"),
];

/// Each provider's own tip accounts, copied verbatim from its docs (a wrong address silently burns lamports). A path's
/// configured `tip_accounts` must come from this list; empty = all of them.
pub fn known_tip_accounts(kind: SendKind) -> &'static [&'static str] {
    match kind {
        // speedlanding.trade/docs.html (2026-10-03)
        SendKind::SpeedLanding => &[
            "SpEEdz8S1KorkMZqjMUxfxrmWwofmp6ReNP2Nx6CUmq",
            "SpeeDy3GJM4wcrQmk1itRFWgidvxX4rwjTLMv78wwjE",
            "SPeEdva37vW8vRtqgYjprQs1g3965icfVN5Rt7SMAyh",
            "speEdrSEpox5GUfHWcBc7tQjRuSfUin2yvB7qoYvvJh",
            "SPeEDmkHkN3A2roSZf6aZyEMsmrGqTHKqwP51y2Y4rV",
            "SpeedLdTJXh2RKpXEaP8JCxkWoUVXhtdPQ1EnxBJMxc",
            "SpEediGKLbbXndSYTzwmz6Z3NDgHQLDcTDEvGFkSMH9",
            "speede8xCcUq2Tiv1efXeTuE3k9TDNq8TnGKaKSc6J4",
        ],
        // landx-1.gitbook.io/landx-docs/tip-addresses (2026-10-03)
        SendKind::Landx => &[
            "LandX1EMgYtrfi4jVJ7ryby4mDpZcef6sVH9b9U1cog",
            "LandX2gHE7y6RejuvoLJK4hJiKkrAwcrJJ34u19Gmo1",
            "LandX3uK1cSUF7hbefKo3oL1j4FhvhxitiMRKut99Z6",
            "LandX4wXzvDyWfq1XXn4StRjwPjzqb7je2kqDGLoT9L",
            "LandX5T4jfRASrcn76owxHM4q9bduNGj24ev4Ufc5fP",
            "LandX6RsjjnfaxfYAFTZX1TW9Cgfe9HFStj9nRDd5SK",
            "LandX7LsdzXDAbbyBjAq5FxLTnGQaU3LojGQMLZCvkt",
            "LandX8Gv3UkhjmgKdSEg4F7yG7Z2tiqhNDYDtxazydN",
            "LandX9fhNN5S7fuBgekKBYeYvK1Sy9hbGvDmHsBGYFh",
            "LandXXxDXaSS8MjrqG9nri51htrfM6V4R3zXDVCeV8R",
        ],
        // developers.jup.ag/docs/transaction/submit (2026-07-29): randomize per transaction
        SendKind::JupiterTx => &[
            "GGztQqQ6pCPaJQnNpXBgELr5cs3WwDakRbh1iEMzjgSJ",
            "2MFoS3MPtvyQ4Wh4M9pdfPjz6UhVoNbFbGJAskCPCj3h",
            "BQ72nSv9f3PRyRKCBnHLVrerrv37CYTHm5h3s9VSGQDV",
            "6U91aKa8pmMxkJwBCfPTmUEfZi6dHe7DcFq2ALvB2tbB",
            "4xDsmeTWPNjgSVSS1VTfzFq3iHZhp77ffPkAmkZkdu71",
            "CapuXNQoDviLvU1PxFiizLgPNQCxrsag1uMeyk6zLVps",
            "9nnLbotNTcUhvbrsA6Mdkx45Sm82G35zo28AqUvjExn8",
            "6LXutJvKUw8Q5ue2gCgKHQdAN4suWW8awzFVC6XCguFx",
            "HFqp6ErWHY6Uzhj8rFyjYuDya2mXUpYEk8VW75K9PSiY",
            "DSN3j1ykL3obAVNv7ZX49VsFCPe4LqzxHnmtLiPwY6xg",
            "69yhtoJR4JYPPABZcSNkzuqbaFbwHsCkja1sP1Q2aVT5",
            "HU23r7UoZbqTUuh3vA7emAGztFtqwTeVips789vqxxBw",
            "3LoAYHuSd7Gh8d7RTFnhvYtiTiefdZ5ByamU42vkzd76",
            "3CgvbiM3op4vjrrjH2zcrQUwsqh5veNVRjFCB9N6sRoD",
            "GP8StUXNYSZjPikyRsvkTbvRV1GBxMErb59cpeCJnDf1",
            "7iWnBRRhBCiNXXPhqiGzvvBkKrvFSWqqmxRyu9VyYBxE",
        ],
        // docs.jito.wtf getTipAccounts (jito-bundle is also checked against the block engine's live list at start)
        SendKind::JitoBundle | SendKind::JitoTx => &[
            "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
            "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY", "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
            "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh", "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
            "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL", "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
        ],
        // helius.dev/docs/sending-transactions/sender
        SendKind::Helius => &[
            "4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE", "D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ",
            "9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta", "5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn",
            "2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD", "2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ",
            "wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF", "3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT",
            "4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey", "4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or",
        ],
        // docs.rpcfast.com "RPC Fast Beam": the tip account picks Beam's provider; Astralane's minimum is the lowest
        SendKind::Rpcfast => &["ASdXviZw2kbViFuAgZF26RPZL1HdybUoWdcveG2nfU8D", "Ax2JBnTPUpBFWe75z3YtgueWUfvZPZ6ZFXiMWJMUnjbo"],
        // raiden-4.gitbook.io bolt-low-latency/tip-addresses
        SendKind::Bolt => &[
            "t1TcSg9biJsz4NjKjhopK8QZzPS4KzBgFSszu5QTGgF", "t2XFAFBaUkCzxJwEbLWFX9PKFjfBCp2tSyFtx5z4RZM",
            "t3QLYyXH4vZYbEifLqjD581t5dPVhq9LABxWceySzL2", "t46SqGmwStEffUMp1fr2xmv5uyR85TB9annJuLKLf83",
            "t55hdzzftxWkYy3J8t32C9RRcZDuMZ4LDuBmbTzJFkU", "t6UtTQLUGHJJrzxAb8PBBZdZKra8SWUqvTv9zPnxKNz",
            "t7qUQU35sLpPydh42BcPmtEfTWW8gBe4Ry3gjwVnokJ", "t8pPgarSK3TnuLbbHmoE1RCQdLxfxuPqNTyFjBKahok",
            "t96GGdw3MiaGR993XN8PSsRpKGXx56t5Wf6zcF1hBpY",
        ],
        // astralane.gitbook.io low-latency/endpoints-and-configs
        SendKind::Iris => &[
            "astrazznxsGUhWShqgNtAdfrzP2G83DzcWVJDxwV9bF", "astra4uejePWneqNaJKuFFA8oonqCE1sqF6b45kDMZm",
            "astra9xWY93QyfG6yM8zwsKsRodscjQ2uU2HKNL5prk", "astraRVUuTHjpwEVvNBeQEgwYx9w9CFyfxjYoobCZhL",
            "astraEJ2fEj8Xmy6KLG7B3VfbKfsHXhHrNdCQx7iGJK", "astraubkDw81n4LuutzSQ8uzHCv4BhPVhfvTcYv8SKC",
            "astraZW5GLFefxNPAatceHhYjfA1ciq9gvfEg2S47xk", "astrawVNP4xDBKT7rAdxrLYiTSTdqtUr63fSMduivXK",
            "AstrA1ejL4UeXC2SBP4cpeEmtcFPZVLxx3XGKXyCW6to", "AsTra79FET4aCKWspPqeSFvjJNyp96SvAnrmyAxqg5b7",
            "AstrABAu8CBTyuPXpV4eSCJ5fePEPnxN8NqBaPKQ9fHR", "AsTRADtvb6tTmrsqULQ9Wji9PigDMjhfEMza6zkynEvV",
            "AsTRAEoyMofR3vUPpf9k68Gsfb6ymTZttEtsAbv8Bk4d", "AStrAJv2RN2hKCHxwUMtqmSxgdcNZbihCwc1mCSnG83W",
            "Astran35aiQUF57XZsmkWMtNCtXGLzs8upfiqXxth2bz", "AStRAnpi6kFrKypragExgeRoJ1QnKH7pbSjLAKQVWUum",
            "ASTRaoF93eYt73TYvwtsv6fMWHWbGmMUZfVZPo3CRU9C",
        ],
        // docs.hellomoon.io/reference/lunar-lander
        SendKind::Lunar => &[
            "moon17L6BgxXRX5uHKudAmqVF96xia9h8ygcmG2sL3F", "moon26Sek222Md7ZydcAGxoKG832DK36CkLrS3PQY4c",
            "moon7fwyajcVstMoBnVy7UBcTx87SBtNoGGAaH2Cb8V", "moonBtH9HvLHjLqi9ivyrMVKgFUsSfrz9BwQ9khhn1u",
            "moonCJg8476LNFLptX1qrK8PdRsA1HD1R6XWyu9MB93", "moonF2sz7qwAtdETnrgxNbjonnhGGjd6r4W4UC9284s",
            "moonKfftMiGSak3cezvhEqvkPSzwrmQxQHXuspC96yj", "moonQBUKBpkifLcTd78bfxxt4PYLwmJ5admLW6cBBs8",
            "moonXwpKwoVkMegt5Bc776cSW793X1irL5hHV1vJ3JA", "moonZ6u9E2fgk6eWd82621eLPHt9zuJuYECXAYjMY1C",
        ],
        // the senders below: verbatim from each provider's docs, 2026-10-03 (consultant/data/sender-tip-accounts-2026-10-03.json)
        SendKind::Nozomi => &[
            "TEMPaMeCRFAS9EKF53Jd6KpHxgL47uWLcpFArU1Fanq", "noz3jAjPiHuBPqiSPkkugaJDkJscPuRhYnSpbi8UvC4",
            "noz3str9KXfpKknefHji8L1mPgimezaiUyCHYMDv1GE", "noz6uoYCDijhu1V7cutCpwxNiSovEwLdRHPwmgCGDNo",
            "noz9EPNcT7WH6Sou3sr3GGjHQYVkN3DNirpbvDkv9YJ", "nozc5yT15LazbLTFVZzoNZCwjh3yUtW86LoUyqsBu4L",
            "nozFrhfnNGoyqwVuwPAW4aaGqempx4PU6g6D9CJMv7Z", "nozievPk7HyK1Rqy1MPJwVQ7qQg2QoJGyP71oeDwbsu",
            "noznbgwYnBLDHu8wcQVCEw6kDrXkPdKkydGJGNXGvL7", "nozNVWs5N8mgzuD3qigrCG2UoKxZttxzZ85pvAQVrbP",
            "nozpEGbwx4BcGp6pvEdAh1JoC2CQGZdU6HbNP1v2p6P", "nozrhjhkCr3zXT3BiT4WCodYCUFeQvcdUkM7MqhKqge",
            "nozrwQtWhEdrA6W8dkbt9gnUaMs52PdAv5byipnadq3", "nozUacTVWub3cL4mJmGCYjKZTnE9RbdY5AP46iQgbPJ",
            "nozWCyTPppJjRuw2fpzDhhWbW355fzosWSzrrMYB1Qk", "nozWNju6dY353eMkMqURqwQEoM3SFgEKC6psLCSfUne",
            "nozxNBgWohjR75vdspfxR5H9ceC7XXH99xpxhVGt3Bb",
        ],
        SendKind::ZeroSlot => &[
            "6fQaVhYZA4w3MBSXjJ81Vf6W1EDYeUPXpgVQ6UQyU1Av", "4HiwLEP2Bzqj3hM2ENxJuzhcPCdsafwiet3oGkMkuQY4",
            "7toBU3inhmrARGngC7z6SjyP85HgGMmCTEwGNRAcYnEK", "8mR3wB1nh4D6J9RUCugxUpc6ya8w38LPxZ3ZjcBhgzws",
            "6SiVU5WEwqfFapRuYCndomztEwDjvS5xgtEof3PLEGm9", "TpdxgNJBWZRL8UXF5mrEsyWxDWx9HQexA9P1eTWQ42p",
            "D8f3WkQu6dCF33cZxuAsrKHrGsqGP2yvAHf8mX6RXnwf", "GQPFicsy3P3NXxB5piJohoxACqTvWE9fKpLgdsMduoHE",
            "Ey2JEr8hDkgN8qKJGrLf2yFjRhW7rab99HVxwi5rcvJE", "4iUgjMT8q2hNZnLuhpqZ1QtiV8deFPy2ajvvjEpKKgsS",
            "3Rz8uD83QsU8wKvZbgWAPvCNDU6Fy8TSZTMcPm3RB6zt", "DiTmWENJsHQdawVUUKnUXkconcpW4Jv52TnMWhkncF6t",
            "HRyRhQ86t3H4aAtgvHVpUJmw64BDrb61gRiKcdKUXs5c", "7y4whZmw388w1ggjToDLSBLv47drw5SUXcLk6jtmwixd",
            "J9BMEWFbCBEjtQ1fG5Lo9kouX1HfrKQxeUxetwXrifBw", "8U1JPQh3mVQ4F5jwRdFTBzvNRQaYFQppHQYoH38DJGSQ",
            "Eb2KpSC8uMt9GmzyAEm5Eb1AAAgTjRaXWFjKyFXHZxF3", "FCjUJZ1qozm1e8romw216qyfQMaaWKxWsuySnumVCCNe",
            "ENxTEjSQ1YabmUpXAdCgevnHQ9MHdLv8tzFiuiYJqa13", "6rYLG55Q9RpsPGvqdPNJs4z5WTxJVatMB8zV3WJhs5EK",
            "Cix2bHfqPcKcM233mzxbLk14kSggUUiz2A87fJtGivXr",
        ],
        SendKind::NodeOne => &[
            "node1PqAa3BWWzUnTHVbw8NJHC874zn9ngAkXjgWEej", "node1UzzTxAAeBTpfZkQPJXBAqixsbdth11ba1NXLBG",
            "node1Qm1bV4fwYnCurP8otJ9s5yrkPq7SPZ5uhj3Tsv", "node1PUber6SFmSQgvf2ECmXsHP5o3boRSGhvJyPMX1",
            "node1AyMbeqiVN6eoQzEAwCA6Pk826hrdqdAHR7cdJ3", "node1YtWCoTwwVYTFLfS19zquRQzYX332hs1HEuRBjC",
        ],
        SendKind::Falcon => &[
            "Fa1con11xLjPddfzRwRUB16sbFZggp2JeJkCeWREyR8X", "Fa1con11TM1RuAQzbQzYjTy4Ekfap9Lnc9fnEbQYEd6Q",
            "Fa1con113Bvi76nS5AzUiRDC2fqjfzkNMUNRLgQybMYt", "Fa1con1QGHJK232s8yZpzZZwqPexnAKcoyKj626LNsMv",
            "Fa1con1zUzb6qJVFz5tNkPq1Ahm8H1qKW7Q48252QbkQ", "Fa1con16d3MSwd3SAiwvr2LwgkpE7ot8zntbpuec8HAx",
            "Fa1con1i7mpa7Qc6epYJ6r4P9AbU77DFFz173r59Df1x", "Fa1con18nWn8TdAGL7JX8PertfMUGVSc899NawokJ4Bq",
            "Fa1con1GKusK2EqsfzrDzGPaYZSxQtFGzJiRMMU9Zm2g", "Fa1con1RDwVwM9VrJ53CwVefD3VU9c58EMpDawV7fLMi",
        ],
        SendKind::Everstake => &[
            "J4cL8c22KNLHwheuWxK1SCYBWASWPGhEi6xvcGyf6o3S", "EzuhsszPxRUHBwGPXtKoqCB58EiTJ1QiYA2XrhbUEFbr",
            "7wsUm2VDopGDFyXkyhmgUh9V15QkEvnyqbgUPcagLcw2", "Cy3WAM9NdjFG3kXCxXmD17WmtJMBKVpoBXabkSm88Xdt",
            "BEEya88mme6JJ4rgshBR23eiDHmygUii9opUHE3qxnqK", "Gq21dPAGVuuZucqBQeCkfbbqoEowL1t88igZekJ93CRu",
            "79HFWkNoPhotXuFYi1ksuK5hE7AUnKasafP6c71hS9sM", "Cp4pCm5JjDaZ4gXB8eSjNJvQ8eg7uK6awgjveofrSATz",
            "DMHQ51qK2wChtDEUED54cqzbSLMLGvTygQCv5uLTUmZP", "GDnz7cAA7hKEFmDyrk6mz3drybHWc3Gn14y9LCsvvtjE",
        ],
        SendKind::BlockRazor => &[
            "FjmZZrFvhnqqb9ThCuMVnENaM3JGVuGWNyCAxRJcFpg9", "6No2i3aawzHsjtThw81iq1EXPJN6rh8eSJCLaYZfKDTG",
            "A9cWowVAiHe9pJfKAj3TJiN9VpbzMUq6E4kEvf5mUT22", "Gywj98ophM7GmkDdaWs4isqZnDdFCW7B46TXmKfvyqSm",
            "68Pwb4jS7eZATjDfhmTXgRJjCiZmw1L7Huy4HNpnxJ3o", "4ABhJh5rZPjv63RBJBuyWzBK3g9gWMUQdTZP2kiW31V9",
            "B2M4NG5eyZp5SBQrSdtemzk5TqVuaWGQnowGaCBt8GyM", "5jA59cXMKQqZAVdtopv8q3yyw9SYfiE3vUCbt7p8MfVf",
            "5YktoWygr1Bp9wiS1xtMtUki1PeYuuzuCF98tqwYxf61", "295Avbam4qGShBYK7E9H5Ldew4B3WyJGmgmXfiWdeeyV",
            "EDi4rSy2LZgKJX74mbLTFk4mxoTgT6F7HxxzG2HBAFyK", "BnGKHAC386n4Qmv9xtpBVbRaUTKixjBe3oagkPFKtoy6",
            "Dd7K2Fp7AtoN8xCghKDRmyqr5U169t48Tw5fEd3wT9mq", "AP6qExwrbRgBAVaehg4b5xHENX815sMabtBzUzVB4v8S",
        ],
        SendKind::FlashBlock => &[
            "FLaShB3iXXTWE1vu9wQsChUKq3HFtpMAhb8kAh1pf1wi", "FLashhsorBmM9dLpuq6qATawcpqk1Y2aqaZfkd48iT3W",
            "FLaSHJNm5dWYzEgnHJWWJP5ccu128Mu61NJLxUf7mUXU", "FLaSHR4Vv7sttd6TyDF4yR1bJyAxRwWKbohDytEMu3wL",
            "FLASHRzANfcAKDuQ3RXv9hbkBy4WVEKDzoAgxJ56DiE4", "FLasHstqx11M8W56zrSEqkCyhMCCpr6ze6Mjdvqope5s",
            "FLAShWTjcweNT4NSotpjpxAkwxUr2we3eXQGhpTVzRwy", "FLasHXTqrbNvpWFB6grN47HGZfK6pze9HLNTgbukfPSk",
            "FLAshyAyBcKb39KPxSzXcepiS8iDYUhDGwJcJDPX4g2B", "FLAsHZTRcf3Dy1APaz6j74ebdMC6Xx4g6i9YxjyrDybR",
        ],
        SendKind::NextBlock => &[
            "NextbLoCkVtMGcV47JzewQdvBpLqT9TxQFozQkN98pE", "NexTbLoCkWykbLuB1NkjXgFWkX9oAtcoagQegygXXA2",
            "NeXTBLoCKs9F1y5PJS9CKrFNNLU1keHW71rfh7KgA1X", "NexTBLockJYZ7QD7p2byrUa6df8ndV2WSd8GkbWqfbb",
            "neXtBLock1LeC67jYd1QdAa32kbVeubsfPNTJC1V5At", "nEXTBLockYgngeRmRrjDV31mGSekVPqZoMGhQEZtPVG",
            "NEXTbLoCkB51HpLBLojQfpyVAMorm3zzKg7w9NFdqid", "nextBLoCkPMgmG8ZgJtABeScP35qLa2AMCNKntAP7Xc",
        ],
        SendKind::Bloxroute => &[
            "3UQUKjhMKaY2S6bjcQD6yHB7utcZt5bfarRCmctpRtUd", "FogxVNs6Mm2w9rnGL1vkARSwJxvLE8mujTv3LK8RnUhF",
            "bLx7MvxGaKdKL7mEbpk9tC79z6MnBSJoJkuaEAPu6Nd", "bLx7XBqSg3LUPVf1bRgCnkJmgVZR8QEgDJBPqcRLHvp",
            "bLx8KeZxinPwy6kkUgyzMLeqb2ARNsWjADG1dhSsVba", "bLxADBknoNj8WAGw2W6GBYeq848Xx6ajhaymV1YvrHm",
            "bLxAc88vRBwvcUQJEgcxNfBLvHPikY4csNsUmPeWea2", "bLxQ88oCiTsL8Xj4YWekKi1hjrgmbE3J3FFZ2xZHR3h",
            "bLxS7NoLuynNRJ4mCnEE2YbtwJFttYsEyp2ME7rp2yt", "bLxW6mCov7VEbrKc3S9tcBRcfSzRnLCbNp3Dfn3SJG5",
            "bLxXSGXs4mYPTC5okZXed1qzvjNwNJ48QJ82hT2V7w7", "bLxYi3vojbbB7hVzVDVTdBLVPhp7GJ3ZB3BwdK5sFXi",
            "bLxhLPgBXtUpX4b1bH3HatuMGMSKT9GnwtuCGiMSAqe", "bLxpY1mniuFW4PgkNA4JiNxoeKHFszryi6tNgyZAiAA",
            "bLxuETxd2tgWxBALNwPzAfHhsik4BzD3nrEBCiPNZQD", "bLxuL2gK5FW7xfahvwLrxLyW76vcCpNsKQY2CmnE6kV",
            "bLxv4Hnub7nDJWHs8s17o9bGU65Bnx6Yqp2fqtMgHmm",
        ],
        SendKind::Shyft | SendKind::Haan | SendKind::Tpu | SendKind::Rpc => &[],
    }
}

/// The first signature of a signed transaction, base58. v1 (SIMD-0385) puts the signatures at the end; legacy and v0
/// start with a compact-u16 count (one byte below 128) and then them.
pub fn first_signature(raw: &[u8]) -> Option<String> {
    if *raw.first()? == 0x81 {
        let n = *raw.get(1)? as usize;
        if n == 0 || raw.len() < 64 * n + 2 { return None; }
        let s = raw.len() - 64 * n;
        return Some(bs58::encode(&raw[s..s + 64]).into_string());
    }
    let n = raw[0];
    if n == 0 || n >= 0x80 || raw.len() < 65 { return None; }
    Some(bs58::encode(&raw[1..65]).into_string())
}

fn is_signature(s: &str) -> bool { bs58::decode(s).into_vec().is_ok_and(|v| v.len() == 64) }

fn short(s: &str) -> String { s.chars().take(200).collect() }

/// a URL's host ("" when it has none); never the URL itself, whose path or query may hold a key
pub fn host_of(url: &str) -> String { reqwest::Url::parse(url).ok().and_then(|u| u.host_str().map(String::from)).unwrap_or_default() }

/// An endpoint's reply: a JSON-RPC result, Bolt's / Iris's `{"signature"|"result": …}`, or Haan's plain signature.
fn parse_reply(name: &str, status: u16, body: &[u8]) -> Result<String> {
    let text = String::from_utf8_lossy(body);
    let text = text.trim();
    let ok = (200..300).contains(&status);
    if let Ok(v) = serde_json::from_str::<Value>(text) {
        if let Some(e) = v.get("error").filter(|e| !e.is_null()) {
            let m = match (e["code"].as_i64(), e["message"].as_str(), e.as_str()) { (Some(c), Some(m), _) => format!("{c} {m}"), (_, _, Some(s)) => s.to_string(), _ => e.to_string() };
            bail!("{name}: HTTP {status} {}", short(&m));
        }
        if v.get("success") == Some(&Value::Bool(false)) { bail!("{name}: HTTP {status} {}", short(text)); }
        for k in ["result", "signature"] {
            if let Some(s) = v.get(k).and_then(Value::as_str) { if ok && is_signature(s) { return Ok(s.to_string()); } }
        }
        bail!("{name}: HTTP {status}, no signature in reply: {}", short(text));
    }
    let t = text.trim_matches('"');
    if ok && is_signature(t) { return Ok(t.to_string()); }
    if status == 429 { bail!("{name}: HTTP 429, rate limited"); }
    bail!("{name}: HTTP {status} {}", short(text))
}

/// a transport error without its URL (keys live in some URLs, and errors go to the logs)
fn net(name: &str, e: reqwest::Error) -> anyhow::Error { anyhow::anyhow!("{name}: {}", e.without_url()) }

fn env_value(var: &str, what: &str) -> Result<String> {
    match std::env::var(var) {
        Ok(v) if !v.trim().is_empty() => Ok(v.trim().to_string()),
        _ => bail!("{what}: environment variable {var} is empty or missing (set it in .env)"),
    }
}

fn header(h: &mut HeaderMap, name: &'static str, value: String) -> Result<()> {
    h.insert(HeaderName::from_static(name), HeaderValue::from_str(&value).context("not a valid header value")?);
    Ok(())
}

/// How a path is kept warm (Tpu: its own loop keeps the next leaders' connections open)
enum Ping { Get(String), Health, Tips, None }

#[derive(Default)]
pub struct PathStats {
    pub sent: u64,
    pub ok: u64,
    pub refused: u64,
    /// not sent: over the path's rate
    pub limited: u64,
    /// of `limited`: copies ranked last for a crowded pool (WP-00, F6: `Prio` rank 2), the rest were not
    pub limited_crowded: u64,
    /// not sent: the copy did not pay this path's tip (or Helius's priority fee)
    pub bad_tx: u64,
    pub warm_errors: u64,
    send_us: Vec<u64>,
    warm_us: Vec<u64>,
}

/// What an endpoint answered for one copy: its HTTP status (None for gRPC), its reply (cut to 200 characters), the
/// signature it returned and, for a bundle, the bundle id; how long the copy waited in the rate queue
#[derive(Clone, Debug)]
pub struct Reply { pub sig: String, pub bundle: Option<String>, pub status: Option<u16>, pub reply: String, pub queue_wait_us: Option<u64> }

/// A signed copy for a path of `kind` whose tip accounts are `tips`: one signed transaction, nothing after it, that pays
/// at least the kind's minimum tip to one of `tips` with a top-level System transfer (a tip account behind a lookup
/// table does not count: Jito forbids it), and for Helius a compute-unit price. Returns its signature. The send path's
/// last check (`Path::check`), and the dry run's (no `Path`)
pub fn verify_copy(raw: &[u8], kind: SendKind, tips: &[Pk], name: &str) -> Result<String> {
    let sig = first_signature(raw).context("not a signed transaction")?;
    let min = kind.min_tip();
    if min == 0 && kind != SendKind::Helius { return Ok(sig); }
    let (tx, used) = crate::tx::parse_wire(raw).context("transaction does not parse")?;
    if used != raw.len() { bail!("{} stray bytes after the transaction", raw.len() - used); }
    if kind == SendKind::Helius && tx.cu_price_micro.is_none() { bail!("no compute-unit price (Helius Sender rejects it)"); }
    let paid = tip_paid(&tx, tips);
    if paid < min { bail!("pays {paid} lamports to {name}'s tip accounts; it needs at least {min}"); }
    Ok(sig)
}

/// lamports a parsed transaction pays to `tips` with top-level System transfers
pub fn tip_paid(tx: &crate::tx::Tx, tips: &[Pk]) -> u64 {
    tx.ixs.iter().filter_map(|ix| {
        if *tx.keys.get(ix.program as usize)? != SYSTEM_PROGRAM || ix.data.len() != 12 || ix.data[..4] != [2, 0, 0, 0] { return None; }
        let to = tx.keys.get(*ix.accounts.get(1)? as usize)?;
        tips.contains(to).then(|| u64::from_le_bytes(ix.data[4..12].try_into().unwrap()))
    }).sum()
}

/// A copy that was refused before or by the endpoint (status None: never reached it, or gRPC). `code`: why, when it never
/// left (`rate_queue_timeout`, `crowded_pool`: the rate queue; `bad_tx`: it did not pay this path; `jito_auth_stale`: no
/// valid cached token), None when the endpoint refused it or did not answer. `answered`: the endpoint answered (an HTTP
/// status, or a gRPC status that refuses the bundle: `jito::refused_code`), so the copy cannot land; false when it never
/// left or got no answer (a timeout, a transport error after it may have left: review WP-05 #7)
#[derive(Clone, Debug)]
pub struct Refusal { pub status: Option<u16>, pub msg: String, pub code: Option<&'static str>, pub answered: bool }
impl std::fmt::Display for Refusal { fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { f.write_str(&self.msg) } }
impl std::error::Error for Refusal {}
fn refuse(status: Option<u16>, msg: impl Into<String>) -> Refusal { Refusal { status, msg: msg.into(), code: None, answered: status.is_some() } }
fn refuse_code(code: &'static str, msg: impl Into<String>) -> Refusal { Refusal { status: None, msg: msg.into(), code: Some(code), answered: false } }
/// a gRPC endpoint's refusal (no HTTP status): it answered
fn refuse_answered(msg: impl Into<String>) -> Refusal { Refusal { status: None, msg: msg.into(), code: None, answered: true } }

/// What `Paths::new` needs beyond the paths: the bundle path's queue (`[send_policy] queue_ms`) and the payer, whose
/// keypair no provider key may be (I-10)
#[derive(Clone, Debug, Default)]
pub struct PathsOpts { pub queue_ms: u64, pub payer: Option<Pk> }

/// The public key of a secret if it is one: a base58 64-byte keypair (secret then public half: its seed's key), a
/// base58 32-byte seed, or a solana-keygen JSON byte array of either length
pub fn keypair_pubkey(s: &str) -> Option<Pk> {
    let t = s.trim();
    let bytes: Vec<u8> = if t.starts_with('[') { serde_json::from_str::<Vec<u8>>(t).ok()? } else { bs58::decode(t).into_vec().ok()? };
    let seed: [u8; 32] = match bytes.len() { 64 | 32 => bytes[..32].try_into().ok()?, _ => return None };
    Some(ed25519_dalek::SigningKey::from_bytes(&seed).verifying_key().to_bytes())
}

/// The secret values a path's config names that are set now: its URL's and keep-alive URL's `${...}` variables (and
/// every query value and path segment of the expanded URLs), `token_env`, `jito_auth_env`: (what, value)
fn secret_values(c: &SendPath) -> Vec<(String, String)> {
    let mut out = Vec::new();
    for (what, u) in [("url", Some(c.url.as_str())), ("ping_url", c.ping_url.as_deref())] {
        let Some(u) = u else { continue };
        for v in crate::config::env_vars(u) { if let Ok(x) = std::env::var(&v) { out.push((format!("{what} ${{{v}}}"), x.trim().to_string())); } }
        if let Some(x) = crate::config::expand(u).and_then(|e| reqwest::Url::parse(&e).ok()) {
            for (k, v) in x.query_pairs() { out.push((format!("{what} query {k}"), v.to_string())); }
            for seg in x.path_segments().into_iter().flatten() { out.push((format!("{what} path"), seg.to_string())); }
        }
    }
    for (what, v) in [("token_env", c.token_env.as_deref()), ("jito_auth_env", c.jito_auth_env.as_deref())] {
        if let Some(x) = v.and_then(|v| std::env::var(v).ok()) { out.push((what.to_string(), x.trim().to_string())); }
    }
    out
}

/// PLAN-ADDENDUM I-10: a provider key that is a keypair must be a dedicated one. Refused when any secret value of the
/// path (`secret_values`) or its jito auth keypair file is the payer's keypair. Returns how many values were checked.
/// The key material is never printed
pub fn check_key_material(c: &SendPath, payer: &Pk) -> Result<usize> {
    let mut n = 0;
    for (what, v) in secret_values(c) {
        n += 1;
        if keypair_pubkey(&v).is_some_and(|k| k == *payer) {
            bail!("send path {}: its {what} is the payer's keypair (PLAN-ADDENDUM I-10: a provider key that is a keypair must be a dedicated one)", c.name);
        }
    }
    if c.kind == SendKind::JitoBundle {
        let f = c.auth_keypair.as_deref().unwrap_or(jito::DEFAULT_AUTH_KEYPAIR);
        if let Ok(k) = jito::load_keypair(f) {
            n += 1;
            if k.verifying_key().to_bytes() == *payer { bail!("send path {}: its auth keypair is the payer's (the block engine key must never be the trading wallet)", c.name); }
        }
    }
    Ok(n)
}

pub struct Path {
    pub name: String,
    pub kind: SendKind,
    tips: Vec<Pk>,
    tip_lamports: u64,
    tip_share: Option<f64>,
    tip_max: u64,
    cursor: AtomicUsize,
    budget: Option<Budget>,
    url: String,
    /// the URL's host (copies.jsonl `endpoint`; never the URL: keys live in some)
    host: String,
    ping: Ping,
    headers: HeaderMap,
    preflight: bool,
    http: reqwest::Client,
    pub jito: Option<Arc<jito::Jito>>,
    pub tpu: Option<Arc<tpu::Tpu>>,
    /// LandX over UDP: the connected socket and the 12-byte key every packet starts with
    udp: Option<(Arc<tokio::net::UdpSocket>, Vec<u8>)>,
    pub stats: Mutex<PathStats>,
}

impl Path {
    async fn new(c: &SendPath, rec: &crate::rec::Rec, opts: &PathsOpts) -> Result<Path> {
        let what = format!("send path {}", c.name);
        let url = crate::config::expand(&c.url).with_context(|| format!("{what}: url {} names an environment variable that is empty or missing", c.url))?;
        // I-10 at run time too: a URL whose `${...}` expands into plain http:// (the whole URL from the environment), or a
        // plain-http URL that a header key goes to (review WP-05 #5)
        let secret = !crate::config::env_vars(&c.url).is_empty() || c.token_env.is_some() || c.jito_auth_env.is_some();
        if secret && crate::config::cleartext_scheme(&url) && c.no_tls_endpoint.is_none() {
            let scheme = url.trim_start().split("://").next().unwrap_or("").to_ascii_lowercase();
            bail!("{what}: its url expands into plain {scheme}:// (no TLS) and carries a secret (in the URL or a header): use the provider's https:// endpoint \
                (PLAN-ADDENDUM I-10), or set no_tls_endpoint");
        }
        let mut headers = HeaderMap::new();
        let token = c.token_env.as_deref().map(|v| env_value(v, &what)).transpose()?;
        // tpu-direct: token_env is the Bearer key of the RPC that answers the leader schedule (e.g. Haan)
        let tpu_bearer = if c.kind == SendKind::Tpu { token.clone() } else { None };
        match (c.kind, token.clone()) {
            (SendKind::Tpu, Some(_)) => {}
            (SendKind::JitoTx, Some(t)) => header(&mut headers, "x-jito-auth", t)?,
            (SendKind::Haan, Some(t)) => header(&mut headers, "authorization", format!("Bearer {t}"))?,
            (SendKind::Haan, None) => bail!("{what}: haan needs token_env (its API key, sent as a Bearer token)"),
            (SendKind::Bolt, Some(t)) => header(&mut headers, "api-x-token", t)?,
            (SendKind::Bolt, None) => bail!("{what}: bolt needs token_env (sent as api-x-token)"),
            (SendKind::NodeOne, Some(t)) => header(&mut headers, "api-key", t)?,
            (SendKind::FlashBlock | SendKind::NextBlock | SendKind::Bloxroute, Some(t)) => header(&mut headers, "authorization", t)?,
            (SendKind::JupiterTx, Some(t)) => header(&mut headers, "x-api-key", t)?,
            (SendKind::JupiterTx, None) => bail!("{what}: jupiter-tx needs token_env (its portal API key, sent as x-api-key)"),
            // LandX: over UDP the key starts every packet (token_env); over HTTP it is in the url path
            (SendKind::Landx, _) => {}
            (k @ (SendKind::NodeOne | SendKind::FlashBlock | SendKind::NextBlock | SendKind::Bloxroute), None) => bail!("{what}: {k:?} needs token_env (its API key)"),
            (_, None) => {}
            (k, Some(_)) => bail!("{what}: {k:?} takes its key in the URL (url = \"...${{NAME}}...\"), not token_env"),
        }
        if let Some(v) = &c.jito_auth_env {
            if c.kind != SendKind::Haan { bail!("{what}: jito_auth_env is for haan (jito-tx uses token_env)"); }
            header(&mut headers, "x-jito-auth", env_value(v, &what)?)?;
        }
        let base = || reqwest::Url::parse(&url).with_context(|| format!("{what}: bad url"));
        let ping = match (&c.ping_url, c.kind) {
            (Some(u), _) => {
                let x = crate::config::expand(u).with_context(|| format!("{what}: ping_url names a missing environment variable"))?;
                // the keep-alive carries the path's headers too (I-10)
                if (!crate::config::env_vars(u).is_empty() || !headers.is_empty()) && crate::config::cleartext_scheme(&x) && c.no_tls_endpoint.is_none() {
                    bail!("{what}: its ping_url is plain (no TLS) and carries a secret (in the URL or a header): use https:// (PLAN-ADDENDUM I-10), or set no_tls_endpoint");
                }
                Ping::Get(x)
            }
            (None, SendKind::JitoBundle) => Ping::Tips,
            (None, SendKind::Helius | SendKind::Lunar | SendKind::Bolt) => {
                // Helius: /fast -> /ping; Lunar /send-bin and Bolt /api/v1/sendRawTransaction: /ping at the host
                let b = base()?;
                let path = if c.kind == SendKind::Helius { b.path().strip_suffix("/fast").map(|p| format!("{p}/ping")).unwrap_or_else(|| "/ping".into()) } else { "/ping".into() };
                Ping::Get(b.join(&path)?.to_string())
            }
            (None, SendKind::Iris) => Ping::Get(base()?.join("/gethealth")?.to_string()),
            (None, SendKind::Nozomi | SendKind::NodeOne) => Ping::Get(base()?.join("/ping")?.to_string()),
            (None, SendKind::ZeroSlot | SendKind::BlockRazor) => Ping::Get(base()?.join("/health")?.to_string()),
            (None, SendKind::FlashBlock | SendKind::NextBlock | SendKind::Bloxroute) => Ping::Get(base()?.join("/")?.to_string()),
            (None, SendKind::Falcon | SendKind::Everstake) => Ping::Health,
            (None, SendKind::Haan) => Ping::Get(url.clone()),
            (None, SendKind::JitoTx | SendKind::Shyft | SendKind::Rpcfast | SendKind::Rpc | SendKind::JupiterTx) => Ping::Health,
            (None, SendKind::Tpu) => Ping::None,
            (None, SendKind::SpeedLanding) => Ping::Get(base()?.join("/ping")?.to_string()),
            (None, SendKind::Landx) => if url.starts_with("udp://") { Ping::None } else { Ping::Get(base()?.join("/ping")?.to_string()) },
        };
        let known = known_tip_accounts(c.kind);
        let names: Vec<&str> = if c.tip_accounts.is_empty() { known.to_vec() } else { c.tip_accounts.iter().map(String::as_str).collect() };
        let tips: Vec<Pk> = if c.tip_lamports > 0 { names.iter().map(|a| crate::tx::pk(a)).collect() } else { Vec::new() };
        // the bundle path's queue is the send policy's ([send_policy] queue_ms; PLAN WP-05 item 5)
        let queue_ms = if c.kind == SendKind::JitoBundle { opts.queue_ms } else { c.queue_ms };
        let budget = c.max_per_sec.map(|n| Budget::new(n, Duration::from_millis(queue_ms)));
        let http = reqwest::Client::builder().tcp_nodelay(true).pool_idle_timeout(Duration::from_secs(85)).pool_max_idle_per_host(4)
            .timeout(SEND_TIMEOUT).build()?;
        let jito = if c.kind == SendKind::JitoBundle {
            if !url.starts_with("https://") && !url.starts_with("http://") { bail!("{what}: the block engine url needs a scheme (https://...)"); }
            let key = jito::load_keypair(c.auth_keypair.as_deref().unwrap_or(jito::DEFAULT_AUTH_KEYPAIR))?;
            if opts.payer.is_some_and(|p| p == key.verifying_key().to_bytes()) { bail!("{what}: the auth keypair is the payer's (PLAN-ADDENDUM I-10)"); }
            let j = jito::Jito::connect(&url, key, rec.clone()).await.with_context(|| format!("{what}: connect"))?;
            j.token().await.with_context(|| format!("{what}: authenticate as {} (is the key whitelisted?)", j.pubkey()))?;
            let live = j.tip_accounts().await.with_context(|| format!("{what}: getTipAccounts"))?;
            for t in &tips {
                let b = crate::tx::b58(t);
                if !live.contains(&b) { bail!("{what}: tip account {b} is not one of the block engine's ({})", live.join(", ")); }
            }
            Some(j)
        } else { None };
        let tpu = if c.kind == SendKind::Tpu { Some(tpu::Tpu::new(url.clone(), tpu_bearer.clone()).await.with_context(|| format!("{what}: leader book"))?) } else { None };
        let udp = if c.kind == SendKind::Landx && url.starts_with("udp://") {
            let hostport = url.trim_start_matches("udp://").trim_end_matches('/').to_string();
            let key = token.clone().ok_or_else(|| anyhow::anyhow!("{what}: landx over UDP needs token_env (its 12-byte API key)"))?;
            if key.len() != 12 { bail!("{what}: the LandX API key must be 12 bytes (it is {})", key.len()); }
            let addr = tokio::net::lookup_host(hostport.as_str()).await.with_context(|| format!("{what}: resolve {hostport}"))?
                .next().with_context(|| format!("{what}: {hostport} has no address"))?;
            let sock = tokio::net::UdpSocket::bind("0.0.0.0:0").await.with_context(|| format!("{what}: udp bind"))?;
            sock.connect(addr).await.with_context(|| format!("{what}: udp connect {addr}"))?;
            Some((Arc::new(sock), key.into_bytes()))
        } else { None };
        let host = host_of(&url);
        Ok(Path { name: c.name.clone(), kind: c.kind, tips, tip_lamports: c.tip_lamports, tip_share: c.tip_share,
            tip_max: c.tip_max_lamports.unwrap_or(u64::MAX), cursor: AtomicUsize::new(0), budget, url, host, ping, headers,
            preflight: c.preflight, http, jito, tpu, udp, stats: Default::default() })
    }

    /// tests: a jito-bundle path on `jito` (e.g. `Jito::for_test` with an in-memory block engine), Jito's own tip
    /// accounts, `max_per_sec` and `queue_ms` for its rate queue
    #[cfg(test)]
    pub fn test_bundle(jito: Arc<jito::Jito>, max_per_sec: Option<u32>, queue_ms: u64) -> Path {
        Path { name: "jito-bundle".into(), kind: SendKind::JitoBundle, tips: known_tip_accounts(SendKind::JitoBundle).iter().map(|a| crate::tx::pk(a)).collect(),
            tip_lamports: 1_000, tip_share: Some(0.7), tip_max: 100_000, cursor: AtomicUsize::new(0),
            budget: max_per_sec.map(|n| Budget::new(n, Duration::from_millis(queue_ms))), url: "https://127.0.0.1:9".into(), host: "127.0.0.1".into(), ping: Ping::Tips,
            headers: HeaderMap::new(),
            preflight: false, http: reqwest::Client::new(), jito: Some(jito), tpu: None, udp: None, stats: Default::default() }
    }

    /// the endpoint's host (never the full URL: keys live in some); a jito-bundle path: its block engine (copies.jsonl
    /// `endpoint`, FT-006)
    pub fn endpoint(&self) -> String { self.host.clone() }

    /// kind and endpoint host (never the full URL: keys live in some)
    pub fn describe(&self) -> String {
        let host = self.endpoint();
        let rate = self.budget.as_ref().map(|b| format!(" max {}/s", b.per_sec())).unwrap_or_default();
        format!("{:?} {host}{rate}", self.kind)
    }

    /// true when a copy that loses costs nothing (a Jito bundle); never re-forward such a copy on a paid path
    pub fn free_miss(&self) -> bool { self.kind == SendKind::JitoBundle }

    /// The tip this path's copy must carry for a trade with `gross` predicted gross edge (lamports), and the account to
    /// pay it to (rotating); None = no tip. jito-bundle with `tip_share`: that share of the edge, within the floor and cap.
    pub fn tip(&self, gross: i64) -> Option<(Pk, u64)> {
        if self.tips.is_empty() { return None; }
        let lamports = match self.tip_share {
            Some(s) => ((gross.max(0) as f64 * s) as u64).clamp(self.tip_lamports, self.tip_max),
            None => self.tip_lamports,
        };
        Some((self.tips[self.cursor.fetch_add(1, Ordering::Relaxed) % self.tips.len()], lamports))
    }

    /// The copy must be one signed transaction that pays this path's minimum tip to one of its accounts with a top-level
    /// System transfer (a tip account behind a lookup table does not count: Jito forbids it), and for Helius a
    /// compute-unit price. Returns the transaction's signature.
    pub fn check(&self, raw: &[u8]) -> Result<String> { verify_copy(raw, self.kind, &self.tips, &self.name) }

    /// arbx-fast: the path's tip accounts (the executor picks a Helius Sender copy's tip account from them)
    pub fn tip_accounts(&self) -> &[Pk] { &self.tips }

    /// the rate queue's waiting sends and λ (status `exec.queue_now`, `lambda_now`)
    pub fn queue_now(&self) -> Option<(usize, Option<i64>)> { self.budget.as_ref().map(|b| (b.waiting(), b.lambda())) }

    /// Check, wait for the rate budget (the queue: bands, crowding, EV), deliver. Never retried here: a late copy is
    /// worthless. `attempt` joins the bundle's results to it. The reply carries the queue wait
    pub async fn send(&self, raw: &[u8], prio: Prio, attempt: Option<u64>) -> Result<Reply, Refusal> {
        let sig = match self.check(raw) {
            Ok(s) => s,
            Err(e) => { self.stats.lock().unwrap().bad_tx += 1; return Err(refuse_code("bad_tx", format!("{}: refused before sending: {e}", self.name))); }
        };
        let mut waited = None;
        if let Some(b) = &self.budget {
            match b.acquire(prio).await {
                Ok(g) => waited = Some(g.waited),
                Err(d) => {
                    let mut st = self.stats.lock().unwrap();
                    st.limited += 1;
                    if prio.crowded() { st.limited_crowded += 1; }
                    return Err(refuse_code(d.reason(), format!("{}: over its rate, not sent ({})", self.name, d.reason())));
                }
            }
        }
        let t = Instant::now();
        let mut r = self.deliver(raw, &sig, attempt).await;
        if let Ok(rep) = &mut r { rep.queue_wait_us = waited.map(|w| w.as_micros() as u64); }
        let mut s = self.stats.lock().unwrap();
        s.sent += 1;
        match &r { Ok(_) => { s.ok += 1; s.send_us.push(t.elapsed().as_micros() as u64); } Err(_) => s.refused += 1 }
        r
    }

    async fn deliver(&self, raw: &[u8], sig: &str, attempt: Option<u64>) -> Result<Reply, Refusal> {
        let name = &self.name;
        let net = |e: reqwest::Error| refuse(None, net(name, e).to_string());
        let rep = |sig: String, bundle: Option<String>, status: Option<u16>, reply: String| Reply { sig, bundle, status, reply, queue_wait_us: None };
        let answer = |status: u16, body: &[u8], bundle: Option<String>| -> Result<Reply, Refusal> {
            let reply = short(String::from_utf8_lossy(body).trim());
            match parse_reply(name, status, body) {
                Ok(got) => Ok(rep(got, bundle, Some(status), reply)),
                Err(e) => Err(refuse(Some(status), e.to_string())),
            }
        };
        // senders whose success reply carries no signature (or nests it): a 2xx without an error is an acceptance
        let lenient = |status: u16, body: &[u8]| -> Result<Reply, Refusal> {
            let text = short(String::from_utf8_lossy(body).trim());
            let v: Value = serde_json::from_slice(body).unwrap_or(Value::Null);
            if let Some(sg) = v["data"]["signatures"][0].as_str() { return Ok(rep(sg.to_string(), None, Some(status), text)); }
            match parse_reply(name, status, body) {
                Ok(got) => Ok(rep(got, None, Some(status), text)),
                Err(_) if (200..300).contains(&status) && v.get("error").map_or(true, |e| e.is_null()) && v.get("success") != Some(&Value::Bool(false)) =>
                    Ok(rep(sig.to_string(), None, Some(status), text)),
                Err(e) => Err(refuse(Some(status), e.to_string())),
            }
        };
        match self.kind {
            SendKind::JitoBundle => {
                let j = self.jito.as_ref().ok_or_else(|| refuse(None, "jito-bundle without a block engine client"))?;
                let id = j.send_bundle(&[raw], sig, attempt).await.map_err(|e| match e {
                    jito::BundleError::AuthStale => refuse_code("jito_auth_stale", format!("{name}: sendBundle: {e}")),
                    jito::BundleError::Refused(_) => refuse_answered(format!("{name}: sendBundle refused: {e}")),
                    jito::BundleError::Other(_) => refuse(None, format!("{name}: sendBundle: {e}")),
                })?;
                Ok(rep(sig.to_string(), Some(id.clone()), None, id))
            }
            SendKind::Landx => {
                if let Some((sock, key)) = &self.udp {
                    let mut p = Vec::with_capacity(key.len() + raw.len());
                    p.extend_from_slice(key);
                    p.extend_from_slice(raw);
                    sock.send(&p).await.map_err(|e| refuse(None, format!("{name}: udp: {e}")))?;
                    Ok(rep(sig.to_string(), None, None, "udp sent".into()))
                } else {
                    let resp = self.http.post(&self.url).headers(self.headers.clone()).header(CONTENT_TYPE, "application/octet-stream")
                        .body(raw.to_vec()).send().await.map_err(net)?;
                    let status = resp.status().as_u16();
                    lenient(status, &resp.bytes().await.map_err(net)?)
                }
            }
            SendKind::Tpu => {
                let t = self.tpu.as_ref().ok_or_else(|| refuse(None, "tpu path without its leader book"))?;
                let to = t.send(raw).await.map_err(|e| refuse(None, format!("{e:#}")))?;
                Ok(rep(sig.to_string(), None, None, format!("written to leaders {}", to.join(","))))
            }
            SendKind::NextBlock | SendKind::Bloxroute | SendKind::FlashBlock => {
                let b64 = base64::engine::general_purpose::STANDARD.encode(raw);
                let body = match self.kind {
                    SendKind::FlashBlock => json!({ "transactions": [b64] }),
                    SendKind::Bloxroute => json!({ "transaction": { "content": b64 }, "skipPreFlight": true, "frontRunningProtection": false, "submitProtection": "SP_LOW", "useStakedRPCs": true }),
                    _ => json!({ "transaction": { "content": b64 }, "skipPreFlight": true, "frontRunningProtection": false }),
                };
                let resp = self.http.post(&self.url).headers(self.headers.clone()).json(&body).send().await.map_err(net)?;
                let status = resp.status().as_u16();
                lenient(status, &resp.bytes().await.map_err(net)?)
            }
            SendKind::NodeOne | SendKind::BlockRazor => {
                let resp = self.http.post(&self.url).headers(self.headers.clone()).header(CONTENT_TYPE, "application/octet-stream")
                    .body(raw.to_vec()).send().await.map_err(net)?;
                let status = resp.status().as_u16();
                lenient(status, &resp.bytes().await.map_err(net)?)
            }
            SendKind::JitoTx | SendKind::Helius | SendKind::Shyft | SendKind::Rpcfast | SendKind::Rpc
            | SendKind::Nozomi | SendKind::ZeroSlot | SendKind::Falcon | SendKind::Everstake | SendKind::JupiterTx | SendKind::SpeedLanding => {
                let b64 = base64::engine::general_purpose::STANDARD.encode(raw);
                // Helius / Shyft as web3.js's sendRawTransaction sent them in arbed; Jito and Beam as arbed's jitoSend
                let opts = match self.kind {
                    SendKind::Helius | SendKind::Shyft | SendKind::Rpc | SendKind::Nozomi | SendKind::ZeroSlot | SendKind::Falcon | SendKind::Everstake
                    | SendKind::JupiterTx => {
                        let mut o = json!({ "encoding": "base64", "skipPreflight": !self.preflight, "maxRetries": 0 });
                        if self.preflight { o["preflightCommitment"] = json!("processed"); }
                        o
                    }
                    _ => json!({ "encoding": "base64" }),
                };
                let body = json!({ "jsonrpc": "2.0", "id": 1, "method": "sendTransaction", "params": [b64, opts] });
                let resp = self.http.post(&self.url).headers(self.headers.clone()).json(&body).send().await.map_err(net)?;
                let status = resp.status().as_u16();
                // jito-tx with ?bundleOnly=true answers with the bundle id in a header
                let bundle = resp.headers().get("x-bundle-id").and_then(|v| v.to_str().ok()).map(String::from);
                // DET: constant-k names the staked forwarder it used (stake study: its node has no stake of its own)
                let route = resp.headers().get("x-ck-tx-route").and_then(|v| v.to_str().ok()).map(|s| s.chars().take(60).collect::<String>());
                let mut r = answer(status, &resp.bytes().await.map_err(net)?, bundle);
                if let (Ok(rep), Some(rt)) = (&mut r, route) { rep.reply = format!("{} route={rt}", rep.reply); }
                r
            }
            SendKind::Haan | SendKind::Bolt | SendKind::Iris | SendKind::Lunar => {
                let resp = self.http.post(&self.url).headers(self.headers.clone()).header(CONTENT_TYPE, "application/octet-stream")
                    .body(raw.to_vec()).send().await.map_err(net)?;
                let status = resp.status().as_u16();
                answer(status, &resp.bytes().await.map_err(net)?, None)
            }
        }
    }

    /// One keep-alive round trip (any reply warms the connection); None = skipped (the bundle budget was full).
    pub async fn warm(&self) -> Result<Option<Duration>> {
        let t = Instant::now();
        let r: Result<()> = async {
            match &self.ping {
                Ping::Get(u) => { self.http.get(u).headers(self.headers.clone()).send().await.map_err(|e| net(&self.name, e))?.bytes().await.map_err(|e| net(&self.name, e))?; }
                Ping::Health => {
                    let body = json!({ "jsonrpc": "2.0", "id": 1, "method": "getHealth", "params": [] });
                    self.http.post(&self.url).headers(self.headers.clone()).json(&body).send().await.map_err(|e| net(&self.name, e))?.bytes().await.map_err(|e| net(&self.name, e))?;
                }
                Ping::None => match &self.tpu {
                    Some(t) => { t.connect_next().await?; }
                    None => return Err(anyhow::anyhow!("skip")),
                },
                Ping::Tips => {
                    // re-authenticates when the token nears expiry; never takes a bundle's room
                    if !self.budget.as_ref().map_or(true, |b| b.try_now()) { return Err(anyhow::anyhow!("skip")); }
                    self.jito.as_ref().context("no block engine client")?.tip_accounts().await?;
                }
            }
            Ok(())
        }.await;
        let d = t.elapsed();
        let mut s = self.stats.lock().unwrap();
        match r {
            Ok(()) => { s.warm_us.push(d.as_micros() as u64); Ok(Some(d)) }
            Err(e) if e.to_string() == "skip" => Ok(None),
            Err(e) => { s.warm_errors += 1; Err(e) }
        }
    }

    /// AUTH PROBE (`arbx senders --probe`): deliver 4 bytes that cannot be a transaction (nothing can land, nothing is
    /// paid) and return what the endpoint answered. A key it rejects reads as an auth error (HTTP 401/403), one it accepts
    /// as a decode error. jito-bundle is skipped: logging in already checked its key.
    pub async fn probe(&self) -> String {
        if self.kind == SendKind::JitoBundle { return "skipped (the login already checked the key)".into(); }
        if self.kind == SendKind::Tpu { return "skipped (a leader sends no reply to read)".into(); }
        match self.deliver(&[1, 2, 3, 4], "", None).await {
            Ok(r) => format!("accepted junk?! reply {}", r.sig),
            Err(e) => e.msg,
        }
    }

    /// one line: counts, send and keep-alive latency (p50/p90, ms)
    pub fn summary(&self) -> String {
        let mut s = self.stats.lock().unwrap();
        let p = |v: &mut Vec<u64>, q: f64| { if v.is_empty() { return f64::NAN; } v.sort_unstable(); v[((v.len() - 1) as f64 * q).round() as usize] as f64 / 1000.0 };
        let (s50, s90, w50, w90) = (p(&mut s.send_us, 0.5), p(&mut s.send_us, 0.9), p(&mut s.warm_us, 0.5), p(&mut s.warm_us, 0.9));
        let line = format!("{}: sent {} ok {} refused {} over-rate {} (crowded {}) bad-tx {}; send {s50:.1}/{s90:.1} ms; keep-alive {w50:.1}/{w90:.1} ms ({}, {} errors)",
            self.name, s.sent, s.ok, s.refused, s.limited, s.limited_crowded, s.bad_tx, s.warm_us.len(), s.warm_errors);
        if s.send_us.len() > 100_000 { s.send_us.clear(); }
        if s.warm_us.len() > 100_000 { s.warm_us.clear(); }
        match &self.jito { Some(j) => format!("{line}; bundle results {:?}", j.counts.lock().unwrap()), None => line }
    }
}

/// One copy of a trade for one path, the tip it carries (account, lamports), the slot of its blockhash, and (FT-006) the
/// kind of the leader it is aimed at (`jito`, `bam`, ...: copies.jsonl `leader_kind`)
#[derive(Clone)]
pub struct Copy { pub path: usize, pub raw: Arc<Vec<u8>>, pub tip: Option<(Pk, u64)>, pub blockhash_slot: Option<u64>, pub leader_kind: Option<&'static str> }

/// One line of copies.jsonl: one copy sent (or not) to one path
#[derive(Clone, Debug, serde::Serialize)]
pub struct Sent {
    pub attempt: u64,
    pub path: String,
    /// our transaction's signature (each path's copy differs when tips differ)
    pub sig: Option<String>,
    pub tip_account: Option<String>,
    pub tip_lamports: u64,
    /// request left / answer came back (ns); 0 = never sent / never answered
    pub t_sent: u64,
    pub t_ack: u64,
    pub ms: f64,
    /// accepted by the endpoint
    pub ok: bool,
    pub status: Option<u16>,
    /// the endpoint's reply, or why the copy failed
    pub reply: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")] pub bundle: Option<String>,
    /// (1.2, WP-05) the slot of the blockhash it was built on, how long it waited in the rate queue (µs; null: not
    /// queued, or never got a slot), why it never left (`rate_queue_timeout`, `crowded_pool`, `bad_tx`,
    /// `jito_auth_stale`; null: it left, or the endpoint refused it), and λ when it was queued
    pub blockhash_slot: Option<u64>,
    pub queue_wait_us: Option<u64>,
    pub drop: Option<&'static str>,
    pub lambda: Option<i64>,
    /// (1.3, FT-006) the endpoint the copy went to (the path's host, never its URL: keys live in some; a jito-bundle path:
    /// its block engine) and the kind of the target slot's leader (`jito`, `bam`, `other`, `unknown`; null: not given)
    pub endpoint: Option<String>,
    pub leader_kind: Option<&'static str>,
}

/// Everything that happened to one fired trade
#[derive(Clone, Debug, serde::Serialize)]
pub struct Fired { pub id: u64, pub t_ns: u64, pub copies: Vec<Sent> }

impl Fired {
    /// ---- WP-09: read back as `Serialize` wrote it (journal INPUT 9 `settled` `fired`: a replay hands it to its executor)
    pub fn from_json(v: &serde_json::Value) -> Option<Fired> {
        Some(Fired { id: v["id"].as_u64()?, t_ns: v["t_ns"].as_u64()?, copies: v["copies"].as_array()?.iter().map(Sent::from_json).collect::<Option<Vec<_>>>()? })
    }
}

impl Sent {
    /// ---- WP-09: read back as `Serialize` wrote it (a copy of journal INPUT 9 `fired`)
    pub fn from_json(v: &serde_json::Value) -> Option<Sent> {
        let s = |k: &str| v[k].as_str().map(String::from);
        Some(Sent { attempt: v["attempt"].as_u64()?, path: v["path"].as_str()?.to_string(), sig: s("sig"), tip_account: s("tip_account"),
            tip_lamports: v["tip_lamports"].as_u64()?, t_sent: v["t_sent"].as_u64()?, t_ack: v["t_ack"].as_u64()?, ms: v["ms"].as_f64().unwrap_or(0.0),
            ok: v["ok"].as_bool()?, status: v["status"].as_u64().and_then(|x| u16::try_from(x).ok()), reply: s("reply"), bundle: s("bundle"),
            blockhash_slot: v["blockhash_slot"].as_u64(), queue_wait_us: v["queue_wait_us"].as_u64(), drop: v["drop"].as_str().map(drop_code),
            lambda: v["lambda"].as_i64(), endpoint: s("endpoint"), leader_kind: v["leader_kind"].as_str().and_then(leader_kind_code) })
    }
}

/// a copy's `leader_kind` (copies.jsonl 1.3) as the static string the sender writes; None: not a leader kind
pub fn leader_kind_code(s: &str) -> Option<&'static str> {
    ["jito", "bam", "other", "unknown"].into_iter().find(|k| *k == s)
}

/// a copy's `drop` code (copies.jsonl, MEASUREMENT §4.38) as the static string the sender writes; one this build does
/// not write: `other`
pub fn drop_code(s: &str) -> &'static str {
    match s {
        "rate_queue_timeout" => "rate_queue_timeout", "crowded_pool" => "crowded_pool", "bad_tx" => "bad_tx", "jito_auth_stale" => "jito_auth_stale",
        "send_task" => "send_task", _ => "other",
    }
}

pub struct Paths {
    pub list: Vec<Arc<Path>>,
    /// copies.jsonl (core) and keepalive.jsonl (slow), through the recorder
    rec: crate::rec::Rec,
    rt: tokio::runtime::Handle,
}

impl Paths {
    /// Build every enabled path (jito-bundle: connect, authenticate, check the tip accounts against the block engine).
    /// `rec` gets copies.jsonl, keepalive.jsonl and bundles.jsonl (`Rec::off()`: nothing recorded). With `lenient`, a
    /// path that can't be built (a key missing from .env, ...) is left out and named in the returned notes instead of
    /// failing; a provider key that is the payer's keypair (I-10) fails the start even then. Call inside the runtime the
    /// sends run on (the hot one).
    pub async fn new(cfgs: &[SendPath], opts: PathsOpts, rec: crate::rec::Rec, lenient: bool) -> Result<(Arc<Paths>, Vec<String>)> {
        let mut list = Vec::new();
        let mut notes = Vec::new();
        for c in cfgs.iter().filter(|c| c.enabled) {
            if let Some(p) = &opts.payer { check_key_material(c, p)?; }
            if let Some(n) = crate::config::cleartext_check(c)? { notes.push(n); }
            match Path::new(c, &rec, &opts).await {
                Ok(p) => list.push(Arc::new(p)),
                Err(e) if lenient => notes.push(format!("{}: left out: {e:#}", c.name)),
                Err(e) => return Err(e),
            }
        }
        Ok((Arc::new(Paths { list, rec, rt: tokio::runtime::Handle::current() }), notes))
    }

    pub fn index(&self, name: &str) -> Option<usize> { self.list.iter().position(|p| p.name == name) }

    /// tests: paths made by hand (no network at construction), recording into `rec`
    #[cfg(test)]
    pub fn for_test(list: Vec<Path>, rec: crate::rec::Rec) -> Arc<Paths> {
        Arc::new(Paths { list: list.into_iter().map(Arc::new).collect(), rec, rt: tokio::runtime::Handle::current() })
    }

    /// the first jito-bundle path (the only one a live run sends through)
    pub fn bundle_path(&self) -> Option<usize> { self.list.iter().position(|p| p.kind == SendKind::JitoBundle) }

    /// the rate queues' waiting sends, and the lowest λ of them (status `exec.queue_now`, `lambda_now`)
    pub fn queue_now(&self) -> (usize, Option<i64>) {
        let mut n = 0;
        let mut l: Option<i64> = None;
        for p in &self.list { if let Some((w, x)) = p.queue_now() { n += w; if let Some(x) = x { l = Some(l.map_or(x, |y| y.min(x))); } } }
        (n, l)
    }

    /// Keep every path warm (one round trip each `every`, each one a line in keepalive.jsonl), follow the bundle result
    /// streams, and keep each block engine's auth token renewed (`Jito::keep_token`), until `stop`. The jito-bundle
    /// path's round trip is the block engine's RTT (`leaders::note_be_rtt`: attempts' `leader.be_rtt_ms`)
    pub fn start(self: &Arc<Self>, stop: Arc<AtomicBool>, every: Duration, status: impl Fn(String) + Clone + Send + Sync + 'static) {
        for p in &self.list {
            if let Some(j) = &p.jito {
                self.rt.spawn(j.clone().follow_results(stop.clone(), status.clone()));
                self.rt.spawn(j.clone().keep_token(stop.clone()));
            }
            if let Some(t) = &p.tpu { self.rt.spawn(t.clone().keep_warm(stop.clone())); }
        }
        let me = self.clone();
        self.rt.spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                for p in &me.list {
                    let (p, status, me) = (p.clone(), status.clone(), me.clone());
                    tokio::spawn(async move {
                        let t_ns = now_ns();
                        let r = p.warm().await;
                        note_keepalive(&p, &r);
                        let (ms, error) = match &r { Ok(Some(d)) => (Some(d.as_secs_f64() * 1e3), None), Ok(None) => return, Err(e) => (None, Some(format!("{e:#}"))) };
                        if let Some(e) = &error { status(format!("{} keep-alive: {e}", p.name)); }
                        me.rec.json(crate::rec::KEEPALIVE, json!({ "t_ns": t_ns, "path": p.name, "ms": ms, "error": error }));
                    });
                }
                tokio::time::sleep(every).await;
            }
        });
    }

    pub fn summary(&self) -> Vec<String> { self.list.iter().map(|p| p.summary()).collect() }

    /// Send one trade's copies, from any thread (the work runs on the runtime), all at once (Stage 0: one bundle copy).
    /// Every copy is a line in copies.jsonl, including the ones never sent and the ones never answered. `net`: the send
    /// path's network-call scope (`netcount`), carried into every copy's task
    pub fn fire(self: &Arc<Self>, attempt: u64, copies: Vec<Copy>, prio: Prio) -> tokio::task::JoinHandle<Fired> { self.fire_after(attempt, copies, prio, Duration::ZERO) }

    /// `fire`, the copies leaving `delay` later (WP-11's X2 arm): a tokio sleep on the send task itself, so the caller (the
    /// engine thread) returns at once; the fire result's `t_ns` and each copy's `t_sent` are taken after it. A zero delay is
    /// `fire` exactly (no sleep)
    pub fn fire_after(self: &Arc<Self>, attempt: u64, copies: Vec<Copy>, prio: Prio, delay: Duration) -> tokio::task::JoinHandle<Fired> {
        let me = self.clone();
        let net = crate::netcount::current();
        self.rt.spawn(crate::netcount::in_task(net.clone(), async move {
            if !delay.is_zero() { tokio::time::sleep(delay).await; }
            let t0_ns = now_ns();
            let hs: Vec<_> = copies.into_iter().map(|c| {
                let p = me.list[c.path].clone();
                tokio::spawn(crate::netcount::in_task(net.clone(), async move {
                    let mut out = Sent { attempt, path: p.name.clone(), sig: first_signature(&c.raw), tip_account: c.tip.map(|t| crate::tx::b58(&t.0)),
                        tip_lamports: c.tip.map_or(0, |t| t.1), t_sent: 0, t_ack: 0, ms: 0.0, ok: false, status: None, reply: None, bundle: None,
                        blockhash_slot: c.blockhash_slot, queue_wait_us: None, drop: None, lambda: p.queue_now().and_then(|q| q.1), endpoint: None,
                        leader_kind: c.leader_kind };
                    let t = Instant::now();
                    out.t_sent = now_ns();
                    let r = tokio::time::timeout(SEND_TIMEOUT, p.send(&c.raw, prio, Some(attempt))).await
                        .unwrap_or_else(|_| Err(refuse(None, format!("{}: no answer in {SEND_TIMEOUT:?}", p.name))));
                    out.ms = t.elapsed().as_secs_f64() * 1e3;
                    out.endpoint = Some(p.endpoint());
                    match r {
                        Ok(r) => {
                            out.t_ack = now_ns();
                            out.ok = true;
                            out.status = r.status;
                            out.bundle = r.bundle;
                            out.queue_wait_us = r.queue_wait_us;
                            out.reply = Some(if out.sig.as_deref() == Some(r.sig.as_str()) { r.reply } else { format!("{} (returned signature {})", r.reply, r.sig) });
                        }
                        Err(e) => {
                            // an answer (an HTTP status, a gRPC refusal) has its time; a timeout or a transport error has none
                            if e.answered { out.t_ack = now_ns(); }
                            out.status = e.status;
                            out.reply = Some(short(&e.msg));
                            out.drop = e.code;
                            // never left: no send time
                            if e.code.is_some() { out.t_sent = 0; }
                        }
                    }
                    out
                }))
            }).collect();
            let mut out = Vec::with_capacity(hs.len());
            for h in hs { if let Ok(s) = h.await { out.push(s); } }
            // one copies.jsonl line per copy, serialized on the recorder's core writer
            for c in &out { me.rec.emit(crate::rec::COPIES, crate::rec::Record::ser(c.clone())); }
            Fired { id: attempt, t_ns: t0_ns, copies: out }
        }))
    }
}

/// A keep-alive's round trip: the jito-bundle path's is the block engine's RTT, published for attempts
/// (`leaders::note_be_rtt`; MEASUREMENT §4.37 `leader.be_rtt_ms`)
fn note_keepalive(p: &Path, r: &Result<Option<Duration>>) {
    if let Some(ms) = keepalive_be_rtt(p.kind, r) { crate::leaders::note_be_rtt(ms); }
}

/// the block engine's RTT (ms) a keep-alive gives: a jito-bundle path's answered round trip; None otherwise
fn keepalive_be_rtt(kind: SendKind, r: &Result<Option<Duration>>) -> Option<f64> {
    match (kind, r) { (SendKind::JitoBundle, Ok(Some(d))) => Some(d.as_secs_f64() * 1e3), _ => None }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::SendPath;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    const SIG: [u8; 64] = [0x11; 64];

    /// a legacy transaction: payer, `to`, System program; one transfer of `lamports` to `to`, optional CU price
    fn tx(to: Pk, lamports: u64, cu_price: bool) -> Vec<u8> {
        let mut t = vec![1u8];
        t.extend(SIG);
        let cb = crate::tx::COMPUTE_BUDGET;
        t.extend([1, 0, 2]);
        t.push(4); t.extend([9u8; 32]); t.extend(to); t.extend(SYSTEM_PROGRAM); t.extend(cb);
        t.extend([7u8; 32]);
        t.push(if cu_price { 2 } else { 1 });
        t.push(2); t.push(2); t.extend([0, 1]); t.push(12); t.extend([2, 0, 0, 0]); t.extend(lamports.to_le_bytes());
        if cu_price { t.push(3); t.push(0); t.push(9); t.push(3); t.extend(1_000u64.to_le_bytes()); }
        t
    }

    fn cfg(kind: &str, url: String) -> SendPath {
        let mut c: SendPath = toml::from_str(&format!("name = \"t\"\nkind = \"{kind}\"\nurl = \"{url}\"")).unwrap();
        c.tip_lamports = c.kind.min_tip();
        c
    }

    /// WP-08 (plan addendum; review WP-08 #1): the names rivals.jsonl uses (`tip_owner_names`, the engine's `tip_names`)
    /// include the catalogue's accounts the code lists do not name: Glaive's (4,197 cmp2 rows recorded unnamed), Soyas',
    /// AllenHark's, Solami's and the bloXroute / SVS legacy ones. Every catalogue account is named, a code name wins over
    /// the catalogue's, and every service that adds an account of its own names its sender (review #19: a key such as
    /// `temporal_nozomi` must not become a sender name by accident)
    #[test]
    fn rival_tip_names_take_the_catalogue() {
        let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
        let (code, all) = (code_tip_names(), tip_owner_names());
        for (a, want) in [("GLaivinAWh21NaJMhtExtD5G2gZs1xnvaYVZmwqobWZL", "glaive"), ("soyas4s6L8KWZ8rsSk1mF3d1mQScoTGGAgjk98bF8nP", "soyas"),
            ("HWEoBxYs7ssKuudEjzjmpfJVX7Dvi7wescFsVx2L5yoY", "bloxroute"), ("95cfoy472fcQHaw4tPGBTKpn6ZQnfEPfBgDQx6gcRmRg", "bloxroute")] {
            assert_eq!((code.get(&pk(a)), all.get(&pk(a)).map(String::as_str)), (None, Some(want)), "{a}");
        }
        assert_eq!(all.get(&pk("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")).map(String::as_str), Some("jito"), "the code's name first");
        let cat: Value = serde_json::from_str(TIP_CATALOGUE).unwrap();
        let mut added = 0;
        for (svc, s) in cat.as_object().unwrap() {
            let accts: Vec<Pk> = s["tip_accounts"].as_array().into_iter().flatten().map(|a| pk(a.as_str().unwrap())).collect();
            for k in &accts { assert!(all.contains_key(k), "{svc}: {} unnamed", crate::tx::b58(k)); }
            let own = accts.iter().filter(|k| !code.contains_key(*k)).count();
            if own > 0 { assert!(s["sender"].is_string(), "{svc} adds {own} accounts: it needs a `sender`"); }
            added += own;
        }
        assert_eq!((added, all.len()), (46, code.len() + 46), "the catalogue adds 46 accounts (2026-10-04)");
    }

    /// one-shot HTTP/1.1 server: answers `reply` (status, body) and hands back the request it got
    async fn server(status: u16, reply: &'static str) -> (String, tokio::task::JoinHandle<(String, Vec<u8>)>) {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        let h = tokio::spawn(async move {
            let (mut s, _) = l.accept().await.unwrap();
            let mut buf = Vec::new();
            let mut chunk = [0u8; 4096];
            loop {
                let n = s.read(&mut chunk).await.unwrap();
                buf.extend_from_slice(&chunk[..n]);
                if let Some(end) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                    let head = String::from_utf8_lossy(&buf[..end]).to_string();
                    let len: usize = head.lines().find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().parse().unwrap())).unwrap_or(0);
                    while buf.len() < end + 4 + len { let n = s.read(&mut chunk).await.unwrap(); buf.extend_from_slice(&chunk[..n]); }
                    let body = buf[end + 4..end + 4 + len].to_vec();
                    let resp = format!("HTTP/1.1 {status} X\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{reply}", reply.len());
                    s.write_all(resp.as_bytes()).await.unwrap();
                    return (head, body);
                }
            }
        });
        (format!("http://{addr}"), h)
    }

    fn sig58() -> String { bs58::encode(SIG).into_string() }

    #[test]
    fn first_signature_of_v0_and_v1() {
        let t = tx([3; 32], 1, false);
        assert_eq!(first_signature(&t).unwrap(), sig58());
        // v1: 0x81, header (num signers 2 at byte 1) ..., signatures last
        let mut v1 = vec![0x81, 2, 0, 0];
        v1.extend([0u8; 40]);
        v1.extend([0xAA; 64]);
        v1.extend([0xBB; 64]);
        assert_eq!(first_signature(&v1).unwrap(), bs58::encode([0xAA; 64]).into_string());
        assert!(first_signature(&[0u8]).is_none());
    }

    fn no_opts() -> PathsOpts { PathsOpts::default() }

    /// WP-00 (F6): copies refused for the path's rate are counted, and the crowded-rank ones apart; WP-05: the refusal
    /// says why (`rate_queue_timeout`: no queue here)
    #[tokio::test]
    async fn rate_drops_are_split_by_crowded_rank() {
        let mut c = cfg("rpc", "http://127.0.0.1:1".into());
        c.max_per_sec = Some(1);
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let raw = tx([3; 32], 1, false);
        // takes the one slot of this second (its delivery fails: nothing listens there)
        assert!(p.send(&raw, Prio { band: 0, crowd: 0, ev: 1 }, None).await.is_err());
        let over = |e: Result<Reply, Refusal>| e.err().is_some_and(|e| e.msg.contains("over its rate") && e.code == Some("rate_queue_timeout"));
        assert!(over(p.send(&raw, Prio { band: 0, crowd: 1, ev: 9 }, None).await));
        assert!(over(p.send(&raw, Prio { band: 1, crowd: 0, ev: 1 }, None).await));
        let s = p.stats.lock().unwrap();
        assert_eq!((s.limited, s.limited_crowded), (2, 1));
    }

    /// PLAN-ADDENDUM I-10 (the second half): a provider key that is a keypair may not be the payer's. Any secret value a
    /// path names (its URL's `${...}`, the expanded URL's query values and path segments, `token_env`, `jito_auth_env`),
    /// in base58 (64-byte keypair, 32-byte seed) or solana-keygen JSON, and the jito auth keypair file, are checked; a
    /// dedicated keypair passes. `Paths::new` refuses the payer's even when lenient
    #[tokio::test]
    async fn a_provider_key_may_not_be_the_payers_keypair() {
        let payer_key = ed25519_dalek::SigningKey::from_bytes(&[42u8; 32]);
        let payer = payer_key.verifying_key().to_bytes();
        let mut kp = payer_key.to_bytes().to_vec();
        kp.extend(payer);
        let payer_b58 = bs58::encode(&kp).into_string();
        let other = ed25519_dalek::SigningKey::from_bytes(&[43u8; 32]);
        let mut okp = other.to_bytes().to_vec();
        okp.extend(other.verifying_key().to_bytes());
        assert_eq!(keypair_pubkey(&payer_b58), Some(payer));
        assert_eq!(keypair_pubkey(&bs58::encode([42u8; 32]).into_string()), Some(payer), "a 32-byte seed");
        assert_eq!(keypair_pubkey(&serde_json::to_string(&kp).unwrap()), Some(payer), "solana-keygen JSON");
        assert_eq!(keypair_pubkey("not-a-key"), None);
        std::env::set_var("ARB_TEST_SPEED_KEY_PAYER", &payer_b58);
        std::env::set_var("ARB_TEST_SPEED_KEY_OWN", bs58::encode(&okp).into_string());
        let mut c = cfg("speed-landing", "https://fra.speedlanding.trade/sendTx?apikey=${ARB_TEST_SPEED_KEY_PAYER}".into());
        let e = check_key_material(&c, &payer).unwrap_err().to_string();
        assert!(e.contains("payer's keypair") && !e.contains(&payer_b58), "named, never printed: {e}");
        c.url = "https://fra.speedlanding.trade/sendTx?apikey=${ARB_TEST_SPEED_KEY_OWN}".into();
        assert!(check_key_material(&c, &payer).unwrap() >= 1, "a dedicated keypair");
        // the payer's key in a header (token_env), or literally in the URL
        let mut h = cfg("node-one", "https://fra.node1.me/v2".into());
        h.token_env = Some("ARB_TEST_SPEED_KEY_PAYER".into());
        assert!(check_key_material(&h, &payer).is_err());
        let lit = cfg("speed-landing", format!("https://fra.speedlanding.trade/sendTx?apikey={payer_b58}"));
        assert!(check_key_material(&lit, &payer).is_err());
        // the jito auth keypair file
        let d = std::env::temp_dir().join(format!("arbx-jito-auth-{}-{}", std::process::id(), now_ns()));
        std::fs::write(&d, serde_json::to_string(&kp).unwrap()).unwrap();
        let mut j = cfg("jito-bundle", "https://127.0.0.1:1".into());
        j.auth_keypair = Some(d.display().to_string());
        assert!(check_key_material(&j, &payer).unwrap_err().to_string().contains("auth keypair is the payer's"));
        std::fs::write(&d, serde_json::to_string(&okp).unwrap()).unwrap();
        assert!(check_key_material(&j, &payer).is_ok());
        let _ = std::fs::remove_file(&d);
        // lenient or not, the start refuses
        let bad = cfg("speed-landing", "https://127.0.0.1:1/sendTx?apikey=${ARB_TEST_SPEED_KEY_PAYER}".into());
        let r = Paths::new(&[bad], PathsOpts { queue_ms: 0, payer: Some(payer) }, crate::rec::Rec::off(), true).await;
        assert!(r.err().is_some_and(|e| e.to_string().contains("payer's keypair")));
        // and the run-time I-10 check: a `${...}` that expands into plain http://
        std::env::set_var("ARB_TEST_WHOLE_URL", "http://127.0.0.1:1/?api-key=abc");
        let whole = cfg("rpc", "${ARB_TEST_WHOLE_URL}".into());
        let e = Path::new(&whole, &crate::rec::Rec::off(), &no_opts()).await.err().expect("refused").to_string();
        assert!(e.contains("plain http://") && e.contains("I-10") && !e.contains("abc"), "{e}");
    }

    /// the jito-bundle path's keep-alive round trip is the block engine's RTT, published for attempts (`be_rtt_ms`;
    /// `Paths::start` calls `note_keepalive`, which publishes this value with `leaders::note_be_rtt`)
    #[test]
    fn the_bundle_paths_keepalive_is_the_block_engines_rtt() {
        let ok = Ok(Some(Duration::from_micros(41_500)));
        assert_eq!(keepalive_be_rtt(SendKind::JitoBundle, &ok), Some(41.5));
        assert_eq!(keepalive_be_rtt(SendKind::Helius, &ok), None, "another kind's round trip is not the block engine's");
        assert_eq!(keepalive_be_rtt(SendKind::JitoBundle, &Ok(None)), None, "skipped (the budget was full)");
        assert_eq!(keepalive_be_rtt(SendKind::JitoBundle, &Err(anyhow::anyhow!("down"))), None);
    }

    #[tokio::test]
    async fn tips_rotate_and_scale() {
        let mut c = cfg("helius", "http://127.0.0.1:1/fast".into());
        c.tip_lamports = 5_000;
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let (a, l) = p.tip(1_000_000).unwrap();
        let (b, _) = p.tip(0).unwrap();
        assert_eq!(l, 5_000);
        assert_ne!(a, b);
        assert_eq!(crate::tx::b58(&a), known_tip_accounts(SendKind::Helius)[0]);
        let mut j = p;
        (j.tip_share, j.tip_lamports, j.tip_max) = (Some(0.5), 10_000, 1_000_000);
        assert_eq!(j.tip(100_000).unwrap().1, 50_000);
        assert_eq!(j.tip(1_000).unwrap().1, 10_000, "floor");
        assert_eq!(j.tip(10_000_000).unwrap().1, 1_000_000, "cap");
        assert!(matches!(j.ping, Ping::Get(ref u) if u == "http://127.0.0.1:1/ping"));
    }

    #[tokio::test]
    async fn refuses_a_copy_that_does_not_pay_this_path() {
        let mut c = cfg("helius", "http://127.0.0.1:1/fast".into());
        c.tip_lamports = 5_000;
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let helius = crate::tx::pk(known_tip_accounts(SendKind::Helius)[3]);
        assert!(p.check(&tx(helius, 5_000, true)).is_ok());
        assert!(p.check(&tx(helius, 4_999, true)).is_err(), "below the minimum");
        assert!(p.check(&tx(helius, 5_000, false)).is_err(), "no CU price");
        assert!(p.check(&tx([3; 32], 5_000, true)).is_err(), "someone else's account");
        assert!(p.check(&[tx(helius, 5_000, true), vec![0]].concat()).is_err(), "stray bytes");
    }

    #[tokio::test]
    async fn helius_posts_json_rpc_without_preflight() {
        let reply: &'static str = Box::leak(format!("{{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":\"{}\"}}", sig58()).into_boxed_str());
        let (base, h) = server(200, reply).await;
        let mut c = cfg("helius", format!("{base}/fast?swqos_only=true"));
        c.tip_lamports = 5_000;
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let raw = tx(crate::tx::pk(known_tip_accounts(SendKind::Helius)[0]), 5_000, true);
        let r = p.send(&raw, Prio::default(), None).await.unwrap();
        assert_eq!(r.sig, sig58());
        let (head, body) = h.await.unwrap();
        assert!(head.starts_with("POST /fast?swqos_only=true "), "{head}");
        let v: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(v["method"], "sendTransaction");
        assert_eq!(v["params"][0], base64::engine::general_purpose::STANDARD.encode(&raw));
        assert_eq!(v["params"][1], json!({ "encoding": "base64", "skipPreflight": true, "maxRetries": 0 }));
    }

    /// review F12: copies.jsonl through the recorder: one line per copy (serialized on the core writer) with the
    /// attempt, the path, our signature, the send and ack times, the reply and the HTTP status
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn fired_copies_are_recorded() {
        let d = std::env::temp_dir().join(format!("arbx-copies-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let reply: &'static str = Box::leak(format!("{{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":\"{}\"}}", sig58()).into_boxed_str());
        let (base, h) = server(200, reply).await;
        let mut c = cfg("helius", format!("{base}/fast"));
        c.tip_lamports = 5_000;
        let (ps, _) = Paths::new(&[c], no_opts(), rec.clone(), false).await.unwrap();
        let raw = Arc::new(tx(crate::tx::pk(known_tip_accounts(SendKind::Helius)[0]), 5_000, true));
        let fired = ps.fire(42, vec![Copy { path: 0, raw, tip: None, blockhash_slot: Some(77), leader_kind: Some("bam") }], Prio::default()).await.unwrap();
        let _ = h.await;
        assert!(fired.copies[0].ok);
        rec.close();
        let v = crate::rec::read_jsonl(&d, "copies").unwrap();
        assert_eq!(v.len(), 1);
        assert_eq!((v[0]["attempt"].as_u64(), v[0]["path"].as_str(), v[0]["sig"].as_str(), v[0]["ok"].as_bool(), v[0]["status"].as_u64()),
            (Some(42), Some("t"), Some(sig58().as_str()), Some(true), Some(200)));
        assert!(v[0]["t_sent"].as_u64().unwrap() > 0 && v[0]["t_ack"].as_u64().unwrap() >= v[0]["t_sent"].as_u64().unwrap());
        // copies 1.2 (WP-05): the blockhash's slot; not queued (no rate budget), nothing dropped
        assert_eq!((v[0]["blockhash_slot"].as_u64(), v[0]["queue_wait_us"].is_null(), v[0]["drop"].is_null()), (Some(77), true, true));
        // copies 1.3 (FT-006): the endpoint's host (never the URL) and the target leader's kind
        assert_eq!((v[0]["endpoint"].as_str(), v[0]["leader_kind"].as_str()), (Some("127.0.0.1"), Some("bam")));
        let _ = std::fs::remove_dir_all(&d);
    }

    /// FT-006 through the in-memory block engine: a bundle copy aimed at a BAM-led slot reaches the block engine as one
    /// signed transaction, and copies.jsonl names its endpoint (the block engine's host) and the leader kind; a copy line of
    /// 1.2 (no endpoint, no kind) still reads back (journal INPUT 9 `fired`)
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_bundle_copy_records_its_endpoint_and_leader_kind() {
        let d = std::env::temp_dir().join(format!("arbx-copies-bam-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let j = jito::Jito::for_test(rec.clone());
        j.set_cached(Some(jito::CachedToken { value: "tok".into(), exp_ms: now_ns() as i64 / 1_000_000 + 600_000, issued_ms: now_ns() as i64 / 1_000_000 }));
        let got: Arc<Mutex<Vec<Vec<u8>>>> = Default::default();
        let g2 = got.clone();
        j.set_fake(Arc::new(move |txs: &[&[u8]]| { g2.lock().unwrap().push(txs[0].to_vec()); "bam-b0".into() }));
        let ps = Paths::for_test(vec![Path::test_bundle(j, Some(5), 10)], rec.clone());
        assert_eq!(ps.list[0].endpoint(), "127.0.0.1");
        let raw = Arc::new(tx(crate::tx::pk(known_tip_accounts(SendKind::JitoBundle)[2]), 5_000, false));
        let fired = ps.fire(9, vec![Copy { path: 0, raw: raw.clone(), tip: Some((crate::tx::pk(known_tip_accounts(SendKind::JitoBundle)[2]), 5_000)),
            blockhash_slot: Some(100), leader_kind: Some("bam") }], Prio::default()).await.unwrap();
        let c = &fired.copies[0];
        assert!(c.ok && c.bundle.as_deref() == Some("bam-b0"), "{c:?}");
        assert_eq!((c.endpoint.as_deref(), c.leader_kind, c.tip_lamports), (Some("127.0.0.1"), Some("bam"), 5_000));
        assert_eq!(*got.lock().unwrap(), vec![raw.to_vec()], "the one signed transaction reached the block engine");
        rec.close();
        let v = crate::rec::read_jsonl(&d, "copies").unwrap();
        assert_eq!((v[0]["endpoint"].as_str(), v[0]["leader_kind"].as_str(), v[0]["bundle"].as_str()), (Some("127.0.0.1"), Some("bam"), Some("bam-b0")));
        // read back as written (1.3), and a 1.2 line without the new fields
        let back = Sent::from_json(&v[0]).unwrap();
        assert_eq!((back.endpoint.as_deref(), back.leader_kind), (Some("127.0.0.1"), Some("bam")));
        let mut old = v[0].clone();
        for k in ["endpoint", "leader_kind"] { old.as_object_mut().unwrap().remove(k); }
        let back = Sent::from_json(&old).unwrap();
        assert_eq!((back.endpoint, back.leader_kind, back.attempt), (None, None, 9));
        assert_eq!((leader_kind_code("jito"), leader_kind_code("other"), leader_kind_code("x")), (Some("jito"), Some("other"), None));
        let _ = std::fs::remove_dir_all(&d);
    }

    /// WP-11 (X2): `fire_after` sleeps on the send task, never on its caller: the handle comes back at once and the copy
    /// leaves the delay later (its `t_sent` and the fire's `t_ns` after the sleep); a zero delay is `fire`
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn fire_after_sleeps_on_the_send_task() {
        let d = std::env::temp_dir().join(format!("arbx-copies-x2-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let j = jito::Jito::for_test(rec.clone());
        j.set_cached(Some(jito::CachedToken { value: "tok".into(), exp_ms: now_ns() as i64 / 1_000_000 + 600_000, issued_ms: now_ns() as i64 / 1_000_000 }));
        j.set_fake(Arc::new(move |_: &[&[u8]]| "x2-b0".into()));
        let ps = Paths::for_test(vec![Path::test_bundle(j, Some(50), 10)], rec.clone());
        let tip = crate::tx::pk(known_tip_accounts(SendKind::JitoBundle)[1]);
        for (attempt, delay_ms) in [(1u64, 20u64), (2, 0)] {
            let raw = Arc::new(tx(tip, 5_000 + attempt, false));
            let t0 = now_ns();
            let h = ps.fire_after(attempt, vec![Copy { path: 0, raw, tip: Some((tip, 5_000)), blockhash_slot: Some(100), leader_kind: Some("jito") }], Prio::default(),
                Duration::from_millis(delay_ms));
            let handed = now_ns() - t0;
            assert!(handed < 15_000_000, "the caller is not held by the delay: {handed} ns");
            let fired = h.await.unwrap();
            let c = &fired.copies[0];
            assert!(c.ok, "{c:?}");
            assert!(c.t_sent >= t0 + delay_ms * 1_000_000 && fired.t_ns >= t0 + delay_ms * 1_000_000, "{delay_ms} ms: the copy left {} ms after the fire",
                (c.t_sent - t0) as f64 / 1e6);
        }
        rec.close();
        let _ = std::fs::remove_dir_all(&d);
    }

    #[tokio::test]
    async fn haan_posts_raw_bytes_with_both_headers() {
        let reply: &'static str = Box::leak(sig58().into_boxed_str());
        let (base, h) = server(200, reply).await;
        std::env::set_var("ARB_TEST_HAAN_KEY", "k1");
        std::env::set_var("ARB_TEST_JITO_UUID", "u1");
        let mut c = cfg("haan", format!("{base}/api/v1/transactions"));
        c.token_env = Some("ARB_TEST_HAAN_KEY".into());
        c.jito_auth_env = Some("ARB_TEST_JITO_UUID".into());
        // review WP-05 #5: header keys over plain http are refused at the start too, unless the exception is recorded
        let e = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.err().expect("refused").to_string();
        assert!(e.contains("plain http://") && e.contains("I-10") && !e.contains("k1") && !e.contains("u1"), "{e}");
        c.no_tls_endpoint = Some("the test server has no TLS".into());
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let raw = tx([3; 32], 0, false);
        assert_eq!(p.send(&raw, Prio::default(), None).await.unwrap().sig, sig58());
        let (head, body) = h.await.unwrap();
        let head = head.to_ascii_lowercase();
        assert!(head.contains("authorization: bearer k1") && head.contains("x-jito-auth: u1") && head.contains("content-type: application/octet-stream"), "{head}");
        assert_eq!(body, raw);
    }

    #[tokio::test]
    async fn bolt_error_reply_is_an_error_with_its_words() {
        let (base, _h) = server(400, "{\"success\":false,\"error\":\"missing tip\"}").await;
        std::env::set_var("ARB_TEST_BOLT_KEY", "b1");
        let mut c = cfg("bolt", format!("{base}/api/v1/sendRawTransaction"));
        c.token_env = Some("ARB_TEST_BOLT_KEY".into());
        c.no_tls_endpoint = Some("the test server has no TLS".into());
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let raw = tx(crate::tx::pk(known_tip_accounts(SendKind::Bolt)[0]), 1_000_000, false);
        let e = p.send(&raw, Prio::default(), None).await.unwrap_err().to_string();
        assert!(e.contains("missing tip"), "{e}");
        assert_eq!(p.stats.lock().unwrap().refused, 1);
    }

    #[tokio::test]
    async fn errors_never_carry_the_url() {
        std::env::set_var("ARB_TEST_IRIS_KEY", "SECRETKEY");
        // (https: I-10 refuses a secret over plain http)
        let mut c = cfg("iris", "https://127.0.0.1:1/irisb?api-key=${ARB_TEST_IRIS_KEY}&method=sendTransaction".into());
        c.tip_lamports = 10_000;
        let p = Path::new(&c, &crate::rec::Rec::off(), &no_opts()).await.unwrap();
        let raw = tx(crate::tx::pk(known_tip_accounts(SendKind::Iris)[0]), 10_000, false);
        let e = format!("{:#}", p.send(&raw, Prio::default(), None).await.unwrap_err());
        assert!(!e.contains("SECRETKEY"), "{e}");
        let w = format!("{:#}", p.warm().await.unwrap_err());
        assert!(!w.contains("SECRETKEY") && !p.describe().contains("SECRETKEY"), "{w}");
    }

    #[test]
    fn replies() {
        let s = sig58();
        assert_eq!(parse_reply("x", 200, format!("{{\"success\":true,\"signature\":\"{s}\"}}").as_bytes()).unwrap(), s);
        assert_eq!(parse_reply("x", 200, format!("{{\"result\":\"{s}\"}}").as_bytes()).unwrap(), s);
        assert!(parse_reply("x", 200, b"{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32602,\"message\":\"Invalid request\"}}").unwrap_err().to_string().contains("-32602 Invalid request"));
        assert!(parse_reply("x", 429, b"Too Many Requests").unwrap_err().to_string().contains("429"));
        assert!(parse_reply("x", 200, b"ok").is_err());
    }

}
