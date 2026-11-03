package core

// dip24 (engine 10-29): no hard limits, the PROFIT LOCK, the rolling 24 h pre-send fee budget (pauses, never stops),
// the regular mode live | paper | off, the log-only OBSERVATORY, the feed names. Everything here comes from the text
// log (the start lines and the 60 s "DIP status" line); older runs have none of it and render exactly as before.

import (
	"regexp"
	"strings"
)

var (
	rxLockSet   = regexp.MustCompile(`give back max\(([\d.]+) SOL, ([\d.]+)% of the peak profit\)`)
	rxLockSt    = regexp.MustCompile(`\| lock: peak ([-+]?[\d.]+), floor ([-+]?[\d.]+) \(([\d.]+) give-back\), run PnL ([-+]?[\d.]+)`)
	rxLockFire  = regexp.MustCompile(`^PROFIT LOCK: peak ([-+]?[\d.]+), floor ([-+]?[\d.]+), balance ([\d.]+) \(run PnL ([-+]?[\d.]+)\)`)
	rxFee24     = regexp.MustCompile(`\| fees 24 h ([\d.]+)/([\d.]+) SOL( PAUSED)?(?: \(pauses (\d+)\))?`)
	rxFeeBudCfg = regexp.MustCompile(`^([\d.]+) SOL per rolling 24 h`)
	rxFeePR     = regexp.MustCompile(`last 24 h ([\d.]+) SOL [<>]=? ([\d.]+) SOL`)
	rxFeePN     = regexp.MustCompile(`\(pause #(\d+)`)
	rxRegPaper  = regexp.MustCompile(`REGULAR PAPER: picks (\d+), fills (\d+) \(no-fill (\d+)\), exits (\d+), paper P&L ([-+]?[\d.]+) SOL gross / ([-+]?[\d.]+) net, open (\d+)`)
	rxObsHead   = regexp.MustCompile(`^sent (\d+) dropped (\d+) queued (\d+) done (\d+)$`)
	rxObsRec    = regexp.MustCompile(`^(\d+) records ([\d.]+) MB in (\d+) part\(s\), p99 ([\d.]+) us/msg, ~(\d+) MB$`)
	rxObsCnt    = regexp.MustCompile(`^([a-z][a-z0-9_-]*(?: [a-z][a-z0-9_-]*)?) (\d+)(?: fills (\d+))?$`)
	rxObsErr    = regexp.MustCompile(`^WRITE ERRORS (\d+)`)
	rxFeedSt    = regexp.MustCompile(`FEEDSTATUS feed=(\S+)`)
)

// ObsCount is one observatory counter of the status line ("rearm windows 106 fills 88": K "rearm", N 106, Fills 88).
type ObsCount struct {
	K, Sub   string
	N, Fills int64
	HasFills bool
}

// ObsStat: the observatory (dip24, log only): its start line and the latest status-line part.
type ObsStat struct {
	On                          bool // the "DIP OBSERVATORY" start line
	Names                       []string
	Out                         string
	HasLine                     bool // an OBS status part
	Sent, Dropped, Queued, Done int64
	Counts                      []ObsCount
	Records, Parts, MemMB       int64
	MB, P99                     float64
	HasRec                      bool
	WriteErr                    int64
	Min                         int // the log minute of the latest part
}

// RegPaper: the "REGULAR PAPER: ..." status part.
type RegPaper struct {
	Picks, Fills, NoFill, Exits, Open int64
	Gross, Net                        float64
}

// D24Log: a session's dip24 lines.
type D24Log struct {
	Limits      bool   // the "DIP LIMITS:" line
	TimeTxt     string // its pieces as logged
	RegTxt      string
	PSFillsTxt  string
	NoTime      bool // time: no time limit (or --minutes 0 with the limits line)
	RegUnl      bool // regular buys unlimited
	PSFillsUnl  bool // pre-send fills unlimited
	HasLock     bool // the profit lock is set (give back max(M, F x peak))
	LockOff     bool // "profit lock none"
	LockM       int64
	LockF       float64 // 0.30
	HasLockSt   bool    // a "lock:" status part
	LockPeak    int64
	LockFloor   int64
	LockGive    int64
	LockPnL     int64
	LockMin     int
	LockPending int64 // "PROFIT LOCK pending confirmation" lines
	LockFired   bool
	LockFire    [4]int64 // peak, floor, balance, run PnL at the stop
	HasBud24    bool     // the rolling 24 h budget (from the limits line / the status part)
	Bud24       int64
	HasFee24    bool // a "fees 24 h" status part
	Fee24       int64
	FeePaused   bool // the latest state: the status part or a PAUSED / RESUMED line, whichever came last
	FeePauses   int64
	FeePausedAt int    // log minute of the last pause (-1 none)
	RegMode     string // live | paper | off ("" = not logged: before dip24)
	HasRegP     bool
	RegP        RegPaper
	Obs         ObsStat
}

// Any: the session logged any dip24 line.
func (d *D24Log) Any() bool {
	return d.Limits || d.HasLock || d.HasLockSt || d.LockFired || d.HasFee24 || d.RegMode != "" || d.Obs.On || d.Obs.HasLine
}

func lamF(s string) int64 {
	return mustLam(s)
}

// d24Line handles a dip24 start / event line; true = consumed.
func (M *Model) d24Line(S *Sess, st string) bool {
	d := &S.D24
	switch {
	case strings.HasPrefix(st, "DIP LIMITS:"):
		d.Limits = true
		for _, p := range strings.Split(strings.TrimPrefix(st, "DIP LIMITS:"), " | ") {
			p = PyStrip(p)
			switch {
			case strings.HasPrefix(p, "time "):
				d.TimeTxt = strings.TrimPrefix(p, "time ")
				d.NoTime = strings.Contains(d.TimeTxt, "no time limit")
			case strings.HasPrefix(p, "regular buys "):
				d.RegTxt = strings.TrimPrefix(p, "regular buys ")
				d.RegUnl = d.RegTxt == "unlimited"
			case strings.HasPrefix(p, "pre-send fills "):
				d.PSFillsTxt = strings.TrimPrefix(p, "pre-send fills ")
				d.PSFillsUnl = d.PSFillsTxt == "unlimited"
			case strings.HasPrefix(p, "profit lock "):
				if m := rxLockSet.FindStringSubmatch(p); m != nil {
					d.HasLock, d.LockOff = true, false
					d.LockM, d.LockF = lamF(m[1]), mustFloat(m[2])/100
				} else if strings.HasSuffix(p, "none") {
					d.LockOff = true
				}
			case strings.HasPrefix(p, "pre-send fee budget "):
				if m := rxFeeBudCfg.FindStringSubmatch(strings.TrimPrefix(p, "pre-send fee budget ")); m != nil {
					d.HasBud24, d.Bud24 = true, lamF(m[1])
				}
			}
		}
		return true
	case strings.HasPrefix(st, "DIP REGULAR "):
		r := strings.TrimPrefix(st, "DIP REGULAR ")
		switch {
		case strings.HasPrefix(r, "LIVE"):
			d.RegMode = "live"
		case strings.HasPrefix(r, "PAPER"):
			d.RegMode = "paper"
		case strings.HasPrefix(r, "OFF"):
			d.RegMode = "off"
		default:
			return false
		}
		return true
	case strings.HasPrefix(st, "DIP OBSERVATORY"):
		d.Obs.On = true
		if i := strings.Index(st, "): "); i >= 0 {
			r := st[i+3:]
			if j := strings.Index(r, " -> "); j >= 0 {
				d.Obs.Out = PyStrip(strings.SplitN(r[j+4:], " | ", 2)[0])
				r = r[:j]
			}
			d.Obs.Names = nil
			for _, x := range strings.Split(r, ",") {
				if x = PyStrip(x); x != "" {
					d.Obs.Names = append(d.Obs.Names, x)
				}
			}
		}
		return true
	case strings.HasPrefix(st, "PROFIT LOCK"):
		switch {
		case strings.HasPrefix(st, "PROFIT LOCK ON"):
			if m := rxLockSet.FindStringSubmatch(st); m != nil {
				d.HasLock, d.LockOff = true, false
				d.LockM, d.LockF = lamF(m[1]), mustFloat(m[2])/100
			}
		case strings.HasPrefix(st, "PROFIT LOCK pending"):
			d.LockPending++
		case strings.HasPrefix(st, "PROFIT LOCK:"):
			d.LockFired = true
			if m := rxLockFire.FindStringSubmatch(st); m != nil {
				d.LockFire = [4]int64{lamF(m[1]), lamF(m[2]), lamF(m[3]), lamF(m[4])}
			}
		default:
			return false
		}
		return true
	case strings.HasPrefix(st, "PRESEND LIVE PAUSED (fee budget)"):
		d.FeePaused, d.FeePausedAt = true, M.LogMin
		if m := rxFeePR.FindStringSubmatch(st); m != nil {
			d.Fee24, d.HasFee24 = lamF(m[1]), true
			d.Bud24, d.HasBud24 = lamF(m[2]), true
		}
		if m := rxFeePN.FindStringSubmatch(st); m != nil {
			d.FeePauses = max(d.FeePauses, atoi(m[1]))
		} else {
			d.FeePauses++
		}
		return true
	case strings.HasPrefix(st, "PRESEND LIVE RESUMED (fee budget)"):
		d.FeePaused = false
		if m := rxFeePR.FindStringSubmatch(st); m != nil {
			d.Fee24, d.HasFee24 = lamF(m[1]), true
			d.Bud24, d.HasBud24 = lamF(m[2]), true
		}
		return true
	}
	return false
}

// feedLine: the feed names a log line gives ("feeds: a, b" or "FEEDSTATUS feed=x"); true = consumed.
func (M *Model) feedLine(st string) bool {
	add := func(n string) {
		n = strings.Trim(n, " ,;")
		if n == "" || len(M.Feeds) >= 32 {
			return
		}
		for _, x := range M.Feeds {
			if x == n {
				return
			}
		}
		M.Feeds = append(M.Feeds, n)
	}
	switch {
	case strings.HasPrefix(st, "feeds: "):
		for _, x := range strings.Split(strings.TrimPrefix(st, "feeds: "), ",") {
			add(PyStrip(x))
		}
		return true
	case strings.HasPrefix(st, "FEEDSTATUS"):
		if m := rxFeedSt.FindStringSubmatch(st); m != nil {
			add(m[1])
		}
		return true
	}
	return false
}

// d24Status reads the dip24 parts of a "DIP status" line (cheap: each regex only after its marker is found).
func (M *Model) d24Status(S *Sess, st string) {
	d := &S.D24
	if strings.Contains(st, "| lock: ") {
		if m := rxLockSt.FindStringSubmatch(st); m != nil {
			d.HasLockSt = true
			d.LockPeak, d.LockFloor, d.LockGive, d.LockPnL = lamF(m[1]), lamF(m[2]), lamF(m[3]), lamF(m[4])
			d.LockMin = M.LogMin
		}
	}
	if strings.Contains(st, "| fees 24 h ") {
		if m := rxFee24.FindStringSubmatch(st); m != nil {
			d.HasFee24, d.Fee24 = true, lamF(m[1])
			d.HasBud24, d.Bud24 = true, lamF(m[2])
			d.FeePaused = m[3] != ""
			if m[4] != "" {
				d.FeePauses = max(d.FeePauses, atoi(m[4]))
			}
		}
	}
	if strings.Contains(st, "REGULAR PAPER: ") {
		if m := rxRegPaper.FindStringSubmatch(st); m != nil {
			d.HasRegP = true
			d.RegP = RegPaper{Picks: atoi(m[1]), Fills: atoi(m[2]), NoFill: atoi(m[3]), Exits: atoi(m[4]), Gross: mustFloat(m[5]), Net: mustFloat(m[6]), Open: atoi(m[7])}
			if d.RegMode == "" {
				d.RegMode = "paper"
			}
		}
	}
	if i := strings.Index(st, "| OBS: "); i >= 0 {
		o := &d.Obs
		o.HasLine, o.Min = true, M.LogMin
		o.Counts = o.Counts[:0]
		o.HasRec, o.WriteErr = false, 0
		for k, p := range strings.Split(st[i+7:], " | ") {
			p = PyStrip(p)
			if k == 0 {
				if m := rxObsHead.FindStringSubmatch(p); m != nil {
					o.Sent, o.Dropped, o.Queued, o.Done = atoi(m[1]), atoi(m[2]), atoi(m[3]), atoi(m[4])
					continue
				}
			}
			if m := rxObsRec.FindStringSubmatch(p); m != nil {
				o.HasRec = true
				o.Records, o.MB, o.Parts, o.P99, o.MemMB = atoi(m[1]), mustFloat(m[2]), atoi(m[3]), mustFloat(m[4]), atoi(m[5])
				continue
			}
			if m := rxObsErr.FindStringSubmatch(p); m != nil {
				o.WriteErr = atoi(m[1])
				continue
			}
			if m := rxObsCnt.FindStringSubmatch(p); m != nil && len(o.Counts) < 24 {
				f := strings.Fields(m[1])
				c := ObsCount{K: f[0], N: atoi(m[2])}
				if len(f) > 1 {
					c.Sub = f[1]
				}
				if m[3] != "" {
					c.Fills, c.HasFills = atoi(m[3]), true
				}
				o.Counts = append(o.Counts, c)
				continue
			}
			break // not an OBS part: the rest of the line belongs to something else
		}
	}
}

// ------------------------------------------------------------------------------------------------- the view

// LockView: the profit lock for the view: its setting, the peak, the level the run stops below, how far away.
type LockView struct {
	On        bool
	M         int64
	F         float64
	Peak      int64
	Floor     int64 // the run stops taking new buys below this run P&L
	PnL       int64 // the run P&L the floor is compared with (the engine's when it logged one, else ours)
	Dist      int64 // PnL - Floor
	Engine    bool  // peak / floor / PnL from the engine's status line (else computed from our P&L line)
	Fired     bool
	FirePeak  int64
	FireFloor int64
	FirePnL   int64
}

// LockFloor is the engine's lock_floor: give-back G = max(m, f x peak profit); floor = max(-cap, peak - G).
func LockFloor(peak, m int64, f float64, capL int64, hasCap bool) int64 {
	g := max(m, int64(f*float64(max(peak, 0))+0.5))
	fl := peak - g
	if hasCap && fl < -capL {
		fl = -capL
	}
	return fl
}

func (v *View) d24View(S *Sess) {
	d := &S.D24
	v.D24 = d
	v.NoTimeLimit = d.NoTime || (d.Limits && !v.Planned.Truthy())
	if d.HasLock || d.HasLockSt || d.LockFired {
		L := LockView{On: true, M: d.LockM, F: d.LockF}
		capL, hasCap := int64(0), v.LossCapN.Truthy()
		if hasCap {
			capL = v.LossCapN.Int()
		}
		if d.HasLockSt {
			L.Peak, L.Floor, L.PnL, L.Engine = d.LockPeak, d.LockFloor, d.LockPnL, true
		} else {
			// before the first status line: our own P&L line's high (the engine takes its peak from the balance)
			pk := int64(0)
			for _, x := range v.Series {
				pk = max(pk, x)
			}
			L.Peak, L.PnL = pk, v.STotal
			L.Floor = LockFloor(pk, d.LockM, d.LockF, capL, hasCap)
		}
		L.Dist = L.PnL - L.Floor
		if d.LockFired {
			L.Fired = true
			L.FirePeak, L.FireFloor, L.FirePnL = d.LockFire[0], d.LockFire[1], d.LockFire[3]
		}
		v.Lock = L
	}
}

// RegModeOf: the regular bot's mode for the view ("" = not logged).
func (v *View) RegModeOf() string {
	if v.D24 == nil {
		return ""
	}
	return v.D24.RegMode
}

// LockSetting is the profit lock's setting in words ("max(0.650 SOL, 30% of the peak)").
func (L LockView) LockSetting() string {
	return "max(" + F(float64(L.M)/LAM, 3) + " SOL, " + F(L.F*100, 0) + "% of the peak)"
}

// d24Items: the dip24 config items (only when the run logged them: older runs keep their items).
func d24Items(v *View, add func(key, label, state, short, full string)) {
	d := v.D24
	if d == nil || !d.Any() {
		return
	}
	if v.Lock.On {
		st := "on"
		if v.Lock.Fired {
			st = "part"
		}
		full := "give back " + v.Lock.LockSetting() + " " + G.Sep + " peak " + Sol(v.Lock.Peak, true, 4, true) + " " + G.Sep + " stops below " + Sol(v.Lock.Floor, true, 4, true)
		if v.Lock.Fired {
			full += " " + G.Sep + " FIRED"
		}
		add("lock", "Profit lock", st, "lock "+F(float64(v.Lock.M)/LAM, 2)+"/"+F(v.Lock.F*100, 0)+"%", full)
	} else if d.LockOff {
		add("lock", "Profit lock", "off", "lock off", "off")
	}
	if d.HasBud24 {
		st := "on"
		if d.FeePaused {
			st = "part"
		}
		short := "fee24 " + F(float64(d.Fee24)/LAM, 2) + "/" + F(float64(d.Bud24)/LAM, 2)
		full := F(float64(d.Fee24)/LAM, 4) + " / " + F(float64(d.Bud24)/LAM, 4) + " SOL failed-try fees in the last 24 h (pauses, never stops)"
		if d.FeePaused {
			short += " PAUSED"
			full += " " + G.Sep + " PAUSED"
		}
		if d.FeePauses > 0 {
			full += " " + G.Sep + " pauses " + Itoa(d.FeePauses)
		}
		add("fee24", "Fee budget 24 h", st, short, full)
	}
	if d.RegMode != "" {
		st := map[string]string{"live": "on", "paper": "part", "off": "off"}[d.RegMode]
		full := map[string]string{"live": "live (sends real buys)", "paper": "paper: decided as live, never sent", "off": "off: no regular buys"}[d.RegMode]
		if d.HasRegP {
			full += " " + G.Sep + " paper " + Itoa(d.RegP.Picks) + " picks, " + Itoa(d.RegP.Fills) + " fills, net " + FS(d.RegP.Net, 4)
		}
		add("regmode", "Regular mode", st, "REG "+d.RegMode, full)
	}
	if d.Limits {
		parts := []string{}
		lim := func(lbl, txt string, unl bool) {
			if unl {
				parts = append(parts, lbl+" no limit")
			} else if txt != "" && txt != "-" {
				parts = append(parts, lbl+" "+txt)
			}
		}
		lim("regular buys", d.RegTxt, d.RegUnl)
		lim("pre-send fills", d.PSFillsTxt, d.PSFillsUnl)
		if len(parts) > 0 {
			add("limits", "Trade limits", "na", "limits "+limShort(d), strings.Join(parts, " "+G.Sep+" "))
		}
	}
	if d.Obs.On || d.Obs.HasLine {
		add("obs", "Observatory", "on", "obs", "log only, never sends: "+strings.Join(d.Obs.Names, ", "))
	}
}

func limShort(d *D24Log) string {
	if d.RegUnl && d.PSFillsUnl {
		return "none"
	}
	r, p := d.RegTxt, d.PSFillsTxt
	if d.RegUnl {
		r = "-"
	}
	if d.PSFillsUnl {
		p = "-"
	}
	return r + "/" + p
}

// d24Alerts: the profit lock fired or near, the fee budget pause.
func d24Alerts(v *View, A []Alert) []Alert {
	d := v.D24
	if d == nil {
		return A
	}
	L := v.Lock
	switch {
	case L.Fired:
		A = append(A, Alert{"bad", "PROFIT LOCK stopped new buys (peak " + Sol(L.FirePeak, true, 3, true) + ", floor " + Sol(L.FireFloor, true, 3, true) + ", run P&L " + Sol(L.FirePnL, true, 3, true) + ")"})
	case L.On && v.Running && L.Peak > 0 && L.Dist < int64(0.10*LAM):
		A = append(A, Alert{"warn", "profit lock " + F(float64(L.Dist)/LAM, 3) + " SOL away (stops below " + Sol(L.Floor, true, 3, true) + ")"})
	}
	if d.Obs.WriteErr > 0 && v.Running {
		A = append(A, Alert{"warn", "observatory WRITE ERRORS " + Itoa(d.Obs.WriteErr)})
	}
	if d.FeePaused && v.Running {
		A = append(A, Alert{"warn", "pre-send PAUSED: 24 h fees " + F(float64(d.Fee24)/LAM, 3) + "/" + F(float64(d.Bud24)/LAM, 3) + " SOL (resumes as they roll off)"})
	}
	return A
}

// d24Text: the snapshot's dip24 lines (none for older runs).
func d24Text(v *View) []string {
	d := v.D24
	if d == nil || !d.Any() {
		return nil
	}
	var out []string
	if d.Limits || d.HasBud24 {
		t := "no limit"
		if !v.NoTimeLimit && v.Planned.Truthy() {
			t = HMS(v.Planned.Float()*60, true, false)
		}
		parts := []string{"time " + t}
		nl := func(txt string, unl bool) string {
			if unl {
				return "no limit"
			}
			if txt == "" {
				return "?"
			}
			return txt
		}
		if d.Limits {
			parts = append(parts, "regular buys "+nl(d.RegTxt, d.RegUnl), "pre-send fills "+nl(d.PSFillsTxt, d.PSFillsUnl))
		}
		if d.HasBud24 {
			f := "fee budget 24 h " + F(float64(d.Fee24)/LAM, 4) + "/" + F(float64(d.Bud24)/LAM, 4) + " SOL"
			if d.FeePaused {
				f += " PAUSED"
			}
			if d.FeePauses > 0 {
				f += " (pauses " + Itoa(d.FeePauses) + ")"
			}
			parts = append(parts, f)
		}
		out = append(out, "limits    "+strings.Join(parts, ", "))
	}
	if L := v.Lock; L.On {
		src := ""
		if !L.Engine {
			src = " (est.)"
		}
		line := "lock      give back " + L.LockSetting() + "; peak " + Sol(L.Peak, true, 4, true) + ", stops below " + Sol(L.Floor, true, 4, true) +
			", run P&L " + Sol(L.PnL, true, 4, true) + " (" + F(float64(L.Dist)/LAM, 3) + " SOL away)" + src
		if L.Fired {
			line += "; STOPPED by profit lock (peak " + Sol(L.FirePeak, true, 4, true) + ", floor " + Sol(L.FireFloor, true, 4, true) + ")"
		}
		out = append(out, line)
	}
	if d.RegMode != "" {
		line := "reg mode  " + d.RegMode
		if d.HasRegP {
			p := d.RegP
			line += ": picks " + Itoa(p.Picks) + ", fills " + Itoa(p.Fills) + " (no-fill " + Itoa(p.NoFill) + "), exits " + Itoa(p.Exits) +
				", paper P&L " + FS(p.Gross, 4) + " gross / " + FS(p.Net, 4) + " net, open " + Itoa(p.Open)
		}
		out = append(out, line)
	}
	if o := d.Obs; o.On || o.HasLine {
		line := "observ.   log only"
		if o.HasLine {
			line += ": " + strings.Join(ObsCountsTextLive(o.Counts, v.RA.On), ", ")
			if o.HasRec {
				line += "; " + IC(o.Records) + " records " + F(o.MB, 1) + " MB, p99 " + F(o.P99, 1) + " us/msg"
			}
			if o.Dropped > 0 {
				line += "; DROPPED " + IC(o.Dropped)
			}
			if o.WriteErr > 0 {
				line += "; WRITE ERRORS " + IC(o.WriteErr)
			}
		} else if len(o.Names) > 0 {
			line += ": " + strings.Join(o.Names, ", ") + " (no status line yet)"
		}
		out = append(out, line)
	}
	return out
}

// ObsName: an observatory counter's display name.
func ObsName(k string) string {
	switch k {
	case "rearm":
		return "re-arm"
	case "mig":
		return "migration"
	case "race":
		return "feed race"
	case "inslot":
		return "INSLOT"
	}
	return k
}

// ObsCountsText: "re-arm 106 windows / 88 fills", "hold 47", ...
func ObsCountsText(cs []ObsCount) []string { return ObsCountsTextLive(cs, false) }

// ObsLabel: an observatory counter's name; with the live re-arm on (dip26), its re-arm shadow is "paper re-arm".
func ObsLabel(k string, liveRearm bool) string {
	if k == "rearm" && liveRearm {
		return "paper re-arm"
	}
	return ObsName(k)
}

// ObsCountsTextLive is ObsCountsText with the live re-arm's label rule.
func ObsCountsTextLive(cs []ObsCount, liveRearm bool) []string {
	out := make([]string, 0, len(cs))
	for _, c := range cs {
		s := ObsLabel(c.K, liveRearm) + " " + IC(c.N)
		if c.Sub != "" {
			s += " " + c.Sub
		}
		if c.HasFills {
			s += " / " + IC(c.Fills) + " fills"
		}
		out = append(out, s)
	}
	return out
}

// d24JSON: the snapshot JSON's "dip24" object (only when the run logged dip24 lines).
func d24JSON(v *View, d *JObj) {
	x := v.D24
	if x == nil || !x.Any() {
		return
	}
	o := &JObj{}
	o.Set("no_time_limit", v.NoTimeLimit)
	o.Set("regular_buys_unlimited", x.RegUnl)
	o.Set("presend_fills_unlimited", x.PSFillsUnl)
	if L := v.Lock; L.On {
		l := &JObj{}
		l.Set("min_lamports", L.M)
		l.Set("frac", PyFloat(L.F))
		l.Set("peak_lamports", L.Peak)
		l.Set("floor_lamports", L.Floor)
		l.Set("pnl_lamports", L.PnL)
		l.Set("distance_lamports", L.Dist)
		l.Set("from_engine", L.Engine)
		l.Set("fired", L.Fired)
		o.Set("profit_lock", l)
	} else {
		o.Set("profit_lock", nil)
	}
	if x.HasBud24 {
		f := &JObj{}
		f.Set("fees_lamports", x.Fee24)
		f.Set("budget_lamports", x.Bud24)
		f.Set("paused", x.FeePaused)
		f.Set("pauses", x.FeePauses)
		o.Set("fee_budget_24h", f)
	} else {
		o.Set("fee_budget_24h", nil)
	}
	o.Set("regular_mode", optStr(x.RegMode))
	if x.Obs.HasLine {
		ob := &JObj{}
		for _, c := range x.Obs.Counts {
			ob.Set(c.K, c.N)
		}
		ob.Set("records", x.Obs.Records)
		ob.Set("dropped", x.Obs.Dropped)
		o.Set("observatory", ob)
	} else {
		o.Set("observatory", nil)
	}
	d.Set("dip24", o)
}

// inferD24: the build when the records / log are dip24's (no process to ask).
func inferD24(S *Sess) bool { return S.D24.Any() }
