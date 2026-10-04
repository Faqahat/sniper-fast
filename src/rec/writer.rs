//! The writer threads: one per class (MEASUREMENT §1.2-§1.3). Each owns its streams' files: it encodes records (JSON,
//! text or binary), cuts zstd frames (every `flush_ms`, every 4 MiB of raw data, and on the core writer whenever its
//! queue is empty), rotates files (`rotate_mb` raw, `rotate_min`), writes each file's schema header first, and keeps
//! the manifest's per-file numbers. The slow class writes plain files, one write per line.
//!
//! Faults (review F1, F2, F15):
//! - A record counts as written only once its bytes are on disk. An open, compression or write error is counted per
//!   stream with the records it lost ([`Recorder::io_error`]: a core stream's is a core loss, status.jsonl's stops the
//!   segment). A frame that was cut short is cut off the file again, so the frames after it stay readable; a file that
//!   could not be opened is tried again (at most once a second), its header first.
//! - Each record's encoding (and each task) runs under `catch_unwind`: one that panics is counted and left out. A panic
//!   anywhere else ends the thread's loop: its files are closed as far as possible, the recorder is told
//!   ([`Recorder::writer_died`]), and what is left in its queue is counted as dropped.
//! - What arrives after the close drained the queue is counted as late.
use super::{Class, Ctl, FileState, FileStat, Format, Msg, Record, Recorder, Spec, S, FRAME_MAX};
use crate::feeds::clock::now_ns;
use crossbeam_channel::{Receiver, RecvTimeoutError, Sender};
use serde_json::json;
use sha2::Digest;
use std::io::{Seek, SeekFrom, Write};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::PathBuf;
use std::sync::atomic::Ordering::Relaxed;
use std::sync::Arc;
use std::time::{Duration, Instant};

/// a file that could not be opened is tried again after this long
const REOPEN_AFTER: Duration = Duration::from_secs(1);

pub(super) fn run(rec: Arc<Recorder>, class: Class, rx: Receiver<Ctl>, _done: Sender<()>) {
    crate::runtime::nice_this_thread(crate::runtime::BG_NICE);
    pin(&rec.cfg.writer_cpus);
    let comp = zstd::bulk::Compressor::new(rec.cfg.zstd_level).ok();
    let mut w = Writer { rec: rec.clone(), series: (0..rec.n_streams()).map(|_| None).collect(), states: (0..rec.n_streams()).map(|_| None).collect(), comp,
        out: Vec::new(), scratch: Vec::new() };
    let res = catch_unwind(AssertUnwindSafe(|| run_loop(&mut w, &rec, class, &rx)));
    let died = res.is_err();
    if let Err(p) = res {
        // save what can be saved, then say so
        let _ = catch_unwind(AssertUnwindSafe(|| w.close_all()));
        rec.writer_died(class, &format!("panicked: {}", panic_text(&p)));
    }
    // what is still queued will not be written: late after a close (review F15), dropped when the writer died
    while let Ok(c) = rx.try_recv() {
        if let Ctl::Rec(m) = c {
            let st = rec.st(m.s);
            let q = &rec.queues[st.spec.queue as usize];
            q.depth.fetch_sub(1, Relaxed);
            q.bytes.fetch_sub(m.size, Relaxed);
            if died { rec.on_drop(m.s, None, "writer gone"); } else { st.late.fetch_add(1, Relaxed); }
        }
    }
}

fn run_loop(w: &mut Writer, rec: &Recorder, class: Class, rx: &Receiver<Ctl>) {
    let flush = Duration::from_millis(rec.cfg.flush_ms.max(1));
    // the core streams' records reach the disk at once (a few a second: tiny frames cost nothing), so a hard kill loses
    // none that were taken (review F4)
    let eager = class == Class::Core;
    let mut next = Instant::now() + flush;
    loop {
        let got = rx.recv_timeout(next.saturating_duration_since(Instant::now()));
        // test hook (a stalled writer): what it took stays counted in the queue until it goes on
        while rec.stalled(class) { std::thread::sleep(Duration::from_millis(1)); }
        if rec.crash_requested(class) { panic!("test hook: the {} writer crashes", class.as_str()); }
        if got.is_ok() { rec.progress[class.idx()].fetch_add(1, Relaxed); }
        match got {
            Ok(Ctl::Rec(m)) => { w.record(m); if eager && rx.is_empty() { w.flush_pending(); } }
            Ok(Ctl::Sync(ack)) => { w.flush_all(); let _ = ack.send(()); }
            Ok(Ctl::Open(s, t, ack)) => { let r = w.open_now(s, t); if let Some(a) = ack { let _ = a.send(r); } }
            Ok(Ctl::State(s, st)) => w.set_state(s, st),
            Ok(Ctl::Close) => {
                // what was emitted while the close began
                while let Ok(c) = rx.try_recv() {
                    match c {
                        Ctl::Rec(m) => w.record(m),
                        Ctl::Sync(a) => { let _ = a.send(()); }
                        Ctl::Open(s, t, a) => { let r = w.open_now(s, t); if let Some(a) = a { let _ = a.send(r); } }
                        Ctl::State(s, st) => w.set_state(s, st),
                        Ctl::Close => {}
                    }
                }
                break;
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }
        if Instant::now() >= next { w.tick(); next = Instant::now() + flush; }
    }
    w.close_all();
}

fn panic_text(p: &Box<dyn std::any::Any + Send>) -> String {
    p.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.downcast_ref::<String>().cloned()).unwrap_or_else(|| "?".into())
}

/// pin this thread to `cpus` (`[record] writer_cpus`; empty = anywhere)
fn pin(cpus: &[usize]) {
    if cpus.is_empty() { return; }
    // SAFETY: a zeroed cpu_set_t is a valid empty set; CPU_SET bounds-checks the index
    unsafe {
        let mut set: libc::cpu_set_t = std::mem::zeroed();
        for &c in cpus { if c < 1024 { libc::CPU_SET(c, &mut set); } }
        let _ = libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &set);
    }
}

struct Writer {
    rec: Arc<Recorder>,
    series: Vec<Option<Series>>,
    /// per-file encoder state by stream (review F16)
    states: Vec<Option<Box<dyn FileState>>>,
    comp: Option<zstd::bulk::Compressor<'static>>,
    out: Vec<u8>,
    scratch: Vec<u8>,
}

/// One stream's current file
struct Series {
    spec: Spec,
    path: PathBuf,
    file: Option<std::fs::File>,
    /// the open failed: the error, and when to try again
    open_err: Option<(String, Instant)>,
    file_seq: u32,
    opened: Instant,
    /// the zstd frame being built (compressed formats)
    raw: Vec<u8>,
    /// records in `raw`, not on disk yet
    pending: u64,
    /// the file's header (and per-file state preamble) until it is on disk: sent again after a failed write
    preamble: Option<Vec<u8>>,
    stat: FileStat,
    hasher: sha2::Sha256,
}

impl Series {
    /// open the file (a compressed file is created afresh, a plain one appended to). True when the file is new (empty)
    fn try_open(&mut self, rec: &Recorder, s: S) -> bool {
        let r = if self.spec.format.plain() { std::fs::OpenOptions::new().create(true).append(true).open(&self.path) } else { std::fs::File::create(&self.path) };
        match r {
            Ok(f) => {
                let fresh = f.metadata().map_or(true, |m| m.len() == 0);
                self.file = Some(f);
                self.open_err = None;
                fresh
            }
            Err(e) => {
                let msg = e.to_string();
                rec.io_error(s, "open", &msg, 0);
                self.open_err = Some((msg, Instant::now() + REOPEN_AFTER));
                true
            }
        }
    }

    /// the file is open, or opens now (a failed open is tried again at most once a second)
    fn ready(&mut self, rec: &Recorder, s: S) -> bool {
        if self.file.is_some() { return true; }
        if self.open_err.as_ref().is_some_and(|e| Instant::now() < e.1) { return false; }
        let fresh = self.try_open(rec, s);
        // a plain file someone else created meanwhile gets no header
        if self.file.is_some() && self.spec.format.plain() && !fresh { self.preamble = None; }
        self.file.is_some()
    }

    /// one plain write (a line, with the header first if it is still owed). Err: (operation, error)
    fn write_plain(&mut self, rec: &Recorder, s: S, bytes: &[u8]) -> Result<(), (&'static str, String)> {
        if !self.ready(rec, s) { return Err(("open", self.open_err.as_ref().map_or_else(String::new, |e| e.0.clone()))); }
        let f = self.file.as_mut().expect("ready");
        if let Some(pre) = self.preamble.take() {
            if let Err(e) = f.write_all(&pre) { self.preamble = Some(pre); return Err(("write", e.to_string())); }
            self.stat.bytes_written += pre.len() as u64;
        }
        f.write_all(bytes).map_err(|e| ("write", e.to_string()))?;
        self.stat.bytes_written += bytes.len() as u64;
        Ok(())
    }

    /// after a frame that was not written: its records are gone; the header, if still owed, goes with the next frame
    fn reset_raw(&mut self) {
        self.raw.clear();
        self.pending = 0;
        if let Some(p) = &self.preamble { self.raw.extend_from_slice(p); }
    }
}

impl Writer {
    fn record(&mut self, m: Msg) {
        let rec = self.rec.clone();
        let st = rec.st(m.s);
        let q = &rec.queues[st.spec.queue as usize];
        q.depth.fetch_sub(1, Relaxed);
        if m.size > 0 { q.bytes.fetch_sub(m.size, Relaxed); }
        let r = match m.r {
            Record::Task(f) => { if catch_unwind(AssertUnwindSafe(f)).is_err() { rec.encode_failed(m.s, "a task panicked"); } return; }
            r => r,
        };
        if self.series[m.s.0 as usize].is_none() { let x = self.open(m.s, 0, now_ns()); self.series[m.s.0 as usize] = Some(x); }
        if let Some(g) = m.gap { for (first, n) in g { self.write_one(m.s, gap_record(&st.spec, first, n)); } }
        self.write_one(m.s, r);
    }

    /// a new file of stream `s` (its header stamped `t`): the header and the per-file state's preamble come first
    fn open(&mut self, s: S, file_seq: u32, t: u64) -> Series {
        let spec = self.rec.spec(s).clone();
        let name = spec.file_name(file_seq);
        let stat = FileStat { path: name.clone(), ..Default::default() };
        self.rec.st(s).files.lock().unwrap_or_else(|e| e.into_inner()).push(stat.clone());
        let mut x = Series { path: self.rec.dir.join(&name), spec, file: None, open_err: None, file_seq, opened: Instant::now(), raw: Vec::new(), pending: 0,
            preamble: None, stat, hasher: sha2::Sha256::new() };
        let fresh = x.try_open(&self.rec, s);
        // the schema header (§1.3): a plain file gets one only when it is new (run.log never)
        let mut pre = self.header(s, &x.spec, file_seq, t).unwrap_or_default();
        if let Some(st) = self.states[s.0 as usize].as_mut() {
            if catch_unwind(AssertUnwindSafe(|| st.on_new_file(file_seq, &mut pre))).is_err() { self.rec.encode_failed(s, "a per-file state's on_new_file panicked"); }
        }
        if !pre.is_empty() && (!x.spec.format.plain() || fresh) {
            x.stat.bytes_raw += pre.len() as u64;
            if x.spec.format.plain() {
                x.preamble = Some(pre);
                if x.file.is_some() { if let Err((op, e)) = x.write_plain(&self.rec, s, &[]) { self.rec.io_error(s, op, &e, 0); } }
            } else {
                x.raw.extend_from_slice(&pre);
                x.preamble = Some(pre);
            }
        }
        x
    }

    /// `Ctl::Open`: the stream's file now (its first file, if it has none yet)
    fn open_now(&mut self, s: S, t: u64) -> Result<(), String> {
        let i = s.0 as usize;
        if self.series[i].is_none() { let x = self.open(s, 0, t); self.series[i] = Some(x); }
        let x = self.series[i].as_mut().expect("opened");
        if x.ready(&self.rec, s) { Ok(()) } else { Err(x.open_err.as_ref().map_or_else(|| "not open".to_string(), |e| e.0.clone())) }
    }

    fn set_state(&mut self, s: S, mut st: Box<dyn FileState>) {
        let i = s.0 as usize;
        if let Some(x) = self.series[i].as_mut() {
            // the file is already open: the state starts with it
            let mut pre = Vec::new();
            if catch_unwind(AssertUnwindSafe(|| st.on_new_file(x.file_seq, &mut pre))).is_err() { self.rec.encode_failed(s, "a per-file state's on_new_file panicked"); }
            x.stat.bytes_raw += pre.len() as u64;
            x.raw.extend_from_slice(&pre);
            if let Some(p) = x.preamble.as_mut() { p.extend_from_slice(&pre); }
        }
        self.states[i] = Some(st);
    }

    /// the file's first record (§1.3)
    fn header(&self, s: S, spec: &Spec, file_seq: u32, t: u64) -> Option<Vec<u8>> {
        let extra = &self.rec.st(s).header_extra;
        match spec.format {
            Format::PlainText => None,
            Format::Jsonl | Format::PlainJsonl => {
                let mut h = json!({ "schema": spec.schema, "run": self.rec.run, "file_seq": file_seq, "started_ns": t, "producer": self.rec.producer });
                for (k, v) in extra { h[k] = json!(v); }
                let mut b = serde_json::to_vec(&h).unwrap_or_default();
                b.push(b'\n');
                Some(b)
            }
            Format::Text => {
                let clean = |v: &str| v.replace(char::is_whitespace, "_");
                let mut l = format!("# {} run={} file_seq={file_seq} started_ns={t} producer={}", spec.schema, clean(&self.rec.run), clean(&self.rec.producer));
                for (k, v) in extra { l.push_str(&format!(" {k}={}", clean(v))); }
                l.push('\n');
                Some(l.into_bytes())
            }
            Format::Bin { magic, format } => {
                let mut h = json!({ "schema": spec.schema, "run": self.rec.run, "file_seq": file_seq, "started_ns": t, "producer": self.rec.producer });
                for (k, v) in extra { h[k] = json!(v); }
                let j = serde_json::to_vec(&h).unwrap_or_default();
                let mut b = magic.to_vec();
                b.extend(format.to_le_bytes());
                b.extend((j.len() as u16).to_le_bytes());
                b.extend(j);
                Some(b)
            }
        }
    }

    fn write_one(&mut self, s: S, r: Record) {
        let rotate_bytes = (self.rec.cfg.rotate_mb * (1 << 20) as f64) as u64;
        let i = s.0 as usize;
        let Some(mut x) = self.series[i].take() else { return };
        let t = now_ns();
        let plain = x.spec.format.plain();
        let lines = x.spec.format.lines();
        let buf = if plain { self.scratch.clear(); &mut self.scratch } else { &mut x.raw };
        let start = buf.len();
        let state = self.states[i].as_mut();
        // the record's encoding: a panic (or a stateful record without its state) leaves it out, counted
        let n = match catch_unwind(AssertUnwindSafe(|| encode(r, &mut *buf, state))) {
            Ok(Ok(n)) => n,
            Ok(Err(why)) => { buf.truncate(start); self.rec.encode_failed(s, why); self.series[i] = Some(x); return; }
            Err(p) => { buf.truncate(start); self.rec.encode_failed(s, &format!("a record's encoder panicked: {}", panic_text(&p))); self.series[i] = Some(x); return; }
        };
        if n == 0 { buf.truncate(start); self.series[i] = Some(x); return; }
        if lines { buf.push(b'\n'); }
        x.stat.bytes_raw += (buf.len() - start) as u64;
        x.stat.first_t_ns.get_or_insert(t);
        x.stat.last_t_ns = Some(t);
        if plain {
            let line = std::mem::take(&mut self.scratch);
            match x.write_plain(&self.rec, s, &line) {
                Ok(()) => { x.stat.records += n; self.rec.st(s).written_records.fetch_add(n, Relaxed); }
                Err((op, e)) => self.rec.io_error(s, op, &e, n),
            }
            self.scratch = line;
            self.series[i] = Some(x);
            return;
        }
        x.pending += n;
        if x.raw.len() >= FRAME_MAX { self.end_frame(s, &mut x); }
        if !x.spec.single && x.stat.bytes_raw >= rotate_bytes { x = self.rotate(s, x); }
        self.series[i] = Some(x);
    }

    /// compress what is pending into one zstd frame and write it; its records count as written once it is on disk
    fn end_frame(&mut self, s: S, x: &mut Series) {
        if x.raw.is_empty() { return; }
        let rec = self.rec.clone();
        let n = x.pending;
        if !x.ready(&rec, s) {
            // the file cannot be opened (the open's error was counted when it was tried): these records are lost
            rec.st(s).io_lost.fetch_add(n, Relaxed);
            x.reset_raw();
            return;
        }
        self.out.clear();
        self.out.reserve(zstd::zstd_safe::compress_bound(x.raw.len()));
        let done = match self.comp.as_mut() { Some(c) => c.compress_to_buffer(&x.raw, &mut self.out).map(|_| ()).map_err(|e| e.to_string()), None => Err("no zstd compressor".into()) };
        if let Err(e) = done { rec.io_error(s, "compress", &e, n); x.reset_raw(); return; }
        let f = x.file.as_mut().expect("ready");
        match f.write_all(&self.out) {
            Ok(()) => {
                x.hasher.update(&self.out);
                x.stat.bytes_written += self.out.len() as u64;
                x.stat.records += n;
                let st = rec.st(s);
                st.written_bytes.fetch_add(self.out.len() as u64, Relaxed);
                st.written_records.fetch_add(n, Relaxed);
                x.pending = 0;
                x.preamble = None;
                x.raw.clear();
            }
            Err(e) => {
                // a frame cut short would hide every later frame from a reader: back to the last complete one
                let _ = f.set_len(x.stat.bytes_written);
                let _ = f.seek(SeekFrom::Start(x.stat.bytes_written));
                rec.io_error(s, "write", &e.to_string(), n);
                x.reset_raw();
            }
        }
        self.publish(s, x);
    }

    /// the manifest's copy of the current file's numbers
    fn publish(&self, s: S, x: &Series) {
        let mut files = self.rec.st(s).files.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(last) = files.iter_mut().rev().find(|f| f.path == x.stat.path) { *last = x.stat.clone(); }
    }

    fn close_file(&mut self, s: S, x: &mut Series) {
        self.end_frame(s, x);
        if let Some(f) = x.file.take() { let _ = f.sync_data(); }
        x.stat.closed = true;
        // plain files stay open for appends by other writers (control.rs, the panic hook): no hash
        if !x.spec.format.plain() { x.stat.sha256 = Some(crate::provenance::hex(&std::mem::take(&mut x.hasher).finalize())); }
        self.publish(s, x);
    }

    fn rotate(&mut self, s: S, mut x: Series) -> Series {
        self.close_file(s, &mut x);
        self.open(s, x.file_seq + 1, now_ns())
    }

    /// every `flush_ms`: end the frames, rotate files that are `rotate_min` old
    fn tick(&mut self) {
        let age = Duration::from_secs(self.rec.cfg.rotate_min.max(1) * 60);
        for i in 0..self.series.len() {
            let s = S(i as u16);
            let Some(mut x) = self.series[i].take() else { continue };
            if x.spec.format.plain() { self.publish(s, &x); self.series[i] = Some(x); continue; }
            self.end_frame(s, &mut x);
            if !x.spec.single && x.stat.records > 0 && x.opened.elapsed() >= age { x = self.rotate(s, x); }
            self.series[i] = Some(x);
        }
    }

    /// end the frames that hold records (the core writer, whenever its queue is empty)
    fn flush_pending(&mut self) {
        for i in 0..self.series.len() {
            if !self.series[i].as_ref().is_some_and(|x| x.pending > 0) { continue; }
            let mut x = self.series[i].take().expect("checked");
            self.end_frame(S(i as u16), &mut x);
            self.series[i] = Some(x);
        }
    }

    fn flush_all(&mut self) {
        for i in 0..self.series.len() {
            let Some(mut x) = self.series[i].take() else { continue };
            self.end_frame(S(i as u16), &mut x);
            self.publish(S(i as u16), &x);
            self.series[i] = Some(x);
        }
    }

    fn close_all(&mut self) {
        for i in 0..self.series.len() {
            let Some(mut x) = self.series[i].take() else { continue };
            self.close_file(S(i as u16), &mut x);
            self.series[i] = Some(x);
        }
    }
}

/// a record's bytes into `buf`: the records it holds (a task is not a record)
fn encode(r: Record, buf: &mut Vec<u8>, state: Option<&mut Box<dyn FileState>>) -> Result<u64, &'static str> {
    match r {
        Record::Json(v) => { let _ = serde_json::to_writer(&mut *buf, &v); Ok(1) }
        Record::Line(l) => { buf.extend_from_slice(l.as_bytes()); Ok(1) }
        Record::Enc(f) => { f(buf); Ok(1) }
        Record::EncN(n, f) => { f(buf); Ok(n as u64) }
        Record::Bin(b) => { buf.extend_from_slice(&b); Ok(1) }
        Record::Stateful(f) => match state { Some(st) => { f(st.as_any(), buf); Ok(1) } None => Err("a stateful record with no per-file state installed") },
        Record::Task(f) => { f(); Ok(0) }
    }
}

/// A replay stream's GAP record (MEASUREMENT §4.12 accounts kind 6, §4.13 journal kind 12); a JSON stream gets a
/// `{"gap": ...}` line
fn gap_record(spec: &Spec, first: u64, n: u64) -> Record {
    match spec.format {
        Format::Bin { magic, .. } if magic == super::ACCOUNTS_MAGIC => {
            let mut b = vec![6u8];
            b.extend(16u32.to_le_bytes());
            b.extend(first.to_le_bytes());
            b.extend(n.to_le_bytes());
            Record::Bin(b)
        }
        Format::Bin { magic, .. } if magic == super::JOURNAL_MAGIC => {
            // u8 kind | u32 body_len (the body only) | u64 seq | u64 t_engine_ns | body: u64 first_lost_seq | u64 n_lost
            let mut b = vec![12u8];
            b.extend(16u32.to_le_bytes());
            b.extend(first.to_le_bytes());
            b.extend(now_ns().to_le_bytes());
            b.extend(first.to_le_bytes());
            b.extend(n.to_le_bytes());
            Record::Bin(b)
        }
        _ => Record::Json(json!({ "gap": { "first_lost_seq": first, "n_lost": n } })),
    }
}
