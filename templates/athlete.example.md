# Athlete

Example file — the real `athlete.md` is gitignored. This file is Claude's working
memory of the athlete: keep it current, and keep it honest.

- Age band, weight.
- Running background, marathon PB (and how it was set).
- Fixed weekly commitments — club runs, gym sessions, family constraints.
- Recent volume by month, notable recent efforts.

## Zones

**Pace (min/km):** Z1 recovery > a:bc · Z2 easy … · Z3 steady/MP … · Z4 threshold … · Z5 VO2 … · Z6 < x:yz

**HR (bpm):** Z1 ≤ … · Z2 … · Z3 … · Z4 … · Z5 ≥ …

**Key paces:** current MP · target MP · threshold — note the source (race, best effort) and recalibrate at tune-up races

**Current calibration.** When a session shows the paces are stale (e.g. threshold pace hit at sub-threshold HR), record the working band here with the evidence date and "provisional until confirmed" — durable calibration lives here, the blow-by-blow stays in the week review.

**Calibration history.** A small table — Date · What · Value · Evidence · Status — tracking each pace change over the block, so a provisional band isn't forgotten and the fitness trend stays visible.

## Preferences

Captured at setup (the `setup` command interviews for these); the check-in reads them before
drafting a week, so the workouts it writes match how this athlete actually trains. Defaults in
[brackets].

**Units & device** — distance/pace in km (min/km) or miles (min/mile) [km]; watch model.

**Prescription**
- Primary target on hard efforts: pace · HR · power · effort/RPE only [pace, HR as context].
- Reps/blocks measured by: time (6×2min) · distance (6×400m) · mixed [time short, distance long].

**What the watch shows**
- Targets on **every step** — easy runs also show a pace/HR band [default] — or **hard efforts
  only** (easy runs carry a bare duration, pace guidance in the prose), set with
  `ROBO_COACH_TARGETS=hard-only` in `.env`.
- Easy-run guidance: pace band · HR ceiling · RPE/"conversational" [RPE + prose].

**Check-in** — lead with effort/RPE before the data [effort-first] or data-first · depth: brief
· full [brief] · day + time [Sunday ~17:00].

**Structure** — runs/week, peak volume, rest day, long-run day, quality day(s); fixed
commitments (club runs, gym); strength in the plan (which days) or self-managed.

## Flags / watchlist

Only currently-open items live here; resolved observations stay in the week reviews (`weeks/*.md`).

- (open niggles, illness, life stress, patterns being watched — each with what the next reading needs to close it)
