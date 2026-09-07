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

No API keys, no database required. The game itself is a single self-contained
page, `web/index.html`, which also works opened directly in a browser or hosted
as a static file. `app.py` is a thin Streamlit shell that serves it edge to
edge, so the deployment path is unchanged.

## Deploying

Push to a public GitHub repo, then at `share.streamlit.io` create an app
pointing at `app.py`. Nothing else to configure.

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

Everything after the menu runs in the browser. Every tap is resolved locally
and the AI's reply lands about a second later with its own animation, so the
game feels like a game rather than a form. An earlier version built each
board from 100 Streamlit buttons, which meant a server round trip per tap and
a grid that collapsed into a vertical list on phones.

**Graphics.** Ships are drawn as steel hulls that span their cells, with a bow,
a stern and turrets on the middle sections. The ocean is a shaded tile, the
frame is brushed steel, the type is a military stencil. Every shot gets an
effect: a cannon report and a white splash ring for a miss, a flash, fireball
and smoke burst for a hit, and a red peg that keeps burning on the hull. A
sunk ship turns into a charred wreck and settles. Your own board shakes when
you are hit, and phones vibrate.

**Sound** is synthesised on the fly with WebAudio, so there are no files to
load: cannon, splash, explosion, sinking, incoming-shell whistle, fanfare and
defeat. The speaker button in the top bar or the checkbox on the menu turns it
off.

**Desktop** shows both boards side by side. **Phones** show one board at a
time, switched with two tabs; a badge and a toast tell you when the enemy hits
you while you are looking at the other board.

## Ship placement

Both modes open on a deployment screen. The fleet arrives placed at random, so
a player who does not care can just confirm. Anyone who does can clear it and
place every ship by hand. Legal squares are lit green, illegal ones are dead,
hovering previews the hull on desktop, and **Rotate** (or the <kbd>R</kbd>
key) flips the orientation. Undo, Random and Clear are available until you
confirm.

## Two-player modes

**Online rooms.** One player creates a room and gets a four-character code; the
other joins by entering it, or by opening the app's link with `?game=CODE`
appended. Both fleets live on the Streamlit server and each browser is only
ever sent its own board plus what it has discovered, so ship positions never
reach a browser that should not have them. The seat token is written to the
URL, so a refresh or a dropped phone connection reclaims the same seat. While
you are in a room the page is refreshed every two seconds so you see the
opponent's move without touching anything.

**Two players, one device.** Each commander deploys in private behind a
hand-over screen, then the device is passed back and forth after every shot.

## How the page talks to the server

`web/index.html` is registered as a bidirectional Streamlit component. The
server hands it a `state` dict on every render (room status, your board, what
you have discovered, the leaderboard) and the page reports actions back as its
value: create, join, ready, fire, leave, finish. Each action carries a nonce,
because a component's value persists across reruns and would otherwise be
replayed. The AI game never touches the server at all; only the final score is
sent, which is how the shared leaderboard and the optional Gemini commentary
are still produced by the Python side.

## Architecture

```
app.py                   Streamlit host: serves the page as a component, owns
                         rooms, the shared leaderboard and commentary
web/index.html           The game: engine, density AI, graphics, sound,
                         placement, hot-seat and online play
engine/fleet.py          Ships, placement, shot resolution
engine/duel.py           Two-player room state (server side)
engine/match.py          Python reference match state and scoring
ai/density.py            Python reference probability-density AI
services/rooms.py        Shared cross-session room store
services/leaderboard.py  Storage interface + Gist and local backends
services/narrator.py     Optional Gemini commentary with fallbacks
legacy_app.py            Previous widget-based UI, kept for reference
tests_web.mjs            Validation of the browser engine
tests_headless.py        Validation of the Python engine
```

The browser engine is a line-for-line port of the Python one, and both test
suites run the same eleven groups of checks.

## Testing

```bash
node tests_web.mjs
python tests_headless.py
```

Eleven groups each: fleet placement legality over 200 seeds, shot resolution
and sink detection, density model responses to misses and hits, parity
behaviour in hunt versus target, no duplicate fire, the strength ordering
above, match completion and scoring, the fairness assertions, per-move latency
(well under a millisecond in the browser), two-player turn ownership and win
handling, and manual placement legality.

## Known limitations

- Rooms are held in memory, so a redeploy or the free tier sleeping ends any
  online game in progress. The AI game and hot-seat mode are unaffected.
- Online play assumes a single server process, which is what Community Cloud
  provides today.
- Placement is tap-to-place rather than drag-and-drop.
