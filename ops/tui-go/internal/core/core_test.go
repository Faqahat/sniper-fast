package core

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

var dataDir = func() string {
	if d := os.Getenv("DIPMON_DATA"); d != "" {
		return d
	}
	return "/home/moiz/sniper-data/runs"
}()

// ------------------------------------------------------------------------------------------------- tail

func TestTailPartialTruncateReplace(t *testing.T) {
	d := t.TempDir()
	p := filepath.Join(d, "x.jsonl")
	write := func(s string, app bool) {
		fl := os.O_CREATE | os.O_WRONLY | os.O_TRUNC
		if app {
			fl = os.O_CREATE | os.O_WRONLY | os.O_APPEND
		}
		f, err := os.OpenFile(p, fl, 0o644)
		if err != nil {
			t.Fatal(err)
		}
		f.WriteString(s)
		f.Close()
	}
	write(`{"ev":"dump","t":1}`+"\n"+`{"ev":"du`, false)
	tl := NewTail(p)
	ln := tl.Read(1 << 20)
	if len(ln) != 1 || string(ln[0]) != `{"ev":"dump","t":1}` || string(tl.Buf) != `{"ev":"du` {
		t.Fatalf("complete line + partial kept: %q %q", ln, tl.Buf)
	}
	write(`mp","t":2}`+"\n", true)
	ln = tl.Read(1 << 20)
	if len(ln) != 1 || string(ln[0]) != `{"ev":"dump","t":2}` || len(tl.Buf) != 0 {
		t.Fatalf("partial completed: %q %q", ln, tl.Buf)
	}
	write(`{"ev":"dump","t":3}`, true)
	if ln = tl.Read(1 << 20); len(ln) != 0 || len(tl.Buf) == 0 {
		t.Fatal("a record without its newline must be held")
	}
	if b := tl.FlushPartialJSON(); string(b) != `{"ev":"dump","t":3}` || len(tl.Buf) != 0 {
		t.Fatalf("flush partial: %q", b)
	}
	write(`{"ev":"dump","t":9}`+"\n", false)
	tl.Read(1 << 20)
	if !tl.Reset {
		t.Fatal("truncation not noticed")
	}
	p2 := p + ".new"
	os.WriteFile(p2, []byte(strings.Repeat(`{"ev":"dump","t":10}`+"\n", 50)), 0o644)
	t2 := NewTail(p)
	t2.Read(1 << 20)
	os.Rename(p2, p)
	t2.Read(1 << 20)
	if !t2.Reset {
		t.Fatal("replacement (new inode) not noticed")
	}
	t3 := NewTail(p)
	var got [][]byte
	for {
		got = append(got, t3.Read(37)...)
		if t3.Pending() == 0 {
			break
		}
	}
	if len(got) != 50 {
		t.Fatalf("small chunks: %d lines", len(got))
	}
	if NewTail(filepath.Join(d, "nope")).Read(100) != nil {
		t.Fatal("missing file must give no lines")
	}
}

// TestTailConcurrentWriter (run with -race): a writer appends records in odd pieces while the reader follows.
func TestTailConcurrentWriter(t *testing.T) {
	d := t.TempDir()
	p := filepath.Join(d, "dip_ams_r1.jsonl")
	lp := filepath.Join(d, "dip_ams_r1.log")
	os.WriteFile(p, nil, 0o644)
	os.WriteFile(lp, nil, 0o644)
	const n = 3000
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		f, _ := os.OpenFile(p, os.O_APPEND|os.O_WRONLY, 0)
		g, _ := os.OpenFile(lp, os.O_APPEND|os.O_WRONLY, 0)
		defer f.Close()
		defer g.Close()
		r := rand.New(rand.NewSource(1))
		buf := ""
		for i := 0; i < n; i++ {
			buf += fmt.Sprintf(`{"ev":"presend_attempt_land","fee":5120,"res":"6042","t":%d}`+"\n", 1793096817160592067+int64(i))
			if r.Intn(3) == 0 || i == n-1 {
				cut := r.Intn(len(buf) + 1)
				f.WriteString(buf[:cut])
				f.WriteString(buf[cut:])
				buf = ""
			}
			if i%100 == 0 {
				g.WriteString(fmt.Sprintf("RUNTIME lag 60s n=1 p50=1.0ms p99=2.0ms max=3.0ms\n"))
			}
		}
	}()
	src := NewSource(p, "", 0, 100)
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		src.Step(4096)
		if src.Model.JLines >= n {
			break
		}
	}
	wg.Wait()
	for src.Pending() {
		src.Step(1 << 20)
	}
	S := src.Model.Sessions[0]
	if src.Model.JLines != n || S.PSFeeN != n || S.PSFeeCnt != n*5120 || src.Model.Bad != 0 {
		t.Fatalf("lines %d fees %d/%d bad %d", src.Model.JLines, S.PSFeeN, S.PSFeeCnt, src.Model.Bad)
	}
}

// TestPriceConcurrent (run with -race): the price goroutine's fields read while it stores.
func TestPriceConcurrent(t *testing.T) {
	p := NewPrice(0, false)
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		for i := 0; i < 1000; i++ {
			p.mu.Lock()
			p.usd, p.t, p.src = 100+float64(i), float64(time.Now().UnixNano())/1e9, "x"
			p.mu.Unlock()
		}
	}()
	go func() {
		defer wg.Done()
		for i := 0; i < 1000; i++ {
			p.Get()
		}
	}()
	wg.Wait()
}

// ------------------------------------------------------------------------------------------------- formatting

func TestPyFormatting(t *testing.T) {
	cases := map[float64]string{100: "100.0", 0.58772926: "0.58772926", 1.79310414e18: "1.79310414e+18", 1e-05: "1e-05",
		0.0001: "0.0001", 1e16: "1e+16", 1234567: "1234567.0", -0.046: "-0.046", 7800.056772174: "7800.056772174",
		0.27125768411686646: "0.27125768411686646", 123456789012345.6: "123456789012345.6"}
	for f, want := range cases {
		if got := PyRepr(f); got != want {
			t.Errorf("PyRepr(%v) = %q, want %q", f, got, want)
		}
	}
	if FS(0.5877, 4) != "+0.5877" || FS(-0.00004, 4) != "-0.0000" || F(2.5, 0) != "2" || F(3.5, 0) != "4" {
		t.Error("fixed formatting")
	}
	if FC(1234567.891, 2) != "1,234,567.89" || IC(-1234) != "-1,234" || IC(999) != "999" {
		t.Error("thousands separators")
	}
	if Usd(-12345, true, 100, true, 2) != "-$0.00" || Usd(587729260, true, 187.42, true, 2) != "+$110.15" {
		t.Errorf("usd %q %q", Usd(-12345, true, 100, true, 2), Usd(587729260, true, 187.42, true, 2))
	}
	if got, want := JSONDumps("×·✓\x7f\""), "\"\\u00d7\\u00b7\\u2713\\u007f\\\"\""; got != want { // = Python's json.dumps
		t.Errorf("json escapes: %q != %q", got, want)
	}
	if PyStrip("\x1c  a b  ") != "a b" {
		t.Error("strip")
	}
	if T12(1793096817160592067, false) != "3:26 PM" || T12(1793096817160592067, true) != "3:26:57 PM" {
		t.Errorf("t12 %q %q", T12(1793096817160592067, false), T12(1793096817160592067, true))
	}
	w := WrapText("aaaa bbbb cccc dddd", 9, 2)
	if len(w) != 3 || w[0] != "aaaa bbbb" || w[1] != "  cccc" || w[2] != "  dddd" { // = Python's wrap_text
		t.Errorf("wrap %q", w)
	}
}

func TestCleanMasksSecrets(t *testing.T) {
	s := Clean("rpc https://user:pass@host/x?api-key=SECRET123&b=1 token=abc\tok \x07 ✓ 中")
	for _, bad := range []string{"SECRET123", "pass@", "abc", "\x07", "\t", "中"} {
		if strings.Contains(s, bad) {
			t.Errorf("%q still in %q", bad, s)
		}
	}
	if !strings.Contains(s, "✓") {
		t.Errorf("narrow symbols kept: %q", s)
	}
}

// TestGarbageLines: odd / broken / huge lines never panic and are counted as bad.
func TestGarbageLines(t *testing.T) {
	M := NewModel(0, 100)
	r := rand.New(rand.NewSource(7))
	var lines [][]byte
	base := []string{`{"ev":"fire","mint":"M","t":1793096817160592067,"spend":"x","writes":7}`, `{"ev":"close","mint":"M","sell_land":{"a":1},"land":[null,1,"z"]}`,
		`{"ev":"presend_live_close","w":1,"mint":"M","land":[1],"exit_slot":5,"sell_lands":[[1,2,3,true]]}`, `{"ev":"presend_live_realized","w":"x","pnl":1e400}`,
		`{"ev":"run_start","t":5,"presend_live":[1],"m2":"x"}`, `{"ev":"run_end","presend_live":[1,2]}`, `[1,2]`, `{"ev":"buy_land","mint":"M","variant":{"paths":[1]}}`,
		`{"ev":"presend_attempt_land","res":"`, `{"ev":`, `{"ev":"presend_live_fill","w":1e30,"mint":null}`, strings.Repeat("x", 100000)}
	for i := 0; i < 2000; i++ {
		b := []byte(base[r.Intn(len(base))])
		if r.Intn(3) == 0 && len(b) > 2 {
			b = b[:r.Intn(len(b))]
		}
		lines = append(lines, b)
	}
	M.FeedJSONL(lines)
	M.FeedLog([][]byte{[]byte("REALIZED mint=M pnl=1.2.3 SOL source=x"), []byte("START BALANCE x SOL; kill switch below y SOL"),
		[]byte("DIP status fired 1 closed 1 open 0 slot 5 skipped {bad"), []byte("\xff\xfe broken utf8"), []byte("DIP LIVE | 99999999999999999999 min")})
	ctx := &Ctx{Src: &Source{Model: M, TJ: NewTail("/nonexistent"), TL: NewTail("/nonexistent")}, Price: NewPrice(100, false)}
	v := BuildView(ctx, -1)
	_ = SnapshotJSON(v, ctx, nil)
	_ = SnapshotText(v, ctx, 110)
	if M.Bad == 0 {
		t.Fatal("bad lines not counted")
	}
}

// ------------------------------------------------------------------------------------------------- the card

type recCount struct{ buys, sells, buySol, sellSol int64 }

// countRecords scans a run file with encoding/json, independently of the model's parser.
func countRecords(t *testing.T, path string) recCount {
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var c recCount
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 16<<20)
	for sc.Scan() {
		line := sc.Bytes()
		ls := string(line)
		if !strings.Contains(ls, `"presend_live_fill"`) && !strings.Contains(ls, `"buy_land"`) && !strings.Contains(ls, `"sell_land"`) &&
			!strings.Contains(ls, `"presend_live_sell_land"`) {
			continue
		}
		var o map[string]any
		if json.Unmarshal(line, &o) != nil {
			continue
		}
		num := func(k string) int64 {
			if x, ok := o[k].(float64); ok {
				return int64(x)
			}
			return 0
		}
		switch o["ev"] {
		case "presend_live_fill":
			c.buys++
			c.buySol += num("sol_in")
		case "buy_land":
			c.buys++
			c.buySol += num("sol")
		case "presend_live_sell_land", "sell_land":
			c.sells++
			c.sellSol += num("sol")
		}
	}
	return c
}

func localRuns(t *testing.T) []string {
	var out []string
	have := map[string]bool{}
	for _, d := range []string{dataDir, tuiDataDir} { // the shared run copies, then dipmon's own (r28)
		for _, pat := range []string{"ams/runs/dip_ams_r*.jsonl", "fra/runs/dip_r*.jsonl"} {
			m, _ := filepath.Glob(filepath.Join(d, pat))
			for _, p := range m {
				if !have[filepath.Base(p)] {
					have[filepath.Base(p)] = true
					out = append(out, p)
				}
			}
		}
	}
	if len(out) == 0 {
		t.Skip("no local run data")
	}
	return out
}

// TestCardIdentityAllRuns: profit - loss + rent - fees == the run P&L exactly; buys / sells and their SOL equal the
// engine's landed-buy / landed-sell records, on every local run.
func TestCardIdentityAllRuns(t *testing.T) {
	for _, p := range localRuns(t) {
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
		c := CardOf(src.Model.Sessions, nil)
		var total int64
		for _, S := range src.Model.Sessions {
			total += S.Total()
		}
		if c.Profit-c.Loss+c.Rent-c.Fees != total || c.Net != total {
			t.Errorf("%s: profit %d - loss %d + rent %d - fees %d = %d != P&L %d", filepath.Base(p), c.Profit, c.Loss, c.Rent, c.Fees,
				c.Profit-c.Loss+c.Rent-c.Fees, total)
		}
		rc := countRecords(t, p)
		if rc.buys != c.Buys || rc.sells != c.Sells || rc.buySol != c.BuySol || rc.sellSol != c.SellSol {
			t.Errorf("%s: txns %d/%d vol %d/%d != records %d/%d vol %d/%d", filepath.Base(p), c.Buys, c.Sells, c.BuySol, c.SellSol,
				rc.buys, rc.sells, rc.buySol, rc.sellSol)
		}
	}
}

// TestTodayIdentity: for every PKT day with runs, the day card adds up, and its net equals what the runs booked in
// that day's minutes (the P&L line's buckets + the engine's own fee count at a session's end).
func TestTodayIdentity(t *testing.T) {
	runs := localRuns(t)
	days := map[int64]bool{}
	loaded := map[string]*Source{}
	for _, p := range runs {
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
		loaded[p] = src
		for _, S := range src.Model.Sessions {
			if S.T0 != 0 {
				d0, _, _ := DayRange(float64(S.T0))
				days[d0] = true
			}
		}
	}
	checked := 0
	for _, p := range runs {
		if !strings.Contains(p, "/ams/") {
			continue
		}
		src := loaded[p]
		if len(src.Model.Sessions) == 0 || src.Model.CurT == 0 {
			continue
		}
		td := NewToday(src)
		td.Start(float64(src.Model.CurT))
		for td.Step(8 << 20) {
		}
		c := td.Total(src.Model)
		if c.Profit-c.Loss+c.Rent-c.Fees != c.Net {
			t.Errorf("%s day %s: the card does not add up", filepath.Base(p), c.Label)
		}
		// independent: the buckets of every run of the directory in the day's minutes
		var want int64
		for _, q := range runs {
			if filepath.Dir(q) != filepath.Dir(p) {
				continue
			}
			for _, S := range loaded[q].Model.Sessions {
				for mm, d := range S.Buckets {
					if mm >= td.Day.From && mm < td.Day.To {
						want += d
					}
				}
				if S.PSRec {
					if adj := S.PSFees() - S.PSFeeCnt; adj != 0 {
						te := S.TEnd()
						if te == 0 {
							te = S.CurT
						}
						if m := floorDiv(te, minuteNS); m >= td.Day.From && m < td.Day.To {
							want -= adj
						}
					}
				}
			}
		}
		if c.Net != want {
			t.Errorf("%s day %s: today net %d != booked %d", filepath.Base(p), c.Label, c.Net, want)
		}
		checked++
	}
	if checked == 0 {
		t.Skip("no AMS runs")
	}
}

// TestATHLow: the ATH / low (the card, --snapshot, --json) are the extremes of the series the chart draws, on every
// local run and every session scope: the run's = the Python dipmon's series_hi / series_lo, the first minute at the
// highest / lowest value; from ATH = the last point - the ATH (<= 0); the JSON fields match.
func TestATHLow(t *testing.T) {
	for _, p := range localRuns(t) {
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
		ctx := &Ctx{Src: src, FixedNow: float64(src.Model.CurT) / 1e9}
		for scope := -1; scope < len(src.Model.Sessions); scope++ {
			v := BuildView(ctx, scope)
			s := v.PnL()
			if !s.Ok() {
				if v.HasBest {
					t.Errorf("%s: series_hi without a series", filepath.Base(p))
				}
				continue
			}
			a, at := s.ATH()
			l, lt := s.Low()
			hi, lo, hiI, loI := s.Vals[0], s.Vals[0], 0, 0
			for i, x := range s.Vals {
				if x > hi {
					hi, hiI = x, i
				}
				if x < lo {
					lo, loI = x, i
				}
			}
			if a != hi || l != lo || s.Hi != hiI || s.Lo != loI {
				t.Errorf("%s scope %d: ATH/low %d/%d != the series' %d/%d", filepath.Base(p), scope, a, l, hi, lo)
			}
			if float64(a) != v.Best[0] || at != v.Best[1] || float64(l) != v.Worst[0] || lt != v.Worst[1] {
				t.Errorf("%s scope %d: ATH/low != series_hi/series_lo", filepath.Base(p), scope)
			}
			if f := s.FromATH(); f > 0 || f != s.Vals[len(s.Vals)-1]-a {
				t.Errorf("%s scope %d: from ATH %d", filepath.Base(p), scope, f)
			}
			if scope == -1 {
				var d struct {
					SeriesHi []float64 `json:"series_hi"`
					SeriesLo []float64 `json:"series_lo"`
					ATH      *float64  `json:"ath_sol"`
					ATHT     *int64    `json:"ath_t"`
					Low      *float64  `json:"low_sol"`
					LowT     *int64    `json:"low_t"`
					From     *float64  `json:"from_ath_sol"`
				}
				if err := json.Unmarshal([]byte(SnapshotJSON(v, ctx, nil)), &d); err != nil {
					t.Fatalf("%s: %v", filepath.Base(p), err)
				}
				if d.ATH == nil || *d.ATH != d.SeriesHi[0]/1e9 || float64(*d.ATHT) != d.SeriesHi[1] || *d.Low != d.SeriesLo[0]/1e9 ||
					float64(*d.LowT) != d.SeriesLo[1] || *d.From != float64(s.FromATH())/1e9 {
					t.Errorf("%s: the JSON ath / low fields do not match series_hi / series_lo", filepath.Base(p))
				}
			}
		}
	}
}

// TestTodaySeries: the day's series (the chart and the ATH / low with s) ends at the day card's net, its ATH / low
// are its first extremes, and every minute equals an independent sum of what every run of the directory booked that day
// up to that minute (each item at its minute, the engine's extra fee count at the session's end).
func TestTodaySeries(t *testing.T) {
	runs := localRuns(t)
	loaded := map[string]*Source{}
	for _, p := range runs {
		src := NewSource(p, "", 0, 50)
		src.LoadAll(LoadChunk, 0, nil)
		loaded[p] = src
	}
	// one current run per directory and day (the last one): every run of the day is in its series
	last := map[string]string{}
	for _, p := range runs {
		src := loaded[p]
		if len(src.Model.Sessions) == 0 || src.Model.CurT == 0 {
			continue
		}
		d0, _, _ := DayRange(float64(src.Model.CurT))
		k := filepath.Dir(p) + "|" + strconv.FormatInt(d0, 10)
		if q := last[k]; q == "" || loaded[q].Model.CurT < src.Model.CurT {
			last[k] = p
		}
	}
	checked := 0
	for _, p := range runs {
		src := loaded[p]
		if len(src.Model.Sessions) == 0 || src.Model.CurT == 0 {
			continue
		}
		if d0, _, _ := DayRange(float64(src.Model.CurT)); last[filepath.Dir(p)+"|"+strconv.FormatInt(d0, 10)] != p {
			continue
		}
		td := NewToday(src)
		now := float64(src.Model.CurT)
		td.Start(now)
		for td.Step(LoadChunk) { // the same chunks as LoadAll: log lines book at the same minutes
		}
		c := td.Total(src.Model)
		s := td.Series(src.Model, now, c.Net)
		if !s.Ok() {
			t.Errorf("%s: no day series", filepath.Base(p))
			continue
		}
		if s.End() != c.Net {
			t.Errorf("%s day %s: the series ends at %d, the card's net is %d", filepath.Base(p), c.Label, s.End(), c.Net)
		}
		for i, x := range s.Vals {
			if x > s.Vals[s.Hi] || x < s.Vals[s.Lo] || (x == s.Vals[s.Hi] && i < s.Hi) || (x == s.Vals[s.Lo] && i < s.Lo) {
				t.Errorf("%s: the day's ATH / low are not the first extremes", filepath.Base(p))
				break
			}
		}
		// independent: every run of the same directory, minute by minute
		book := map[int64]int64{}
		first := int64(0)
		note := func(m int64) {
			if first == 0 || m < first {
				first = m
			}
		}
		for _, q := range runs {
			if filepath.Dir(q) != filepath.Dir(p) {
				continue
			}
			for _, S := range loaded[q].Model.Sessions {
				for mm, d := range S.Buckets {
					if mm >= td.Day.From && mm < td.Day.To {
						book[mm] += d
						note(mm)
					}
				}
				te := S.TEnd()
				if te == 0 {
					te = S.CurT
				}
				if adj := S.PSFees() - S.PSFeeCnt; S.PSRec && adj != 0 {
					if m := floorDiv(te, minuteNS); m >= td.Day.From && m < td.Day.To {
						book[m] -= adj
						note(m)
					}
				}
				if S.T0 != 0 {
					s0, s1 := floorDiv(S.T0, minuteNS), floorDiv(S.T0, minuteNS)
					if te != 0 {
						s1 = floorDiv(te, minuteNS)
					}
					if s0 < td.Day.To && s1 >= td.Day.From {
						note(max(s0, td.Day.From))
					}
				}
			}
		}
		if first != s.M0 {
			t.Errorf("%s day %s: the series starts at minute %d, want %d", filepath.Base(p), c.Label, s.M0, first)
			continue
		}
		acc := int64(0)
		for i := range s.Vals {
			acc += book[s.M0+int64(i)]
			if s.Vals[i] != acc {
				t.Errorf("%s day %s: minute %d: %d != booked %d", filepath.Base(p), c.Label, i, s.Vals[i], acc)
				break
			}
		}
		checked++
	}
	if checked == 0 {
		t.Skip("no runs")
	}
}
