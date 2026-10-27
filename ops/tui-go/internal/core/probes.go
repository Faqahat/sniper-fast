package core

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// RealPath is os.path.realpath: absolute, symlinks resolved as far as the path exists.
func RealPath(p string) string {
	a, err := filepath.Abs(p)
	if err != nil {
		return p
	}
	if r, err := filepath.EvalSymlinks(a); err == nil {
		return r
	}
	dir, base := filepath.Split(a)
	if dir != "" && dir != a {
		return filepath.Join(RealPath(strings.TrimSuffix(dir, "/")), base)
	}
	return a
}

// ------------------------------------------------------------------------------------------------------- engine

// SafeFlags / SafeSwitches: the only command-line items of the engine that dipmon keeps (numbers and names; never
// paths, URLs or keys).
var SafeFlags = map[string]bool{"--minutes": true, "--max-loss-sol": true, "--cu-limit": true, "--cu-price-micro": true,
	"--spend-lamports": true, "--dip-tier": true, "--dip-tp": true, "--dip-sl": true, "--dip-hold-slots": true, "--dip-guard": true,
	"--dip-m2-mode": true, "--presend-live-size-sol": true, "--presend-live-k": true, "--presend-live-max-fills": true,
	"--presend-live-fee-budget-sol": true, "--presend-live-routes": true, "--presend-live-quiet-stop": true,
	"--presend-live-quiet-skip": true, "--presend-live-quiet-warmup-min": true, "--sell-fanout": true, "--route-by-client": true,
	"--skip-clients": true, "--max-buys": true, "--max-inflight": true}

var SafeSwitches = map[string]bool{"--presend-live": true, "--presend-live-dry": true, "--presend-shadow": true,
	"--nonce-fanout": true, "--dip-near-leaders": true, "--presend-live-quiet-preload": true, "--dip-dev-list": true,
	"--dip-m2": true, "--live": true}

const clkTck = 100 // USER_HZ on Linux

// Engine is the engine process of this run, found by its --dip-log in /proc/*/cmdline (read-only).
type Engine struct {
	mu      sync.Mutex
	Target  string
	Enabled bool
	PID     int
	Flags   map[string]string // value "1" for a switch
	Build   string
	Seen    bool
	GoneAt  time.Time
	CPU     float64
	HasCPU  bool
	RSS     int64
	Threads int64
	Start   float64 // unix seconds, 0 = unknown
	last    struct {
		t     time.Time
		ticks int64
		ok    bool
	}
	scanT time.Time
	btime int64
}

// NewEngine for a run file ("" = disabled target).
func NewEngine(jsonl string, enabled bool) *Engine {
	e := &Engine{Flags: map[string]string{}}
	if jsonl != "" {
		e.Target = RealPath(jsonl)
	}
	if st, err := os.Stat("/proc"); err == nil && st.IsDir() {
		e.Enabled = enabled
	}
	if b, err := os.ReadFile("/proc/stat"); err == nil {
		for _, l := range strings.Split(string(b), "\n") {
			if strings.HasPrefix(l, "btime") {
				f := strings.Fields(l)
				if len(f) > 1 {
					e.btime, _ = strconv.ParseInt(f[1], 10, 64)
				}
			}
		}
	}
	return e
}

// EngineProc: a process with --dip-log.
type EngineProc struct {
	PID  int
	Log  string
	Args []string
}

func dipLogOf(pid int) (string, []string) {
	raw, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/cmdline")
	if err != nil || !bytes.Contains(raw, []byte("--dip-log")) {
		return "", nil
	}
	var args []string
	for _, a := range bytes.Split(raw, []byte{0}) {
		if len(a) > 0 {
			args = append(args, decodeReplace(a))
		}
	}
	idx := -1
	for i, a := range args {
		if a == "--dip-log" {
			idx = i
			break
		}
	}
	if idx < 0 || idx+1 >= len(args) {
		return "", nil
	}
	p := args[idx+1]
	if !filepath.IsAbs(p) {
		if cwd, err := os.Readlink("/proc/" + strconv.Itoa(pid) + "/cwd"); err == nil {
			p = PyJoin(cwd, p)
		}
	}
	return RealPath(p), args
}

// FindEngines lists every process carrying --dip-log (never this one).
func FindEngines() []EngineProc {
	ents, err := os.ReadDir("/proc")
	if err != nil {
		return nil
	}
	me := os.Getpid()
	var out []EngineProc
	for _, d := range ents {
		pid, err := strconv.Atoi(d.Name())
		if err != nil || pid == me {
			continue
		}
		if p, args := dipLogOf(pid); p != "" {
			out = append(out, EngineProc{PID: pid, Log: p, Args: args})
		}
	}
	return out
}

var rxBuild = regexp.MustCompile(`(dip\d+)`)
var rxBuildArg = regexp.MustCompile(`snipe_engine\w*?(dip\d+)`)

// Scan looks for the engine (every 10 s unless forced).
func (e *Engine) Scan(force bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.scanLocked(force)
}

func (e *Engine) scanLocked(force bool) {
	if !e.Enabled || e.Target == "" {
		return
	}
	if !force && time.Since(e.scanT) < 10*time.Second {
		return
	}
	e.scanT = time.Now()
	for _, p := range FindEngines() {
		if p.Log == e.Target {
			e.adopt(p.PID, p.Args)
			return
		}
	}
}

func (e *Engine) adopt(pid int, args []string) {
	e.PID = pid
	e.Seen = true
	e.GoneAt = time.Time{}
	e.last.ok = false
	exe := ""
	if len(args) > 0 {
		exe = filepath.Base(args[0])
	}
	m := rxBuild.FindStringSubmatch(exe)
	if m == nil {
		if l, err := os.Readlink("/proc/" + strconv.Itoa(pid) + "/exe"); err == nil {
			m = rxBuild.FindStringSubmatch(filepath.Base(l))
		}
	}
	if m == nil {
		for _, a := range args {
			if strings.Contains(a, "snipe_engine") {
				m = rxBuildArg.FindStringSubmatch(a)
				break
			}
		}
	}
	switch {
	case m != nil:
		e.Build = m[1]
	case exe != "":
		e.Build = RuneSlice(exe, 20)
	default:
		e.Build = ""
	}
	fl := map[string]string{}
	for i, a := range args {
		if SafeFlags[a] && i+1 < len(args) {
			fl[a] = RuneSlice(args[i+1], 300)
		} else if SafeSwitches[a] {
			fl[a] = "1"
		}
	}
	e.Flags = fl
}

// Sample reads the engine's CPU / RSS / threads (or notices it is gone, and rescans).
func (e *Engine) Sample() {
	e.mu.Lock()
	defer e.mu.Unlock()
	if !e.Enabled {
		return
	}
	if e.PID == 0 {
		e.scanLocked(false)
		return
	}
	stat, err1 := os.ReadFile("/proc/" + strconv.Itoa(e.PID) + "/stat")
	statm, err2 := os.ReadFile("/proc/" + strconv.Itoa(e.PID) + "/statm")
	var rest, sm []string
	if err1 == nil && err2 == nil {
		if i := bytes.LastIndexByte(stat, ')'); i >= 0 {
			rest = strings.Fields(string(stat[i+1:]))
		}
		sm = strings.Fields(string(statm))
	}
	if err1 != nil || err2 != nil || len(rest) < 20 || len(sm) < 2 {
		e.PID = 0
		e.HasCPU = false
		e.GoneAt = time.Now()
		e.scanLocked(true)
		return
	}
	ut, _ := strconv.ParseInt(rest[11], 10, 64)
	stt, _ := strconv.ParseInt(rest[12], 10, 64)
	ticks := ut + stt
	now := time.Now()
	if e.last.ok {
		dtw := now.Sub(e.last.t).Seconds()
		if dtw > 0.2 {
			e.CPU, e.HasCPU = float64(ticks-e.last.ticks)/clkTck/dtw*100, true
			e.last.t, e.last.ticks = now, ticks
		}
	} else {
		e.last.t, e.last.ticks, e.last.ok = now, ticks, true
	}
	e.Threads, _ = strconv.ParseInt(rest[17], 10, 64)
	pages, _ := strconv.ParseInt(sm[1], 10, 64)
	e.RSS = pages * int64(os.Getpagesize())
	if e.btime > 0 {
		st, _ := strconv.ParseInt(rest[19], 10, 64)
		s := float64(e.btime) + float64(st)/clkTck
		nowf := float64(now.UnixNano()) / 1e9
		if nowf-s > 0 && nowf-s < 90*86400 {
			e.Start = s
		} else {
			e.Start = 0
		}
	}
}

// Alive: an engine process is attached.
func (e *Engine) Alive() bool {
	if e == nil {
		return false
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.PID != 0
}

// EngineInfo is a copy of the probe's fields (safe to read without the lock).
type EngineInfo struct {
	Target  string
	Enabled bool
	PID     int
	Flags   map[string]string
	Build   string
	Seen    bool
	GoneAt  time.Time
	CPU     float64
	HasCPU  bool
	RSS     int64
	Threads int64
	Start   float64
}

// Snapshot copies the probe's fields.
func (e *Engine) Snapshot() EngineInfo {
	if e == nil {
		return EngineInfo{Flags: map[string]string{}}
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	c := EngineInfo{Target: e.Target, Enabled: e.Enabled, PID: e.PID, Build: e.Build, Seen: e.Seen, GoneAt: e.GoneAt, CPU: e.CPU,
		HasCPU: e.HasCPU, RSS: e.RSS, Threads: e.Threads, Start: e.Start, Flags: map[string]string{}}
	for k, v := range e.Flags {
		c.Flags[k] = v
	}
	return c
}

// ------------------------------------------------------------------------------------------------------- price

// Price is SOL/USD: Binance, else CoinGecko, every 60 s in a goroutine (5 s timeouts); the last price cached in
// /tmp/dipmon-solusd-<uid>.json (shared with the Python dipmon).
type Price struct {
	mu       sync.Mutex
	Fixed    float64
	usd      float64
	t        float64
	src      string
	err      string
	Every    time.Duration
	Net      bool
	cache    string
	kick     chan struct{}
	started  bool
	OnChange func()
	fetching bool
}

// NewPrice: fixed > 0 = --usd (no network); net=false = --no-usd.
func NewPrice(fixed float64, net bool) *Price {
	p := &Price{Fixed: fixed, Every: 60 * time.Second, Net: net && fixed == 0,
		cache: fmt.Sprintf("/tmp/dipmon-solusd-%d.json", os.Getuid()), kick: make(chan struct{}, 1)}
	if fixed != 0 {
		p.usd, p.t, p.src = fixed, float64(time.Now().UnixNano())/1e9, "fixed"
	} else {
		p.loadCache()
	}
	return p
}

func (p *Price) loadCache() {
	b, err := os.ReadFile(p.cache)
	if err != nil {
		return
	}
	var d map[string]any
	if json.Unmarshal(b, &d) != nil {
		return
	}
	usd, ok1 := d["usd"].(float64)
	t, ok2 := d["t"].(float64)
	if !ok1 || !ok2 || !(usd > 1 && usd < 100000) || float64(time.Now().UnixNano())/1e9-t >= 12*3600 {
		return
	}
	src := "cache"
	if s, ok := d["src"].(string); ok {
		src = s
	}
	p.usd, p.t, p.src = usd, t, RuneSlice(src, 12)+" (cache)"
}

func (p *Price) saveCache() {
	b, _ := json.Marshal(map[string]any{"usd": p.usd, "t": p.t, "src": p.src})
	tmp := p.cache + "." + strconv.Itoa(os.Getpid())
	if os.WriteFile(tmp, b, 0o644) == nil {
		_ = os.Rename(tmp, p.cache)
	}
}

var priceSources = []struct {
	name, url string
	parse     func(map[string]any) (float64, bool)
}{
	{"binance", "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", func(d map[string]any) (float64, bool) {
		s, ok := d["price"].(string)
		if !ok {
			f, ok := d["price"].(float64)
			return f, ok
		}
		f, err := strconv.ParseFloat(s, 64)
		return f, err == nil
	}},
	{"coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", func(d map[string]any) (float64, bool) {
		s, ok := d["solana"].(map[string]any)
		if !ok {
			return 0, false
		}
		f, ok := s["usd"].(float64)
		return f, ok
	}},
}

// FetchOnce tries each source; true when a price was stored.
func (p *Price) FetchOnce(timeout time.Duration) bool {
	p.mu.Lock()
	p.fetching = true
	p.mu.Unlock()
	defer func() {
		p.mu.Lock()
		p.fetching = false
		p.mu.Unlock()
	}()
	cl := &http.Client{Timeout: timeout}
	var errs []string
	for _, s := range priceSources {
		req, _ := http.NewRequest("GET", s.url, nil)
		req.Header.Set("User-Agent", "dipmon/3.0")
		req.Header.Set("Accept", "application/json")
		resp, err := cl.Do(req)
		if err != nil {
			errs = append(errs, s.name+": "+errKind(err))
			continue
		}
		body, err := io.ReadAll(io.LimitReader(resp.Body, 65536))
		resp.Body.Close()
		if err != nil {
			errs = append(errs, s.name+": read")
			continue
		}
		var d map[string]any
		if json.Unmarshal(body, &d) != nil {
			errs = append(errs, s.name+": JSONDecodeError")
			continue
		}
		v, ok := s.parse(d)
		if !ok {
			errs = append(errs, s.name+": KeyError")
			continue
		}
		if v > 1 && v < 100000 {
			p.mu.Lock()
			p.usd, p.t, p.src, p.err = v, float64(time.Now().UnixNano())/1e9, s.name, ""
			p.saveCache()
			cb := p.OnChange
			p.mu.Unlock()
			if cb != nil {
				cb()
			}
			return true
		}
		errs = append(errs, s.name+": odd price "+PyRepr(v))
	}
	p.mu.Lock()
	p.err = RuneSlice(strings.Join(errs, "; "), 120)
	cb := p.OnChange
	p.mu.Unlock()
	if cb != nil {
		cb()
	}
	return false
}

func errKind(err error) string {
	s := err.Error()
	switch {
	case strings.Contains(s, "Timeout") || strings.Contains(s, "timeout"):
		return "timeout"
	case strings.Contains(s, "no such host"):
		return "DNS"
	case strings.Contains(s, "refused"):
		return "refused"
	}
	return "URLError"
}

// Start runs the fetch loop in a goroutine (no-op without network).
func (p *Price) Start() {
	p.mu.Lock()
	if !p.Net || p.started {
		p.mu.Unlock()
		return
	}
	p.started = true
	p.mu.Unlock()
	go func() {
		for {
			p.FetchOnce(5 * time.Second)
			select {
			case <-p.kick:
			case <-time.After(p.Every):
			}
		}
	}()
}

// Refresh asks the loop to fetch now.
func (p *Price) Refresh() {
	select {
	case p.kick <- struct{}{}:
	default:
	}
}

// Get: (usd, source, age seconds (ok=false when fixed / unknown), error text, fetching).
func (p *Price) Get() (usd float64, src string, age float64, ageOK bool, errText string, fetching bool) {
	if p == nil {
		return 0, "", 0, false, "", false
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.t != 0 && p.Fixed == 0 {
		age, ageOK = float64(time.Now().UnixNano())/1e9-p.t, true
	}
	return p.usd, p.src, age, ageOK, p.err, p.fetching
}

// ------------------------------------------------------------------------------------------------------- system

// SysInfo: disk, load, memory and dipmon's own CPU / RSS (sampled at most every 5 s).
type SysInfo struct {
	Path              string
	Disk              float64
	HasDisk           bool
	Load              [3]float64
	HasLoad           bool
	MemUsed, MemTotal int64
	NCPU              int
	OwnCPU            float64
	HasOwn            bool
	OwnRSS            int64
	own               struct {
		t   time.Time
		cpu float64
		ok  bool
	}
	t      time.Time
	Frozen bool // tests: keep the values as they are
}

func NewSysInfo(path string, ncpu int) *SysInfo { return &SysInfo{Path: path, NCPU: ncpu} }

// Sample refreshes the figures (every 5 s unless forced).
func (s *SysInfo) Sample(force bool) {
	if s == nil || s.Frozen {
		return
	}
	now := time.Now()
	if !force && now.Sub(s.t) < 5*time.Second {
		return
	}
	s.t = now
	var st syscall.Statfs_t
	if syscall.Statfs(s.Path, &st) == nil && st.Blocks > 0 {
		s.Disk, s.HasDisk = (1-float64(st.Bavail)/float64(st.Blocks))*100, true
	} else {
		s.HasDisk = false
	}
	if b, err := os.ReadFile("/proc/loadavg"); err == nil {
		f := strings.Fields(string(b))
		if len(f) >= 3 {
			for i := 0; i < 3; i++ {
				s.Load[i], _ = strconv.ParseFloat(f[i], 64)
			}
			s.HasLoad = true
		}
	}
	if b, err := os.ReadFile("/proc/meminfo"); err == nil {
		var tot, avail int64
		for _, l := range strings.Split(string(b), "\n") {
			k, v, ok := strings.Cut(l, ":")
			if !ok {
				continue
			}
			f := strings.Fields(v)
			if len(f) == 0 {
				continue
			}
			n, _ := strconv.ParseInt(f[0], 10, 64)
			switch k {
			case "MemTotal":
				tot = n * 1024
			case "MemAvailable":
				avail = n * 1024
			}
		}
		if tot > 0 {
			s.MemUsed, s.MemTotal = tot-avail, tot
		}
	}
	var ru syscall.Rusage
	if syscall.Getrusage(syscall.RUSAGE_SELF, &ru) == nil {
		c := float64(ru.Utime.Sec) + float64(ru.Utime.Usec)/1e6 + float64(ru.Stime.Sec) + float64(ru.Stime.Usec)/1e6
		if s.own.ok {
			dt := now.Sub(s.own.t).Seconds()
			if dt < 1e-6 {
				dt = 1e-6
			}
			s.OwnCPU, s.HasOwn = (c-s.own.cpu)/dt*100, true
		}
		s.own.t, s.own.cpu, s.own.ok = now, c, true
	}
	if b, err := os.ReadFile("/proc/self/statm"); err == nil {
		f := strings.Fields(string(b))
		if len(f) > 1 {
			n, _ := strconv.ParseInt(f[1], 10, 64)
			s.OwnRSS = n * int64(os.Getpagesize())
		}
	}
}

// ------------------------------------------------------------------------------------------------------- budget

// Budget: the dip budget file's first_start / max_total_loss.
type Budget struct {
	FirstStart, MaxTotalLoss Num
}

// ReadBudget: nil when the file is missing or unreadable.
func ReadBudget(path string) *Budget {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	o, isObj, ok := DecodeObj(b)
	if !ok || !isObj {
		return nil
	}
	return &Budget{FirstStart: toNum(o["first_start"]), MaxTotalLoss: toNum(o["max_total_loss"])}
}
