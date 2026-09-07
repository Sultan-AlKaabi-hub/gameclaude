# FOURSIGHT

Connect Four against a minimax engine with alpha-beta pruning — one that shows
you its work: the value it assigned to every column, the line it expects you to
play, how deep it searched, and how much of the game tree pruning let it skip.

## Running it

```bash
pip install -r requirements.txt
streamlit run app.py
```

No API keys, no database. The leaderboard falls back to local storage.

## Deploying

Push to a public GitHub repo, then at `share.streamlit.io` create an app
pointing at `app.py`. For a permanent shared leaderboard, create a public Gist
containing `leaderboard.json` with `{"version": 1, "entries": []}`, then add
`GIST_ID` and `GITHUB_TOKEN` under the app's Settings → Secrets. Optional
`GEMINI_API_KEY` adds generated post-game commentary; without it the game uses
written fallbacks.

## The AI

**Negamax with alpha-beta pruning**, the canonical adversarial search
algorithm. It assumes optimal play from both sides and discards subtrees that
cannot affect the result.

| Technique | Why it is there | File |
|---|---|---|
| Bitboards | Two 49-bit integers per position; move and win tests are a few integer ops | `engine/board.py` |
| Alpha-beta pruning | Cuts branches that cannot change the outcome | `ai/search.py` |
| Move ordering | Centre-first; more winning lines pass through the centre, so cutoffs come early | `engine/board.py` |
| Transposition table | The same position arises from many move orders | `ai/search.py` |
| Iterative deepening | Shallow passes order moves for deep ones; allows a time budget | `ai/search.py` |
| Heuristic evaluation | Scores non-terminal positions at the search horizon | `ai/search.py` |

### Measured pruning

From `tests_headless.py`, on an opening position:

| Depth | Positions examined | Brute-force upper bound (7^d) |
|---|---|---|
| 4 | 396 | 2,401 |
| 6 | 1,971 | 117,649 |
| 8 | 11,610 | 5,764,801 |

At depth 8 the engine looks at roughly **0.2%** of the nodes a naive minimax
would. That gap is alpha-beta plus move ordering, and it is the whole reason
the engine can think eight plies ahead in pure Python inside 130ms.

### Strength

`BRUTAL` (depth 8) beat `CASUAL` (depth 2) in 14 of 14 games with alternating
first move.

## Scoring

A **run** is a streak of games that ends on your first loss. Each board pays
out on difficulty, moves to spare, and current streak. The sides alternate who
moves first, so neither player keeps the first-move advantage.

## Architecture

```
app.py                Streamlit UI, screen routing, session state
engine/board.py       Bitboard position, legality, win detection
engine/match.py       Match and run state, scoring
ai/search.py          Negamax, alpha-beta, transposition table
services/leaderboard.py  Storage interface + Gist and local backends
services/narrator.py  Optional Gemini commentary with fallbacks
ui/theme.py           Design tokens and CSS
ui/render.py          Board SVG and reasoning panel
tests_headless.py     Engine validation
```

Nothing in `engine/` or `ai/` imports Streamlit, so the rules are testable
headlessly.

## Testing

```bash
python tests_headless.py
```

Ten groups: bitboard win detection in all four orientations, sentinel-row
protection against false wins wrapping between columns, gravity and legality,
mate-in-one detection, forced-block detection, pruning effectiveness, a
strength duel between difficulties, match and run bookkeeping, scoring
monotonicity, and move latency.
