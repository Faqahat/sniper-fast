package core

import (
	"bytes"
	"encoding/json"
	"io"
	"math"
	"sort"
	"strconv"
	"strings"
)

// Num is a JSON number the way Python's json module gives it: an int, a float, or None.
type Num struct {
	K uint8 // NumNone, NumInt, NumFloat
	I int64
	F float64
}

const (
	NumNone uint8 = iota
	NumInt
	NumFloat
)

func IntNum(i int64) Num     { return Num{K: NumInt, I: i} }
func FloatNum(f float64) Num { return Num{K: NumFloat, F: f} }

// Ok: not None.
func (n Num) Ok() bool { return n.K != NumNone }

// Truthy: Python bool(x) (None and 0 / 0.0 are false).
func (n Num) Truthy() bool {
	switch n.K {
	case NumInt:
		return n.I != 0
	case NumFloat:
		return n.F != 0
	}
	return false
}

// Float: the value as a float (None -> 0).
func (n Num) Float() float64 {
	if n.K == NumInt {
		return float64(n.I)
	}
	return n.F
}

// Int: the value as an int (floats truncated, like Python's int(); None -> 0).
func (n Num) Int() int64 {
	if n.K == NumFloat {
		if math.IsNaN(n.F) || math.IsInf(n.F, 0) {
			return 0
		}
		return int64(n.F)
	}
	return n.I
}

// Or is Python's `a or b`.
func (n Num) Or(b Num) Num {
	if n.Truthy() {
		return n
	}
	return b
}

// Repr is str(x) for the number (Python).
func (n Num) Repr() string {
	switch n.K {
	case NumInt:
		return strconv.FormatInt(n.I, 10)
	case NumFloat:
		return PyRepr(n.F)
	}
	return "None"
}

// Obj is a decoded JSON object (numbers kept as json.Number).
type Obj = map[string]any

// DecodeObj parses one JSON line the way json.loads would accept it (a single value, nothing after it).
// ok=false: not valid JSON. isObj=false: valid JSON but not an object.
func DecodeObj(line []byte) (o Obj, isObj bool, ok bool) {
	dec := json.NewDecoder(bytes.NewReader(line))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		return nil, false, false
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, false, false
	}
	m, isMap := v.(map[string]any)
	return m, isMap, true
}

// toNum converts a raw decoded JSON value to a Num (bools and non-numbers -> None).
func toNum(v any) Num {
	jn, ok := v.(json.Number)
	if !ok {
		return Num{}
	}
	s := string(jn)
	if strings.ContainsAny(s, ".eE") {
		f, err := strconv.ParseFloat(s, 64)
		if err != nil && !math.IsInf(f, 0) {
			return Num{}
		}
		return FloatNum(f)
	}
	i, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		// beyond int64: Python keeps a big int; every use here would treat it as out of range
		f, _ := strconv.ParseFloat(s, 64)
		return FloatNum(f) // |x| > 9.2e18: dropped by the range checks that follow
	}
	return IntNum(i)
}

// TimeOK is Python's time_ok(t): an int (ns) from 2017..2049.
func TimeOK(n Num) bool {
	return n.K == NumInt && n.I > 1_500_000_000_000_000_000 && n.I < 2_500_000_000_000_000_000
}

// TimeOKi is time_ok for an int that is known to be an int (0 = None).
func TimeOKi(t int64) bool {
	return t > 1_500_000_000_000_000_000 && t < 2_500_000_000_000_000_000
}

var timeKeys = map[string]bool{"t": true, "t_fire": true, "t_dump_rx": true, "t_send": true, "arm_rule_on_at": true}

// NumKey is o.get(k) for a key in NUM_KEYS after _san: a valid number or None.
func NumKey(o Obj, k string) Num {
	v, ok := o[k]
	if !ok {
		return Num{}
	}
	n := toNum(v)
	if !n.Ok() {
		return Num{}
	}
	if n.K == NumFloat && (math.IsNaN(n.F) || math.Abs(n.F) > 1e20) {
		return Num{}
	}
	if timeKeys[k] && !TimeOK(n) {
		return Num{}
	}
	return n
}

// StrKey is o.get(k) for a key in STR_KEYS after _san: (value, true) for a string, ("", false) otherwise.
func StrKey(o Obj, k string) (string, bool) {
	v, ok := o[k]
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	return s, ok
}

// StrOr is `o.get(k) or dflt` for a STR_KEYS key.
func StrOr(o Obj, k, dflt string) string {
	if s, ok := StrKey(o, k); ok && s != "" {
		return s
	}
	return dflt
}

// Truthy is Python's bool() of a raw decoded JSON value.
func Truthy(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case json.Number:
		n := toNum(x)
		return n.Truthy()
	case string:
		return x != ""
	case []any:
		return len(x) > 0
	case map[string]any:
		return len(x) > 0
	}
	return true
}

// IsFalse is `v is False` (exactly JSON false).
func IsFalse(v any) bool {
	b, ok := v.(bool)
	return ok && !b
}

// SubObj returns o[k] when it is an object (Python isinstance(v, dict)).
func SubObj(o Obj, k string) (Obj, bool) {
	v, ok := o[k]
	if !ok {
		return nil, false
	}
	m, ok := v.(map[string]any)
	return m, ok
}

// ListKey returns o[k] when it is a list.
func ListKey(o Obj, k string) ([]any, bool) {
	v, ok := o[k]
	if !ok {
		return nil, false
	}
	l, ok := v.([]any)
	return l, ok
}

// SanList is the _san treatment of "land" / "sell_land": numbers (|x| < 4e18, not bool) else None, and
// element 2 (a time) must pass time_ok. A non-list is treated as empty.
func SanList(o Obj, k string) []Num {
	l, ok := ListKey(o, k)
	if !ok {
		return nil
	}
	out := make([]Num, len(l))
	for i, x := range l {
		n := toNum(x)
		if n.Ok() && math.Abs(n.Float()) < 4e18 && !(n.K == NumFloat && math.IsNaN(n.F)) {
			out[i] = n
		}
	}
	if len(out) > 2 && out[2].Ok() && !TimeOK(out[2]) {
		out[2] = Num{}
	}
	return out
}

// PyStr is str(v) for a decoded JSON value (Python repr rules for containers).
func PyStr(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case bool:
		if x {
			return "True"
		}
		return "False"
	case json.Number:
		return toNum(x).Repr()
	case string:
		return x
	case []any:
		parts := make([]string, len(x))
		for i, e := range x {
			parts[i] = pyRepr(e)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case map[string]any:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		parts := make([]string, len(keys))
		for i, k := range keys {
			parts[i] = pyRepr(k) + ": " + pyRepr(x[k])
		}
		return "{" + strings.Join(parts, ", ") + "}"
	}
	return "?"
}

func pyRepr(v any) string {
	if s, ok := v.(string); ok {
		return "'" + strings.ReplaceAll(s, "'", "\\'") + "'"
	}
	return PyStr(v)
}

// JSONCompact is json.dumps(v) for a decoded value (only used for substring checks such as "6042").
func JSONCompact(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return ""
	}
	return string(b)
}
