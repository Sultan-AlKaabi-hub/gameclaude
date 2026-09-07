"""
Sequential Monte Carlo estimation of the infiltrator's position.

This is the heart of BLACKOUT. The hunters never receive the player's true
location. They maintain a set of weighted hypotheses ("particles") over the
free cells of the arena and refine it with Bayes' rule every turn:

    predict   p(x_t | z_{1:t-1}) = sum_x' p(x_t | x') p(x' | z_{1:t-1})
    update    p(x_t | z_{1:t})  proportional to  p(z_t | x_t) p(x_t | z_{1:t-1})

The player never sees a health bar. What they see is this distribution
rendered as a density map, and the game's core tension is watching it
concentrate on them. Degeneracy is handled with systematic resampling on an
effective-sample-size trigger, plus roughening to combat sample impoverishment.

Everything below is vectorised over particles with NumPy; the per-turn cost
is dominated by the line-of-sight masks, which are computed once per hunter
per turn over free cells rather than once per particle.
"""

from __future__ import annotations

import numpy as np

from engine.grid import Grid

# Probability that a hunter's sensor fires when the player is genuinely inside
# its radius with a clear line of sight. Below 1.0, so an absent reading is
# evidence but never proof.
P_DETECT = 0.62

# Floor on likelihood so a single surprising observation cannot annihilate the
# entire particle set and leave nothing to resample from.
LIKELIHOOD_FLOOR = 1e-4


class ParticleFilter:
    """A belief over where the player is, held by the hunter collective."""

    def __init__(self, grid: Grid, n_particles: int, rng: np.random.Generator):
        self.grid = grid
        self.n = n_particles
        self.rng = rng

        self.free_cells = grid.free_cells
        self.n_free = len(self.free_cells)
        self.rows = np.array([c[0] for c in self.free_cells], dtype=np.int32)
        self.cols = np.array([c[1] for c in self.free_cells], dtype=np.int32)

        self._build_successors()

        # Uninformed prior: uniform over every cell the player could occupy.
        self.idx = self.rng.integers(0, self.n_free, size=self.n)
        self.weights = np.full(self.n, 1.0 / self.n)

        self._los_cache: dict[tuple[int, int], np.ndarray] = {}

    # ------------------------------------------------------------ internals

    def _build_successors(self) -> None:
        """Precompute the motion model as an index table.

        Row i lists the free-cell indices reachable in one turn from cell i,
        including staying put. Sampling a successor then costs one integer
        draw instead of a graph walk.
        """
        max_succ = 5  # four neighbours plus wait
        self.succ = np.zeros((self.n_free, max_succ), dtype=np.int32)
        self.succ_count = np.zeros(self.n_free, dtype=np.int32)

        for i, cell in enumerate(self.free_cells):
            options = [cell] + self.grid.neighbors(cell)
            for j, opt in enumerate(options[:max_succ]):
                self.succ[i, j] = self.grid.free_index[opt]
            self.succ_count[i] = min(len(options), max_succ)

    def _los_mask(self, origin: tuple[int, int]) -> np.ndarray:
        """Boolean mask over free cells visible from `origin`.

        Cached per position, because hunters revisit cells and the mask is the
        most expensive part of the update.
        """
        cached = self._los_cache.get(origin)
        if cached is not None:
            return cached
        mask = np.fromiter(
            (self.grid.has_line_of_sight(origin, cell) for cell in self.free_cells),
            dtype=bool,
            count=self.n_free,
        )
        if len(self._los_cache) > 400:
            self._los_cache.clear()
        self._los_cache[origin] = mask
        return mask

    # ------------------------------------------------------------- pipeline

    def predict(self) -> None:
        """Diffuse the belief through the player's motion model.

        With no observations arriving (an EMP, for instance) this runs alone
        and the cloud visibly spreads back out — uncertainty growing over time
        is exactly what a correct Bayes filter should show.
        """
        counts = self.succ_count[self.idx]
        choice = (self.rng.random(self.n) * counts).astype(np.int32)
        self.idx = self.succ[self.idx, choice]

        # A fraction of particles take a second step. The hunters' motion
        # model deliberately over-estimates how far the player may have moved,
        # so uncertainty grows faster than they can close distance. Without
        # this the belief tracks a fleeing player forever and contact can
        # never be broken, which removes stealth from a stealth game.
        extra = self.rng.random(self.n) < 0.35
        if extra.any():
            e_idx = self.idx[extra]
            e_counts = self.succ_count[e_idx]
            e_choice = (self.rng.random(e_idx.size) * e_counts).astype(np.int32)
            self.idx[extra] = self.succ[e_idx, e_choice]

    def update(self, observations: list[dict]) -> None:
        """Reweight particles by the likelihood of the sensor readings.

        Each observation is one of:
          {"kind": "range",   "origin": (r, c), "distance": float,
           "sigma": float, "radius": int}
          {"kind": "absent",  "origin": (r, c), "radius": int}
        """
        if not observations:
            return

        log_like = np.zeros(self.n)

        for obs in observations:
            origin = obs["origin"]
            radius = obs["radius"]
            los = self._los_mask(origin)[self.idx]
            dist = np.abs(self.rows[self.idx] - origin[0]) + np.abs(
                self.cols[self.idx] - origin[1]
            )
            detectable = los & (dist <= radius)

            if obs["kind"] == "range":
                sigma = obs["sigma"]
                residual = dist - obs["distance"]
                gauss = np.exp(-(residual**2) / (2.0 * sigma**2))
                # A cell the sensor could not have reached cannot have produced
                # this reading, so it keeps only the floor probability.
                like = np.where(detectable, gauss * P_DETECT, LIKELIHOOD_FLOOR)
            else:  # "absent"
                # Silence is informative: it argues against every cell the
                # sensor was covering. This is what carves visible holes in
                # the density map around each hunter.
                like = np.where(detectable, 1.0 - P_DETECT, 1.0)

            log_like += np.log(np.maximum(like, LIKELIHOOD_FLOOR))

        # Work in log space, then shift before exponentiating to avoid
        # underflow when many sensors agree.
        log_w = np.log(np.maximum(self.weights, 1e-300)) + log_like
        log_w -= log_w.max()
        w = np.exp(log_w)
        total = w.sum()

        if total <= 0 or not np.isfinite(total):
            # Total filter divergence: every hypothesis was ruled out. Restart
            # from a uniform prior rather than propagate garbage.
            self.idx = self.rng.integers(0, self.n_free, size=self.n)
            self.weights = np.full(self.n, 1.0 / self.n)
            return

        self.weights = w / total

        if self.effective_sample_size() < self.n / 2.0:
            self.resample()

    def effective_sample_size(self) -> float:
        """ESS = 1 / sum(w^2). Falls toward 1 as weight concentrates."""
        return float(1.0 / np.sum(self.weights**2))

    def resample(self) -> None:
        """Systematic resampling, then roughening.

        Systematic resampling has lower variance than multinomial and is O(n).
        Roughening moves a small random fraction of particles to a neighbouring
        cell, which prevents the set from collapsing to a handful of duplicated
        hypotheses that can never recover from a wrong guess.
        """
        positions = (self.rng.random() + np.arange(self.n)) / self.n
        cumulative = np.cumsum(self.weights)
        cumulative[-1] = 1.0
        self.idx = self.idx[np.searchsorted(cumulative, positions)]
        self.weights = np.full(self.n, 1.0 / self.n)

        jitter = self.rng.random(self.n) < 0.08
        if jitter.any():
            j_idx = self.idx[jitter]
            counts = self.succ_count[j_idx]
            choice = (self.rng.random(j_idx.size) * counts).astype(np.int32)
            self.idx[jitter] = self.succ[j_idx, choice]

    # ------------------------------------------------------------- readouts

    def belief_grid(self) -> np.ndarray:
        """Marginal probability per cell, shaped like the arena."""
        grid_probs = np.zeros(self.n_free)
        np.add.at(grid_probs, self.idx, self.weights)
        total = grid_probs.sum()
        if total > 0:
            grid_probs /= total
        out = np.zeros((self.grid.height, self.grid.width))
        out[self.rows, self.cols] = grid_probs
        return out

    def normalised_entropy(self) -> float:
        """Shannon entropy of the belief, scaled to [0, 1].

        1.0 means the hunters know nothing beyond the map itself. 0.0 means
        they have you pinned. This is the player's real health bar.
        """
        probs = np.zeros(self.n_free)
        np.add.at(probs, self.idx, self.weights)
        total = probs.sum()
        if total <= 0:
            return 1.0
        probs /= total
        nz = probs[probs > 0]
        entropy = -np.sum(nz * np.log(nz))
        max_entropy = np.log(self.n_free)
        return float(np.clip(entropy / max_entropy, 0.0, 1.0))

    def top_hypotheses(self, k: int) -> list[tuple[tuple[int, int], float]]:
        """The k most probable cells, highest first. Feeds the auction."""
        probs = np.zeros(self.n_free)
        np.add.at(probs, self.idx, self.weights)
        total = probs.sum()
        if total > 0:
            probs /= total
        k = min(k, self.n_free)
        order = np.argpartition(probs, -k)[-k:]
        order = order[np.argsort(-probs[order])]
        return [(self.free_cells[i], float(probs[i])) for i in order]
