"""
The opponent: probability density targeting.

The AI never sees your ships. Each turn it reconstructs what is still possible
and fires where the evidence is thickest:

1. Enumerate **every legal placement** of every ship still afloat.
2. Discard any placement contradicted by what it has learned — one that covers
   a known miss, or overlaps the hull of an already-sunk ship.
3. Count how many surviving placements cover each unknown square.

That count *is* a posterior over ship locations under a uniform prior across
consistent configurations. It is why the heat map is not decoration: the colour
of a square is the number of ways a ship could still be sitting on it.

Two behaviours fall out of this rather than being coded separately:

* **Target mode.** Placements covering an unresolved hit are weighted heavily,
  so the moment you are hit the distribution collapses along the two axes
  through that square and the AI walks the hull.
* **Hunt mode.** With no live hit, the density is broad and centre-weighted,
  because more placements fit through the middle of a board than its corners.

On top of that sits **parity**: a ship of length L must cover at least one
square on every L-spaced lattice, so while the smallest survivor is length L
there is no reason to fire off-lattice. For L=2 that halves the search space at
no cost in information.
"""

from __future__ import annotations

import random

from engine.fleet import HIT, MISS, SIZE, SUNK, UNKNOWN, ShotGrid

# How much more a placement matters if it explains a hit we cannot yet account
# for. High enough that chasing a wounded ship always outranks fresh hunting.
HIT_WEIGHT = 60

DIFFICULTIES = {
    "CADET": {
        "mode": "random", "multiplier": 0.5,
        "blurb": "Fires blind. It has no idea where you are.",
    },
    "OFFICER": {
        "mode": "hunt", "multiplier": 1.0,
        "blurb": "Random search, but works outward from any hit.",
    },
    "ADMIRAL": {
        "mode": "density", "multiplier": 2.0,
        "blurb": "Full probability density over every consistent fleet layout.",
    },
}
DEFAULT_DIFFICULTY = "ADMIRAL"


class TargetingAI:
    """Chooses where to fire, and explains why."""

    def __init__(self, difficulty: str, rng: random.Random):
        self.difficulty = difficulty
        self.mode = DIFFICULTIES.get(difficulty, DIFFICULTIES[DEFAULT_DIFFICULTY])["mode"]
        self.rng = rng
        self.last_density: list[list[float]] | None = None
        self.last_reason = ""
        self.last_placements = 0

    # ------------------------------------------------------------- density

    def density_map(
        self, grid: ShotGrid, lengths: list[int]
    ) -> tuple[list[list[float]], int]:
        """Count consistent placements covering each unknown square."""
        density = [[0.0] * SIZE for _ in range(SIZE)]
        live_hits = set(grid.unresolved_hits())
        placements = 0

        for length in lengths:
            for r in range(SIZE):
                for c in range(SIZE):
                    for dr, dc in ((0, 1), (1, 0)):
                        cells = [(r + dr * i, c + dc * i) for i in range(length)]
                        if cells[-1][0] >= SIZE or cells[-1][1] >= SIZE:
                            continue
                        if not self._consistent(grid, cells):
                            continue
                        placements += 1
                        # A placement that explains existing damage is far more
                        # likely than one that does not.
                        covered = sum(1 for cell in cells if cell in live_hits)
                        weight = 1.0 + HIT_WEIGHT * covered
                        for rr, cc in cells:
                            if grid.state[rr][cc] == UNKNOWN:
                                density[rr][cc] += weight

        return density, placements

    @staticmethod
    def _consistent(grid: ShotGrid, cells: list[tuple[int, int]]) -> bool:
        """Could a ship still occupy exactly these squares?

        A placement is ruled out by a known miss or by the hull of a ship
        already sunk. Unresolved hits are allowed — indeed encouraged — because
        an undamaged ship may well be sitting there.
        """
        for rr, cc in cells:
            state = grid.state[rr][cc]
            if state == MISS or state == SUNK:
                return False
        return True

    # ------------------------------------------------------------- choosing

    def choose(self, grid: ShotGrid, lengths: list[int]) -> tuple[int, int]:
        """Pick a square to fire on."""
        options = [
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if grid.state[r][c] == UNKNOWN
        ]
        if not options:
            return 0, 0

        if self.mode == "random":
            self.last_density = None
            self.last_reason = "Firing at random."
            return self.rng.choice(options)

        if self.mode == "hunt":
            return self._hunt_and_target(grid, options)

        return self._density_shot(grid, lengths, options)

    def _hunt_and_target(
        self, grid: ShotGrid, options: list[tuple[int, int]]
    ) -> tuple[int, int]:
        """Classic behaviour: random until a hit, then probe its neighbours."""
        self.last_density = None
        live = grid.unresolved_hits()
        if live:
            neighbours = []
            for r, c in live:
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < SIZE and 0 <= nc < SIZE and grid.state[nr][nc] == UNKNOWN:
                        neighbours.append((nr, nc))
            if neighbours:
                self.last_reason = "Working outward from a hit."
                return self.rng.choice(neighbours)
        self.last_reason = "Searching at random."
        return self.rng.choice(options)

    def _density_shot(
        self,
        grid: ShotGrid,
        lengths: list[int],
        options: list[tuple[int, int]],
    ) -> tuple[int, int]:
        density, placements = self.density_map(grid, lengths)
        self.last_density = density
        self.last_placements = placements
        live = grid.unresolved_hits()

        candidates = options
        if not live and lengths:
            # Parity only applies while hunting. Once a ship is wounded, the
            # hull runs through specific squares and skipping any of them
            # would be throwing away information.
            step = min(lengths)
            if step > 1:
                lattice = [(r, c) for r, c in options if (r + c) % step == 0]
                if lattice:
                    candidates = lattice
                    self.last_reason = (
                        f"Hunting on a {step}-square lattice — no ship of length "
                        f"{step} can hide between the gaps."
                    )
        if live:
            self.last_reason = (
                f"Tracking damage at {len(live)} square"
                f"{'s' if len(live) != 1 else ''}; "
                "consistent layouts collapse around it."
            )
        elif not self.last_reason:
            self.last_reason = "No contact. Firing where most layouts overlap."

        best = max(candidates, key=lambda cell: density[cell[0]][cell[1]])
        if density[best[0]][best[1]] <= 0:
            # Every consistent placement has been exhausted (possible late in a
            # game against an unusual layout). Fall back to any open square.
            return self.rng.choice(options)
        return best

    # ------------------------------------------------------------- readouts

    def confidence(self) -> float:
        """Share of total density sitting on the single best square.

        A useful legibility signal: low means the AI is genuinely searching,
        high means it has your ship pinned.
        """
        if not self.last_density:
            return 0.0
        flat = [v for row in self.last_density for v in row]
        total = sum(flat)
        return max(flat) / total if total > 0 else 0.0
