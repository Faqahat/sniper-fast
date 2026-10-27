package core

// PnLSeries is a cumulative P&L a minute (the chart's line) and its extremes: the ATH (the first minute at the highest
// value) and the low (the first minute at the lowest). The run's series is the Python dipmon's (series_hi / series_lo);
// the day's adds up every run of the PKT day the same way (see Today.Series).
type PnLSeries struct {
	Vals   []int64 // lamports, cumulative, one a minute
	M0     int64   // the unix minute of Vals[0]
	Hi, Lo int     // indexes of the first maximum / minimum
	Now    int64   // the scope's P&L now: the run P&L (the hero), or the day card's net
}

// NewSeries finds the extremes (the first index of each, like the Python dipmon's v.best / v.worst).
func NewSeries(vals []int64, m0, now int64) *PnLSeries {
	s := &PnLSeries{Vals: vals, M0: m0, Now: now}
	for i, x := range vals {
		if x > vals[s.Hi] {
			s.Hi = i
		}
		if x < vals[s.Lo] {
			s.Lo = i
		}
	}
	return s
}

// Ok: the series has points.
func (s *PnLSeries) Ok() bool { return s != nil && len(s.Vals) > 0 }

// TimeAt is the start of minute i (ns).
func (s *PnLSeries) TimeAt(i int) float64 { return float64(s.M0+int64(i)) * 60e9 }

// ATH is the highest point (lamports) and its minute (ns).
func (s *PnLSeries) ATH() (int64, float64) { return s.Vals[s.Hi], s.TimeAt(s.Hi) }

// Low is the lowest point and its minute.
func (s *PnLSeries) Low() (int64, float64) { return s.Vals[s.Lo], s.TimeAt(s.Lo) }

// End is the last point (the chart's newest).
func (s *PnLSeries) End() int64 { return s.Vals[len(s.Vals)-1] }

// FromATH is the last point minus the ATH (<= 0: the drawdown from the top).
func (s *PnLSeries) FromATH() int64 { return s.End() - s.Vals[s.Hi] }

// PnL is the run's series (the chart's line in the run scope; ATH / low = series_hi / series_lo).
func (v *View) PnL() *PnLSeries {
	if len(v.Series) == 0 {
		return nil
	}
	return NewSeries(v.Series, v.SeriesM0, v.Total)
}

// DayBook is what sessions booked in rng a minute (each item at its booking minute, the engine's extra fee count
// at the session's end: the day card's net is the sum) and the first minute they were active in rng (0: never).
func DayBook(sessions []*Sess, rng MinRange) (map[int64]int64, int64) {
	book := map[int64]int64{}
	var first int64
	note := func(m int64) {
		if first == 0 || m < first {
			first = m
		}
	}
	for _, S := range sessions {
		for m, d := range S.Buckets {
			if rng.in(m) {
				book[m] += d
				note(m)
			}
		}
		te := S.TEnd()
		if te == 0 {
			te = S.CurT
		}
		if S.PSRec {
			if adj := S.PSFees() - S.PSFeeCnt; adj != 0 {
				if m := floorDiv(te, minuteNS); rng.in(m) {
					book[m] -= adj
					note(m)
				}
			}
		}
		// the session's start, or midnight when it began the day before
		if S.T0 != 0 {
			s0, s1 := floorDiv(S.T0, minuteNS), floorDiv(S.T0, minuteNS)
			if te != 0 {
				s1 = floorDiv(te, minuteNS)
			}
			if s0 < rng.To && s1 >= rng.From {
				note(max(s0, rng.From))
			}
		}
	}
	return book, first
}

// Series is the day's cumulative P&L a minute over every run of the day (the ones loaded so far and the current
// one), from the first run's start that day (midnight at the earliest) to now or the last booking; its last point
// is the day card's net. nil when nothing ran that day.
func (t *Today) Series(model *Model, nowNS float64, net int64) *PnLSeries {
	if !t.started {
		return nil
	}
	if !t.othersOK {
		t.others, t.othersFirst = map[int64]int64{}, 0
		for _, p := range t.files {
			if e, ok := t.cache[p]; ok {
				for m, d := range e.book {
					t.others[m] += d
				}
				if e.first != 0 && (t.othersFirst == 0 || e.first < t.othersFirst) {
					t.othersFirst = e.first
				}
			}
		}
		t.othersOK = true
	}
	book, first := DayBook(model.Sessions, t.Day)
	for m, d := range t.others {
		book[m] += d
	}
	if t.othersFirst != 0 && (first == 0 || t.othersFirst < first) {
		first = t.othersFirst
	}
	if first == 0 {
		return nil
	}
	m1 := min(floorDiv(int64(nowNS), minuteNS), t.Day.To-1)
	for m := range book {
		m1 = max(m1, m)
	}
	m1 = max(m1, first)
	vals := make([]int64, 0, m1-first+1)
	acc := int64(0)
	for m := first; m <= m1; m++ {
		acc += book[m]
		vals = append(vals, acc)
	}
	return NewSeries(vals, first, net)
}
