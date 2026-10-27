package core

import (
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	LoadChunk = 512 * 1024      // initial load: bytes per file per step (the Python version's chunk; the minutes of the P&L line depend on it)
	TickBytes = 4 * 1024 * 1024 // live: bytes per file per refresh
)

var runRX = regexp.MustCompile(`^dip_(ams_)?r(\d+)\.jsonl$`)

// RunInfo: (region, run) from a run file name: dip_ams_rN -> AMS, dip_rN -> FRA; ok=false otherwise.
func RunInfo(path string) (string, int, bool) {
	m := runRX.FindStringSubmatch(filepath.Base(path))
	if m == nil {
		return "", 0, false
	}
	n, err := strconv.Atoi(m[2])
	if err != nil {
		return "", 0, false
	}
	if m[1] != "" {
		return "AMS", n, true
	}
	return "FRA", n, true
}

// PyJoin is os.path.join(a, b) (no cleaning, like Python).
func PyJoin(a string, parts ...string) string {
	out := a
	for _, b := range parts {
		switch {
		case strings.HasPrefix(b, "/"):
			out = b
		case out == "" || strings.HasSuffix(out, "/"):
			out += b
		default:
			out += "/" + b
		}
	}
	return out
}

// Source is a run's two files and the model they feed.
type Source struct {
	JSONL, Log  string
	Region      string
	Run         int
	HasRun      bool
	FailBuyFee  int64
	LogKeep     int
	Model       *Model
	TJ, TL      *Tail
	Loaded      bool
	Resets      int
	tLastGrowth time.Time
}

// NewSource: log "" = the .jsonl's name with .log.
func NewSource(jsonl, log string, failBuyFee int64, logKeep int) *Source {
	if log == "" {
		if strings.HasSuffix(jsonl, ".jsonl") {
			log = jsonl[:len(jsonl)-6] + ".log"
		} else {
			log = jsonl + ".log"
		}
	}
	reg, run, ok := RunInfo(jsonl)
	return &Source{JSONL: jsonl, Log: log, Region: reg, Run: run, HasRun: ok, FailBuyFee: failBuyFee, LogKeep: logKeep,
		Model: NewModel(failBuyFee, logKeep), TJ: NewTail(jsonl), TL: NewTail(log), tLastGrowth: time.Now()}
}

// TotalBytes: both files' sizes.
func (s *Source) TotalBytes() int64 {
	var n int64
	if s.TJ.Stat() {
		n += s.TJ.Size
	}
	if s.TL.Stat() {
		n += s.TL.Size
	}
	return n
}

// DoneBytes: bytes read so far.
func (s *Source) DoneBytes() int64 { return s.TJ.Off + s.TL.Off }

// Pending: unread bytes in either file.
func (s *Source) Pending() bool { return s.TJ.Pending() > 0 || s.TL.Pending() > 0 }

// Step reads up to maxBytes from each file (records first, then the log); returns the bytes read.
func (s *Source) Step(maxBytes int64) int64 {
	n0 := s.DoneBytes()
	lj := s.TJ.Read(maxBytes)
	if s.TJ.Reset || s.TL.Reset {
		s.reset()
		return 0
	}
	if len(lj) > 0 {
		s.Model.FeedJSONL(lj)
	}
	ll := s.TL.Read(maxBytes)
	if s.TJ.Reset || s.TL.Reset {
		s.reset()
		return 0
	}
	if len(ll) > 0 {
		s.Model.LiveLog = s.Loaded
		s.Model.FeedLog(ll)
	}
	n := s.DoneBytes() - n0
	if n > 0 {
		s.tLastGrowth = time.Now()
	} else if len(s.TJ.Buf) > 0 && time.Since(s.tLastGrowth) > 3*time.Second {
		if b := s.TJ.FlushPartialJSON(); b != nil { // a record whose newline never came (an engine killed mid-write)
			s.Model.FeedJSONL([][]byte{b})
		}
	}
	return n
}

func (s *Source) reset() {
	s.Resets++
	s.TJ = NewTail(s.JSONL)
	s.TL = NewTail(s.Log)
	s.Model = NewModel(s.FailBuyFee, s.LogKeep)
	s.Loaded = false
}

// LoadAll reads both files to their end in chunks; duty > 0 sleeps that multiple of each chunk's work time
// (yielding the CPU to the engine). progress (may be nil) is called after each chunk.
func (s *Source) LoadAll(chunk int64, duty float64, progress func(*Source)) {
	for {
		t0 := time.Now()
		n := s.Step(chunk)
		if progress != nil {
			progress(s)
		}
		if n == 0 && !s.Pending() {
			break
		}
		if duty > 0 {
			d := time.Duration(float64(time.Since(t0)) * duty)
			if d < time.Millisecond {
				d = time.Millisecond
			}
			time.Sleep(d)
		}
	}
	s.Loaded = true
}

// Exists: either file is there.
func (s *Source) Exists() bool {
	_, e1 := os.Stat(s.JSONL)
	_, e2 := os.Stat(s.Log)
	return e1 == nil || e2 == nil
}
