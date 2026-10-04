//! The long run's recorders: everything needed to reconstruct who did what, when and how, written as the run goes.
//!   txarr.log     every forwarded transaction, when each feed delivered it: `sig8 slot first_ns d0 d1 ..` (µs after
//!                 the first feed, `-` = never), in feed order (meta.json lists the feeds)
//!   rivals.jsonl  every arbitrage-like transaction (2+ venue programs, 2+ of our pools, or a signer already seen doing
//!                 that): its fingerprint at shred time (fees, tips and their sender, nonce, programs, pools, tables)
//!   exec.jsonl    every executed transaction of the executed feed (Haan, PumpSwap): result, error, fee, CU, position
//!                 in the block, the signer's SOL and token changes
//!   moves.log     which transaction moved which of our pools: `sig slot pool t_ns`
//!   slots.log     per entries feed and slot: ticks, entries, transactions, first/last arrival (PoH completeness)
//!   entries.zst   the raw entries of one feed, replayable: per message slot u64, t_ns u64, len u32, bytes (zstd)
//!   alts.jsonl    the lookup tables the engine learned (to decode the archive offline)
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::{Mutex, OnceLock};

pub struct Recorder {
    pub dir: std::path::PathBuf,
    pub txarr: Mutex<BufWriter<std::fs::File>>,
    pub rivals: Mutex<BufWriter<std::fs::File>>,
    pub exec: Mutex<BufWriter<std::fs::File>>,
    pub moves: Mutex<BufWriter<std::fs::File>>,
    pub slots: Mutex<BufWriter<std::fs::File>>,
    pub caps: Mutex<BufWriter<std::fs::File>>,
    /// (feed id, zstd's stdin, the zstd process)
    archive: Option<(u16, Mutex<Option<BufWriter<std::process::ChildStdin>>>, Mutex<Option<std::process::Child>>)>,
}

pub static REC: OnceLock<Recorder> = OnceLock::new();

/// Open the recorders in `dir`; `archive` = the feed id whose raw entries are kept (compressed by an external zstd).
pub fn init(dir: &Path, archive: Option<u16>) -> anyhow::Result<()> {
    let open = |n: &str| -> anyhow::Result<Mutex<BufWriter<std::fs::File>>> { Ok(Mutex::new(BufWriter::with_capacity(1 << 20, std::fs::File::create(dir.join(n))?))) };
    let archive = match archive {
        Some(id) => {
            let mut child = std::process::Command::new("zstd").args(["-q", "-3", "-f", "-o"]).arg(dir.join("entries.zst"))
                .stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::null()).spawn()?;
            let stdin = child.stdin.take().ok_or_else(|| anyhow::anyhow!("zstd stdin"))?;
            Some((id, Mutex::new(Some(BufWriter::with_capacity(4 << 20, stdin))), Mutex::new(Some(child))))
        }
        None => None,
    };
    let r = Recorder { dir: dir.to_path_buf(), txarr: open("txarr.log")?, rivals: open("rivals.jsonl")?, exec: open("exec.jsonl")?, moves: open("moves.log")?, slots: open("slots.log")?, caps: open("caps.jsonl")?, archive };
    REC.set(r).map_err(|_| anyhow::anyhow!("recorder already set"))?;
    Ok(())
}

pub fn get() -> Option<&'static Recorder> { REC.get() }

impl Recorder {
    pub fn line(w: &Mutex<BufWriter<std::fs::File>>, s: &str) { let mut w = w.lock().unwrap(); let _ = w.write_all(s.as_bytes()); let _ = w.write_all(b"\n"); }

    /// one entries message of the archived feed
    pub fn archive(&self, feed: u16, slot: u64, t: u64, bytes: &[u8]) {
        let Some((id, w, _)) = &self.archive else { return };
        if *id != feed { return; }
        let mut g = w.lock().unwrap();
        let Some(w) = g.as_mut() else { return };
        let mut head = [0u8; 20];
        head[..8].copy_from_slice(&slot.to_le_bytes());
        head[8..16].copy_from_slice(&t.to_le_bytes());
        head[16..].copy_from_slice(&(bytes.len() as u32).to_le_bytes());
        if w.write_all(&head).and_then(|_| w.write_all(bytes)).is_err() { *g = None; }
    }

    pub fn flush(&self) {
        for w in [&self.txarr, &self.rivals, &self.exec, &self.moves, &self.slots, &self.caps] { let _ = w.lock().unwrap().flush(); }
        if let Some((_, w, _)) = &self.archive { if let Some(w) = w.lock().unwrap().as_mut() { let _ = w.flush(); } }
    }

    /// end of run: flush everything and let zstd finish its frame
    pub fn finish(&self) {
        self.flush();
        if let Some((_, w, child)) = &self.archive {
            drop(w.lock().unwrap().take());
            if let Some(mut c) = child.lock().unwrap().take() { let _ = c.wait(); }
        }
    }
}

/// The error of an executed transaction from its bincode TransactionError: `ix{i}:custom:0x{code}`, `ix{i}:ie{variant}`
/// or `tx{variant}`.
pub fn tx_error(b: &[u8]) -> String {
    let u32_at = |i: usize| b.get(i..i + 4).map(|s| u32::from_le_bytes(s.try_into().unwrap()));
    match u32_at(0) {
        Some(8) => {
            let ix = b.get(4).copied().unwrap_or(0);
            match u32_at(5) {
                Some(25) => format!("ix{ix}:custom:0x{:x}", u32_at(9).unwrap_or(0)),
                Some(v) => format!("ix{ix}:ie{v}"),
                None => format!("ix{ix}"),
            }
        }
        Some(v) => format!("tx{v}"),
        None => "?".into(),
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn tx_error_decodes_custom_codes() {
        // InstructionError(3, Custom(0x4e580002))
        let mut b = 8u32.to_le_bytes().to_vec();
        b.push(3);
        b.extend(25u32.to_le_bytes());
        b.extend(0x4e58_0002u32.to_le_bytes());
        assert_eq!(super::tx_error(&b), "ix3:custom:0x4e580002");
        assert_eq!(super::tx_error(&6u32.to_le_bytes()), "tx6");
    }
}
