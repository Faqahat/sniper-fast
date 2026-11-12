package core

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

// v5 (11-12, owner after r85): the REAL trading state. The engine can run while it buys nothing: the circuit breaker's pause
// (presend_live_breaker: "no new buys for N min"; ends early when the control key turns the breaker to log), the PKT pause window
// and the manual pause (dip47 pause_window / pause_now), the 24 h fee budget's pause, a stop (profit lock, kill switch, run_stopping,
// DIP DONE, engine gone). The header shows the state in colour instead of RUNNING, with every blocking state under it; Health
// shows the same. A running run that buys but has armed nothing for >= 15 min is IDLE (a soft warning).

// Block: one state that stops new buys now. Until = its end (ns; 0 = open-ended).
type Block struct {
	Kind, Text, Reason string
	Until              int64
	Sev                string // "bad" | "warn"
}

type brkTrip struct {
	T, Until        int64
	Min, Losses     int64
	LastMint        string
	LastPnl         int64
	LogAt           int64 // the control key turned the breaker to log during the pause (0 = no)
	LossThr, WinMin string
}

type modeAt struct {
	T    int64
	Mode string
}

// trading: the records the trading state reads (V5Acc's part).
type trading struct {
	curT     int64 // the model's clock when the record came (the breaker record has no "t")
	trips    []brkTrip
	brkModes []modeAt
	lastArm  int64
	anyArm   bool
	stopWhy  string // presend_live_stop (run_stopping / run_end / ...)
	stopT    int64
}

var rxBreakerSpec = func(s string) (string, string) { // "2:0.1:30:60" -> loss threshold, window min
	p := strings.Split(s, ":")
	if len(p) >= 3 {
		return p[1], p[2]
	}
	return "", ""
}

func (A *V5Acc) tradeFeed(e string, o map[string]any) {
	T := &A.tr
	switch e {
	case "presend_live_breaker":
		t := tOfAny(o)
		if t == 0 {
			t = T.curT
		}
		b := brkTrip{T: t, LastMint: mStr(o, "last_mint")}
		if x, ok := mNum(o, "pause_min"); ok {
			b.Min = int64(x)
		}
		if x, ok := mNum(o, "losses"); ok {
			b.Losses = int64(x)
		}
		if x, ok := mNum(o, "last_pnl"); ok {
			b.LastPnl = int64(x)
		}
		b.Until = t + b.Min*60e9
		b.LossThr, b.WinMin = A.brkThr, A.brkWin
		T.trips = append(T.trips, b)
	case "presend_live_stop":
		T.stopWhy, T.stopT = mStr(o, "why"), tOr(tOfAny(o), T.curT)
	case "presend_live_arm":
		T.lastArm, T.anyArm = T.curT, true
		if t := tOfAny(mObj(o, "trig")); t > T.lastArm {
			T.lastArm = t
		}
	case "presend_live_ledger_mode":
		if d := mObj(o, "dip43"); d != nil {
			if m := mStr(d, "breaker"); m != "" {
				T.brkMode(tOr(tOfAny(o), T.curT), m)
			}
		}
	case "presend_live_filter_state":
		if st := mObj(o, "state"); st != nil {
			if m := mStr(st, "breaker"); m != "" {
				T.brkMode(tOr(tOfAny(o), T.curT), m)
			}
		}
	}
}

func tOr(t, d int64) int64 {
	if t != 0 {
		return t
	}
	return d
}

func (T *trading) brkMode(t int64, m string) {
	if n := len(T.brkModes); n > 0 && T.brkModes[n-1].Mode == m {
		return
	}
	T.brkModes = append(T.brkModes, modeAt{t, m})
	if m == "log" { // the pause under way ends now (the engine: paused = until && !log)
		for i := range T.trips {
			if T.trips[i].LogAt == 0 && t >= T.trips[i].T && t < T.trips[i].Until {
				T.trips[i].LogAt = t
			}
		}
	}
}

func (T *trading) brkModeAt(t int64) string {
	m := "live"
	for _, x := range T.brkModes {
		if x.T <= t {
			m = x.Mode
		}
	}
	return m
}

// minsLeft: "12 min left" / "45 s left".
func minsLeft(until, now int64) string {
	d := until - now
	if d < 60e9 {
		return fmt.Sprintf("%d s left", max(0, d/1e9))
	}
	return fmt.Sprintf("%d min left", (d+59e9)/60e9)
}

// TradingState: the state the header shows instead of RUNNING ("" = buying) and every blocking state now.
func TradingState(v *View, M *Model, S *Sess, now int64) (string, string, []Block) {
	if NoV4 || !v.Running {
		return "", "", nil
	}
	var bl []Block
	T := &M.V5.tr
	// stops first (they do not end by themselves)
	if v.Status == "STOPPING" {
		why := "stop signal"
		switch {
		case S.D24.LockFired:
			why = "profit lock"
		case S.killTruthy():
			why = "kill switch"
		case S.signalTruthy():
			why = "stop: " + S.Signal
		}
		bl = append(bl, Block{Kind: "stopping", Text: "STOPPING: " + why + " (no new buys; open positions exit)", Reason: why, Sev: "bad"})
	} else if T.stopWhy != "" && T.stopT >= S.T0 {
		bl = append(bl, Block{Kind: "stopping", Text: "STOPPING: " + T.stopWhy + " at " + T12(float64(T.stopT), false) + " (no new buys; open positions exit)",
			Reason: T.stopWhy, Sev: "bad"})
	} else if v.PSStopped != "" {
		bl = append(bl, Block{Kind: "stopped", Text: "pre-send STOPPED (" + v.PSStopped + ")", Reason: v.PSStopped, Sev: "bad"})
	}
	// the circuit breaker
	for i := len(T.trips) - 1; i >= 0; i-- {
		b := T.trips[i]
		if now < b.T || now >= b.Until {
			continue
		}
		reason := fmt.Sprintf("trip reason: %d losses", b.Losses)
		if b.LossThr != "" {
			thr := b.LossThr
			if f, err := strconv.ParseFloat(thr, 64); err == nil {
				thr = F(f, 2)
			}
			reason += " " + G.Ge + thr + " in " + b.WinMin + " min"
		}
		if b.LastMint != "" {
			reason += fmt.Sprintf(", last %s %s", RuneSlice(b.LastMint, 8), Sol(b.LastPnl, true, 4, true))
		}
		if b.LogAt != 0 && now >= b.LogAt {
			bl = append(bl, Block{Kind: "breaker_log", Text: "breaker " + G.Arrow + " log at " + T12(float64(b.LogAt), false) + " (its pause ended early; would have run until " +
				T12(float64(b.Until), false) + ")", Sev: "info"})
			break
		}
		if T.brkModeAt(now) == "log" {
			break
		}
		bl = append(bl, Block{Kind: "breaker", Text: "PAUSED: breaker (until " + T12(float64(b.Until), false) + ", " + minsLeft(b.Until, now) + "; " + reason + ")",
			Reason: reason, Until: b.Until, Sev: "bad"})
		break
	}
	// the pause window / manual pause (dip47)
	if R := v.V5; R != nil && R.Pause != nil && R.Pause.Active {
		w := ""
		if n := len(M.V5.pauses); n > 0 {
			w = M.V5.pauses[n-1].Window
		}
		if w == "manual" || (w == "" && R.Pause.Manual == "on") {
			bl = append(bl, Block{Kind: "pause_manual", Text: "PAUSED: manual (pause_now on)", Sev: "bad"})
		} else {
			until := nextEdge(parsePause(w), now, false)
			txt := "PAUSED: pause window " + w + " PKT"
			if until > 0 {
				txt += " (until " + T12(float64(until), false) + ", " + minsLeft(until, now) + ")"
			}
			bl = append(bl, Block{Kind: "pause_window", Text: txt, Until: until, Sev: "bad"})
		}
	}
	// the 24 h fee budget
	if S.D24.FeePaused {
		bl = append(bl, Block{Kind: "fee_budget", Text: "PAUSED: fee budget (24 h failed-try fees at the budget; resumes as they roll off)", Sev: "bad"})
	}
	state, sev := "", ""
	for _, b := range bl {
		if b.Sev == "bad" {
			switch b.Kind {
			case "stopping":
				state = "STOPPING: " + b.Reason
			case "stopped":
				state = "PRE-SEND STOPPED"
			case "breaker":
				state = "PAUSED: breaker"
			case "pause_window":
				state = "PAUSED: pause window"
			case "pause_manual":
				state = "PAUSED: manual"
			case "fee_budget":
				state = "PAUSED: fee budget"
			}
			if b.Until > 0 {
				state += " until " + T12(float64(b.Until), false)
			}
			sev = "bad"
			break
		}
	}
	// IDLE: buying is enabled, a dip43+ run that arms, nothing armed for >= 15 min
	if state == "" && T.anyArm && v.D43 != nil {
		last := max(T.lastArm, v.TFirst)
		if idle := now - last; idle >= 15*60e9 {
			state, sev = fmt.Sprintf("IDLE (no arms in %d min)", idle/60e9), "warn"
			bl = append(bl, Block{Kind: "idle", Text: fmt.Sprintf("IDLE: no window armed since %s (%d min)", T12(float64(last), false), idle/60e9), Sev: "warn"})
		}
	}
	return state, sev, bl
}

// TradingLine: the blocking states in one line ("" = none).
func TradingLine(bl []Block) string {
	var ps []string
	for _, b := range bl {
		ps = append(ps, b.Text)
	}
	return strings.Join(ps, " · ")
}

var _ = json.Valid
