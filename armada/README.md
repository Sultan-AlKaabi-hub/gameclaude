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
engine/match.py          Turn order, game state, scoring
ai/density.py            Probability density targeting
services/leaderboard.py  Storage interface + Gist and local backends
services/narrator.py     Optional Gemini commentary with fallbacks
ui/theme.py              Design tokens and CSS
ui/render.py             Board SVG and heat map overlay
tests_headless.py        Validation
```

Nothing in `engine/` or `ai/` imports Streamlit.

## Testing

```bash
python tests_headless.py
```

Nine groups: fleet placement legality over 200 seeds, shot resolution and sink
detection, density model responses to misses and hits, parity behaviour in hunt
versus target, no duplicate fire, the strength ordering above, match completion
and scoring, the fairness assertions, and per-move latency (about 1 ms).

## Known limitations

- Ship placement is randomised with a reposition button rather than manual
  drag-and-drop placement.
- Single player against the AI. Two-player over a shared room code is possible
  on one Streamlit server but is not implemented here.
