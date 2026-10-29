---
name: home-base
description: Personal home base — the daily brief across every project and commitment, and the way to record anything new. Use when the user says "home base", "/hb", "what's on", "brief me", "what needs me today", "what's going on", or states a new commitment, task, or project out loud in passing (e.g. "I need to order a birthday cake", "the bike's fixed", "the side project's build broke").
---

# Home Base

The ledger lives at `~/code/home-base`. `hb` owns the state; you render it and
interpret what the user says. Never hand-edit entry files — use the commands.

```bash
cd ~/code/home-base && ./bin/hb <command>
```

## Pulling the brief

Run `./bin/hb brief`. It returns JSON and has already applied git auto-touch
and decay — it reflects the current moment, not a stale cache.

```json
{
  "items": [ { "id", "name", "area", "kind", "state", "bucket", "next", "detail" }, ... ],
  "suppressed": { "<bucket>": <count>, ... },
  "flags": [ { "id", "flag" }, ... ],
  "errors": [ "<message>", ... ],
  "silent": true | false
}
```

### Rule zero: silence

**If `silent` is true, say "Nothing needs you today." and stop.** Do not list
the ledger, do not summarize what's tracked, do not pad it with "but here's
what's in flight." Silence is the most common correct output — most days
nothing is overdue, nothing is waiting too long, nothing is idling past its
cadence. A brief that manufactures content to look useful is how this system
dies. If `silent` is false, there is at least one item, flag, or error; render
per the rules below.

### Rendering, in order of importance

1. **Silence wins.** Covered above — check it first, before anything else.
2. **Group `items` by `area`**, in the order the entries happen to come back
   (do not re-sort areas) — area is a grouping key, not a priority signal.
   Within an area, keep the engine's order; it already sorted by urgency
   (`BUCKET_ORDER`: `overdue`, `due_soon`, `upcoming`, `stale_waiting`,
   `idling`, `waking`, `active`).
3. **Never show more than the `items` the engine returned** — it already
   capped at seven. Don't go back to `hb list` to pad the brief out further;
   the cap is deliberate.
4. **If `suppressed` is non-empty**, add one short line summarizing it, e.g.
   `+1 idling, +3 active not shown`. One line, not a breakdown per entry.
5. **`flags` render as warnings** below the grouped items, e.g.
   `⚠ side-project is not under git — uncommitted work has no backup`. There is
   currently one flag kind, `repo_not_git`; render others the same way
   (short, plain-language, not the raw flag string) if new ones appear.
6. **`errors` mean a ledger file is broken** — a corrupt entry, bad TOML, a
   missing required field. Show the message plainly and offer to fix it (read
   the file, don't guess). Errors are not routine; don't bury them at the
   bottom under flags and items — put them where the user will actually see them.
7. **End with one suggestion, not a menu.** If `errors` is non-empty, lead
   the suggestion with fixing that — a broken ledger file is actively lying
   to you and outranks anything `items` could suggest. Otherwise pick
   `items[0]` (the engine already sorted by `BUCKET_ORDER`, so the first item
   is the single highest-urgency thing) and offer to start there. Never list
   three options and ask them to choose — that's the job you're doing for them.
8. **Mark urgency per item**: `⚠` for `overdue`, `due_soon`, and
   `stale_waiting` buckets; `·` for everything else (`upcoming`, `idling`,
   `waking`, `active`). `upcoming` is a soft heads-up (due within 14 days,
   past the `due_soon` window) — worth a `·`, not yet worth alarm.
9. **If `next` is `null`**, say so plainly — `next: (none set)` — rather than
   inventing a next step the engine didn't give you. That gap is itself
   useful signal (it's often why something's been idling for months).

### Example render

Given items in `family` (`upcoming`), `home` (`stale_waiting`, `idling`),
and `software` (`idling`), one flag, no errors, `suppressed: {"idling": 1,
"active": 3}`:

```
Family
  · Birthday party — 9 days
    next: order the cake

Home
  ⚠ Contractor quote — 21 days, waiting on the contractor
    next: chase the quote or drop it
  · Bike tune-up — idle 22 days
    next: replace the chain
  · Garden beds — idle 100 days
    next: (none set)

Software
  · side-project — idle 17 days
    next: pick up where the spec left off

+1 idling, +3 active not shown
⚠ side-project is not under git — uncommitted work has no backup

→ The birthday party is the closest deadline. Start there?
```

The suggestion follows `items[0]` per rule 7 — the engine already sorted by
`BUCKET_ORDER`, and in this run `upcoming` (the birthday party) outranks
`stale_waiting` (the contractor quote). Don't re-rank by eye or by which item
feels most urgent; trust the engine's order, and re-check `BUCKET_ORDER` in
`homebase/brief.py` if it's ever unclear (currently `overdue, due_soon,
upcoming, stale_waiting, idling, waking, active`).

## Recording what the user says

Most of what the user commits to lives in their head, not in any inbox. When they
state something in passing — "I need to order a birthday cake", "the bike's
fixed", "the side project's build broke" — record it without being asked and confirm
in one short line, e.g. "Logged — side-project: build broke."

| What they say | What you run |
|---|---|
| a new ongoing effort | `hb add "<name>" --kind project --area <area>` |
| something with a date | `hb add "<name>" --kind commitment --area <area> --due YYYY-MM-DD` |
| waiting on a person | `hb add "<name>" --kind thread --area <area>` then `hb state <id> waiting` — this stamps `waiting_since` to today automatically, so that's the whole common case. If the user named who, also run `hb set <id> --waiting-on "<name>"`. |
| a seasonal/recurring reminder | `hb add "<name>" --kind recurring --area <area>` then `hb state <id> seasonal` then `hb set <id> --wake <month or YYYY-MM-DD>` — three steps; `hb add` has no `--state` flag, so `seasonal` is always set afterward |
| progress on a thing | `hb touch <id> --next "<the new next step>"` |
| a finished commitment | `hb done <id>` |
| a changed next step | `hb touch <id> --next "<it>"` |
| any other field on an existing entry (`due`, `repo`, `wake`, `waiting_on`, `waiting_since`, `cadence`) | `hb set <id> --<field> "<value>"` |

The entry id is the slug `hb add` prints (lowercased name, non-alphanumerics
to hyphens) — read it back from stdout, don't guess it.

### `hb set` — changing a field after creation

`hb add` only takes fields at creation time (`--kind --area --cadence --due
--repo --next`); `hb touch` only ever changes `next` and `last_touched`;
`hb state` only changes `state` (and, as noted above, auto-stamps
`waiting_since` the first time something becomes `waiting`). Everything
else that needs to change after creation — `--waiting-on`,
`--waiting-since`, `--wake`, `--due`, `--repo`, `--cadence`, `--next` — goes
through `hb set <id> --<flag> <value>`, one or more flags at once. It loads
the entry, applies only the flags given, and saves through the same path
everything else uses — no hand-editing, ever, for any field this skill
asks you to set.

Two cases worth calling out:

- A thread stuck in `waiting` with no `waiting_since` never surfaces as
  `stale_waiting`, no matter how long it waits — `hb state <id> waiting`
  prevents this going forward by auto-stamping it, but if you're ever
  unsure whether an older thread has one, `hb set <id> --waiting-since
  YYYY-MM-DD` fixes it (ask the user since when, don't guess).
- `cadence_days=0` is set at creation with `hb add --cadence 0`, or on an
  existing entry with `hb set <id> --cadence 0` — see "Choosing fields"
  below for when to use it.

**Creating and updating never need permission. Retiring always does.**
`hb retire <id>` moves the entry to the graveyard with `state = dead` — it
never surfaces in a brief again. Only run it when the user actually says kill it,
drop it, forget it, or done with it (not "idling" — idling is normal and
reversible; retiring is not). If you're not sure whether they mean "let it go
idle" versus "kill it", ask.

## Choosing fields

- **area** — `software` `money` `home` `family` `faith` `health`
- **kind** — `project` (ongoing, decays if untouched) · `commitment` (dated,
  happens once, then `done`) · `thread` (someone else holds the ball; the
  staleness clock runs on them) · `recurring` (answers "is it time yet?")
- **cadence_days** (`hb add --cadence N`, default 7) — how often it should
  move before it's flagged idling. 7 for live work, 14–30 for background
  things that move slower but still matter, **0 for anything tracked without
  pressure** — it never decays, never nags, and the *only* way it ever
  surfaces again is by having a `due` date, set with `--due` at `hb add`
  time or later with `hb set <id> --due YYYY-MM-DD`. Setting `next` on a
  cadence-0 entry does *nothing* for visibility — the engine checks cadence
  before it ever looks at `next`. Use 0 for the things the user wants on the
  books but doesn't want asked about — that's the valve that keeps the
  brief short. When unsure which to use, ask; do not guess high (a too-low
  cadence is how the brief turns into noise).
- **next** — one sentence, the concrete next move. Never a list, never a
  subtask tree. If more detail exists elsewhere (a spec, a repo, a doc),
  just say where in conversation rather than trying to store the link —
  `links` has no CLI flag yet, on `hb add` or `hb set`, so there's no
  supported way to record it; don't hand-edit it in.

## Out of scope

There is no `hb work`, no agent dispatch, and no email watching. That is
Stage 2, deliberately deferred until the user has used the brief for a week. If they
ask for either, say so plainly rather than improvising a workaround.
