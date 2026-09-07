# BLACKOUT

A turn-based stealth game where the opponent is a real inference engine.

You are an infiltrator on a dark station. **The hunters cannot see you.** They
share a single probabilistic belief about where you might be, built from noisy
sensor readings and refined every turn with Bayes' rule. That belief is drawn
on screen as a density map, and the whole game is the duel between your
movement and their estimate.

Your stealth score is literally the **Shannon entropy of the AI's uncertainty
about you**. You are graded on how wrong you kept it, not merely on surviving.

---

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

That is the whole setup. No API keys, no database, no configuration. The game
is fully playable out of the box and the leaderboard falls back to local
storage automatically.

---

## Deploying to Streamlit Community Cloud

1. Push this folder to a **public** GitHub repository.
2. At `share.streamlit.io`, create a new app pointing at your repo, with
   `app.py` as the main file.
3. Deploy. It will work immediately with a local leaderboard.

### Making the leaderboard permanent and shared

Streamlit Community Cloud containers have an **ephemeral filesystem** — files
written to local disk are lost on every restart and redeploy. A leaderboard
kept in a local file therefore works perfectly in development and silently
loses everything in production. To make scores durable and shared between
players, the app can keep the table in a public GitHub Gist.

1. Create a **public gist** at `gist.github.com` with one file named exactly
   `leaderboard.json`, containing:
   ```json
   {"version": 1, "entries": []}
   ```
   Copy the long hex ID from the resulting URL.
2. Create a **fine-grained personal access token**: GitHub → Settings →
   Developer settings → Fine-grained tokens. Under *Account permissions*, set
   **Gists** to *Read and write*. Leave everything else at no access.
3. In your Streamlit app's **Settings → Secrets**, paste:
   ```toml
   GIST_ID = "your_gist_id"
   GITHUB_TOKEN = "github_pat_..."
   ```

No code changes. The app detects the credentials and switches backends.

### Optional AI narration

Add a Google AI Studio key for generated mission briefings and after-action
tactical critiques:

```toml
GEMINI_API_KEY = "AIza..."
```

Google's free tier is Flash-only and rate-limited to a small number of
requests per minute. The app calls it **twice per run** and never inside the
turn loop, so it sits comfortably inside the quota. If the key is missing,
the quota is exhausted, or the request times out, the game falls back to
written templates. There is no code path where a third-party outage can block
a turn.

> **Never commit `.streamlit/secrets.toml`.** It is already in `.gitignore`.
> Add that ignore rule *before* your first commit — git will not ignore a file
> it is already tracking, so committing a token once puts it in your history
> permanently.

---

## The AI, and where to see it

Six techniques, all of them observable while you play:

| Technique | Where it shows up | File |
|---|---|---|
| **Particle filter** (sequential Monte Carlo) | The density map itself | `ai/particle_filter.py` |
| **A\*** with a consistent heuristic | Hunter routes ("show hunter intent") | `ai/pathfinding.py` |
| **Sequential single-item auction** | Hunters fan out instead of queueing | `ai/auction.py` |
| **Shannon entropy** | The certainty meter and your stealth score | `ai/particle_filter.py` |
| **Bayesian occupancy reasoning** | Holes carved in the cloud around hunters | `ai/particle_filter.py` |
| **LLM narration** (optional) | Briefings and after-action analysis | `services/narrator.py` |

Details worth knowing:

- **Silence is evidence.** A hunter that detects nothing rules out the cells it
  was covering, which is why the belief develops holes around each hunter even
  when they have found nothing. Absence of detection is not absence of
  information.
- **An EMP is different from a quiet sensor.** A blinded sensor produces *no*
  observation, so the filter only diffuses and uncertainty grows. If an EMP
  merely produced "detected nothing" readings it would *help* the hunters.
- **Sightings do not collapse the belief to a point.** A perfectly certain
  observation would pin the posterior to a single cell that re-confirms itself
  every turn, and contact could never be broken. Close contact is modelled as a
  very tight Gaussian instead, which preserves the Bayesian structure and keeps
  escape possible.
- **Scanning hunters (drawn with a ring) hold position** but take a sharper
  reading. Coverage versus precision is a genuine tradeoff for the AI, and that
  pause is your tempo advantage.

---

## Architecture

```
app.py                  Streamlit entry point, screen routing, session state
engine/
  grid.py               Arena generation, connectivity, line of sight
  state.py              Game state and turn resolution
  scoring.py            Difficulty curve and score model
ai/
  particle_filter.py    Recursive Bayesian estimation of your position
  pathfinding.py        A* search
  auction.py            Multi-agent task allocation
  hunter.py             Sensor model and movement policy
services/
  leaderboard.py        Storage interface + Gist and local backends
  narrator.py           Optional Gemini narration with template fallback
ui/
  theme.py              Design tokens and CSS
  render.py             SVG arena renderer
tests_headless.py       Engine and AI validation
balance_probe.py        Automated difficulty measurement
```

Nothing in `engine/` or `ai/` imports Streamlit. The rules are testable
headlessly and independent of the presentation layer, which is what made the
balance work below possible.

---

## Testing

```bash
python tests_headless.py    # correctness
python balance_probe.py     # difficulty measurement
```

`tests_headless.py` checks map connectivity across seeds, A* path optimality
and contiguity, filter convergence on a stationary target, belief decay under
EMP, hunter dispersion, determinism under a fixed seed, and the per-turn
compute budget.

## Balance

Difficulty was measured, not guessed. `balance_probe.py` plays complete runs
with a scripted agent that plans one turn ahead against where hunters can move
next. Over 50 runs per tier:

| Tier | Clears wave 1 | Reaches wave 3+ | Score multiplier |
|---|---|---|---|
| RECRUIT | 88% | 44% | ×0.75 |
| OPERATIVE | 72% | 28% | ×1.00 |
| GHOST | 54% | 2% | ×1.60 |

An earlier greedy agent with no lookahead cleared wave 1 only ~46% of the
time on the same build. The gap between the two agents is the skill the game
actually rewards: reading hunter positions a turn ahead rather than reacting.

## Performance

Roughly **1.3 ms of compute per turn** on a 19×19 arena with 500 particles and
up to 6 hunters, well inside the 150 ms budget. The dominant cost is the
line-of-sight masks, computed once per hunter per turn over free cells rather
than once per particle, and cached by position.

## Fairness

Runs are deterministic from `seed` plus the action log, so a score can be
replayed and verified. The **daily challenge** derives its seed from the UTC
date, putting every player on an identical arena.

Scores are computed server-side in Python. The browser only renders; it never
holds the score, which is a meaningful advantage over a JavaScript arcade game
where the client can be edited freely.

## Known limitations

- Gist updates are read-modify-write with no compare-and-swap. Two players
  submitting in the same instant can clobber one another. Writes re-read and
  merge before each retry, which shrinks but does not close the window. At
  classroom scale this is acceptable; at real concurrency, move to Postgres.
  `services/leaderboard.py` is written against an interface precisely so this
  is a small change.
- There is no server-side replay verification, so a determined player who can
  run the code locally could construct a score. Verification is possible given
  the determinism guarantee, but is not implemented.
