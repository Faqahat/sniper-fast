package core

import (
	"math"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/mattn/go-runewidth"
)

var (
	rxReal     = regexp.MustCompile(`^\s*REALIZED mint=(\S+) pnl=([-+]?[\d.]+) SOL source=(\S+)(?: run_realized=([-+]?[\d.]+) SOL)?`)
	rxStart    = regexp.MustCompile(`START BALANCE ([\d.]+) SOL; kill switch below ([\d.]+) SOL`)
	rxDone     = regexp.MustCompile(`fired (\d+) closed (\d+) landed buys (\d+) realized ([-+]?[\d.]+) SOL`)
	rxKill     = regexp.MustCompile(`DIP KILL-SWITCH: run PnL ([-+]?[\d.]+) SOL`)
	rxRT       = regexp.MustCompile(`RUNTIME lag 60s .*?n=(\d+) p50=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms`)
	rxRPC      = regexp.MustCompile(`RPC-LAT 60s (\S+) (\S+): n=(\d+) p50=([\d.]+)ms p90=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms timeouts/transport=(\d+)`)
	rxKA       = regexp.MustCompile(`^keepalive: (\S+) keep-alive: (.*)`)
	rxSP       = regexp.MustCompile(`SEND-PATH (\S+) UNHEALTHY`)
	rxPSFee    = regexp.MustCompile(`failed-attempt fees ([\d.]+) ?/ ?([\d.]+)`)
	rxStopped  = regexp.MustCompile(`PRESEND LIVE STOPPED \((\w+)\)`)
	rxFills    = regexp.MustCompile(`fills (\d+) ?/ ?(\d+)`)
	rxEndChk   = regexp.MustCompile(`END CHECK: (\d+) mint\(s\) read at confirmed: (\d+) sold now, (\d+) empty account\(s\) closed, (\d+) held / (\d+) unreadable`)
	rxPSReal   = regexp.MustCompile(`PRESEND LIVE REALIZED (\S+) ([-+]?[\d.]+) SOL`)
	rxShadow   = regexp.MustCompile(`PRESEND shadow: .*?fills (\d+)/(\d+)/(\d+) exits .*?gross ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+) SOL net\([^)]*\) ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+)`)
	rxStReg    = regexp.MustCompile(`fired (\d+) closed (\d+) open (\d+) slot \d+ skipped (\{[^}]*\})`)
	rxStPS     = regexp.MustCompile(`PRESEND LIVE( DRY)?(?: STOPPED \((\w+)\))?: triggers (\d+) armed (\d+) \(now (\d+)\)`)
	rxStQ      = regexp.MustCompile(`QUIET: skips (\d+) \(would-skip in the warm-up (\d+)\) stops (\d+) \| arm rule (.*?) \| signals`)
	rxStQPre   = regexp.MustCompile(`\| preload (running|done \(([\d.]+) s, ([\d.]+) h\)|FAILED)`)
	rxHHMM     = regexp.MustCompile(`(\d{1,2}):(\d{2}) PKT`)
	rxDev      = regexp.MustCompile(`(\d+) wallet\(s\).*?spend ([\d.]+) SOL`)
	rxNear     = regexp.MustCompile(`(\d+) leaders`)
	rxNonce    = regexp.MustCompile(`ON: (\d+)`)
	rxRoute    = regexp.MustCompile(`^snipe_engine: ROUTE (\S+)\s+-> (.+)$`)
	rxSellFan  = regexp.MustCompile(`goes to (\S+) AND (\S+?)[ (]`)
	rxPreH     = regexp.MustCompile(`([\d.]+) h of history`)
	rxPreOn    = regexp.MustCompile(`(?:arm rule on at|on at) (\d{1,2}):(\d{2}) PKT`)
	rxLModel   = regexp.MustCompile(`^model (\S+) tier (\S+)`)
	rxLExit    = regexp.MustCompile(`^exit TP (\S+) / SL -?([\d.]+)% / (\d+) slots`)
	rxLGuard   = regexp.MustCompile(`^guard x([\d.]+)`)
	rxLSpend   = regexp.MustCompile(`^spend ([\d.]+) SOL`)
	rxLMaxBuys = regexp.MustCompile(`^max buys (\d+)`)
	rxLLoss    = regexp.MustCompile(`^loss cap ([\d.]+) SOL`)
	rxLMin     = regexp.MustCompile(`^(\d+) min$`)
	rxQStop    = regexp.MustCompile(`stop at trigger \+ (\d+) slots with < (\d+) other trades`)
	rxQStopOff = regexp.MustCompile(`stop off`)
	rxQSkip    = regexp.MustCompile(`\| skip (on|off)`)
	rxQArm     = regexp.MustCompile(`arm rule from (\d{1,2}):(\d{2}) PKT \(warm-up ([\d.]+) min\)`)
	rxParen    = regexp.MustCompile(`\(.*?\)`)
	rxCtrl     = regexp.MustCompile(`[\x00-\x08\x0b-\x1f\x7f]`)
	rxSecret   = regexp.MustCompile(`(?i)((?:api[-_]?key|token|secret|auth|passw(?:or)?d|key)=)[^&\s"']+`)
	rxUserinfo = regexp.MustCompile(`(://)[^/\s:@]+:[^/\s@]+@`)
)

// important: a log line containing any of these (and not a "DIP status" line) goes to the important list.
var important = []string{"PRESEND LIVE FILL", "PRESEND LIVE EXIT", "PRESEND LIVE REALIZED", "REALIZED mint=", "DIP FIRE",
	"DIP BUY", "DIP EXIT", "KILL", "SIGNAL", "STOPPED", "END CHECK", "QUIET", "START BALANCE", "DIP LIVE |", "=== DIP DONE",
	"Error", "panicked", "UNHEALTHY", "UNSOLD", "SELL-FAIL", "SELL-GIVE", "SELL-STUCK", "refused", "DIP PRESEND LIVE"}

// pyFloat is Python's float() on a regex-matched number ("1.", ".5" ok; "." or "1.2.3" raise).
func pyFloat(s string) (float64, bool) {
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0, false
	}
	return f, true
}

// lamOf is int(round(float(s) * LAM)) (round half to even, like Python's round()).
func lamOf(s string) (int64, bool) {
	f, ok := pyFloat(s)
	if !ok {
		return 0, false
	}
	return int64(math.RoundToEven(f * LAM)), true
}

func atoi(s string) int64 {
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		panic("int() of " + s) // Python: ValueError -> the line counts as bad
	}
	return v
}

func mustLam(s string) int64 {
	v, ok := lamOf(s)
	if !ok {
		panic("float() of " + s)
	}
	return v
}

func mustFloat(s string) float64 {
	v, ok := pyFloat(s)
	if !ok {
		panic("float() of " + s)
	}
	return v
}

// decodeReplace is bytes.decode("utf-8", "replace").
func decodeReplace(b []byte) string {
	if utf8.Valid(b) {
		return string(b)
	}
	var sb strings.Builder
	for len(b) > 0 {
		r, n := utf8.DecodeRune(b)
		if r == utf8.RuneError && n <= 1 {
			sb.WriteRune(0xfffd)
			b = b[1:]
			continue
		}
		sb.WriteRune(r)
		b = b[n:]
	}
	return sb.String()
}

// FeedLog parses text log lines.
func (M *Model) FeedLog(lines [][]byte) {
	if M.LiveLog {
		M.tLive = float64(time.Now().UnixNano()) / 1e9
	} else {
		M.tLive = 0
	}
	for _, raw := range lines {
		M.LLines++
		s := strings.TrimRight(decodeReplace(raw), "\r")
		M.logLineSafe(s)
	}
	M.Version++
}

func (M *Model) logLineSafe(s string) {
	defer func() {
		if r := recover(); r != nil {
			M.Bad++
		}
	}()
	M.logLine(s)
}

var condNarrow = func() *runewidth.Condition {
	c := runewidth.NewCondition()
	c.EastAsianWidth = false
	return c
}()

// Clean makes a log line safe to show: no control chars, no wide / emoji / combining chars, secrets masked.
func Clean(s string) string {
	s = strings.ReplaceAll(s, "\t", "  ")
	s = rxCtrl.ReplaceAllString(s, "?")
	if strings.Contains(s, "=") {
		s = rxSecret.ReplaceAllString(s, "${1}***")
	}
	if strings.Contains(s, "@") {
		s = rxUserinfo.ReplaceAllString(s, "${1}***@")
	}
	ascii := true
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			ascii = false
			break
		}
	}
	if ascii {
		return s
	}
	var b strings.Builder
	for _, r := range s {
		switch {
		case r < 128:
			b.WriteRune(r)
		case G.ASCII:
			b.WriteByte('?')
		case r >= 0x1F000 || condNarrow.RuneWidth(r) == 2 || unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Co, unicode.Cs) ||
			!unicode.In(r, unicode.L, unicode.M, unicode.N, unicode.P, unicode.S, unicode.Z, unicode.Cc):
			b.WriteByte('?')
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

func (M *Model) logLine(s string) {
	st := PyStrip(s)
	if st == "" {
		return
	}
	item := LogItem{Text: Clean(RuneSlice(st, 1000)), Sess: M.lsess, SMin: M.LogSMin, TLive: M.tLive}
	M.LogRing.Push(item)
	if !strings.HasPrefix(st, "DIP status") {
		for _, k := range important {
			if strings.Contains(st, k) {
				M.LogImp.Push(item)
				break
			}
		}
	}
	c0, _ := utf8.DecodeRuneInString(st)
	// ---- engine start / session boundaries
	if strings.HasPrefix(st, "WARNING: date >=") || (strings.HasPrefix(st, "snipe_engine: payer") && !M.recentStart) {
		M.EngineStarts++
		M.SegLive = false
		M.lpend = LogCfg{}
		M.recentStart = true
		M.segLines = 0
		return
	}
	M.segLines++
	if M.segLines > 5 {
		M.recentStart = false
	}
	if strings.HasPrefix(st, "DIP LIVE |") {
		M.lsess++
		M.LogSMin = 0
		M.SegLive = true
		S := M.lcur()
		mergeCfg(&S.Cfg, &M.lpend)
		M.lpend = LogCfg{}
		S.Live, S.HasLive = parseLive(st), true
		return
	}
	var tgt *LogCfg
	if M.SegLive {
		tgt = &M.lcur().Cfg
	} else {
		tgt = &M.lpend
	}
	S := M.lcur()
	if c0 == 'R' {
		if strings.HasPrefix(st, "RUNTIME lag") {
			if m := rxRT.FindStringSubmatch(st); m != nil {
				M.Runtime = [3]float64{mustFloat(m[2]), mustFloat(m[3]), mustFloat(m[4])}
				M.HasRuntime = true
				M.RuntimeWorst = math.Max(M.RuntimeWorst, M.Runtime[1])
			}
			M.LogMin++
			M.LogSMin++
			M.prune()
			return
		}
		if strings.HasPrefix(st, "RPC-LAT") {
			if m := rxRPC.FindStringSubmatch(st); m != nil {
				k := [2]string{m[1], m[2]}
				r := M.RPC[k]
				if r == nil {
					r = &RPCStat{}
					M.RPC[k] = r
					M.RPCOrder = append(M.RPCOrder, k)
				}
				r.N, r.P50, r.P99, r.Mx, r.Min = atoi(m[3]), mustFloat(m[4]), mustFloat(m[6]), mustFloat(m[7]), M.LogMin
				to := atoi(m[8])
				r.TO += to
				r.TOLast = to
			}
			return
		}
		if strings.HasPrefix(st, "REALIZED mint=") {
			if m := rxReal.FindStringSubmatch(st); m != nil {
				pnl := mustLam(m[2])
				if m[4] != "" {
					S.EngineRealized, S.HasEngineReal = mustLam(m[4]), true
				}
				S2 := M.Sess(M.lsess)
				S2.RealQ[m[1]] = append(S2.RealQ[m[1]], pnl)
				M.reconcile(S2, m[1])
			}
			return
		}
	}
	if c0 == 'D' && strings.HasPrefix(st, "DIP status") {
		M.statusLine(S, st)
		return
	}
	if c0 == 'P' {
		if strings.HasPrefix(st, "PRESEND LIVE") {
			M.psLog(S, st)
			return
		}
		if strings.HasPrefix(st, "POLL-RPC-ERROR") {
			M.PollErr[M.LogMin]++
			M.PollErrTotal++
			return
		}
	}
	if c0 == 'k' && strings.HasPrefix(st, "keepalive:") {
		if m := rxKA.FindStringSubmatch(st); m != nil {
			msg := strings.ToLower(m[2])
			kind := ""
			switch {
			case strings.Contains(msg, "refused"):
				kind = "refused"
			case strings.Contains(msg, "timed out") || strings.Contains(msg, "timeout") || strings.Contains(msg, "deadline"):
				kind = "timeout"
			case strings.Contains(msg, "error") || strings.Contains(msg, "fail"):
				kind = "error"
			}
			if kind != "" {
				M.pathErr(m[1], kind)
			}
		}
		return
	}
	if c0 == 'S' {
		if strings.HasPrefix(st, "SEND-PATH") {
			if m := rxSP.FindStringSubmatch(st); m != nil {
				M.pathErr(m[1], "unhealthy")
			}
			return
		}
		if strings.HasPrefix(st, "START BALANCE") {
			if m := rxStart.FindStringSubmatch(st); m != nil {
				a, b := mustLam(m[1]), mustLam(m[2])
				S.StartBal, S.HasStartBal = a, true
				S.KillLevel, S.HasKillLevel = b, true
			}
			return
		}
		if strings.HasPrefix(st, "SIGNAL") {
			S.Signal = strings.ReplaceAll(strings.SplitN(st, ":", 2)[0], "SIGNAL ", "")
			S.HasSignal = true
			return
		}
	}
	if c0 == 'D' {
		if strings.HasPrefix(st, "DIP PRESEND LIVE QUIET") {
			parseQuietInto(&S.Quiet, st)
			return
		}
		if strings.HasPrefix(st, "DIP PRESEND LIVE") {
			S.PSL = parsePSL(st)
			return
		}
		if strings.HasPrefix(st, "DIP KILL-SWITCH") {
			S.KillSet = true
			if m := rxKill.FindStringSubmatch(st); m != nil {
				S.Kill, S.KillIsFloat = mustFloat(m[1]), true
			} else {
				S.Kill, S.KillIsFloat = 0, false
			}
			return
		}
		if strings.HasPrefix(st, "DIP PRESEND SHADOW") {
			tgt.Shadow = true
			return
		}
		if strings.HasPrefix(st, "DIP M2") {
			switch {
			case strings.Contains(st, " GATE"):
				tgt.M2 = "gate"
			case strings.Contains(strings.ToUpper(st), "SHADOW"):
				tgt.M2 = "shadow"
			default:
				tgt.M2 = "on"
			}
			return
		}
		if strings.HasPrefix(st, "DIP dev list") {
			if m := rxDev.FindStringSubmatch(st); m != nil {
				tgt.Dev, tgt.DevTrue = &DevList{N: atoi(m[1]), Size: mustFloat(m[2])}, false
			} else {
				tgt.Dev, tgt.DevTrue = nil, true
			}
			return
		}
		if strings.HasPrefix(st, "DIP near-leader gate") {
			if m := rxNear.FindStringSubmatch(st); m != nil {
				tgt.Near, tgt.NearSet, tgt.NearTrue = atoi(m[1]), true, false
			} else {
				tgt.NearSet, tgt.NearTrue = true, true
			}
			return
		}
		if strings.HasPrefix(st, "DIP SKIP CLIENTS") {
			if strings.Contains(st, "leader is") {
				p := strings.SplitN(st, "leader is", 2)
				tgt.SkipClients = PyStrip(p[len(p)-1])
			} else {
				tgt.SkipClients = "on"
			}
			tgt.HasSkipClients = true
			return
		}
		if strings.HasPrefix(st, "DIP BUY") || strings.HasPrefix(st, "DIP FIRE") {
			return
		}
	}
	if c0 == '=' {
		if strings.HasPrefix(st, "=== DIP DONE") {
			if m := rxDone.FindStringSubmatch(st); m != nil {
				d := &Done{Fired: atoi(m[1]), Closed: atoi(m[2]), Landed: atoi(m[3]), Realized: mustLam(m[4]), Parsed: true}
				S.Done = d
				S.EngineRealized, S.HasEngineReal = d.Realized, true
			} else {
				S.Done = &Done{}
			}
			return
		}
		if strings.HasPrefix(st, "=== DIP PRESEND:") {
			if m := rxShadow.FindStringSubmatch(st); m != nil {
				S.Paper = &Paper{Fills: atoi(m[3]), Gross: mustFloat(m[6]), Net: mustFloat(m[9])}
			}
			return
		}
		if strings.HasPrefix(st, "=== DIP PRESEND LIVE") {
			if m := rxPSFee.FindStringSubmatch(st); m != nil {
				S.LogPSFees = max(S.LogPSFees, mustLam(m[1]))
			}
			return
		}
	}
	if c0 == 'N' && strings.HasPrefix(st, "NONCE-FANOUT") {
		if m := rxNonce.FindStringSubmatch(st); m != nil {
			tgt.Nonce, tgt.NonceSet, tgt.NonceTrue = atoi(m[1]), true, false
		} else if strings.Contains(st, "OFF") {
			tgt.Nonce, tgt.NonceSet, tgt.NonceTrue = 0, true, false
		} else {
			tgt.NonceSet, tgt.NonceTrue = true, true
		}
		return
	}
	if c0 == 's' {
		if strings.HasPrefix(st, "snipe_engine: ROUTE") {
			if m := rxRoute.FindStringSubmatch(st); m != nil {
				if tgt.Routes == nil {
					tgt.Routes = map[string][]string{}
				}
				var parts []string
				for _, x := range strings.Split(m[2], "+") {
					if x = PyStrip(x); x != "" {
						parts = append(parts, x)
					}
				}
				tgt.Routes[m[1]] = parts
			}
			return
		}
		if strings.HasPrefix(st, "snipe_engine: SELL FAN-OUT") {
			if m := rxSellFan.FindStringSubmatch(st); m != nil {
				tgt.SellFan, tgt.SellFanTrue = m[2], false
			} else {
				tgt.SellFan, tgt.SellFanTrue = "", true
			}
			return
		}
	}
	if c0 == 'Q' && strings.HasPrefix(st, "QUIET preload") {
		switch {
		case strings.Contains(st, "preload done"):
			S.Quiet.Preload = "done"
		case strings.Contains(st, "FAILED"):
			S.Quiet.Preload = "failed"
		}
		if m := rxPreH.FindStringSubmatch(st); m != nil {
			S.Quiet.PreloadH = FloatNum(mustFloat(m[1]))
		}
		if strings.Contains(st, "arm rule on now") {
			S.Quiet.RuleState = "on"
		} else if m := rxPreOn.FindStringSubmatch(st); m != nil {
			S.Quiet.OnHHMM, S.Quiet.HasOnHHMM = [2]int{int(atoi(m[1])), int(atoi(m[2]))}, true
		}
		return
	}
	if c0 == 'E' && strings.HasPrefix(st, "Error:") {
		if !M.SegLive {
			M.Refused = append(M.Refused, RuneSlice(st, 200))
		} else {
			S.Errors = append(S.Errors, RuneSlice(st, 200))
		}
		return
	}
	if strings.Contains(st, "panicked") {
		M.Panics = append(M.Panics, RuneSlice(st, 200))
	}
}

// mergeCfg is S.cfg.update(lpend): only the keys lpend has.
func mergeCfg(dst, src *LogCfg) {
	if src.Shadow {
		dst.Shadow = true
	}
	if src.M2 != "" {
		dst.M2 = src.M2
	}
	if src.Dev != nil || src.DevTrue {
		dst.Dev, dst.DevTrue = src.Dev, src.DevTrue
	}
	if src.NearSet {
		dst.Near, dst.NearSet, dst.NearTrue = src.Near, true, src.NearTrue
	}
	if src.HasSkipClients {
		dst.SkipClients, dst.HasSkipClients = src.SkipClients, true
	}
	if src.NonceSet {
		dst.Nonce, dst.NonceSet, dst.NonceTrue = src.Nonce, true, src.NonceTrue
	}
	if src.Routes != nil {
		dst.Routes = src.Routes
	}
	if src.SellFan != "" || src.SellFanTrue {
		dst.SellFan, dst.SellFanTrue = src.SellFan, src.SellFanTrue
	}
}

func (M *Model) psLog(S *Sess, st string) {
	if m := rxPSFee.FindStringSubmatch(st); m != nil {
		S.LogPSFees = max(S.LogPSFees, mustLam(m[1]))
	}
	switch {
	case strings.HasPrefix(st, "PRESEND LIVE STOPPED"):
		p := &PSStoppedLine{Why: "?"}
		if m := rxStopped.FindStringSubmatch(st); m != nil {
			p.Why = m[1]
		}
		if f := rxFills.FindStringSubmatch(st); f != nil {
			p.Fills, p.Cap, p.HasFills = atoi(f[1]), atoi(f[2]), true
		}
		S.PSStopped = p
	case strings.HasPrefix(st, "PRESEND LIVE END CHECK"):
		if m := rxEndChk.FindStringSubmatch(st); m != nil {
			e := [5]int64{}
			for i := 0; i < 5; i++ {
				e[i] = atoi(m[i+1])
			}
			S.EndCheck = &e
		}
	case strings.HasPrefix(st, "PRESEND LIVE REALIZED"):
		if m := rxPSReal.FindStringSubmatch(st); m != nil {
			S.LogPSReal = append(S.LogPSReal, mustLam(m[2]))
		}
	}
}

func (M *Model) statusLine(S *Sess, st string) {
	d := Status{}
	if m := rxStReg.FindStringSubmatch(st); m != nil {
		d.HasReg = true
		d.Fired, d.Closed, d.Open = atoi(m[1]), atoi(m[2]), atoi(m[3])
		if sk, ok := parseIntDict(m[4]); ok {
			d.Skipped = sk
		}
	}
	if m := rxStPS.FindStringSubmatchIndex(st); m != nil {
		g := func(i int) string {
			if m[2*i] < 0 {
				return ""
			}
			return st[m[2*i]:m[2*i+1]]
		}
		d.HasPS = true
		d.PSDry = m[2] >= 0
		d.PSStopped = g(2)
		d.PSTriggers, d.PSArmed, d.PSNow = atoi(g(3)), atoi(g(4)), atoi(g(5))
		rest := st[m[1]:]
		if f := rxFills.FindStringSubmatch(rest); f != nil {
			d.HasFills = true
			d.PSFills, d.PSCap = atoi(f[1]), atoi(f[2])
		}
		if fe := rxPSFee.FindStringSubmatch(rest); fe != nil {
			d.HasFee = true
			d.PSFee, d.PSBudget = mustFloat(fe[1]), mustFloat(fe[2])
			S.LogPSFees = max(S.LogPSFees, mustLam(fe[1]))
		}
	}
	if m := rxShadow.FindStringSubmatch(st); m != nil {
		S.Paper = &Paper{Fills: atoi(m[3]), Gross: mustFloat(m[6]), Net: mustFloat(m[9])}
	}
	if m := rxStQ.FindStringSubmatch(st); m != nil {
		d.HasQ = true
		d.QSkips, d.QWould, d.QStops = atoi(m[1]), atoi(m[2]), atoi(m[3])
		rule := m[4]
		d.QRule = rule
		switch {
		case strings.HasPrefix(rule, "on"):
			S.Quiet.RuleState = "on"
		case rule == "off":
			S.Quiet.RuleState = "off"
		default:
			S.Quiet.RuleState = "warm-up"
		}
		if h := rxHHMM.FindStringSubmatch(rule); h != nil {
			S.Quiet.OnHHMM, S.Quiet.HasOnHHMM = [2]int{int(atoi(h[1])), int(atoi(h[2]))}, true
		}
		if p := rxStQPre.FindStringSubmatch(st); p != nil {
			switch {
			case p[1] == "running":
				S.Quiet.Preload = "running"
			case strings.HasPrefix(p[1], "done"):
				S.Quiet.Preload = "done"
			default:
				S.Quiet.Preload = "failed"
			}
			if p[3] != "" {
				S.Quiet.PreloadH = FloatNum(mustFloat(p[3]))
			}
		}
	}
	d.Min = M.LogMin
	S.Status = d
}

// parseIntDict parses the status line's skipped dict ({"x": 3, ...}) in key order; ok=false: not valid JSON.
func parseIntDict(s string) (*OCounter, bool) {
	o, isObj, ok := DecodeObj([]byte(s))
	if !ok || !isObj {
		return nil, false
	}
	keys := orderedKeys(s, o)
	c := NewOCounter()
	for _, k := range keys {
		v := o[k]
		if b, isBool := v.(bool); isBool { // Python: isinstance(True, int)
			if b {
				c.Add(k, 1)
			} else {
				c.Add(k, 0)
			}
			continue
		}
		if n := toNum(v); n.K == NumInt {
			c.Add(k, n.I)
		}
	}
	return c, true
}

// orderedKeys returns an object's keys in their source order (the last duplicate's position wins in Python too,
// but the first position is kept; fine for the engine's flat dicts).
func orderedKeys(src string, o Obj) []string {
	type kp struct {
		k   string
		pos int
	}
	var ks []kp
	for k := range o {
		pos := strings.Index(src, strconv.Quote(k))
		if pos < 0 {
			pos = len(src)
		}
		ks = append(ks, kp{k, pos})
	}
	for i := 1; i < len(ks); i++ {
		for j := i; j > 0 && ks[j].pos < ks[j-1].pos; j-- {
			ks[j], ks[j-1] = ks[j-1], ks[j]
		}
	}
	out := make([]string, len(ks))
	for i, x := range ks {
		out[i] = x.k
	}
	return out
}

func (M *Model) pathErr(path, kind string) {
	c := M.PathErr[path]
	if c == nil {
		c = map[int]int64{}
		M.PathErr[path] = c
	}
	c[M.LogMin]++
	M.PathKind[path] = kind
	M.PathTotal[path]++
}

func (M *Model) prune() {
	lim := M.LogMin - 70
	if lim <= 0 {
		return
	}
	for k := range M.PollErr {
		if k < lim {
			delete(M.PollErr, k)
		}
	}
	for _, c := range M.PathErr {
		for k := range c {
			if k < lim {
				delete(c, k)
			}
		}
	}
}

// LogTime is a log line's time: (ns, exact). Read live: its arrival; read in the initial load: its session
// start + its minute in the session.
func (M *Model) LogTime(it LogItem) (float64, bool) {
	if it.TLive != 0 {
		return it.TLive * 1e9, true
	}
	ls := it.Sess
	if ls < 0 {
		ls = 0
	}
	if ls >= len(M.Sessions) || M.Sessions[ls].T0 == 0 {
		return 0, false
	}
	return float64(M.Sessions[ls].T0) + float64(it.SMin)*60e9, false
}

func parseLive(st string) LiveCfg {
	d := LiveCfg{}
	parts := strings.Split(st, " | ")
	for _, part := range parts[1:] {
		p := PyStrip(part)
		if m := rxLModel.FindStringSubmatch(p); m != nil {
			d.Model, d.Tier, d.HasModel = m[1], m[2], true
			continue
		}
		if m := rxLExit.FindStringSubmatch(p); m != nil {
			d.TP, d.HasTP = m[1], true
			d.SL, d.HasSL = mustFloat(m[2]), true
			d.Hold, d.HasHold = atoi(m[3]), true
			continue
		}
		if m := rxLGuard.FindStringSubmatch(p); m != nil {
			d.Guard, d.HasGuard = mustFloat(m[1]), true
			continue
		}
		if m := rxLSpend.FindStringSubmatch(p); m != nil {
			d.Spend, d.HasSpend = mustLam(m[1]), true
			continue
		}
		if m := rxLMaxBuys.FindStringSubmatch(p); m != nil {
			d.MaxBuys, d.HasMaxBuys = atoi(m[1]), true
			continue
		}
		if m := rxLLoss.FindStringSubmatch(p); m != nil {
			d.LossCap, d.HasLossCap = mustLam(m[1]), true
			continue
		}
		if m := rxLMin.FindStringSubmatch(p); m != nil {
			d.Minutes, d.HasMinutes = atoi(m[1]), true
		}
	}
	return d
}

// parsePSL parses "DIP PRESEND LIVE (REAL attempts) | ..." into the keys it has (Num / string / bool values).
func parsePSL(st string) map[string]any {
	d := map[string]any{}
	head := strings.SplitN(st, "|", 2)[0]
	d["dry"] = strings.HasPrefix(st, "DIP PRESEND LIVE DRY") || strings.Contains(head, " DRY")
	type rule struct {
		k  string
		rx *regexp.Regexp
		f  func(string) (any, bool)
	}
	intF := func(x string) (any, bool) {
		v, err := strconv.ParseInt(x, 10, 64)
		if err != nil {
			return nil, false
		}
		return IntNum(v), true
	}
	floatF := func(x string) (any, bool) {
		v, ok := pyFloat(x)
		if !ok {
			return nil, false
		}
		return FloatNum(v), true
	}
	lamF := func(x string) (any, bool) {
		v, ok := lamOf(x)
		if !ok {
			return nil, false
		}
		return IntNum(v), true
	}
	rules := []rule{
		{"k", regexp.MustCompile(`(\d+) attempts per slot`), intF},
		{"spend", regexp.MustCompile(`([\d.]+) SOL, limit`), lamF},
		{"limit", regexp.MustCompile(`price x ([\d.]+)`), floatF},
		{"fail_fee", regexp.MustCompile(`a failed attempt (\d+) lamports`), intF},
		{"routes", regexp.MustCompile(`routes (\S+)`), func(x string) (any, bool) { return rxParen.ReplaceAllString(x, ""), true }},
		{"max_fills", regexp.MustCompile(`caps: (\d+) fills`), intF},
		{"fee_budget", regexp.MustCompile(`caps: \d+ fills, fees ([\d.]+) SOL`), lamF},
		{"exit_slots", regexp.MustCompile(`exit (\d+) slots`), intF},
		{"tp", regexp.MustCompile(`TP \+?([\d.]+)%`), floatF},
		{"sl", regexp.MustCompile(`SL -?([\d.]+)%`), floatF},
	}
	for _, r := range rules {
		if m := r.rx.FindStringSubmatch(st); m != nil {
			if v, ok := r.f(m[1]); ok {
				d[r.k] = v
			}
		}
	}
	return d
}

// parseQuietInto is S.quiet.update(_parse_quiet(st)).
func parseQuietInto(q *QuietLog, st string) {
	q.Line = true
	if m := rxQStop.FindStringSubmatch(st); m != nil {
		q.Stop, q.HasStop = m[1]+":"+m[2], true
	} else if rxQStopOff.MatchString(st) {
		q.Stop, q.HasStop = "off", true
	} else {
		q.Stop, q.HasStop = "", false
	}
	if m := rxQSkip.FindStringSubmatch(st); m != nil {
		if m[1] == "on" {
			q.Skip = 1
		} else {
			q.Skip = 0
		}
	} else {
		q.Skip = -1
	}
	if m := rxQArm.FindStringSubmatch(st); m != nil {
		q.OnHHMM, q.HasOnHHMM = [2]int{int(atoi(m[1])), int(atoi(m[2]))}, true
		q.WarmupMin, q.HasWarmup = mustFloat(m[3]), true
	}
	if strings.Contains(st, "RUNNING") && strings.Contains(st, "preload") {
		q.Preload = "running"
	} else if strings.Contains(st, "preload FAILED") {
		q.Preload = "failed"
	}
}
