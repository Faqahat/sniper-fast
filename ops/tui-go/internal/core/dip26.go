package core

// dip26 (engine 10-29; AMS run 38 from 10-30 01:57 PKT): the LIVE RE-ARM and the pre-send send-path A/B.
//
//   - Re-arm: a pre-send window armed after a single >= 6% sell while another wallet still holds >= 6% (from the end of
//     slot dump + 2 to slot dump + 3 + gap, at its own size, its own QUIET stop). Every record of a re-arm window says
//     "kind":"rearm" (arm, skip, rearm_defer, disarm, attempt, attempt_land, fill, exit, sell_land, close, realized); T2
//     records have no kind. dipmon keeps the two apart: the T2 counters (windows armed / now, skips, disarms, QUIET)
//     never count a re-arm record; the money (fills, realized, rent back, failed tries) stays the run's pre-send total
//     (the run P&L is unchanged) with the re-arm's own part beside it (T2 = all - re-arm). The setting comes from
//     run_start presend_live.rearm, else the start line's "| REARM ON: ..." part; the engine's own counters from its
//     60 s status part "rearm: windows ...".
//   - The A/B: a window's tries alternate between its route's paths (the engine's rule: path = paths[(n + w) % len], n =
//     the window's tick). Per path, from the records (read by substring, never decoded): tries written; ticks refused,
//     INFERRED: a tick of the path missing while its window's ticks on both sides were sent (a refusal on that path:
//     its rate caps); a run of >= 2 missing ticks is a pause of every path, counted apart; landed, same slot, send ->
//     land, the send acks; the fills and their P&L by the filling try's path. The engine's 60 s parts "per path
//     sent/ok/6042/deadline/ata/other/unseen", "not-sent {...}" and "acks {...}" as it logs them (the last two for all
//     paths together). The SEND-PATH UNHEALTHY / RECOVERED edges of the A/B's paths.
//
// Older runs have none of it (no "kind", one pre-send path) and render exactly as before.

import (
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var (
	kindRearm  = []byte(`kind":"rearm"`)
	rxRaSt     = regexp.MustCompile(`\| rearm: windows (\d+) armed now (\d+) fills (\d+) realized ([-+]?[\d.]+) SOL \(sells >= [\d.]+% (\d+) candidates (\d+) checks (\d+) waited (\d+) armed after waiting (\d+) pending (\d+) \| attempts (\d+) failed-try fees ([\d.]+) SOL \| closed (\d+) \| skips \{([^}]*)\} \| ends \{([^}]*)\}\)`)
	rxRaSize   = regexp.MustCompile(`size ([\d.]+) SOL`)
	rxRaWin    = regexp.MustCompile(`to slot dump\+(\d+)\+(\d+)`)
	rxRaQuiet  = regexp.MustCompile(`QUIET (\d+:\d+) since the arm`)
	rxRaR5     = regexp.MustCompile(`R5 skip (on|off)`)
	rxRaAge    = regexp.MustCompile(`<= (\d+) slots old`)
	rxRaCurve  = regexp.MustCompile(`curve < ([\d.]+) SOL`)
	rxRaBig    = regexp.MustCompile(`a single sell >= ([\d.]+)% of supply`)
	rxRaStopMs = regexp.MustCompile(`left \(\+(\d+) ms\)`)
	rxPSCaps   = regexp.MustCompile(`(\d+) attempts/s \((\d+) per path\)`)
	rxSPRec    = regexp.MustCompile(`SEND-PATH (\S+) RECOVERED`)
)

const perPathKey = "per path sent/ok/6042/deadline/ata/other/unseen "

// ResNames: the engine's per-path result classes (resolve(): ok, 6042, deadline, ata_exists, other, unseen).
var ResNames = [6]string{"ok", "6042", "deadline", "ata", "other", "unseen"}

func resIdx(res string) int {
	switch res {
	case "ok":
		return 0
	case "6042":
		return 1
	case "deadline":
		return 2
	case "ata_exists":
		return 3
	case "unseen":
		return 5
	}
	return 4
}

// ------------------------------------------------------------------------------------------------- re-arm

// RearmCfg: the re-arm's setting (run_start presend_live.rearm, else the start line's "REARM ON:" part).
type RearmCfg struct {
	On       bool
	Src      string // "run_start" | "log"
	Spend    int64  // lamports
	Gap      int64  // the window's last slot = dump + Wait + Gap
	Wait     int64  // the holders check at the end of slot dump + Wait - 1 (3)
	Quiet    string // the re-arm's QUIET stop N:M ("6:2")
	R5       bool
	HasR5    bool
	MaxAge   int64   // slots (141)
	BigPct   float64 // 6
	CurveSol int64   // no candidate at a post-sell curve >= this (100 SOL)
	StopMs   int64   // the 30 ms stops
}

// RearmEng: the engine's 60 s status part "rearm: windows N armed now N fills N realized x SOL (...)" (the latest).
type RearmEng struct {
	Has                                               bool
	Windows, Now, Fills                               int64
	Realized                                          int64 // the realized lookups' sum (lamports; no rent back)
	Sells6, Cands, Checks, Waited, ArmedWait, Pending int64
	Attempts, Fees, Closed                            int64
	Skips, Ends                                       *OCounter
	Min                                               int
}

// RearmRec: a session's re-arm from its records ("kind":"rearm").
type RearmRec struct {
	Any                     bool // a re-arm record was read
	Arms, ArmedWait, Defers int64
	Open                    map[WKey]bool // armed now (arm -> disarm)
	Skips, Ends, DeferWhy   *OCounter
	Sent                    int64 // tries written
	Fills, Wins, NReal      int64 // fill records; realized records (> 0)
	Realized, Rent          int64 // lamports
	Fees, FeeN              int64 // failed tries' fees and count
}

func newRearmRec() RearmRec {
	return RearmRec{Open: map[WKey]bool{}, Skips: NewOCounter(), Ends: NewOCounter(), DeferWhy: NewOCounter()}
}

// Net is the re-arm's realized + rent back - failed tries' fees.
func (r *RearmRec) Net() int64 { return r.Realized + r.Rent - r.Fees }

func lamOr0(s string) int64 {
	v, _ := lamOf(s)
	return v
}

func i64(s string) int64 {
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
}

// rearmFromRS: run_start presend_live.rearm.
func rearmFromRS(r Obj) *RearmCfg {
	c := &RearmCfg{Src: "run_start", On: Truthy(r["on"])}
	c.Spend = NumKey(r, "spend").Int()
	c.Gap = NumKey(r, "gap").Int()
	c.Wait = NumKey(r, "wait_slots").Int()
	c.Quiet, _ = StrKey(r, "quiet_stop")
	if b, ok := r["r5_skip"].(bool); ok {
		c.R5, c.HasR5 = b, true
	}
	c.MaxAge = NumKey(r, "max_age_slots").Int()
	c.BigPct = NumKey(r, "big_pct").Float()
	c.CurveSol = NumKey(r, "untradeable_sol").Int()
	c.StopMs = NumKey(r, "stop_ms").Int()
	return c
}

// rearmFromLine: the "| REARM ON: ..." part of the "DIP PRESEND LIVE (REAL attempts) | ..." start line (nil: none).
func rearmFromLine(st string) *RearmCfg {
	i := strings.Index(st, "| REARM ON: ")
	if i < 0 {
		return nil
	}
	r := st[i+len("| REARM ON: "):]
	c := &RearmCfg{Src: "log", On: true}
	if m := rxRaSize.FindStringSubmatch(r); m != nil {
		c.Spend = lamOr0(m[1])
	}
	if m := rxRaWin.FindStringSubmatch(r); m != nil {
		c.Wait, c.Gap = i64(m[1]), i64(m[2])
	}
	if m := rxRaQuiet.FindStringSubmatch(r); m != nil {
		c.Quiet = m[1]
	}
	if m := rxRaR5.FindStringSubmatch(r); m != nil {
		c.R5, c.HasR5 = m[1] == "on", true
	}
	if m := rxRaAge.FindStringSubmatch(r); m != nil {
		c.MaxAge = i64(m[1])
	}
	if m := rxRaCurve.FindStringSubmatch(r); m != nil {
		f, _ := pyFloat(m[1])
		c.CurveSol = int64(f)
	}
	if m := rxRaBig.FindStringSubmatch(r); m != nil {
		c.BigPct, _ = pyFloat(m[1])
	}
	if m := rxRaStopMs.FindStringSubmatch(r); m != nil {
		c.StopMs = i64(m[1])
	}
	return c
}

// RearmSetting: the session's re-arm setting (run_start's, else the start line's; zero = none).
func (S *Sess) RearmSetting() RearmCfg {
	if S.RS.Rearm != nil {
		return *S.RS.Rearm
	}
	if S.RALog != nil {
		return *S.RALog
	}
	return RearmCfg{}
}

// HasRearm: the session runs the re-arm (its setting is on, or it wrote re-arm records).
func (S *Sess) HasRearm() bool { return S.RearmSetting().On || S.RA.Any }

// parseKN parses the engine's "{k n, k n}" counters (the inside of the braces).
func parseKN(s string) *OCounter {
	c := NewOCounter()
	for _, p := range strings.Split(s, ",") {
		p = strings.TrimSpace(p)
		i := strings.LastIndexByte(p, ' ')
		if i <= 0 {
			continue
		}
		if n, err := strconv.ParseInt(p[i+1:], 10, 64); err == nil {
			c.Add(p[:i], n)
		}
	}
	return c
}

// raRec handles a re-arm window's own records (arm, skip, rearm_defer, disarm); true = consumed (never a T2 count).
// Its positions' records (fill, exit, close, realized, ...) go through the pre-send path (ps), which counts their
// re-arm part too.
func (M *Model) raRec(S *Sess, e string, o Obj, w WKey) bool {
	ra := &S.RA
	ra.Any = true
	switch e {
	case "presend_live_arm":
		ra.Arms++
		ra.Open[w] = true
		if d, ok := o["deferred"]; ok && d != nil {
			ra.ArmedWait++
		}
		var pct, sol Num // the dump that armed it (the trades' "whale" column)
		if d, ok := SubObj(o, "dump"); ok {
			pct, sol = NumKey(d, "pct"), NumKey(d, "sol")
		}
		M.setArm(S.Idx, w, pct, sol)
		return true
	case "presend_live_skip":
		ra.Skips.Add(StrOr(o, "why", "?"), 1)
		return true
	case "presend_live_disarm":
		delete(ra.Open, w)
		ra.Ends.Add(StrOr(o, "why", "?"), 1)
		return true
	case "presend_live_rearm_defer":
		ra.Defers++
		ra.DeferWhy.Add(StrOr(o, "why", "?"), 1)
		return true
	}
	return false
}

// ------------------------------------------------------------------------------------------------- the A/B

// ABKind: one path's landings by the leader client family.
type ABKind struct {
	Land, Seen, Same int64
	S2R              Hist
}

// ABPath: one pre-send send path's tries (a session's).
type ABPath struct {
	Sent    int64 // tries written (presend_attempt)
	Refused int64 // ticks refused on this path alone (inferred)
	Gapped  int64 // ticks missing in a run of >= 2 (a pause: every path)
	Land    int64 // resolved tries (presend_attempt_land)
	Landed  int64 // resolved and not "unseen"
	Seen    int64 // with a send -> land (ms_send_to_rx)
	Same    int64 // of those, in the send slot (slots_after_send 0)
	Res     [6]int64
	S2R     Hist
	Ack200  int64
	AckBad  int64 // another HTTP status (0 = no answer)
	AckNone int64 // no ack recorded
	Codes   *OCounter
	Fills   int64 // fill records with this path
	Kinds   map[string]*ABKind
	Mins    map[int64]*[4]int64 // unix minute -> tries written, refused, resolved, ack failures (the alerts' last 10 min)
}

// ABEng: the engine's per-path counters of its status line.
type ABEng struct {
	Paths  map[string][7]int64 // sent, ok, 6042, deadline, ata, other, unseen
	Order  []string
	NotSea *OCounter // "not-sent {...}" (all paths)
	Acks   *OCounter // "acks {...}" (all paths): HTTP status -> count
	Has    bool
	Min    int
}

// ABSess: a session's A/B state.
type ABSess struct {
	init   bool
	On     bool     // two or more pre-send paths (the routes, else seen in the tries)
	Routes []string // the tick -> path rule's paths (one route class), nil = unknown (no refusals inferred)
	Spec   string   // the routes as configured ("default=helius-ps+astralane-ps")
	Named  []string // every path of the routes, in their order (the display order)
	Paths  map[string]*ABPath
	Order  []string
	first  string
	lastN  map[int64]int64 // window -> its last written tick
	lastQ  []int64
	maxMin int64
	Eng    ABEng
}

// routeRule: the paths of a routes spec when every class has the same list (the tick -> path rule needs no leader).
func routeRule(spec string) ([]string, []string) {
	rm := RouteMap(spec)
	var all []string
	seen := map[string]bool{}
	var keys []string
	for k := range rm {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var rule []string
	same := true
	for i, k := range keys {
		ps := rm[k]
		if i == 0 {
			rule = ps
		} else if !eqStrs(rule, ps) {
			same = false
		}
		for _, p := range ps {
			if !seen[p] {
				seen[p] = true
				all = append(all, p)
			}
		}
	}
	if !same {
		rule = nil
	}
	return rule, all
}

// abInit reads the routes once (run_start presend_live.routes, else the start line's), at the first try.
func (S *Sess) abInit() *ABSess {
	a := &S.AB
	if a.init {
		return a
	}
	a.init = true
	spec := ""
	if S.RS.PSL != nil {
		if r, ok := S.RS.PSL["routes"].(string); ok {
			spec = r
		}
	}
	if spec == "" {
		if r, ok := S.PSL["routes"].(string); ok {
			spec = r
		}
	}
	if spec != "" {
		rule, all := routeRule(rxParen.ReplaceAllString(spec, ""))
		a.Spec = rxParen.ReplaceAllString(spec, "")
		a.Routes, a.Named = rule, all
		a.On = len(all) >= 2
	}
	return a
}

func (a *ABSess) path(p string) *ABPath {
	x := a.Paths[p]
	if x == nil {
		if a.Paths == nil {
			a.Paths = map[string]*ABPath{}
		}
		if len(a.Paths) >= 16 {
			p = "other"
			if x = a.Paths[p]; x != nil {
				return x
			}
		}
		x = &ABPath{Codes: NewOCounter(), Kinds: map[string]*ABKind{}, Mins: map[int64]*[4]int64{}}
		a.Paths[p] = x
		a.Order = append(a.Order, p)
	}
	return x
}

// bucket: a path's minute (the last 70 minutes are kept).
func (a *ABSess) bucket(p *ABPath, mn int64) *[4]int64 {
	b := p.Mins[mn]
	if b == nil {
		b = &[4]int64{}
		p.Mins[mn] = b
		if mn > a.maxMin {
			a.maxMin = mn
			for _, q := range a.Paths {
				for k := range q.Mins {
					if k < mn-70 {
						delete(q.Mins, k)
					}
				}
			}
		}
	}
	return b
}

func (p *ABPath) kind(k string) *ABKind {
	x := p.Kinds[k]
	if x == nil {
		x = &ABKind{}
		p.Kinds[k] = x
	}
	return x
}

// strAt: strAfter in tail, else in the whole line.
func strAt(tail, line []byte, key string) (string, bool) {
	if v, ok := strAfter(tail, key); ok || len(tail) == len(line) {
		return v, ok
	}
	return strAfter(line, key)
}

func numAt(tail, line []byte, key string) (int64, bool) {
	if v, ok := numAfter(tail, key); ok || len(tail) == len(line) {
		return v, ok
	}
	return numAfter(line, key)
}

// abAttempt: a written try (presend_attempt; tail = the line from "leader"): its path, the window's skipped ticks.
func (M *Model) abAttempt(S *Sess, line, tail []byte, w int64, okw bool) {
	a := S.abInit()
	if !a.On && a.Routes != nil { // the routes have one path: no A/B (older runs: nothing more to read)
		return
	}
	path, _ := strAt(tail, line, `"path":"`)
	if !a.On {
		if a.Routes != nil || path == "" { // the routes are known and have one path: no A/B
			return
		}
		if a.first == "" {
			a.first = path
		}
		if path == a.first {
			return
		}
		a.On = true // a second path in the tries (no routes in the run's records)
	}
	p := a.path(path)
	p.Sent++
	t, okt := numAt(tail, line, `"t":`)
	mn := int64(-1)
	if okt && TimeOKi(t) {
		mn = floorDiv(t, minuteNS)
		a.bucket(p, mn)[0]++
	}
	n, okn := numAt(tail, line, `"n":`)
	if !okw || !okn || len(a.Routes) < 2 || n < 1 {
		return
	}
	if a.lastN == nil {
		a.lastN = map[int64]int64{}
	}
	last, seen := a.lastN[w]
	if n > last+1 && n-last < 100_000 {
		miss := n - last - 1
		for k := last + 1; k < n; k++ {
			L := int64(len(a.Routes))
			q := a.path(a.Routes[((k+w)%L+L)%L])
			if miss == 1 {
				q.Refused++
				if mn >= 0 {
					a.bucket(q, mn)[1]++
				}
			} else {
				q.Gapped++
			}
		}
	}
	if n > last {
		a.lastN[w] = n
	}
	if !seen {
		a.lastQ = append(a.lastQ, w)
		if len(a.lastQ) > 4096 {
			delete(a.lastN, a.lastQ[0])
			a.lastQ = a.lastQ[1:]
		}
	}
}

// abLand: a resolved try (presend_attempt_land; tail = the line from "client").
func (M *Model) abLand(S *Sess, line, tail []byte, path, res, client string, ss float64, okss bool, blk float64, okb bool) {
	a := S.abInit()
	if !a.On {
		return
	}
	p := a.path(path)
	p.Land++
	p.Res[resIdx(res)]++
	if res != "unseen" {
		p.Landed++
	}
	k := p.kind(KindOf(client))
	k.Land++
	if okss {
		p.S2R.Add(ss)
		k.S2R.Add(ss)
		p.Seen++
		k.Seen++
		if okb && blk == 0 {
			p.Same++
			k.Same++
		}
	}
	ack, okA := numAfter(line, `"ack":`) // the second key: near the start
	bad := !okA || ack != 200
	switch {
	case okA && ack == 200:
		p.Ack200++
	case okA:
		p.AckBad++
		if p.Codes.Len() < 32 {
			p.Codes.Add(strconv.FormatInt(ack, 10), 1)
		}
	default:
		p.AckNone++
	}
	if ts, ok := numAt(tail, line, `"t_send":`); ok && TimeOKi(ts) {
		b := a.bucket(p, floorDiv(ts, minuteNS))
		b[2]++
		if bad {
			b[3]++
		}
	}
}

// abFill: a fill record's path.
func (S *Sess) abFill(path string) {
	if a := S.abInit(); a.On && path != "" {
		a.path(path).Fills++
	}
}

// d26Status reads the dip26 parts of a "DIP status" line: the re-arm's, the per-path counters, not-sent, acks. Never
// panics on a malformed part (older runs' lines have the last three too: kept, shown only with the A/B).
func (M *Model) d26Status(S *Sess, st string) {
	if strings.Contains(st, "| rearm: ") {
		if m := rxRaSt.FindStringSubmatch(st); m != nil {
			S.RAEng = RearmEng{Has: true, Windows: i64(m[1]), Now: i64(m[2]), Fills: i64(m[3]), Realized: lamOr0(m[4]), Sells6: i64(m[5]),
				Cands: i64(m[6]), Checks: i64(m[7]), Waited: i64(m[8]), ArmedWait: i64(m[9]), Pending: i64(m[10]), Attempts: i64(m[11]),
				Fees: lamOr0(m[12]), Closed: i64(m[13]), Skips: parseKN(m[14]), Ends: parseKN(m[15]), Min: M.LogMin}
		}
	}
	e := &S.AB.Eng
	if i := strings.Index(st, perPathKey); i >= 0 {
		r := st[i+len(perPathKey):]
		if j := strings.Index(r, " | "); j >= 0 {
			r = r[:j]
		}
		paths := map[string][7]int64{}
		var order []string
		for _, x := range strings.Split(r, ", ") {
			f := strings.Fields(x)
			if len(f) != 2 {
				continue
			}
			ns := strings.Split(f[1], "/")
			if len(ns) != 7 {
				continue
			}
			var c [7]int64
			ok := true
			for k, s := range ns {
				v, err := strconv.ParseInt(s, 10, 64)
				if err != nil {
					ok = false
					break
				}
				c[k] = v
			}
			if ok && len(paths) < 16 {
				if _, dup := paths[f[0]]; !dup {
					order = append(order, f[0])
				}
				paths[f[0]] = c
			}
		}
		e.Paths, e.Order, e.Has, e.Min = paths, order, true, M.LogMin
	}
	if i := strings.Index(st, "not-sent {"); i >= 0 {
		r := st[i+len("not-sent "):]
		if j := strings.IndexByte(r, '}'); j >= 0 {
			if c, ok := parseIntDict(r[:j+1]); ok {
				e.NotSea = c
			}
		}
	}
	if i := strings.Index(st, "| acks {"); i >= 0 {
		r := st[i+len("| acks {"):]
		if j := strings.IndexByte(r, '}'); j >= 0 {
			c := NewOCounter()
			for _, x := range strings.Split(r[:j], ",") {
				k, v, ok := strings.Cut(strings.TrimSpace(x), ":")
				if !ok {
					continue
				}
				if n, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64); err == nil {
					c.Add(strings.TrimSpace(k), n)
				}
			}
			e.Acks = c
		}
	}
}

// PathEdge: a send path's SEND-PATH health edges (UNHEALTHY / RECOVERED lines).
type PathEdge struct {
	Down        bool // the last edge was UNHEALTHY
	Downs, Ups  int64
	Detail      string // the last UNHEALTHY line's reason
	Min         int    // the log minute of the last edge
	TLive       float64
	HasLiveTime bool
}

// pathEdge: a SEND-PATH line (the UNHEALTHY ones also count as the path's errors, as before).
func (M *Model) pathEdge(path string, up bool, st string) {
	if M.PathEdges == nil {
		M.PathEdges = map[string]*PathEdge{}
	}
	e := M.PathEdges[path]
	if e == nil {
		if len(M.PathEdges) >= 64 {
			return
		}
		e = &PathEdge{}
		M.PathEdges[path] = e
	}
	e.Down, e.Min = !up, M.LogMin
	e.TLive, e.HasLiveTime = M.tLive, M.tLive != 0
	if up {
		e.Ups++
		return
	}
	e.Downs++
	if i := strings.Index(st, "UNHEALTHY: "); i >= 0 {
		e.Detail = RuneSlice(Clean(st[i+len("UNHEALTHY: "):]), 120)
	}
}

// ------------------------------------------------------------------------------------------------- the view

// AggRA: the re-arm over the selected sessions (On false: the run has none).
type AggRA struct {
	On                       bool
	Cfg                      RearmCfg
	Fills, Wins, NReal, Sent int64
	Real, Rent, Fees, FeeN   int64
	Net                      int64
	Arms, ArmedWait, Defers  int64
	OpenNow                  int64 // windows armed now (only while running)
	Skips, Ends, DeferWhy    *OCounter
	Exits                    *OExits
	Best, Worst              *Trade
	OpenPos, Closed          int64
	Eng                      RearmEng // the current session's latest status part
	Paper                    ObsCount // the observatory's paper re-arm (log only), when it reports one
	HasPaper                 bool
}

// splitPS: the T2 part of the pre-send figures (all - re-arm; the exits, best / worst and open positions over the
// T2 positions) and the re-arm's. Without re-arm: T2 = the pre-send figures as they are.
func splitPS(sessions []*Sess, ps AggPS, running bool, cur *Sess) (AggPS, AggRA) {
	ra := AggRA{Skips: NewOCounter(), Ends: NewOCounter(), DeferWhy: NewOCounter(), Exits: newOExits()}
	for _, S := range sessions {
		if S.HasRearm() {
			ra.On = true
		}
	}
	if !ra.On {
		return ps, ra
	}
	ra.Cfg = cur.RearmSetting()
	if !ra.Cfg.On {
		for _, S := range sessions {
			if c := S.RearmSetting(); c.On {
				ra.Cfg = c
			}
		}
	}
	ra.Eng = cur.RAEng
	if d := cur.D24; d.Obs.HasLine {
		for _, c := range d.Obs.Counts {
			if c.K == "rearm" {
				ra.Paper, ra.HasPaper = c, true
			}
		}
	}
	t2 := ps
	t2.Exits, t2.Best, t2.Worst, t2.OpenPos, t2.Closed, t2.NotSold, t2.LandMs, t2.After = newOExits(), nil, nil, 0, 0, 0, nil, nil
	for _, S := range sessions {
		r := &S.RA
		ra.Fills += r.Fills
		ra.Wins += r.Wins
		ra.NReal += r.NReal
		ra.Sent += r.Sent
		ra.Real += r.Realized
		ra.Rent += r.Rent
		ra.Fees += r.Fees
		ra.FeeN += r.FeeN
		ra.Arms += r.Arms
		ra.ArmedWait += r.ArmedWait
		ra.Defers += r.Defers
		if running && S == cur {
			ra.OpenNow = int64(len(r.Open))
		}
		ra.Skips.Update(r.Skips)
		ra.Ends.Update(r.Ends)
		ra.DeferWhy.Update(r.DeferWhy)
		for _, tr := range S.PSList {
			A := &t2
			ex, best, worst := &t2.Exits, &t2.Best, &t2.Worst
			openPos, closed := &t2.OpenPos, &t2.Closed
			if tr.Rearm {
				ex, best, worst, openPos, closed = &ra.Exits, &ra.Best, &ra.Worst, &ra.OpenPos, &ra.Closed
			} else {
				if tr.Ms.Ok() {
					A.LandMs = append(A.LandMs, tr.Ms.Float())
				}
				if tr.After.Ok() {
					A.After = append(A.After, tr.After)
				}
			}
			if tr.PClose == nil && !tr.HasPnl {
				*openPos++
				continue
			}
			*closed++
			if !tr.Rearm && tr.Res != "sold" && tr.Res != "?" && tr.Res != "" && tr.PClose != nil {
				A.NotSold++
			}
			why := "?"
			if tr.HasPExit && tr.PExit != "" {
				why = tr.PExit
			}
			e := (*ex).get(why)
			e.N++
			if tr.HasPnl && tr.Pnl > 0 {
				e.Wins++
			}
			if tr.HasPnl {
				e.Pnl += tr.Pnl
				if *best == nil || tr.Pnl > (*best).Pnl {
					*best = tr
				}
				if *worst == nil || tr.Pnl < (*worst).Pnl {
					*worst = tr
				}
			}
		}
	}
	ra.Net = ra.Real + ra.Rent - ra.Fees
	t2.Fills -= ra.Fills
	t2.Wins -= ra.Wins
	t2.NReal -= ra.NReal
	t2.Sent -= ra.Sent
	t2.Real -= ra.Real
	t2.Rent -= ra.Rent
	t2.FeesCnt -= ra.Fees
	t2.Fees -= ra.Fees
	t2.FeeN -= ra.FeeN
	t2.Net -= ra.Net
	return t2, ra
}

// pathOrder: a session's A/B paths, the routes' order first, then the others as their tries came.
func (a *ABSess) pathOrder() []string {
	var out []string
	seen := map[string]bool{}
	for _, p := range a.Named {
		if _, ok := a.Paths[p]; ok && !seen[p] {
			seen[p] = true
			out = append(out, p)
		}
	}
	for _, p := range a.Order {
		if !seen[p] {
			seen[p] = true
			out = append(out, p)
		}
	}
	return out
}

// ABQuick: the A/B for the view and its alerts (cheap; ABOf has the full summary).
type ABQuick struct {
	On    bool
	Spec  string
	Paths []string
}

func abQuick(sessions []*Sess) ABQuick {
	var q ABQuick
	seen := map[string]bool{}
	for _, S := range sessions {
		a := &S.AB
		if !a.On {
			continue
		}
		q.On = true
		if a.Spec != "" {
			q.Spec = a.Spec
		}
		for _, p := range a.pathOrder() {
			if !seen[p] {
				seen[p] = true
				q.Paths = append(q.Paths, p)
			}
		}
	}
	return q
}

// ABKindRow: one path's landings for a client family.
type ABKindRow struct {
	Land, Seen, Same int64
	P50              float64
	HasQ             bool
}

// ABRow: one path of the A/B summary.
type ABRow struct {
	Path                                    string
	Sent, Refused, Gapped                   int64
	Land, Landed, Seen, Same                int64
	Res                                     [6]int64
	P50, P90                                float64
	HasQ                                    bool
	Ack200, AckBad, AckNone                 int64
	Codes                                   *OCounter
	Fills                                   int64 // fill records by their path
	Pos, Wins                               int64 // positions with a realized P&L, by their fill path
	Pnl                                     int64 // their realized P&L
	Kinds                                   map[string]*ABKindRow
	Eng                                     [7]int64
	HasEng                                  bool
	Edge                                    *PathEdge
	Sent10, Refused10, Resolved10, AckBad10 int64 // the last 10 minutes
}

// RefusedShare: refused / (written + refused).
func (r *ABRow) RefusedShare() (float64, bool) {
	d := r.Sent + r.Refused
	if d == 0 {
		return 0, false
	}
	return float64(r.Refused) / float64(d), true
}

// AckFail: the tries without a 200 ack (another status, or none).
func (r *ABRow) AckFail() int64 { return r.AckBad + r.AckNone }

// ABSummary: the send-path A/B over the selected sessions.
type ABSummary struct {
	On            bool
	Spec          string
	Rule          bool // the tick -> path rule is known: refusals inferred per path
	Rows          []ABRow
	Kinds         []string // the client families present, the latency table's order
	NotSent, Acks *OCounter
	MaxPerSec     int64
	PathMaxPerSec int64
	EngHas        bool
}

// ABOf builds the A/B summary of sessions (the trades for the P&L by fill path; nowNS: the last 10 minutes' end).
func ABOf(sessions []*Sess, trades []*Trade, M *Model, nowNS float64) ABSummary {
	s := ABSummary{NotSent: NewOCounter(), Acks: NewOCounter()}
	idx := map[string]int{}
	type acc struct {
		row   *ABRow
		s2r   []*Hist              // the sessions' histograms (merged only when there are several)
		kinds map[string][]*ABKind // by client group
	}
	var accs []*acc
	get := func(p string) *acc {
		if i, ok := idx[p]; ok {
			return accs[i]
		}
		idx[p] = len(accs)
		a := &acc{row: &ABRow{Path: p, Codes: NewOCounter(), Kinds: map[string]*ABKindRow{}}, kinds: map[string][]*ABKind{}}
		accs = append(accs, a)
		return a
	}
	m10 := floorDiv(int64(nowNS), minuteNS) - 9
	for _, S := range sessions {
		a := &S.AB
		if !a.On {
			continue
		}
		s.On = true
		if a.Spec != "" {
			s.Spec = a.Spec
		}
		if len(a.Routes) >= 2 {
			s.Rule = true
		}
		for _, p := range a.pathOrder() {
			x := a.Paths[p]
			g := get(p)
			r := g.row
			r.Sent += x.Sent
			r.Refused += x.Refused
			r.Gapped += x.Gapped
			r.Land += x.Land
			r.Landed += x.Landed
			r.Seen += x.Seen
			r.Same += x.Same
			for i := range r.Res {
				r.Res[i] += x.Res[i]
			}
			g.s2r = append(g.s2r, &x.S2R)
			r.Ack200 += x.Ack200
			r.AckBad += x.AckBad
			r.AckNone += x.AckNone
			r.Codes.Update(x.Codes)
			r.Fills += x.Fills
			for k0, kx := range x.Kinds {
				k := KindGroup(k0)
				g.kinds[k] = append(g.kinds[k], kx)
			}
			for mn, b := range x.Mins {
				if mn >= m10 {
					r.Sent10 += b[0]
					r.Refused10 += b[1]
					r.Resolved10 += b[2]
					r.AckBad10 += b[3]
				}
			}
		}
		if a.Eng.Has {
			s.EngHas = true
			for _, p := range a.Eng.Order {
				g := get(p)
				c := a.Eng.Paths[p]
				for i := range c {
					g.row.Eng[i] += c[i]
				}
				g.row.HasEng = true
			}
		}
		if a.Eng.NotSea != nil {
			s.NotSent.Update(a.Eng.NotSea)
		}
		if a.Eng.Acks != nil {
			s.Acks.Update(a.Eng.Acks)
		}
		if n := S.RS.PSMax; n.Truthy() {
			s.MaxPerSec = n.Int()
		}
		if n := S.RS.PSPathMax; n.Truthy() {
			s.PathMaxPerSec = n.Int()
		}
		if s.MaxPerSec == 0 && S.PSCaps[0] > 0 {
			s.MaxPerSec, s.PathMaxPerSec = S.PSCaps[0], S.PSCaps[1]
		}
	}
	if !s.On {
		return s
	}
	// positions by their fill path: realized P&L, wins
	for _, tr := range trades {
		if tr.Kind != "PS" || !tr.HasPnl || tr.Path == "" {
			continue
		}
		if _, ok := idx[tr.Path]; !ok {
			continue
		}
		r := get(tr.Path).row
		r.Pos++
		r.Pnl += tr.Pnl
		if tr.Pnl > 0 {
			r.Wins++
		}
	}
	one := func(hs []*Hist) *Hist { // a session's own histogram as it is, several merged
		if len(hs) == 1 {
			return hs[0]
		}
		h := &Hist{}
		for _, x := range hs {
			h.Merge(x)
		}
		return h
	}
	kset := map[string]bool{}
	for _, g := range accs {
		r := g.row
		if len(g.s2r) > 0 {
			if q, ok := one(g.s2r).Quantiles(0.5, 0.9); ok {
				r.P50, r.P90, r.HasQ = q[0], q[1], true
			}
		}
		for k, kxs := range g.kinds {
			kr := &ABKindRow{}
			var hs []*Hist
			for _, kx := range kxs {
				kr.Land += kx.Land
				kr.Seen += kx.Seen
				kr.Same += kx.Same
				hs = append(hs, &kx.S2R)
			}
			if q, ok := one(hs).Quantile(0.5); ok {
				kr.P50, kr.HasQ = q, true
			}
			r.Kinds[k] = kr
			kset[k] = true
		}
		if M != nil {
			r.Edge = M.PathEdges[r.Path]
		}
		s.Rows = append(s.Rows, *r)
	}
	order := map[string]int{"Harmonic": 0, "BAM": 1, "Jito": 2, "Firedancer": 3, "Agave": 4, "other": 5}
	for k := range kset {
		s.Kinds = append(s.Kinds, k)
	}
	sort.Slice(s.Kinds, func(i, j int) bool {
		a, b := s.Kinds[i], s.Kinds[j]
		oa, oka := order[a]
		ob, okb := order[b]
		if oka != okb {
			return oka
		}
		if oka {
			return oa < ob
		}
		return a < b
	})
	return s
}

// KindGroup: a client family as the latency tables group them (the five that matter, the rest "other").
func KindGroup(k string) string {
	switch k {
	case "Harmonic", "BAM", "Jito", "Firedancer", "Agave":
		return k
	}
	return "other"
}

// PathCode: a send path in two letters ("HL" helius-*, "AS" astralane-*, ...), for the narrow columns.
func PathCode(p string) string {
	if p == "" {
		return ""
	}
	first, more, _ := strings.Cut(p, "+")
	codes := []struct{ pre, code string }{{"helius", "HL"}, {"astralane", "AS"}, {"nozomi", "NZ"}, {"falcon", "FC"}, {"glaive", "GL"},
		{"soyas", "SY"}, {"solami", "SM"}, {"0slot", "0S"}, {"bolt", "BT"}, {"staked", "SR"}, {"jito", "JT"}, {"landx", "LX"},
		{"harmonic", "HM"}, {"tpu", "TP"}, {"haan", "HN"}, {"speedlanding", "SL"}}
	c := ""
	for _, x := range codes {
		if strings.HasPrefix(first, x.pre) {
			c = x.code
			break
		}
	}
	if c == "" {
		var b []rune
		for _, r := range first {
			if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') {
				b = append(b, r)
				if len(b) == 2 {
					break
				}
			}
		}
		c = strings.ToUpper(string(b))
	}
	if more != "" {
		c += "+"
	}
	return c
}

// d26View: the re-arm, T2 and the A/B for the view.
func (v *View) d26View(sel []*Sess) {
	v.T2, v.RA = splitPS(sel, v.PS, v.Running, v.S)
	v.AB = abQuick(sel)
	v.FAB = FeeABOf(sel) // dip37
}

// d26Items: the re-arm's and the A/B's config items (only when the run has them).
func d26Items(v *View, add func(key, label, state, short, full string)) {
	if v.RA.On {
		c := v.RA.Cfg
		st := "on"
		if !c.On {
			st = "part"
		}
		if v.PSStopped != "" {
			st = "part"
		}
		add("rearm", "Re-arm", st, "RA "+RearmShort(c), RearmFull(c))
	}
	if v.AB.On {
		short := "A/B"
		for i, p := range v.AB.Paths {
			if i == 0 {
				short += " "
			} else {
				short += "/"
			}
			short += PathCode(p)
		}
		full := strings.Join(v.AB.Paths, " / ") + ": the tries alternate (try n of window w on path (n + w) mod " + Itoa(int64(max(1, len(v.AB.Paths)))) + ")"
		if v.AB.Spec != "" {
			full += " " + G.Sep + " routes " + v.AB.Spec
		}
		add("ab", "Send-path A/B", "on", short, full)
	}
}

// RearmShort: "0.65 g20 q6:2" (+ " R5" when its skip is on).
func RearmShort(c RearmCfg) string {
	s := F(float64(c.Spend)/LAM, 2) + " g" + Itoa(c.Gap)
	if c.Quiet != "" {
		s += " q" + c.Quiet
	}
	if c.R5 {
		s += " R5"
	}
	return s
}

// RearmFull: the re-arm's setting in words.
func RearmFull(c RearmCfg) string {
	if !c.On && c.Spend == 0 {
		return "on (re-arm records; no setting logged)"
	}
	wait := c.Wait
	if wait == 0 {
		wait = 3
	}
	s := F(float64(c.Spend)/LAM, 3) + " SOL " + G.Sep + " window dump+" + Itoa(wait) + " " + G.Arrow + " dump+" + Itoa(wait) + "+" + Itoa(c.Gap) + " slots"
	if c.Quiet != "" {
		s += " " + G.Sep + " QUIET stop " + c.Quiet
	}
	if c.HasR5 {
		s += " " + G.Sep + " R5 skip " + map[bool]string{true: "on", false: "off"}[c.R5]
	}
	big := "6"
	if c.BigPct > 0 {
		big = F(c.BigPct, 0)
	}
	s += " " + G.Sep + " after a single sell " + G.Ge + " " + big + "% while another wallet holds " + G.Ge + " " + big + "%"
	if c.MaxAge > 0 {
		s += " (token " + G.Le() + " " + Itoa(c.MaxAge) + " slots"
		if c.CurveSol > 0 {
			s += ", curve < " + Itoa(c.CurveSol) + " SOL"
		}
		s += ")"
	}
	return s
}

// SkipName: a re-arm skip / end reason without its "rearm_" prefix.
func SkipName(k string) string { return strings.TrimPrefix(k, "rearm_") }

// CounterText: "a 3 · b 2" (most common first).
func CounterText(c *OCounter, name func(string) string) string {
	if c == nil {
		return ""
	}
	var parts []string
	for _, kv := range c.MostCommon() {
		k := kv.K
		if name != nil {
			k = name(k)
		}
		parts = append(parts, k+" "+IC(kv.N))
	}
	return strings.Join(parts, " "+G.Sep+" ")
}

// d26Alerts: an A/B path that refuses > 1% of its ticks or whose acks fail on > 1% of its tries in the last 10
// minutes, or whose last SEND-PATH edge is UNHEALTHY (running runs only).
func d26Alerts(v *View, M *Model, A []Alert) []Alert {
	if !v.AB.On || !v.Running {
		return A
	}
	sel := v.Sessions
	if v.Scope >= 0 {
		sel = []*Sess{v.S}
	}
	m10 := floorDiv(int64(v.NowNS()), minuteNS) - 9
	for _, p := range v.AB.Paths {
		var sent, ref, res, bad int64
		for _, S := range sel {
			x := S.AB.Paths[p]
			if x == nil {
				continue
			}
			for mn, b := range x.Mins {
				if mn >= m10 {
					sent += b[0]
					ref += b[1]
					res += b[2]
					bad += b[3]
				}
			}
		}
		if d := sent + ref; d > 0 && float64(ref) > 0.01*float64(d) {
			A = append(A, Alert{"warn", p + " refused " + F(float64(ref)/float64(d)*100, 1) + "% of its tries in 10 min (" + IC(ref) + " of " + IC(d) + ")"})
		}
		if res > 0 && float64(bad) > 0.01*float64(res) {
			A = append(A, Alert{"warn", p + " acks failing: " + IC(bad) + " of " + IC(res) + " not 200 in 10 min"})
		}
		if e := M.PathEdges[p]; e != nil && e.Down {
			A = append(A, Alert{"warn", p + " UNHEALTHY: " + RuneSlice(e.Detail, 60)})
		}
	}
	return A
}

// abPct: "41%" of n / d ("–" when d is 0).
func abPct(n, d int64) string {
	if d == 0 {
		return G.Dash
	}
	return F(float64(n)/float64(d)*100, 0) + "%"
}

// ABRowText: one path's figures for the snapshot.
func ABRowText(r ABRow, rule bool) string {
	ref := "refused ?"
	if rule {
		ref = "refused " + IC(r.Refused)
		if sh, ok := r.RefusedShare(); ok {
			ref += " (" + F(sh*100, 1) + "%)"
		}
	}
	q := G.Dash
	if r.HasQ {
		q = F(r.P50, 0) + " / " + F(r.P90, 0) + " ms"
	}
	s := IC(r.Sent) + " tries, " + ref + ", landed " + abPct(r.Landed, r.Land) + ", same slot " + abPct(r.Same, r.Seen) + ", send->land p50 / p90 " + q +
		", acks not 200: " + IC(r.AckFail())
	if r.AckFail() > 0 {
		var parts []string
		for _, kv := range r.Codes.MostCommon() {
			parts = append(parts, kv.K+" x"+IC(kv.N))
		}
		if r.AckNone > 0 {
			parts = append(parts, "none x"+IC(r.AckNone))
		}
		s += " (" + strings.Join(parts, ", ") + ")"
	}
	s += ", fills " + IC(r.Fills) + ", P&L " + Sol(r.Pnl, true, 4, true)
	if r.Pos > 0 {
		s += " (" + IC(r.Pos) + " positions, " + IC(r.Wins) + " W)"
	}
	if r.Edge != nil && (r.Edge.Downs > 0 || r.Edge.Ups > 0) {
		st := "ok"
		if r.Edge.Down {
			st = "UNHEALTHY"
		}
		s += ", health " + st + " (" + IC(r.Edge.Downs) + " unhealthy / " + IC(r.Edge.Ups) + " recovered)"
	}
	return s
}

// d26Text: the snapshot's re-arm and A/B lines (none for older runs).
func d26Text(v *View, ctx *Ctx) []string {
	var out []string
	if ra := v.RA; ra.On {
		c := ra.Cfg
		line := "re-arm    config " + RearmFull(c) + "; windows " + IC(ra.Arms)
		if v.Running {
			line += " (now " + IC(ra.OpenNow) + ")"
		}
		line += ", armed after waiting " + IC(ra.ArmedWait) + ", deferred " + IC(ra.Defers) + ", tries " + IC(ra.Sent)
		out = append(out, line)
		sk := CounterText(ra.Skips, SkipName)
		if sk == "" {
			sk = "none"
		}
		en := CounterText(ra.Ends, nil)
		if en == "" {
			en = "none"
		}
		out = append(out, "          skips: "+sk+" | ends: "+en)
		if ra.Exits != nil && len(ra.Exits.Keys) > 0 {
			var parts []string
			for _, k := range ra.Exits.Sorted() {
				e := ra.Exits.M[k]
				parts = append(parts, k+" "+IC(e.N)+" ("+Sol(e.Pnl, true, 4, true)+")")
			}
			out = append(out, "          exits: "+strings.Join(parts, ", "))
		}
		var tail []string
		if e := ra.Eng; e.Has {
			tail = append(tail, "engine: candidates "+IC(e.Cands)+", checks "+IC(e.Checks)+", pending "+IC(e.Pending)+", sells >= 6% "+IC(e.Sells6)+
				", realized "+Sol(e.Realized, true, 4, true))
		}
		if ra.HasPaper {
			p := "paper (observatory, log only) " + IC(ra.Paper.N) + " windows"
			if ra.Paper.HasFills {
				p += " / " + IC(ra.Paper.Fills) + " fills"
			}
			tail = append(tail, p)
		}
		if len(tail) > 0 {
			out = append(out, "          "+strings.Join(tail, " | "))
		}
	}
	if v.AB.On {
		sel := v.Sessions
		if v.Scope >= 0 {
			sel = []*Sess{v.S}
		}
		s := ABOf(sel, v.Trades, v.Model, v.NowNS())
		head := "A/B       "
		if s.Spec != "" {
			head += "routes " + s.Spec + " (the tries alternate)"
		}
		if s.MaxPerSec > 0 {
			head += ", caps " + IC(s.MaxPerSec) + "/s, " + IC(s.PathMaxPerSec) + "/s a path"
		}
		out = append(out, head)
		w := 0
		for _, r := range s.Rows {
			w = max(w, RuneLen(r.Path))
		}
		for _, r := range s.Rows {
			out = append(out, "          "+PadRight(r.Path, w)+"  "+ABRowText(r, s.Rule))
		}
		var tail []string
		if s.NotSent.Len() > 0 {
			tail = append(tail, "not sent (engine, all paths): "+CounterText(s.NotSent, nil))
		} else if s.EngHas {
			tail = append(tail, "not sent (engine): none")
		}
		if s.Acks.Len() > 0 {
			tail = append(tail, "acks (engine): "+CounterText(s.Acks, nil))
		}
		if s.Rule {
			tail = append(tail, "refused = inferred from the windows' missing ticks")
		}
		if len(tail) > 0 {
			out = append(out, "          "+strings.Join(tail, "; "))
		}
	}
	return out
}

// d26JSON: the snapshot JSON's "dip26" object (only when the run has the re-arm or the A/B).
func d26JSON(v *View, d *JObj) {
	if !v.RA.On && !v.AB.On {
		return
	}
	o := &JObj{}
	money := func(fills, wins, real, rent, fees, feeN, net, sent int64) *JObj {
		x := &JObj{}
		x.Set("fills", fills)
		x.Set("wins", wins)
		x.Set("realized", real)
		x.Set("rent", rent)
		x.Set("fees", fees)
		x.Set("failed_tries", feeN)
		x.Set("net", net)
		x.Set("sent", sent)
		return x
	}
	if ra := v.RA; ra.On {
		t2 := v.T2
		t := money(t2.Fills, t2.Wins, t2.Real, t2.Rent, t2.Fees, t2.FeeN, t2.Net, t2.Sent)
		t.Set("armed", t2.Armed)
		o.Set("t2", t)
		r := money(ra.Fills, ra.Wins, ra.Real, ra.Rent, ra.Fees, ra.FeeN, ra.Net, ra.Sent)
		r.Set("windows", ra.Arms)
		r.Set("open_windows", ra.OpenNow)
		r.Set("armed_after_waiting", ra.ArmedWait)
		r.Set("deferred", ra.Defers)
		r.Set("skips", ra.Skips.JSON())
		r.Set("ends", ra.Ends.JSON())
		c := &JObj{}
		c.Set("on", ra.Cfg.On)
		c.Set("source", optStr(ra.Cfg.Src))
		c.Set("spend", ra.Cfg.Spend)
		c.Set("gap", ra.Cfg.Gap)
		c.Set("quiet_stop", optStr(ra.Cfg.Quiet))
		if ra.Cfg.HasR5 {
			c.Set("r5_skip", ra.Cfg.R5)
		} else {
			c.Set("r5_skip", nil)
		}
		r.Set("cfg", c)
		if e := ra.Eng; e.Has {
			x := &JObj{}
			x.Set("windows", e.Windows)
			x.Set("armed_now", e.Now)
			x.Set("fills", e.Fills)
			x.Set("realized", e.Realized)
			x.Set("candidates", e.Cands)
			x.Set("checks", e.Checks)
			x.Set("pending", e.Pending)
			x.Set("attempts", e.Attempts)
			x.Set("fees_failed", e.Fees)
			r.Set("engine", x)
		} else {
			r.Set("engine", nil)
		}
		o.Set("rearm", r)
	} else {
		o.Set("t2", nil)
		o.Set("rearm", nil)
	}
	if v.AB.On {
		sel := v.Sessions
		if v.Scope >= 0 {
			sel = []*Sess{v.S}
		}
		s := ABOf(sel, v.Trades, v.Model, v.NowNS())
		ab := &JObj{}
		ab.Set("routes", optStr(s.Spec))
		ab.Set("refusals_inferred", s.Rule)
		ps := &JObj{}
		for _, r := range s.Rows {
			x := &JObj{}
			x.Set("sent", r.Sent)
			x.Set("refused", r.Refused)
			x.Set("paused_ticks", r.Gapped)
			x.Set("resolved", r.Land)
			x.Set("landed", r.Landed)
			x.Set("seen", r.Seen)
			x.Set("same_slot", r.Same)
			res := &JObj{}
			for i, n := range ResNames {
				res.Set(n, r.Res[i])
			}
			x.Set("results", res)
			if r.HasQ {
				x.Set("send_to_land_p50_ms", PyFloat(r.P50))
				x.Set("send_to_land_p90_ms", PyFloat(r.P90))
			} else {
				x.Set("send_to_land_p50_ms", nil)
				x.Set("send_to_land_p90_ms", nil)
			}
			x.Set("acks_200", r.Ack200)
			x.Set("acks_other", r.AckBad)
			x.Set("acks_none", r.AckNone)
			x.Set("fills", r.Fills)
			x.Set("positions", r.Pos)
			x.Set("pnl", r.Pnl)
			ps.Set(r.Path, x)
		}
		ab.Set("paths", ps)
		ab.Set("not_sent", s.NotSent.JSON())
		ab.Set("acks", s.Acks.JSON())
		o.Set("ab", ab)
	} else {
		o.Set("ab", nil)
	}
	d.Set("dip26", o)
}

// inferD26: the build when the records / log are dip26's (no process to ask).
func inferD26(S *Sess) bool { return S.HasRearm() }
