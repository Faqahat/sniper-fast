// Package core is dipmon's data side: incremental tails of a run's .jsonl + .log, the parsed model, the
// accounting (= the Python dipmon v1 and the standard run reports, to the lamport), the view built from it,
// the snapshot / JSON output, the engine / price / system probes.
//
// This file: Python-compatible formatting, so every number the Go version prints is the string Python prints.
package core

import (
	"math"
	"strconv"
	"strings"
	"unicode/utf8"
)

// PyRepr is Python's repr(float): the shortest round-trip digits, fixed notation for 1e-4 <= |x| < 1e16
// (with ".0" when integral), scientific notation otherwise ("1e-05", "1.7615244e+18").
func PyRepr(f float64) string {
	if math.IsNaN(f) {
		return "NaN"
	}
	if math.IsInf(f, 1) {
		return "Infinity"
	}
	if math.IsInf(f, -1) {
		return "-Infinity"
	}
	if f == 0 {
		if math.Signbit(f) {
			return "-0.0"
		}
		return "0.0"
	}
	// shortest digits + decimal exponent
	e := strconv.FormatFloat(f, 'e', -1, 64) // e.g. "-1.7615244e+18"
	neg := false
	if e[0] == '-' {
		neg = true
		e = e[1:]
	}
	i := strings.IndexByte(e, 'e')
	mant, expS := e[:i], e[i+1:]
	exp, _ := strconv.Atoi(expS)
	digits := strings.Replace(mant, ".", "", 1)
	decpt := exp + 1 // position of the decimal point after the first digit
	var out string
	if decpt > -4 && decpt <= 16 {
		// fixed notation
		switch {
		case decpt <= 0:
			out = "0." + strings.Repeat("0", -decpt) + digits
		case decpt >= len(digits):
			out = digits + strings.Repeat("0", decpt-len(digits)) + ".0"
		default:
			out = digits[:decpt] + "." + digits[decpt:]
		}
	} else {
		m := digits[:1]
		if len(digits) > 1 {
			m += "." + digits[1:]
		}
		x := decpt - 1
		sign := "+"
		if x < 0 {
			sign = "-"
			x = -x
		}
		xs := strconv.Itoa(x)
		if len(xs) < 2 {
			xs = "0" + xs
		}
		out = m + "e" + sign + xs
	}
	if neg {
		return "-" + out
	}
	return out
}

// F is Python's f"{x:.{prec}f}".
func F(x float64, prec int) string {
	if math.IsInf(x, 1) {
		return "inf"
	}
	if math.IsInf(x, -1) {
		return "-inf"
	}
	if math.IsNaN(x) {
		return "nan"
	}
	return strconv.FormatFloat(x, 'f', prec, 64)
}

// FS is Python's f"{x:+.{prec}f}".
func FS(x float64, prec int) string {
	s := F(x, prec)
	if !strings.HasPrefix(s, "-") {
		return "+" + s
	}
	return s
}

// commas inserts thousands separators into a plain decimal number string ("-1234567.5" -> "-1,234,567.5").
func commas(s string) string {
	neg := strings.HasPrefix(s, "-") || strings.HasPrefix(s, "+")
	sign := ""
	if neg {
		sign, s = s[:1], s[1:]
	}
	intPart, frac := s, ""
	if i := strings.IndexByte(s, '.'); i >= 0 {
		intPart, frac = s[:i], s[i:]
	}
	if len(intPart) <= 3 {
		return sign + intPart + frac
	}
	var b strings.Builder
	pre := len(intPart) % 3
	if pre > 0 {
		b.WriteString(intPart[:pre])
	}
	for i := pre; i < len(intPart); i += 3 {
		if b.Len() > 0 {
			b.WriteByte(',')
		}
		b.WriteString(intPart[i : i+3])
	}
	return sign + b.String() + frac
}

// FC is Python's f"{x:,.{prec}f}".
func FC(x float64, prec int) string { return commas(F(x, prec)) }

// IC is Python's f"{n:,}" for an int.
func IC(n int64) string { return commas(strconv.FormatInt(n, 10)) }

// Itoa is str(int).
func Itoa(n int64) string { return strconv.FormatInt(n, 10) }

// G0 is Python's f"{x:g}" (6 significant digits, trailing zeros dropped).
func G0(x float64) string {
	if x == math.Trunc(x) && math.Abs(x) < 1e6 {
		return strconv.FormatInt(int64(x), 10)
	}
	s := strconv.FormatFloat(x, 'g', 6, 64)
	if strings.Contains(s, "e") {
		return s
	}
	if strings.Contains(s, ".") {
		s = strings.TrimRight(strings.TrimRight(s, "0"), ".")
	}
	return s
}

// pySpace reports Python's str.isspace() for one rune.
func pySpace(r rune) bool {
	switch r {
	case ' ', '\t', '\n', '\v', '\f', '\r', 0x1c, 0x1d, 0x1e, 0x1f, 0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000:
		return true
	}
	return r >= 0x2000 && r <= 0x200a
}

// PyStrip is Python's str.strip() (Unicode whitespace as Python defines it).
func PyStrip(s string) string {
	return strings.TrimFunc(s, pySpace)
}

// RuneSlice returns the first n code points of s (Python s[:n]).
func RuneSlice(s string, n int) string {
	if n <= 0 {
		return ""
	}
	if len(s) <= n {
		return s
	}
	i := 0
	for k := range s {
		if i == n {
			return s[:k]
		}
		i++
	}
	return s
}

// RuneLen is len(s) in code points.
func RuneLen(s string) int { return utf8.RuneCountInString(s) }

// PadRight / PadLeft are Python's f"{s:<n}" / f"{s:>n}" (code points).
func PadRight(s string, n int) string {
	if k := RuneLen(s); k < n {
		return s + strings.Repeat(" ", n-k)
	}
	return s
}

func PadLeft(s string, n int) string {
	if k := RuneLen(s); k < n {
		return strings.Repeat(" ", n-k) + s
	}
	return s
}

// ------------------------------------------------------------------------------------------- Python's json.dumps(indent=1)

// JObj is an insertion-ordered JSON object.
type JObj struct {
	Keys []string
	Vals []any
}

// Set appends (or replaces) a key.
func (o *JObj) Set(k string, v any) *JObj {
	for i, x := range o.Keys {
		if x == k {
			o.Vals[i] = v
			return o
		}
	}
	o.Keys = append(o.Keys, k)
	o.Vals = append(o.Vals, v)
	return o
}

// Get returns a key's value.
func (o *JObj) Get(k string) (any, bool) {
	for i, x := range o.Keys {
		if x == k {
			return o.Vals[i], true
		}
	}
	return nil, false
}

// PyFloat marks a float that must print as Python's repr even when integral ("100.0").
type PyFloat float64

// JSONDumps renders v the way Python's json.dumps(v, indent=1) does (ensure_ascii, ", " / ": ").
// Values: nil, bool, int, int64, PyFloat, float64, string, []any, *JObj, Num.
func JSONDumps(v any) string {
	var b strings.Builder
	dumpValue(&b, v, 0)
	return b.String()
}

func dumpValue(b *strings.Builder, v any, level int) {
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case int:
		b.WriteString(strconv.Itoa(x))
	case int64:
		b.WriteString(strconv.FormatInt(x, 10))
	case PyFloat:
		b.WriteString(PyRepr(float64(x)))
	case float64:
		b.WriteString(PyRepr(x))
	case Num:
		switch x.K {
		case NumInt:
			b.WriteString(strconv.FormatInt(x.I, 10))
		case NumFloat:
			b.WriteString(PyRepr(x.F))
		default:
			b.WriteString("null")
		}
	case string:
		dumpString(b, x)
	case []any:
		if len(x) == 0 {
			b.WriteString("[]")
			return
		}
		b.WriteString("[")
		for i, e := range x {
			if i > 0 {
				b.WriteString(",")
			}
			b.WriteString("\n")
			b.WriteString(strings.Repeat(" ", level+1))
			dumpValue(b, e, level+1)
		}
		b.WriteString("\n")
		b.WriteString(strings.Repeat(" ", level))
		b.WriteString("]")
	case *JObj:
		if x == nil || len(x.Keys) == 0 {
			b.WriteString("{}")
			return
		}
		b.WriteString("{")
		for i, k := range x.Keys {
			if i > 0 {
				b.WriteString(",")
			}
			b.WriteString("\n")
			b.WriteString(strings.Repeat(" ", level+1))
			dumpString(b, k)
			b.WriteString(": ")
			dumpValue(b, x.Vals[i], level+1)
		}
		b.WriteString("\n")
		b.WriteString(strings.Repeat(" ", level))
		b.WriteString("}")
	default:
		dumpString(b, "?")
	}
}

const hexDigits = "0123456789abcdef"

func dumpString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 || r > 0x7e {
				if r == utf8.RuneError {
					r = 0xfffd
				}
				if r > 0xffff {
					r -= 0x10000
					writeU(b, 0xd800+(r>>10))
					writeU(b, 0xdc00+(r&0x3ff))
				} else {
					writeU(b, r)
				}
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
}

func writeU(b *strings.Builder, r rune) {
	b.WriteString(`\u`)
	b.WriteByte(hexDigits[(r>>12)&0xf])
	b.WriteByte(hexDigits[(r>>8)&0xf])
	b.WriteByte(hexDigits[(r>>4)&0xf])
	b.WriteByte(hexDigits[r&0xf])
}
