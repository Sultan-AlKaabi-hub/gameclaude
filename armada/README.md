# ARMADA

Battleship against an opponent that never sees your ships — and shows you
exactly how it reasons about where they are.

Each turn the AI enumerates every legal placement of every ship you still have
afloat, discards the ones contradicted by its own shots, and counts how many
survivors cover each square. It fires at the maximum. That count is rendered as
a heat map on your board, so you watch its belief about your fleet form, narrow,
and collapse onto a hull the moment it lands a hit.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

No API keys, no database required.

## Deploying

Push to a public GitHub repo, then at `share.streamlit.io` create an app
pointing at `app.py`. For a permanent shared leaderboard, create a public Gist
containing `leaderboard.json` with `{"version": 1, "entries": []}`, then add
`GIST_ID` and `GITHUB_TOKEN` under Settings → Secrets. An optional
`GEMINI_API_KEY` adds generated post-game commentary; without it the game falls
back to written analysis.

## The AI

Given only its own shot grid and the lengths of ships still afloat:

1. **Enumerate** every legal placement of every surviving ship, both orientations.
2. **Eliminate** any placement covering a known miss or overlapping an
   already-sunk hull.
3. **Count** how many survivors cover each unknown square, and fire at the peak.

Under a uniform prior over consistent fleet layouts, that count *is* the
posterior probability that a square holds a ship. The heat map is the posterior.

**Hunting and targeting are one mechanism, not two.** Placements explaining an
unresolved hit carry a weight of 60, so the instant you take damage the
distribution collapses along the two axes through that square and the AI walks
the hull. No separate targeting mode exists in the code.

**Parity.** A ship of length L must touch every L-spaced lattice, so while your
smallest survivor is a 2-cell Destroyer there is no reason to fire off the
checkerboard — it halves the search space at zero information cost. It is
disabled the moment a hit goes unresolved, because then every square matters.

### Measured strength

Average shots to clear a full fleet, 40 randomised layouts each. A perfect game
is 17; a strong human plays around 45–55.

| Difficulty | Method | Avg shots |
|---|---|---|
| CADET | Uniform random fire | 96.7 |
| OFFICER | Random hunt, adjacent targeting | 64.3 |
| **ADMIRAL** | **Full probability density + parity** | **43.5** |

### Fairness

`ai/density.py` never imports `Fleet` and never touches `owner_grid`. Its
entry point takes exactly two arguments: a shot grid and a list of ship lengths.
`tests_headless.py` asserts both of these by inspecting the source and the
function signature, so the guarantee cannot silently rot.

## Interface

The board is built from real Streamlit buttons, one per square, so **the board
itself is the control surface** — you click the square you are looking at. An
earlier version drew the board as a picture with a separate grid of buttons
underneath it, which meant looking at one thing and clicking another.

Cell colour comes from the widget key. Streamlit attaches a `.st-key-<key>`
class to any keyed widget, so encoding a square's state into its key
(`cellhit_3_4`, `cellsea_0_0`) lets one CSS rule paint every cell of that state
at once. See `[class*="st-key-cellhit_"]` in `ui/theme.py`.

Your own board is display-only and is drawn as a CSS grid of divs instead: 100
divs cost far less than 100 widgets, and they can carry the AI's heat map
underneath the hulls.

### Palette

The first palette failed for a diagnosable reason: hulls were dark teal on dark
navy, about one tonal step apart, so the board read as one muddy field. The
current scheme separates every layer by value, and inverts the hulls to be
*lighter* than the water — a ship is a bright object on a dark sea, as in life.
Light-on-dark is also easier to sustain over a long session than a
near-isoluminant scheme.

## Ship placement

Both modes open on a deployment screen. The fleet arrives placed at random, so
a player who does not care can just confirm. Anyone who does can clear it and
place every ship by hand, choosing orientation with **Rotate**.

Illegal squares are **disabled rather than rejected after the click**, so the
board answers "can this go here?" before you commit. Undo, Random and Clear are
all available until you confirm.

In two-player mode the room enters a deployment phase once both commanders have
joined; the battle opens when both have confirmed their fleets.

## Mobile

Two targeting modes, switchable from the menu:

- **Tap the grid** — a 10x10 button grid. Best on desktop.
- **Coordinate picker** — column, row, fire. Three taps, works at any width.

The second exists because Streamlit's columns can collapse into a vertical
stack on narrow viewports, which would turn the grid into an unusable 100-item
list. Rather than guess how a given phone renders it, both are provided.

## Architecture

```
app.py                   Streamlit UI, screens, session state
engine/fleet.py          Ships, placement, shot resolution, shot grids
engine/match.py          Turn order, game state, scoring (vs AI)
engine/duel.py           Two-player game state, seats, turn ownership
services/rooms.py        Shared cross-session room store
ai/density.py            Probability density targeting
services/leaderboard.py  Storage interface + Gist and local backends
services/narrator.py     Optional Gemini commentary with fallbacks
ui/theme.py              Design tokens and CSS
ui/board.py              Clickable board widgets and the heat map grid
tests_headless.py        Validation
```

Nothing in `engine/` or `ai/` imports Streamlit.

## Testing

```bash
python tests_headless.py
```

Eleven groups: fleet placement legality over 200 seeds, shot resolution and sink
detection, density model responses to misses and hits, parity behaviour in hunt
versus target, no duplicate fire, the strength ordering above, match completion
and scoring, the fairness assertions, per-move latency (about 1 ms), and
two-player seat claiming, turn ownership, out-of-turn rejection, win and
forfeit handling, the isolation of each player's shot grid, and manual
placement legality (overlap, overhang, undo, clear, full hand-placed fleet).

## Two-player mode

A separate mode alongside the AI game. One player creates a room and gets a
four-character code; the other joins by entering it, or by opening the app's
link with `?game=CODE` appended.

**How the state is shared.** Streamlit runs every browser session as a thread
inside one server process. `st.cache_resource` returns the same object to every
session rather than a copy, so a single dictionary of rooms is visible to both
players. Every read-modify-write goes through a `threading.Lock`, because those
sessions are genuinely concurrent.

**How a player sees the opponent's move.** The board sits in an
`st.fragment(run_every="2s")`, which reruns on a timer without user input. Only
that fragment redraws, not the whole page. On Streamlit builds without
fragments the app degrades to a manual refresh button rather than breaking.

**Why the seat token is in the URL.** Each player's seat token is written to the
address bar as well as session state. A refresh or a dropped mobile connection
therefore reclaims the same seat instead of locking the player out of their own
game.

**Hidden information.** Both fleets live on the server and each session is only
ever rendered its own board plus what it has discovered. Ship positions are
never sent to a browser that should not have them — which is stronger than a
peer-to-peer design, where the opponent's board has to be transmitted and the
client trusted not to look.

### Limitations of two-player mode

- **Rooms are held in memory.** A redeploy, or the free tier putting the app to
  sleep, ends any game in progress. The UI reports the room as expired and
  returns you to the menu rather than crashing. The AI game is unaffected.
- **It assumes a single server process.** If the app were ever scaled to
  several replicas, two players could land on different ones and never meet.
  Community Cloud does not do this today.
- Rooms are pruned after 20 minutes idle or 2 hours total, capped at 200.
- Anyone with the code can take a free seat, first come. Rooms lock at two.

## Known limitations

- Placement is click-to-place rather than drag-and-drop; Streamlit has no
  drag primitive without a custom component.
