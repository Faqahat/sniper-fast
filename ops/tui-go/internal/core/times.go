package core

import (
	"math"
	"strconv"
	"time"
)

// PKT is Pakistan time (UTC+5, no DST): every time dipmon shows.
var PKT = time.FixedZone("PKT", 5*3600)

// PyTime converts a ns timestamp the way Python's datetime.fromtimestamp(ns / 1e9, PKT) does: the ns are
// divided as a float, the fraction is rounded half-even to microseconds (so a time 0.4 us before a second
// shows that next second, as in the Python version).
func PyTime(ns float64) time.Time {
	f := ns / 1e9
	sec := math.Floor(f)
	us := math.RoundToEven((f - sec) * 1e6)
	if us >= 1e6 {
		sec++
		us -= 1e6
	}
	return time.Unix(int64(sec), int64(us)*1000).In(PKT)
}

// Clock formats a ns time in PKT with the Python strftime subset used here: "%H:%M:%S", "%H:%M",
// "%Y-%m-%d %H:%M:%S". 0 -> the dash glyph.
func Clock(ns float64, layout string) string {
	if ns == 0 {
		return G.Dash
	}
	if math.IsNaN(ns) || math.IsInf(ns, 0) || math.Abs(ns) > 9e21 {
		return "?"
	}
	d := PyTime(ns)
	switch layout {
	case "%H:%M":
		return two(d.Hour()) + ":" + two(d.Minute())
	case "%Y-%m-%d %H:%M:%S":
		return strconv.Itoa(d.Year()) + "-" + two(int(d.Month())) + "-" + two(d.Day()) + " " + two(d.Hour()) + ":" + two(d.Minute()) + ":" + two(d.Second())
	default:
		return two(d.Hour()) + ":" + two(d.Minute()) + ":" + two(d.Second())
	}
}

func two(n int) string {
	if n < 10 {
		return "0" + strconv.Itoa(n)
	}
	return strconv.Itoa(n)
}

// T12 is a PKT clock time in 12-hour form: "3:26 PM", with secs "3:26:51 PM".
func T12(ns float64, secs bool) string {
	if ns == 0 {
		return G.Dash
	}
	if math.IsNaN(ns) || math.IsInf(ns, 0) || math.Abs(ns) > 9e21 {
		return "?"
	}
	d := PyTime(ns)
	h := d.Hour() % 12
	if h == 0 {
		h = 12
	}
	s := strconv.Itoa(h) + ":" + two(d.Minute())
	if secs {
		s += ":" + two(d.Second())
	}
	if d.Hour() < 12 {
		return s + " AM"
	}
	return s + " PM"
}

// T12Date is "Oct 27, 3:26 PM".
func T12Date(ns float64, secs bool) string {
	if ns == 0 {
		return G.Dash
	}
	d := PyTime(ns)
	return d.Format("Jan") + " " + strconv.Itoa(d.Day()) + ", " + T12(ns, secs)
}

// HMS is Python's hms(sec): h:mm (or h:mm:ss). ok=false -> the dash.
func HMS(sec float64, ok bool, secs bool) string {
	if !ok {
		return G.Dash
	}
	s := int64(math.Max(0, sec))
	h, m, x := s/3600, (s%3600)/60, s%60
	out := strconv.FormatInt(h, 10) + ":" + two(int(m))
	if secs {
		out += ":" + two(int(x))
	}
	return out
}

// Dur is a duration: "2h 10m" / "45m" / "30s".
func Dur(sec float64, ok bool) string {
	if !ok {
		return G.Dash
	}
	s := int64(math.Max(0, sec))
	if s < 60 {
		return strconv.FormatInt(s, 10) + "s"
	}
	h, m := s/3600, (s%3600)/60
	if h > 0 {
		return strconv.FormatInt(h, 10) + "h " + two(int(m)) + "m"
	}
	return strconv.FormatInt(m, 10) + "m"
}

// AgeS is Python's age_s(sec): "12s" / "5m" / "1.5h".
func AgeS(sec float64, ok bool) string {
	if !ok {
		return G.Dash
	}
	sec = math.Max(0, sec)
	if sec < 90 {
		return F(sec, 0) + "s"
	}
	if sec < 5400 {
		return F(sec/60, 0) + "m"
	}
	return F(sec/3600, 1) + "h"
}

// HHMMns is Python's hhmm_ns(base, hh, mm): the HH:MM PKT clock time on or after (base - 1 h), in ns.
func HHMMns(base int64, hh, mm int) (int64, bool) {
	if base == 0 || hh < 0 || hh >= 24 || mm < 0 || mm >= 60 {
		return 0, false
	}
	d0 := PyTime(float64(base))
	x := time.Date(d0.Year(), d0.Month(), d0.Day(), hh, mm, 0, 0, PKT)
	if x.Before(d0.Add(-time.Hour)) {
		x = x.AddDate(0, 0, 1)
	}
	return x.Unix() * 1_000_000_000, true
}

// DayRange is the PKT calendar day holding ns: (first unix minute, end unix minute, "Tue Oct 27").
func DayRange(ns float64) (int64, int64, string) {
	d := PyTime(ns)
	d0 := time.Date(d.Year(), d.Month(), d.Day(), 0, 0, 0, 0, PKT)
	m0 := d0.Unix() / 60
	return m0, m0 + 1440, d0.Format("Mon Jan") + " " + strconv.Itoa(d0.Day())
}
