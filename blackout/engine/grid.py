"""
Arena geometry for BLACKOUT.

The grid is the shared substrate for every AI subsystem: A* plans over it,
the particle filter maintains a distribution over its free cells, and the
sensor model uses its line-of-sight rules to decide what the hunters observe.

Coordinates are (row, col) throughout. Movement is 4-directional, which keeps
Manhattan distance an admissible and consistent A* heuristic.
"""

from __future__ import annotations

import random
from collections import deque

import numpy as np

FLOOR = 0
WALL = 1

# 4-directional movement: north, south, west, east.
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
DIRECTION_NAMES = {(-1, 0): "N", (1, 0): "S", (0, -1): "W", (0, 1): "E"}


class Grid:
    """A walkable arena with walls, generated deterministically from a seed."""

    def __init__(self, height: int, width: int, seed: int, wall_density: float = 0.22):
        self.height = height
        self.width = width
        self.seed = seed
        self.cells = np.zeros((height, width), dtype=np.int8)
        self._generate(seed, wall_density)
        self.free_cells = [
            (r, c)
            for r in range(height)
            for c in range(width)
            if self.cells[r, c] == FLOOR
        ]
        self.free_index = {cell: i for i, cell in enumerate(self.free_cells)}

    # ---------------------------------------------------------------- build

    def _generate(self, seed: int, wall_density: float) -> None:
        """Scatter rectangular obstacles, then keep only the largest region.

        Rectangles rather than per-cell noise produce corridors and sight
        lines, which is what makes hiding tactical instead of random.
        """
        rng = random.Random(seed)
        target = int(self.height * self.width * wall_density)
        placed = 0
        attempts = 0

        while placed < target and attempts < 500:
            attempts += 1
            bh = rng.randint(1, 3)
            bw = rng.randint(1, 3)
            r = rng.randint(1, max(1, self.height - bh - 1))
            c = rng.randint(1, max(1, self.width - bw - 1))
            for rr in range(r, min(r + bh, self.height - 1)):
                for cc in range(c, min(c + bw, self.width - 1)):
                    if self.cells[rr, cc] == FLOOR:
                        self.cells[rr, cc] = WALL
                        placed += 1

        self._keep_largest_region()

    def _keep_largest_region(self) -> None:
        """Flood fill every open region; wall off all but the biggest.

        Without this, map generation can strand an objective behind walls and
        make a wave unwinnable. Connectivity is a correctness requirement, not
        a nicety.
        """
        seen = np.zeros_like(self.cells, dtype=bool)
        best: list[tuple[int, int]] = []

        for r in range(self.height):
            for c in range(self.width):
                if self.cells[r, c] != FLOOR or seen[r, c]:
                    continue
                region = []
                queue = deque([(r, c)])
                seen[r, c] = True
                while queue:
                    cr, cc = queue.popleft()
                    region.append((cr, cc))
                    for dr, dc in DIRECTIONS:
                        nr, nc = cr + dr, cc + dc
                        if (
                            0 <= nr < self.height
                            and 0 <= nc < self.width
                            and not seen[nr, nc]
                            and self.cells[nr, nc] == FLOOR
                        ):
                            seen[nr, nc] = True
                            queue.append((nr, nc))
                if len(region) > len(best):
                    best = region

        keep = set(best)
        for r in range(self.height):
            for c in range(self.width):
                if self.cells[r, c] == FLOOR and (r, c) not in keep:
                    self.cells[r, c] = WALL

    # ---------------------------------------------------------------- query

    def in_bounds(self, cell: tuple[int, int]) -> bool:
        r, c = cell
        return 0 <= r < self.height and 0 <= c < self.width

    def walkable(self, cell: tuple[int, int]) -> bool:
        return self.in_bounds(cell) and self.cells[cell[0], cell[1]] == FLOOR

    def neighbors(self, cell: tuple[int, int]) -> list[tuple[int, int]]:
        r, c = cell
        out = []
        for dr, dc in DIRECTIONS:
            nxt = (r + dr, c + dc)
            if self.walkable(nxt):
                out.append(nxt)
        return out

    def has_line_of_sight(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        """Bresenham ray; any wall between the endpoints blocks the view."""
        r0, c0 = a
        r1, c1 = b
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)
        sr = 1 if r0 < r1 else -1
        sc = 1 if c0 < c1 else -1
        err = dr - dc

        while (r0, c0) != (r1, c1):
            if (r0, c0) != a and self.cells[r0, c0] == WALL:
                return False
            e2 = 2 * err
            if e2 > -dc:
                err -= dc
                r0 += sr
            if e2 < dr:
                err += dr
                c0 += sc
        return True

    def random_free_cells(
        self,
        count: int,
        rng: random.Random,
        exclude: set[tuple[int, int]] | None = None,
        min_separation: int = 0,
    ) -> list[tuple[int, int]]:
        """Sample distinct free cells, optionally spaced apart."""
        exclude = exclude or set()
        pool = [c for c in self.free_cells if c not in exclude]
        rng.shuffle(pool)
        chosen: list[tuple[int, int]] = []
        for cell in pool:
            if len(chosen) == count:
                break
            if all(manhattan(cell, other) >= min_separation for other in chosen):
                chosen.append(cell)
        # Relax the spacing constraint rather than return too few cells.
        i = 0
        while len(chosen) < count and i < len(pool):
            if pool[i] not in chosen:
                chosen.append(pool[i])
            i += 1
        return chosen


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
