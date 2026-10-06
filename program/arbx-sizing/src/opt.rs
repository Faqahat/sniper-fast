//! The locator (DESIGN.md §3): it finds candidate sizes from cheap real-valued models in `Fx`. It decides nothing:
//! the planner evaluates every candidate exactly.
//! * Möbius × Möbius: the closed form `x* = (√(A·B) − B)/C` of the composed curve (§3.3).
//! * Mixes with DLMM: the marginal walk over breakpoints (bin ends of either leg, mapped into `x`), with a closed-form
//!   interior root per interval and the non-concavity guard (§3.4). The DLMM bins are walked once with their exact
//!   drain amounts; the exact swap states passed near each optimum (and the furthest one) go back to the planner,
//!   which resumes its exact quotes from them instead of walking from the active bin again.
//! * Golden section over exact evaluations (§3.6), for states the model refuses.
//! * Concentrated-liquidity legs (Raydium CLMM, Orca Whirlpool; PLAN-ADDENDUM WP-21): piecewise Möbius. Each piece is
//!   one exact swap step (a constant-liquidity range between initialized ticks, tick-spacing or tick-group boundaries)
//!   with its exact input and output, modelled by the range's virtual-reserve curve; a limit-order fill at a tick is
//!   a linear piece (DESIGN.md §2.8, §3.4).
use crate::fx::Fx;
use crate::venue::dlmm::{Cursor, DlmmLeg, RateMemo, MAX_ARRAYS};
#[cfg(feature = "rayclmm")]
use crate::venue::raydium_clmm::{self, RayClmmLeg};
#[cfg(feature = "whirlpool")]
use crate::venue::orca_whirlpool::{self, WhirlLeg};

/// Walk steps per pair: every step ends at least one piece of one leg, a Möbius leg has one piece and a DLMM leg
/// one per bin with liquidity it may consume (its budget, and at most 70 per passed array). So the bound is per leg
/// (REVIEW.md F3): it never cuts a walk short. A CLMM leg's pieces are bounded by its walk budget (swap steps, at most
/// 255 on chain, two pieces per step at most) and by `MAX_STEPS` off chain, where a long walk ends the domain.
pub const MAX_STEPS: usize = 2 * (MAX_ARRAYS * 70) + 4;
/// local optima kept per pair
pub const MAX_OPTIMA: usize = 3;

/// `M(u) = a·u/(b + c·u)` on `[0, cap)` (cap = ∞ when unbounded); `ab` = a·b, kept for the derivative
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Mob { pub a: Fx, pub b: Fx, pub c: Fx, pub cap: Fx, pub ab: Fx }

impl Mob {
    pub fn new(a: Fx, b: Fx, c: Fx, cap: Fx) -> Mob { Mob { a, b, c, cap, ab: a.mul(b) } }
    #[inline(never)]
    pub fn f(&self, u: Fx) -> Fx { self.a.mul(u).div(self.b.add(self.c.mul(u))) }
    /// M'(u) = a·b/(b + c·u)²
    #[inline(never)]
    pub fn d(&self, u: Fx) -> Fx { let t = self.b.add(self.c.mul(u)); self.ab.div(t.mul(t)) }
    /// M⁻¹(v) = b·v/(a − c·v), ∞ when v ≥ a/c
    #[inline(never)]
    pub fn inv(&self, v: Fx) -> Fx {
        let cv = self.c.mul(v);
        if cv >= self.a { return Fx::INF; }
        self.b.mul(v).div(self.a.sub(cv))
    }
}

/// `y = v0 + s·(u − u0)` on `[u0, u1)`, ending at `v1`; one DLMM bin (`id`, `price` for the guard's bound)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Line { pub u0: Fx, pub v0: Fx, pub s: Fx, pub u1: Fx, pub v1: Fx, pub id: i32, pub price: u128 }

impl Line {
    pub fn f(&self, u: Fx) -> Fx { self.v0.add(self.s.mul(u.sub(self.u0))) }
    pub fn inv(&self, v: Fx) -> Fx { self.u0.add(v.sub(self.v0).div(self.s)) }
}

/// One exact CLMM swap step in absolute coordinates: `y = v0 + M(u − u0)` on `[u0, u1)`, ending exactly at `v1` (the
/// step's exact input and output); `m` is the step's curve in local coordinates (`m.c == 0`: a line, a limit-order fill
/// at the tick's price). `bound`: an upper bound on the slope of every later piece of the leg.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Seg { pub u0: Fx, pub v0: Fx, pub m: Mob, pub u1: Fx, pub v1: Fx, pub bound: Fx }

impl Seg {
    pub fn f(&self, u: Fx) -> Fx { self.v0.add(self.m.f(u.sub(self.u0))) }
    pub fn d(&self, u: Fx) -> Fx { self.m.d(u.sub(self.u0)) }
    pub fn inv(&self, v: Fx) -> Fx { self.u0.add(self.m.inv(v.sub(self.v0))) }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Piece { Mob(Mob), Line(Line), Seg(Seg), End }

impl Piece {
    fn end(&self) -> Fx { match self { Piece::Mob(m) => m.cap, Piece::Line(l) => l.u1, Piece::Seg(g) => g.u1, Piece::End => Fx::ZERO } }
    fn f(&self, u: Fx) -> Fx { match self { Piece::Mob(m) => m.f(u), Piece::Line(l) => l.f(u), Piece::Seg(g) => g.f(u), Piece::End => Fx::ZERO } }
    /// the value at the piece's end (a line's and a step's are exact)
    fn f_end(&self) -> Fx { match self { Piece::Mob(m) => m.f(m.cap), Piece::Line(l) => l.v1, Piece::Seg(g) => g.v1, Piece::End => Fx::ZERO } }
    fn d(&self, u: Fx) -> Fx { match self { Piece::Mob(m) => m.d(u), Piece::Line(l) => l.s, Piece::Seg(g) => g.d(u), Piece::End => Fx::ZERO } }
    fn inv(&self, v: Fx) -> Fx { match self { Piece::Mob(m) => m.inv(v), Piece::Line(l) => l.inv(v), Piece::Seg(g) => g.inv(v), Piece::End => Fx::INF } }
}

/// A leg's model
#[derive(Clone, Copy, Debug)]
pub enum LegModel<'l, 'a> {
    Mobius(Mob),
    Bins(&'l DlmmLeg<'a>),
    /// Raydium CLMM: its exact swap steps (feature `rayclmm`)
    #[cfg(feature = "rayclmm")]
    RayClmm(&'l RayClmmLeg<'a>),
    /// Orca Whirlpool: its exact swap steps (feature `whirlpool`)
    #[cfg(feature = "whirlpool")]
    Whirl(&'l WhirlLeg<'a>),
}

/// Exact swap states (DLMM cursors) the locator passed on one leg near a point: positioned at the bin of the piece it
/// was in and at the bin of the piece before. The planner resumes exact quotes from the furthest one an amount
/// reaches.
pub type Marks<'l, 'a> = [Option<Cursor<'l, 'a>>; 2];

/// The pieces of a leg in input order: one Möbius piece, or one line per DLMM bin with liquidity. A DLMM stream
/// walks the bins once with the exact drain amounts and keeps the exact states it passes.
pub struct Stream<'l, 'a> {
    mob: Option<Mob>,
    leg: Option<&'l DlmmLeg<'a>>,
    /// a CLMM leg's exact swap steps, and the pieces of the step read but not yet handed out
    #[cfg(feature = "rayclmm")]
    ray: Option<raydium_clmm::Steps<'l, 'a>>,
    #[cfg(feature = "whirlpool")]
    whirl: Option<orca_whirlpool::Steps<'l, 'a>>,
    queue: [Option<Seg>; 2],
    /// the furthest exact state: where the next piece starts, unless `ended`
    cur: Option<Cursor<'l, 'a>>,
    ended: bool,
    /// the starts of the current and the previous piece (`starts[which]` is the current one)
    starts: Marks<'l, 'a>,
    which: usize,
    /// the current piece's end (u1, v1), the next piece's start
    u: Fx,
    v: Fx,
    memo: RateMemo,
    /// bins with liquidity walked
    pub bins: u16,
}

impl<'l, 'a> Stream<'l, 'a> {
    pub fn new(m: &LegModel<'l, 'a>) -> Self {
        let mut st = Stream { mob: None, leg: None, cur: None, ended: false, starts: [None; 2], which: 0, u: Fx::ZERO, v: Fx::ZERO,
            memo: RateMemo::default(), bins: 0,
            #[cfg(feature = "rayclmm")]
            ray: None,
            #[cfg(feature = "whirlpool")]
            whirl: None,
            queue: [None; 2] };
        match m {
            LegModel::Mobius(mob) => st.mob = Some(*mob),
            LegModel::Bins(leg) => { st.leg = Some(*leg); st.cur = Some(leg.start()); }
            #[cfg(feature = "rayclmm")]
            LegModel::RayClmm(leg) => st.ray = Some(leg.stream()),
            #[cfg(feature = "whirlpool")]
            LegModel::Whirl(leg) => st.whirl = Some(leg.stream()),
        }
        st
    }

    /// The next piece of a CLMM leg: one exact swap step (range or limit-order fill) as a [`Seg`]
    #[allow(unused_mut, unused_variables)]
    fn next_clmm(&mut self) -> Option<Piece> {
        if let Some(g) = self.queue.iter_mut().find_map(|q| q.take()) { return Some(Piece::Seg(g)); }
        let (u, v) = (self.u, self.v);
        let mut buf: [Option<Seg>; 2] = [None; 2];
        let mut n = 0usize;
        let mut cu = u;
        let mut cv = v;
        let mut push = |used: u64, out: u64, mob: Option<(Fx, Fx, Fx)>, bound: Fx| {
            if used == 0 { return; }
            let (fu, fo) = (Fx::from_u64(used), Fx::from_u64(out));
            // a line (a limit-order fill at the tick's price): a = out, b = used, c = 0 — the slope out/used
            let (a, b, c) = mob.unwrap_or((fo, fu, Fx::ZERO));
            let g = Seg { u0: cu, v0: cv, m: Mob::new(a, b, c, fu), u1: cu.add(fu), v1: cv.add(fo), bound };
            cu = g.u1;
            cv = g.v1;
            if let Some(slot) = buf.get_mut(n) { *slot = Some(g); n += 1; }
        };
        let mut any = false;
        #[cfg(feature = "rayclmm")]
        if let Some(st) = self.ray.as_mut() {
            any = true;
            if st.next(&mut |p| push(p.used, p.out, p.mobius, p.bound)).is_err() { self.ended = true; }
        }
        #[cfg(feature = "whirlpool")]
        if let Some(st) = self.whirl.as_mut() {
            any = true;
            if st.next(&mut |p| push(p.used, p.out, p.mobius, p.bound)).is_err() { self.ended = true; }
        }
        if !any { return None; }
        self.bins = self.bins.saturating_add(1);
        let [first, second] = buf;
        let Some(g) = first else {
            // a step with no input taken (a zero step on a boundary): read on
            return if self.ended { Some(Piece::End) } else { self.next_clmm() };
        };
        self.u = second.map_or(g.u1, |h| h.u1);
        self.v = second.map_or(g.v1, |h| h.v1);
        self.queue = [second, None];
        Some(Piece::Seg(g))
    }

    #[inline(never)]
    pub fn next(&mut self) -> Piece {
        if let Some(m) = self.mob.take() { return Piece::Mob(m); }
        if let Some(p) = self.next_clmm() { return p; }
        if self.ended { return Piece::End; }
        let (Some(leg), Some(mut c)) = (self.leg, self.cur) else { return Piece::End };
        let mut start = c;
        match leg.advance(&mut c, &mut self.memo, Some(&mut start)) {
            Ok((bp, pass)) => {
                self.which ^= 1;
                if let Some(slot) = self.starts.get_mut(self.which) { *slot = Some(start); }
                if pass { self.cur = Some(c); } else { self.ended = true; }
                self.bins = self.bins.saturating_add(1);
                let (u0, v0) = (self.u, self.v);
                self.u = Fx::from_u64(start.used.saturating_add(bp.drain_in));
                self.v = Fx::from_u64(start.out.saturating_add(bp.out));
                Piece::Line(Line { u0, v0, s: Fx::from_u64(bp.out).div(Fx::from_u64(bp.drain_in)), u1: self.u, v1: self.v, id: bp.id, price: bp.price })
            }
            Err(_) => { self.ended = true; Piece::End }
        }
    }

    /// an upper bound on this leg's slope for inputs ≥ u (`ended`: u is the piece's end)
    fn bound_after(&self, p: &Piece, u: Fx, ended: bool) -> Fx {
        match (p, self.leg) {
            (Piece::Mob(m), _) => if ended { Fx::ZERO } else { m.d(u) },
            (Piece::Line(l), Some(leg)) => { let ub = leg.bound_after(l.id, l.price); if ended { ub } else { l.s.max(ub) } }
            (Piece::Seg(g), _) => if ended { g.bound } else { g.d(u).max(g.bound) },
            _ => Fx::ZERO,
        }
    }

    /// the exact states near the current piece
    pub fn marks(&self) -> Marks<'l, 'a> { [self.starts.get(self.which).copied().flatten(), self.starts.get(self.which ^ 1).copied().flatten()] }
    /// the furthest exact state and the start of the current piece
    pub fn front(&self) -> Marks<'l, 'a> { [self.cur, self.starts.get(self.which).copied().flatten()] }
}

/// A local optimum of the model
#[derive(Clone, Copy, Debug)]
pub struct Optimum<'l, 'a> {
    pub x: Fx,
    /// model profit out1(out0(x)) − x, in quote units
    pub profit: i128,
    /// the optimum sits on the domain end (cap, capacity, walk budget) rather than where the marginal crosses 1
    pub at_cap: bool,
    /// exact states near x on leg 0 and near out0(x) on leg 1
    pub marks: [Marks<'l, 'a>; 2],
}

#[derive(Clone, Copy, Debug)]
pub struct Located<'l, 'a> {
    pub optima: [Option<Optimum<'l, 'a>>; MAX_OPTIMA],
    pub steps: u16,
    pub bins: u16,
    /// the furthest exact states of each leg
    pub front: [Marks<'l, 'a>; 2],
}

impl Default for Located<'_, '_> {
    fn default() -> Self { Located { optima: [None; MAX_OPTIMA], steps: 0, bins: 0, front: [[None; 2]; 2] } }
}

impl<'l, 'a> Located<'l, 'a> {
    fn push(&mut self, o: Optimum<'l, 'a>) {
        if let Some(slot) = self.optima.iter_mut().find(|s| s.is_none()) { *slot = Some(o); }
    }
    pub fn count(&self) -> usize { self.optima.iter().filter(|o| o.is_some()).count() }
    /// the optima, best model profit first
    pub fn sorted(&self) -> [Option<Optimum<'l, 'a>>; MAX_OPTIMA] {
        let mut v = self.optima;
        v.sort_unstable_by(|a, b| match (a, b) {
            (Some(a), Some(b)) => b.profit.cmp(&a.profit),
            (Some(_), None) => core::cmp::Ordering::Less,
            (None, Some(_)) => core::cmp::Ordering::Greater,
            _ => core::cmp::Ordering::Equal,
        });
        v
    }
    /// The furthest exact state of leg `side` (0 buy, 1 sell) that an input `x` reaches: every state recorded on a
    /// leg lies on the same walk, so the one with the largest `reach ≤ x` is the closest start for an exact quote.
    pub fn cursor(&self, side: usize, x: u64) -> Option<Cursor<'l, 'a>> {
        let mut best: Option<Cursor<'l, 'a>> = None;
        let mut consider = |c: &Option<Cursor<'l, 'a>>| {
            if let Some(c) = c { if c.reach <= x && best.map_or(true, |b| c.reach > b.reach) { best = Some(*c); } }
        };
        for m in self.front.get(side).into_iter().flatten() { consider(m); }
        for o in self.optima.iter().flatten() { for m in o.marks.get(side).into_iter().flatten() { consider(m); } }
        best
    }
}

fn profit(z: Fx, x: Fx) -> i128 { z.floor_u128().min(i128::MAX as u128) as i128 - x.floor_u128().min(i128::MAX as u128) as i128 }

#[inline(never)]
/// x* of the composed Möbius curve (A = a0·a1, B = b0·b1, C = c0·b1 + c1·a0), None when A ≤ B (no profit at 0)
pub fn mobius_root(m0: &Mob, m1: &Mob) -> Option<Fx> {
    let a = m0.a.mul(m1.a);
    let b = m0.b.mul(m1.b);
    let c = m0.c.mul(m1.b).add(m1.c.mul(m0.a));
    if a <= b { return None; }
    Some(a.mul(b).sqrt().sub(b).div(c))
}

/// A piece re-centred at a point of its domain, for the CLMM roots: a Möbius `a·ξ/(b + c·ξ)` of the distance ξ from that
/// point (re-centring a Möbius through its origin at `s` gives `a' = a·b/(b + c·s)`, `b' = b + c·s`, `c' = c`), or a line
/// of slope `s`
#[derive(Clone, Copy, Debug)]
enum Shape { Mob { a: Fx, b: Fx, c: Fx }, Lin { s: Fx } }

fn recentre(p: &Piece, at: Fx) -> Option<Shape> {
    let mob = |a: Fx, b: Fx, c: Fx, s: Fx| { let b2 = b.add(c.mul(s)); Shape::Mob { a: a.mul(b).div(b2), b: b2, c } };
    Some(match p {
        Piece::Mob(m) => mob(m.a, m.b, m.c, at),
        Piece::Line(l) => Shape::Lin { s: l.s },
        Piece::Seg(g) if g.m.c.is_zero() => Shape::Lin { s: g.m.a.div(g.m.b) },
        Piece::Seg(g) => mob(g.m.a, g.m.b, g.m.c, at.sub(g.u0)),
        Piece::End => return None,
    })
}

/// The interior root of π' = 1 when a CLMM step is one of the pieces: both pieces re-centred at the interval's start
/// (leg 0 at `lo`, leg 1 at `out0(lo)`), the table's formulas from there (DESIGN.md §3.4). Some(None): no root after
/// `lo`; None: no interior root at all (line × line, π' constant)
fn root_general(p0: &Piece, p1: &Piece, lo: Fx) -> Option<Option<Fx>> {
    let (s0, s1) = (recentre(p0, lo)?, recentre(p1, p0.f(lo))?);
    Some(match (s0, s1) {
        (Shape::Mob { a: a0, b: b0, c: c0 }, Shape::Mob { a: a1, b: b1, c: c1 }) => {
            let (a, b, c) = (a0.mul(a1), b0.mul(b1), c0.mul(b1).add(c1.mul(a0)));
            let t = a.mul(b).sqrt();
            if t <= b || c.is_zero() { None } else { Some(lo.add(t.sub(b).div(c))) }
        }
        (Shape::Lin { s }, Shape::Mob { a, b, c }) => {
            // (b + c·y')² = s·a·b at leg 1's distance y' from out0(lo); x = lo + y'/s
            let t = s.mul(a).mul(b).sqrt();
            if t <= b || c.is_zero() || s.is_zero() { None } else { Some(lo.add(t.sub(b).div(c).div(s))) }
        }
        (Shape::Mob { a, b, c }, Shape::Lin { s }) => {
            let t = s.mul(a).mul(b).sqrt();
            if t <= b || c.is_zero() { None } else { Some(lo.add(t.sub(b).div(c))) }
        }
        (Shape::Lin { .. }, Shape::Lin { .. }) => return None,
    })
}

#[inline(never)]
/// The interior root of π' = 1 on (lo, hi) for the current pieces (DESIGN.md §3.4 table); `Some(lo)` when rounding
/// puts it at or before `lo`
fn root(p0: &Piece, p1: &Piece, lo: Fx, hi: Fx) -> Option<Fx> {
    if matches!(p0, Piece::Seg(_)) || matches!(p1, Piece::Seg(_)) {
        let Some(r) = root_general(p0, p1, lo)? else { return Some(lo) };
        return if r <= lo { Some(lo) } else if r < hi { Some(r) } else { None };
    }
    let r = match (p0, p1) {
        (Piece::Mob(m0), Piece::Mob(m1)) => mobius_root(m0, m1)?,
        (Piece::Line(l), Piece::Mob(m)) => {
            let t = l.s.mul(m.a).mul(m.b).sqrt();
            if t <= m.b { return Some(lo); }
            let y = t.sub(m.b).div(m.c);
            if y <= l.v0 { return Some(lo); }
            l.u0.add(y.sub(l.v0).div(l.s))
        }
        (Piece::Mob(m), Piece::Line(l)) => {
            let t = l.s.mul(m.a).mul(m.b).sqrt();
            if t <= m.b { return Some(lo); }
            t.sub(m.b).div(m.c)
        }
        _ => return None,
    };
    if r <= lo { Some(lo) } else if r < hi { Some(r) } else { None }
}

/// Locate the model's local optima of π(x) = out1(out0(x)) − x on [0, x_cap].
#[inline(never)]
pub fn locate<'l, 'a>(m0: &LegModel<'l, 'a>, m1: &LegModel<'l, 'a>, x_cap: Fx) -> Located<'l, 'a> {
    let mut res = Located::default();
    let (mut s0, mut s1) = (Stream::new(m0), Stream::new(m1));
    let (mut p0, mut p1) = (s0.next(), s1.next());
    // Möbius × Möbius: the closed form
    if let (Piece::Mob(a), Piece::Mob(b)) = (p0, p1) {
        let x_max = x_cap.min(a.cap).min(a.inv(b.cap));
        let z = |x: Fx| b.f(a.f(x));
        let none = [[None; 2]; 2];
        match mobius_root(&a, &b) {
            None => res.push(Optimum { x: Fx::ZERO, profit: 0, at_cap: false, marks: none }),
            Some(r) if r >= x_max => res.push(Optimum { x: x_max, profit: profit(z(x_max), x_max), at_cap: true, marks: none }),
            Some(r) => res.push(Optimum { x: r, profit: profit(z(r), r), at_cap: false, marks: none }),
        }
        return res;
    }
    // x and the leg-0 output y = out0(x) in the model; out1(y) is evaluated only where an optimum is recorded. When
    // leg 1 has ended, its value at y is its last piece's end.
    let (mut x, mut y) = (Fx::ZERO, Fx::ZERO);
    let mut z_end = Fx::ZERO;
    let z_at = |p1: &Piece, z_end: Fx, y: Fx| if matches!(p1, Piece::End) { z_end } else { p1.f(y) };
    // the legs' marginals at (x, y) on the current pieces, carried from the previous step's interval end
    let (mut d0, mut d1) = (p0.d(x), p1.d(y));
    // before 0 the profit counts as rising, so a falling start records 0
    let mut rising = true;
    for step in 0..MAX_STEPS {
        res.steps = step as u16 + 1;
        if matches!(p0, Piece::End) || matches!(p1, Piece::End) || x >= x_cap {
            if rising { res.push(Optimum { x, profit: profit(z_at(&p1, z_end, y), x), at_cap: true, marks: [s0.marks(), s1.marks()] }); }
            rising = false;
            break;
        }
        let e0 = p0.end();
        let e1y = p1.end();
        let e1 = if e1y.is_inf() { Fx::INF } else { p0.inv(e1y) };
        let x_next = e0.min(e1).min(x_cap);
        let (adv0, adv1) = (x_next >= e0, x_next >= e1);
        let y_next = if adv1 && !adv0 { e1y } else if adv0 { p0.f_end() } else { p0.f(x_next) };
        // π' on this interval falls from d0·d1 at x to d0e·d1e at its end (each piece is concave): the interior root
        // is computed only when π' crosses 1 inside
        let (d0e, d1e) = (p0.d(x_next), p1.d(y_next));
        if d0.mul(d1) > Fx::ONE {
            if d0e.mul(d1e) > Fx::ONE {
                rising = true;
            } else if let Some(r) = root(&p0, &p1, x, x_next) {
                res.push(Optimum { x: r, profit: profit(p1.f(p0.f(r)), r), at_cap: false, marks: [s0.marks(), s1.marks()] });
                rising = false;
            } else {
                rising = true;
            }
        } else {
            if rising { res.push(Optimum { x, profit: profit(p1.f(y), x), at_cap: false, marks: [s0.marks(), s1.marks()] }); }
            rising = false;
        }
        if res.count() >= MAX_OPTIMA { break; }
        // non-concavity guard, on EVERY step once an optimum is known and the profit is not rising (REVIEW.md F6):
        // continue only while some later marginal can still exceed 1. The bound only falls along the walk, so the
        // first step where it is ≤ 1 ends every later rise.
        if res.count() > 0 && !rising {
            let b = s0.bound_after(&p0, x_next, adv0).mul(s1.bound_after(&p1, y_next, adv1));
            if b <= Fx::ONE { break; }
        }
        x = x_next;
        y = y_next;
        if adv0 { p0 = s0.next(); d0 = p0.d(x); } else { d0 = d0e; }
        if adv1 {
            z_end = p1.f_end();
            p1 = s1.next();
            d1 = p1.d(y);
        } else { d1 = d1e; }
    }
    res.bins = s0.bins.saturating_add(s1.bins);
    // the walk ran out while still rising: the last point reached is the best the model knows
    if rising && res.count() == 0 { res.push(Optimum { x: x.min(x_cap), profit: profit(z_at(&p1, z_end, y), x), at_cap: true, marks: [s0.marks(), s1.marks()] }); }
    res.front = [s0.front(), s1.front()];
    res
}

/// φ⁻¹ = 0.6180339887 as a 32-bit fraction
const PHI_INV_Q32: u128 = 2_654_435_769;

/// Golden-section search for the maximum of an exact evaluator on the integers of [lo, hi] (DESIGN.md §3.6).
/// `None` evaluations count as −∞. Stops after `max_iters` iterations or when the bracket is ≤ max(1, w0 >> 12).
/// Returns the best point evaluated (at most `max_iters + 2` evaluations).
pub fn golden(lo: u64, hi: u64, max_iters: u8, eval: &mut dyn FnMut(u64) -> Option<i128>) -> Option<(u64, i128)> {
    if lo > hi { return None; }
    let g = |a: u64, b: u64| ((b - a) as u128 * PHI_INV_Q32 >> 32) as u64;
    let tol = ((hi - lo) >> 12).max(1);
    let (mut a, mut b) = (lo, hi);
    let mut c = b - g(a, b);
    let mut d = a + g(a, b);
    let mut fc = eval(c);
    let mut fd = eval(d);
    let mut best: Option<(u64, i128)> = None;
    let keep = |x: u64, v: Option<i128>, best: &mut Option<(u64, i128)>| {
        if let Some(v) = v { if best.map_or(true, |(bx, bv)| v > bv || (v == bv && x < bx)) { *best = Some((x, v)); } }
    };
    keep(c, fc, &mut best);
    keep(d, fd, &mut best);
    let ge = |p: Option<i128>, q: Option<i128>| match (p, q) { (Some(p), Some(q)) => p >= q, (Some(_), None) => true, (None, Some(_)) => false, (None, None) => true };
    for _ in 0..max_iters {
        if b - a <= tol { break; }
        if ge(fc, fd) {
            b = d;
            d = c;
            fd = fc;
            c = b - g(a, b);
            fc = eval(c);
            keep(c, fc, &mut best);
        } else {
            a = c;
            c = d;
            fc = fd;
            d = a + g(a, b);
            fd = eval(d);
            keep(d, fd, &mut best);
        }
    }
    best
}
