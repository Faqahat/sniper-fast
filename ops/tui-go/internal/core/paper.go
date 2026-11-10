package core

// The paper partition (dipmon 3.3 / v4): the engine's shadow (row c, net incl. its tries) on the same T2 triggers as the live
// run, split by what the live run did with each trigger: armed and sent at least one try / skipped by a filter / armed with
// nothing sent (every send withheld). The engine's status line has the shadow's whole-run net; the split is rebuilt from the
// records: each shadow window's net_cheap (its exit) minus its unfilled tries (row c's armed slots x 20 per slot x the
// shadow's cheap failed-try fee), exactly the engine's own formula per window.

const (
	paperK       = 20                          // the shadow's tries per slot (presend.rs K_ABC)
	paperFeeLams = 5000 + 60_000*1_000/1e6     // the shadow's cheap failed try (presend.rs FEE_CHEAP, lamports)
	paperFee     = float64(paperFeeLams) / 1e9 // SOL
)

// PaperSplit is the partition.
type PaperSplit struct {
	Any                 bool // the run has shadow windows (presend_arm records)
	SentN, SkipN, NoneN int  // shadow fills by what live did with the trigger
	SentNet, SkipNet    float64
	NoneNet             float64
	OtherN              int // shadow fills whose trigger live never saw (no live skip / arm: a paused or stopped live run)
	OtherNet            float64
	Size                float64 // the shadow's row c size (its first fill's sol_in, SOL)
	HasSize             bool
}

// Paper computes the partition (cheap: one pass over the shadow windows).
func (F *FiltAcc) Paper() PaperSplit {
	P := PaperSplit{Any: len(F.shArms) > 0}
	if F.hasSh0 {
		P.Size, P.HasSize = F.shSize0, true
	}
	for _, a := range F.shArms {
		sig := a.sig
		v, n := 0.0, 0
		if a.exit != nil {
			v, n = *a.exit, 1
		}
		if a.hasSlots {
			v -= float64(max(paperK*a.slots-int64(n), 0)) * paperFee
		}
		switch la, armed := F.liveSigA[sig]; {
		case armed && F.liveSent[la] == 0:
			P.NoneN += n
			P.NoneNet += v
		case armed:
			P.SentN += n
			P.SentNet += v
		case F.skipSig[sig]:
			P.SkipN += n
			P.SkipNet += v
		default:
			P.OtherN += n
			P.OtherNet += v
		}
	}
	return P
}
