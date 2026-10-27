package core

import (
	"bufio"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// Card is the trading-card view of a scope (one run or a PKT day): profit (the winning trades' P&L), loss (the
// losing trades'), rent back, fees (failed pre-send tries + failed buys), landed buys / sells and their SOL.
// Profit - Loss + Rent - Fees == Net exactly; for a run Net is the run P&L.
type Card struct {
	Profit, Loss    int64
	Wins, Losses    int64
	Rent, Fees      int64
	Buys, Sells     int64
	BuySol, SellSol int64
	Net             int64
	Runs            []int
	Loading         int
	Label           string
}

// WinRate: wins / (wins + losses).
func (c Card) WinRate() (float64, bool) {
	n := c.Wins + c.Losses
	if n == 0 {
		return 0, false
	}
	return float64(c.Wins) / float64(n), true
}

// AvgWin / AvgLoss (lamports, floor like Python's //).
func (c Card) AvgWin() (int64, bool) {
	if c.Wins == 0 {
		return 0, false
	}
	return floorDiv(c.Profit, c.Wins), true
}

func (c Card) AvgLoss() (int64, bool) {
	if c.Losses == 0 {
		return 0, false
	}
	return floorDiv(c.Loss, c.Losses), true
}

// PF is the profit factor (profit / loss).
func (c Card) PF() (float64, bool) {
	if c.Loss == 0 {
		return 0, false
	}
	return float64(c.Profit) / float64(c.Loss), true
}

func (c *Card) addPnl(p int64) {
	switch {
	case p > 0:
		c.Profit += p
		c.Wins++
	case p < 0:
		c.Loss -= p
		c.Losses++
	}
}

func (c *Card) add(o Card) {
	c.Profit += o.Profit
	c.Loss += o.Loss
	c.Wins += o.Wins
	c.Losses += o.Losses
	c.Rent += o.Rent
	c.Fees += o.Fees
	c.Buys += o.Buys
	c.Sells += o.Sells
	c.BuySol += o.BuySol
	c.SellSol += o.SellSol
	c.Net += o.Net
}

// MinRange is a [from, to) range of unix minutes; nil = everything.
type MinRange struct{ From, To int64 }

func (r *MinRange) in(m int64) bool { return r == nil || (m >= r.From && m < r.To) }

// CardOf builds the card of sessions (rng nil: the whole sessions; else what was booked in those minutes, each
// item at its own minute: a fill's P&L and rent at its booking minute, a failed try at its try, a failed buy at
// the buy, landed buys / sells at their records' times).
func CardOf(sessions []*Sess, rng *MinRange) Card {
	var c Card
	for _, S := range sessions {
		if S.PSRec {
			for _, r := range S.RealRecs {
				if rng.in(r.Min) {
					c.addPnl(r.Amt)
				}
			}
			for _, r := range S.RentRecs {
				if rng.in(r.Min) {
					c.Rent += r.Amt
				}
			}
			if rng == nil {
				c.Fees += S.PSFees()
			} else {
				for m, f := range S.FeeBuckets {
					if rng.in(m) {
						c.Fees += f
					}
				}
				// the engine's own fee count above ours: booked at the session's end
				if adj := S.PSFees() - S.PSFeeCnt; adj != 0 {
					te := S.TEnd()
					if te == 0 {
						te = S.CurT
					}
					if rng.in(floorDiv(te, minuteNS)) {
						c.Fees += adj
					}
				}
			}
		} else if len(S.LogPSReal) > 0 || S.LogPSFees != 0 {
			// an old run: only the log's PRESEND LIVE lines (no times: booked at the session start)
			m := floorDiv(S.T0, minuteNS)
			if rng.in(m) {
				for _, p := range S.LogPSReal {
					c.addPnl(p)
				}
				c.Fees += S.LogPSFees
			}
		}
		for _, tr := range S.Reg {
			if !tr.HasPnl || (rng != nil && (!tr.HasBm || !rng.in(tr.Bm))) {
				continue
			}
			switch tr.Res {
			case "filled":
				c.addPnl(tr.Pnl)
			case "guard", "lighthouse", "failed":
				c.Fees -= tr.Pnl
			}
		}
		if rng == nil {
			c.Buys += S.Tx.Buys
			c.Sells += S.Tx.Sells
			c.BuySol += S.Tx.BuySol
			c.SellSol += S.Tx.SellSol
		} else {
			for m, x := range S.Tx.ByMin {
				if rng.in(m) {
					c.Buys += x.Buys
					c.Sells += x.Sells
					c.BuySol += x.BuySol
					c.SellSol += x.SellSol
				}
			}
		}
	}
	c.Net = c.Profit - c.Loss + c.Rent - c.Fees
	return c
}

// FileSpan is (first record time, last record time) of a run file: its first line and its tail.
func FileSpan(path string) (int64, int64) {
	f, err := os.Open(path)
	if err != nil {
		return 0, 0
	}
	defer f.Close()
	var t0, t1 int64
	br := bufio.NewReaderSize(f, 65536)
	if line, err := br.ReadSlice('\n'); err == nil || err == io.EOF || err == bufio.ErrBufferFull {
		if t := tOf(line); TimeOKi(t) {
			t0 = t
		}
	}
	st, err := f.Stat()
	if err != nil {
		return t0, 0
	}
	n := st.Size()
	off := n - 262144
	if off < 0 {
		off = 0
	}
	buf := make([]byte, n-off)
	if _, err := f.ReadAt(buf, off); err != nil && err != io.EOF {
		return t0, 0
	}
	lines := strings.Split(string(buf), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if t := tOf([]byte(lines[i])); TimeOKi(t) {
			t1 = t
			break
		}
	}
	return t0, t1
}

var rxRunPrefix = regexp.MustCompile(`^(dip_(?:ams_)?r)\d+\.jsonl$`)

type todayEntry struct {
	key   [3]int64 // size, mtime, day start
	card  Card
	run   int
	book  map[int64]int64 // the day's P&L a minute (DayBook)
	first int64           // the run's first minute that day
}

type todayPending struct {
	path string
	key  [3]int64
	src  *Source
}

// Today is the day card: every run of this node's runs directory with records on the current PKT day (the
// current run live, the others loaded once, in chunks, and only their day card kept).
type Today struct {
	Self     *Source
	Day      MinRange
	Label    string
	files    []string
	cache    map[string]todayEntry
	pending  []todayPending
	Err      string
	started  bool
	lastScan time.Time
	// the other runs' bookings merged (Series), rebuilt when a file finishes loading or the day changes
	others      map[int64]int64
	othersFirst int64
	othersOK    bool
}

// NewToday for the current run's source.
func NewToday(self *Source) *Today { return &Today{Self: self, cache: map[string]todayEntry{}} }

// Start (re)scans the directory for the day holding ns (cached cards are kept while their file is unchanged).
func (t *Today) Start(ns float64) {
	m0, m1, label := DayRange(ns)
	t.Day, t.Label, t.started, t.lastScan = MinRange{m0, m1}, label, true, time.Now()
	t.othersOK = false
	dir := filepath.Dir(t.Self.JSONL)
	if abs, err := filepath.Abs(dir); err == nil {
		dir = abs
	}
	me := RealPath(t.Self.JSONL)
	pre := rxRunPrefix.FindStringSubmatch(filepath.Base(t.Self.JSONL))
	t.files, t.pending = nil, nil
	ents, err := os.ReadDir(dir)
	if err != nil {
		t.Err = err.Error()
		return
	}
	names := make([]string, 0, len(ents))
	for _, e := range ents {
		names = append(names, e.Name())
	}
	sort.Strings(names)
	for _, nm := range names {
		if !runRX.MatchString(nm) || (pre != nil && !strings.HasPrefix(nm, pre[1])) {
			continue
		}
		p := filepath.Join(dir, nm)
		if RealPath(p) == me {
			continue
		}
		st, err := os.Stat(p)
		if err != nil {
			continue
		}
		key := [3]int64{st.Size(), st.ModTime().Unix(), m0}
		if c, ok := t.cache[p]; ok && c.key == key {
			t.files = append(t.files, p)
			continue
		}
		t0, t1 := FileSpan(p)
		if t1 == 0 || floorDiv(t1, minuteNS) < m0 || (t0 != 0 && floorDiv(t0, minuteNS) >= m1) {
			continue // no records on this day
		}
		t.files = append(t.files, p)
		t.pending = append(t.pending, todayPending{path: p, key: key, src: NewSource(p, "", 0, 20)})
	}
}

// Started: Start was called.
func (t *Today) Started() bool { return t.started }

// Step reads one chunk of the next pending file; true while work remains.
func (t *Today) Step(chunk int64) bool {
	if len(t.pending) == 0 {
		return false
	}
	p := &t.pending[0]
	n := p.src.Step(chunk)
	if n == 0 && !p.src.Pending() {
		_, run, _ := RunInfo(p.path)
		book, first := DayBook(p.src.Model.Sessions, t.Day)
		t.cache[p.path] = todayEntry{key: p.key, card: CardOf(p.src.Model.Sessions, &t.Day), run: run, book: book, first: first}
		t.pending = t.pending[1:]
		t.othersOK = false
	}
	return len(t.pending) > 0
}

// Pending: files still loading.
func (t *Today) Pending() int { return len(t.pending) }

// Total is the day card over the other runs (loaded so far) and the current one (live).
func (t *Today) Total(model *Model) Card {
	c := CardOf(model.Sessions, &t.Day)
	var runs []int
	if model.Sessions != nil {
		if _, run, ok := RunInfo(t.Self.JSONL); ok && (c.Buys+c.Sells+c.Wins+c.Losses > 0 || c.Fees != 0 || c.Net != 0 || t.selfOnDay(model)) {
			runs = append(runs, run)
		}
	}
	for _, p := range t.files {
		if e, ok := t.cache[p]; ok {
			c.add(e.card)
			runs = append(runs, e.run)
		}
	}
	sort.Ints(runs)
	c.Runs = runs
	c.Loading = len(t.pending)
	c.Label = t.Label
	return c
}

func (t *Today) selfOnDay(model *Model) bool {
	for _, S := range model.Sessions {
		if S.T0 != 0 && t.Day.in(floorDiv(S.T0, minuteNS)) {
			return true
		}
	}
	return model.CurT != 0 && t.Day.in(floorDiv(model.CurT, minuteNS))
}
