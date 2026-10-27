//! shreder_rec library: generated gRPC types, a minimal VersionedTransaction parser with a pump.fun
//! instruction summary, and small helpers (time formatting, key-file parsing, secret redaction).
//! Read-only measurement tool; nothing here signs or sends transactions.

pub mod pb {
    tonic::include_proto!("shreder_binary");
}

pub mod txparse;
pub mod util;
